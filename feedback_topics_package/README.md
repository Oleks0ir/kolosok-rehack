# Feedback topics and AI summaries

Requires Python 3.10+. Install with `python -m pip install -r requirements.txt`.

## Run

```powershell
python feedback_topics.py input.xlsx --output topics.json
python summarize_topics.py topics.json --output topics_summary.json --model gpt-5.4 --workers 5 --language en
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

Source spreadsheets, generated JSON reports, caches, secrets, and virtual
environments are excluded from version control. The editable
`sentiment_rules_en.json` is intentionally tracked.

## Tests

```powershell
python -m unittest discover -p "test_*.py"
```

Tests include independent linkage verification, count reconciliation, concurrent
requests, cache resume, request limits, evidence validation, and error recovery.
API calls are mocked; the tests do not establish live API latency or summary quality.

Detailed instructions: [clustering](README_RU.md) and [summaries](README_SUMMARIES_RU.md).
