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
2. **Decide** — given the signals, pick exactly one next action: one of the 8 tools
   (`query_data`, `web_search`, `add_claim`, `add_assumption`, `propose_requirement`, `score`,
   `challenge`, `ask_pm`) plus its arguments, and a `rationale` string explaining why. **This is
   the one step that needs a real LLM call** — the skeleton in `loop.py` stubs it with a fixed
   priority rule so the rest of the loop is runnable and testable today.
3. **Act** — call the chosen tool's endpoint. The API is the single write path, so a failed
   call (400) means the decision was invalid (e.g. a dangling input id) — log it and let Decide
   pick something else next iteration, don't crash the loop.
4. **Pause** — stop after `max_actions` iterations, or immediately if Decide's only option was
   `ask_pm`, and hand a summary of what was written back to the PM. The PM reviews/steers via
   `POST /decide` on any node Act created; nothing here auto-applies a PM's changes — VISION.md
   says stale propagation and re-review are the next loop's job, not this one's.

## State the loop needs between pauses

- `max_actions`: the pause budget (VISION.md: "after N actions").
- Nothing else needs to persist in the loop process itself — the graph *is* the state. Each
  resume re-runs Look from scratch, which is why stale/open-question signals must be computed
  from the graph, not from loop memory.

## Known limitation (observed in a live test run)

With `gpt-4o-mini`, Decide sometimes keeps calling `query_data` for the same source instead of
moving on to `add_claim` once evidence already exists — the `evidence_without_claim` signal is
there, but the model doesn't always act on it. The loop itself doesn't break (a rejected call
now logs an error and lets Decide try again, see `act()`), so this is prompt-quality tuning,
not a correctness bug. Worth revisiting the system prompt or trying a stronger model if it
matters for the demo.

## What's intentionally not here (teammate's call)

- The real Decide step (LLM prompt, tool-call parsing) — `loop.py`'s `decide()` is a stub, see
  its `shortcut:` comment.
- Any UI/CLI for the PM to review a pause's summary — that's the GUI module's job; this loop
  just returns/prints the summary.
- Detecting "PM answered a Question" to resume faster — out of scope for the first pass; Look
  re-reading the whole graph each time covers it for now.
