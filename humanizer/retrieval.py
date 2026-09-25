"""Local domain-filtered BM25 over provenance-checked sentence records."""
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re


def tokens(text):
    return re.findall(r'[a-z]+(?:\'[a-z]+)?|\d+(?:\.\d+)?', text.lower())


def internal(root, value):
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Corpus path escapes root')
    return path


class StyleIndex:
    def __init__(self, corpus_root, allow_candidates=False):
        root = Path(corpus_root).resolve()
        self.diagnostics, self.rows = [], {}
        self.postings = defaultdict(lambda: defaultdict(dict))
        self.lengths = defaultdict(dict)
        digest = hashlib.sha256()
        catalog_path = root/'catalog.json'
        raw = catalog_path.read_bytes(); digest.update(raw)
        catalog = {r['record_id']: r for r in json.loads(raw) if 'record_id' in r}
        paths = [root/'index/ready_sentences.jsonl']
        if allow_candidates: paths.append(root/'index/candidate_sentences.jsonl')
        allowed = {'ready', 'review_required'} if allow_candidates else {'ready'}
        docs, failed = {}, set()
        for path in paths:
            if not path.exists(): continue
            raw = path.read_bytes(); digest.update(raw)
            for line in raw.decode().splitlines():
                row = json.loads(line); rid = row.get('record_id')
                record = catalog.get(rid, {})
                if row.get('pipeline_status') not in allowed or record.get('pipeline_status') not in allowed:
                    continue
                if rid in failed: continue
                try:
                    for field in ('category', 'doi', 'pipeline_status'):
                        if row.get(field) != record.get(field):
                            raise ValueError('Stale indexed ' + field)
                    for field in ('year', 'journal'):
                        if field in record and row.get(field) != record[field]:
                            raise ValueError('Stale indexed ' + field)
                    if row.get('source_file') != record.get('local_file'):
                        raise ValueError('Stale indexed source identity')
                    if rid not in docs:
                        processed = internal(root, record['processed_file'])
                        source = internal(root, row['source_file'])
                        if not source.is_file(): raise ValueError('Missing original source')
                        data = processed.read_bytes(); digest.update(data)
                        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
                        digest.update(source_hash.encode())
                        doc = json.loads(data)
                        if doc.get('record_id') != rid or doc.get('source_file') != row['source_file']:
                            raise ValueError('Processed provenance does not match catalog')
                        if doc.get('source_sha256') != source_hash or record.get('sha256') != source_hash:
                            raise ValueError('Source content changed; organize the corpus again')
                        docs[rid] = {p['id']: p['text'] for p in doc['paragraphs']}
                    paragraph = docs[rid][row['paragraph_id']]
                    if row['text'] not in paragraph: raise ValueError('Sentence does not match paragraph')
                except (ValueError, KeyError, OSError) as exc:
                    failed.add(rid)
                    self.diagnostics.append({'record_id': rid, 'issue': type(exc).__name__})
                    digest.update(f'broken:{rid}'.encode())
                    continue
                row = {**row, 'paragraph_text': paragraph}
                sid, domain = row['id'], row['category']
                if sid in self.rows: continue
                self.rows[sid] = row
                terms = Counter(tokens(row['text']))
                self.lengths[domain][sid] = sum(terms.values())
                for term, count in terms.items(): self.postings[domain][term][sid] = count
        self.fingerprint = digest.hexdigest()
        self.means = {domain: sum(lengths.values())/len(lengths) or 1 for domain, lengths in self.lengths.items()}
        if not self.rows:
            raise ValueError('No usable style sentences. Review the corpus or explicitly use --allow-candidates.')

    def search(self, query, domain, limit=20):
        if limit < 1: return []
        scores = defaultdict(float)
        lengths = self.lengths.get(domain, {})
        n = len(lengths)
        if not n: return []
        for term in sorted(set(tokens(query))):
            posting = self.postings[domain].get(term, {})
            idf = math.log(1 + (n-len(posting)+0.5)/(len(posting)+0.5))
            for sid, tf in posting.items():
                scores[sid] += idf*tf*2.5/(tf+1.5*(0.25+0.75*lengths[sid]/self.means[domain]))
        return [{**self.rows[sid], 'score': scores[sid]} for sid in sorted(scores, key=lambda s: (-scores[s], s))[:limit]]


def select_references(candidates, selected_ids, limit=3):
    known = {c['id']: c for c in candidates}
    if any(sid not in known for sid in selected_ids): raise ValueError('Reranker selected unknown reference')
    result, seen = [], set()
    for sid in selected_ids:
        row = known[sid]; source = row.get('doi') or row['record_id']
        if source not in seen:
            seen.add(source); result.append(row)
        if len(result) == limit: break
    return result
