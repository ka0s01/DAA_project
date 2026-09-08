/* Delivery Command Center — dashboard logic (vanilla JS, no build step).
 *
 * Data flow: GET /api/data once → draw the city. Plan previews and the whole
 * simulation live server-side; this file only renders responses and drives the
 * buttons. While a run is live it polls /api/sim/state every ~450 ms — each poll
 * also advances the simulated clock server-side by real elapsed time × timescale.
 */
"use strict";

/* ------------------------------------------------------------------ */
/* tiny DOM helpers                                                    */
/* ------------------------------------------------------------------ */
const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  for (const c of children) {
    if (c == null) continue;
    node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return node;
}
function svg(tag, attrs = {}, children = []) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  for (const c of children) {
    if (c == null) continue;
    node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return node;
}
const esc = (s) => String(s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* mm:ss from simulated minutes */
function fmtMin(min) {
  if (min == null) return "--:--";
  const m = Math.floor(min / 60), s = Math.round(min % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}
const PRIO = { 1: "P1", 2: "P2", 3: "P3" };
const SHORT = {
  fire: "Fire Stn", hospital: "Hospital", clinic: "Clinic", pharmacy: "Pharmacy",
  school: "High School", electronics: "Electronics", mall: "Central Mall",
  grocery: "Grocery", market: "Northgate Mkt", diner: "Harbor Diner",
  bookstore: "Bookstore", cafe: "Park Cafe",
};

/* ------------------------------------------------------------------ */
/* app state                                                           */
/* ------------------------------------------------------------------ */
const D = { config: null, roads: [], roadById: {}, stops: [], stopById: {},
            items: [], col_x: [], row_y: [], avenues: [], streets: [],
            bridge_rows: [], river: null, depot: null };
let params = { capacity: 430, premium: 220, strictness: 4.0, scope: "loaded",
               excluded: new Set() };
let plan = null;                  // last /api/plan result
let state = null;                 // last /api/sim/state snapshot
let lastEvt = 0;                  // highest server event id we've shown
let pollTimer = null;
const runningPhase = () => state && (state.phase === "running" || state.phase === "paused");

const layers = {};                // svg layers inside #world
const roadEl = {};                // road id -> {vis, hit, mid, name, kind}
const tipBox = $("tooltip");
const mapPanel = $("map-panel");

/* ------------------------------------------------------------------ */
/* initial data + first plan preview                                   */
/* ------------------------------------------------------------------ */
async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  const body = await r.json();
  if (!r.ok) throw new Error(body.error || `${r.status} ${url}`);
  return body;
}
function svgScale() {
  const r = mapPanel.querySelector("svg").getBoundingClientRect();
  return r.width / 1072;
}

async function init() {
  const data = await fetchJSON("/api/data");
  Object.assign(D, data);
  data.roads.forEach((rd) => (D.roadById[rd.id] = rd));
  data.stops.forEach((s) => (D.stopById[s.id] = s));
  params.capacity = data.config.van_capacity_kg;
  params.premium = data.config.priority_premium_default;
  params.strictness = data.config.strictness_default;

  // seed any active disruptions / phase that survived a reload
  const snap = await fetchJSON("/api/sim/state");
  lastEvt = Math.max(0, ...(snap.events || []).map((e) => e.id));
  state = { ...snap, events: [] };

  drawCity();
  buildCatalog();
  syncControls();
  wireEvents();

  await planAndPreview();
  if (plan) {
    pushEvent(fmtMin(state.clock), "Awaiting dispatch — dashed route below is the preview.",
              "plan");
    renderRouteOrder();
  }
}

/* ------------------------------------------------------------------ */
/* tooltip (HTML coords)                                               */
/* ------------------------------------------------------------------ */
function tooltip(html, x, y) {
  tipBox.innerHTML = html;
  tipBox.style.display = "block";
  const s = svgScale();
  const rect = mapPanel.getBoundingClientRect();
  const px = rect.left + (44 + x) * s;
  const py = rect.top + (30 + y) * s;
  tipBox.style.left = Math.min(px + 14, rect.right - tipBox.offsetWidth - 8) + "px";
  tipBox.style.top = (py - tipBox.offsetHeight - 12) + "px";
}
function moveTip(e) {
  if (tipBox.style.display === "none") return;
  const rect = mapPanel.getBoundingClientRect();
  tipBox.style.left = Math.min(e.clientX - rect.left + 14,
    rect.right - rect.left - tipBox.offsetWidth - 8) + "px";
  tipBox.style.top = (e.clientY - rect.top - tipBox.offsetHeight - 10) + "px";
}

/* ------------------------------------------------------------------ */
/* map drawing                                                         */
/* ------------------------------------------------------------------ */
function drawCity() {
  const wrap = $("map-wrap");
  wrap.innerHTML = "";
  const svgRoot = svg("svg", { viewBox: "0 0 1072 660" });
  wrap.appendChild(svgRoot);

  const world = svg("g", { transform: "translate(44,30)" });
  svgRoot.appendChild(world);

  // --- street / avenue furniture (in outer margin) ---
  D.streets.forEach((name, i) => {
    svgRoot.appendChild(svg("text", { class: "street-label", x: 22,
      y: 30 + D.row_y[i] + 4, "text-anchor": "end" }, name));
  });
  D.avenues.forEach((name, i) => {
    svgRoot.appendChild(svg("text", { class: "avenue-label", x: 44 + D.col_x[i],
      y: 14, "text-anchor": "middle" }, name));
  });

  // --- river (bottom) ---
  const r = D.river;
  world.appendChild(svg("rect", { class: "river", x: r.left - 8, y: -14,
    width: (r.right - r.left) + 16, height: 660, rx: 8 }));
  const rmid = (r.left + r.right) / 2;
  world.appendChild(svg("text", { class: "river-label", x: rmid, y: 340,
    transform: `rotate(-90 ${rmid} 340)`, "text-anchor": "middle" }, "R I V E R"));

  // --- roads (visual + transparent click target) ---
  for (const rd of D.roads) {
    const a = rd.a, b = rd.b, br = rd.kind === "bridge";
    const vis = svg("line", { class: `road ${br ? "bridge" : ""}`,
      x1: a.x, y1: a.y, x2: b.x, y2: b.y });
    const hit = svg("line", { class: `road hit ${br ? "bridge" : ""}`,
      x1: a.x, y1: a.y, x2: b.x, y2: b.y });
    const g = svg("g", {}, [vis, hit]);
    world.appendChild(g);
    roadEl[rd.id] = { vis, hit, name: rd.name, kind: rd.kind,
      mid: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 } };
  }

  // --- route → stops → disruption badges → van (top-most) ---
  layers.route = svg("g"); world.appendChild(layers.route);
  layers.stops = svg("g"); world.appendChild(layers.stops);
  layers.badges = svg("g"); world.appendChild(layers.badges);
  layers.van = svg("g", { style: "display:none" }); world.appendChild(layers.van);

  // --- depot + stops ---
  const dep = D.depot;
  layers.stops.appendChild(svg("rect", { class: "depot",
    x: dep.x - 9, y: dep.y - 9, width: 18, height: 18, rx: 4 }));
  layers.stops.appendChild(svg("text", { class: "depot-label",
    x: dep.x, y: dep.y + 26, "text-anchor": "middle" }, "DEPOT"));

  for (const st of D.stops) {
    const grp = svg("g", {});
    const c = svg("circle", { class: `stop p${st.priority}`,
      cx: st.x, cy: st.y, r: 11 });
    grp.appendChild(c);
    const below = st.y < 300;
    grp.appendChild(svg("text", { class: "stop-label", x: st.x + 14,
      y: st.y + (below ? 18 : -16), "text-anchor": "start" }, SHORT[st.id] || st.name));
    grp.appendChild(svg("text", { class: "stop-chip", x: st.x - 15, y: st.y + 4,
      "text-anchor": "middle" }, PRIO[st.priority]));
    layers.stops.appendChild(grp);
    st._circle = c;
    st._grp = grp;
    grp.addEventListener("mouseenter", () => tooltip(
      `<b>${esc(st.name)}</b> · ${PRIO[st.priority]} · service ${st.service} min` +
      (st.deadline ? ` · deadline ${fmtMin(st.deadline)}` : ""), st.x, st.y));
    grp.addEventListener("mousemove", moveTip);
    grp.addEventListener("mouseleave", () => (tipBox.style.display = "none"));
  }

  // --- van ---
  const v = svg("g", { class: "van-g" }, [
    svg("circle", { class: "van-ring", r: 15 }),
    svg("circle", { class: "van", r: 9 }),
    svg("circle", { r: 2, fill: "#fff" }),
  ]);
  layers.van.appendChild(v);

  wireRoadClicks();
}

