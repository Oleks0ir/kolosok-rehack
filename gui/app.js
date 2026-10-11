// Graph-first PM view over the decision-graph API (served by the backend at /ui, same origin).
import { layout, STAGE, CARD_W, CARD_H } from "./layout.js";
import { createStart } from "./start.js";

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const short = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

let graph = { nodes: [], edges: [] };
let view = {}; // derived lookups, rebuilt on every load
let selected = null;
let lastPos = {}; // layout positions of the current render (drag-to-connect snaps back to them)
// Modes that turn graph clicks into picks instead of selection:
let draft = null; // {type, inputs: [ids], relation}: the "new node" form is open
let linking = null; // {from, to}: connect `from` as a new input of `to`
// Focus mode: the graph shows only the chain of focusId (what it's built on + what's built on
// it), so it stays readable at any size. Off = the whole graph with the chain highlighted.
let focusMode = true;
let focusId = null;
let showOld = false; // old versions are hidden unless something current still builds on them
let drawnSig = ""; // which nodes are drawn: refit the view only when that changes
let sideTab = "inbox";

const store = {
  get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* storage blocked */ } },
};
let lastSeen = store.get("lastSeen"); // ISO time of the PM's last "mark as seen"; null = first visit
const isBrief = (n) => n.type === "Note" && n.content?.kind === "brief";

const token = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const INK = token("--ink"), PAPER = token("--paper"), MUTED = token("--muted"), GHOST = token("--ghost");
const M_LIGHT = token("--m-light"), M_RED = token("--m-red");

// Nodes are ink-on-paper cards (DESIGN.md), drawn as SVG images: cytoscape labels can't mix an
// uppercase type line with a 2-line title. Edges stay in cytoscape (for chain lookups) but are
// invisible; the flow layer (#flow, under the canvas) draws them as ghost lines and M stripes.
const cy = cytoscape({
  container: $("#graph"),
  minZoom: 0.2,
  maxZoom: 2.5,
  style: [
    { selector: "node", style: {
      shape: "rectangle", width: CARD_W, height: CARD_H, "background-color": PAPER,
      "background-image": "data(card)", "background-fit": "contain", "border-width": 0,
    } },
    { selector: "node:selected", style: { "background-image": "data(cardOn)", "border-width": 3, "border-color": M_LIGHT } },
    { selector: "node.picked", style: { "border-width": 3, "border-style": "dashed", "border-color": M_LIGHT } },
    { selector: "node:active", style: { "overlay-opacity": 0 } },
    { selector: "edge", style: { opacity: 0, events: "no" } },
    { selector: ".faded", style: { opacity: 0.12 } },
  ],
});

window.cy = cy; // for debugging in the browser console and for UI tests

// ---- API ---------------------------------------------------------------

async function api(path, body) {
  const resp = await fetch(path, body && {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? resp.statusText));
  return data;
}

function toast(msg, isError = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = isError ? "error" : "";
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.textContent = ""; }, isError ? 8000 : 3000);
}

// ---- data --------------------------------------------------------------

async function load() {
  const [nodes, edges] = await Promise.all([api("/nodes"), api("/edges")]);
  // polling during agent runs calls this every 1.5 s: only redraw when something changed
  const sig = nodes.map((n) => n.id + n.status).join() + edges.length;
  if (sig === load.sig) return;
  load.sig = sig;
  graph = { nodes, edges };
  view = derive(nodes, edges);
  if (lastSeen === null) { // first visit: what's there now counts as seen
    lastSeen = nodes.length ? nodes.at(-1).timestamp : new Date(0).toISOString();
    store.set("lastSeen", lastSeen);
  }
  render();
}

function derive(nodes, edges) {
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const decisionsFor = {}, supersededBy = {}, inputs = {}, dependents = {};
  for (const e of edges) {
    (inputs[e.from_id] ??= []).push(e);
    // decisions show up as the target's verdict, not in its "Used by" list
    if (e.relation === "decides") (decisionsFor[e.to_id] ??= []).push(byId[e.from_id]);
    else (dependents[e.to_id] ??= []).push(e);
  }
  for (const n of nodes) if (n.replaces) supersededBy[n.replaces] = n.id;
  const brief = nodes.filter((n) => isBrief(n) && !supersededBy[n.id]).at(-1) ?? null;
  return { byId, decisionsFor, supersededBy, inputs, dependents, brief };
}

const latestOf = (id) => { while (view.supersededBy[id]) id = view.supersededBy[id]; return id; };

/** Everything id is (transitively) built on. */
function upstream(id) {
  const seen = new Set();
  const todo = [id];
  while (todo.length) {
    for (const e of view.inputs[todo.pop()] || []) if (!seen.has(e.to_id)) { seen.add(e.to_id); todo.push(e.to_id); }
  }
  return seen;
}

/** id's chain: what it's built on, what's built on it, and the other versions of those. */
function chainIds(id) {
  const chain = new Set([id, ...upstream(id), ...builtOn(id)]);
  for (const c of [...chain]) {
    for (let v = c; view.supersededBy[v]; v = view.supersededBy[v]) chain.add(view.supersededBy[v]);
    // older versions + what still hangs off them: the stale nodes an edit broke belong to its chain
    for (let v = view.byId[c]?.replaces; v; v = view.byId[v]?.replaces) {
      chain.add(v);
      for (const d of builtOn(v)) chain.add(d);
    }
  }
  return chain;
}

/** For a stale node: the edit upstream that broke it, as "EVD-001 was edited → EVD-005". */
function brokenBy(id) {
  const edited = [...upstream(id)].find((u) => view.supersededBy[u]);
  return edited ? { old: edited, now: latestOf(edited) } : null;
}

const summary = (n) => {
  const c = n.content || {};
  if (c.rows) return `${c.file ?? "file"} · ${c.rows.length} rows`;
  return String(c.text ?? c.quote ?? c.file ?? c.verdict ?? JSON.stringify(c));
};
const verdictOf = (id) => (view.decisionsFor[id] || []).at(-1)?.content?.verdict;

// ---- graph -------------------------------------------------------------

function visibleNodes() {
  let ns = graph.nodes.filter((n) => n.type in STAGE && !isBrief(n)); // the brief lives in the brief bar
  if (!showOld) { // an old version stays only while something current still builds on it (explains a stale node)
    ns = ns.filter((n) => !view.supersededBy[n.id] || n.id === focusId
      || (view.dependents[n.id] || []).some((e) => !view.supersededBy[e.from_id]));
  }
  if (focusId && view.byId[focusId]) {
    const chain = chainIds(focusId);
    ns = ns.filter((n) => chain.has(n.id));
  }
  return ns;
}

function render() {
  if (focusMode && selected && view.byId[selected]) focusId = selected;
  else if (!draft && !linking) focusId = null;
  renderGraph();
  if (!graph.nodes.length || forceStart) guard(start.show)({ name: $("#pm").value });
  else start.hide();
  renderStats();
  renderJump();
  renderBrief();
  renderSide();
  if (draft || linking) markPicked(); // an open form must survive redraws (e.g. agent polling)
  else if (selected && view.byId[selected]) highlight();
  else showHint(false);
  renderTimeline();
}

