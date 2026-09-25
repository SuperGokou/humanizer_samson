import json
import unittest
import requests
from humanizer.client import DeepSeekClient, BudgetExceeded, AuthenticationError, ProtocolError, TransientAPIError

class Response:
    def __init__(self,status=200,content='{"scores":[]}',finish='stop'):
        self.status_code=status; self.content=content; self.finish=finish
    def json(self):
        return {'id':'test','choices':[{'message':{'content':self.content},'finish_reason':self.finish}], 'usage':{'prompt_tokens':10,'completion_tokens':5}}
class Session:
    def __init__(self,*responses): self.responses=list(responses); self.sent=[]
    def post(self,*args,**kwargs):
        self.sent.append((args,kwargs)); response=self.responses.pop(0)
        if isinstance(response,Exception): raise response
        return response
class ClientTests(unittest.TestCase):
    config={'api_key':'test-secret','base_url':'https://api.deepseek.com'}
    def client(self,session,n=4): return DeepSeekClient(self.config,n,session=session,sleep=lambda _:None)
    def test_request_and_usage(self):
        session=Session(Response()); client=self.client(session)
        r=client.complete('score','deepseek-flash',{'sentences':[]})
        self.assertEqual(r['usage']['prompt_tokens'],10)
        body=session.sent[0][1]['json']; self.assertEqual(body['thinking'],{'type':'disabled'})
        self.assertEqual(body['response_format'],{'type':'json_object'})
        self.assertNotIn('test-secret',json.dumps(client.calls))
    def test_budget_counts_retries(self):
        c=self.client(Session(Response(429)),1)
        with self.assertRaises(BudgetExceeded): c.complete('score','deepseek-flash',{})
        self.assertEqual(len(c.calls),1)
    def test_auth_no_retry_and_no_secret(self):
        c=self.client(Session(Response(401,'test-secret')))
        with self.assertRaises(AuthenticationError) as exc: c.complete('score','deepseek-flash',{})
        self.assertNotIn('test-secret',str(exc.exception)); self.assertEqual(len(c.calls),1)
    def test_transient_retry(self):
        c=self.client(Session(Response(503),Response()))
        c.complete('score','deepseek-flash',{}); self.assertEqual(len(c.calls),2)
    def test_uncertain_timeout(self):
        c=self.client(Session(requests.Timeout('test-secret')))
        with self.assertRaises(TransientAPIError) as exc: c.complete('score','deepseek-flash',{})
        self.assertTrue(exc.exception.uncertain); self.assertEqual(len(c.calls),1)
    def test_strict_json(self):
        for content,finish in [('{}','length'), ('{"a":1,"a":2}','stop'), ('{"a":NaN}','stop'), ('```json\n{}\n```','stop')]:
            with self.subTest(content=content):
                with self.assertRaises(ProtocolError): self.client(Session(Response(content=content,finish=finish))).complete('score','deepseek-flash',{})
