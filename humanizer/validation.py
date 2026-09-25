"""Strict model contracts and conservative token-preservation checks."""
import math
import re
from .client import ProtocolError
from .document import sentence_spans, INLINE_PROTECTED
from .windows import DIMENSIONS

def _root(payload,key):
    if not isinstance(payload,dict) or set(payload)!={key} or not isinstance(payload[key],list):
        raise ProtocolError('Invalid '+key+' response shape')
    return payload[key]

def _ids(rows,expected):
    ids=[r.get('id') if isinstance(r,dict) else None for r in rows]
    if any(not isinstance(i,str) for i in ids) or len(ids)!=len(set(ids)) or set(ids)!=set(expected):
        raise ProtocolError('Response sentence IDs do not match the request')

def validate_scores(payload,expected_ids):
    rows=_root(payload,'scores'); _ids(rows,expected_ids)
    for row in rows:
        if set(row)!={'id','reason','risk_tags',*DIMENSIONS}: raise ProtocolError('Invalid score fields')
        if not isinstance(row['reason'],str) or not isinstance(row['risk_tags'],list) or any(not isinstance(v,str) for v in row['risk_tags']): raise ProtocolError('Invalid score explanation')
        for key in DIMENSIONS:
            value=row[key]
            if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=100: raise ProtocolError('Score must be finite, numeric and 0–100')
    return [{**r,'sentence_id':r['id']} for r in rows]

def validate_rewrites(payload,expected_ids):
    rows=_root(payload,'rewrites'); _ids(rows,expected_ids)
    for row in rows:
        if set(row)!={'id','text'} or not isinstance(row['text'],str) or not row['text'].strip(): raise ProtocolError('Invalid rewrite fields')
        if '\n' in row['text'] or len(list(sentence_spans(row['text'])))!=1: raise ProtocolError('Rewrite must contain exactly one sentence')
    return {r['id']:r['text'] for r in rows}

def validate_rerank(payload,expected_ids):
    if not isinstance(payload,dict) or set(payload)!={'selected_ids','reason'} or not isinstance(payload['reason'],str): raise ProtocolError('Invalid rerank shape')
    ids=payload['selected_ids']
    if not isinstance(ids,list) or len(ids)>3 or any(not isinstance(i,str) or i not in expected_ids for i in ids) or len(ids)!=len(set(ids)): raise ProtocolError('Invalid reference IDs')
    return ids

def validate_review(payload,expected_ids):
    rows=_root(payload,'issues')
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'sentence_ids','type','reason','action'}: raise ProtocolError('Invalid review issue')
        if row['action']!='revert' or not isinstance(row['type'],str) or not isinstance(row['reason'],str): raise ProtocolError('Invalid review action')
        ids=row['sentence_ids']
        if not isinstance(ids,list) or not ids or any(not isinstance(i,str) or i not in expected_ids for i in ids): raise ProtocolError('Unknown reviewed sentence')
    return rows

_NUMBER = re.compile(r'(?<![\w.])[+−-]?\d+(?:[.,]\d+)*(?:[eE][+−-]?\d+)?(?:\s*(?:%|°\s*[CF]|mL|ml|kg|mg|km|cm|mm|µm|μm|mol|mM|Hz|Pa|USD|EUR|L|g|m|s)\b|%)?')
_PROTECTED = INLINE_PROTECTED

def _numbers(text): return [re.sub(r'\s+','',m.group()) for m in _NUMBER.finditer(text)]
def _has(text,term): return len(re.findall(r'(?<!\w)'+re.escape(term)+r'(?!\w)',text,re.I))

def check_invariants(original,rewritten,sentence_id,glossary):
    issues=[]
    def issue(code,detail): issues.append({'code':code,'sentence_id':sentence_id,'detail':detail})
    if _numbers(original)!=_numbers(rewritten): issue('protected_number_changed','Signed numeric values, their units, order or multiplicity changed')
    if _PROTECTED.findall(original)!=_PROTECTED.findall(rewritten): issue('protected_expression_changed','Citation, formula or inline code changed')
    for term,variants in glossary.items():
        variants=[term]+variants
        before=sum(_has(original,t) for t in variants); after=sum(_has(rewritten,t) for t in variants)
        if before!=after: issue('glossary_changed','Protected term family changed: '+term)
    # Simple labelled quantities can be proven locally; broader associations need review.
    pattern=r'\b([A-Za-z][\w-]*)\s+(?:is|was|=)\s*([+−-]?\d+(?:\.\d+)?)'
    a=dict(re.findall(pattern,original)); b=dict(re.findall(pattern,rewritten))
    if a and a.keys()==b.keys() and a!=b: issue('numeric_association_changed','Values were reassigned to labelled entities')
    return issues

def check_reference_overlap(text,references,min_words=12):
    words=re.findall(r'\w+',text.lower()); grams={tuple(words[i:i+min_words]) for i in range(len(words)-min_words+1)}
    issues=[]
    for ref in references:
        other=re.findall(r'\w+',ref['paragraph_text'].lower())
        if any(tuple(other[i:i+min_words]) in grams for i in range(len(other)-min_words+1)):
            issues.append({'code':'reference_overlap','sentence_id':None,'detail':f'At least {min_words} consecutive words overlap reference '+ref['id']})
    return issues