function renderGraph() {
  const drawn = visibleNodes();
  const pos = layout(drawn, graph.edges);
  lastPos = pos;
  const sig = drawn.map((n) => n.id).join();
  const changed = sig !== drawnSig; // new nodes (e.g. mid agent run) or a new focus must be in view
  drawnSig = sig;
  cy.elements().remove();
  cy.add(drawn.map((n) => ({
    group: "nodes",
    data: { id: n.id, type: n.type, card: card(n, false), cardOn: card(n, true) },
    position: pos[n.id],
  })));
  const isDrawn = (id) => id in pos;
  // arrows follow the chain (input -> derived), except "X supports/contradicts Y", which points at Y
  const pointsAtInput = (e) => e.relation === "supports" || e.relation === "contradicts";
  cy.add(graph.edges.filter((e) => isDrawn(e.from_id) && isDrawn(e.to_id)).map((e, i) => ({
    group: "edges",
    data: { id: `e${i}`, source: pointsAtInput(e) ? e.from_id : e.to_id, target: pointsAtInput(e) ? e.to_id : e.from_id },
    classes: e.relation,
  })));
  cy.add(drawn.filter((n) => n.replaces && isDrawn(n.replaces)).map((n) => ({
    group: "edges", data: { id: `v-${n.id}`, source: n.replaces, target: n.id }, classes: "version",
  })));
  renderFocusbar(drawn.length);
  drawFlow();
  if (changed) requestAnimationFrame(fitView); // after the page layout settled (first load, focus bar height)
}

// ---- cards: ink on paper ----------------------------------------------------
// A 2px rule on top, an uppercase "CLAIM · CLM-001" line with a state tag, a 2-line title.
// Chosen (approved, or selected) = solid ink with white text; rejected / old = muted.

const FONT = `'BMW Type Next', -apple-system, system-ui, 'Helvetica Neue', Arial, sans-serif`;

/** Word-wrap text into at most `lines` lines of about `width` characters, ellipsis at the end. */
function wrap(text, width, lines) {
  const out = [];
  let line = "";
  for (const word of text.replace(/\s+/g, " ").trim().split(" ")) {
    if ((line + " " + word).trim().length <= width) { line = (line + " " + word).trim(); continue; }
    if (line) out.push(line);
    line = word.length > width ? word.slice(0, width - 1) + "…" : word;
    if (out.length === lines) break;
  }
  if (out.length < lines && line) out.push(line);
  const all = out.length === lines && out.join(" ").length < text.trim().length;
  if (all) out[lines - 1] = short(out[lines - 1], width - 1) + (out[lines - 1].endsWith("…") ? "" : "…");
  return out.slice(0, lines);
}

/** {tag, rule, muted, dark} for a node: its state in the design language (no tinted fills). */
function cardState(n) {
  const verdict = verdictOf(n.id);
  const waiting = waitingOn(n);
  const old = Boolean(view.supersededBy[n.id]);
  const tag = old ? "old version" : n.status === "stale" ? "stale" : waiting === "pm" ? "needs you"
    : waiting === "agent" ? "agent next" : verdict ? { approve: "approved", reject: "rejected", postpone: "postponed" }[verdict] : "";
  return {
    tag,
    rule: old || verdict === "reject" ? GHOST : n.status === "stale" ? M_RED : INK,
    dashed: verdict === "postpone",
    muted: old || verdict === "reject",
    dark: verdict === "approve",
  };
}

