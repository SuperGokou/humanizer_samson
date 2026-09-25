import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from humanizer.retrieval import StyleIndex, select_references

class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); (self.root/'index').mkdir()
        rows, catalog = [], []
        for i, (category, status) in enumerate([('Finance','review_required'), ('Science','review_required'), ('Finance','held')]):
            rid = f'p{i}'; source = f'{rid}.txt'; processed = f'{rid}.json'
            (self.root/source).write_text('bank liquidity risk')
            (self.root/processed).write_text(json.dumps({'record_id':rid, 'source_file':source, 'source_sha256':hashlib.sha256((self.root/source).read_bytes()).hexdigest(),'paragraphs':[{'id':'para1','text':'bank liquidity risk in context'}, {'id':'para2','text':'wrong context'}]}))
            catalog.append({'record_id':rid, 'processed_file':processed,'pipeline_status':status,'category':category,'doi':f'https://doi.org/10.1234/{rid}','local_file':source,'sha256':hashlib.sha256((self.root/source).read_bytes()).hexdigest()})
            rows.append({'id':f'{rid}_s1','record_id':rid,'paragraph_id':'para1','category':category,'pipeline_status':status,'doi':f'https://doi.org/10.1234/{rid}','text':'bank liquidity risk','source_file':source})
        (self.root/'catalog.json').write_text(json.dumps(catalog))
        (self.root/'index/candidate_sentences.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
    def test_explicit_candidates_and_provenance(self):
        with self.assertRaises(ValueError): StyleIndex(self.root)
        index = StyleIndex(self.root, True); hits = index.search('bank liquidity', 'Finance')
        self.assertEqual(len(hits),1); self.assertEqual(hits[0]['paragraph_text'],'bank liquidity risk in context')
        self.assertEqual(hits,index.search('bank liquidity','Finance'))
        self.assertEqual(index.search('unrelated','Finance'),[])
        with self.assertRaises(ValueError): select_references(hits,['invented'])
        self.assertEqual(len(select_references(hits*2,[hits[0]['id']]*2)),1)
    def test_broken_source_and_fingerprint(self):
        first = StyleIndex(self.root, True)
        (self.root/'p0.txt').unlink()
        second = StyleIndex(self.root, True)
        self.assertEqual(second.search('bank','Finance'),[])
        self.assertTrue(second.diagnostics)
        self.assertNotEqual(first.fingerprint,second.fingerprint)
    def test_path_traversal(self):
        path = self.root/'catalog.json'; rows=json.loads(path.read_text()); rows[0]['processed_file']='../outside.json'; path.write_text(json.dumps(rows))
        index=StyleIndex(self.root,True)
        self.assertEqual(index.search('bank','Finance'),[])
        self.assertTrue(index.diagnostics)

    def test_stale_index_cannot_override_catalog(self):
        path=self.root/'catalog.json'; rows=json.loads(path.read_text())
        rows[0].update(category='Science',doi='https://doi.org/10.1234/new',local_file='new.txt')
        (self.root/'new.txt').write_text('bank liquidity risk')
        path.write_text(json.dumps(rows))
        index=StyleIndex(self.root,True)
        self.assertEqual(index.search('bank','Finance'),[])
        self.assertTrue(index.diagnostics)

    def test_changed_source_hash_rejected(self):
        import hashlib
        catalog=self.root/'catalog.json'; rows=json.loads(catalog.read_text())
        digest=hashlib.sha256((self.root/'p0.txt').read_bytes()).hexdigest()
        rows[0]['sha256']=digest; catalog.write_text(json.dumps(rows))
        p=self.root/'p0.json'; document=json.loads(p.read_text())
        document.update(record_id='p0',source_file='p0.txt',source_sha256=digest)
        p.write_text(json.dumps(document))
        (self.root/'p0.txt').write_text('Changed original source')
        index=StyleIndex(self.root,True)
        self.assertEqual(index.search('bank','Finance'),[])
        self.assertTrue(index.diagnostics)
