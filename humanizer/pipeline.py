"""Fixed stages, durable operation cache, bounded final review and safe fallback."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
from .client import AuthenticationError, BudgetExceeded, ProtocolError, TransientAPIError
from .output import write_json, save_outputs
from .retrieval import select_references
from .validation import validate_scores, validate_rewrites, validate_rerank, validate_review, check_invariants, check_reference_overlap
from .windows import aggregate_scores


def _hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()

@contextmanager
def _run_lock(directory,resume):
    directory.mkdir(parents=True,exist_ok=True)
    with (directory/'.lock').open('a') as handle:
        try: fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('Another process owns this output directory') from None
        try:
            existing=[p for p in directory.iterdir() if p.name!='.lock']
            if existing and not resume: raise ValueError('Output directory is not empty; use --resume or a new directory')
            if resume and not (directory/'checkpoint.json').exists(): raise ValueError('No checkpoint to resume')
            yield
        finally:fcntl.flock(handle,fcntl.LOCK_UN)


def _review_groups(sentences,replacements,limit):
    """Partition by section and size, then explicitly include every split boundary."""
    groups=[]; current=[]; length=0
    for sentence in sentences:
        cost=len(sentence['text'])+len(replacements.get(sentence['id'],sentence['text']))+150
        if cost>limit: raise ValueError('A sentence exceeds the review character budget; it cannot be silently truncated')
        if current and (length+cost>limit or current[-1]['section_id']!=sentence['section_id']):
            groups.append(current); current=[]; length=0
        current.append(sentence); length+=cost
    if current:groups.append(current)
    boundaries=[]
    for a,b in zip(groups,groups[1:]):
        pair=[a[-1],b[0]]
        if sum(len(s['text'])+len(replacements.get(s['id'],s['text']))+150 for s in pair)>limit:
            raise ValueError('A boundary pair exceeds the review character budget')
        boundaries.append(pair)
    return groups+boundaries


def run_rewrite(document,windows,index,client,options):
    known={s['id'] for s in document['sentences']}
    owned=[sid for w in windows for sid in w['owned_ids']]
    if len(owned)!=len(set(owned)) or set(owned)!=known or any(set(w['sentence_ids'])-known or set(w['owned_ids'])-set(w['sentence_ids']) for w in windows):
        raise ValueError('Invalid window sentence IDs or ownership')
    directory=Path(options['output_dir'])
    with _run_lock(directory,options['resume']):
        result=_run(document,windows,index,client,options,directory)
        save_outputs(result,directory)
        return result


def _run(document,windows,index,client,options,directory):
    manifest={key:options[key] for key in ('input_sha256','models','prompt_version','glossary','window_size','stride','domain','allow_candidates')}
    manifest.update(index_fingerprint=index.fingerprint if index else None,no_retrieval=options.get('no_retrieval',False),dry_run=options['dry_run'],review_char_limit=options.get('review_char_limit',12000))
    if manifest['input_sha256']!=document['sha256']:raise ValueError('Input hash does not match document')
    checkpoint_path=directory/'checkpoint.json'
    if options['resume']:
        checkpoint=json.loads(checkpoint_path.read_text())
        if checkpoint['cache_key']!=_hash(manifest):raise ValueError('Resume configuration or input changed; start a new output directory')
    else:
        checkpoint={'manifest':manifest,'cache_key':_hash(manifest),'operations':{},'calls':[],'completed_windows':[],'status':'pending'}
    previous_calls=list(checkpoint['calls'])
    result={'status':'dry_run' if options['dry_run'] else 'complete','document':document,'replacements':{},'scores':{},'references':{},'issues':[],'calls':previous_calls,'manifest':manifest,'windows':windows,'retrieval_diagnostics':index.diagnostics if index else []}
    observations=[]
    def persist():
        checkpoint['calls']=previous_calls+(list(client.calls) if client else [])
        write_json(checkpoint_path,checkpoint)
    if any(op['status'] in ('in_flight','uncertain') for op in checkpoint['operations'].values()):
        result['status']='uncertain'; result['issues'].append({'code':'uncertain_request','sentence_id':None,'detail':'A previous request may have completed or incurred charges. Automatic replay is disabled.'})
        # Reuse only already published output, without replaying any API request.
        if (directory/'report.json').exists():
            saved=json.loads((directory/'report.json').read_text())
            for key in ('replacements','scores','references'):result[key]=saved[key]
        return result
    if client:client.on_event=persist
    persist()
    def call(stage,model,payload):
        key=_hash({'stage':stage,'model':model,'payload':payload})
        cached=checkpoint['operations'].get(key)
        if cached and cached['status']=='completed':return cached['completion']['payload']
        if cached and cached['status']=='protocol_failure':raise ProtocolError('Previously invalid model response')
        checkpoint['operations'][key]={'stage':stage,'model':model,'status':'in_flight'}; persist()
        try:
            completion=client.complete(stage,model,payload)
        except ProtocolError:
            checkpoint['operations'][key]['status']='protocol_failure'; persist(); raise
        except TransientAPIError as exc:
            checkpoint['operations'][key]['status']='uncertain' if exc.uncertain else 'pending'; persist(); raise
        except (BudgetExceeded,AuthenticationError):
            checkpoint['operations'][key]['status']='pending'; persist(); raise
        checkpoint['operations'][key].update(status='completed',completion=completion); persist()
        return completion['payload']
    def issue(code,detail,sid=None):result['issues'].append({'code':code,'sentence_id':sid,'detail':detail})
    def titles(group):
        return {s['section_id']: document['section_titles'].get(s['section_id'], '') for s in group}
    def sentence_context(s):
        return {key: s[key] for key in ('id', 'text', 'block_id', 'section_id', 'segment_id', 'start', 'end')}
    def review(group,phase):
        payload={'section_titles':titles(group),'phase':phase,'glossary':options['glossary'],'sentences':[{'id':s['id'],'section_id':s['section_id'],'block_id':s['block_id'],'original':s['text'],'revised':result['replacements'].get(s['id'],s['text'])} for s in group]}
        return validate_review(call('review',options['models']['review'],payload),[s['id'] for s in group])
    sentences={s['id']:s for s in document['sentences']}
    degraded=False
    try:
        for window in windows:
            context=[sentences[sid] for sid in window['sentence_ids']]
            if any(sid not in window['sentence_ids'] for sid in window['owned_ids']):raise ValueError('Window owns a sentence outside its context')
            candidates=index.search(' '.join(s['text'] for s in context),options['domain']) if index else []
            if options['dry_run']:
                result['references'][window['id']]=select_references(candidates,[c['id'] for c in candidates]);continue
            refs=[]
            if candidates:
                try:
                    rerank={'section_titles':titles(context),'sentences':[sentence_context(s) for s in context],'candidates':candidates}
                    ids=validate_rerank(call('rerank',options['models']['default'],rerank),[c['id'] for c in candidates])
                    refs=select_references(candidates,ids)
                except (ProtocolError,ValueError):
                    issue('rerank_failed','Invalid reranking response; no reference was selected')
            result['references'][window['id']]=refs
            payload={'section_titles':titles(context),'sentences':[sentence_context(s) for s in context],'owned_ids':window['owned_ids'],'references':refs,'glossary':options['glossary']}
            try:
                scores=validate_scores(call('score',options['models']['default'],payload),window['sentence_ids'])
                observations.extend({**s,'window_id':window['id']} for s in scores)
            except ProtocolError:
                scores=[]; degraded=True;issue('score_failed','Invalid scores; no editorial values fabricated')
            payload={**payload,'editorial_scores':scores}
            complex_tags={'complex_argument','technical_ambiguity','numeric_association','causal_claim','meaning_risk','terminology_risk'}
            complex_window=any(complex_tags.intersection(s['risk_tags']) for s in scores) or any('$' in s['text'] or '\\(' in s['text'] or len(s['text'])>500 for s in context)
            models=[options['models']['complex']] if complex_window else [options['models']['default'],options['models']['complex']]
            if len(set(models))==1:models=models[:1]
            accepted=None
            for model in models:
                failures=[]
                try:
                    replacements=validate_rewrites(call('rewrite',model,payload),window['owned_ids'])
                    for sid,text in replacements.items():
                        failures.extend(check_invariants(sentences[sid]['text'],text,sid,options['glossary']))
                        if text!=sentences[sid]['text']:
                            failures.extend({**i,'sentence_id':sid} for i in check_reference_overlap(text,refs))
                except ProtocolError:
                    replacements={};failures=[{'code':'rewrite_protocol_failed','sentence_id':None,'detail':'Invalid rewrite shape or IDs'}]
                if not failures:accepted=replacements;break
                result['issues'].extend(failures)
                payload={**payload,'validation_issues':failures}
            if accepted is None:
                accepted={sid:sentences[sid]['text'] for sid in window['owned_ids']}
                issue('reverted_after_validation','Window-owned sentences retained after failed validation: '+window['id'])
            result['replacements'].update(accepted)
            if window['id'] not in checkpoint['completed_windows']:checkpoint['completed_windows'].append(window['id'])
            persist()
        if not options['dry_run']:
            limit=manifest['review_char_limit']
            flagged=set()
            for group in _review_groups(document['sentences'],result['replacements'],limit):
                for row in review(group,'final'):
                    flagged.update(row['sentence_ids'])
                    for sid in row['sentence_ids']:issue('review_revert',row['reason'],sid)
            affected={sentences[sid]['block_id'] for sid in flagged}
            for sid in flagged:result['replacements'][sid]=sentences[sid]['text']
            if affected:
                # Recheck the affected paragraph and its immediate neighbours together.
                positions=[i for i,s in enumerate(document['sentences']) if s['block_id'] in affected]
                selected=set(positions)
                for i in positions:
                    if i: selected.add(i-1)
                    if i+1<len(document['sentences']):selected.add(i+1)
                recheck=[s for i,s in enumerate(document['sentences']) if i in selected]
                fallback_blocks=set()
                for group in _review_groups(recheck,result['replacements'],limit):
                    for row in review(group,'after_reversion'):
                        fallback_blocks.update(sentences[sid]['block_id'] for sid in row['sentence_ids'])
                        fallback_blocks.update(affected)
                for s in document['sentences']:
                    if s['block_id'] in fallback_blocks:result['replacements'][s['id']]=s['text']
                for block in sorted(fallback_blocks):issue('paragraph_reverted','Entire original paragraph retained after recheck: '+block)
        if degraded:result['status']='incomplete'
    except TransientAPIError as exc:
        result['status']='uncertain' if exc.uncertain else 'incomplete';issue('uncertain_request' if exc.uncertain else 'api_unavailable',str(exc))
    except (BudgetExceeded,AuthenticationError,ProtocolError,ValueError) as exc:
        result['status']='incomplete';issue(type(exc).__name__,str(exc))
    finally:
        if client:client.on_event=None
    result['scores']=aggregate_scores(observations)
    checkpoint['status']=result['status'];persist()
    result['calls']=checkpoint['calls']
    result['usage_totals']={key:sum((c.get('usage') or {}).get(key,0) for c in result['calls']) for key in ('prompt_tokens','completion_tokens','total_tokens')}
    result['cost_estimate']=None
    return result