/* ------------------------------------------------------------------ */
/* road interaction                                                    */
/* ------------------------------------------------------------------ */
function wireRoadClicks() {
  for (const rd of D.roads) {
    const h = roadEl[rd.id].hit;
    h.addEventListener("mouseenter", () => {
      const act = (state && state.disruptions || []).find((x) => x.id === rd.id);
      tooltip(`<b>${esc(rd.name)}</b> · ${rd.kind} · ${rd.minutes} min` +
        (act ? `<br><span style="color:#f87171">● ${act.kind === "roadblock" ? "closed" : "slowed ×" + act.factor}</span>`
             : "<br>click = roadblock · alt-click = traffic"), rd.a.x, rd.a.y);
    });
    h.addEventListener("mousemove", moveTip);
    h.addEventListener("mouseleave", () => (tipBox.style.display = "none"));
    h.addEventListener("click", (e) =>
      toggleDisruption(rd.id, (e.altKey || e.shiftKey) ? "traffic" : "roadblock"));
  }
}

function setRoadClass(rid, cls) {
  const er = roadEl[rid];
  if (!er) return;
  er.vis.classList.remove("blocked", "traffic");
  er.hit.classList.remove("blocked");
  if (cls) { er.vis.classList.add(cls); if (cls === "blocked") er.hit.classList.add(cls); }
}

