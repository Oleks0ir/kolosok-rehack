import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("summarize_topics", Path(__file__).with_name("summarize_topics.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture(two_topics=False):
    reviews, fragments, assignments = [], [], []
    # JP: 8 negative out of 10. GB: 12 negative out of 30.
    # JP is 25% of topic reviews, has 80% negatives internally, and supplies 40% of all negatives.
    for i in range(40):
        rid, fid = f"R{i:03d}", f"F{i:03d}"
        country = "JP" if i < 10 else "GB"
        sentiment = "negative" if i < 8 or 10 <= i < 22 else "positive"
        reviews.append({"id": rid, "text": "Seats are uncomfortable." if sentiment == "negative" else "Seats are comfortable.",
                        "fragment_ids": [fid], "metadata": {"Country": country, "Engine Type": "ICE", "Derivate (e-code)": "F70"}})
        fragments.append({"fragment_id": fid, "review_id": rid, "topic_id": "T1", "text": reviews[-1]["text"],
                          "sentiment": {"label": sentiment, "request": False}, "cosine_to_topic_centroid": .8})
        assignments.append({"review_id": rid, "sentiment": sentiment, "fragment_ids": [fid], "request": False})
    topics = [{"topic_id": "T1", "title": "seat comfort", "keywords": [{"term": "seat", "weight": 1}], "reviews": assignments}]
    if two_topics:
        fragments.append({"fragment_id": "Fextra", "review_id": "R000", "topic_id": "T2", "text": "The screen is confusing.",
                          "sentiment": {"label": "negative", "request": False}, "cosine_to_topic_centroid": .9})
        reviews[0]["fragment_ids"].append("Fextra")
        topics.append({"topic_id": "T2", "title": "screen", "keywords": [{"term": "screen", "weight": 1}],
                       "reviews": [{"review_id": "R000", "sentiment": "negative", "fragment_ids": ["Fextra"]}]})
    return {"source": {}, "reviews": reviews, "fragments": fragments, "topics": topics}


class FakeClient:
    def __init__(self):
        self.usage = {"input_tokens": 0, "output_tokens": 0, "requests": 0, "cache_hits": 0}
        self.successful_responses = 0

    def complete(self, prompt, payload, schema, name):
        self.usage["requests"] += 1
        self.successful_responses += 1
        if name == "corpus_summary":
            return {"summary": "Reviews contain both praise and complaints.", "key_topic_ids": list(payload["topics"])[:1],
                    "signal_notes": [], "limitations": []}
        return {"title": "Seat comfort", "summary": "Views on seat comfort differ.",
                "sentiments": {s: {"summary": "Relevant reviews are present." if payload["sentiment"][s]["count"] else "No such reviews are present.",
                                   "evidence_fragment_ids": [e["fragment_id"] for e in payload["examples"] if e["assigned_sentiment"] == s][:1]}
                               for s in m.SENTIMENTS},
                "signal_notes": [], "limitations": []}


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.input = self.folder / "topics.json"
        self.output = self.folder / "summary.json"

    def tearDown(self):
        self.temp.cleanup()

    def args(self, source=None, extra=()):
        m.save_json(self.input, source or fixture())
        args = m.parse_args([str(self.input), "-o", str(self.output), *extra])
        args.input_sha256 = "fixture"
        return args

    def test_distinct_denominators_and_signal(self):
        args = self.args()
        report = m.build_statistics(fixture(), args)
        t = report["topics"]["T1"]
        self.assertEqual(t["country"]["JP"], .25)
        self.assertEqual(t["segments"]["country"]["JP"]["negative_rate"], .8)
        self.assertEqual(t["segments"]["country"]["JP"]["share_of_all_topic_negative_reviews"], .4)
        signal = next(s for s in t["signals"] if s["dimension"] == "country" and s["value"] == "JP")
        self.assertEqual((signal["numerator"], signal["denominator"]), (8, 10))
        self.assertEqual(signal["gap_percentage_points"], 40)

    def test_no_double_count_in_overview(self):
        source = fixture(two_topics=True)
        report = m.build_statistics(source, self.args(source))
        self.assertEqual(report["overview"]["review_count"], 40)
        self.assertEqual(sum(t["review_count"] for t in report["topics"].values()), 41)
        self.assertEqual(report["overview"]["sentiment"]["negative"]["count"], 20)

    def test_unknown_not_neutral(self):
        source = fixture()
        source["fragments"][0]["sentiment"]["label"] = "undetermined"
        source["topics"][0]["reviews"][0]["sentiment"] = "undetermined"
        report = m.build_statistics(source, self.args(source))
        self.assertEqual(report["topics"]["T1"]["sentiment"]["undetermined"]["count"], 1)
        self.assertEqual(report["topics"]["T1"]["sentiment"]["neutral"]["count"], 0)

    def test_small_segments_retained_without_signal(self):
        report = m.build_statistics(fixture(), self.args(extra=("--min-segment", "11")))
        self.assertIn("JP", report["topics"]["T1"]["country"])
        self.assertFalse(any(s["value"] == "JP" for s in report["topics"]["T1"]["signals"]))

    def test_joint_counts_are_not_independent_products(self):
        source = fixture()
        for r in source["reviews"][:10]:
            r["metadata"]["Engine Type"] = "EV"
        report = m.build_statistics(source, self.args(source))
        joint = report["topics"]["T1"]["country_engine_type"]
        self.assertEqual(joint["JP"]["EV"]["review_count"], 10)
        self.assertNotIn("ICE", joint["JP"])

    def test_stats_only_has_no_ai_calls(self):
        with patch.object(m, "urlopen", side_effect=AssertionError("Network forbidden")):
            report = m.run(self.args(extra=("--stats-only",)))
        self.assertEqual(report["status"], "statistics_only")
        self.assertIsNone(report["topics"]["T1"]["summary"])
        self.assertEqual(len(report["topics"]), 1)

    def test_resume_and_cache_keep_numbers_unchanged(self):
        source = fixture(two_topics=True)
        args = self.args(source, ("--limit", "1"))
        client = FakeClient()
        first = m.run(args, client)
        self.assertEqual(first["status"], "partial")
        self.assertEqual(client.usage["requests"], 1)
        client2 = FakeClient()
        second = m.run(args, client2)
        self.assertEqual(second["status"], "complete")
        self.assertEqual(client2.usage["requests"], 2)  # one remaining topic and global summary
        self.assertEqual(client2.usage["cache_hits"], 1)
        self.assertEqual(second["topics"]["T1"]["country"], first["topics"]["T1"]["country"])
        self.assertEqual(second["topics"]["T1"]["sentiment"]["negative"]["count"], 20)
        third_client = FakeClient()
        third = m.run(args, third_client)
        self.assertEqual(third["status"], "complete")
        self.assertEqual(third_client.usage["requests"], 0)

    def test_parallel_requests_overlap_and_preserve_results(self):
        args = self.args(fixture(two_topics=True), ("--workers", "2"))
        client = FakeClient()
        original = client.complete
        barrier = threading.Barrier(2, timeout=5)
        def concurrent(prompt, payload, schema, name):
            if name == "topic_summary":
                barrier.wait()  # Fails if the implementation serializes calls.
            return original(prompt, payload, schema, name)
        client.complete = concurrent
        report = m.run(args, client)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(client.usage["requests"], 3)
        self.assertEqual(report["overview"]["review_count"], 40)

    def test_limit_smaller_than_workers_is_not_exceeded(self):
        client = FakeClient()
        report = m.run(self.args(fixture(two_topics=True), ("--workers", "5", "--limit", "1")), client)
        self.assertEqual(client.usage["requests"], 1)
        self.assertEqual(report["ai"]["completed_topics"], 1)

    def test_model_change_does_not_reuse_other_models_cache(self):
        m.run(self.args(extra=("--model", "gpt-5-mini")), FakeClient())
        client = FakeClient()
        report = m.run(self.args(extra=("--model", "gpt-5.4")), client)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(client.usage["requests"], 2)
        self.assertEqual(client.usage["cache_hits"], 0)

    def test_hallucinated_evidence_rejected(self):
        report = m.build_statistics(fixture(), self.args())
        payload = m.topic_payload("T1", report["topics"]["T1"])
        data = FakeClient().complete("", payload, m.TOPIC_SCHEMA, "topic_summary")
        data["sentiments"]["positive"]["evidence_fragment_ids"] = ["FAKE"]
        with self.assertRaises(ValueError):
            m.validate_narrative(data, payload)

    def test_percentage_prose_rejected(self):
        report = m.build_statistics(fixture(), self.args())
        payload = m.topic_payload("T1", report["topics"]["T1"])
        data = FakeClient().complete("", payload, m.TOPIC_SCHEMA, "topic_summary")
        data["summary"] = "80% of cars are defective."
        with self.assertRaises(ValueError):
            m.validate_narrative(data, payload)

    def test_only_english_output_is_accepted(self):
        with self.assertRaises(SystemExit):
            m.parse_args([str(self.input), "--language", "ru"])
        with self.assertRaisesRegex(ValueError, "Only English"):
            m.instructions("ru")

    def test_duplicate_assignments_rejected(self):
        source = fixture()
        source["topics"][0]["reviews"].append(source["topics"][0]["reviews"][0])
        with self.assertRaises(ValueError):
            m.build_statistics(source, self.args(source))

    def test_http_structured_output_contract(self):
        answer = {"summary": "Overall feedback is mixed.", "key_topic_ids": [], "signal_notes": [], "limitations": []}
        response = {"status": "completed", "usage": {"input_tokens": 10, "output_tokens": 20},
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(answer)}]}]}
        captured = []
        def fake_open(request, timeout):
            captured.append(json.loads(request.data))
            return io.BytesIO(json.dumps(response).encode())
        with patch.object(m, "urlopen", side_effect=fake_open):
            client = m.OpenAIClient("test-key-not-real", "gpt-5.4")
            result = client.complete("instructions", {"data": "untrusted text"}, m.GLOBAL_SCHEMA, "corpus_summary")
        self.assertEqual(result, answer)
        self.assertEqual(captured[0]["model"], "gpt-5.4")
        self.assertFalse(captured[0]["store"])
        self.assertTrue(captured[0]["text"]["format"]["strict"])
        self.assertEqual(client.usage["input_tokens"], 10)

    def test_schema_rejects_extra_fields(self):
        with self.assertRaises(ValueError):
            m.check_schema({"summary": "x", "key_topic_ids": [], "signal_notes": [], "limitations": [], "invented_count": 5}, m.GLOBAL_SCHEMA)

    def test_failure_preserves_completed_summaries(self):
        source = fixture(two_topics=True)
        args = self.args(source)
        client = FakeClient()
        original = client.complete
        def failing(prompt, payload, schema, name):
            if payload.get('topic_id') == 'T2':
                raise RuntimeError('simulated API failure')
            return original(prompt, payload, schema, name)
        client.complete = failing
        with self.assertRaises(RuntimeError):
            m.run(args, client)
        saved = json.loads(self.output.read_text(encoding='utf-8'))
        self.assertEqual(saved['status'], 'partial')
        self.assertEqual(saved['topics']['T1']['summary_status'], 'complete')
        self.assertIsNone(saved['topics']['T2']['summary'])

    def test_constant_metadata_not_flagged_as_subgroup(self):
        source = fixture()
        for f in source['fragments']:
            f['sentiment']['label'] = 'negative'
        for a in source['topics'][0]['reviews']:
            a['sentiment'] = 'negative'
        report = m.build_statistics(source, self.args(source))
        self.assertFalse(any(s['dimension'] in ('model', 'engine_type') for s in report['topics']['T1']['signals']))


if __name__ == "__main__":
    unittest.main(verbosity=2)
