// Graph-first PM view over the decision-graph API (served by the backend at /ui, same origin).
import { layout, STAGE } from "./layout.js";

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

const COLORS = Object.fromEntries(
  Object.keys(STAGE).map((t) => [t, getComputedStyle(document.documentElement).getPropertyValue(`--${t}`).trim()]),
);

const cy = cytoscape({
  container: $("#graph"),
  minZoom: 0.2,
  maxZoom: 2.5,
  style: [
    { selector: "node", style: {
      shape: "round-rectangle", width: 210, height: 64, "background-color": (n) => COLORS[n.data("type")],
      label: "data(label)", "text-wrap": "wrap", "text-max-width": 196, "font-size": 11,
      "text-valign": "center", color: "#0f172a", "border-width": 1, "border-color": "#cbd5e1",
    } },
    { selector: "node.stale", style: { "border-width": 3, "border-style": "dashed", "border-color": "#f97316" } },
    { selector: "node.superseded", style: { opacity: 0.45 } },
    { selector: "node.approve", style: { "border-width": 4, "border-color": "#16a34a" } },
    { selector: "node.reject", style: { "border-width": 4, "border-color": "#dc2626" } },
    { selector: "node.postpone", style: { "border-width": 4, "border-color": "#a16207" } },
    { selector: "node.awaiting", style: { "border-width": 4, "border-style": "double", "border-color": "#7c3aed" } },
    { selector: "node.picked", style: { "border-width": 5, "border-style": "solid", "border-color": "#2563eb" } },
    { selector: "node:selected", style: { "overlay-color": "#2563eb", "overlay-opacity": 0.15, "overlay-padding": 6 } },
    { selector: "edge", style: {
      width: 1.5, "line-color": "#94a3b8", "target-arrow-color": "#94a3b8", "target-arrow-shape": "triangle",
      "curve-style": "bezier", "font-size": 9, color: "#64748b", "text-background-color": "#f8fafc",
      "text-background-opacity": 1,
    } },
    { selector: "edge.contradicts", style: { "line-color": "#dc2626", "target-arrow-color": "#dc2626", label: "contradicts" } },
    { selector: "edge.supports", style: { "line-color": "#16a34a", "target-arrow-color": "#16a34a", label: "supports" } },
    { selector: "edge.scores", style: { "line-style": "dashed", label: "scores" } },
    { selector: "edge.version", style: { "line-style": "dotted", "line-color": "#f97316", "target-arrow-color": "#f97316", label: "new version" } },
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
  return { byId, decisionsFor, supersededBy, inputs, dependents };
}

const summary = (n) => {
  const c = n.content || {};
  if (c.rows) return `${c.file ?? "file"} · ${c.rows.length} rows`;
  return String(c.text ?? c.quote ?? c.file ?? c.verdict ?? JSON.stringify(c));
};
const verdictOf = (id) => (view.decisionsFor[id] || []).at(-1)?.content?.verdict;

// ---- graph -------------------------------------------------------------

function render() {
  const drawn = graph.nodes.filter((n) => n.type in STAGE);
  const pos = layout(drawn, graph.edges);
  lastPos = pos;
  const grew = drawn.length > cy.nodes().length; // new nodes (e.g. mid agent run) must stay in view
  cy.elements().remove();
  cy.add(drawn.map((n) => ({
    group: "nodes",
    data: { id: n.id, type: n.type, label: `${n.id}${n.version > 1 ? ` v${n.version}` : ""}\n${short(summary(n), 70)}` },
    position: pos[n.id],
    classes: [n.status === "stale" && "stale", view.supersededBy[n.id] && "superseded", verdictOf(n.id),
      waitingOn(n) && "awaiting"].filter(Boolean).join(" "),
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
  if (grew) {
    cy.fit(undefined, 40);
    if (cy.zoom() > 1) { cy.zoom(1); cy.center(); } // a 2-node graph shouldn't fill the screen
  }

  $("#empty").hidden = graph.nodes.length > 0;
  renderStats();
  renderJump();
  if (draft || linking) markPicked(); // an open form must survive redraws (e.g. agent polling)
  else if (selected && view.byId[selected]) select(selected);
  else showHint();
  renderTimeline();
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

// ---- selection + detail panel ------------------------------------------

function select(id) {
  // a redraw of the same node must not wipe what the PM is typing
  const keep = id === selected && {
    reason: $("#reason")?.value, edit: $("#edit")?.value, open: $(".actions details")?.open,
  };
  selected = id;
  cy.elements().removeClass("faded").unselect();
  const el = cy.getElementById(id);
  if (el.nonempty()) {
    cy.elements().addClass("faded");
    el.predecessors().union(el.successors()).union(el).removeClass("faded");
    el.select();
  }
  $("#jump").value = id;
  history.replaceState(null, "", `#${id}`); // shareable link to this node
  showDetail(view.byId[id]);
  renderTimeline();
  if (keep && $("#reason")) {
    $("#reason").value = keep.reason ?? "";
    if (keep.edit !== undefined) $("#edit").value = keep.edit;
    $(".actions details").open = Boolean(keep.open);
  }
}

function showHint() {
  selected = null;
  history.replaceState(null, "", location.pathname);
  cy.elements().removeClass("faded");
  $("#detail").innerHTML = `<p class="hint">Select a node to see its chain, content and decisions.</p>`;
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
    ${n.status === "stale" && !newer ? `<p class="warn">Something this is built on changed — the agent should redo or confirm it.</p>` : ""}
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
  $("#graph").hidden = v !== "graph";
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
  if (!["Question", "Note"].includes(n.type)) return null;
  if (n.created_by.startsWith("PM:")) return pmInputDoneBy(n) ? null : "agent";
  return n.type === "Question" && !(view.dependents[n.id] || []).length ? "pm" : null;
}

function enterMode() {
  hideMenu();
  selected = null;
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
  m.style.left = `${Math.max(0, Math.min(x, box.width - m.offsetWidth - 8))}px`;
  m.style.top = `${Math.max(0, Math.min(y, box.height - m.offsetHeight - 8))}px`;
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
    else toast(st.exit_code === 0 ? "Agent run finished" : `Agent run failed (exit ${st.exit_code}), see log`, st.exit_code !== 0);
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