function paintDisruptions(disruptions) {
  D.roads.forEach((rd) => setRoadClass(rd.id, null));
  layers.badges.innerHTML = "";
  for (const d of disruptions || []) {
    const er = roadEl[d.id];
    if (!er) continue;
    setRoadClass(d.id, d.kind === "roadblock" ? "blocked" : "traffic");
    layers.badges.appendChild(svg("text", { x: er.mid.x, y: er.mid.y + 6,
      "text-anchor": "middle", style: "font-size:17px;pointer-events:none" },
      d.kind === "roadblock" ? "⛔" : "🐢"));
  }
}

async function toggleDisruption(rid, kind) {
  const active = ((state && state.disruptions) || []).filter((d) => d.id === rid);
  const same = active.find((d) => d.kind === kind);
  const post = (path, body) => fetchJSON(path, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (same) {                       // same disruption present → lift it
    await post("/api/disrupt/clear", { id: rid });
  } else {
    if (active.length) await post("/api/disrupt/clear", { id: rid }); // replace other kind
    await post("/api/disrupt", { id: rid, kind });
  }
  const s = await fetchJSON("/api/sim/state");
  applyState(s);
  if (!runningPhase()) await planAndPreview();  // live re-plan around the change
}

/* ------------------------------------------------------------------ */
/* route + van drawing                                                 */
/* ------------------------------------------------------------------ */
function polyline(pts, cls) {
  return svg("polyline", { points: pts.map((p) => p.join(",")).join(" "), class: cls });
}
function drawRoute() {
  layers.route.innerHTML = "";
  if (plan && plan.path) {
    layers.route.appendChild(polyline(plan.path.map((p) => [p.x, p.y]), "route-preview"));
  }
  if (!state || state.phase === "idle") return;
  for (const hist of state.history_paths || []) {
    layers.route.appendChild(polyline(hist, "route-ghost"));
  }
  if ((state.remaining_path || []).length > 1) {
    layers.route.appendChild(polyline(state.remaining_path, "route-live-wrap"));
    layers.route.appendChild(polyline(state.remaining_path, "route-live"));
  }
}
function drawVan(pos) {
  if (!pos) { layers.van.style.display = "none"; return; }
  layers.van.style.display = "";
  layers.van.setAttribute("transform", `translate(${pos[0]},${pos[1]})`);
}
function paintStops() {
  // dim any store that is NOT scheduled on the current route/plan, so a van that
  // merely drives through a shop's intersection is not mistaken for a visit.
  const live = state && (state.phase === "running" || state.phase === "paused");
  const scheduled = new Set();
  if (live) {
    (state.delivered || []).forEach((d) => scheduled.add(d.stop));
    (state.etas || []).forEach((et) => scheduled.add(et.stop));
  } else if (plan && plan.stops) {
    plan.stops.forEach((s) => scheduled.add(s.id));
  }
  const done = new Set((state && state.delivered || []).map((x) => x.stop));
  D.stops.forEach((st) => {
    st._circle.classList.remove("done", "next");
    st._grp.style.opacity = scheduled.has(st.id) ? "" : "0.32";
    if (done.has(st.id)) st._circle.classList.add("done");
  });
  if (live) {
    const nxt = state.etas && state.etas[0];
    const c = nxt && D.stopById[nxt.stop];
    if (c) c._circle.classList.add("next");
  }
}

/* ------------------------------------------------------------------ */
/* catalog (items)                                                     */
/* ------------------------------------------------------------------ */
function buildCatalog() {
  const list = $("item-list");
  list.innerHTML = "";
  const byStop = new Map(D.stops.map((st) => [st.id, []]));
  D.items.forEach((it) => byStop.get(it.to).push(it));
  for (const st of D.stops) {
    list.appendChild(el("div", { class: "stop-group" }, [
      el("div", { class: "grp-head" }, [
        el("span", { class: `tier p${st.priority}` }, PRIO[st.priority]),
        document.createTextNode(st.name),
      ]),
      ...byStop.get(st.id).map(catalogRow),
    ]));
  }
}
function catalogRow(it) {
  const row = el("label", { class: "item-row" });
  const cb = el("input", { type: "checkbox", checked: "" });
  cb.dataset.id = it.id;
  row.append(cb, el("div", { class: "nm" }, it.name),
    el("div", { class: "meta" },
      `${it.weight}kg · ${it.value}v · P${it.priority}`));
  row._cb = cb;
  cb.addEventListener("change", () => {
    if (cb.checked) params.excluded.delete(it.id);
    else params.excluded.add(it.id);
    schedulePlan();
  });
  return row;
}
function applyItemStatus() {
  const chosen = new Set((plan ? plan.load.chosen : []).map((x) => x.id));
  document.querySelectorAll("#item-list .item-row").forEach((row) => {
    const id = row._cb.dataset.id;
    row.classList.remove("chosen", "skipped", "excluded");
    row.title = params.excluded.has(id) ? "excluded from the knapsack"
      : chosen.has(id) ? "loaded by 0/1 knapsack"
      : "not loaded — no room at this capacity/premium";
    row.classList.add(params.excluded.has(id) ? "excluded"
      : chosen.has(id) ? "chosen" : "skipped");
  });
}

/* ------------------------------------------------------------------ */
/* params + plan preview                                               */
/* ------------------------------------------------------------------ */
function readParams() {
  params.capacity = +$("cap").value;
  params.premium = +$("prem").value;
  params.strictness = +$("strict").value;
  params.scope = currentScope();
  return { ...params, excluded: [...params.excluded] };
}
function currentScope() {
  const on = document.querySelector("#scope button.on");
  return on ? on.dataset.scope : "loaded";
}
function syncControls() {
  $("cap").value = params.capacity; $("cap-val").textContent = params.capacity;
  $("prem").value = params.premium; $("prem-val").textContent = params.premium;
  $("strict").value = params.strictness;
  $("strict-val").textContent = params.strictness.toFixed(1);
  document.querySelectorAll("#scope button").forEach((b) =>
    b.classList.toggle("on", b.dataset.scope === params.scope));
}
function setBusy(busy) {
  ["cap", "prem", "strict", "btn-plan"].forEach((id) => { $(id).disabled = busy; });
  document.querySelectorAll("#item-list input, #scope button").forEach((n) => {
    n.disabled = busy;
  });
  $("btn-start").disabled = busy || !plan;
}
let planDebounce = null;
function schedulePlan() {
  if (runningPhase()) return;               // planning locks while a run is live
  clearTimeout(planDebounce);
  planDebounce = setTimeout(planAndPreview, 160);
}
async function planAndPreview() {
  if (runningPhase()) return;
  let p;
  try {
    p = await fetchJSON("/api/plan", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(readParams()) });
  } catch (e) { console.error("plan failed", e); return; }
  plan = p;
  renderPlan();
  if (!runningPhase()) { drawRoute(); renderRouteOrder(); paintStops(); }
}
function renderPlan() {
  const L = plan.load;
  $("load-fill").style.width = Math.min(100, L.fill_pct) + "%";
  $("s-fill").textContent = L.fill_pct + "%";
  $("s-weight").textContent = `${L.total_weight} / ${L.capacity} kg`;
  $("s-value").textContent = L.total_value;
  const w = $("load-warns");
  w.hidden = !plan.warnings.length;
  w.textContent = plan.warnings.join(" ");
  applyItemStatus();
  setBusy(false);
  paintDisruptions(state ? state.disruptions : []);
}

