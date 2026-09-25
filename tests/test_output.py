import csv
import tempfile
import unittest
from pathlib import Path
from humanizer.document import parse_document
from humanizer.output import save_outputs

class OutputTests(unittest.TestCase):
    def test_escaped_and_detector_blank(self):
        with tempfile.TemporaryDirectory() as tmp:
            result={'status':'dry_run','document':parse_document('<script>alert(1)</script>'),'replacements':{},'scores':{},'references':{},'issues':[],'calls':[],'manifest':{'domain':'Science'}}
            save_outputs(result,Path(tmp))
            html=(Path(tmp)/'comparison.html').read_text()
            self.assertNotIn('<script>alert(1)</script>',html); self.assertIn('&lt;script&gt;',html)
            rows=list(csv.DictReader((Path(tmp)/'evaluation.csv').read_text().splitlines()))
            self.assertEqual(rows[0]['detector_score'],'')
