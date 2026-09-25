"""Atomic local outputs; reports contain text and provenance, never credentials."""
import csv
import html
import io
import json
import os
from pathlib import Path
import tempfile
from .document import render_document


def atomic_text(path,text):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='') as handle:
            handle.write(text); handle.flush(); os.fsync(handle.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def write_json(path,value):
    atomic_text(path,json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def save_outputs(result,output_dir):
    output_dir=Path(output_dir); output_dir.mkdir(parents=True,exist_ok=True)
    document=result['document']; replacements=result['replacements']
    atomic_text(output_dir/'rewritten.md',render_document(document,replacements))
    write_json(output_dir/'report.json',result)
    esc=lambda v:html.escape(str(v),quote=True)
    rows=[]
    for sentence in document['sentences']:
        sid=sentence['id']; original=sentence['text']; revised=replacements.get(sid,original)
        scores=result['scores'].get(sid,{})
        rows.append('<tr><th>'+esc(sid)+'</th><td>'+esc(original)+'</td><td>'+esc(revised)+'</td><td><pre>'+esc(json.dumps(scores,ensure_ascii=False,indent=2))+'</pre></td></tr>')
    sources=[]
    for window,refs in result['references'].items():
        for ref in refs:
            doi=ref.get('doi',''); label=esc(doi)
            if doi.startswith('https://doi.org/') and not any(c.isspace() for c in doi):
                label='<a rel="noreferrer" href="'+esc(doi)+'">'+label+'</a>'
            sources.append('<li>'+esc(window)+' · '+label+' · '+esc(ref.get('pipeline_status',''))+'<pre>'+esc(ref['paragraph_text'])+'</pre></li>')
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Academic rewrite comparison</title><style>body{font:16px/1.5 system-ui;margin:2rem;color:#172330}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd4db;padding:1rem;vertical-align:top}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}td{width:30%}.status{padding:1rem;background:#eef3f7}a{color:#1859a0}</style><h1>Academic rewrite comparison</h1>'''
    page+='<p class="status">Status: '+esc(result['status'])+'. Editorial scores are not AI detector probabilities. Candidate references require human review.</p>'
    page+='<table><thead><tr><th>ID</th><th>Original</th><th>Revised</th><th>Editorial assessment</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table>'
    page+='<h2>Full original</h2><pre>'+esc(document['text'])+'</pre><h2>Full revised</h2><pre>'+esc(render_document(document,replacements))+'</pre><h2>References</h2><ul>'+''.join(sources)+'</ul><h2>Issues and reversions</h2><pre>'+esc(json.dumps(result['issues'],ensure_ascii=False,indent=2))+'</pre></html>'
    atomic_text(output_dir/'comparison.html',page)
    # Preserve user-entered detector results on resume.
    if not (output_dir/'evaluation.csv').exists():
        buffer=io.StringIO(); writer=csv.DictWriter(buffer,fieldnames=['variant','domain','detector','detector_score','checked_at','notes'])
        writer.writeheader()
        for variant in ('original','rewritten'):writer.writerow({'variant':variant,'domain':result['manifest']['domain']})
        atomic_text(output_dir/'evaluation.csv',buffer.getvalue())
