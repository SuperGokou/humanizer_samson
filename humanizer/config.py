"""Read only known assignments. Environment files are never executed."""
import os
from pathlib import Path
import re
import shlex

class ConfigurationError(ValueError): pass

MODELS = {'deepseek-flash', 'deepseek-v4-pro'}
KEYS = {'DEEPSEEK_API_KEY', 'DEEPSEEK_BASE_URL', 'DEEPSEEK_MODEL', 'DEEPSEEK_COMPLEX_MODEL', 'DEEPSEEK_REVIEW_MODEL'}

def load_config(project_root, environ=None, require_key=True):
    values = {}
    path = Path(project_root)/'.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            match = re.match(r'^\s*(?:export\s+)?([A-Z_]+)\s*=\s*(.*)$',line)
            if not match or match[1] not in KEYS: continue
            try: parts = shlex.split(match[2],comments=True,posix=True)
            except ValueError: raise ConfigurationError('Malformed quoted configuration value') from None
            if len(parts)>1: raise ConfigurationError('Configuration values containing spaces must be quoted')
            values[match[1]] = parts[0] if parts else ''
    env = os.environ if environ is None else environ
    values.update({k:env[k] for k in KEYS if k in env})
    base = values.get('DEEPSEEK_BASE_URL','https://api.deepseek.com').rstrip('/')
    if base not in ('https://api.deepseek.com','https://api.deepseek.com/v1'):
        raise ConfigurationError('Only the official DeepSeek HTTPS endpoint is supported')
    models = {'default':values.get('DEEPSEEK_MODEL','deepseek-flash'), 'complex':values.get('DEEPSEEK_COMPLEX_MODEL','deepseek-v4-pro'), 'review':values.get('DEEPSEEK_REVIEW_MODEL','deepseek-v4-pro')}
    if any(m not in MODELS for m in models.values()): raise ConfigurationError('Unsupported DeepSeek model')
    key = values.get('DEEPSEEK_API_KEY','')
    if require_key and not key: raise ConfigurationError('Set DEEPSEEK_API_KEY in the project .env')
    return {'api_key':key,'base_url':base,'models':models}
