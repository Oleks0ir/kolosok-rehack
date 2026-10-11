import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from openpyxl import Workbook
from pypdf import PdfWriter

import data_library as lib
import summarize_topics
from test_summarize_topics import fixture


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.conn = lib.connect(self.root / "library.sqlite")

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def workbook(self, name, sheets):
        workbook = Workbook()
        workbook.remove(workbook.active)
        for title, rows in sheets.items():
            sheet = workbook.create_sheet(title)
            for row in rows:
                sheet.append(row)
        path = self.root / name
        workbook.save(path)
        workbook.close()
        return path

    def feedback(self, name="feedback.xlsx", text="Comfortable seats."):
        return self.workbook(name, {"Feedback_Explorer": [
            ["ID", "Customer Feedback", "Category"],
            ["R1", text, "Seats"], ["R1", text, "Comfort"]]})

    def count(self, table):
        return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def test_versions_deduplication_and_old_reimport(self):
        path = self.feedback()
        original = path.read_bytes()
        lib.ingest_file(self.conn, path)
        first = self.conn.execute("SELECT * FROM reviews").fetchone()
        self.assertEqual(json.loads(first["metadata_json"]), {"Category": ["Seats", "Comfort"]})
        self.assertEqual(self.count("review_rows"), 2)
        self.assertEqual(lib.ingest_file(self.conn, path)["status"], "unchanged")
        self.feedback(text="Seats need improvement.")
        lib.ingest_file(self.conn, path)
        current = self.conn.execute("SELECT * FROM current_reviews").fetchone()
        self.assertEqual(current["review_key"], first["review_key"])
        self.assertEqual(current["review_text"], "Seats need improvement.")
        self.assertNotEqual(current["version_id"], first["version_id"])
        path.write_bytes(original)
        self.assertEqual(lib.ingest_file(self.conn, path)["status"], "unchanged")
        self.assertEqual(self.count("dataset_versions"), 2)
        self.assertEqual(self.conn.execute("SELECT version_id FROM current_versions").fetchone()[0], current["version_id"])

    def test_namespaced_review_ids_and_renamed_update(self):
        path = self.feedback()
        lib.ingest_file(self.conn, path, "f70")
        lib.ingest_file(self.conn, path, "g70")
        keys = {r[0] for r in self.conn.execute("SELECT review_key FROM reviews")}
        self.assertEqual(len(keys), 2)
        renamed = self.feedback("new_name.xlsx", "New review text.")
        lib.ingest_file(self.conn, renamed, "f70")
        self.assertEqual(self.count("datasets"), 2)
        self.assertEqual(self.count("dataset_versions"), 3)

    def test_conflicting_text_rolls_back_complete_file(self):
        path = self.workbook("bad.xlsx", {"Feedback": [
            ["ID", "Customer Feedback"], ["R1", "Good."], ["R1", "Bad."]]})
        with self.assertRaisesRegex(ValueError, "conflicting texts"):
            lib.ingest_file(self.conn, path)
        for table in ("assets", "datasets", "dataset_versions", "source_rows", "reviews"):
            self.assertEqual(self.count(table), 0)
        self.assertEqual(lib.check(self.conn)["status"], "ok")

    def test_failed_update_preserves_current_version(self):
        path = self.feedback()
        lib.ingest_file(self.conn, path)
        self.workbook(path.name, {"Feedback": [["ID", "Customer Feedback"], ["R2", None]]})
        with self.assertRaises(ValueError):
            lib.ingest_file(self.conn, path)
        self.assertEqual(self.count("dataset_versions"), 1)
        self.assertEqual(self.conn.execute("SELECT review_text FROM current_reviews").fetchone()[0], "Comfortable seats.")

    def test_sales_preserve_combined_group_zero_and_unknown_scenario(self):
        path = self.workbook("sales.xlsx", {"G60_G68": [
            ["market", "market_code", "volume_2024", "volume_2030"], ["China", "CN", 0, 100]]})
        lib.ingest_file(self.conn, path)
        rows = list(self.conn.execute("SELECT * FROM current_sales ORDER BY year"))
        self.assertEqual([r["volume"] for r in rows], [0, 100])
        self.assertTrue(all(r["model_group"] == "G60_G68" and r["scenario"] == "unspecified" for r in rows))
        self.assertEqual(rows[0]["cell_address"], "C2")

    def test_study_units_regions_and_sample_total(self):
        path = self.workbook("studies.xlsx", {
            "CN_EU_2025": [[None, "Dataset country"], [None, "China", None, "EU"],
                           ["Overall satisfaction", "BMW 5 Series G68", "BMW 7 Series G70", "BMW 1 Series F70"],
                           ["Mean", 8.5, 9, 7.2]],
            "US_2025": [["Exterior styling", None, "BMW 5 Series G60", "BMW 7 Series G70"],
                        ["Sample total", "% of column, sample base", 1, 1],
                        ["Excellent", "% of column, sample base", 0, .25]]})
        lib.ingest_file(self.conn, path)
        rows = list(self.conn.execute("SELECT * FROM study_observations"))
        self.assertEqual(len(rows), 7)
        self.assertEqual([r["region_code"] for r in rows[:3]], ["CN", "CN", "EU"])
        self.assertEqual(rows[0]["unit"], "unspecified_scale")
        for row in rows[3:5]:
            self.assertEqual(row["value"], 1)
            self.assertEqual(row["unit"], "fraction")
            self.assertIsNone(row["sample_size"])
        self.assertEqual(rows[5]["value"], 0)

    def test_generic_preserves_formula_and_date_with_warnings(self):
        from datetime import datetime
        path = self.workbook("misc.xlsx", {"Data": [["Value", "Date"], ["=1+1", datetime(2025, 1, 2)]]})
        result = lib.ingest_file(self.conn, path)
        self.assertEqual(result["kind"], "generic")
        row = self.conn.execute("SELECT * FROM source_rows WHERE row_number=2").fetchone()
        values, metadata = json.loads(row["values_json"]), json.loads(row["cell_metadata_json"])
        self.assertIsNone(values[0])
        self.assertEqual(values[1]["iso8601"], "2025-01-02T00:00:00")
        self.assertEqual(metadata["A"]["formula"], "=1+1")
        self.assertIn("formula_without_cache", {r[0] for r in self.conn.execute("SELECT code FROM import_issues")})

    def test_pdf_empty_password_and_unreadable_pages(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.encrypt("", "owner-secret")
        path = self.root / "document.pdf"
        with path.open("wb") as stream:
            writer.write(stream)
        lib.ingest_file(self.conn, path)
        self.assertEqual(self.conn.execute("SELECT extraction_status FROM document_pages").fetchone()[0], "needs_ocr")
        self.assertEqual(self.conn.execute("SELECT content FROM assets").fetchone()[0], path.read_bytes())

    def analysis_fixture(self):
        source = fixture(two_topics=True)
        rows = [["ID", "Customer Feedback", "Country", "Engine Type", "Derivate (e-code)"]]
        rows += [[r["id"], r["text"], *r["metadata"].values()] for r in source["reviews"]]
        workbook = self.workbook("f70.xlsx", {"Feedback": rows})
        lib.ingest_file(self.conn, workbook)
        source["source"]["sha256"] = lib.sha(workbook.read_bytes())
        topics = self.root / "F70_topics.json"
        topics.write_text(lib.dumps(source), encoding="utf-8")
        summary_path = self.root / "F70_topics_summary.json"
        args = summarize_topics.parse_args([str(topics), "-o", str(summary_path), "--stats-only"])
        args.input_sha256 = lib.sha(topics.read_bytes())
        summary = summarize_topics.build_statistics(source, args)
        summary_path.write_text(lib.dumps(summary), encoding="utf-8")
        return topics, summary_path

    def test_analysis_links_and_rejects_mismatched_checksum(self):
        topics, summary_path = self.analysis_fixture()
        result = lib.attach_analysis(self.conn, topics, summary_path)
        self.assertEqual(result["status"], "attached")
        self.assertEqual(self.count("topic_reviews"), 41)
        self.assertEqual(self.count("reviews"), 40)
        self.assertEqual(lib.attach_analysis(self.conn, topics, summary_path)["status"], "unchanged")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["source"]["input_sha256"] = "wrong"
        summary_path.write_text(lib.dumps(summary), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "checksum"):
            lib.attach_analysis(self.conn, topics, summary_path)
        self.assertEqual(self.count("analysis_runs"), 1)

    def test_analysis_assignment_failure_is_atomic(self):
        topics, summary_path = self.analysis_fixture()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["topics"]["T2"]["review_ids"] = ["R001"]
        summary_path.write_text(lib.dumps(summary), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "assignments"):
            lib.attach_analysis(self.conn, topics, summary_path)
        self.assertEqual(self.count("analysis_runs"), 0)
        self.assertEqual(self.count("analysis_topics"), 0)
        self.assertEqual(self.count("assets"), 1)

    def test_ready_status_is_bound_to_exact_source_version(self):
        topics, summary_path = self.analysis_fixture()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["status"] = "complete"
        summary_path.write_text(lib.dumps(summary), encoding="utf-8")
        lib.attach_analysis(self.conn, topics, summary_path)
        self.assertEqual(lib.inventory(self.conn)[0]["analysis_status"], "ready")
        self.assertEqual(lib.inventory(self.conn)[0]["analysis_topics"], 2)
        self.assertIn("## Analysis ready", lib.status_markdown(self.conn))
        self.feedback("f70.xlsx", "Changed source content.")
        lib.ingest_file(self.conn, self.root / "f70.xlsx")
        self.assertEqual(lib.inventory(self.conn)[0]["analysis_status"], "awaiting_analysis")
        self.assertEqual(self.count("analysis_runs"), 1)

    def test_export_is_self_contained_and_hashes_match(self):
        source = self.feedback()
        raw = source.read_bytes()
        lib.ingest_file(self.conn, source)
        output = self.root / "export"
        lib.export_bundle(self.conn, output)
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        for entry in manifest["files"]:
            content = (output / entry["path"]).read_bytes()
            self.assertEqual(lib.sha(content), entry["sha256"])
            self.assertEqual(len(content), entry["bytes"])
            if entry["records"] is not None:
                self.assertEqual(len(content.splitlines()), entry["records"])
        assets = [json.loads(line) for line in (output / "assets.jsonl").read_text().splitlines()]
        self.assertEqual((output / assets[0]["path"]).read_bytes(), raw)
        review = json.loads((output / "reviews.jsonl").read_text(encoding="utf-8"))
        self.assertIsInstance(review["metadata_json"], dict)
        backup = lib.connect(output / "library.sqlite")
        try:
            self.assertEqual(lib.check(backup)["counts"]["reviews"], 1)
        finally:
            backup.close()
        with self.assertRaisesRegex(ValueError, "empty"):
            lib.export_bundle(self.conn, output)

    def test_foreign_keys_and_corrupt_source_are_detected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.conn:
                lib.put(self.conn, "document_pages", version_id="missing", page_number=1,
                        extracted_text="", extraction_status="needs_ocr")
        lib.ingest_file(self.conn, self.feedback())
        with self.conn:
            self.conn.execute("UPDATE assets SET content=?", (b"corrupt",))
        with self.assertRaisesRegex(ValueError, "checksum"):
            lib.check(self.conn)


if __name__ == "__main__":
    unittest.main()