function card(n, on) {
  const s = cardState(n);
  const dark = on || s.dark;
  const bg = dark ? INK : PAPER;
  const fg = dark ? "#fff" : s.muted ? MUTED : INK;
  const sub = dark ? "#b9b6ae" : MUTED;
  const tagColor = dark ? "#fff" : s.tag === "stale" ? M_RED : s.muted ? MUTED : INK;
  // ~7.6 px per uppercase character at 11px bold: the type line gives way to the state tag
  const room = Math.floor((CARD_W - 28) / 7.6) - (s.tag ? s.tag.length + 1 : 0);
  const idv = `${n.id}${n.version > 1 ? ` v${n.version}` : ""}`;
  const head = (`${n.type} · ${idv}`.length <= room ? `${n.type} · ${idv}` : idv).toUpperCase();
  const lines = wrap(summary(n), 24, 2);
  const x = (s) => esc(s);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${CARD_W}" height="${CARD_H}" viewBox="0 0 ${CARD_W} ${CARD_H}">
    <rect width="${CARD_W}" height="${CARD_H}" fill="${bg}"/>
    <line x1="0" y1="1" x2="${CARD_W}" y2="1" stroke="${dark ? INK : s.rule}" stroke-width="${s.dashed ? 2 : 3}" ${s.dashed && !dark ? `stroke-dasharray="6 4"` : ""}/>
    <text x="10" y="22" font-family="${FONT}" font-size="11" font-weight="700" letter-spacing="0.9" fill="${sub}">${x(head)}</text>
    ${s.tag ? `<text x="${CARD_W - 10}" y="22" text-anchor="end" font-family="${FONT}" font-size="11" font-weight="700" letter-spacing="0.9" fill="${tagColor}">${x(s.tag.toUpperCase())}</text>` : ""}
    ${lines.map((l, i) => `<text x="10" y="${48 + i * 22}" font-family="${FONT}" font-size="17.5" fill="${fg}" ${s.muted && !dark && verdictOf(n.id) === "reject" ? `text-decoration="line-through"` : ""}>${x(l)}</text>`).join("")}
  </svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

// ---- the flow: ghost lines for every link, M stripes on the active chain ------------------
// Drawn in graph coordinates in an SVG under the (transparent) cytoscape canvas and moved with
// the viewport, so the stripes stay parallel at any zoom and the cards hide them as they pass.

const SW = 6; // one stripe's width in graph units (3 touching stripes = one bundle)
const BEND = 24; // samples per S-bend

/** Path of a horizontal S-bend from (x1,y1) to (x2,y2), offset by `o` along its normal. */
function sbend(x1, y1, x2, y2, o = 0) {
  if (Math.abs(x2 - x1) < 1) { // same column: loop out to the right and back
    const r = Math.max(48, Math.abs(y2 - y1) / 3);
    const d = Math.sign(y2 - y1) || 1;
    return `M${x1},${y1 - o * d}C${x1 + r + o},${y1 - o * d} ${x2 + r + o},${y2 + o * d} ${x2},${y2 + o * d}`;
  }
  const k = (x2 - x1) / 2;
  let d = "";
  for (let j = 0; j <= BEND; j++) {
    const t = j / BEND, u = 1 - t;
    // cubic Bézier P0=(x1,y1) P1=(x1+k,y1) P2=(x2-k,y2) P3=(x2,y2) and its derivative
    const bx = u * u * u * x1 + 3 * u * u * t * (x1 + k) + 3 * u * t * t * (x2 - k) + t * t * t * x2;
    const by = (u * u * u + 3 * u * u * t) * y1 + (3 * u * t * t + t * t * t) * y2;
    const dx = 3 * u * u * k + 6 * u * t * (x2 - k - x1 - k) + 3 * t * t * k;
    const dy = 6 * u * t * (y2 - y1);
    const len = Math.hypot(dx, dy) || 1;
    d += `${j ? "L" : "M"}${(bx - (dy / len) * o).toFixed(1)},${(by + (dx / len) * o).toFixed(1)}`;
  }
  return d;
}

function setFlowViewport() {
  const { x, y } = cy.pan();
  $("#flow g").setAttribute("transform", `translate(${x},${y}) scale(${cy.zoom()})`);
}

function drawFlow() {
  setFlowViewport();
  const sel = selected && cy.getElementById(selected);
  const chain = sel?.nonempty() ? sel.predecessors().union(sel.successors()).edges() : cy.collection();
  const active = new Set(chain.filter((e) => !e.hasClass("contradicts")).map((e) => e.id()));
  const fade = sel?.nonempty() && !focusId;
  // each edge runs from the right side of its left end to the left side of its right end
  const links = cy.edges().map((e) => {
    let a = e.source(), b = e.target();
    if (a.position().x > b.position().x) [a, b] = [b, a];
    const same = Math.abs(a.position().x - b.position().x) < 1;
    return { e, a, b, same, on: active.has(e.id()) };
  });
  // Sankey ports: the active bundles on one side of a card stack up, ordered by where they go
  const ports = {};
  const side = (node, key, other, l, end) => (ports[node.id() + key] ??= []).push({ l, end, y: other.position().y });
  for (const l of links.filter((l) => l.on)) {
    l.off = [0, 0];
    side(l.a, "R", l.b, l, 0);
    side(l.b, l.same ? "R" : "L", l.a, l, 1);
  }
  for (const list of Object.values(ports)) {
    list.sort((p, q) => p.y - q.y);
    const step = Math.min(3 * SW, (CARD_H - 14) / list.length);
    list.forEach((p, j) => { p.l.off[p.end] = (j - (list.length - 1) / 2) * step; p.l.w = Math.min(p.l.w ?? SW, step / 3); });
  }
  const ghosts = [], stripes = [];
  for (const l of links) {
    const pa = l.a.position(), pb = l.b.position();
    const x1 = pa.x + CARD_W / 2, x2 = l.same ? pb.x + CARD_W / 2 : pb.x - CARD_W / 2;
    const cls = [...["contradicts", "version"].filter((c) => l.e.hasClass(c)), fade && !l.on && "faded"].filter(Boolean).join(" ");
    if (!l.on) { ghosts.push(`<path class="ghost ${cls}" d="${sbend(x1, pa.y, x2, pb.y)}"/>`); continue; }
    const [oa, ob] = l.off;
    for (let i = 0; i < 3; i++) {
      const o = (i - 1) * l.w; // stripe i of the bundle, along the curve's normal
      stripes.push(`<path class="stripe s${i}" stroke-width="${(l.w + 0.4).toFixed(2)}" d="${sbend(x1, pa.y + oa, x2, pb.y + ob, o)}"/>`);
    }
  }
  $("#flow g").innerHTML = ghosts.join("") + stripes.join("");
}
cy.on("viewport resize", setFlowViewport);
cy.on("position", "node", () => { cancelAnimationFrame(drawFlow.raf); drawFlow.raf = requestAnimationFrame(drawFlow); });

function fitView() {
  cy.resize();
  cy.fit(undefined, 28);
  if (cy.zoom() > 1) { cy.zoom(1); cy.center(); } // a 2-node graph shouldn't fill the screen
}

function renderFocusbar(count) {
  const old = `<label><input type="checkbox" id="showOld" ${showOld ? "checked" : ""}> show old versions</label>`;
  $("#focusbar").innerHTML = focusId
    ? `<span>Chain of <b>${esc(focusId)}</b>: what it's built on and what's built on it (${count} nodes)</span>
       <button type="button" data-focus="off">Show whole graph</button>${old}`
    : `<span>Whole graph · ${count} nodes</span>
       ${selected ? `<button type="button" data-focus="on">Focus on ${esc(selected)}'s chain</button>`
         : `<span>Click a node or an inbox item to see only its chain.</span>`}${old}`;
}

function renderStats() {
  const count = (pred) => graph.nodes.filter(pred).length;
  const decided = Object.keys(view.decisionsFor).length;
  $("#stats").textContent = [
    `${graph.nodes.length} nodes`,
    `${count((n) => n.type === "Requirement" && !view.supersededBy[n.id])} requirements`,
    `${decided} decided`,
    `${count((n) => n.status === "stale" && !view.supersededBy[n.id])} stale`,
    `${count((n) => waitingOn(n) === "pm")} questions for you`,
    `${count((n) => waitingOn(n) === "agent")} waiting for the agent`,
  ].join(" · ");
}

function nodeOptions(current = null) {
  const groups = {};
  for (const n of graph.nodes) (groups[n.type] ??= []).push(n);
  return `<option value="">—</option>` + Object.entries(groups).map(([type, ns]) =>
    `<optgroup label="${esc(type)}">${ns.map((n) =>
      `<option value="${esc(n.id)}" ${n.id === current ? "selected" : ""}>${esc(n.id)} — ${esc(short(summary(n), 50))}</option>`,
    ).join("")}</optgroup>`).join("");
}

function renderJump() {
  $("#jump").innerHTML = nodeOptions(selected);
}

// ---- work lists: inbox + requirements ----------------------------------
// The PM's loop: inbox -> click an item -> its chain -> act -> next item; empty inbox -> Run agent.

function inboxGroups() {
  const live = graph.nodes.filter((n) => !view.supersededBy[n.id] && !isBrief(n) && n.type !== "Decision");
  const seen = new Date(lastSeen || 0);
  const broke = (n) => {
    const b = brokenBy(n.id);
    return b ? `${esc(b.old)} was edited → ${esc(b.now)}` : "something it is built on changed";
  };
  return [
    { key: "asks", title: "The agent asks you", hint: "Answer so it can continue.",
      items: live.filter((n) => waitingOn(n) === "pm") },
    { key: "broken", title: "Broken by an edit", hint: "Built on something that changed. The agent redoes them on its next run.",
      items: live.filter((n) => n.status === "stale"), why: broke,
      action: { label: "Let the agent redo these", run: runAgent, primary: true } },
    { key: "decide", title: "Waiting for your decision", hint: "Proposed requirements: approve, reject or postpone.",
      items: live.filter((n) => n.type === "Requirement" && n.status !== "stale" && !verdictOf(n.id)) },
    { key: "agent", title: "Waiting for the agent", hint: "Your requests; handled first on the next run.",
      items: live.filter((n) => waitingOn(n) === "agent"), action: { label: "Run agent", run: runAgent } },
    { key: "new", title: "New since your last visit",
      items: live.filter((n) => !n.created_by.startsWith("PM:") && new Date(n.timestamp) > seen),
      why: (n) => esc(n.rationale ? short(n.rationale, 90) : ""), action: { label: "Mark all as seen", run: markSeen } },
  ];
}

function itemHtml(n, why = "") {
  const verdict = verdictOf(n.id);
  return `<button type="button" class="item ${n.id === selected ? "current" : ""}" data-goto="${esc(n.id)}">
    <span class="head"><span class="pill ${esc(n.type)}">${esc(n.id)}</span>
      ${verdict ? `<span class="pill ${esc(verdict)}">${esc(verdict)}</span>` : ""}
      ${n.status === "stale" ? `<span class="pill stale">stale</span>` : ""}</span>
    <span class="text">${esc(short(summary(n), 110))}</span>
    ${why ? `<span class="why">${why}</span>` : ""}</button>`;
}

const MAX_ITEMS = 8;

function renderSide() {
  const groups = inboxGroups();
  renderSide.actions = Object.fromEntries(groups.filter((g) => g.action).map((g) => [g.key, g.action.run]));
  const html = groups.filter((g) => g.items.length).map((g) => `
    <section class="group ${g.key}">
      <h3><span class="dot"></span>${esc(g.title)} (${g.items.length})</h3>
      ${g.hint ? `<p class="hint">${esc(g.hint)}</p>` : ""}
      ${g.items.slice(0, MAX_ITEMS).map((n) => itemHtml(n, g.why?.(n))).join("")}
      ${g.items.length > MAX_ITEMS ? `<p class="meta">+${g.items.length - MAX_ITEMS} more</p>` : ""}
      ${g.action ? `<button type="button" class="group-action ${g.action.primary ? "primary" : ""}" data-group="${g.key}">${esc(g.action.label)}</button>` : ""}
    </section>`).join("");
  $("#inbox").innerHTML = html || (graph.nodes.length
    ? `<p class="hint">Nothing needs you right now.</p>
       <button type="button" class="group-action primary" data-group="run">Run the agent to continue</button>`
    : `<p class="hint">Start a project in the middle panel.</p>`);
  const needsPm = groups.filter((g) => ["asks", "broken", "decide"].includes(g.key)).reduce((s, g) => s + g.items.length, 0);
  $("#inboxCount").textContent = needsPm || "";
  $("#inboxCount").classList.toggle("hot", needsPm > 0);
  renderReqs();
}

const REQ_ORDER = { undecided: 0, postpone: 1, approve: 2, reject: 3 };

function renderReqs() {
  const reqs = graph.nodes.filter((n) => n.type === "Requirement" && !view.supersededBy[n.id])
    .map((n) => ({ n, v: verdictOf(n.id) || "undecided" }))
    .sort((a, b) => (b.n.status === "stale") - (a.n.status === "stale") || REQ_ORDER[a.v] - REQ_ORDER[b.v]);
  $("#reqCount").textContent = reqs.length || "";
  $("#reqs").innerHTML = reqs.map(({ n, v }) => {
    const up = [...upstream(n.id)].map((id) => view.byId[id]);
    const evidence = up.filter((u) => u.type === "Evidence").length;
    const sources = up.filter((u) => u.type === "Source").length;
    return itemHtml(n, `${v === "undecided" ? `<span class="pill none">undecided</span> ` : ""}${evidence} evidence · ${sources} source${sources === 1 ? "" : "s"}`);
  }).join("") || `<p class="hint">No requirements yet. The agent proposes them from claims.</p>`;
}

function setTab(tab) {
  sideTab = tab;
  for (const b of document.querySelectorAll("[data-tab]")) b.setAttribute("aria-selected", String(b.dataset.tab === tab));
  $("#inbox").hidden = tab !== "inbox";
  $("#reqs").hidden = tab !== "reqs";
}

function markSeen() {
  lastSeen = graph.nodes.length ? graph.nodes.at(-1).timestamp : new Date().toISOString();
  store.set("lastSeen", lastSeen);
  renderSide();
}

// ---- brief + start screen ----------------------------------------------

function renderBrief() {
  const b = view.brief;
  $("#briefbar").innerHTML = !graph.nodes.length ? "" : b
    ? `<span class="eyebrow">${esc(b.content.vehicle ?? "")} · ${esc(b.content.market ?? "")}</span>
       <span class="goal" title="${esc(b.content.text ?? "")}">${esc(b.content.text ?? "")}</span>
       <button type="button" id="editBrief">Edit brief</button>`
    : `<span class="meta">No brief yet: the agent doesn't know your goal.</span>
       <button type="button" id="editBrief">Set a brief</button>`;
}

function openBrief() {
  enterMode();
  const c = view.brief?.content ?? {};
  const opt = (values, cur) => values.map((v) => `<option ${v === cur ? "selected" : ""}>${esc(v)}</option>`).join("");
  $("#detail").innerHTML = `
    <h2>${view.brief ? "Edit the brief" : "Set a brief"}</h2>
    <p class="meta">The agent reads the brief on every run and works towards it.
      ${view.brief ? `Saving writes v${view.brief.version + 1} of ${esc(view.brief.id)}.` : ""}</p>
    <div class="actions">
      <label>Vehicle <select id="briefVehicle">${opt(["BMW 5 Series", "BMW 1 Series", "BMW 7 Series"], c.vehicle)}</select></label>
      <label>Market <select id="briefMarket">${opt(["Europe", "China", "United States"], c.market)}</select></label>
      <label for="briefText">What should the agent work out?</label>
      <textarea id="briefText" rows="4">${esc(c.text ?? "")}</textarea>
      <label for="reason">Why (optional)</label>
      <textarea id="reason"></textarea>
      <div class="row"><button type="button" id="saveBrief" class="primary">Save brief</button>
        <button type="button" id="cancelMode">Cancel</button></div>
    </div>`;
}

async function saveBrief() {
  const content = { kind: "brief", vehicle: $("#briefVehicle").value, market: $("#briefMarket").value,
    text: $("#briefText").value.trim() };
  if (!content.text) throw new Error("Write what the agent should work out.");
  const rationale = $("#reason").value.trim() || null;
  const created = view.brief
    ? await api("/edit", { content, target_id: view.brief.id, created_by: pmName(), rationale })
    : await api("/nodes", { type: "Note", content, inputs: [], created_by: pmName(), rationale });
  toast(`Brief saved (${created.id})`);
  showHint();
  await load();
}

// The start screen (start.js) collects the choices; this writes them: brief, sources, first run.
// ?start in the URL shows it over an existing graph too (to demo or design it).
let forceStart = new URLSearchParams(location.search).has("start");
const start = createStart($("#start"), { loadDatasets: () => api("/datasets"), onStart: startProject });

async function startProject({ vehicle, market, goal, name, datasets, file, steps }) {
  $("#pm").value = name;
  store.set("pmName", name);
  const by = `PM:${name}`;
  await api("/nodes", { type: "Note", inputs: [], created_by: by, rationale: "project brief from the start screen",
    content: { kind: "brief", vehicle, market, text: goal } });
  for (const f of datasets) await api("/import/dataset", { name: f, created_by: by });
  if (file) await api("/import/csv", { filename: file.name, text: await file.text(), created_by: by });
  $("#actions").value = steps;
  forceStart = false;
  await load();
  await runAgent();
  toast("Agent started: its work appears live; what needs you lands in your inbox.");
}

// ---- selection + detail panel ------------------------------------------

function select(id) {
  selected = id;
  if (focusMode && focusId !== id) { focusId = id; renderGraph(); }
  highlight();
  renderSide();
}

/** Mark the selected node in the graph and show its details. */
function highlight() {
  const id = selected;
  // a redraw of the same node must not wipe what the PM is typing
  const keep = $("#detail").dataset.node === id && {
    reason: $("#reason")?.value, edit: $("#edit")?.value, open: $(".actions details")?.open,
  };
  cy.elements().removeClass("faded").unselect();
  const el = cy.getElementById(id);
  if (el.nonempty()) {
    if (!focusId) { // focus mode already shows only the chain; the whole graph fades the rest
      cy.elements().addClass("faded");
      el.predecessors().union(el.successors()).union(el).removeClass("faded");
    }
    el.select();
  }
  drawFlow(); // the selected node's chain lights up as the M stripes
  $("#jump").value = id;
  history.replaceState(null, "", `#${id}`); // shareable link to this node
  showDetail(view.byId[id]);
  $("#detail").dataset.node = id;
  renderFocusbar(cy.nodes().length);
  renderTimeline();
  if (keep && $("#reason")) {
    $("#reason").value = keep.reason ?? "";
    if (keep.edit !== undefined && $("#edit")) $("#edit").value = keep.edit;
    if ($(".actions details")) $(".actions details").open = Boolean(keep.open);
  }
}

