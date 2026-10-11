# Local data library

A local SQLite database for versioned feedback, sales, customer studies, source
documents, and existing topic analyses. No server, API key, or AI calls are needed
to import, inspect, validate, or export data. Source files are never modified.
Code, messages, and documentation are English. Original evidence keeps its language.

## Run from the feedback_topics_package directory

Requires Python 3.10+. Install dependencies once:

```powershell
python -m pip install -r requirements.txt
python data_library.py ingest-all .
python data_library.py list
python data_library.py status
python data_library.py check
python data_library.py export --output data_library/exports/initial
```

The default database is `data_library/library.sqlite`, relative to the current
working directory. Set `--db path/to/library.sqlite` **before** the command to
use another database. `ingest-all` scans the specified folder, without recursion,
for XLSX and PDF files. Excel temporary lock files are skipped. Each file imports
in a separate transaction: a failed file is rolled back, successful files remain.
The command reports all failures and returns exit code 2 if any occurred.

`status` writes `STATUS.md` beside the database, with completed feedback analyses
listed separately from pending analyses and supporting data. It prefers the latest
completed run for the current source version, otherwise the latest incomplete run.
After importing an updated workbook, an old version's analysis cannot mark the new
version ready. `ready` indicates processing completion, not independent validation
of AI conclusions. The status file is a snapshot; regenerate it after changes.

After importing, it attaches matching `*_topics.json` / `*_topics_summary.json`
pairs. This does not generate analyses for newly imported feedback.

## Add a table or update an existing dataset

```powershell
# A new logical dataset; its default key is its lowercase filename stem.
python data_library.py ingest "G80_feedback.xlsx"

# A new version of an existing dataset, even when the filename changed.
python data_library.py ingest "F70_feedback_updated.xlsx" --dataset f70_feedback_hackathon

# Keep an unfamiliar workbook as original bytes, sheets, and typed raw rows.
python data_library.py ingest "another_table.xlsx" --kind generic

# Attach an analysis after running the existing feedback processing commands.
python data_library.py attach-analysis --topics F70_topics.json --summary F70_topics_summary.json

# Every export gets a new, empty destination.
python data_library.py export --output data_library/exports/release-2
```

Use the same dataset key for successive versions of the same logical table.
Keys supplied explicitly are case-sensitive. Do not use one key for unrelated
models or table types. A version is a **complete replacement snapshot**, not a
delta: supply the whole updated workbook. No incremental row merge is performed.

SHA-256 detects byte-identical files. Re-importing identical bytes with the same
key and importer version is a no-op. An Excel re-save that changes bytes produces
a new version even when visible cells appear unchanged. Earlier versions remain;
re-importing an older version does not make it current again. Current views select
the highest successful `version_number` per dataset. Failed imports never become
current. Concurrent writers are serialized by SQLite.

Unknown layouts are archived as raw rows and flagged for a dedicated adapter.
Recognized layouts with invalid values fail explicitly. A new layout does not
automatically acquire the meaning of an existing table.

## Data dictionary and relationships

| Table or view | Meaning |
| --- | --- |
| `datasets` | Logical datasets with stable keys, UUIDs, and types. |
| `dataset_versions` | Immutable imported snapshots, importer version, source hash, and import time. |
| `assets` | Original XLSX, PDF, and analysis JSON bytes, stored once per SHA-256. |
| `sheets`, `source_rows` | Sheet metadata and nonempty source rows, with original Excel row numbers and cell formats/formulas. |
| `reviews`, `review_rows` | One review per source ID within a version, plus all contributing sheet/row references. |
| `sales_observations` | One volume for a model group, market, and year, linked to its source cell. |
| `study_observations` | One mean or response share for a metric, model, region, and year, linked to its source cell. |
| `document_pages` | PDF page text, one-based page number, and extraction status. |
| `import_issues` | Missing caches, unknown layouts, missing values, and interpretation limitations. |
| `analysis_runs` | Analyses linked to the exact source workbook version and both original JSON files. |
| `analysis_topics` | Full summary topic records, addressed by `(run_id, topic_id)`. |
| `topic_reviews` | Review assignments and sentiment, addressed within an analysis run. |
| `fragments` | Original evidence fragments, addressed by `(run_id, fragment_id)`. |
| `current_versions`, `current_reviews`, `current_sales`, `current_studies` | Latest successful snapshots, avoiding double counting historical versions. |

