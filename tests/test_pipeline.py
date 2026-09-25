import json
import tempfile
import unittest
from pathlib import Path
from humanizer.document import parse_document, render_document
from humanizer.windows import make_windows
from humanizer.pipeline import run_rewrite
from humanizer.client import BudgetExceeded, TransientAPIError
from humanizer.prompts import PROMPT_VERSION

class FakeClient:
    def __init__(self,limit=100,bad_numbers=False,review_bad=False,uncertain=False,risk_tags=None):
        self.calls=[]; self.limit=limit; self.bad_numbers=bad_numbers; self.review_bad=review_bad; self.uncertain=uncertain; self.on_event=None; self.risk_tags=risk_tags or []
    def complete(self,stage,model,payload):
        if len(self.calls)>=self.limit: raise BudgetExceeded('Budget exhausted')
        self.calls.append({'stage':stage,'model':model,'status':'complete','usage':{'prompt_tokens':1,'completion_tokens':1}})
        if self.on_event:self.on_event()
        if self.uncertain:raise TransientAPIError('Unknown server result',True)
        if stage=='rerank': data={'selected_ids':[],'reason':'No suitable match'}
        elif stage=='score': data={'scores':[{'id':s['id'],'naturalness':50,'clarity':60,'redundancy':40,'style_match':50,'rewrite_need':50,'reason':'Verbose','risk_tags':self.risk_tags} for s in payload['sentences']]}
        elif stage=='rewrite':
            data={'rewrites':[{'id':s['id'],'text':s['text'].replace('recorded','observed').replace('12','99') if self.bad_numbers else s['text'].replace('recorded','observed')} for s in payload['sentences'] if s['id'] in payload['owned_ids']]}
        else:
            data={'issues':[{'sentence_ids':[payload['sentences'][0]['id']],'type':'coherence','reason':'Mismatch','action':'revert'}] if self.review_bad else []}
        return {'payload':data,'usage':{},'model':model,'elapsed_seconds':0,'request_id':'fake'}

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name)/'run'
        self.doc=parse_document(' '.join(f'Observation {i} is recorded.' for i in range(1,13)))
        self.options={'domain':'Finance','output_dir':self.out,'dry_run':False,'resume':False,'models':{'default':'deepseek-flash','complex':'deepseek-v4-pro','review':'deepseek-v4-pro'},'glossary':{},'allow_candidates':False,'max_calls':20,'input_sha256':self.doc['sha256'],'prompt_version':PROMPT_VERSION,'window_size':8,'stride':4,'no_retrieval':True}
    def run_it(self,client=None,doc=None,**updates):
        doc=doc or self.doc
        return run_rewrite(doc,make_windows(doc),None,client,{**self.options,'input_sha256':doc['sha256'],**updates})
    def test_resume_preserves_completed_work(self):
        first=self.run_it(FakeClient(limit=2))
        self.assertEqual(first['status'],'incomplete')
        client=FakeClient(); final=self.run_it(client,resume=True)
        self.assertEqual(final['status'],'complete')
        self.assertIn('observed',(self.out/'rewritten.md').read_text())
        self.assertEqual(len(final['calls']),5)
        self.assertEqual(len(final['scores']['s000005']['observations']),2)
        self.assertEqual(len(client.calls),3)
    def test_numeric_failure_reverts_once(self):
        result=self.run_it(FakeClient(bad_numbers=True))
        self.assertEqual(result['replacements']['s000012'],self.doc['sentences'][-1]['text'])
        self.assertTrue(any(i['code']=='reverted_after_validation' for i in result['issues']))
        self.assertEqual(sum(c['stage']=='rewrite' and c['model']=='deepseek-v4-pro' for c in result['calls']),1)
    def test_uncertain_never_replayed(self):
        self.assertEqual(self.run_it(FakeClient(uncertain=True))['status'],'uncertain')
        c=FakeClient(); self.assertEqual(self.run_it(c,resume=True)['status'],'uncertain'); self.assertFalse(c.calls)
    def test_manifest_and_output_guards(self):
        self.run_it(None,dry_run=True)
        with self.assertRaises(ValueError):self.run_it(FakeClient(),resume=True)
        with self.assertRaises(ValueError):self.run_it(None,dry_run=True)
    def test_protected_only(self):
        doc=parse_document('```\nx = 2\n```'); c=FakeClient()
        result=self.run_it(c,doc)
        self.assertEqual(result['status'],'complete'); self.assertFalse(c.calls)
        self.assertEqual((self.out/'rewritten.md').read_text(),doc['text'])
    def test_review_fallback_whole_paragraph(self):
        result=self.run_it(FakeClient(review_bad=True))
        self.assertEqual(render_document(self.doc,result['replacements']),self.doc['text'])
        self.assertTrue(any(i['code']=='paragraph_reverted' for i in result['issues']))
    def test_section_boundary_review(self):
        doc=parse_document('# A\n\nOne observation is recorded.\n\n# B\n\nAnother observation is recorded.')
        result=self.run_it(FakeClient(),doc)
        self.assertEqual(sum(c['stage']=='review' for c in result['calls']),3)

    def test_invalid_window_id(self):
        windows=make_windows(self.doc); windows[0]['sentence_ids'].append('missing')
        with self.assertRaises(ValueError):
            run_rewrite(self.doc,windows,None,FakeClient(),self.options)
    def test_changed_input_cannot_resume(self):
        self.run_it(FakeClient(limit=1))
        with self.assertRaises(ValueError):
            self.run_it(FakeClient(),parse_document('Changed input.'),resume=True)
    def test_crash_in_flight_cannot_resume(self):
        self.run_it(FakeClient(limit=1))
        path=self.out/'checkpoint.json'; state=json.loads(path.read_text())
        state['operations']['crashed']={'status':'in_flight'}; path.write_text(json.dumps(state))
        client=FakeClient(); result=self.run_it(client,resume=True)
        self.assertEqual(result['status'],'uncertain'); self.assertEqual(client.calls,[])

    def test_simple_style_flags_do_not_force_pro(self):
        result=self.run_it(FakeClient(risk_tags=['filler','boilerplate']))
        self.assertTrue(all(c['model']=='deepseek-flash' for c in result['calls'] if c['stage']=='rewrite'))

    def test_inline_formula_mutation_reverts_without_semantic_help(self):
        class FormulaClient(FakeClient):
            def complete(self,stage,model,payload):
                result=super().complete(stage,model,payload)
                if stage=='rewrite':
                    for row in result['payload']['rewrites']:row['text']=row['text'].replace('f(x)','h(x)')
                return result
        doc=parse_document('The identity $f(x). g(y)$ holds.')
        result=self.run_it(FormulaClient(),doc)
        self.assertEqual(render_document(doc,result['replacements']),doc['text'])
        self.assertTrue(any(i['code']=='protected_expression_changed' for i in result['issues']))

    def test_model_payload_contains_heading_and_paragraph_context(self):
        class CaptureClient(FakeClient):
            def __init__(self):super().__init__();self.payloads=[]
            def complete(self,stage,model,payload):
                self.payloads.append((stage,payload))
                return super().complete(stage,model,payload)
        doc=parse_document('# Hypothetical scenario\n\nThe bank defaults.\n\nThis is a simulation.')
        client=CaptureClient();self.run_it(client,doc)
        for stage,payload in client.payloads:
            self.assertEqual(payload['section_titles']['sec1'],'Hypothetical scenario',stage)
            self.assertNotEqual(payload['sentences'][0]['block_id'],payload['sentences'][1]['block_id'],stage)