/* ------------------------------------------------------------------ */
/* route order + KPI + status bar                                      */
/* ------------------------------------------------------------------ */
function seqRow(pos, name, prio, when, extra, cls) {
  const row = el("div", { class: `seqrow ${cls || ""}` });
  row.appendChild(el("span", { class: `pos p${prio}` }, String(pos)));
  row.appendChild(el("span", { class: "nm" }, name));
  if (when) row.appendChild(el("span", { class: "eta" }, when));
  if (extra) row.appendChild(el("span", { class: "eta" }, extra));
  return row;
}
function renderRouteOrder() {
  const box = $("route-order");
  box.innerHTML = "";
  const ph = state && state.phase;
  const live = ph === "running" || ph === "paused";
  const done = ph === "done";

  if (live) {
    // actual live sequence: delivered (with arrival times) then remaining ETAs
    let n = 0;
    (state.delivered || []).forEach((d) => {
      n++;
      const late = d.late > 0 ? `⚠ ${d.late.toFixed(1)} late` : "";
      box.appendChild(seqRow(n, d.name, d.priority, fmtMin(d.arrived), late,
        "delivered" + (d.late > 0 ? " late" : "")));
    });
    (state.etas || []).forEach((et, i) => {
      n++;
      box.appendChild(seqRow(n, et.name, et.priority, "ETA " + fmtMin(et.eta_min), "",
        i === 0 ? "next" : ""));
    });
    $("st-target").textContent = state.etas && state.etas.length
      ? "→ " + state.etas[0].name : "heading home → DEPOT";
    return;
  }

  // not live: always show the current plan's order (preview) as soon as it exists
  if (plan && plan.stops && plan.stops.length) {
    const recap = done && planMatchesRun();      // finished run, plan unchanged
    const delivered = recap
      ? new Map((state.delivered || []).map((d) => [d.stop, d]))
      : null;
    plan.stops.forEach((st, i) => {
      let when = null, extra = "", cls = "";
      if (st.items) extra = st.items === 1 ? "1 item" : st.items + " items";
      if (recap && delivered.has(st.id)) {
        const d = delivered.get(st.id);
        when = fmtMin(d.arrived);
        extra = d.late > 0 ? `⚠ ${d.late.toFixed(1)} late` : "✓ delivered";
        cls = "delivered" + (d.late > 0 ? " late" : "");
      }
      box.appendChild(seqRow(i + 1, st.name, st.priority, when, extra, cls));
    });
    $("st-target").textContent = "preview — dispatch to run";
    return;
  }

  if (done) {                                   // finished auto-demo, no preview kept
    (state.delivered || []).forEach((d, i) => {
      box.appendChild(seqRow(i + 1, d.name, d.priority, fmtMin(d.arrived),
        d.late > 0 ? `⚠ ${d.late.toFixed(1)} late` : "", "delivered" +
        (d.late > 0 ? " late" : "")));
    });
    $("st-target").textContent = "run complete — back at DEPOT";
    return;
  }
  box.appendChild(el("div", { class: "empty" }, "Plan a load to see the stop order."));
}

