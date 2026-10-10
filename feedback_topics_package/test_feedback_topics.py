from pathlib import Path
import importlib.util
import json
import math
import tempfile
import unittest
from types import SimpleNamespace

import numpy as np
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('feedback_topics', ROOT / 'feedback_topics.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
RULE_PATH = ROOT / 'sentiment_rules_en.json'


def partition(groups):
    return {frozenset(g) for g in groups}


def brute_force_average_linkage(similarity, threshold):
    # Independent textbook implementation: globally closest pair, means of ORIGINAL distances.
    groups = [[i] for i in range(len(similarity))]
    while len(groups) > 1:
        best, pair = -math.inf, None
        for a in range(len(groups)):
            for b in range(a + 1, len(groups)):
                score = sum(similarity[i, j] for i in groups[a] for j in groups[b]) / (len(groups[a]) * len(groups[b]))
                if score > best:
                    best, pair = score, (a, b)
        if best < 1 - threshold - 1e-12:
            break
        a, b = pair
        groups[a] += groups.pop(b)
    return groups


class MathTests(unittest.TestCase):
    def test_tfidf_formula(self):
        nodes = [{'tokens': ['alpha', 'beta']}, {'tokens': ['alpha']}, {'tokens': ['gamma']}]
        vectors, vocabulary = module.tfidf(nodes, min_df=1, max_df_ratio=1)
        v = {vocabulary[k]: value for k, value in vectors[0].items()}
        self.assertAlmostEqual(v['alpha'] / v['beta'], (1 + math.log(4/3)) / (1 + math.log(4/2)))
        self.assertAlmostEqual(sum(x*x for x in vectors[0].values()), 1)

    def test_sparse_cosines(self):
        vectors = [{0: 0.6, 1: 0.8}, {0: 1.0}, {2: 1.0}]
        s = module.cosine_matrix(vectors)
        self.assertAlmostEqual(s[0, 1], 0.6)
        self.assertEqual(s[0, 2], 0)
        self.assertTrue(np.allclose(s, s.T))

    def test_linkage_against_global_brute_force(self):
        for seed in range(60):
            rng = np.random.default_rng(seed)
            x = rng.random((3 + seed % 14, 8))
            x /= np.linalg.norm(x, axis=1, keepdims=True)
            s = x @ x.T
            np.fill_diagonal(s, -np.inf)
            for threshold in (0, .08, .15, .25, .45, .7, .95):
                actual = module.average_linkage(s.copy(), threshold)
                expected = brute_force_average_linkage(s, threshold)
                self.assertEqual(partition(actual), partition(expected), (seed, threshold))

    def test_duplicate_and_zero_similarity(self):
        s = np.array([[-np.inf, 1, 0], [1, -np.inf, 0], [0, 0, -np.inf]])
        self.assertEqual(partition(module.average_linkage(s.copy(), 0)), {frozenset([0, 1]), frozenset([2])})

    def test_empty_singleton_and_memory_guard(self):
        self.assertEqual(module.average_linkage(np.empty((0, 0)), .7), [])
        self.assertEqual(module.average_linkage(np.array([[-np.inf]]), .7), [[0]])
        with self.assertRaises(ValueError):
            module.cosine_matrix([{0: 1.0}] * 1000, max_memory_mb=1)


class SentimentTests(unittest.TestCase):
    def setUp(self):
        self.rules = module.SentimentRules(json.loads(RULE_PATH.read_text()))

    def test_negation_and_domain_phrases(self):
        cases = {
            'The seats are comfortable.': 'positive',
            'The seats are not comfortable.': 'negative',
            'No problems with the brakes.': 'positive',
            'No paper manual.': 'negative',
            'The interface does not work.': 'negative',
            'It is not only comfortable.': 'positive',
            'The boot is 380 litres.': 'undetermined',
            'I would like rear seat heating.': 'undetermined',
            'The seats are comfortable and the screen is confusing.': 'mixed',
        }
        for text, expected in cases.items():
            self.assertEqual(self.rules.analyze(text)['label'], expected, text)

    def test_request_independent_of_polarity(self):
        result = self.rules.analyze('I would prefer physical buttons.')
        self.assertTrue(result['request'])
        self.assertEqual(result['label'], 'undetermined')

    def test_opinion_aggregation(self):
        self.assertEqual(module.combined_sentiment(['positive', 'positive', 'negative']), 'mixed')
        self.assertEqual(module.combined_sentiment(['undetermined', 'positive']), 'positive')
        self.assertEqual(module.combined_sentiment(['undetermined']), 'undetermined')


class WorkbookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def workbook(self, rows):
        wb = Workbook()
        ws = wb.active
        ws.title = 'Feedback'
        ws.append(['ID', 'Customer Feedback', 'Country', 'Engine Type', 'Old Topic'])
        for row in rows:
            ws.append(row)
        path = self.folder / 'fixture.xlsx'
        wb.save(path)
        return path

    def test_conflicting_id_rejected(self):
        path = self.workbook([['a', 'one', 'GB', 'ICE', None], ['a', 'two', 'GB', 'ICE', None]])
        with self.assertRaisesRegex(ValueError, 'different review texts'):
            module.read_reviews(path)

    def test_duplicate_rows_and_offsets(self):
        text = '  Seats are comfortable, but the screen is confusing.\nNo paper manual. '
        path = self.workbook([['a', text, 'GB', 'ICE', 'first'], ['a', text, 'GB', 'ICE', 'second']])
        reviews, name, rows = module.read_reviews(path)
        self.assertEqual((len(reviews), rows), (1, 2))
        self.assertEqual(reviews[0]['metadata']['Old Topic'], ['first', 'second'])
        nodes, occurrences = module.split_fragments(reviews)
        self.assertEqual(len(occurrences), 3)
        for f in occurrences:
            self.assertEqual(text[f['start']:f['end']], f['text'])

    def test_end_to_end_and_counts(self):
        path = self.workbook([
            ['a', 'Seats are comfortable. Seats are uncomfortable. Screen is confusing.', 'GB', 'ICE', 'x'],
            ['a', 'Seats are comfortable. Seats are uncomfortable. Screen is confusing.', 'GB', 'ICE', 'y'],
            ['b', 'Seats are comfortable.', 'JP', 'ICE', 'z'],
            ['c', 'Screen is confusing.', 'JP', 'ICE', None],
            ['d', 'Great car.', 'SE', 'ICE', None],
            ['e', None, 'SE', 'ICE', None],
        ])
        args = module.parse_args([str(path), '-o', str(self.folder / 'result.json'), '--min-df', '1', '--max-df', '1', '--threshold', '0', '--rules', str(RULE_PATH)])
        report = module.run(args)
        self.assertEqual(report['source']['unique_review_count'], 5)
        self.assertEqual(report['summary']['topic_count'], 2)
        seat = next(t for t in report['topics'] if any(k['term'] == 'seat' for k in t['keywords']))
        self.assertEqual(seat['review_count'], 2)
        self.assertEqual(seat['sentiment_counts']['mixed'], 1)
        self.assertEqual(seat['sentiment_counts']['positive'], 1)
        self.assertEqual(report['summary']['fully_unassigned_review_count'], 2)
        self.assertEqual(report['summary']['unassigned_fragment_count'], 1)
        self.assertEqual(sum(b['review_count'] for b in seat['breakdowns']['Country']), 2)
        disk = json.loads((self.folder / 'result.json').read_text(encoding='utf-8'))
        module.validate_report(disk)

    def test_all_empty_vocabulary_still_preserves_reviews(self):
        path = self.workbook([['a', 'Great car.', 'GB', 'ICE', 'x']])
        args = module.parse_args([str(path), '-o', str(self.folder / 'empty.json'), '--rules', str(RULE_PATH)])
        report = module.run(args)
        self.assertEqual(report['topics'], [])
        self.assertEqual(report['summary']['fully_unassigned_review_count'], 1)
        self.assertEqual(report['fragments'][0]['sentiment']['label'], 'positive')

    def test_metadata_does_not_affect_topic_vectors(self):
        first = [{'id': 'a', 'text': 'The seats are comfortable.', 'metadata': {'Country': 'GB', 'Old Topic': 'wrong'}}]
        second = [{'id': 'a', 'text': 'The seats are comfortable.', 'metadata': {'Country': 'JP', 'Old Topic': 'another'}}]
        n1, _ = module.split_fragments(first)
        n2, _ = module.split_fragments(second)
        self.assertEqual(module.tfidf(n1, min_df=1, max_df_ratio=1), module.tfidf(n2, min_df=1, max_df_ratio=1))


if __name__ == '__main__':
    unittest.main(verbosity=2)