/** Nothing selected: back to the whole graph (redraw=false when render() already drew it). */
function showHint(redraw = true) {
  selected = null;
  history.replaceState(null, "", location.pathname);
  cy.elements().removeClass("faded");
  $("#detail").dataset.node = "";
  $("#detail").innerHTML = `<p class="hint">Select a node, or an item in your inbox, to see its chain, content and decisions.</p>`;
  if (redraw && focusId) { focusId = null; renderGraph(); }
  else { renderFocusbar(cy.nodes().length); drawFlow(); }
  if (redraw) renderSide();
}

const chip = (id, extra = "") => `<button type="button" class="chip" data-goto="${esc(id)}">${esc(id)}${extra}</button>`;

function contentHtml(n) {
  const c = n.content || {};
  if (c.rows) {
    return `<p>${esc(c.file ?? "file")} — ${c.rows.length} rows</p>
      <details><summary>Show rows</summary><pre class="json">${esc(JSON.stringify(c.rows, null, 1))}</pre></details>`;
  }
  let html = c.text ? `<p>${esc(c.text)}</p>` : "";
  if (c.quote && c.quote !== c.text) html += `<blockquote>“${esc(c.quote)}”</blockquote>`;
  if (c.source_ref) html += `<p class="meta">${esc(c.source_ref)}</p>`;
  if (c.url) html += `<p><a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.url)}</a></p>`;
  const rest = Object.fromEntries(Object.entries(c).filter(([k]) => !["text", "quote", "source_ref", "url"].includes(k)));
  if (Object.keys(rest).length) html += `<pre class="json">${esc(JSON.stringify(rest, null, 1))}</pre>`;
  return html || `<p class="meta">(empty)</p>`;
}

