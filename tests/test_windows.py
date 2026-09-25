import unittest
from humanizer.document import parse_document
from humanizer.windows import make_windows, aggregate_scores

class WindowTests(unittest.TestCase):
    def test_coverage(self):
        for n in [1, 4, 8, 9, 12, 17]:
            doc = parse_document(' '.join(f'Observation {i} is recorded.' for i in range(n)))
            windows = make_windows(doc)
            owners = [s for w in windows for s in w['owned_ids']]
            self.assertEqual(len(owners), n)
            self.assertEqual(set(owners), {s['id'] for s in doc['sentences']})
            if n == 12:
                self.assertEqual([len(w['sentence_ids']) for w in windows], [8, 8])
    def test_boundaries_and_validation(self):
        doc = parse_document('# One\n\nFirst. Second.\n\n$$x=2$$\n\nThird.\n\n# Two\n\nFourth.')
        windows = make_windows(doc)
        self.assertEqual([len(w['sentence_ids']) for w in windows], [2, 1, 1])
        for size, stride in [(4, 2), (11, 4), (8, 0), (8, 8)]:
            with self.assertRaises(ValueError): make_windows(doc, size, stride)
    def test_aggregation(self):
        result = aggregate_scores([{'sentence_id': 's1', 'clarity': 20}, {'sentence_id': 's1', 'clarity': 80}])
        self.assertEqual(result['s1']['clarity'], 50)
        self.assertEqual(len(result['s1']['observations']), 2)
