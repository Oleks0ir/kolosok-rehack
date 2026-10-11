// Start screen: the PM's first choices drawn as the three M stripes flowing down like a Sankey
// diagram. At each choice the stripes fan out to the options; the one the PM picks pulls them
// back together and they flow on through it to the next choice, the brief and the Start button.
// Motion follows Apple's fluid-interface rules: critically damped springs that start from the
// current on-screen value, so every change can be redirected mid-flight.

const N = 3; // stripes: light blue, dark blue, red
const W = 10; // width of one stripe (px); they touch, like the M stripes
const FORK = 96; // vertical run in which the stripes curve into a row (= the row's top padding)
const RESPONSE = 0.45; // spring response in seconds (Apple: 0.3–0.4 for UI moves, a bit calmer here)
const DAMPING = 1; // critically damped: no overshoot
const DEFAULT_GOAL = "Which customer requirements should the successor generation fulfil, "
  + "based on what customers say about the current model?";
const UPLOAD = "__upload";

const STAGES = [
  { key: "vehicle", title: "Vehicle", hint: "Whose successor are we planning?", options: [
    { value: "BMW 1 Series", label: "1 Series", sub: "F70" },
    { value: "BMW 5 Series", label: "5 Series", sub: "G60" },
    { value: "BMW 7 Series", label: "7 Series", sub: "G70" }] },
  { key: "market", title: "Market", hint: "Where should it win?", options: [
    { value: "United States", label: "USA", sub: "US" },
    { value: "Europe", label: "Europe", sub: "EU" },
    { value: "China", label: "China", sub: "CN" }] },
  { key: "sources", title: "Sources", hint: "What the agent may read. Pick one or more.", multi: true, options: [] },
  { key: "brief", title: "Brief", hint: "The question the agent works on. Edit it if you like." },
  { key: "launch", title: "Start", hint: "Every step is recorded under your name." },
];

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * root: the empty <section id="start">. loadDatasets: () => Promise<[{name, rows}]>.
 * onStart({vehicle, market, datasets, file, goal, name, steps}): does the API work; throw to stay.
 */
