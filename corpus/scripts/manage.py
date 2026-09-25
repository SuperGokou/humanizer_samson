#!/usr/bin/env python3
"""Incremental local corpus manager. Catalog is authoritative; exports are derived."""
import argparse, collections, contextlib, copy, csv, datetime, fcntl, hashlib, io, json, os
import pathlib, re, shutil, subprocess, sys, tempfile, unicodedata
from urllib.parse import unquote
from lxml import etree

GROUPS = ('Science','Technology','Engineering','Mathematics','Finance')
VERSION = '1.0'
DEFAULT_CONFIG = {'cutoff_year':2021, 'language':'en'}

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def digest(data): return hashlib.sha256(data).hexdigest()
def dumps(value): return json.dumps(value, ensure_ascii=False, indent=2)+'\n'
def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.'+path.name, dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
def doi(value):
    value = unquote(str(value or '')).strip()
    value = re.sub(r'^(?:https?://(?:dx\.)?doi.org/|doi:\s*)','',value,flags=re.I).lower()
    if value and not re.fullmatch(r'10\.\d{4,9}/\S+',value): raise ValueError('Invalid DOI: '+value)
    return 'https://doi.org/'+value if value else ''
def normalized_title(value): return re.sub(r'\W+','',unicodedata.normalize('NFKC',str(value)).lower())
def internal(root, rel):
    path=(root/rel).resolve()
    if not path.is_relative_to(root.resolve()): raise ValueError('Catalog path outside corpus: '+str(rel))
    return path

def normalize(row):
    row=copy.deepcopy(row); row['doi']=doi(row.get('doi'))
    row.setdefault('category','Unclassified')
    if row['category'] not in GROUPS: row['category']='Unclassified'
    try: row['year']=int(row.get('year') or str(row.get('publication_date',''))[:4])
    except (ValueError,TypeError): row['year']=None
    if not row.get('record_id'):
        key=row['doi'] or row.get('sha256') or row.get('openalex_id')
        if not key: raise ValueError('Record requires a DOI, OpenAlex ID, or attached file')
        row['record_id']='paper_'+digest(key.encode())[:20]
    row.setdefault('download_status','metadata_only')
    return row

