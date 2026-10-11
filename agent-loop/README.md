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
python loop.py                                 # needs OPENAI_API_KEY in the env for the LLM
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

## What's intentionally not here (teammate's call)

- Any UI/CLI for the PM to review a pause's summary — that's the GUI module's job; this loop
  just returns/prints the summary.
- Detecting "PM answered a Question" to resume faster — out of scope for the first pass; Look
  re-reading the whole graph each time covers it for now.
