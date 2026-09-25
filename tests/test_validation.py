import unittest
from humanizer.validation import validate_scores, validate_rewrites, validate_rerank, validate_review, check_invariants, check_reference_overlap
from humanizer.client import ProtocolError

class ValidationTests(unittest.TestCase):
    def test_scores(self):
        row={'id':'s1','naturalness':70,'clarity':80,'redundancy':20,'style_match':65,'rewrite_need':40,'reason':'Verbose','risk_tags':[]}
        self.assertEqual(validate_scores({'scores':[row]},['s1'])[0]['sentence_id'],'s1')
        for bad in [True, float('nan'),float('inf'),101,-1]:
            with self.assertRaises(ProtocolError): validate_scores({'scores':[{**row,'clarity':bad}]},['s1'])
        with self.assertRaises(ProtocolError): validate_scores({'scores':[row,row]},['s1'])
    def test_ids_and_shapes(self):
        with self.assertRaises(ProtocolError): validate_rewrites({'rewrites':[{'id':'s1','text':'A result.'}]},['s1','s2'])
        with self.assertRaises(ProtocolError): validate_rewrites({'rewrites':[{'id':'s1','text':'First. Second.'}]},['s1'])
        with self.assertRaises(ProtocolError): validate_rerank({'selected_ids':['bad'],'reason':'x'},['known'])
        with self.assertRaises(ProtocolError): validate_review({'issues':[{'sentence_ids':['bad'],'type':'x','reason':'x','action':'revert'}]},['s1'])
    def test_protection(self):
        for a,b in [('Returns fell by -3.5% [12].','Returns fell by 3.5% [12].'),('We used 10 mL.','We used 10 L.'),('A is 1 and B is 2.','B is 1 and A is 2.'),('The value $x=2$ holds [1].','The value $x=3$ holds [1].'),('Smith (2020) found this.','Smith found this.')]:
            self.assertTrue(check_invariants(a,b,'s1',{}),(a,b))
        self.assertTrue(check_invariants('OLS is used.','Regression is used.','s1',{'OLS':['ordinary least squares']}))
        self.assertFalse(check_invariants('OLS is used.','ordinary least squares is used.','s1',{'OLS':['ordinary least squares']}))
    def test_overlap(self):
        text='These twelve consecutive words form a long matching phrase from our reference document.'
        self.assertTrue(check_reference_overlap(text,[{'id':'r1','paragraph_text':text}]))
        self.assertFalse(check_reference_overlap('Independent wording.',[{'id':'r1','paragraph_text':text}]))