def save(root, before, rows, action):
    if before==rows: return False
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    snapshot=root/'snapshots'/stamp
    atomic(snapshot/'catalog.json',dumps(before))
    atomic(snapshot/'change.json',dumps({'action':action,'at':now(),'before_records':len(before),'after_records':len(rows),'after_sha256':digest(dumps(rows).encode())}))
    atomic(root/'catalog.json',dumps(rows))
    with (root/'history.jsonl').open('a',encoding='utf-8') as f:
        f.write(json.dumps({'at':now(),'action':action,'snapshot':str(snapshot.relative_to(root)),'records':len(rows)},ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
    return True

@contextlib.contextmanager
def locked(root):
    root.mkdir(parents=True,exist_ok=True)
    with (root/'.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        yield

def xml_tree(path):
    return etree.parse(str(path),etree.XMLParser(resolve_entities=False,no_network=True,recover=False,remove_comments=True,remove_pis=True)).getroot()
def xml_meta(path):
    root=xml_tree(path)
    def first(expr):
        nodes=root.xpath(expr)
        return ' '.join(nodes[0].itertext()).strip() if nodes else ''
    return {k:v for k,v in {
        'doi':first('./front/article-meta/article-id[@pub-id-type="doi"]'),
        'title':first('./front/article-meta/title-group/article-title'),
        'journal':first('./front/journal-meta/journal-title-group/journal-title'),
        'year':first('./front/article-meta/pub-date/year'),
        'language':root.get('{http://www.w3.org/XML/1998/namespace}lang',''),
        'fulltext_license_evidence':' '.join(etree.tostring(x,encoding='unicode') for x in root.xpath('./front/article-meta/permissions/license')),
    }.items() if v}

def read_input(path, category=None, offline=False):
    if path.is_dir():
        out=[]
        for child in sorted(path.iterdir()):
            if child.name.startswith('.') or child.suffix.lower() not in ('.pdf','.xml','.csv','.json','.txt'): continue
            if child.suffix.lower()=='.json' and any(child.with_suffix(ext).exists() for ext in ('.pdf','.xml')):continue
            out.extend(read_input(child,category,offline))
        return out
    ext=path.suffix.lower()
    if ext in ('.pdf','.xml'):
        meta=xml_meta(path) if ext=='.xml' else {}
        side=path.with_suffix('.json')
        user=json.loads(side.read_text()) if side.exists() else {}
        if not isinstance(user,dict):raise ValueError('Sidecar must be a JSON object')
        if meta.get('doi') and user.get('doi') and doi(meta['doi'])!=doi(user['doi']):raise ValueError('DOI conflict between XML and sidecar')
        meta.update(user)
        if category and meta.get('category') in (None,'','Unclassified'):meta['category']=category
        meta['sha256']=digest(path.read_bytes());meta['_source']=str(path.resolve());meta['_import_source']=str(path.resolve())
        return [normalize(meta)]
    if ext=='.csv': data=list(csv.DictReader(path.open(encoding='utf-8-sig',newline='')))
    elif ext=='.json':
        data=json.loads(path.read_text(encoding='utf-8-sig'));data=data if isinstance(data,list) else [data]
    elif ext=='.txt':
        data=[]
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if not line.strip() or line.lstrip().startswith('#'):continue
            d=doi(line); item={'doi':d}
            if not offline:
                try:item.update(enrich(d))
                except Exception as exc:item['enrichment_error']=str(exc)
            data.append(item)
    else:raise ValueError('Supported inputs: directory, CSV, JSON, DOI TXT, PDF, XML')
    out=[]
    for item in data:
        if not isinstance(item,dict):raise ValueError('Each record must be a JSON object')
        item=dict(item)
        if category and item.get('category') in (None,'','Unclassified'):item['category']=category
        if item.get('local_file'):
            source=(path.parent/item.pop('local_file')).resolve()
            if not source.is_file():raise ValueError('Attachment not found: '+str(source))
            item['_source']=str(source);item['sha256']=digest(source.read_bytes())
            if source.suffix.lower()=='.xml':
                for k,v in xml_meta(source).items():
                    if item.get(k) in (None,''):item[k]=v
        item['_import_source']=str(path.resolve())
        out.append(normalize(item))
    return out

def merge(rows,incoming,root):
    rows=copy.deepcopy(rows); copies=[]; changes=collections.Counter()
    for item in incoming:
        item=copy.deepcopy(item);source=item.pop('_source',None);origin=item.pop('_import_source',None)
        match=next((r for r in rows if (item.get('doi') and r.get('doi')==item['doi']) or (item.get('sha256') and r.get('sha256')==item['sha256']) or r['record_id']==item['record_id']),None)
        if match and match.get('doi') and item.get('doi') and match['doi']!=item['doi']:raise ValueError('Same file has conflicting DOI')
        if not match:
            match={'record_id':item['record_id'],'created_at':now()};rows.append(match);changes['added']+=1
        before=copy.deepcopy(match)
        if origin and origin not in match.get('import_sources',[]):match.setdefault('import_sources',[]).append(origin)
        # Automated imports fill gaps; never replace existing metadata or human decisions.
        for key,value in item.items():
            if key in ('record_id','manual_review','pipeline_status','processed_file','processing','local_file','text_file'):continue
            if match.get(key) in (None,'',[],{}) or (key=='category' and match.get(key)=='Unclassified'):match[key]=value
        if source:
            source=pathlib.Path(source);sha=digest(source.read_bytes())
            if not match.get('local_file') or match.get('sha256')!=sha:
                if match.get('local_file'):
                    match.setdefault('asset_versions',[]).append({k:match.get(k) for k in ('local_file','sha256','download_url')})
                dest=pathlib.Path('fulltext/imported')/(sha+source.suffix.lower())
                copies.append((source,root/dest));match.update(local_file=str(dest),sha256=sha,download_status='downloaded_'+source.suffix[1:].lower())
                match.pop('processing',None);match.pop('processed_file',None)
            if source.suffix.lower()=='.xml':
                xm=xml_meta(source)
                if xm.get('doi') and match.get('doi') and doi(xm['doi'])!=match['doi']:raise ValueError('Attachment DOI mismatch')
                if xm.get('doi'):match['identity_verification']='doi_in_xml'
                if xm.get('fulltext_license_evidence'):match['fulltext_license_evidence']=xm['fulltext_license_evidence']
        if match!=before:match['updated_at']=now();changes['changed']+=1
    # All validation occurs before copying or saving the catalog.
    for source,dest in copies:
        dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():shutil.copyfile(source,dest)
    return rows,dict(changes)

def license_state(row):
    evidence=row.get('fulltext_license_evidence','').lower()
    if re.search(r'creativecommons.org/licenses/by-(?:nc|nd|sa)',evidence) or 'License restriction found' in row.get('reuse_review','') or row.get('ingestion_status')=='excluded_until_license_review':return 'restricted'
    if 'creativecommons.org/licenses/by/' in evidence or 'creativecommons.org/publicdomain/zero/' in evidence:return 'verified'
    return 'unknown'

def extract_xml(path):
    tree=xml_tree(path);body=tree.find('body')
    if body is None:raise ValueError('XML contains no body')
    paragraphs=[];formulas=[]
    def render(node):
        text=node.text or ''
        for child in node:
            tag=etree.QName(child).localname
            if tag in ('inline-formula','disp-formula','math','tex-math'):
                fid='FORMULA_'+str(len(formulas)+1);formulas.append({'id':fid,'source':etree.tostring(child,encoding='unicode')});text+='['+fid+']'
            else:text+=render(child)
            text+=child.tail or ''
        return text
    for node in body.xpath('.//p | .//disp-formula'):
        if any(etree.QName(a).localname in ('fig','table-wrap','ref-list','p','disp-formula') for a in node.iterancestors()):continue
        section='Body'
        for a in node.iterancestors('sec'):
            if a.find('title') is not None:section=' '.join(a.find('title').itertext());break
        if etree.QName(node).localname=='disp-formula':
            fid='FORMULA_'+str(len(formulas)+1);formulas.append({'id':fid,'source':etree.tostring(node,encoding='unicode')});text='['+fid+']'
        else:text=render(node)
        text=re.sub(r'\s+',' ',text).strip()
        if text:paragraphs.append({'section':section,'text':text,'source_xpath':tree.getroottree().getpath(node),'kind':'formula' if etree.QName(node).localname=='disp-formula' else 'prose'})
    return paragraphs,formulas,[]

def extract_pdf(path):
    p=subprocess.run(['pdftotext','-layout',str(path),'-'],capture_output=True,text=True,timeout=90)
    if p.returncode:raise ValueError('pdftotext failed: '+p.stderr[:200])
    if len(p.stdout.strip())<100:raise ValueError('OCR required: insufficient extractable text')
    pages=p.stdout.split('\f');lines=[];edges=collections.Counter()
    for page in pages:
        ls=[x.strip() for x in page.splitlines() if x.strip()]
        for x in set(ls[:2]+ls[-2:]):
            if len(x)<160:edges[x]+=1
    repeated={x for x,n in edges.items() if n>=max(3,len(pages)//2)}
    paragraphs=[];section='Body';in_refs=False
    for page_no,page in enumerate(pages,1):
        for block in re.split(r'\n\s*\n',page):
            kept=[x.strip() for x in block.splitlines() if x.strip() and x.strip() not in repeated and not re.fullmatch(r'\d+',x.strip())]
            text=' '.join(kept).strip()
            if not text:continue
            if re.match(r'^(?:\d+[. ]+)?(?:references|bibliography)\s*$',text,re.I):in_refs=True
            if in_refs:continue
            if len(text)<85 and re.match(r'^(?:\d+[.\d ]+)?(?:introduction|methods|materials and methods|results|discussion|conclusions?|abstract)\b',text,re.I):section=text;continue
            paragraphs.append({'section':section,'text':text,'page':page_no,'kind':'prose'})
    return paragraphs,[],['pdf_layout_and_formulas_require_review']

def sentences(text):
    # Conservative boundaries: decimals and common abbreviations remain intact.
    parts=re.split(r'(?<=[.!?])\s+(?=[A-Z])',text);out=[]
    for part in parts:
        if out and re.search(r'\b(?:Fig|Figs|Eq|Eqs|Dr|Prof|Mr|Mrs|vs|et al|e\.g|i\.e)\.$',out[-1]):out[-1]+=' '+part
        else:out.append(part)
    return out

def status(row,config):
    review=row.get('manual_review',{})
    if row.get('is_retracted'):return 'retracted'
    if review.get('decision') in ('hold','reject'):return 'held'
    if row.get('year') and row['year']>config['cutoff_year']:return 'out_of_scope'
    if row.get('language') and row['language']!=config['language']:return 'out_of_scope'
    if not row.get('local_file'):return 'metadata_only'
    if row.get('processing_error'):
        return 'integrity_error' if 'hash' in row['processing_error'].lower() else 'processing_error'
    if not row.get('processed_file'):return 'processing_pending'
    if license_state(row)!='verified':return 'license_review'
    if not row.get('doi') or not row.get('year') or not row.get('language') or not row.get('title') or row['category'] not in GROUPS:return 'metadata_review'
    if not row.get('identity_verification') or row['identity_verification']=='pending':return 'identity_review'
    if review.get('decision')!='approve' or review.get('source_sha256')!=row.get('sha256'):return 'review_required'
    return 'ready'

def organize(root,rows,config):
    counts=collections.Counter()
    for row in rows:
        if row.get('local_file'):
            try:
                path=internal(root,row['local_file']);sha=digest(path.read_bytes())
                if row.get('sha256') and sha!=row['sha256']:raise ValueError('File hash mismatch; original must be restored')
                row.setdefault('sha256',sha)
                signature=digest((sha+VERSION).encode());processed=root/'processed'/row['record_id']/'document.json'
                if row.get('processing',{}).get('signature')!=signature or not processed.exists():
                    paragraphs,formulas,warnings=extract_xml(path) if path.suffix.lower()=='.xml' else extract_pdf(path)
                    if not paragraphs:raise ValueError('No body paragraphs extracted')
                    chunks=[]
                    for n,p in enumerate(paragraphs,1):
                        p['id']=row['record_id']+'_p'+str(n)
                        if p['kind']=='prose':
                            for i,s in enumerate(sentences(p['text']),1):chunks.append({'id':p['id']+'_s'+str(i),'paragraph_id':p['id'],'section':p['section'],'text':s,'source_xpath':p.get('source_xpath'),'page':p.get('page')})
                    doc={'record_id':row['record_id'],'source_file':row['local_file'],'source_sha256':sha,'processor_version':VERSION,'paragraphs':paragraphs,'sentences':chunks,'formulas':formulas,'warnings':warnings}
                    atomic(processed,dumps(doc));atomic(processed.with_name('body.txt'),'\n\n'.join(p['text'] for p in paragraphs)+'\n')
                    row.update(processed_file=str(processed.relative_to(root)),processing={'signature':signature,'version':VERSION,'paragraphs':len(paragraphs),'sentences':len(chunks),'formulas':len(formulas),'warnings':warnings})
                    counts['processed']+=1
                else:counts['skipped_unchanged']+=1
                row.pop('processing_error',None)
            except Exception as exc:row['processing_error']=str(exc);counts['errors']+=1
        row['pipeline_status']=status(row,config)
    return dict(counts)

def export(root,rows):
    report=root/'reports';report.mkdir(exist_ok=True)
    columns=list(dict.fromkeys(k for r in rows for k in r))
    def csv_text(items):
        f=io.StringIO();w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
        for r in items:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})
        return '\ufeff'+f.getvalue()
    atomic(root/'catalog.csv',csv_text(rows));by_group={}
    for group in (*GROUPS,'Unclassified'):
        items=[r for r in rows if r['category']==group];by_group[group]={'records':len(items),'fulltext':sum(bool(r.get('local_file')) for r in items),'statuses':dict(collections.Counter(r.get('pipeline_status','not_processed') for r in items))}
        atomic(root/(group+'.csv'),csv_text(items))
        lines=['# '+group+' — '+str(len(items))+' records','']
        for r in items:lines+=['- ['+str(r.get('title') or r.get('doi') or r['record_id']).replace('[','(').replace(']',')')+']('+str(r.get('doi') or '#')+') — '+str(r.get('year') or '?')+' · '+r.get('pipeline_status','not_processed')]
        atomic(root/'reading_lists'/(group+'.md'),'\n'.join(lines)+'\n')
    summary={'total':len(rows),'fulltext':sum(bool(r.get('local_file')) for r in rows),'processed':sum(bool(r.get('processed_file')) and not r.get('processing_error') for r in rows),'statuses':dict(collections.Counter(r.get('pipeline_status','not_processed') for r in rows)),'groups':by_group}
    candidate_lines=[]; ready_lines=[]
    for r in rows:
        if r.get('pipeline_status') not in ('review_required','ready') or not r.get('processed_file'):continue
        doc=json.loads(internal(root,r['processed_file']).read_text())
        for chunk in doc['sentences']:
            entry=chunk|{'record_id':r['record_id'],'doi':r.get('doi'),'category':r['category'],'year':r.get('year'),'journal':r.get('journal'),'pipeline_status':r['pipeline_status'],'source_file':r.get('local_file')}
            line=json.dumps(entry,ensure_ascii=False)+'\n';candidate_lines.append(line)
            if r['pipeline_status']=='ready':ready_lines.append(line)
    atomic(root/'index/candidate_sentences.jsonl',''.join(candidate_lines))
    atomic(root/'index/ready_sentences.jsonl',''.join(ready_lines))
    summary.update(candidate_sentences=len(candidate_lines),ready_sentences=len(ready_lines))
    atomic(report/'summary.json',dumps(summary))
    review=[{k:r.get(k) for k in ('record_id','doi','title','category','pipeline_status','processing_error','manual_review')} for r in rows if r.get('pipeline_status')!='ready']
    atomic(report/'review_queue.json',dumps(review));atomic(report/'ready.json',dumps([r for r in rows if r.get('pipeline_status')=='ready']))
    refs=[]
    for r in rows:
        fields={'title':r.get('title',''),'author':str(r.get('authors','')).replace('; ',' and '),'journal':r.get('journal',''),'year':r.get('year') or '', 'doi':r.get('doi','').removeprefix('https://doi.org/')}
        refs.append('@article{'+r['record_id']+',\n'+',\n'.join('  '+k+' = {'+str(v).replace('{','').replace('}','')+'}' for k,v in fields.items())+'\n}')
    atomic(root/'references.bib','\n\n'.join(refs)+'\n')
    referenced={str(internal(root,r[k])) for r in rows for k in ('local_file','text_file') if r.get(k)}
    for r in rows:
        referenced.update(str(internal(root,a['local_file'])) for a in r.get('asset_versions',[])+r.get('additional_files',[]) if a.get('local_file'))
    unreferenced=[str(p.relative_to(root)) for p in (root/'fulltext').rglob('*') if p.is_file() and str(p.resolve()) not in referenced]
    atomic(report/'unreferenced_files.json',dumps(unreferenced))
    titles=collections.defaultdict(list)
    for r in rows:
        if r.get('title'):titles[normalized_title(r['title'])].append(r['record_id'])
    atomic(report/'possible_duplicates.json',dumps([v for v in titles.values() if len(v)>1]))
    lines=['# 当前语料库状态','',f"记录 {len(rows)}；全文 {summary['fulltext']}；已解析 {summary['processed']}。",'', '| 学科 | 记录 | 全文 |','|---|---:|---:|']
    lines.extend(f"| {g} | {v['records']} | {v['fulltext']} |" for g,v in by_group.items())
    lines+=['','状态：'+json.dumps(summary['statuses'],ensure_ascii=False),'','自动整理不会替代人工学科、文章类型、许可和质量复核。ready 需显式批准，且满足年份、许可、身份和解析条件。']
    atomic(report/'STATUS.md','\n'.join(lines)+'\n')
    return summary

def enrich(d):
    import requests
    response=requests.get('https://api.openalex.org/works/'+d,timeout=30);response.raise_for_status();w=response.json()
    p=w.get('primary_location') or {};t=w.get('primary_topic') or {};f=str(t.get('field',{}).get('id','')).rsplit('/',1)[-1];sf=str(t.get('subfield',{}).get('id','')).rsplit('/',1)[-1]
    category='Finance' if sf=='2003' else 'Technology' if f=='17' else 'Mathematics' if f=='26' else 'Engineering' if f in ('22','15','21','25') else 'Science' if f in ('11','13','16','19','23','31') else 'Unclassified'
    return {'doi':d,'title':w.get('title'),'openalex_id':w.get('id'),'year':w.get('publication_year'),'publication_date':w.get('publication_date'),'journal':(p.get('source') or {}).get('display_name'),'language':w.get('language'),'category':category,'license':p.get('license'),'authors':'; '.join(a['author']['display_name'] for a in w.get('authorships',[])),'pdf_urls':' | '.join(dict.fromkeys(l['pdf_url'] for l in w.get('locations',[]) if l.get('pdf_url') and l.get('is_oa') and l.get('license') in ('cc-by','cc0') and l.get('version')=='publishedVersion')),'metadata_source':'OpenAlex','metadata_retrieved_at':now(),'is_retracted':w.get('is_retracted',False)}

def fetch(root,rows,limit):
    import requests
    result=collections.Counter()
    for row in [r for r in rows if not r.get('local_file') and r.get('doi')][:limit]:
        errors=[];d=row['doi'];options=[]
        try:
            remote=enrich(d)
            for k,v in remote.items():
                if row.get(k) in (None,'',[],{}):row[k]=v
            response=requests.get('https://www.ebi.ac.uk/europepmc/webservices/rest/search',params={'query':'DOI:"'+d.removeprefix('https://doi.org/')+'"','format':'json'},timeout=30);response.raise_for_status()
            for x in response.json().get('resultList',{}).get('result',[]):
                if x.get('pmcid') and x.get('isOpenAccess')=='Y' and doi(x.get('doi'))==d:options.append(('xml','https://www.ebi.ac.uk/europepmc/webservices/rest/'+x['pmcid']+'/fullTextXML'))
        except Exception as exc:errors.append(str(exc))
        options.extend(('pdf',u) for u in row.get('pdf_urls','').split(' | ') if u)
        for ext,url in options[:4]:
            try:
                r=requests.get(url,timeout=(10,45));r.raise_for_status()
                if ext=='pdf' and not r.content.startswith(b'%PDF-'):raise ValueError('Response is not a PDF')
                with tempfile.TemporaryDirectory() as tmp:
                    p=pathlib.Path(tmp)/('article.'+ext);p.write_bytes(r.content)
                    items=read_input(p,row['category'],True)
                    if items[0].get('doi') and items[0]['doi']!=d:raise ValueError('Downloaded DOI mismatch')
                    items[0]['doi']=d
                    merged,_=merge([row],items,root);row.clear();row.update(merged[0]);row['download_url']=r.url
                result['downloaded']+=1;break
            except Exception as exc:errors.append(url+' => '+str(exc))
        else:result['unavailable']+=1
        row['download_errors']='; '.join(errors);row['last_fetch_at']=now()
        print('fetch',d,'downloaded' if row.get('local_file') else 'unavailable',flush=True)
    return dict(result)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=pathlib.Path,default=pathlib.Path(__file__).resolve().parents[1]);sub=p.add_subparsers(dest='command',required=True)
    ip=sub.add_parser('import');ip.add_argument('path',type=pathlib.Path);ip.add_argument('--category',choices=GROUPS);ip.add_argument('--offline',action='store_true')
    for name in ('organize','report','audit'):sub.add_parser(name)
    fp=sub.add_parser('fetch');fp.add_argument('--limit',type=int,default=20)
    rp=sub.add_parser('review');rp.add_argument('doi_or_id');rp.add_argument('--decision',choices=('approve','hold','reject','pending'),required=True);rp.add_argument('--note',required=True)
    args=p.parse_args(argv);root=args.root.resolve()
    try:
        with locked(root):
            catalog=root/'catalog.json';before=json.loads(catalog.read_text()) if catalog.exists() else []
            rows=[normalize(r) for r in before];config=DEFAULT_CONFIG| (json.loads((root/'config.json').read_text()) if (root/'config.json').exists() else {})
            result={}
            if args.command=='import':rows,result=merge(rows,read_input(args.path.resolve(),args.category,args.offline),root)
            elif args.command=='organize':result=organize(root,rows,config)
            elif args.command=='fetch':
                if args.limit<1:raise ValueError('--limit must be positive')
                result=fetch(root,rows,args.limit)
            elif args.command=='review':
                key=args.doi_or_id if args.doi_or_id.startswith('paper_') else doi(args.doi_or_id)
                match=next((r for r in rows if key in (r['record_id'],r.get('doi'))),None)
                if not match:raise ValueError('Record not found')
                match['manual_review']={'decision':args.decision,'note':args.note,'at':now(),'source_sha256':match.get('sha256')}
            for r in rows:r['pipeline_status']=status(r,config)
            if len({r['record_id'] for r in rows})!=len(rows):raise ValueError('Duplicate record IDs')
            changed=save(root,before,rows,args.command)
            summary=export(root,rows)
            print(dumps({'changed':changed,'operation':result,'summary':summary}))
        return 0
    except Exception as exc:
        print('ERROR: '+str(exc),file=sys.stderr);return 1
if __name__=='__main__':sys.exit(main())