/** Who-acts-next line for questions / PM input, plus the ask-the-agent buttons. */
function steeringHtml(n) {
  const waiting = waitingOn(n);
  const request = n.content?.request && REQUESTS[n.content.request];
  let html = "";
  if (waiting === "agent") html = `<p><span class="pill awaiting">waiting for the agent</span> ${request ? `request: ${esc(request)}` : ""} — handled on the next agent run.</p>`;
  else if (waiting === "pm") html = `<p><span class="pill awaiting">needs your answer</span> <button type="button" class="chip" data-answer="${esc(n.id)}">Answer</button></p>`;
  else if (n.created_by.startsWith("PM:") && ["Question", "Note"].includes(n.type)) html = `<p class="meta">Handled by the agent: ${chip(pmInputDoneBy(n))}</p>`;
  else if (n.type === "Question") html = `<p class="meta">Answered: ${(view.dependents[n.id] || []).map((e) => chip(e.from_id)).join(" ")}</p>`;
  if (n.type === "Decision" || view.supersededBy[n.id]) return html;
  return `${html}<div class="row chips">
    <button type="button" class="chip" data-request="challenge">Ask the agent to challenge this</button>
    <button type="button" class="chip" data-request="dig_deeper">Ask the agent to dig deeper</button></div>`;
}

function showDetail(n) {
  const decisions = view.decisionsFor[n.id] || [];
  const verdict = verdictOf(n.id);
  // counter-evidence on this node that arrived after decision d: its evidence changed, re-review
  const newerCounter = (d) => (view.dependents[n.id] || [])
    .filter((e) => e.relation === "contradicts" && new Date(view.byId[e.from_id].timestamp) > new Date(d.timestamp))
    .map((e) => e.from_id);
  const reReview = decisions.length > 0 && (decisions.at(-1).status === "stale" || newerCounter(decisions.at(-1)).length > 0);
  const newer = view.supersededBy[n.id];
  const ins = view.inputs[n.id] || [];
  const deps = view.dependents[n.id] || [];
  const rel = (e) => (e.relation === "derived_from" ? "" : ` · ${e.relation}`);
  const editable = n.type !== "Decision" && !newer;
  const editValue = typeof n.content?.text === "string" ? n.content.text : JSON.stringify(n.content, null, 2);

  $("#detail").innerHTML = `
    <h2>${esc(n.id)} <span class="pill ${esc(n.type)}">${esc(n.type)}</span>
      ${verdict ? `<span class="pill ${esc(verdict)}">${esc(verdict)}</span>` : ""}
      ${reReview ? `<span class="pill stale">re-review</span>` : ""}
      ${n.status === "stale" ? `<span class="pill stale">stale</span>` : ""}</h2>
    <p class="meta">v${n.version} · ${esc(n.created_by)} · ${esc(new Date(n.timestamp).toLocaleString())}</p>
    ${newer ? `<p class="warn">Superseded by ${chip(newer)}</p>` : ""}
    ${n.replaces ? `<p class="meta">Previous version: ${chip(n.replaces)}</p>` : ""}
    ${n.status === "stale" && !newer ? `<p class="warn">${brokenBy(n.id) ? `${chip(brokenBy(n.id).old)} was edited → ${chip(brokenBy(n.id).now)}, and this is built on it.` : "Something this is built on changed."}
      <button type="button" class="chip" data-redo="1">Let the agent redo it</button></p>` : ""}
    ${steeringHtml(n)}

    <h3>Content</h3>${contentHtml(n)}
    ${n.rationale ? `<h3>Why (rationale)</h3><p>${esc(n.rationale)}</p>` : ""}
    ${n.method ? `<h3>Method</h3><p class="meta">${esc(n.method)}</p>` : ""}

    <h3>Built on (${ins.length})</h3>
    <div class="chips">${ins.map((e) => chip(e.to_id, rel(e))).join("") || `<span class="meta">nothing — a starting point</span>`}</div>
    <h3>Used by (${deps.length})</h3>
    <div class="chips">${deps.map((e) => chip(e.from_id, rel(e))).join("") || `<span class="meta">nothing yet</span>`}</div>

    <h3>Decisions (${decisions.length})</h3>
    ${decisions.map((d) => `<div class="decision">
        <span class="pill ${esc(d.content?.verdict)}">${esc(d.content?.verdict)}</span>
        ${esc(d.created_by)} · ${esc(new Date(d.timestamp).toLocaleString())}
        ${d.status === "stale" ? `<span class="warn"> · re-review: evidence changed</span>` : ""}
        ${newerCounter(d).length ? `<span class="warn"> · re-review: counter-evidence ${newerCounter(d).map((id) => chip(id)).join(" ")} came in after this</span>` : ""}
        ${d.rationale ? `<div>${esc(d.rationale)}</div>` : ""}</div>`).join("") || `<p class="meta">No PM decision yet.</p>`}

    ${editable ? `
    <h3>PM decision</h3>
    <div class="actions">
      <label for="reason">Reason (goes into the audit trail)</label>
      <textarea id="reason" placeholder="Why approve, reject or postpone?"></textarea>
      <div class="row">
        <button type="button" class="approve" data-verdict="approve">Approve</button>
        <button type="button" class="reject" data-verdict="reject">Reject</button>
        <button type="button" class="postpone" data-verdict="postpone">Postpone</button>
      </div>
      <details>
        <summary>Edit (creates v${n.version + 1}; everything built on this goes stale)</summary>
        <textarea id="edit" rows="5">${esc(editValue)}</textarea>
        <div class="row"><button type="button" id="saveEdit">Save new version</button></div>
      </details>
      <label>Connect: add an input to ${esc(n.id)} <select id="addInput">${nodeOptions()}</select></label>
    </div>` : ""}`;
}

// ---- audit timeline ----------------------------------------------------
// Every node is one audit entry (append-only graph = the audit trail, VISION.md write rule 2).

