import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest


spec = importlib.util.spec_from_file_location("export_topics", Path(__file__).with_name("export_topics.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def sentiment(positive=0, negative=0, mixed=0, neutral=0, undetermined=0):
    return {s: {"count": n, "share": None, "summary": None, "evidence_fragment_ids": []}
            for s, n in zip(m.SENTIMENTS, (positive, negative, mixed, neutral, undetermined))}


def fixture():
    # R1 occurs in BOTH topics; overview must never be computed by summing topics.
    return {
        "schema_version": "2.0", "status": "partial", "settings": {}, "definitions": {},
        "warnings": ["Original warning"],
        "overview": {"review_count": 3, "sentiment": sentiment(positive=1, mixed=1, undetermined=1),
                     "summary": None, "model": {"F70": 1}},
        "topics": {
            "T0001": {"title": "Comfort | Seating", "summary": "Source summary", "review_count": 2,
                      "sentiment": sentiment(positive=1, undetermined=1), "review_ids": ["R1", "R2"],
                      "country": {"JP": .5, "GB": .5}, "keywords": [{"term": "seat", "weight": 1}],
                      "evidence": [{"fragment_id": "F1", "review_id": "R1", "text": "Original quote",
                                    "assigned_sentiment": "positive", "fragment_sentiment": "positive"}],
                      "summary_status": "complete", "limitations": ["Small selected sample"],
                      "sampling": {"selected_fragments": 1, "total_topic_fragments": 4}},
            "T0002": {"title": "Screen", "summary": None, "review_count": 2, "summary_status": "pending",
                      "sentiment": sentiment(negative=1, mixed=1), "review_ids": ["R1", "R3"],
                      "evidence": [], "limitations": []},
        },
    }


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input = self.root / "summary.json"
        self.report = fixture()

    def tearDown(self):
        self.temp.cleanup()

    def run_export(self, report=None, **kwargs):
        self.input.write_text(json.dumps(report or self.report, ensure_ascii=False), encoding="utf-8-sig")
        result = m.export_report(self.input, **kwargs)
        folder = result["output_dir"]
        catalog = [json.loads(line) for line in (folder / "topics.jsonl").read_text(encoding="utf-8").splitlines()]
        return result, folder, catalog

    def test_overlap_denominators_and_exact_details(self):
        _, folder, catalog = self.run_export()
        meta = json.loads((folder / "overview.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["overview"], self.report["overview"])
        self.assertEqual(meta["overview"]["review_count"], 3)
        self.assertEqual(sum(t["review_count"] for t in catalog), 4)
        self.assertEqual(catalog[0]["share_of_source_reviews"], .666667)
        self.assertEqual(catalog[0]["sentiment_counts"]["undetermined"], 1)
        self.assertEqual(catalog[0]["sentiment_counts"]["neutral"], 0)
        self.assertEqual(catalog[1]["negative_or_mixed_rate"], 1)
        digest = hashlib.sha256(self.input.read_bytes()).hexdigest()
        for topic in catalog:
            full = json.loads((folder / topic["details_file"]).read_text(encoding="utf-8"))
            self.assertEqual(full["topic"], self.report["topics"][topic["topic_id"]])
            self.assertEqual(full["source_summary_sha256"], digest)
        self.assertEqual(meta["source_summary"]["sha256"], digest)

    def test_html_script_escape_and_literal_markdown(self):
        attack = '</script><script>window.injected=true</script><img src=x onerror=alert(1)>'
        self.report["topics"]["T0001"]["summary"] = attack
        _, folder, _ = self.run_export()
        page = (folder / "report.html").read_text(encoding="utf-8")
        self.assertNotIn(attack, page)
        embedded = re.search(r'<script type="application/json" id="report-data">(.*?)</script>', page, re.S)[1]
        parsed = json.loads(embedded)
        self.assertEqual(parsed["details"]["T0001"]["summary"], attack)
        self.assertIn('\\u003c/script', embedded)
        overview = (folder / "overview.md").read_text(encoding="utf-8")
        self.assertIn('Comfort \\| Seating', overview)
        self.assertNotIn('<img', overview)

    def test_generated_interface_and_guide_are_english(self):
        _, folder, _ = self.run_export()
        for name in ("report.html", "overview.md", "README.md"):
            content = (folder / name).read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"[\u0400-\u04FF]", content), name)
        page = (folder / "report.html").read_text(encoding="utf-8")
        self.assertIn('<html lang="en">', page)
        self.assertNotIn('href="overview.md"', page)

    def test_template_explains_how_to_open_generated_report(self):
        template = Path(__file__).with_name("report_template.html").read_text(encoding="utf-8")
        self.assertEqual(template.count("__REPORT_DATA__"), 1)
        self.assertIn("This is the source template", template)
        self.assertNotIn('href="overview.md"', template)

    def test_empty_statistics_only_input(self):
        empty = copy.deepcopy(self.report)
        empty["topics"] = {}
        empty["status"] = "statistics_only"
        empty["overview"] = {"review_count": 0, "sentiment": sentiment(), "summary": None}
        _, folder, catalog = self.run_export(empty)
        self.assertEqual(catalog, [])
        self.assertIn("No AI summary is available yet", (folder / "overview.md").read_text(encoding="utf-8"))
        zero = self.report["topics"]["T0001"]
        zero["review_count"], zero["sentiment"] = 0, sentiment()
        topic = m.compact_topic("T0001", zero, 0, 10)
        self.assertIsNone(topic["negative_or_mixed_rate"])
        self.assertIsNone(topic["share_of_source_reviews"])

    def test_small_sample_threshold_and_top_do_not_drop_topics(self):
        _, folder, catalog = self.run_export(small_sample=2, top=1)
        self.assertEqual(len(catalog), 2)
        self.assertFalse(any(t["small_sample"] for t in catalog))
        overview = (folder / "overview.md").read_text(encoding="utf-8")
        self.assertIn("Most frequent topics — top 1", overview)
        self.assertTrue(m.compact_topic("T", self.report["topics"]["T0001"], 3, 3)["small_sample"])

    def test_rerun_is_deterministic_and_keeps_input(self):
        _, folder, _ = self.run_export()
        before = self.input.read_bytes()
        files = {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
        m.export_report(self.input)
        self.assertEqual(before, self.input.read_bytes())
        self.assertEqual(files, {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()})

    def test_reject_bad_counts_schema_path_and_nonfinite(self):
        invalids = []
        broken = fixture()
        broken["topics"]["T0001"]["review_count"] = 99
        invalids.append(broken)
        broken = fixture()
        broken["topics"]["../../escape"] = broken["topics"].pop("T0001")
        invalids.append(broken)
        broken = fixture()
        broken["schema_version"] = "1.0"
        invalids.append(broken)
        broken = fixture()
        broken["topics"]["T0001"]["sentiment"]["positive"]["share"] = float("nan")
        invalids.append(broken)
        for broken in invalids:
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                self.run_export(broken)
        self.assertFalse(self.input.with_suffix(".readable").exists())

    def test_refuse_input_overwrite(self):
        self.input = self.root / "overview.json"
        self.input.write_text(json.dumps(self.report), encoding="utf-8")
        before = self.input.read_bytes()
        with self.assertRaisesRegex(ValueError, "overwrite"):
            m.export_report(self.input, self.root)
        self.assertEqual(self.input.read_bytes(), before)
        self.assertFalse((self.root / "report.html").exists())

    def test_rerun_removes_only_previous_generated_topic_files(self):
        _, folder, _ = self.run_export()
        extra = folder / "topics" / "personal-note.json"
        extra.write_text('{"note":"keep"}', encoding="utf-8")
        del self.report["topics"]["T0002"]
        self.run_export()
        self.assertFalse((folder / "topics" / "T0002.json").exists())
        self.assertTrue((folder / "topics" / "T0001.json").exists())
        self.assertEqual(extra.read_text(encoding="utf-8"), '{"note":"keep"}')


if __name__ == "__main__":
    unittest.main()