function planMatchesRun() {
  const dlv = ((state && state.delivered) || []).map((d) => d.stop);
  const ps = ((plan && plan.stops) || []).map((s) => s.id);
  return ps.length > 0 && dlv.length === ps.length &&
    dlv.every((id, i) => id === ps[i]);
}
function renderKpis() {
  if (!state) return;
  const done = (state.delivered || []).length;
  $("clock-pill").textContent = fmtMin(state.clock);
  $("st-delivered").textContent = done;
  $("st-remaining").textContent = state.phase === "done" ? 0
    : Math.max(0, state.route_stop_total - done);
  $("st-reroutes").textContent = state.stats.reroutes;
  $("st-eta").textContent = (state.phase === "done")
    ? fmtMin(state.clock)
    : (state.etas && state.etas[0] ? "ETA " + fmtMin(state.etas[0].eta_min) : "–");
  const ph = state.phase || "idle";
  const pill = $("phase-pill");
  pill.textContent = ph === "running" ? "● running"
    : ph === "paused" ? "‖ paused"
    : ph === "done" ? "■ done" : "idle";
  pill.className = "pill " + ph;
  syncRunButtons();
  if (ph === "done") $("st-target").textContent = "run complete — back at DEPOT";
}
function syncRunButtons() {
  const ph = state ? state.phase : "idle";
  const live = ph === "running" || ph === "paused";
  const pb = $("btn-playpause");
  pb.disabled = !live;
  pb.textContent = ph === "paused" ? "▶ Resume" : "⏸ Pause";
}

