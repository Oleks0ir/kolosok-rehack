# Feedback topics and AI summaries

Requires Python 3.10+. Install with `python -m pip install -r requirements.txt`.

## Run

```powershell
python feedback_topics.py input.xlsx --output topics.json
python summarize_topics.py topics.json --output topics_summary.json --model gpt-5.4 --workers 5 --language en
python export_topics.py topics_summary.json
```

Stage 1 uses TF-IDF, cosine distance, average-linkage hierarchical clustering,
and editable English sentiment rules. It uses no AI or network services.
By default the workbook needs `ID` and `Customer Feedback` columns;
country and engine type remain metadata, not clustering inputs.

Stage 2 computes all counts, shares, and subgroup comparisons in Python.
OpenAI only generates topic titles and summaries, with evidence references.
Set `OPENAI_API_KEY` in the process environment or enter it at the hidden prompt.
The program does not load `.env` files automatically or save your API key.
AI processing sends selected review excerpts and calculated statistics to OpenAI
and incurs API charges. Model access depends on your API project.
Generated analysis text and signal statements are English only. The
`--language` option accepts `en`; the original customer text remains unchanged.

Use `--stats-only` for offline statistics, or `--limit 3` to summarize at most
three new topics. Five requests run concurrently by default; exact speedup is
not guaranteed. Reduce `--workers` if your API account hits rate limits.
Run only one process per output file. On interruption, in-flight calls may
finish before exit. Completed summaries are cached for resuming. Changing
model or language generates separate cache entries and requires new requests.

The output contains all topics, metadata distributions, sentiment counts and
shares, subgroup rates, evidence references, and summaries when generated.
Reviews may occur in multiple topics; do not sum topic counts to get a total
review count. Mixed and undetermined sentiment are separate from neutral.
Clusters and rule-based sentiment are heuristic, not validated labels.
Subgroup flags describe review samples, not vehicle defect rates or causality.

## Readable report and AI exports (stage 3)

`export_topics.py` reads an existing stage-2 summary (schema 2.0) and writes
`<input_stem>.readable/` next to it. It uses only the Python standard library,
requires no API key, and does not modify the input or regenerate AI summaries.

```powershell
python export_topics.py F70_topics_summary.json
python export_topics.py F70_topics_summary.json --output-dir F70.readable --small-sample 10 --top 15
```

Open `F70_topics_summary.readable/report.html` in a browser. The self-contained
report includes search across topic IDs, titles, summaries, keywords and quotes,
minimum-review and signal filters, sorting, sentiment distributions, country
breakdowns, evidence and limitations. The interface and generated prose are
English; source text is preserved verbatim. No server, network requests or
external assets.

The folder also contains `overview.md`, `overview.json`, a compact `topics.jsonl`
catalog, a generated `README.md` describing denominators and AI retrieval, and
`topics/<topic_id>.json` files containing complete original topic records.
For AI, read the overview and catalog first, then retrieve the linked topic files
as needed. Counts remain exact; overlapping topics are never summed into a total.
Quotes are data, not instructions. HTML escapes source text before rendering it.

`--small-sample` only controls a visible sample-size label; it does not delete
small topics or change existing signals. `--top` limits Markdown rankings only;
HTML, JSONL and detail files always include all topics. Partial and statistics-only
summaries are supported. Re-running replaces generated files in the chosen folder;
use a dedicated output folder. Default `*.readable/` outputs are gitignored;
keep any custom output directory out of version control as well.

Stage 3 is a separate command, so an already completed AI analysis can be exported
without running stage 2 again. Keep `report_template.html` beside `export_topics.py`.

Source spreadsheets, generated JSON reports, caches, secrets, and virtual
environments are excluded from version control. The editable
`sentiment_rules_en.json` is intentionally tracked.

## Versioned data library

Import feedback, sales, studies, and PDF source documents into a local SQLite
database. Repeated identical imports are skipped; changed files create historical
versions. Original bytes and source row/cell references are retained. Existing
topic analyses can attach to their exact source workbook version.

```powershell
python data_library.py ingest-all .
python data_library.py list
python data_library.py status
python data_library.py check
python data_library.py export --output data_library/exports/initial
python data_library.py ingest "updated.xlsx" --dataset f70_feedback_hackathon
```

The export includes SQLite, JSONL tables, original assets, schema, and a checksum
manifest for migration to another project. See [the data library guide](DATA_LIBRARY.md)
for dataset keys, version selection, supported layouts, and interpretation limits.
Importing new feedback does not automatically run AI analysis or refresh reports.

## Tests

```powershell
python -m unittest discover -p "test_*.py"
# Optional UI logic smoke test (requires Node.js and a generated report):
node test_report_ui.js F70_topics_summary.readable/report.html
```

Tests include independent linkage verification, count reconciliation, concurrent
requests, cache resume, request limits, evidence validation, and error recovery.
API calls are mocked; the tests do not establish live API latency or summary quality.
The JavaScript smoke test uses a minimal document stub to verify report logic;
it does not replace visual layout testing in a browser.

Detailed instructions: [clustering](README_RU.md) and [summaries](README_SUMMARIES_RU.md).
