# GUI — graph-first PM view

Plain HTML/JS, no build step. The backend serves this folder at **http://localhost:8000/ui/**
(`/` redirects there), so it shares the API's origin. Graph rendering: cytoscape.js 3.30.2 from
cdnjs. Talks to the API only (`GET /nodes`, `GET /edges`, `POST /nodes`, `POST /decide`,
`POST /edit`, `POST /import/csv`, `POST /agent/run`, `GET /agent/status`). `window.cy` exposes
the graph in the browser console for debugging.

| File | What |
|---|---|
| `index.html`, `style.css` | Layout: one top bar, brief + inbox (left), graph canvas, detail panel (right) |
| `theme.css` | Shared design tokens (`--paper`, `--ink`, `--m-*`, `--type`) and the font, used by every page |
| `app.js` | Loads the graph, renders it, detail panel, PM actions. Nodes are ink-on-paper cards (SVG images in cytoscape); edges are drawn by the flow layer (`#flow`, an SVG under the canvas): ghost lines, and the selected node's chain as the three M stripes, Sankey-style |
| `DESIGN.md` | **Design language** ("M stripes as flow"): colors, type, stripes, motion. New pages follow it |
| `start.js`, `start.css` | Start screen: choices drawn as M stripes on spring-animated Sankey curves. Uses BMW Type Next if installed or put in `gui/fonts/` (gitignored, licensed), else the system font |
| `layout.js` | Chain layout: each node sits one column right of the deepest node it's built on, so the chain grows left to right the way it is stored (a PM question mid-chain stays in the chain). Self-check: `node gui/layout.test.mjs` |

## The PM's loop

1. **Empty graph → start screen** (`start.js`, `start.css`; `/ui/?start` shows it over an existing
   graph too, to demo or design it): the three M stripes flow down and fan out to each choice —
   vehicle, market, data files (`GET /datasets`, `POST /import/dataset`, or your own CSV via
   `POST /import/csv`) — then through the brief into **Start agent**. The brief is a PM Note with
   `content.kind = "brief"`; it is shown in the brief bar, not drawn, and the agent reads it every run.
2. **Inbox** (left): only what needs the PM — *the agent asks you*, *broken by an edit* (with the
   edit that caused it), *waiting for your decision* (undecided requirements), *waiting for the
   agent*, *new since your last visit* ("Mark all as seen" is remembered in this browser).
3. **Click an item → focus mode:** the graph shows only that node's chain (what it's built on,
   what's built on it, other versions). **Show whole graph** switches back; old versions are hidden
   unless something current still builds on them.
4. **Act** in the detail panel, then **Run agent** (or *Let the agent redo these*): it handles PM
   input first, then redoes stale nodes, never builds on rejected ones, then continues.
5. **Requirements** tab: the output — every current requirement with its status and evidence count.

## Using it

- **Import CSV…** turns a file into one Source node with its rows (`POST /import/csv`; needs
  your PM name, which is recorded as the importer).
- **Run agent** starts `agent-loop/loop.py` for N actions in the background (`POST /agent/run`,
  one run at a time). The GUI polls every 1.5 s, adds new nodes as they appear and refits the
  view; the status says whether the run uses the LLM or the rule-based fallback, and
  **Agent log** shows one line per action.
- **Finished / dead ends:** an approved requirement is **FINISHED** (its chain is done). A rejected
  node is a **dead end**, and so is what rests only on rejected nodes and the branch that only led
  there (e.g. the claim and evidence under a rejected duplicate requirement); a question or
  challenge aimed at a node neither keeps it alive nor kills it. Dead ends are faded, hidden
  unless **show dead ends** is ticked, and leave the inbox; they stay in the data and the Audit trail.
- Nodes the **last run** wrote are marked **NEW** (the three M stripes as the card's top rule),
  read from the run's log; the marks clear when the next run starts.
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
- New nodes land one column right of what they're built on, not where they were dropped (the layout is computed).

### Audit timeline

**Audit timeline** (top bar) swaps the graph for the full trail, newest first. Every node is
one entry — the graph is append-only, so it *is* the audit trail: who (PM / agent / import),
when, what in plain words ("edited CLM-001 → v2", "asked the agent to challenge CLM-001",
"recorded counter-evidence EVD-002 against CLM-001", "approve CLM-001"), the node's text and
the documented why. Edits list the nodes that went stale because of them. Filter by who, by
type, or to the selected node's chain (e.g. one requirement's whole history incl. decisions).
Clicking an entry or an id selects that node; switching back to the graph keeps the selection.

A PM decision shows **re-review** when what it rests on changed afterwards: an edit upstream
(stale) or counter-evidence against the node that arrived after the decision.

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
| 4b. Audit timeline | Who / when / what / why for every node, filters (who, type, selected node's chain), edits list what they made stale; approvals flagged "re-review" when counter-evidence arrives later | ✅ done |
| 4c. PM loop | Start screen + brief, inbox, requirements tab, focus mode, old versions hidden, "build by hand" folded away; agent redoes stale nodes (`POST /tools/revise`) and skips rejected ones | ✅ done |
| 5. Demo polish | Requirement scores in the graph once scoring exists (agent-loop open problem #1), demo script, screenshots as fallback | planned |

Known limits:
- The graph only auto-refreshes during an agent run (use **Refresh** after changes made
  elsewhere, e.g. by a teammate's script).
- Layout is deterministic columns by chain depth: fine for tens of nodes, crowded past ~100. Long
  chains get wide; focus mode keeps zoom ≥ 0.7 and centres the selected node (drag to see the rest).
- Scores can't be created by hand and aren't shown yet — blocked on a scoring formula.
- The agent's API base is hardcoded to `localhost:8000`, so "Run agent" only works when the
  backend listens there.
- Phone width was checked down to 600px only (headless Edge can't go narrower).
- UI flows were verified with throwaway puppeteer scripts that aren't in the repo (they'd need
  Node packages the team hasn't agreed on); re-test by hand after GUI changes.
