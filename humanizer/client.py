"""Bounded requests with secret-free metadata and conservative ambiguous failures."""
import json
import time
import requests
from .config import ConfigurationError, MODELS
from .prompts import build_messages

class ProtocolError(ValueError): pass
class AuthenticationError(RuntimeError): pass
class BudgetExceeded(RuntimeError): pass
class TransientAPIError(RuntimeError):
    def __init__(self,message,uncertain=False):
        super().__init__(message); self.uncertain=uncertain

def strict_json(text):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: raise ProtocolError('Duplicate JSON key')
            result[key]=value
        return result
    def constant(_): raise ProtocolError('Non-finite JSON number')
    try: result=json.loads(text,object_pairs_hook=pairs,parse_constant=constant)
    except (ValueError,TypeError): raise ProtocolError('Response is not strict JSON') from None
    if not isinstance(result,dict): raise ProtocolError('Response must be a JSON object')
    return result

class DeepSeekClient:
    def __init__(self,config,max_calls,session=None,sleep=None):
        if max_calls < 1: raise ConfigurationError('max_calls must be positive')
        self.config=config; self.max_calls=max_calls
        self.session=session or requests.Session(); self.sleep=sleep or time.sleep
        self.calls=[]; self.on_event=None
    def _event(self):
        if self.on_event: self.on_event()
    def complete(self,stage,model,payload):
        if model not in MODELS: raise ConfigurationError('Unsupported model')
        if self.config['base_url'] not in ('https://api.deepseek.com','https://api.deepseek.com/v1'):
            raise ConfigurationError('Unsupported endpoint')
        body={'model':model,'messages':build_messages(stage,payload),'response_format':{'type':'json_object'},'max_tokens':4096,'stream':False,'thinking':{'type':'disabled'}}
        for attempt in range(3):
            if len(self.calls)>=self.max_calls: raise BudgetExceeded('API call budget exhausted')
            call={'stage':stage,'model':model,'attempt':attempt+1,'status':'in_flight','usage':None,'cost_estimate':None,'parameters':{k:v for k,v in body.items() if k!='messages'}}
            self.calls.append(call); self._event(); start=time.monotonic()
            try:
                response=self.session.post(self.config['base_url']+'/chat/completions',json=body,headers={'Authorization':'Bearer '+self.config['api_key']},timeout=(15,120),allow_redirects=False)
            except requests.RequestException:
                call.update(status='uncertain',elapsed_seconds=time.monotonic()-start); self._event()
                raise TransientAPIError('Transport failed; server completion is unknown. No automatic replay.',True) from None
            call.update(http_status=response.status_code,elapsed_seconds=time.monotonic()-start)
            if response.status_code in (401,402,403):
                call['status']='authentication_failed'; self._event(); raise AuthenticationError('DeepSeek authentication, access or balance failure')
            if response.status_code==429 or response.status_code in (500,502,503,504):
                call['status']='transient_failure'; self._event()
                if attempt<2: self.sleep(min(2**attempt,8)); continue
                raise TransientAPIError('DeepSeek temporarily unavailable after three attempts')
            if response.status_code!=200:
                call['status']='http_failure'; self._event(); raise ProtocolError('Unexpected API HTTP status '+str(response.status_code))
            try:
                data=response.json(); choice=data['choices'][0]
                usage=data.get('usage')
                if isinstance(usage,dict):
                    call['usage']={k:v for k,v in usage.items() if k.endswith('_tokens') and type(v) is int and v>=0}
                if choice['finish_reason']!='stop': raise ProtocolError('Incomplete model output')
                result=strict_json(choice['message']['content'])
            except (ValueError,KeyError,IndexError,TypeError):
                call['status']='protocol_failure'; self._event(); raise ProtocolError('Malformed or truncated model response') from None
            call['status']='complete'; call['request_id']=data.get('id') if isinstance(data.get('id'),str) else None
            self._event()
            return {'payload':result,'usage':call['usage'],'model':model,'elapsed_seconds':call['elapsed_seconds'],'request_id':call['request_id']}
