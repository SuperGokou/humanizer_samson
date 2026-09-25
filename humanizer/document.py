"""Keep character offsets into the original document; never rebuild whitespace."""
import hashlib
import re

_ABBREVIATIONS = {'dr', 'mr', 'mrs', 'ms', 'prof', 'fig', 'figs', 'eq', 'eqs', 'vs', 'al', 'e.g', 'i.e', 'cf', 'approx', 'no'}

def sentence_spans(text):
    start = 0
    for match in re.finditer(r'[.!?。！？]+[\"\'”’»\)\]]*(?=\s|$)', text):
        punctuation = match.start()
        prefix = text[:punctuation]
        word = re.search(r'([A-Za-z.]+)$', prefix)
        if text[punctuation] == '.' and word:
            token = word.group(1).lower()
            if token in _ABBREVIATIONS or (len(token) == 1 and token.isalpha()):
                continue
        left = start + len(text[start:match.end()]) - len(text[start:match.end()].lstrip())
        if left < match.end():
            yield left, match.end()
        start = match.end()
    left = start + len(text[start:]) - len(text[start:].lstrip())
    right = len(text.rstrip())
    if left < right:
        yield left, right

def parse_document(text):
    blocks, sentences = [], []
    section, segment = 0, 0
    lines = list(re.finditer(r'.*(?:\n|$)', text))
    fence, math, references = None, False, False
    current = None
    def add(kind, start, end):
        nonlocal current
        if current and current['kind'] == kind and kind == 'prose' and current['end'] == start:
            current['end'] = end
        else:
            current = {'id': f'b{len(blocks)+1:05d}', 'section_id': f'sec{section}', 'segment_id': f'seg{segment}', 'kind': kind, 'start': start, 'end': end}
            blocks.append(current)
    for match in lines:
        if match.start() == match.end():
            continue
        raw, line = match.group(), match.group().strip()
        if fence:
            kind = 'protected'
            if re.match(re.escape(fence) + r'\s*$', line): fence = None
        elif math:
            kind = 'protected'
            if '$$' in line or '\\]' in line: math = False
        elif re.match(r'^(#{1,6})\s+', line):
            kind = 'heading'
            section += 1
            references = bool(re.match(r'^#{1,6}\s+(references|bibliography)\s*$', line, re.I))
        elif references:
            kind = 'protected'
        elif re.match(r'^(references|bibliography)\s*$', line, re.I):
            kind, references = 'protected', True
        elif re.match(r'^(`{3,}|~{3,})', line):
            kind = 'protected'
            fence = re.match(r'^(`{3,}|~{3,})', line).group()
        elif line.startswith(('$$', '\\[')):
            kind = 'protected'
            math = not (line.startswith('$$') and line.count('$$') >= 2 or line.startswith('\\[') and '\\]' in line)
        elif (not line or re.match(r'^(?:[-*+]\s|\d+[.)]\s|>|\||<!--|---+$)', line) or raw.startswith(('    ', '\t'))):
            kind = 'protected' if line else 'blank'
        else:
            kind = 'prose'
        if kind not in ('prose', 'blank'):
            segment += 1
        add(kind, match.start(), match.end())
    for block in blocks:
        if block['kind'] != 'prose':
            continue
        for a, b in sentence_spans(text[block['start']:block['end']]):
            start, end = block['start'] + a, block['start'] + b
            sentences.append({'id': f's{len(sentences)+1:06d}', 'block_id': block['id'], 'section_id': block['section_id'], 'segment_id': block['segment_id'], 'start': start, 'end': end, 'text': text[start:end]})
    return {'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest(), 'blocks': blocks, 'sentences': sentences}

def render_document(document, replacements):
    known = {s['id']: s for s in document['sentences']}
    if set(replacements) - known.keys():
        raise ValueError('Unknown sentence ID in replacements')
    result = document['text']
    for sid in sorted(replacements, key=lambda sid: known[sid]['start'], reverse=True):
        value = replacements[sid]
        if not isinstance(value, str): raise ValueError('Replacement must be text')
        s = known[sid]
        result = result[:s['start']] + value + result[s['end']:]
    return result