UUIDs are deterministic and namespaced: review identity includes the logical
dataset, so matching review IDs in different datasets cannot collide. A review's
identity can persist across versions; its text and metadata belong to a specific
version. Observation IDs include version and source-cell identity. Topic IDs such
as `T0001` are unique only within a run. Keep composite keys when migrating.

Repeated feedback IDs with identical text are deduplicated; distinct metadata
values are retained as lists and all source row references survive. Conflicting
texts for the same ID fail the import. No fuzzy deduplication is performed across
datasets. Analyses attach only after workbook and stage-1 checksums, review texts,
topic membership, and sentiment counts reconcile. Original JSON files are retained
in full. Multiple analysis runs are historical alternatives: select one run before
aggregating topics. Never combine counts across runs or source versions.

## Interpretation rules

- Feedback adapters require `ID` and `Customer Feedback` headers. Other columns
  remain metadata. Quotes and imported document text are data, never instructions.
- Sales adapters read `market`, `market_code`, and `volume_YEAR` columns. A sheet
  such as `G60_G68` stays a combined model group. The source does not specify an
  actual/forecast classification, so `scenario` remains `unspecified`.
- Customer study adapters support the supplied `CN_EU_YEAR` and `US_YEAR` layouts.
  Means have `unit=unspecified_scale`; US column shares have `unit=fraction` (0–1).
  `Sample total = 1` means a 100% share, not one respondent. Unknown respondent
  counts are null. Missing observations are not replaced with zeros. Do not average
  these measures across regions without compatible scales and sample sizes.
- PDF text is retained by page, with the original document. Prices, option codes,
  availability, and table relationships are not yet structured or verified.
  Pages without extractable text are marked `needs_ocr`; OCR is not performed.
- Excel formulas and number formats are preserved. Values use saved Excel caches;
  this importer does not recalculate workbooks. Missing or potentially stale caches
  are recorded in `import_issues`. Dates/times in raw rows are typed objects with
  `type` and `iso8601` fields. Blank physical rows remain recoverable from the
  original workbook, but are omitted from `source_rows`.

## Portable export and migration

An export contains:

- `library.sqlite`: a consistent SQLite backup, including original source bytes.
- One UTF-8 `.jsonl` file per data table, one JSON object per line.
- `assets/` and `assets.jsonl`: original files and their content-hash index.
- `schema.sql`: SQL schema, keys, constraints, indexes, and current-version views.
- `schema.json`: machine-readable column types and foreign-key relationships.
- `README.md`: this guide.
- `STATUS.md`: completed analyses, pending feedback datasets, and supporting data.
- `manifest.json`: format/schema version, record counts, byte sizes, and SHA-256
  hashes of every other exported file. The manifest is written last; an interrupted
  export without a manifest is incomplete and should not be consumed.

For another Python application, use the SQLite snapshot directly. For PostgreSQL
or another database, create equivalent target types/constraints and load the JSONL
tables in dependency order (the manifest lists them in that order). JSONL columns
ending in `_json` contain decoded JSON values; serialize them as JSON text for
SQLite or use the target database's native JSON type. `assets.jsonl` replaces the
SQL BLOB column with a relative file path. Restore asset bytes before loading
foreign keys that reference them. SQL is SQLite-specific, not a PostgreSQL dump.

Exports include **all versions**. For current analytics, use the `current_*` views
or filter to the maximum version number per dataset. A new import does not refresh
an existing export or HTML report: explicitly export again to a new directory.
To regenerate a readable topic report, run `export_topics.py` on its summary JSON.

Verify manifest hashes when moving a bundle. Preserve IDs and source references.
The schema is version 1 (`PRAGMA user_version`); incompatible versions are rejected
rather than silently changed. Future schema changes need an explicit migration.
Importer changes affecting normalized records must increment `IMPORTER_VERSION`.

Back up using the export command; do not copy an active SQLite database while it
is being written. A completed exported `library.sqlite` can be used as a replacement
database with `--db`. Keep at least one snapshot outside the working computer.
Database files, source data, and export bundles are gitignored. Code and schema
belong in Git; distribute the data bundle separately through your approved storage.