let currentView = "graph";

function setView(v) {
  currentView = v;
  for (const b of document.querySelectorAll("[data-view]")) b.setAttribute("aria-pressed", String(b.dataset.view === v));
  $("#graphwrap").hidden = v !== "graph";
  $("#timeline").hidden = v !== "timeline";
  hideMenu();
  if (v === "graph") cy.resize();
  else renderTimeline();
}

/** Everything (transitively) built on id, including PM decisions on those nodes. */
function builtOn(id) {
  const seen = new Set();
  const todo = [id];
  while (todo.length) {
    const cur = todo.pop();
    const next = [...(view.dependents[cur] || []).map((e) => e.from_id), ...(view.decisionsFor[cur] || []).map((d) => d.id)];
    for (const d of next) if (!seen.has(d)) { seen.add(d); todo.push(d); }
  }
  return [...seen];
}

/** One line saying what happened, in PM language. */
function describe(n) {
  const ins = view.inputs[n.id] || [];
  const ids = (rel) => ins.filter((e) => !rel || e.relation === rel).map((e) => chip(e.to_id)).join(" ");
  const request = n.content?.request;
  if (n.type === "Decision") return `<b>${esc(n.content?.verdict ?? "decided")}</b> ${ids()}`;
  if (n.replaces) {
    const old = view.byId[n.replaces];
    const sameContent = old && JSON.stringify(old.content) === JSON.stringify(n.content);
    const stale = builtOn(n.replaces).filter((id) => view.byId[id]?.status === "stale");
    return `${sameContent ? "connected a new input to" : "edited"} ${chip(n.replaces)} → v${n.version} ${chip(n.id)}`
      + (stale.length ? `<div class="why">now stale because of this: ${stale.map((id) => chip(id)).join(" ")}</div>` : "");
  }
  if (n.type === "Source") return `imported ${chip(n.id)}`;
  if (request) return `asked the agent to <b>${esc(REQUESTS[request])}</b> ${ids()} ${chip(n.id)}`;
  if (n.type === "Question") return `asked ${n.created_by.startsWith("PM:") ? "the agent" : "the PM"} ${chip(n.id)}${ins.length ? ` about ${ids()}` : ""}`;
  if (n.type === "Note" && ins.some((e) => view.byId[e.to_id]?.type === "Question")) return `answered ${ids()} with ${chip(n.id)}`;
  if (ins.some((e) => e.relation === "contradicts")) return `recorded counter-evidence ${chip(n.id)} against ${ids("contradicts")}`;
  if (n.type === "Score") return `scored ${ids()} → ${chip(n.id)}`;
  return `added ${esc(n.type)} ${chip(n.id)}${ins.length ? ` from ${ids()}` : ""}`;
}

const actorClass = (by) => (by.startsWith("PM:") ? "pm" : by.startsWith("agent:") ? "agent" : "other");

function renderTimeline() {
  if (currentView !== "timeline") return;
  const types = [...new Set(graph.nodes.map((n) => n.type))];
  const typeSel = $("#trailType");
  if (typeSel.options.length !== types.length + 1) {
    typeSel.innerHTML = `<option value="">all</option>` + types.map((t) => `<option>${esc(t)}</option>`).join("");
  }
  const actor = $("#trailActor").value;
  const type = typeSel.value;
  let chain = null;
  if ($("#trailChain").checked && selected) {
    const el = cy.getElementById(selected);
    chain = new Set([selected, ...(el.nonempty() ? el.predecessors().union(el.successors()).nodes().map((x) => x.id()) : [])]);
    for (const id of [...chain]) for (const d of view.decisionsFor[id] || []) chain.add(d.id);
  }
  const shown = graph.nodes.filter((n) =>
    (!actor || (actor === "other" ? actorClass(n.created_by) === "other" : n.created_by.startsWith(actor)))
    && (!type || n.type === type) && (!chain || chain.has(n.id))).reverse();
  $("#trail").innerHTML = shown.map((n) => `
    <li class="entry ${n.id === selected ? "current" : ""}" data-id="${esc(n.id)}">
      <time datetime="${esc(n.timestamp)}">${esc(new Date(n.timestamp).toLocaleString())}</time>
      <span class="actor ${actorClass(n.created_by)}">${esc(n.created_by)}</span>
      <div class="body">
        <div>${describe(n)}</div>
        ${n.type === "Decision" ? "" : `<div class="text">${esc(short(summary(n), 160))}</div>`}
        ${n.rationale ? `<div class="why">Why: ${esc(n.rationale)}</div>` : ""}
      </div>
    </li>`).join("") || `<li class="meta">Nothing matches these filters.</li>`;
}

// ---- PM actions --------------------------------------------------------

function pmName() {
  const name = $("#pm").value.trim();
  if (!name) throw new Error("Enter your PM name at the top first.");
  return `PM:${name}`;
}

function reason() {
  const text = $("#reason").value.trim();
  if (!text) throw new Error("A reason is required — it is the documented rationale in the audit trail.");
  return text;
}

async function decide(verdict) {
  await api("/decide", { content: { verdict }, target_id: selected, created_by: pmName(), rationale: reason() });
  toast(`${selected}: ${verdict}`);
  $("#reason").value = "";
  await load();
}

async function saveEdit() {
  const n = view.byId[selected];
  const raw = $("#edit").value;
  const content = typeof n.content?.text === "string" ? { ...n.content, text: raw.trim() } : JSON.parse(raw);
  const created = await api("/edit", { content, target_id: n.id, created_by: pmName(), rationale: reason() });
  toast(`${n.id} → ${created.id} (v${created.version}); dependents marked stale`);
  selected = created.id;
  await load();
}

// ---- composing: new nodes + connections ---------------------------------

const CREATABLE = ["Source", "Evidence", "Claim", "Assumption", "Requirement", "Question", "Note"];
const NO_INPUTS = new Set(["Source", "Question", "Note"]); // backend rule: everything else needs inputs
const NEXT = { // what a PM typically builds on a node of this type (right-click menu)
  Source: ["Evidence"], Evidence: ["Claim"], Claim: ["Requirement", "Assumption"],
  Assumption: ["Requirement"], Note: ["Claim"],
};
const REQUESTS = { challenge: "challenge", dig_deeper: "dig deeper" };
const requestDraft = (id, request) => openDraft("Question", [id], {
  request,
  text: request === "challenge"
    ? `Challenge ${id}: look for evidence against it in the sources.`
    : `Dig deeper on ${id}: find more, different evidence about it.`,
});

// The agent-loop's handled() rule, mirrored: a PM Question/Note is done once the agent built
// on it, or — for "challenge" — once the agent built on its target after it was asked.
function pmInputDoneBy(n) {
  const agentDeps = (id) => (view.dependents[id] || []).map((e) => view.byId[e.from_id])
    .filter((d) => d.created_by.startsWith("agent:"));
  const own = agentDeps(n.id)[0];
  if (own || n.content?.request !== "challenge") return own?.id;
  return (view.inputs[n.id] || []).flatMap((e) => agentDeps(e.to_id))
    .find((d) => new Date(d.timestamp) > new Date(n.timestamp))?.id;
}

/** Who has to act: "agent" (open PM input), "pm" (unanswered agent question), else null. */
function waitingOn(n) {
  if (!["Question", "Note"].includes(n.type) || isBrief(n)) return null; // the brief is a goal, not a request
  if (n.created_by.startsWith("PM:")) return pmInputDoneBy(n) ? null : "agent";
  return n.type === "Question" && !(view.dependents[n.id] || []).length ? "pm" : null;
}

