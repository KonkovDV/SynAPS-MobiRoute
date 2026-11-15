// Mixed fleet, live dispatch replay and the benchmark heat strip.
// Data comes from site/data/*.json, written by benchmark/export_vrp_site_data.py.

const CLASS_ORDER = ["van_1.5t", "truck_5t", "truck_10t", "tractor_20t"];
const CLASS_NAME = {
  "van_1.5t": ["Фургон 1,5 т", "Van 1.5 t"],
  truck_5t: ["Грузовик 5 т", "Truck 5 t"],
  truck_10t: ["Грузовик 10 т", "Truck 10 t"],
  tractor_20t: ["Тягач 20 т", "Tractor 20 t"],
};
const PLANT_NAME = [["тягач", "tow tractor"], ["бортовой с краном", "flatbed + crane"], ["крытый фургон", "covered van"]];
const FAMILY = [
  ["solomon", "Solomon · VRPTW", "56"],
  ["lilim", "Li & Lim · PDPTW", "1"],
  ["sartori-buriol", "Sartori–Buriol · PDPTW, OSRM", "25"],
  ["cordeau", "Cordeau · DARP", "48"],
];

export function initVrp(ctx) {
  const { load, near, $ } = ctx;
  near($("fleet"), () => load("data/fleet-mix.json").then((d) => fleet(ctx, d)).catch((e) => console.error(e)));
  near($("dispatch"), () => Promise.all([load("data/dispatch.json"), load("data/comparisons.json")])
    .then(([d, c]) => dispatch(ctx, d, c))
    .catch((e) => console.error(e)));
  near($("bench"), () => Promise.all([load("data/benchmarks.json"), load("data/comparisons.json")])
    .then(([b, c]) => bench(ctx, b, c))
    .catch((e) => console.error(e)));
}