/* ------------------------------------------------------------------ */
/* event log                                                           */
/* ------------------------------------------------------------------ */
function pushEvent(time, msg, kind = "info") {
  if (kind === "info") return;   // service / pause chatter — not shown in the log
  const box = $("event-log");
  box.prepend(el("div", { class: `ev ${kind}` },
    [el("span", { class: "t" }, time), el("span", { class: "m" }, msg)]));
  while (box.children.length > 120) box.removeChild(box.lastChild);
}
function ingestEvents(events) {
  for (const e of events || []) {
    if (e.id > lastEvt) { pushEvent(fmtMin(e.clock), e.message, e.kind); lastEvt = e.id; }
  }
}

/* ------------------------------------------------------------------ */
/* live simulation                                                     */
/* ------------------------------------------------------------------ */
function setPolling(on) {
  if (on && !pollTimer) pollTimer = setInterval(refreshState, 450);
  else if (!on && pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}
async function refreshState() {
  try {
    const s = await fetchJSON("/api/sim/state");
    applyState(s);
  } catch (e) { /* transient — keep polling */ }
}
function applyState(s) {
  state = s;
  ingestEvents(s.events);
  renderKpis();
  paintDisruptions(s.disruptions);
  drawRoute();
  drawVan(s.pos);
  paintStops();
  renderRouteOrder();
  setBusy(runningPhase());
  if (s.phase === "running") setPolling(true);
  else setPolling(false);
}

async function dispatch() {
  if (runningPhase()) return;
  $("event-log").innerHTML = "";   // start this run's log clean
  lastEvt = 0;
  const res = await fetchJSON("/api/sim/start", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...readParams(), autoplay: true,
      timescale: +$("speed").value }) });
  applyState(res.sim);
  pushEvent("00:00",
    `Dispatched — ${res.plan.k} stops · ${res.plan.method} · travel ${res.plan.travel} min`,
    "plan");
}

async function resetRun() {
  const s = await fetchJSON("/api/reset", { method: "POST" });
  lastEvt = 0;
  plan = null;                    // clear preview; re-plan right after
  applyState(s);
  await planAndPreview();         // fresh preview with current sliders, no disruptions
}

async function postControl(action, timescale) {
  if (!state || state.phase === "idle") return;
  const body = { action };
  if (timescale) body.timescale = timescale;
  const s = await fetchJSON("/api/sim/control", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  applyState(s);
}
/* ------------------------------------------------------------------ */
/* buttons                                                             */
/* ------------------------------------------------------------------ */
function wireEvents() {
  ["cap", "prem", "strict"].forEach((id) => {
    $(id).addEventListener("input", () => {
      $("cap-val").textContent = $("cap").value;
      $("prem-val").textContent = $("prem").value;
      $("strict-val").textContent = (+$("strict").value).toFixed(1);
      schedulePlan();
    });
  });
  document.querySelectorAll("#scope button").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll("#scope button").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      schedulePlan();
    });
  });
  $("btn-plan").addEventListener("click", planAndPreview);
  $("btn-start").addEventListener("click", dispatch);
  $("btn-reset").addEventListener("click", resetRun);
  $("btn-demo").addEventListener("click", autoDemo);

  $("btn-playpause").addEventListener("click", () => {
    if (!state || state.phase === "idle" || state.phase === "done") return;
    postControl(state.phase === "running" ? "pause" : "play");
  });
  $("speed").addEventListener("input", () => {
    $("speed-val").textContent = $("speed").value + "×";
    if (state && (state.phase === "running" || state.phase === "paused"))
      postControl(state.phase === "running" ? "play" : "pause", +$("speed").value);
  });

  mapPanel.addEventListener("mousemove", moveTip);
  window.addEventListener("keydown", (e) => { if (e.key === "Escape") tipBox.style.display = "none"; });
}

async function autoDemo() {
  const res = await fetchJSON("/api/demo/scenario", { method: "POST" });
  if (!res.ok) { pushEvent(fmtMin(0), res.error, "warn"); return; }
  lastEvt = 0; $("event-log").innerHTML = "";
  state = res.sim;
  plan = null;                                  // draw live path, not a preview
  pushEvent("00:00", `Auto-demo armed — ${res.roadblock.name} will close at ` +
    fmtMin(res.roadblock.at) + ".", "disruption");
  applyState(res.sim);
  postControl("play", +$("speed").value);
}

/* ------------------------------------------------------------------ */
/* start                                                               */
/* ------------------------------------------------------------------ */
document.addEventListener("DOMContentLoaded", init);
