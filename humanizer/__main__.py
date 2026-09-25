"""Command-line entry point. Defaults to approved corpus references only."""
import argparse
import json
from pathlib import Path
import sys
from .client import DeepSeekClient
from .config import load_config, MODELS
from .document import parse_document
from .pipeline import run_rewrite
from .prompts import PROMPT_VERSION
from .retrieval import StyleIndex
from .windows import make_windows


def main(argv=None):
    parser=argparse.ArgumentParser(description='Context-preserving academic editing')
    sub=parser.add_subparsers(dest='command',required=True)
    command=sub.add_parser('rewrite')
    command.add_argument('input',type=Path)
    command.add_argument('--domain',required=True,choices=['Science','Technology','Engineering','Mathematics','Finance'])
    command.add_argument('--output',required=True,type=Path)
    command.add_argument('--corpus',type=Path)
    command.add_argument('--glossary',type=Path)
    command.add_argument('--model',choices=sorted(MODELS))
    command.add_argument('--window-size',type=int,default=8)
    command.add_argument('--stride',type=int,default=4)
    command.add_argument('--max-calls',type=int,default=30)
    for option in ('allow-candidates','dry-run','resume','no-retrieval'):command.add_argument('--'+option,action='store_true')
    args=parser.parse_args(argv)
    root=Path(__file__).resolve().parent.parent
    try:
        if args.input.suffix.lower() not in ('.txt','.md'):raise ValueError('Input must be UTF-8 .txt or .md')
        if args.max_calls<1:raise ValueError('--max-calls must be positive')
        text=args.input.read_bytes().decode('utf-8')
        document=parse_document(text);windows=make_windows(document,args.window_size,args.stride)
        glossary=json.loads(args.glossary.read_text()) if args.glossary else {}
        if not isinstance(glossary,dict) or any(not isinstance(k,str) or not k or not isinstance(v,list) or any(not isinstance(t,str) or not t for t in v) for k,v in glossary.items()):raise ValueError('Glossary must map terms to lists of allowed variants')
        config=load_config(root,require_key=not args.dry_run)
        if args.model:config['models']['default']=args.model
        index=None if args.no_retrieval else StyleIndex(args.corpus or root/'corpus',args.allow_candidates)
        options={'domain':args.domain,'output_dir':args.output,'dry_run':args.dry_run,'resume':args.resume,'models':config['models'],'glossary':glossary,'allow_candidates':args.allow_candidates,'max_calls':args.max_calls,'input_sha256':document['sha256'],'prompt_version':PROMPT_VERSION,'window_size':args.window_size,'stride':args.stride,'no_retrieval':args.no_retrieval}
        client=None if args.dry_run else DeepSeekClient(config,args.max_calls)
        result=run_rewrite(document,windows,index,client,options)
    except (ValueError,OSError) as exc:
        print('Error: '+str(exc),file=sys.stderr);return 2
    print(json.dumps({'status':result['status'],'output_dir':str(args.output.resolve()),'sentences':len(document['sentences']),'windows':len(windows),'cumulative_calls':len(result['calls'])},ensure_ascii=False))
    return 0 if result['status'] in ('complete','dry_run') else 1

if __name__=='__main__':sys.exit(main())