function enterMode() {
  hideMenu();
  selected = null;
  $("#detail").dataset.node = "";
  history.replaceState(null, "", location.pathname);
  cy.elements().removeClass("faded").unselect();
}

function closeModes() {
  draft = linking = null;
  markPicked();
  showHint();
}

function markPicked() {
  cy.nodes().removeClass("picked");
  const ids = draft ? draft.inputs : linking ? [linking.from, linking.to].filter(Boolean) : [];
  for (const id of ids) cy.getElementById(id).addClass("picked");
}

// request: "challenge" | "dig_deeper" turns a PM Question into an instruction the agent handles first
function openDraft(type, inputs = [], { relation = "derived_from", request = null, text = "" } = {}) {
  enterMode();
  linking = null;
  draft = { type, inputs: [...inputs], relation, request };
  $("#detail").innerHTML = `
    <h2>New <span class="pill ${esc(type)}">${esc(type)}</span>
      ${request ? `<span class="pill awaiting">request to the agent: ${esc(REQUESTS[request])}</span>` : ""}</h2>
    <p class="meta">${request ? "The next agent run handles this before anything else. " : ""}
      ${NO_INPUTS.has(type) ? "Inputs are optional." : "Needs at least one input."}
      Click nodes in the graph to add or remove inputs. It appears in the ${esc(type)} column.</p>
    <div class="actions">
      <label for="draftText">Text</label>
      <textarea id="draftText" rows="3">${esc(text)}</textarea>
      <h3>Built on</h3>
      <div class="chips" id="draftInputs"></div>
      <label>Add input <select id="draftPick">${nodeOptions()}</select></label>
      ${type === "Source" ? "" : `<label>Relation to its inputs <select id="draftRel">
        <option value="derived_from">derived from</option><option value="supports">supports</option>
        <option value="contradicts">contradicts (counter-evidence)</option></select></label>`}
      <label for="reason">Why (rationale, optional)</label>
      <textarea id="reason"></textarea>
      <div class="row"><button type="button" id="createNode" class="primary">Create ${esc(type)}</button>
        <button type="button" id="cancelMode">Cancel</button></div>
    </div>`;
  if ($("#draftRel")) $("#draftRel").value = relation;
  renderDraftInputs();
  $("#draftText").focus();
}

function renderDraftInputs() {
  $("#draftInputs").innerHTML = draft.inputs.map((id) =>
    `<button type="button" class="chip" data-unpick="${esc(id)}" aria-label="Remove input ${esc(id)}">${esc(id)} ✕</button>`,
  ).join("") || `<span class="meta">nothing yet</span>`;
  markPicked();
}

function togglePick(id) {
  draft.inputs = draft.inputs.includes(id) ? draft.inputs.filter((i) => i !== id) : [...draft.inputs, id];
  renderDraftInputs();
}

async function createNode() {
  const text = $("#draftText").value.trim();
  if (!text) throw new Error("Write the node's text first.");
  const created = await api("/nodes", {
    type: draft.type, content: draft.request ? { text, request: draft.request } : { text },
    inputs: draft.inputs, created_by: pmName(), rationale: $("#reason").value.trim() || null,
    relation: draft.relation,
  });
  toast(draft.request ? `${created.id} created — Run agent to have it handled` : `${created.id} created`);
  draft = null;
  selected = created.id;
  await load();
}

function openLink(from = null, to = null) {
  enterMode();
  draft = null;
  linking = { from, to };
  renderLink();
}

function renderLink() {
  const { from, to } = linking;
  const target = to && view.byId[to];
  const end = (id) => (id ? `<b>${esc(id)}</b>` : `<i>click a node</i>`);
  $("#detail").innerHTML = `
    <h2>Connect</h2>
    <div class="actions">
      <p>${end(from)} becomes an input of ${end(to)}</p>
      ${from && to ? `
        <p class="meta">Edges are permanent and only written together with a node, so this writes
          ${esc(to)} v${target.version + 1} with the extra input; v${target.version} and everything
          built on it turn stale.</p>
        <label for="reason">Why connect them? (audit trail)</label>
        <textarea id="reason"></textarea>` : `<p class="hint">Click the missing node in the graph. Esc cancels.</p>`}
      <div class="row">
        ${from && to ? `<button type="button" id="doLink" class="primary">Connect</button>
          <button type="button" id="swapLink">Swap direction</button>` : ""}
        <button type="button" id="cancelMode">Cancel</button>
      </div>
    </div>`;
  markPicked();
}

function pickLinkEnd(id) {
  if (!linking.from) linking.from = id;
  else linking.to = id;
  renderLink();
}

async function doLink() {
  const target = view.byId[linking.to];
  const created = await api("/edit", {
    content: target.content, target_id: target.id, created_by: pmName(), rationale: reason(),
    add_inputs: [linking.from],
  });
  toast(`${linking.from} connected: ${target.id} → ${created.id} (v${created.version})`);
  linking = null;
  selected = created.id;
  await load();
}

function showMenu(x, y, items) {
  const m = $("#menu");
  showMenu.items = items;
  m.innerHTML = items.map((it, i) => `<button type="button" role="menuitem" data-i="${i}">${esc(it.label)}</button>`).join("");
  m.hidden = false;
  const box = $("#graph").getBoundingClientRect(); // keep the menu inside the graph area
  const main = $("main").getBoundingClientRect(); // the menu is positioned in <main>, the graph is its 2nd column
  m.style.left = `${box.left - main.left + Math.max(0, Math.min(x, box.width - m.offsetWidth - 8))}px`;
  m.style.top = `${box.top - main.top + Math.max(0, Math.min(y, box.height - m.offsetHeight - 8))}px`;
  m.querySelector("button").focus();
}

function hideMenu() {
  $("#menu").hidden = true;
}

function nodeMenu(id) {
  const n = view.byId[id];
  return [
    ...(waitingOn(n) === "pm" ? [{ label: `Answer ${id}`, run: () => openDraft("Note", [id]) }] : []),
    ...(NEXT[n.type] || []).map((t) => ({ label: `New ${t} from ${id}`, run: () => openDraft(t, [id]) })),
    { label: `Ask the agent to challenge ${id}`, run: () => requestDraft(id, "challenge") },
    { label: `Ask the agent to dig deeper on ${id}`, run: () => requestDraft(id, "dig_deeper") },
    { label: `Supporting evidence for ${id}`, run: () => openDraft("Evidence", [id], { relation: "supports" }) },
    { label: `Counter-evidence for ${id} (by hand)`, run: () => openDraft("Evidence", [id], { relation: "contradicts" }) },
    { label: `Ask a question about ${id}`, run: () => openDraft("Question", [id]) },
    { label: `Add a note to ${id}`, run: () => openDraft("Note", [id]) },
    ...(view.supersededBy[id] ? [] : [{ label: `Connect: add an input to ${id}…`, run: () => openLink(null, id) }]),
    { label: `Connect: use ${id} as an input of…`, run: () => openLink(id, null) },
  ];
}

const inside = (b, x, y) => x >= b.x1 && x <= b.x2 && y >= b.y1 && y <= b.y2;
const nodeAt = (x, y, except = null) => cy.nodes().filter((n) => n.id() !== except && inside(n.renderedBoundingBox(), x, y))[0];

// ---- data in + agent runs ----------------------------------------------

