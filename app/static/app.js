const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const state = { run: null, status: null, profiles: [], view: "requirements", evidenceResults: null };

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[char]));
}
function dateLabel(value) {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.valueOf()) ? esc(value) : d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}
function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove("show"), 3200);
}
async function api(url, options = {}) {
  const response = await fetch(url, { ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
  let body = {};
  try { body = await response.json(); } catch {}
  if (!response.ok) throw new Error(body.detail || "Request failed (" + response.status + ")");
  return body;
}
function busy(button, on, label) {
  if (!button) return;
  if (on) { button.dataset.original = button.innerHTML; button.disabled = true; button.textContent = label || "Working…"; }
  else { button.disabled = false; if (button.dataset.original) button.innerHTML = button.dataset.original; }
}
async function refresh() {
  try {
    const pair = await Promise.all([api("/api/status"), api("/api/runs/latest"), api("/api/profiles")]);
    state.status = pair[0];
    state.run = pair[1].run;
    state.profiles = pair[2];
    $("#profileSelect").innerHTML = state.profiles.map((x)=>'<option value="'+esc(x.id)+'">'+esc(x.label)+'</option>').join("");
    renderStatus();
    render();
  } catch (error) {
    $("#systemStatus").textContent = "API unavailable";
    $("#envPill").textContent = "API unavailable";
    $("#emptyState").classList.remove("hidden");
    $("#workspace").classList.add("hidden");
    toast(error.message);
  }
}
function renderStatus() {
  const s = state.status || {};
  const parts = [];
  if (s.llm_enabled) parts.push("LLM");
  if (s.web_search_enabled) parts.push("Web");
  $("#systemStatus").textContent = parts.length ? "Connected: " + parts.join(" · ") : "Local-first workspace";
  $("#envPill").innerHTML = '<span class="status-dot"></span>' + (parts.length ? esc(parts.join(" + ")) : "Offline-ready");
  $("#envPill").title = s.llm_enabled ? "LLM enabled (" + s.model + "); evidence may be sent to OpenAI." : "Local rules active. Optional API keys can be added in .env.";
}
function render() {
  const run = state.run;
  $("#emptyState").classList.toggle("hidden", Boolean(run));
  $("#workspace").classList.toggle("hidden", !run);
  if (!run) {
    $("#runLabel").textContent = "No run yet";
    $("#runDate").textContent = "Start with the demo dataset or add your own evidence.";
    $("#footerRun").textContent = "Local data · no run";
    return;
  }
  const reqs = run.requirements || [];
  const evidence = run.evidence || [];
  const approved = reqs.filter((r) => r.status === "approved").length;
  const isDemo = !(run.input?.raw_text || (run.input?.evidence || []).length);
  $("#runLabel").textContent = run.id;
  $("#runDate").textContent = dateLabel(run.created_at) + (isDemo ? " · synthetic demo data" : "") + (run.parent_run_id ? " · replay of " + run.parent_run_id : "");
  $("#footerRun").textContent = run.id + " · saved locally";
  $("#metricEvidence").textContent = evidence.length;
  $("#metricEvidenceMeta").textContent = evidence.filter((x) => x.in_scope).length + " in scope · " + evidence.filter((x) => !x.in_scope).length + " flagged";
  $("#metricSignals").textContent = (run.signals || []).length;
  $("#metricRequirements").textContent = reqs.length;
  $("#metricApproved").textContent = approved + " approved";
  $("#metricOpen").textContent = (reqs.length - approved) + " for review";
  $("#metricAudit").textContent = (run.audit_events || []).length;
  $("#navReqCount").textContent = reqs.length;
  $("#tabReqCount").textContent = reqs.length;
  $("#exportLink").href = "/api/runs/" + encodeURIComponent(run.id) + "/export.csv";
  renderFilters();
  renderRequirements();
  renderEvidence();
  renderAudit();
  renderPipeline();
  const savedSimulations = run.simulations || [];
  if (savedSimulations.length) showSimulation(savedSimulations[savedSimulations.length - 1].results || {});
  setView(state.view);
}
function renderFilters() {
  const select = $("#categoryFilter"), current = select.value;
  const categories = [...new Set((state.run.requirements || []).map((x) => x.category))].sort();
  select.innerHTML = '<option value="">All categories</option>' + categories.map((x) => '<option value="' + esc(x) + '">' + esc(x) + '</option>').join("");
  select.value = categories.includes(current) ? current : "";
}
function renderRequirements() {
  const category = $("#categoryFilter").value, status = $("#statusFilter").value;
  const rows = [...(state.run.requirements || [])].filter((r) => (!category || r.category === category) && (!status || r.status === status)).sort((a,b) => b.score-a.score);
  const list = $("#requirementList");
  if (!rows.length) { list.innerHTML = '<div class="empty-filter">No requirements match these filters.</div>'; return; }
  list.innerHTML = rows.map((r, index) => {
    const rank = r.score_breakdown?.category_rank || index + 1;
    const statusClass = ["approved","rejected","challenged"].includes(r.status) ? r.status : "";
    return '<article class="req-row" data-req="' + esc(r.id) + '" tabindex="0" role="button">'
      + '<div class="req-main"><span class="rank-number">' + String(rank).padStart(2,"0") + '</span><div><div class="req-title">' + esc(r.text) + '</div><div class="req-category">' + esc(r.id) + ' · ' + esc(r.category) + ' · v' + esc(r.version) + '</div></div></div>'
      + '<div class="score-wrap"><span class="score-value">' + esc(r.score) + '</span><span class="score-meter"><i style="width:' + Math.max(0,Math.min(100,Number(r.score)||0)) + '%"></i></span></div>'
      + '<span class="evidence-badge ' + esc(r.evidence_level) + '">' + esc(r.evidence_level.replaceAll("_"," ")) + '</span>'
      + '<span class="status-badge ' + statusClass + '">' + esc(r.status) + '</span><span class="row-arrow">›</span></article>';
  }).join("");
  $$(".req-row",list).forEach((row) => {
    row.addEventListener("click", () => openRequirement(row.dataset.req));
    row.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") openRequirement(row.dataset.req); });
  });
}
function renderEvidence() {
  const all = state.evidenceResults || state.run.evidence || [];
  const source = $("#sourceFilter").value, query = $("#evidenceSearch").value.toLowerCase().trim();
  const rows = all.filter((x) => (!source || x.source_type === source) && (!query || (x.text_or_value + " " + x.source_ref + " " + x.market).toLowerCase().includes(query)));
  const total = state.run.evidence || [];
  $("#evidenceSummary").textContent = total.length + " total items · " + total.filter((x) => x.in_scope).length + " in scope · " + total.filter((x) => !x.in_scope).length + " flagged as out of scope";
  $("#evidenceList").innerHTML = rows.length ? rows.map((x) => {
    const ref = x.source_type === "web" && /^https:\/\//i.test(x.source_ref)
      ? '<a href="' + esc(x.source_ref) + '" target="_blank" rel="noopener noreferrer">' + esc(x.source_ref) + '</a>'
      : esc(x.source_ref || "Imported");
    return '<article class="evidence-item"><div class="evidence-source"><span class="source-badge ' + esc(x.source_type) + '">' + esc(x.source_type) + '</span><span class="source-ref">' + ref + '</span></div>'
      + '<div class="evidence-text">' + esc(x.text_or_value) + '</div><div class="evidence-meta"><span>' + esc(x.market) + ' · ' + esc(x.date) + '</span><span class="reliability">Reliability ' + Math.round(Number(x.reliability||0)*100) + '%</span>'
      + (x.in_scope ? "" : '<span class="excluded-pill">' + esc(x.exclusion_reason || "Out of scope") + '</span>') + '</div></article>';
  }).join("") : '<div class="empty-filter">No evidence matches this search.</div>';
}
function renderAudit() {
  const filter = ($("#auditSearch")?.value || "").toLowerCase().trim();
  const events = [...(state.run.audit_events || [])].reverse().filter((x) => !filter || (x.action + " " + x.target_id + " " + x.rationale).toLowerCase().includes(filter));
  $("#auditList").innerHTML = events.length ? events.map((x) => {
    const human = x.actor?.type === "human";
    return '<article class="audit-event"><time class="audit-time">' + dateLabel(x.ts) + '</time><div class="audit-spine"><span class="audit-node ' + (human ? "human" : "") + '"></span></div>'
      + '<div class="audit-card"><div class="audit-title">' + esc(x.action.replaceAll("."," · ")) + '</div><div class="audit-rationale">' + esc(x.rationale) + '</div><div class="audit-meta">'
      + (human ? "PM" : "AI / system") + ' · ' + esc(x.actor?.name || "workbench") + ' · ' + esc(x.target_id) + '</div></div></article>';
  }).join("") : '<div class="empty-filter">No events are recorded yet.</div>';
}
function renderPipeline() {
  $$(".pipe-step[data-pipe]").forEach((x) => x.classList.add("complete"));
  const reqs = state.run.requirements || [];
  const gate = {
    M6: reqs.some((x) => ["approved","rejected","challenged","edited"].includes(x.status)),
    M7: reqs.some((x) => x.specification_status === "approved"),
    M8: (state.run.simulations || []).length > 0,
    M9: Boolean(state.run.final?.signed_off)
  };
  $$(".pipe-step[data-gate]").forEach((x) => {
    const done = Boolean(gate[x.dataset.gate]);
    x.classList.toggle("complete", done);
    x.classList.toggle("gate", !done && ["M6","M9"].includes(x.dataset.gate));
  });
}
function setView(name) {
  state.view = name;
  $$(".view-panel").forEach((x) => x.classList.toggle("hidden", x.id !== "view-" + name));
  $$(".view-tab,.nav-item").forEach((x) => x.classList.toggle("active", x.dataset.view === name));
}
function listBlock(title, values) {
  return '<div class="detail-section"><h3>' + esc(title) + '</h3><div class="trace-list">'
    + (values?.length ? values.map((x) => '<div class="trace-item">' + esc(x) + '</div>').join("") : '<div class="trace-item">None recorded</div>')
    + '</div></div>';
}
async function openRequirement(id) {
  try {
    const trace = await api("/api/trace/" + encodeURIComponent(id)), r = trace.requirement;
    $("#detailEyebrow").textContent = r.id + " · " + r.category;
    $("#detailTitle").textContent = r.text;
    const factors = r.score_breakdown?.factors || {};
    const factorRows = Object.entries(factors).map(([name,f]) => '<div class="factor-row"><span>' + esc(name.replaceAll("_"," ")) + '</span><span class="factor-track"><i style="width:' + Math.min(100,Math.max(0,Number(f.value)*100)) + '%"></i></span><b>' + esc(f.points) + ' pts</b></div>').join("");
    const signals = trace.signals.map((x) => '<div class="trace-item"><b>' + esc(x.theme.replaceAll("_"," ")) + '</b> · ' + esc(x.type) + ' · ' + esc(x.sentiment) + ' · ' + esc(x.mention_count) + ' mention(s)<br>' + esc(x.summary) + '<br><small>' + Math.round(x.share_of_feedback*100) + '% mention share · Satisfaction ' + esc(x.satisfaction_index) + '/100 · ' + x.evidence_ids.length + ' linked source(s)</small></div>').join("");
    const evidence = trace.evidence.map((x) => '<div class="trace-item"><b>' + esc(x.source_type) + '</b> · ' + esc(x.source_ref) + ' · ' + Math.round(x.reliability*100) + '% reliability<br>' + esc(x.text_or_value) + '</div>').join("");
    $("#detailBody").innerHTML = '<div class="detail-score"><strong>' + esc(r.score) + '<small style="font-size:11px;color:#8592a3">/100</small></strong><span>' + esc(r.evidence_level.replaceAll("_"," ")) + ' evidence · rank ' + esc(r.score_breakdown?.category_rank || "—") + ' in category</span><span class="status-badge ' + esc(r.status) + '">' + esc(r.status) + '</span></div>'
      + '<div class="detail-section"><h3>Why this ranks here</h3><p>' + esc(r.rationale) + '</p><p style="margin-top:6px;color:#8d98a6">Formula: ' + esc(r.score_breakdown?.formula || "Explainable weighted score") + '</p>'
      + ((r.score_breakdown?.context_notes || []).length ? '<div class="trace-list" style="margin-top:8px">' + r.score_breakdown.context_notes.map((x)=>'<div class="trace-item">'+esc(x)+'</div>').join("") + '</div>' : '') + '</div>'
      + '<div class="detail-section"><h3>Factor breakdown</h3><div class="factor-list">' + factorRows + '</div></div>'
      + listBlock("Assumptions",r.assumptions) + listBlock("Uncertainties",r.uncertainties)
      + '<div class="detail-section"><h3>M7 · Customer-facing specification · ' + esc((r.specification_status || "not_started").replaceAll("_", " ")) + '</h3><textarea class="detail-edit" id="targetSpec" placeholder="Propose a measurable target for PM review">' + esc(r.target_spec || "") + '</textarea></div>'
      + '<div class="detail-section"><h3>Signal trail · M3</h3><div class="trace-list">' + (signals || '<div class="trace-item">No signals linked.</div>') + '</div></div>'
      + '<div class="detail-section"><h3>Original sources · M1 / M2</h3><div class="trace-list">' + (evidence || '<div class="trace-item">No source evidence linked.</div>') + '</div></div>'
      + '<label class="form-label">PM comment <textarea class="detail-comment" id="decisionComment" rows="2" placeholder="Required for every review action. Rejection requires a reason."></textarea></label>'
      + '<label class="form-label">Edited requirement text <textarea class="detail-edit" id="editedText" rows="2" placeholder="Fill this in before choosing Edit."></textarea></label>'
      + '<div class="detail-actions"><button class="button button-primary" data-decision="approve">Approve</button><button class="button button-danger" data-decision="reject">Reject</button><button class="button button-warn" data-decision="challenge">Challenge</button><button class="button button-quiet" data-decision="edit">Edit / version</button><button class="button button-quiet" id="saveSpec">Save target</button><button class="button button-primary" id="approveSpec" ' + (r.target_spec ? "" : "disabled") + '>Approve spec · M7</button><span class="detail-support">M6 and M9 require PM sign-off</span></div>';
    $$("#detailBody [data-decision]").forEach((button) => button.addEventListener("click", () => submitDecision(r.id,button.dataset.decision)));
    $("#saveSpec").addEventListener("click", () => submitSpec(r.id,false));
    $("#approveSpec").addEventListener("click", () => submitSpec(r.id,true));
    $("#detailDialog").showModal();
  } catch (error) { toast(error.message); }
}
async function submitDecision(id, action) {
  const comment = $("#decisionComment").value.trim();
  if (comment.length < 2) return toast("Add a PM comment before recording this decision.");
  const body = { action, comment, actor_name: "Product Manager" };
  if (action === "edit") body.edited_text = $("#editedText").value.trim();
  try {
    const result = await api("/api/requirements/" + encodeURIComponent(id) + "/decision", { method:"POST", body:JSON.stringify(body) });
    $("#detailDialog").close();
    await loadRun(result.run_id);
    toast(action === "challenge" ? "Challenge recorded; review response is in the audit trail." : "Requirement " + action + " recorded.");
  } catch (error) { toast(error.message); }
}
async function submitSpec(id, approve) {
  const comment = $("#decisionComment").value.trim();
  if (comment.length < 2) return toast("Add a PM comment before saving the specification.");
  const body = { target_spec: $("#targetSpec").value.trim() || null, approve, comment, actor_name:"Product Manager" };
  try {
    const result = await api("/api/requirements/" + encodeURIComponent(id) + "/specification", { method:"POST", body:JSON.stringify(body) });
    $("#detailDialog").close();
    await loadRun(result.run_id);
    toast(approve ? "M7 specification approved." : "M7 target saved for PM review.");
  } catch (error) { toast(error.message); }
}
async function loadRun(id) {
  state.run = await api("/api/runs/" + encodeURIComponent(id));
  state.evidenceResults = null;
  render();
}
async function runDemo(button) {
  busy(button,true,"Running pipeline…");
  try {
    state.run = await api("/api/demo",{method:"POST",body:"{}"});
    state.evidenceResults = null; state.view = "requirements"; render();
    toast("Demo run complete. Open a requirement to review its evidence trail.");
  } catch (error) { toast(error.message); }
  finally { busy(button,false); }
}
function openImport() {
  $("#importError").textContent = ""; $("#rawEvidence").value = ""; $("#evidenceFile").value = "";
  $("#importDialog").showModal();
}
async function submitImport() {
  const button = $("#submitImport"), file = $("#evidenceFile").files[0], pasted = $("#rawEvidence").value.trim();
  if (!file && !pasted) { $("#importError").textContent = "Choose a file or paste evidence text."; return; }
  busy(button,true,"Ingesting evidence…"); $("#importError").textContent = "";
  try {
    const raw = file ? await file.text() : pasted;
    const run = await api("/api/runs",{method:"POST",body:JSON.stringify({
      profile_id:$("#profileSelect").value,file_name:file?.name || null,raw_text:raw,
      source_type:$("#importSource").value,include_web:$("#includeWeb").value === "true"
    })});
    $("#importDialog").close(); state.run=run; state.evidenceResults=null; state.view="requirements"; render();
    toast("Evidence ingested. The previous run remains in run history.");
  } catch (error) { $("#importError").textContent=error.message; }
  finally { busy(button,false); }
}
function openReplay() {
  if (!state.run) return;
  const weights = state.run.config?.weights || {};
  const weightHtml = Object.entries(weights).map(([name,value]) => '<div class="weight-control"><label><span>' + esc(name.replaceAll("_"," ")) + '</span><b id="weight-' + esc(name) + '">' + Math.round(Number(value)*100) + '%</b></label><input type="range" min="0" max="0.6" step="0.01" value="' + Number(value) + '" data-weight="' + esc(name) + '"></div>').join("");
  const rules = state.run.config?.context_rules || [];
  const ruleHtml = rules.map((rule) => '<label class="checkbox-line weight-control"><input type="checkbox" data-context="' + esc(rule.id) + '" ' + (rule.pm_confirmed ? "checked" : "") + '><span><b>' + esc(rule.id.replaceAll("_"," ")) + '</b><br>' + esc(rule.description) + '</span></label>').join("");
  $("#weightEditor").innerHTML = weightHtml + ruleHtml;
  $$("#weightEditor input[data-weight]").forEach((input) => input.addEventListener("input",() => { $("#weight-" + CSS.escape(input.dataset.weight)).textContent=Math.round(Number(input.value)*100)+"%"; }));
  $("#replayError").textContent=""; $("#replayDialog").showModal();
}
async function submitReplay() {
  const button=$("#submitReplay"), weights=Object.fromEntries($$("#weightEditor input[data-weight]").map((x)=>[x.dataset.weight,Number(x.value)]));
  const oldRules=state.run.config?.context_rules||[];
  const confirmedRules=oldRules.map((rule)=>({...rule,pm_confirmed:Boolean($$('#weightEditor input[data-context="' + CSS.escape(rule.id) + '"]')[0]?.checked)}));
  busy(button,true,"Creating branch…");
  try {
    state.run=await api("/api/runs/"+encodeURIComponent(state.run.id)+"/replay",{method:"POST",body:JSON.stringify({start_at:$("#replayStage").value,config_overrides:{weights,context_rules:confirmedRules}})});
    $("#replayDialog").close(); state.evidenceResults=null; render(); toast("Replay branch created; prior run preserved.");
  } catch(error) { $("#replayError").textContent=error.message; }
  finally { busy(button,false); }
}
async function runSimulation() {
  if (!state.run) return;
  const button=$("#runSimulation"); busy(button,true,"Simulating…");
  try {
    const result=await api("/api/runs/"+encodeURIComponent(state.run.id)+"/simulation",{method:"POST",body:JSON.stringify({
      options:{A:$("#optionA").value.trim(),B:$("#optionB").value.trim(),C:$("#optionC").value.trim()},
      include_in_score:$("#includeSimulation").checked,actor_name:"Product Manager"
    })});
    showSimulation(result); await loadRun(state.run.id); setView("simulation");
    toast(result.include_in_score?"Simulation recorded as a 10% low-evidence factor.":"Simulation recorded; main scores were not changed.");
  } catch(error) { toast(error.message); }
  finally { busy(button,false); }
}
function showSimulation(result) {
  const averages=result.option_averages||{}, max=Math.max(1,...Object.values(averages).map(Number));
  const bars=Object.entries(averages).map(([key,value])=>'<div class="sim-bar-row"><b>'+esc(key)+'</b><span class="sim-bar"><i style="width:'+Math.max(2,Number(value)/max*100)+'%"></i></span><strong>'+esc(value)+'</strong></div>').join("");
  const personas=(result.personas||[]).map((x)=>'<div class="persona-chip"><b>'+esc(x.persona)+'</b>'+x.ratings.map((r)=>esc(r.option)+" "+esc(r.rating)).join(" · ")+'</div>').join("");
  $("#simulationResults").innerHTML='<div class="sim-results-card"><div class="sim-results-head"><b>'+esc(result.label||"Synthetic customer comparison")+'</b><span class="low-evidence-pill">WEAK EVIDENCE</span></div><div class="sim-bars">'+bars+'</div><div class="persona-grid">'+personas+'</div><p class="audit-rationale">'+esc(result.note)+'</p></div>';
}
function openFinal() {
  if (!state.run) return;
  const approved=(state.run.requirements||[]).filter((x)=>x.status==="approved"&&x.specification_status==="approved");
  $("#finalRequirementList").innerHTML=approved.length?approved.map((x)=>'<label class="final-row"><input type="checkbox" value="'+esc(x.id)+'" checked><span>'+esc(x.text)+'<small>'+esc(x.id)+' · '+esc(x.score)+'/100 · '+esc(x.evidence_level.replaceAll("_"," "))+'</small></span></label>').join(""):'<div class="empty-filter">No M6-approved requirements with an M7-approved specification are ready.</div>';
  $("#finalComment").value=""; $("#finalError").textContent=""; $("#submitFinal").disabled=!approved.length; $("#finalDialog").showModal();
}
async function submitFinal() {
  const comment=$("#finalComment").value.trim();
  if (comment.length<2) { $("#finalError").textContent="Add a sign-off comment."; return; }
  const ids=$$("#finalRequirementList input:checked").map((x)=>x.value);
  if (!ids.length) { $("#finalError").textContent="Select at least one approved requirement."; return; }
  try {
    const result=await api("/api/runs/"+encodeURIComponent(state.run.id)+"/finalize",{method:"POST",body:JSON.stringify({requirement_ids:ids,comment,actor_name:"Product Manager"})});
    $("#finalDialog").close(); await loadRun(state.run.id); toast("Final list signed off with "+result.requirement_count+" approved requirement(s).");
  } catch(error) { $("#finalError").textContent=error.message; }
}
async function openHistory() {
  try {
    const runs = await api("/api/runs");
    $("#historyList").innerHTML = runs.length ? runs.map((run) => '<button class="final-row" data-run="' + esc(run.id) + '" style="width:100%;text-align:left;border:0;cursor:pointer"><span><b>' + esc(run.id) + '</b><small>' + dateLabel(run.created_at) + ' · ' + esc(run.requirement_count) + ' requirements · ' + esc(run.status) + (run.parent_run_id ? ' · replay from ' + esc(run.replay_from) : ' · source run') + '</small></span></button>').join("") : '<div class="empty-filter">No runs yet.</div>';
    $$("#historyList [data-run]").forEach((button) => button.addEventListener("click",async()=>{ $("#historyDialog").close(); await loadRun(button.dataset.run); }));
    $("#historyDialog").showModal();
  } catch(error) { toast(error.message); }
}
async function semanticSearch() {
  if (!state.run) return;
  const q=$("#evidenceSearch").value.trim();
  if (!q) { state.evidenceResults=null; renderEvidence(); return; }
  try {
    const result=await api("/api/evidence/search?run_id="+encodeURIComponent(state.run.id)+"&q="+encodeURIComponent(q));
    state.evidenceResults=result.results||[]; renderEvidence();
  } catch(error) { toast(error.message); }
}
function bindEvents() {
  $$(".view-tab,.nav-item").forEach((x)=>x.addEventListener("click",()=>setView(x.dataset.view)));
  $("#categoryFilter").addEventListener("change",renderRequirements);
  $("#statusFilter").addEventListener("change",renderRequirements);
  $("#sourceFilter").addEventListener("change",renderEvidence);
  $("#evidenceSearch").addEventListener("input",()=>{state.evidenceResults=null;renderEvidence();});
  $("#evidenceSearch").addEventListener("keydown",(e)=>{if(e.key==="Enter")semanticSearch();});
  $("#openImport").addEventListener("click",openImport); $("#emptyImport").addEventListener("click",openImport);
  $("#cancelImport").addEventListener("click",()=>$("#importDialog").close()); $("#submitImport").addEventListener("click",submitImport);
  $("#runDemo").addEventListener("click",(e)=>runDemo(e.currentTarget)); $("#emptyDemo").addEventListener("click",(e)=>runDemo(e.currentTarget));
  $("#openReplay").addEventListener("click",openReplay); $("#cancelReplay").addEventListener("click",()=>$("#replayDialog").close());
  $("#submitReplay").addEventListener("click",submitReplay); $("#runSimulation").addEventListener("click",runSimulation);
  $("#submitFinal").addEventListener("click",submitFinal); $("#cancelFinal").addEventListener("click",()=>$("#finalDialog").close());
  $("#openFinal").addEventListener("click",openFinal);
  $("#openHistory").addEventListener("click",openHistory);
  $("#auditSearch").addEventListener("input",renderAudit);
}
bindEvents();
refresh();
