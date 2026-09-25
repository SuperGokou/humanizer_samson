"""Overlapping contexts with deterministic, exclusive editing ownership."""
from itertools import groupby
from statistics import median

DIMENSIONS = ('naturalness', 'clarity', 'redundancy', 'style_match', 'rewrite_need')

def make_windows(document, size=8, stride=4):
    if not 5 <= size <= 10 or not 0 < stride < size:
        raise ValueError('Window size must be 5–10 and 0 < stride < size')
    windows = []
    for key, group in groupby(document['sentences'], lambda s: (s['section_id'], s['segment_id'])):
        group = list(group)
        local, centers = [], []
        start = 0
        while start < len(group):
            chunk = group[start:start+size]
            window = {'id': f'w{len(windows)+len(local)+1:05d}', 'section_id': key[0], 'segment_id': key[1], 'sentence_ids': [s['id'] for s in chunk], 'owned_ids': []}
            local.append(window)
            centers.append(start + (len(chunk)-1)/2)
            if start + size >= len(group): break
            start += stride
        for i, s in enumerate(group):
            candidates = [j for j, w in enumerate(local) if s['id'] in w['sentence_ids']]
            owner = min(candidates, key=lambda j: (abs(i-centers[j]), j))
            local[owner]['owned_ids'].append(s['id'])
        windows.extend(local)
    return windows

def aggregate_scores(results):
    grouped = {}
    for row in results:
        grouped.setdefault(row['sentence_id'], []).append(row)
    return {sid: {**{key: median(r[key] for r in rows if key in r) for key in DIMENSIONS if any(key in r for r in rows)}, 'observations': rows} for sid, rows in grouped.items()}
