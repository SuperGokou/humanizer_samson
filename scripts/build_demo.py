#!/usr/bin/env python3
"""Render the static demo from checked-in synthetic snapshots; no network or keys."""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'docs' / 'demo'


def escape(value):
    return html.escape(str(value), quote=True)


def main():
    cases = [json.loads((DEST / 'data' / f'{name}.json').read_text()) for name in ('finance', 'science')]
    md = ['# Humanizer EN · Recorded Demo', '', '[← Project overview](../../README.md) · [Offline HTML preview](index.html)', '',
          '> These are recorded API results for synthetic workflow fixtures—not real research, a live editor, or a detector benchmark. No API key is needed to view them.', '',
          '## At a glance', '', '| Fixture | Sentences | Final changes | API requests | Total tokens | Status |', '| --- | ---: | ---: | ---: | ---: | --- |']
    for case in cases:
        count = sum(s['original'] != s['revised'] for s in case['sentences'])
        md.append(f"| {case['domain']} | {len(case['sentences'])} | {count} | {len(case['calls'])} | {case['usage']['total_tokens']:,} | {case['status']} |")
    md += ['', 'The runs below use prompt `contextual-2`. Current code uses `contextual-3`, with subsequent context/provenance fixes verified offline. Token counts are recorded usage; monetary cost and external detector scores were not measured.', '']
    sections = []
    for case in cases:
        domain = case['domain']; slug = domain.lower()
        changed = sum(s['original'] != s['revised'] for s in case['sentences'])
        md += [f'## {domain}', '', f'[Original fixture](../../examples/{slug}_synthetic.md) · [Synthetic result snapshot](data/{slug}.json)', '', '| Sentence | Original | Final revision |', '| --- | --- | --- |']
        cards = []
        for n, sentence in enumerate(case['sentences'], 1):
            original, revised = sentence['original'], sentence['revised']
            state = 'Revised' if original != revised else 'Retained'
            md.append(f"| {n:02d} · {state} | {original.replace('|', '&#124;')} | {revised.replace('|', '&#124;')} |")
            cards.append(f'<div class="sentence {"changed" if state == "Revised" else ""}"><div class="number">{n:02d}<span>{state}</span></div><p>{escape(original)}</p><p>{escape(revised)}</p></div>')
        notes = ['All numbers, the placeholder citation [1], and the non-causal qualification remain in the final output.']
        if case['issues']:
            notes.append('The review stage requested a reversion. Its recorded reason was “' + case['issues'][0]['detail'] + '”. This is a model judgment, not an independently established defect; the final output conservatively retains the original.')
        else:
            notes.append('The recorded validation and final-review stages raised no issues. This is not a guarantee of semantic equivalence.')
        md += ['', *notes, '', '### Traceable style references', '', '| DOI | Source status |', '| --- | --- |']
        for ref in case['references']:
            md.append(f"| [{ref['doi'].removeprefix('https://doi.org/')} ]({ref['doi']}) | `{ref['pipeline_status']}` |")
        md += ['', 'References supplied stylistic context only; their scientific claims are not evidence for these synthetic fixtures. Full third-party paragraphs are omitted from the distributable demo.', '', '### Recorded model calls', '', '| Stage | Model |', '| --- | --- |']
        for call in case['calls']:md.append(f"| {call['stage']} | `{call['model']}` |")
        ref_html = ''.join('<li><a href="' + escape(r['doi']) + '" rel="noreferrer">' + escape(r['doi'].removeprefix('https://doi.org/')) + '</a><span>Candidate · review required</span></li>' for r in case['references'])
        calls_html = ' → '.join(escape(c['stage']) + ' <small>' + escape(c['model']) + '</small>' for c in case['calls'])
        sections.append(f'''<section id="{slug}" aria-labelledby="{slug}-title"><div class="section-head"><div><div class="eyebrow">SYNTHETIC FIXTURE / {slug.upper()}</div><h2 id="{slug}-title">{domain} <span>Recorded result</span></h2></div><a class="download" href="data/{slug}.json">View result JSON ↗</a></div>
<div class="stats"><div><strong>{changed} / 8</strong><span>sentences changed</span></div><div><strong>{len(case['calls'])}</strong><span>API requests recorded</span></div><div><strong>{case['usage']['total_tokens']:,}</strong><span>total tokens</span></div><div><strong>Complete</strong><span>workflow status</span></div></div>
<div class="comparison"><div class="table-head"><span>ID / decision</span><span>Original</span><span>Final revision</span></div>{''.join(cards)}</div>
<div class="note">{''.join('<p>'+escape(n)+'</p>' for n in notes)}</div>
<details><summary>Inspect model calls &amp; source provenance</summary><p class="calls">{calls_html}</p><ul class="refs">{ref_html}</ul><p>Style references only. Full third-party paragraphs are omitted from this demo.</p></details></section>''')
    md += ['', '## Run your own example', '', 'From a fresh checkout, try a free, local preflight:', '', '```bash', 'python3 -m humanizer rewrite examples/finance_synthetic.md \\', '  --domain Finance --output runs/demo-dry --no-retrieval --dry-run', '```', '', 'For model-backed editing, configure `.env` and follow the [quick start](../../README.md#quick-start). The development corpus is not bundled with the repository.', '', '## Open the browser preview', '', 'Download or clone the repository, then open `docs/demo/index.html` directly in a browser. GitHub renders this Markdown page but displays HTML files as source. The browser preview is static and works offline; it has no upload form or live model connection.', '', 'Regenerate the demo after updating its synthetic snapshots:', '', '```bash', 'python3 scripts/build_demo.py', '```', '']
    (DEST / 'README.md').write_text('\n'.join(md))
    css = '''*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f4f3ed;color:#172c37;font:16px/1.6 system-ui,-apple-system,sans-serif}a{color:inherit;text-underline-offset:4px}header{background:#122632;color:#f7f5ee;padding:24px max(24px,calc((100vw - 1120px)/2)) 60px}.nav{display:flex;justify-content:space-between;align-items:center;gap:24px;font-size:14px;margin-bottom:58px}.nav strong{letter-spacing:2px}.nav div{display:flex;gap:24px}.eyebrow{font-size:11px;font-weight:700;letter-spacing:2px;color:#2d7563}header .eyebrow{color:#89d3be}h1{font:clamp(38px,5vw,64px)/1.1 Georgia,serif;letter-spacing:-2px;margin:16px 0 24px;max-width:790px}header p{color:#c2d0d4;max-width:720px;font-size:17px}.pill{display:inline-block;border:1px solid #4d6b73;padding:7px 14px;border-radius:30px;font-size:12px;margin-top:10px}.wrap{max-width:1168px;margin:auto;padding:32px 24px 64px}.intro{padding:18px 22px;background:#e9ede7;border-left:3px solid #367d67;font-size:14px;margin-bottom:48px}section{scroll-margin-top:24px;margin-bottom:64px}.section-head{display:flex;align-items:center;justify-content:space-between;gap:24px;margin-bottom:20px}h2{font:38px/1.2 Georgia,serif;margin:8px 0}h2 span{display:inline-block;font:11px system-ui;color:#486556;border:1px solid #b5c7bb;border-radius:20px;padding:6px 10px;vertical-align:middle;margin-left:12px}.download{font-size:13px}.stats{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid #d7ded6;background:#fcfcf7;border-radius:12px;padding:22px 0;margin-bottom:24px}.stats div{padding:0 24px;border-right:1px solid #d7ded6}.stats div:last-child{border:0}.stats strong{display:block;font-size:25px;font-weight:550;letter-spacing:-1px}.stats span{font-size:12px;color:#61716d}.comparison{border:1px solid #d7ded6;border-radius:12px;overflow:hidden;background:#fffef9}.table-head,.sentence{display:grid;grid-template-columns:110px 1fr 1fr}.table-head{background:#e8ece5;padding:14px 20px;font-size:11px;letter-spacing:1px;text-transform:uppercase;font-weight:700}.sentence{padding:0 20px;border-top:1px solid #e3e7df;gap:0}.sentence p{padding:18px 24px 18px 0;margin:0;font-size:14px}.sentence p:last-child{padding-left:24px;border-left:1px solid #e3e7df}.sentence.changed{background:#f0f7ee}.number{padding-top:18px;font-size:12px;color:#597064}.number span{display:block;font-size:10px;margin-top:4px}.changed .number{color:#17614c;font-weight:700}.note{font-size:13px;color:#566a63;margin:16px 0}.note p{margin:8px 0}details{border-top:1px solid #d2dbd2;padding:16px 0;font-size:13px}summary{cursor:pointer;font-weight:600}.calls{line-height:2.3}small{font-size:10px;background:#e4ebe4;padding:3px 5px}.refs{padding-left:18px}.refs li{margin:12px 0}.refs span{display:block;color:#61716d;font-size:11px}footer{border-top:1px solid #cbd6cd;padding-top:22px;font-size:12px;color:#52695c}a:focus-visible,summary:focus-visible{outline:3px solid #c8752f;outline-offset:4px}@media(max-width:700px){header{padding:20px 20px 38px}.nav{margin-bottom:36px;align-items:flex-start}.nav div{gap:12px;flex-wrap:wrap;font-size:12px}.wrap{padding:22px 16px}.section-head{align-items:flex-start;flex-direction:column;gap:8px}.stats{grid-template-columns:1fr 1fr;gap:18px}.stats div:nth-child(2){border:0}.table-head{display:none}.sentence{grid-template-columns:70px 1fr;padding:0 16px}.sentence p:last-child{grid-column:2;padding:0 0 18px;border:0}.sentence p:nth-child(2):before{content:'ORIGINAL';display:block;font-size:10px;color:#687b71;margin-bottom:5px}.sentence p:last-child:before{content:'FINAL';display:block;font-size:10px;color:#33795f;margin-bottom:5px}.sentence p{padding:16px 0}h2{font-size:32px}h2 span{margin-left:5px}.stats strong{font-size:22px}}'''
    page = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Recorded synthetic academic-editing examples with traceable decisions and usage."><title>Humanizer EN · Recorded Demo</title><style>'+css+'</style></head><body>'
    page += '<header><nav class="nav" aria-label="Main navigation"><strong>HUMANIZER EN</strong><div><a href="#finance">Finance</a><a href="#science">Science</a><a href="https://github.com/SuperGokou/humanizer_samson">GitHub ↗</a></div></nav><div class="eyebrow">CONTEXT-AWARE ACADEMIC EDITING</div><h1>Every edit, in context.<br>Every decision, reviewable.</h1><p>Explore recorded synthetic examples from the editing pipeline. Compare the original with the final text, then inspect the decisions behind the result.</p><span class="pill">Recorded demo · No API calls · Works offline</span></header>'
    page += '<main class="wrap"><div class="intro"><strong>Workflow evidence, not a quality benchmark.</strong> These fixtures are synthetic. Recorded runs use prompt contextual-2; current code uses contextual-3. No AI-detector results or monetary cost estimates are claimed.</div>'+''.join(sections)+'<footer>Humanizer EN · Synthetic demonstration snapshots · No private manuscripts or API credentials included.<br>Run the CLI with your own authorized text to produce a new comparison.</footer></main></body></html>'
    (DEST / 'index.html').write_text(page)
    print('Built docs/demo/README.md and docs/demo/index.html from synthetic snapshots.')


if __name__ == '__main__':
    main()