const fmtInt = (v) => Math.round(v).toLocaleString("ru-RU").replace(/,/g, " ");
const hhmm = (t) => {
  const m = Math.max(0, Math.round(t));
  return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`;
};

/* ---------- mixed fleet ---------- */
function fleet({ $, tr, svgEl, reduce, rerender }, data) {
  const svg = $("fleet-map");
  const input = $("fleet-n");
  const pad = 30;
  const xs = data.nodes.map((n) => n.x);
  const ys = data.nodes.map((n) => n.y);
  const lo = Math.min(...xs, ...ys);
  const span = Math.max(Math.max(...xs) - lo, Math.max(...ys) - lo) || 1;
  const px = (n) => pad + ((data.nodes[n].x - lo) / span) * (600 - 2 * pad);
  const py = (n) => 600 - pad - ((data.nodes[n].y - lo) / span) * (600 - 2 * pad);
  const clsIndex = (t) => CLASS_ORDER.indexOf(data.types[t].cls);
  const grid = svgEl("g", { stroke: "var(--grid)", "stroke-width": 1 }, svg);
  for (let k = 0; k <= 6; k++) {
    const v = pad + (k / 6) * (600 - 2 * pad);
    svgEl("line", { x1: v, y1: pad, x2: v, y2: 600 - pad }, grid);
    svgEl("line", { x1: pad, y1: v, x2: 600 - pad, y2: v }, grid);
  }
  const base = svgEl("g", {}, svg);
  const layer = svgEl("g", {}, svg);
  const top = svgEl("g", {}, svg);
  const last = data.days[data.days.length - 1];
  const used = new Set(last.routes.flatMap((r) => r.nodes));
  for (const n of used) svgEl("circle", { cx: px(n), cy: py(n), r: 2.2, fill: "var(--muted)", opacity: 0.25 }, base);
  for (const d of data.depots) {
    svgEl("rect", { x: px(d) - 8, y: py(d) - 8, width: 16, height: 16, rx: 4, fill: "var(--ink)" }, top);
    const t = svgEl("text", { x: px(d) + 12, y: py(d) + 4, "font-size": 13, "font-weight": 700, fill: "var(--ink)" }, top);
    t.textContent = data.nodes[d].name;
  }
  const depotOf = (t) => data.types[t].depot;

  function draw(k, animate) {
    const day = data.days[k];
    $("fleet-n-val").textContent = String(day.orders);
    layer.textContent = "";
    const pickups = new Set(day.transfers.map((p) => p[0]));
    day.routes.forEach((route, r) => {
      const ci = clsIndex(route.type);
      const depot = depotOf(route.type);
      const seq = [depot, ...route.nodes, depot];
      const d = seq.map((n, i) => `${i ? "L" : "M"}${px(n).toFixed(1)} ${py(n).toFixed(1)}`).join(" ");
      const path = svgEl("path", {
        d,
        fill: "none",
        stroke: `var(--c${ci})`,
        "stroke-width": 2.2,
        "stroke-linejoin": "round",
        opacity: 0.9,
        "stroke-dasharray": data.types[route.type].hired ? "6 5" : "none",
      }, layer);
      if (animate && !reduce.matches && !data.types[route.type].hired) {
        const len = path.getTotalLength();
        path.style.strokeDasharray = `${len}`;
        path.style.strokeDashoffset = `${len}`;
        path.animate([{ strokeDashoffset: len }, { strokeDashoffset: 0 }], { duration: 900 + 25 * r, easing: "cubic-bezier(.2,.8,.2,1)", fill: "forwards" });
      }
      for (const n of route.nodes) {
        const pick = pickups.has(n);
        svgEl("circle", { cx: px(n), cy: py(n), r: 3.6, fill: pick ? "var(--card-on-bg)" : `var(--c${ci})`, stroke: `var(--c${ci})`, "stroke-width": pick ? 2 : 0 }, layer);
      }
    });
    const rub = tr("₽", "RUB");
    $("fleet-kpis").innerHTML = [
      [tr("обслужено", "served"), `${day.served} / ${day.orders}`],
      [tr("машин в работе", "vehicles out"), String(day.vehicles)],
      [tr("стоимость дня", "day cost"), `${fmtInt(day.cost)} ${rub}`],
      [tr("пробег", "distance"), `${fmtInt(day.distance)} ${tr("км", "km")}`],
    ].map(([a, b]) => `<div><dt>${a}</dt><dd>${b}</dd></div>`).join("");
    const mix = $("fleet-mix");
    mix.textContent = "";
    CLASS_ORDER.forEach((cls, ci) => {
      const own = data.types.find((t) => t.cls === cls && !t.hired);
      const hired = data.types.find((t) => t.cls === cls && t.hired);
      const usedOwn = day.byType[own.id] || 0;
      const usedHired = day.byType[hired.id] || 0;
      const row = document.createElement("div");
      row.className = "mix-row";
      row.style.setProperty("--c", `var(--c${ci})`);
      const cells = [];
      for (let u = 0; u < own.units; u++) cells.push(`<span class="own${u < usedOwn ? "" : " idle"}"></span>`);
      for (let u = 0; u < hired.units; u++) cells.push(`<span class="hired${u < usedHired ? "" : " idle"}"></span>`);
      row.innerHTML = `<span class="cls"><i></i>${tr(...CLASS_NAME[cls])}</span><div class="mix-cells">${cells.join("")}</div><span class="n">${usedOwn}+${usedHired}</span>`;
      row.title = tr(`своих ${usedOwn} из ${own.units}, наёмных ${usedHired} из ${hired.units}`, `own ${usedOwn} of ${own.units}, hired ${usedHired} of ${hired.units}`);
      mix.appendChild(row);
    });
  }
  input.addEventListener("input", () => draw(Number(input.value), true));
  rerender.push(() => draw(Number(input.value), false));
  draw(Number(input.value), false);
}

/* ---------- live dispatch replay ---------- */
function reasonText(tr, why) {
  const late = /reaches the pickup ([\d.]+) min after/.exec(why);
  if (late) return tr(`ближайшая свободная машина опоздает на ${late[1]} мин`, `nearest free vehicle would be ${late[1]} min late`);
  if (why.startsWith("no vehicle type")) return tr("ни один тип машины не берёт этот груз", "no vehicle type can carry it");
  if (why.includes("driver's break")) return tr("кто успевает — заняты, связаны обещаниями или водителю негде сделать перерыв", "those in time are full, bound by promises or have no place left for a break");
  if (why.startsWith("every vehicle")) return tr("кто успевает — заняты или нарушили бы обещания", "those in time are full or bound by promises");
  return why;
}

// Vehicle track: depart just in time for the first stop, rest where the plan
// says. A break in gap g comes before plan[g] (g = length: before the return):
// at the previous stop when it starts as that service ends, else on arrival.
function buildTrack(data, p) {
  const n = p.nodes.length;
  const stopAt = (g) => (g === 0 || g > n ? data.depot : p.nodes[g - 1]);
  const goTo = (g) => (g >= n ? data.depot : p.nodes[g]);
  const rests = (p.rests || []).map(([gap, start, minutes, final]) => ({ gap, from: start, to: start + minutes, minutes, final }));
  const restIn = new Map(rests.map((r) => [r.gap, r]));
  const events = [];
  for (let g = 0; g <= n; g++) {
    const from = stopAt(g);
    const to = goTo(g);
    const leg = p.legs[g];
    const r = restIn.get(g);
    let leave;
    if (g === 0) leave = r ? r.from - leg : p.starts[0] - leg;
    else {
      leave = p.starts[g - 1] + p.service[g - 1];
      if (r && Math.abs(r.from - leave) < 0.05) leave = r.to;
    }
    if (g === 0) events.push({ t: leave, from, to: from });
    events.push({ t: leave, from, to, arrive: leave + leg });
  }
  return { events, rests };
}

function dispatch(ctx, plain, comparisons) {
  const { $, tr, svgEl, reduce, rerender, load } = ctx;
  const svg = $("disp-map");
  const pad = 28;
  const ground = svgEl("g", {}, svg);
  const trails = svgEl("g", {}, svg);
  const marks = svgEl("g", {}, svg);
  const cars = svgEl("g", {}, svg);
  const feed = $("disp-feed");
  const restCell = $("disp-rest-cell");
  const live = new Map(); // request id -> {pickup mark, delivery mark}
  const scenarios = { plain };
  let mode = "plain";
  let data;
  let X;
  let Y;
  let tracks = [];
  let decisions = [];
  let byId = new Map();
  let plannedPickup = new Map();
  let deliveredAt = new Map();
  let events = [];
  let t0 = 0;
  let t1 = 0;
  let shown = 0;

  function setData(d) {
    data = d;
    const xs = d.nodes.map((nd) => nd.x);
    const ys = d.nodes.map((nd) => nd.y);
    const lo = Math.min(...xs, ...ys);
    const span = Math.max(Math.max(...xs) - lo, Math.max(...ys) - lo) || 1;
    X = (k) => pad + ((d.nodes[k].x - lo) / span) * (600 - 2 * pad);
    Y = (k) => 600 - pad - ((d.nodes[k].y - lo) / span) * (600 - 2 * pad);
    for (const layer of [ground, trails, marks, cars]) layer.textContent = "";
    live.clear();
    const sites = new Map();
    d.nodes.forEach((nd, k) => { if (k !== d.depot && !sites.has(nd.name)) sites.set(nd.name, k); });
    for (const [, k] of sites) svgEl("rect", { x: X(k) - 5, y: Y(k) - 5, width: 10, height: 10, rx: 2, fill: "none", stroke: "var(--grid)", "stroke-width": 1.5 }, ground);
    svgEl("rect", { x: X(d.depot) - 8, y: Y(d.depot) - 8, width: 16, height: 16, rx: 4, fill: "var(--ink)" }, ground);
    tracks = d.plans.map((p) => {
      const color = `var(--c${[0, 2, 3][p.type] ?? 0})`;
      const halo = svgEl("circle", { r: 13, fill: "none", stroke: "var(--rest)", "stroke-width": 3, opacity: 0 }, cars);
      const dot = svgEl("circle", { r: 7, fill: color, stroke: "#000", "stroke-width": 2 }, cars);
      return { p, color, dot, halo, ...buildTrack(d, p) };
    });
    byId = new Map(d.requests.map((r) => [r.id, r]));
    decisions = [...d.decisions].sort((a, b) => a.t - b.t);
    plannedPickup = new Map();
    deliveredAt = new Map();
    d.plans.forEach((p, v) => p.nodes.forEach((nd, i) => {
      plannedPickup.set(nd, { t: p.starts[i], v });
      deliveredAt.set(nd, p.starts[i] + p.service[i]);
    }));
    const restEvents = tracks.flatMap((tk) => tk.rests.map((r) => ({ t: r.from, rest: r, type: tk.p.type })));
    events = [...decisions.map((x) => ({ t: x.t, d: x })), ...restEvents].sort((a, b) => a.t - b.t);
    t0 = Math.min(...decisions.map((x) => x.t)) - 10;
    t1 = Math.max(...d.plans.map((p) => p.starts[p.starts.length - 1])) + 20;
    restCell.hidden = !tracks.some((tk) => tk.rests.length);
    restCell.parentElement.classList.toggle("five", !restCell.hidden);
  }

  const position = (track, t) => {
    let pos = [X(data.depot), Y(data.depot)];
    for (const ev of track.events) {
      if (t < ev.t) break;
      if (ev.arrive == null || t >= ev.arrive) { pos = [X(ev.to), Y(ev.to)]; continue; }
      const f = (t - ev.t) / Math.max(1e-6, ev.arrive - ev.t);
      pos = [X(ev.from) + (X(ev.to) - X(ev.from)) * f, Y(ev.from) + (Y(ev.to) - Y(ev.from)) * f];
    }
    return pos;
  };

  function pushFeed(ev) {
    const li = document.createElement("li");
    let text;
    let right;
    if (ev.rest) {
      const r = ev.rest;
      li.className = "rest";
      const part = r.final ? (r.minutes < 45 ? tr(", вторая часть", ", second part") : "") : tr(", первая часть", ", first part");
      text = tr(`${PLANT_NAME[ev.type][0]}: перерыв водителя${part}`, `${PLANT_NAME[ev.type][1]}: driver's break${part}`);
      right = `${r.minutes} ${tr("мин", "min")}`;
    } else {
      const d = ev.d;
      li.className = d.ok ? "" : "no";
      const req = byId.get(d.id);
      if (d.ok) {
        const type = d.vt ?? data.plans[d.veh]?.type ?? 0;
        const wait = Math.round(d.pick - d.t);
        text = tr(`${d.id} · ${req.pallets} пал. → ${PLANT_NAME[type][0]} · подача через ${wait} мин`, `${d.id} · ${req.pallets} pal. → ${PLANT_NAME[type][1]} · pickup in ${wait} min`);
      } else {
        text = `${d.id} ✕ ${reasonText(tr, d.why)}`;
      }
      right = `${d.ms.toFixed(2)} ${tr("мс", "ms")}`;
    }
    li.innerHTML = `<time>${hhmm(ev.t)}</time><span></span><span class="ms"></span>`;
    li.children[1].textContent = text;
    li.children[2].textContent = right;
    feed.prepend(li);
    while (feed.children.length > 9) feed.lastElementChild.remove();
  }

  function paint(t, animateFeed) {
    let begun = 0;
    for (const tk of tracks) {
      const [x, y] = position(tk, t);
      tk.dot.setAttribute("cx", x);
      tk.dot.setAttribute("cy", y);
      const now = tk.rests.some((r) => t >= r.from && t < r.to);
      tk.halo.setAttribute("cx", x);
      tk.halo.setAttribute("cy", y);
      tk.halo.setAttribute("opacity", now ? 1 : 0);
      begun += tk.rests.filter((r) => r.final && t >= r.from).length;
    }
    let acc = 0;
    let dec = 0;
    let resp = 0;
    let ms = 0;
    for (const d of decisions) {
      if (d.t > t) break;
      dec++;
      ms += d.ms;
      if (d.ok) { acc++; resp += d.pick - d.t; }
    }
    if (animateFeed) {
      while (shown < events.length && events[shown].t <= t) pushFeed(events[shown++]);
    }
    for (const d of decisions) {
      const req = byId.get(d.id);
      let m = live.get(d.id);
      const visible = d.t <= t && (d.ok ? t <= (deliveredAt.get(req.d) ?? d.t) : t <= d.t + 25);
      if (!visible) { if (m) { m.g.remove(); live.delete(d.id); } continue; }
      if (!m) {
        const g = svgEl("g", {}, marks);
        const color = d.ok ? (tracks[d.veh]?.color ?? "var(--ink2)") : "var(--bad)";
        const pk = svgEl("circle", { cx: X(req.p), cy: Y(req.p), r: 5, fill: color }, g);
        const line = svgEl("line", { x1: X(req.p), y1: Y(req.p), x2: X(req.d), y2: Y(req.d), stroke: color, "stroke-width": 1.2, "stroke-dasharray": "3 4", opacity: 0.55 }, g);
        const q = svgEl("circle", { cx: X(req.d), cy: Y(req.d), r: 4.5, fill: "none", stroke: color, "stroke-width": 2 }, g);
        if (!d.ok) { line.remove(); q.remove(); }
        if (!reduce.matches && animateFeed) {
          const ring = svgEl("circle", { cx: X(req.p), cy: Y(req.p), r: 6, fill: "none", stroke: color, "stroke-width": 2 }, trails);
          ring.animate([{ r: 6, opacity: 0.9 }, { r: 30, opacity: 0 }], { duration: 900, easing: "ease-out" }).onfinish = () => ring.remove();
        }
        m = { g, p: pk, line };
        live.set(d.id, m);
      }
      if (d.ok) {
        const picked = t >= (plannedPickup.get(req.p)?.t ?? Infinity);
        m.p.setAttribute("opacity", picked ? 0.25 : 1);
      }
    }
    $("disp-clock").textContent = hhmm(t);
    $("disp-acc").textContent = `${acc} / ${dec}`;
    $("disp-resp").textContent = acc ? `${(resp / acc).toFixed(1)} ${tr("мин", "min")}` : "—";
    $("disp-ms").textContent = dec ? `${(ms / dec).toFixed(2)} ${tr("мс", "ms")}` : "—";
    $("disp-rest").textContent = String(begun);
  }

  let speed = 1;
  const DAY_MS = 60000;
  let playing = !reduce.matches;
  let visible = false;
  let simT = 0;
  let lastNow = performance.now();
  const reset = () => { simT = t0; shown = 0; feed.textContent = ""; for (const m of live.values()) m.g.remove(); live.clear(); };
  const still = () => { feed.textContent = ""; events.slice(-9).forEach(pushFeed); shown = events.length; paint(t1, false); };
  const frame = (now) => {
    const dt = now - lastNow;
    lastNow = now;
    if (playing && visible && !document.hidden) {
      simT += (dt / DAY_MS) * (t1 - t0) * speed;
      if (simT > t1 + 30) reset();
      paint(Math.min(simT, t1), true);
    }
    if (playing) requestAnimationFrame(frame);
  };
  const btn = $("disp-play");
  const sync = () => btn.setAttribute("aria-pressed", String(playing));
  btn.addEventListener("click", () => {
    playing = !playing;
    sync();
    if (playing) { lastNow = performance.now(); requestAnimationFrame(frame); }
  });
  document.querySelectorAll("#dispatch .speeds button").forEach((b) => b.addEventListener("click", () => {
    speed = Number(b.dataset.speed);
    document.querySelectorAll("#dispatch .speeds button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  }));
  new IntersectionObserver(([e]) => { visible = e.isIntersecting; }, { threshold: 0.1 }).observe(svg);

  const table = document.querySelector("#disp-policies tbody");
  const names = {
    insertion: ["вставка", "insertion"],
    "insertion+alns": ["вставка + ALNS раз в 30 мин", "insertion + ALNS every 30 min"],
    "ortools-resolve": ["OR-Tools заново на каждую заявку", "OR-Tools re-solve per order"],
  };
  const fill = () => {
    table.textContent = "";
    const ruled = `${plain.name}-breaks`;
    const rows = (comparisons?.realtime?.rows || []).filter((r) => r.day === plain.name || r.day === ruled);
    for (const r of rows) {
      const tr_ = table.insertRow();
      tr_.innerHTML = "<th scope='row'></th><td></td><td></td><td></td>";
      const label = tr(...(names[r.policy] || [r.policy, r.policy]));
      tr_.cells[0].textContent = r.day === ruled ? `${label}${tr(", приказ № 160", ", Order No. 160")}` : label;
      tr_.cells[1].textContent = `${(100 * r.acceptance_rate).toFixed(1)}%`;
      tr_.cells[2].textContent = `${r.response_mean_min.toFixed(1)} ${tr("мин", "min")}`;
      tr_.cells[3].textContent = r.decision_ms_mean >= 100 ? `${(r.decision_ms_mean / 1000).toFixed(1)} ${tr("с", "s")}` : `${r.decision_ms_mean.toFixed(2)} ${tr("мс", "ms")}`;
      const current = r.day === data.name && r.policy === data.policy;
      tr_.classList.toggle("on", current);
      if (current) tr_.setAttribute("aria-current", "true");
    }
  };

  const empty = () => {
    const k = data.kpi || {};
    if (k.empty_km == null || !k.distance) return;
    const beta = (100 * (1 - k.empty_km / k.distance)).toFixed(0);
    const nobody = k.uncarriable ? tr(` ${k.uncarriable} заявок не берёт ни один тип машины: из остальных принято ${(100 * k.acceptance_of_carriable).toFixed(1)}%.`, ` No vehicle type can carry ${k.uncarriable} of the orders; of the rest ${(100 * k.acceptance_of_carriable).toFixed(1)}% are accepted.`) : "";
    const breaks = k.breaks ? tr(` Перерывов водителей: ${k.breaks}, каждый маршрут проверен по правилу.`, ` Drivers' breaks: ${k.breaks}, every route checked against the rule.`) : "";
    $("disp-empty").textContent = tr(
      `За смену: ${Math.round(k.distance)} км, из них порожних ${Math.round(k.empty_km)} (коэффициент использования пробега ${beta}%).`,
      `The shift: ${Math.round(k.distance)} km, ${Math.round(k.empty_km)} of them empty (mileage utilisation ${beta}%).`,
    ) + nobody + breaks;
  };

  const show = (next) => {
    mode = next;
    setData(scenarios[next]);
    document.querySelectorAll("#disp-mode button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mode === next)));
    $("disp-legend-rest").hidden = next !== "rests";
    reset();
    if (playing) paint(simT, true);
    else still();
    fill();
    empty();
  };
  document.querySelectorAll("#disp-mode button").forEach((b) => b.addEventListener("click", () => {
    const next = b.dataset.mode;
    if (next === mode) return;
    if (scenarios[next]) { show(next); return; }
    b.setAttribute("aria-busy", "true");
    load("data/dispatch-rests.json").then((d) => { scenarios[next] = d; show(next); })
      .catch((e) => console.error(e))
      .finally(() => b.removeAttribute("aria-busy"));
  }));

  setData(plain);
  simT = t0;
  sync();
  if (playing) requestAnimationFrame(frame);
  else still();
  fill();
  rerender.push(fill);
  empty();
  rerender.push(empty);
}

/* ---------- benchmarks ---------- */
function heatColor(r) {
  if (!(r.feasible && r.complete)) return "var(--bad)";
  if (r.vehicle_delta > 0) return "color-mix(in srgb, var(--c4) 75%, transparent)";
  if (r.vehicle_delta < 0) return "var(--good)";
  const g = r.gap_pct ?? 0;
  if (g <= 0.01) return "var(--good)";
  if (g <= 1) return "color-mix(in srgb, var(--good) 55%, transparent)";
  if (g <= 3) return "color-mix(in srgb, var(--c2) 75%, transparent)";
  return "color-mix(in srgb, var(--c3) 85%, transparent)";
}

function bench({ $, tr, rerender, onReveal }, data, comparisons) {
  const host = $("heat");
  const render = () => {
    host.textContent = "";
    const tip = document.createElement("p");
    tip.className = "heat-tip";
    tip.setAttribute("aria-live", "polite");
    tip.textContent = tr("Наведите на клетку, чтобы увидеть инстанс.", "Hover a cell to see the instance.");
    for (const [key, label] of FAMILY) {
      const rows = data.rows.filter((r) => r.family === key);
      if (!rows.length) continue;
      const s = data.summary[key];
      const line = document.createElement("div");
      line.className = "heat-row";
      const fleetNote = s.at_reference_fleet == null ? "" : tr(`${s.at_reference_fleet}/${s.instances} при том же числе машин · `, `${s.at_reference_fleet}/${s.instances} at the reference fleet · `);
      const gapNote = s.median_gap_pct == null ? "" : tr(`медиана ${s.median_gap_pct.toFixed(2)}%`, `median ${s.median_gap_pct.toFixed(2)}%`);
      line.innerHTML = `<h4>${label}<small>${fleetNote}${gapNote}</small></h4><div class="cells"></div>`;
      const cells = line.querySelector(".cells");
      for (const r of rows) {
        const b = document.createElement("button");
        b.type = "button";
        b.style.setProperty("--h", heatColor(r));
        const ref = r.ref_vehicles == null ? "" : tr(` (лучшее известное ${r.ref_vehicles})`, ` (best known ${r.ref_vehicles})`);
        const gap = r.vehicle_delta > 0 ? tr(`на ${r.vehicle_delta} машину больше`, `${r.vehicle_delta} more vehicle`) : r.gap_pct == null ? "—" : `${r.gap_pct.toFixed(2)}%`;
        const text = `<b>${r.instance}</b> · ${r.requests} ${tr("заказов", "orders")} · ${tr("машин", "vehicles")} ${r.vehicles}${ref} · ${r.cost.toFixed(2)} ${tr("против", "vs")} ${r.ref_cost.toFixed(2)} · ${tr("разрыв", "gap")} ${gap} · ${r.seconds.toFixed(1)} ${tr("с", "s")}`;
        b.setAttribute("aria-label", text.replace(/<[^>]+>/g, ""));
        const show = () => { tip.innerHTML = text; };
        b.addEventListener("mouseenter", show);
        b.addEventListener("focus", show);
        b.addEventListener("click", show);
        cells.appendChild(b);
      }
      host.appendChild(line);
    }
    const key = document.createElement("div");
    key.className = "heat-key";
    const entries = [
      ["var(--good)", tr("лучшее известное или лучше", "best known or better")],
      ["color-mix(in srgb, var(--good) 55%, transparent)", "≤ 1%"],
      ["color-mix(in srgb, var(--c2) 75%, transparent)", "1–3%"],
      ["color-mix(in srgb, var(--c3) 85%, transparent)", "> 3%"],
      ["color-mix(in srgb, var(--c4) 75%, transparent)", tr("+1 машина", "+1 vehicle")],
    ];
    key.innerHTML = entries.map(([c, l]) => `<span><i style="--h:${c}"></i>${l}</span>`).join("");
    host.appendChild(key);
    host.appendChild(tip);
  };
  render();
  rerender.push(render);

  const exact = comparisons?.exact?.summary;
  const exactText = () => {
    if (!exact) return;
    $("exact-stat").innerHTML = `${exact.alns_matches_optimum}<small>/${exact.proven_optimal}</small>`;
    $("exact-text").textContent = tr(
      `Случайные задачи с полным набором ограничений — несколько типов машин, вектор ёмкости, навыки, лимит поездки, смены, необязательные заказы. CP-SAT доказывает оптимум (в среднем ${exact.mean_exact_seconds} с), ALNS находит его за ${exact.mean_alns_seconds} с.`,
      `Random instances with every constraint: several vehicle types, capacity vector, skills, ride limits, shifts, optional orders. CP-SAT proves the optimum (${exact.mean_exact_seconds} s on average); ALNS finds it in ${exact.mean_alns_seconds} s.`,
    );
    const stat = document.getElementById("stat-exact");
    if (stat) { stat.dataset.count = String(exact.alns_matches_optimum); stat.dataset.suf = `/${exact.proven_optimal}`; stat.textContent = `${exact.alns_matches_optimum}/${exact.proven_optimal}`; }
  };
  exactText();
  rerender.push(exactText);

  const bars = (hostId, rows, a, b, labelFn, valueFn) => {
    const el = $(hostId);
    el.textContent = "";
    const fills = [];
    for (const r of rows) {
      const va = valueFn(r, a);
      const vb = valueFn(r, b);
      const top = Math.max(va, vb) || 1;
      const row = document.createElement("div");
      row.className = "vs-row";
      row.innerHTML = `<span class="lbl"></span><div class="tracks"><div class="track"><div class="fill a"></div></div><div class="track"><div class="fill b"></div></div></div>`;
      row.querySelector(".lbl").textContent = labelFn(r);
      row.title = `${labelFn(r)}: ${va.toFixed(2)} / ${vb.toFixed(2)}`;
      el.appendChild(row);
      const [fa, fb] = row.querySelectorAll(".fill");
      fills.push([fa, (100 * va) / top], [fb, (100 * vb) / top]);
    }
    const go = () => fills.forEach(([f, w]) => { f.style.width = `${Math.max(1, w)}%`; });
    onReveal.set(el.closest(".reveal"), go);
    if (el.closest(".reveal")?.classList.contains("in")) requestAnimationFrame(go);
  };

  const ort = comparisons?.ortools?.rows || [];
  const pairs = [];
  for (const r of ort) {
    if (r.solver.startsWith("ALNS")) {
      const o = ort.find((x) => x.instance === r.instance && x.solver.startsWith("OR-Tools"));
      if (o) pairs.push({ name: r.instance, alns: r, ort: o });
    }
  }
  const pick = pairs.filter((p) => /R101|RC201|bar-n100-1|ber-n100-1|a4-24|cargo-day|plant/.test(p.name)).slice(0, 7);
  const ortRender = () => bars(
    "ortools-vs",
    pick,
    "alns",
    "ort",
    (p) => p.name.replace("cargo-day-", "cargo ").replace("plant-", "plant "),
    (p, side) => (p.name.startsWith("cargo") || p.name.startsWith("plant") ? p[side].cost : p[side].distance),
  );
  ortRender();
  rerender.push(ortRender);

  const speed = comparisons?.speed?.rows || [];
  const speedRender = () => bars(
    "speed-vs",
    speed,
    "native_ms_per_iteration",
    "python_ms_per_iteration",
    (r) => `${r.case.split(",")[0]} ×${r.speedup}`,
    (r, side) => r[side],
  );
  speedRender();
  rerender.push(speedRender);
  if (speed.length) {
    const best = Math.max(...speed.map((r) => r.speedup));
    const stat = document.getElementById("stat-speed");
    if (stat) { stat.dataset.count = String(Math.round(best)); stat.textContent = `×${Math.round(best)}`; }
  }
}
