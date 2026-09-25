"""Keep character offsets into the original document; never rebuild whitespace."""
import hashlib
import re

# Shared with hard validation: these spans must remain whole during segmentation.
INLINE_PROTECTED = re.compile(r'\$[^$\n]+\$|\\\(.*?\\\)|\[[^\]\n]+\]|\([^()\n]*(?:19|20)\d{2}[a-z]?[^()\n]*\)|`[^`\n]+`')

_ABBREVIATIONS = {'dr', 'mr', 'mrs', 'ms', 'prof', 'fig', 'figs', 'eq', 'eqs', 'vs', 'al', 'e.g', 'i.e', 'cf', 'approx', 'no'}

def sentence_spans(text):
    start = 0
    protected = [(m.start(), m.end()) for m in INLINE_PROTECTED.finditer(text)]
    for match in re.finditer(r'[.!?。！？]+[\"\'”’»\)\]]*(?=\s|$)', text):
        if any(a <= match.start() < b for a, b in protected):
            continue
        punctuation = match.start()
        prefix = text[:punctuation]
        word = re.search(r'([A-Za-z.]+)$', prefix)
        if text[punctuation] == '.' and word:
            token = word.group(1).lower()
            is_unit = bool(re.search(r'\d\s*°?\s*[A-Za-z]$', prefix))
            if token in _ABBREVIATIONS or (len(token) == 1 and token.isalpha() and not is_unit):
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
    section_titles, heading_stack = {'sec0': ''}, []
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
            heading = re.match(r'^(#{1,6})\s+(.+?)\s*#*$', line)
            level, title = len(heading[1]), heading[2]
            heading_stack = [(depth, text) for depth, text in heading_stack if depth < level]
            heading_stack.append((level, title))
            section_titles[f'sec{section}'] = ' / '.join(title for _, title in heading_stack)
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
    return {'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest(), 'blocks': blocks, 'sentences': sentences, 'section_titles': section_titles}

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
