# GUI — graph-first PM view

Plain HTML/JS, no build step. The backend serves this folder at **http://localhost:8000/ui/**
(`/` redirects there), so it shares the API's origin. Graph rendering: cytoscape.js 3.30.2 from
cdnjs. Talks to the API only (`GET /nodes`, `GET /edges`, `POST /nodes`, `POST /decide`,
`POST /edit`, `POST /import/csv`, `POST /agent/run`, `GET /agent/status`). `window.cy` exposes
the graph in the browser console for debugging.

| File | What |
|---|---|
| `index.html`, `style.css` | Layout: top bar, legend, graph canvas, detail panel |
| `app.js` | Loads the graph, renders it, detail panel, PM actions |
| `layout.js` | Column-per-stage layout (Source → Evidence → Claim → Requirement → Score). Self-check: `node gui/layout.test.mjs` |

## Using it

- **Import CSV…** turns a file into one Source node with its rows (`POST /import/csv`; needs
  your PM name, which is recorded as the importer).
- **Run agent** starts `agent-loop/loop.py` for N actions in the background (`POST /agent/run`,
  one run at a time). The GUI polls every 1.5 s, adds new nodes as they appear and refits the
  view; the status says whether the run uses the LLM or the rule-based fallback, and
  **Agent log** shows one line per action.
- Click a node (or pick it in **Jump to**, keyboard-accessible) to highlight its whole chain —
  everything it is built on and everything built on it — and open its details.
- `#NODE-ID` in the URL selects that node, so a link like `/ui/#REQ-001` can be shared.
- **PM decision:** enter your PM name at the top, write a reason, then Approve / Reject /
  Postpone (`POST /decide`). The verdict shows as the node's border colour.
- **Edit:** writes a new version (`POST /edit`). The old version and everything built on it
  turn stale (dashed orange); PM decisions on them show "re-review: evidence changed".
- Decisions are not drawn as nodes; they appear as the target's verdict and in its detail panel.

### Building the graph by hand (PM)

- **Palette** (the type chips under the top bar): drag one onto the graph to create that node
  type, or onto a node to build on it; clicking a chip does the same, building on the selected
  node. Score isn't in the palette (no scoring formula yet), Decisions use the PM decision panel.
- **Right-click** empty space: "New …" for every type. Right-click a node: the typical next step
  (Evidence → "New Claim from…", Claim → Requirement / Assumption, …), supporting evidence,
  counter-evidence (`contradicts`), ask a question, add a note, and connect.
- While the **new-node form** is open, clicking graph nodes adds/removes them as inputs
  (blue border); keyboard users use its "Add input" list. Evidence, Claim, Assumption and
  Requirement need at least one input — the backend enforces it.
- **Connect** two existing nodes: drag one node onto the other (the earlier chain stage becomes
  the input; "Swap direction" flips it), use the right-click "Connect" items, or "Connect: add
  an input" in a node's detail panel. Edges are append-only and only written with a node, so
  connecting writes a **new version** of the target with the extra input (`POST /edit` with
  `add_inputs`); the old version and everything built on it turn stale. Connections that would
  create a loop are refused.
- New nodes land in their type's column, not where they were dropped (the layout is computed).

### Steering the agent

- **Ask the agent to challenge / dig deeper** on any node (right-click, or the buttons in its
  detail panel): writes a PM Question with `content.request` built on that node. The next
  agent run handles PM input before anything else.
- The agent's own questions show **needs your answer**; **Answer** writes a Note built on the
  question, which the agent uses on its next run.
- Purple double border / "waiting" = someone has to act: an open PM request (the agent) or an
  unanswered agent question (you). The top bar counts both. "Handled by" / "Answered" link to
  the node that closed it.
- Esc closes menus and cancels a form.

## Phase plan

| Phase | Scope | Status |
|---|---|---|
| 1. Skeleton | Served by backend, graph view, chain highlight, node detail, jump-to, deep links | ✅ done |
| 2. PM review | Approve / reject / postpone / edit with reason, stale + re-review flags | ✅ done |
| 3. Agent control | Import CSV, Run agent (backend starts `agent-loop` as a subprocess), live status + log, auto-refresh while it runs | ✅ done |
| 3b. Build by hand | Palette drag & drop, right-click menus, new-node form with click-to-pick inputs, connecting nodes (drag onto / menu / panel) as new versions | ✅ done |
| 4. PM steering | "Ask the agent to challenge / dig deeper" (right-click or detail panel), answering agent questions, "waiting for the agent" / "needs your answer" status in graph, panel and stats; the agent handles PM input first (`agent-loop/README.md` → PM steering) | ✅ done |
| 4b. Audit timeline | Chronological who / when / what / why view, filterable by type and actor | next |
| 5. Demo polish | Requirement scores in the graph once scoring exists (agent-loop open problem #1), demo script, screenshots as fallback | planned |

Known limits: the graph only auto-refreshes during an agent run (use **Refresh** after
changes made elsewhere); layout is deterministic columns, fine for tens of nodes, crowded for
hundreds; the agent's API base is hardcoded to `localhost:8000`.