export function createStart(root, { loadDatasets, onStart }) {
  const choice = { vehicle: null, market: null, sources: new Set(), file: null };
  let anchors = Array.from({ length: N }, () => ({})); // per stripe: {stage: {x, y (springs), h, through}}
  let launching = false;
  let frame = 0;

  root.innerHTML = `
    <form class="start-inner" novalidate>
      <svg class="flow" aria-hidden="true"></svg>
      <div class="intro">
        <p class="kicker"><span class="mark" aria-hidden="true"><i></i><i></i><i></i></span>Decision Graph</p>
        <h1 id="startTitle">New decision project</h1>
        <p class="lede">Make three choices. The agent then builds the reasoning step by step, and you
          review and steer every link of the chain.</p>
      </div>
      ${STAGES.map(rowHtml).join("")}
    </form>
    <input type="file" class="csv" accept=".csv,text/csv" hidden>`;
  const form = root.querySelector("form");
  const svg = root.querySelector(".flow");
  const rows = [...root.querySelectorAll(".row")];
  const csv = root.querySelector(".csv");

  function rowHtml(s, i) {
    let body;
    if (s.key === "brief") {
      body = `<label class="brief card" data-target>
        <span class="eyebrow">What should the agent work out?</span>
        <textarea name="goal" rows="3">${esc(DEFAULT_GOAL)}</textarea></label>`;
    } else if (s.key === "launch") {
      body = `<div class="launch">
          <label class="field"><span>Your name</span><input name="pm" autocomplete="name" required></label>
          <label class="field steps"><span>Agent steps</span><input name="steps" type="number" min="1" max="20" value="8"></label>
          <button type="submit" class="go" data-target>Start agent</button>
        </div>
        <p class="error" role="alert"></p>`;
    } else {
      body = `<div class="options" role="group" aria-label="${esc(s.title)}">${optionsHtml(s)}</div>`;
    }
    return `<div class="row" data-stage="${i}">
      <div class="label"><span class="num">${i + 1}</span><div><h2>${esc(s.title)}</h2><p>${esc(s.hint)}</p></div></div>
      <div class="body">${body}</div></div>`;
  }

  function optionsHtml(s) {
    if (!s.options.length) return `<span class="loading">loading…</span>`;
    return s.options.map((o) => `<button type="button" class="opt card" data-target data-value="${esc(o.value)}"
      aria-pressed="false"><b>${esc(o.label)}</b><span>${esc(o.sub)}</span></button>`).join("");
  }

  // ---- state -------------------------------------------------------------

  const answered = (s) => {
    const key = STAGES[s].key;
    if (key === "sources") return choice.sources.size > 0;
    if (key === "brief") return true;
    if (key === "launch") return launching;
    return choice[key] !== null;
  };

  /** Stages shown: everything up to and including the first open choice. */
  function visibleStages() {
    const vis = [];
    for (let s = 0; s < STAGES.length; s++) {
      if (!targetsOf(s).length) break; // e.g. sources still loading
      vis.push(s);
      if (!answered(s)) break;
    }
    return vis;
  }

  /** The cards the stripes flow into at stage s: the picked ones, or all options while open. */
  function targetsOf(s) {
    const all = [...rows[s].querySelectorAll("[data-target]")];
    const picked = all.filter((el) => el.classList.contains("on"));
    return picked.length ? picked : all;
  }

  function pick(s, value) {
    const st = STAGES[s];
    if (st.multi) {
      if (value === UPLOAD && !choice.sources.has(UPLOAD)) { csv.click(); return; } // picked once a file is chosen
      if (choice.sources.has(value)) choice.sources.delete(value); else choice.sources.add(value);
      if (value === UPLOAD) choice.file = null;
    } else {
      choice[st.key] = value;
    }
    update();
  }

  /** Re-mark the options, reveal what's next and send the stripes there. */
  function update() {
    STAGES.forEach((st, s) => {
      if (!st.options) return;
      const on = (v) => (st.multi ? choice.sources.has(v) : choice[st.key] === v);
      for (const b of rows[s].querySelectorAll(".opt")) {
        b.classList.toggle("on", on(b.dataset.value));
        b.setAttribute("aria-pressed", String(on(b.dataset.value)));
        b.classList.toggle("off", answered(s) && !on(b.dataset.value));
      }
    });
    const upload = root.querySelector(`.opt[data-value="${UPLOAD}"] span`);
    if (upload) upload.textContent = choice.file ? choice.file.name : "upload a file";
    const vis = visibleStages();
    const opened = rows.filter((r, s) => vis.includes(s) && !r.classList.contains("shown"));
    rows.forEach((r, s) => {
      const shown = vis.includes(s);
      r.classList.toggle("shown", shown);
      r.inert = !shown;
    });
    route();
    // a newly opened row scrolls into view (the brief opens together with the Start row)
    if (opened.length && vis.length > 1) {
      setTimeout(() => opened.at(-1).scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "nearest" }), 120);
    }
  }

  // ---- geometry + springs ------------------------------------------------

  /** Position of el inside the form, ignoring transforms (rows slide in while the stripes aim at them). */
  function box(el) {
    let x = 0, y = 0;
    for (let e = el; e && e !== form; e = e.offsetParent) { x += e.offsetLeft; y += e.offsetTop; }
    return { cx: x + el.offsetWidth / 2, top: y, h: el.offsetHeight };
  }

  function originX() {
    return box(rows[0].querySelector(".body")).cx;
  }

  const spring = (v) => ({ v, vel: 0, t: v });
  const springs = () => anchors.flatMap(Object.values).flatMap((a) => [a.x, a.o, a.y]);

  /**
   * Set every stripe's target at every visible stage; new stages grow out of the previous one.
   * An anchor is where a stripe enters a card: x = the card's center, o = the stripe's offset
   * from it (stripes sharing a card lie side by side), y = the card's top, h = its height.
   */
  function route() {
    svg.setAttribute("width", form.scrollWidth);
    svg.setAttribute("height", form.scrollHeight);
    const vis = visibleStages();
    const ox = originX();
    for (let i = 0; i < N; i++) {
      const next = {};
      let exit = { x: ox, o: (i - 1) * W, y: 0 };
      for (const s of vis) {
        const T = targetsOf(s);
        const cardOf = (j) => Math.floor((j * T.length) / N); // in order, so stripes never cross
        const t = cardOf(i);
        const group = [...Array(N).keys()].filter((j) => cardOf(j) === t); // stripes sharing this card
        const b = box(T[t]);
        // a new stage grows out of where the stripe is now
        const a = anchors[i][s] ?? { x: spring(exit.x), o: spring(exit.o), y: spring(exit.y) };
        a.x.t = b.cx; a.o.t = (group.indexOf(i) - (group.length - 1) / 2) * W; a.y.t = b.top;
        a.h = b.h; a.through = answered(s);
        next[s] = a;
        exit = { x: a.x.v, o: a.o.v, y: a.y.v + a.h };
      }
      if (launching) { // the bundle shoots on down, past the bottom of the page
        const a = anchors[i].tail ?? { x: spring(exit.x), o: spring(exit.o), y: spring(exit.y) };
        a.x.t = exit.x; a.o.t = exit.o; a.y.t = form.scrollHeight + 400; a.h = 0; a.through = false;
        next.tail = a;
      }
      anchors[i] = next;
    }
    kick();
  }

  function kick() {
    if (reducedMotion()) {
      for (const s of springs()) { s.v = s.t; s.vel = 0; }
      draw();
      return;
    }
    if (frame) return;
    let last = performance.now();
    const tick = (now) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      let moving = false;
      for (const s of springs()) moving = step(s, dt) || moving;
      draw();
      frame = moving ? requestAnimationFrame(tick) : 0;
    };
    frame = requestAnimationFrame(tick);
  }

  /** One spring step, in small sub-steps so it stays stable; X and Y spring independently. */
  function step(s, dt) {
    const k = (2 * Math.PI / RESPONSE) ** 2;
    const c = (4 * Math.PI * DAMPING) / RESPONSE;
    for (let t = 0; t < dt; t += 1 / 240) {
      const h = Math.min(1 / 240, dt - t);
      s.vel += (-k * (s.v - s.t) - c * s.vel) * h;
      s.v += s.vel * h;
    }
    if (Math.abs(s.v - s.t) < 0.05 && Math.abs(s.vel) < 0.05) { s.v = s.t; s.vel = 0; return false; }
    return true;
  }

  /**
   * Path commands for a stripe running from center px (offset po) at height py into center x
   * (offset o) at height y: straight down, then an S-bend within FORK px. The offset is applied
   * along the curve's normal, not sideways, so stripes running together stay parallel and keep
   * their full width through the bend.
   */
  function curve(px, po, py, x, o, y) {
    const cs = Math.max(py, y - FORK);
    const k = (y - cs) / 2;
    let d = cs > py ? `L${(px + po).toFixed(1)},${cs.toFixed(1)}` : "";
    const SAMPLES = 28;
    for (let j = 1; j <= SAMPLES; j++) {
      const t = j / SAMPLES, u = 1 - t;
      // cubic Bézier P0=(px,cs) P1=(px,cs+k) P2=(x,y-k) P3=(x,y) and its derivative
      const bx = (u * u * u + 3 * u * u * t) * px + (3 * u * t * t + t * t * t) * x;
      const by = u * u * u * cs + 3 * u * u * t * (cs + k) + 3 * u * t * t * (y - k) + t * t * t * y;
      const dx = 6 * u * t * (x - px);
      const dy = 3 * u * u * k + 6 * u * t * (y - k - cs - k) + 3 * t * t * k;
      const len = Math.hypot(dx, dy);
      const [nx, ny] = len > 1e-6 ? [dy / len, -dx / len] : [1, 0];
      const off = po + (o - po) * t * t * (3 - 2 * t); // ease from the old offset to the new one
      d += `L${(bx + nx * off).toFixed(1)},${(by + ny * off).toFixed(1)}`;
    }
    return d;
  }

  function draw() {
    const vis = visibleStages();
    const ox = originX();
    const paths = [];
    const exits = []; // per stage: where the bundle leaves it (center), for the ghost lines
    let prev = { x: ox, y: 0 };
    for (const s of vis) {
      const as = anchors.map((a) => a[s]).filter(Boolean);
      if (!as.length) break;
      exits[s] = prev;
      prev = { x: as.reduce((t, a) => t + a.x.v, 0) / as.length, y: Math.max(...as.map((a) => a.y.v + a.h)) };
    }
    // thin grey lines to the options that aren't picked keep them part of the flow (and clickable)
    for (const s of vis) {
      if (!STAGES[s].options || !exits[s]) continue;
      const T = targetsOf(s);
      for (const el of rows[s].querySelectorAll(".opt")) {
        if (T.includes(el)) continue;
        const b = box(el);
        const e = exits[s];
        paths.push(`<path class="ghost" d="M${e.x},${e.y}${curve(e.x, 0, e.y, b.cx, 0, b.top)}"/>`);
      }
    }
    for (let i = 0; i < N; i++) {
      let px = ox, po = (i - 1) * W, py = 0;
      let d = `M${px + po},${py}`;
      for (const key of [...vis, "tail"]) {
        const a = anchors[i][key];
        if (!a) continue;
        d += curve(px, po, py, a.x.v, a.o.v, a.y.v);
        if (!a.through) { d += `l0,2`; break; } // ends tucked under the card it points at
        d += `L${(a.x.v + a.o.v).toFixed(1)},${(a.y.v + a.h).toFixed(1)}`;
        px = a.x.v; po = a.o.v; py = a.y.v + a.h;
      }
      paths.push(`<path class="stripe s${i}" d="${d}"/>`);
    }
    svg.innerHTML = paths.join("");
  }

  // ---- events ------------------------------------------------------------

  form.addEventListener("click", (ev) => {
    const b = ev.target.closest(".opt");
    if (!b) return;
    pick(Number(b.closest(".row").dataset.stage), b.dataset.value);
  });
  csv.addEventListener("change", () => {
    const file = csv.files[0];
    csv.value = ""; // the same file can be picked again
    if (!file) return;
    choice.file = file;
    choice.sources.add(UPLOAD);
    update();
  });
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (launching) return;
    const err = root.querySelector(".error");
    const name = form.pm.value.trim();
    const goal = form.goal.value.trim();
    err.textContent = !name ? "Enter your name: every step you take is recorded under it."
      : !goal ? "Write what the agent should work out." : "";
    if (err.textContent) { (name ? form.goal : form.pm).focus(); return; }
    const go = root.querySelector(".go");
    launching = true;
    go.disabled = true;
    go.textContent = "Starting…";
    update();
    try {
      await onStart({
        vehicle: choice.vehicle, market: choice.market, goal, name,
        datasets: [...choice.sources].filter((v) => v !== UPLOAD), file: choice.file,
        steps: Math.min(20, Math.max(1, Number(form.steps.value) || 8)),
      });
      launching = false;
      leave();
    } catch (e) {
      launching = false;
      err.textContent = e.message;
      go.disabled = false;
      go.textContent = "Start agent";
      update();
    }
  });
  new ResizeObserver(() => { if (!root.hidden) route(); }).observe(form);

  // the rest of the page is behind the start screen: keep it out of the tab order
  const setBackdropInert = (on) => {
    for (const el of document.body.children) if (el !== root) el.inert = on;
  };

  function leave() {
    root.classList.add("leaving");
    setTimeout(() => { root.hidden = true; root.classList.remove("leaving"); setBackdropInert(false); },
      reducedMotion() ? 0 : 450);
  }

  let loaded = false;
  async function show({ name = "" } = {}) {
    if (!root.hidden) return;
    root.hidden = false;
    setBackdropInert(true);
    if (name && !form.pm.value) form.pm.value = name;
    anchors = Array.from({ length: N }, () => ({})); // stripes grow in from the top
    update();
    if (loaded) return;
    loaded = true;
    const datasets = await loadDatasets();
    STAGES[2].options = [
      ...datasets.map((d) => ({ value: d.name, label: d.name.replace(/\.csv$/i, "").replace(/[_-]+/g, " "), sub: `${d.rows} rows` })),
      { value: UPLOAD, label: "Your CSV", sub: "upload a file" },
    ];
    rows[2].querySelector(".options").innerHTML = optionsHtml(STAGES[2]);
    update();
  }

  return {
    show,
    hide() { if (!launching && !root.hidden) { root.hidden = true; setBackdropInert(false); } },
    get launching() { return launching; },
  };
}
