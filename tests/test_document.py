import unittest
from humanizer.document import parse_document, render_document

class DocumentTests(unittest.TestCase):
    def test_nonprose_and_roundtrip(self):
        text = '# Results\n\nThe estimate is 3.14. Dr. Smith agrees.\n\n$$x=2$$\n\n```python\nx = 1\n```\n\n| a | b |\n|---|---|\n\n- item\n\n# References\n\nSmith. 2020. Title.\n'
        doc = parse_document(text)
        self.assertEqual(len(doc['sentences']), 2)
        self.assertEqual(render_document(doc, {}), text)
        result = render_document(doc, {doc['sentences'][0]['id']: 'The estimated value is 3.14.'})
        self.assertEqual(result, text.replace('The estimate is 3.14.', 'The estimated value is 3.14.'))
    def test_quotes_tail_and_spans(self):
        doc = parse_document('He said “It works.” (See Fig. 2.)\nA final observation')
        self.assertEqual([s['text'] for s in doc['sentences']], ['He said “It works.”', '(See Fig. 2.)', 'A final observation'])
        for s in doc['sentences']:
            self.assertEqual(doc['text'][s['start']:s['end']], s['text'])
        with self.assertRaises(ValueError):
            render_document(doc, {'missing': 'bad'})

    def test_temperature_unit_ends_sentence(self):
        doc = parse_document('The temperature was 25 °C. The volume was 10 mL.')
        self.assertEqual(len(doc['sentences']), 2)
