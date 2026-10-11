# Agent loop — design

Implements the loop from `VISION.md` → "System: how the graph gets built". Talks to the
decision-graph API only over HTTP (`backend/`'s `/tools/*`, `/decide`, `/nodes*` — see the
root `README.md`'s "For teammates" section), never imports `backend/app/` directly, so this
module can be built and run independently of the backend.

## The loop

```
Look → Decide → Act → Pause
```

1. **Look** — `GET /nodes` (or targeted subsets) and compute a few signals about the current
   graph state: which Sources have no Evidence yet, which Claims have no Requirement built on
   them, which nodes are `stale`, which Questions are still open. This is the "what's known,
   open, weak or contradictory" read VISION.md describes.
2. **Decide** — given the signals and this run's recent actions, pick exactly one next
   action: one of the 8 tools (`query_data`, `web_search`, `add_claim`, `add_assumption`,
   `propose_requirement`, `score`, `challenge`, `ask_pm`) plus its arguments, and a `rationale`
   string explaining why. `llm.py` does this with OpenAI tool-calling; `DECIDE_MODE` picks how:
   - `llm` (default): the LLM picks the tool and writes everything.
   - `hybrid`: `decide_rule_based()` picks the tool and input ids (guaranteed progress), the
     LLM only writes content + rationale. Limit: only one `query_data` per source, so it
     extracts one finding per file and then walks that finding to `ask_pm`.
   - No `OPENAI_API_KEY`: `decide_rule_based()` alone (tests, offline).
3. **Act** — call the chosen tool's endpoint. The API is the single write path, so a failed
   call (400) means the decision was invalid (e.g. a dangling input id) — log it and let Decide
   pick something else next iteration, don't crash the loop.
4. **Pause** — stop after `max_actions` iterations, or immediately if Decide's only option was
   `ask_pm`, and hand a summary of what was written back to the PM. The PM reviews/steers via
   `POST /decide` on any node Act created; nothing here auto-applies a PM's changes — VISION.md
   says stale propagation and re-review are the next loop's job, not this one's.

## State the loop needs between pauses

- `max_actions`: the pause budget (VISION.md: "after N actions").
- The last 5 actions of the current run (`history` in `run()`), so Decide sees its own repeats
  and rejected calls. Not kept across pauses — the graph *is* the state. Each resume re-runs
  Look from scratch, which is why stale/open-question signals must be computed from the graph,
  not from loop memory.

## Running it with data

The loop needs a Source with real content, or there is nothing to extract evidence from.
Until the ingestion module exists, seed one from a CSV (backend running):

```bash
python seed.py sample_data/demo_feedback.csv   # 12 synthetic 5 Series rows (from alex_demo1)
python loop.py 8                               # max actions (default 5); needs OPENAI_API_KEY for the LLM
```

## Why it used to stall (fixed)

Early live runs (gpt-4o-mini, then gpt-6-luna: 1 of 3 clean) kept calling `query_data` and
never reached a claim. Causes: the seeded Source held only a filename, so evidence was the
model's own "inspect the file" request and it rightly refused to build claims on it; Decide had
no memory of its last actions; and once a source had evidence it vanished from the signals,
so the model guessed ids. Fixed by real rows in Sources (`seed.py`), the `sources` signal plus
`inputs` on each evidence node, recent-action history, and a stricter prompt. Live result after
the fix: 8/8 actions without errors, Source → Evidence → Claim → Requirement → Score, then the
next finding.

## Evaluation (2026-10-11) — 1 run per model × mode

Setup: fresh DB, `seed.py sample_data/demo_feedback.csv`, `run(max_actions=8)`.

| Model · mode | Actions | Graph built | Tokens in / out | Cost |
|---|---|---|---|---|
| gpt-4o-mini · llm | 8 | 3 EVD → 2 CLM → 2 REQ → 1 SCR | 21,177 / 720 | $0.0036 |
| gpt-4o-mini · hybrid | 4 | 1 EVD → 1 CLM → 1 REQ → QST | 10,907 / 342 | $0.0018 |
| **gpt-6-luna · llm** | 8 | 3 EVD → 3 CLM → 2 REQ | 22,487 / 878 | **$0.0027** |
| gpt-6-luna · hybrid | 4 | 1 EVD → 1 CLM → 1 REQ → QST | 11,326 / 425 | $0.0013 |

Prices: gpt-6-luna $0.10 / $0.50 per M tokens in/out, gpt-4o-mini $0.15 / $0.60 (third-party
listings — check OpenAI's pricing page). One run each, so indicative, not statistical.

What works: no stalls, 0 errors and 0 guessed ids in 24 actions; 7/8 evidence quotes match a
CSV row exactly; both models walk the chain unprompted and pick a new row each time.

Quality: **gpt-6-luna is clearly better** — testable requirements ("…validate recognition
performance with representative in-car utterances") and rationales that cite ids. gpt-4o-mini
writes vague requirements ("needs improvement…"), overclaims ("growing customer concern" from a
single row), and in hybrid mode copied the evidence verbatim into the claim.

**Recommendation:** use gpt-6-luna in `llm` mode: `OPENAI_MODEL=gpt-6-luna` in the env of
whatever starts the loop (the backend, for GUI runs). `llm.py` sends `reasoning_effort="none"`
for gpt-6 models, which OpenAI requires for tool calls on chat.completions. The default stays
gpt-4o-mini until the team switches it.

## PM steering (PM input comes first)

VISION.md: "PM input becomes the agent's next priority." Convention in the graph:

| PM writes (via the GUI) | Meaning |
|---|---|
| Question with `content.request = "challenge"`, built on node X | find real counter-evidence against X |
| Question with `content.request = "dig_deeper"`, built on X | find more evidence on X's topic |
| Note built on an agent Question | the PM's answer |
| any other PM Question / Note | an instruction |

- `look()` puts every PM Question/Note the agent hasn't acted on into `pm_input`; Decide must
  handle the first item before anything else (prompt rule 0, rule-based: `ask_pm`).
- **Handled** (`handled()`) = an agent node is built on it. `link_pm_input()` adds the item to
  the new node's inputs deterministically (not left to the LLM). `challenge` takes a single
  target id, so a challenge request also counts as handled by agent work on its target after
  it was asked.
- **Gates** (`check()`, seen necessary live): while a request is first, calls must set
  `fulfills_pm_request: true` — models otherwise grabbed off-topic rows for "dig deeper" while
  their own rationale said so. `challenge` must quote a real source row that isn't the
  target's own row — gpt-4o-mini recorded the claim's own row as counter-evidence, luna
  recorded "none found". A rejected call lands in history; the model then hands back via
  `ask_pm` ("no counter-evidence found"), which pauses the run.
- Live (gpt-6-luna, demo CSV): challenge → honest "none found" question to the PM; dig deeper
  → one gated off-topic attempt, then an honest question; PM answer Note → `add_assumption`
  built on it. gpt-4o-mini fabricated on both requests before the gates.

## Open problems (for whoever picks this up)

Ordered by impact on the demo. 1–2 decide whether the output looks like prioritized
requirements or a list of one-verbatim paraphrases.

1. **Scoring isn't defined.** `score` takes a free-text `formula` and nothing computes a
   score — 4o-mini's SCR node just restated the requirement, and both hybrid runs paused to ask
   the PM "what scoring criteria?". Needs a real formula (VISION.md: "fixed scoring formula"),
   ideally backend-side. The CSV's `reliability` column (0.72–0.92) is a ready input that no run
   used.
2. **No consolidation — every requirement rests on one row.** Each claim links exactly one
   evidence node. Rows 2, 8 and 11 are all about charging; luna noticed the connection but still
   made a separate claim. Options: prompt rule "if a finding supports an existing claim's theme,
   claim across several evidence_ids", or a two-phase run (extract all evidence, then group).
3. **`quote` field misused outside Evidence.** Requirements and Questions sometimes put the
   model's own text in `quote`, which reads like a citation. Fix: separate `_CONTENT` schemas —
   `quote`/`source_ref` only on `query_data`.
4. **Questions aren't linked to what they ask about.** Both QST-001 nodes have no inputs
   though they ask about REQ-001. Fix: `decide_rule_based()`'s `ask_pm` passes the relevant ids,
   or hybrid lets the LLM fill `inputs`.
5. **Hybrid extracts one finding per file**, because `sources_without_evidence` empties after
   the first `query_data`. Needs a "rows left unprocessed" signal if hybrid should go deeper.
6. **Prompt size grows with the source.** ~2.7k input tokens per call for 12 rows, mostly the
   CSV (`sources` signal in `look()`, marked `shortcut:`). Real verbatim files need chunking or
   per-call row selection before they're seeded.
7. **Unused tools.** No run called `web_search`, `challenge` or `add_assumption` — Look has no
   signal that would trigger them (e.g. "requirement with only one evidence" → `challenge`).

## What's intentionally not here (teammate's call)

- Any UI/CLI for the PM to review a pause's summary — that's the GUI module's job; this loop
  just returns/prints the summary.
- Detecting "PM answered a Question" to resume faster — out of scope for the first pass; Look
  re-reading the whole graph each time covers it for now.