async function importCsv(file) {
  const created = await api("/import/csv", { filename: file.name, text: await file.text(), created_by: pmName() });
  toast(`${file.name} imported as ${created.id} (${created.content.rows.length} rows)`);
  selected = created.id;
  await load();
}

function showAgent(st) {
  $("#run").disabled = st.running;
  const state = st.running ? "running…" : st.exit_code == null ? "idle"
    : st.exit_code === 0 ? "last run finished" : `last run failed (exit ${st.exit_code}), see log`;
  $("#agentStatus").textContent = `Agent: ${state} · ${st.llm ? "LLM" : "rule-based (no OPENAI_API_KEY on the backend)"}`;
  $("#agentLog pre").textContent = st.log || "(no output yet)";
}

async function runAgent() {
  showAgent(await api("/agent/run", { max_actions: Number($("#actions").value) }));
  poll();
}

function poll() {
  clearTimeout(poll.timer);
  poll.timer = setTimeout(guard(async () => {
    const st = await api("/agent/status");
    showAgent(st);
    await load();
    if (st.running) poll();
    else {
      setTab("inbox");
      toast(st.exit_code === 0 ? "Agent run finished: check your inbox" : `Agent run failed (exit ${st.exit_code}), see log`, st.exit_code !== 0);
    }
  }), 1500);
}

const guard = (fn) => (...args) => Promise.resolve().then(() => fn(...args)).catch((e) => toast(e.message, true));

$("#detail").addEventListener("click", guard(async (ev) => {
  const t = ev.target.closest("button");
  if (!t) return;
  if (t.dataset.goto) select(t.dataset.goto);
  else if (t.dataset.verdict) await decide(t.dataset.verdict);
  else if (t.dataset.unpick) togglePick(t.dataset.unpick);
  else if (t.dataset.request) requestDraft(selected, t.dataset.request);
  else if (t.dataset.answer) openDraft("Note", [t.dataset.answer]);
  else if (t.dataset.redo) await runAgent();
  else if (t.id === "saveBrief") await saveBrief();
  else if (t.id === "saveEdit") await saveEdit();
  else if (t.id === "createNode") await createNode();
  else if (t.id === "doLink") await doLink();
  else if (t.id === "swapLink") { linking = { from: linking.to, to: linking.from }; renderLink(); }
  else if (t.id === "cancelMode") closeModes();
}));
$("#detail").addEventListener("change", (ev) => {
  const { id, value } = ev.target;
  if (id === "draftPick" && value) { togglePick(value); ev.target.value = ""; }
  else if (id === "draftRel") draft.relation = value;
  else if (id === "addInput" && value) openLink(value, selected);
});

cy.on("tap", "node", (ev) => {
  const id = ev.target.id();
  if (draft) togglePick(id);
  else if (linking) pickLinkEnd(id);
  else select(id);
});
cy.on("tap", (ev) => {
  if (ev.target !== cy) return;
  hideMenu();
  if (!draft && !linking) showHint();
});
cy.on("cxttap", (ev) => {
  const { x, y } = ev.renderedPosition;
  showMenu(x, y, ev.target === cy
    ? CREATABLE.map((t) => ({ label: `New ${t}`, run: () => openDraft(t) }))
    : nodeMenu(ev.target.id()));
});
// drag a node onto another to connect them; the earlier stage of the chain becomes the input
cy.on("dragfree", "node", (ev) => {
  const a = ev.target;
  const p = a.renderedPosition();
  const b = nodeAt(p.x, p.y, a.id());
  if (!b) return;
  a.position(lastPos[a.id()]);
  const aFirst = STAGE[a.data("type")] <= STAGE[b.data("type")];
  openLink(aFirst ? a.id() : b.id(), aFirst ? b.id() : a.id());
});
$("#graph").addEventListener("contextmenu", (ev) => ev.preventDefault());
$("#menu").addEventListener("click", (ev) => {
  const b = ev.target.closest("button");
  if (!b) return;
  hideMenu();
  guard(showMenu.items[b.dataset.i].run)();
});
document.addEventListener("mousedown", (ev) => { if (!ev.target.closest("#menu")) hideMenu(); });
document.addEventListener("keydown", (ev) => {
  if (ev.key !== "Escape") return;
  hideMenu();
  if (draft || linking) closeModes();
});

// palette: click opens the form (building on the selected node); drag drops onto the graph
for (const b of document.querySelectorAll("[data-new]")) {
  b.addEventListener("click", () => openDraft(b.dataset.new, selected && view.byId[selected] ? [selected] : []));
  b.addEventListener("dragstart", (ev) => ev.dataTransfer.setData("text/x-node-type", b.dataset.new));
}
$("#graph").addEventListener("dragover", (ev) => {
  if (ev.dataTransfer.types.includes("text/x-node-type")) ev.preventDefault();
});
$("#graph").addEventListener("drop", (ev) => {
  const type = ev.dataTransfer.getData("text/x-node-type");
  if (!type) return;
  ev.preventDefault();
  const box = $("#graph").getBoundingClientRect();
  const target = nodeAt(ev.clientX - box.left, ev.clientY - box.top);
  openDraft(type, target ? [target.id()] : []);
});
$("#jump").addEventListener("change", (ev) => (ev.target.value ? select(ev.target.value) : showHint()));
for (const b of document.querySelectorAll("[data-view]")) b.addEventListener("click", () => setView(b.dataset.view));
for (const id of ["#trailActor", "#trailType", "#trailChain"]) $(id).addEventListener("change", renderTimeline);
$("#trail").addEventListener("click", (ev) => {
  const target = ev.target.closest("[data-goto]") || ev.target.closest("[data-id]");
  if (target) select(target.dataset.goto || target.dataset.id);
});
$("#refresh").addEventListener("click", guard(load));
$("#work").addEventListener("click", guard(async (ev) => {
  const t = ev.target.closest("button");
  if (!t) return;
  if (t.dataset.tab) setTab(t.dataset.tab);
  else if (t.dataset.goto) select(t.dataset.goto);
  else if (t.dataset.group === "run") await runAgent();
  else if (t.dataset.group) await renderSide.actions[t.dataset.group]();
}));
$("#focusbar").addEventListener("click", (ev) => {
  const t = ev.target.closest("[data-focus]");
  if (!t) return;
  focusMode = t.dataset.focus === "on";
  focusId = focusMode ? selected : null;
  renderGraph();
  if (selected) highlight();
});
$("#focusbar").addEventListener("change", (ev) => {
  if (ev.target.id !== "showOld") return;
  showOld = ev.target.checked;
  renderGraph();
  if (selected) highlight();
});
$("#briefbar").addEventListener("click", (ev) => { if (ev.target.id === "editBrief") openBrief(); });
$("#importBtn").addEventListener("click", () => $("#csv").click());
$("#csv").addEventListener("change", guard(async (ev) => {
  const file = ev.target.files[0];
  ev.target.value = ""; // allow re-importing the same file
  if (file) await importCsv(file);
}));
$("#run").addEventListener("click", guard(runAgent));

const pm = $("#pm");
try { pm.value = localStorage.getItem("pmName") || ""; } catch { /* storage blocked: just ask each time */ }
pm.addEventListener("change", () => { try { localStorage.setItem("pmName", pm.value.trim()); } catch { /* ignore */ } });

selected = decodeURIComponent(location.hash.slice(1)) || null;
guard(load)();
guard(async () => { // a run may already be going (page reloaded mid-run)
  const st = await api("/agent/status");
  showAgent(st);
  if (st.running) poll();
})();
