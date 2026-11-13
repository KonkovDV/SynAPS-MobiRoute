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
  const { load } = ctx;
  load("data/fleet-mix.json").then((d) => fleet(ctx, d)).catch((e) => console.error(e));
  load("data/dispatch.json").then((d) => load("data/comparisons.json").then((c) => dispatch(ctx, d, c))).catch((e) => console.error(e));
  Promise.all([load("data/benchmarks.json"), load("data/comparisons.json")])
    .then(([b, c]) => bench(ctx, b, c))
    .catch((e) => console.error(e));
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
  if (why.startsWith("no vehicle type")) return tr("нет подходящего типа машины", "no suitable vehicle type");
  if (why.startsWith("every vehicle")) return tr("кто успевает — заняты или нарушили бы обещания", "those in time are full or bound by promises");
  return why;
}

function dispatch({ $, tr, svgEl, reduce, rerender }, data, comparisons) {
  const svg = $("disp-map");
  const pad = 28;
  const xs = data.nodes.map((n) => n.x);
  const ys = data.nodes.map((n) => n.y);
  const lo = Math.min(...xs, ...ys);
  const span = Math.max(Math.max(...xs) - lo, Math.max(...ys) - lo) || 1;
  const X = (n) => pad + ((data.nodes[n].x - lo) / span) * (600 - 2 * pad);
  const Y = (n) => 600 - pad - ((data.nodes[n].y - lo) / span) * (600 - 2 * pad);
  const sites = new Map();
  data.nodes.forEach((nd, k) => {
    if (k === data.depot) return;
    const key = nd.name;
    if (!sites.has(key)) sites.set(key, k);
  });
  const ground = svgEl("g", {}, svg);
  for (const [, k] of sites) svgEl("rect", { x: X(k) - 5, y: Y(k) - 5, width: 10, height: 10, rx: 2, fill: "none", stroke: "var(--grid)", "stroke-width": 1.5 }, ground);
  svgEl("rect", { x: X(data.depot) - 8, y: Y(data.depot) - 8, width: 16, height: 16, rx: 4, fill: "var(--ink)" }, ground);
  const trails = svgEl("g", {}, svg);
  const marks = svgEl("g", {}, svg);
  const cars = svgEl("g", {}, svg);

  // Vehicle tracks: depart the depot just in time for the first stop.
  const tracks = data.plans.map((p) => {
    const events = [];
    let at = data.depot;
    let clock = p.starts[0] - p.legs[0];
    events.push({ t: clock, from: at, to: at });
    p.nodes.forEach((n, i) => {
      events.push({ t: clock, from: at, to: n, arrive: clock + p.legs[i] });
      clock = p.starts[i] + p.service[i];
      at = n;
    });
    events.push({ t: clock, from: at, to: data.depot, arrive: clock + p.legs[p.legs.length - 1] });
    const color = `var(--c${[0, 2, 3][p.type] ?? 0})`;
    const dot = svgEl("circle", { r: 7, fill: color, stroke: "#000", "stroke-width": 2 }, cars);
    return { p, events, color, dot };
  });
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
  const byId = new Map(data.requests.map((r) => [r.id, r]));
  const decisions = [...data.decisions].sort((a, b) => a.t - b.t);
  const plannedPickup = new Map();
  const deliveredAt = new Map();
  data.plans.forEach((p, v) => p.nodes.forEach((n, i) => {
    plannedPickup.set(n, { t: p.starts[i], v });
    deliveredAt.set(n, p.starts[i] + p.service[i]);
  }));
  const t0 = Math.min(...decisions.map((d) => d.t)) - 10;
  const t1 = Math.max(...data.plans.map((p) => p.starts[p.starts.length - 1])) + 20;

  const feed = $("disp-feed");
  let shown = 0;
  function pushFeed(d) {
    const li = document.createElement("li");
    li.className = d.ok ? "" : "no";
    const req = byId.get(d.id);
    let text;
    if (d.ok) {
      const type = data.plans[d.veh]?.type ?? 0;
      const wait = Math.round(d.pick - d.t);
      text = tr(`${d.id} · ${req.pallets} пал. → ${PLANT_NAME[type][0]} · подача через ${wait} мин`, `${d.id} · ${req.pallets} pal. → ${PLANT_NAME[type][1]} · pickup in ${wait} min`);
    } else {
      text = `${d.id} ✕ ${reasonText(tr, d.why)}`;
    }
    li.innerHTML = `<time>${hhmm(d.t)}</time><span></span><span class="ms">${d.ms.toFixed(2)} ${tr("мс", "ms")}</span>`;
    li.children[1].textContent = text;
    feed.prepend(li);
    while (feed.children.length > 9) feed.lastElementChild.remove();
  }

  const live = new Map(); // request id -> {pickup mark, delivery mark}
  function paint(t, animateFeed) {
    for (const tr_ of tracks) {
      const [x, y] = position(tr_, t);
      tr_.dot.setAttribute("cx", x);
      tr_.dot.setAttribute("cy", y);
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
      while (shown < decisions.length && decisions[shown].t <= t) pushFeed(decisions[shown++]);
    }
    for (const d of decisions) {
      const req = byId.get(d.id);
      let m = live.get(d.id);
      const visible = d.t <= t && (d.ok ? t <= (deliveredAt.get(req.d) ?? d.t) : t <= d.t + 25);
      if (!visible) { if (m) { m.g.remove(); live.delete(d.id); } continue; }
      if (!m) {
        const g = svgEl("g", {}, marks);
        const color = d.ok ? tracks[d.veh].color : "var(--bad)";
        const p = svgEl("circle", { cx: X(req.p), cy: Y(req.p), r: 5, fill: color }, g);
        const line = svgEl("line", { x1: X(req.p), y1: Y(req.p), x2: X(req.d), y2: Y(req.d), stroke: color, "stroke-width": 1.2, "stroke-dasharray": "3 4", opacity: 0.55 }, g);
        const q = svgEl("circle", { cx: X(req.d), cy: Y(req.d), r: 4.5, fill: "none", stroke: color, "stroke-width": 2 }, g);
        if (!d.ok) { line.remove(); q.remove(); }
        if (!reduce.matches && animateFeed) {
          const ring = svgEl("circle", { cx: X(req.p), cy: Y(req.p), r: 6, fill: "none", stroke: color, "stroke-width": 2 }, trails);
          ring.animate([{ r: 6, opacity: 0.9 }, { r: 30, opacity: 0 }], { duration: 900, easing: "ease-out" }).onfinish = () => ring.remove();
        }
        m = { g, p, line };
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
  }

  let speed = 1;
  const DAY_MS = 60000;
  let playing = !reduce.matches;
  let visible = false;
  let simT = t0;
  let lastNow = performance.now();
  const reset = () => { simT = t0; shown = 0; feed.textContent = ""; for (const m of live.values()) m.g.remove(); live.clear(); };
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
  sync();
  if (playing) requestAnimationFrame(frame);
  else { decisions.slice(-9).forEach(pushFeed); shown = decisions.length; paint(t1, false); }

  const table = document.querySelector("#disp-policies tbody");
  const names = {
    insertion: ["вставка", "insertion"],
    "insertion+alns": ["вставка + ALNS раз в 30 мин", "insertion + ALNS every 30 min"],
    "ortools-resolve": ["OR-Tools заново на каждую заявку", "OR-Tools re-solve per order"],
  };
  const fill = () => {
    table.textContent = "";
    const rows = (comparisons?.realtime?.rows || []).filter((r) => r.day === data.name);
    for (const r of rows) {
      const tr_ = table.insertRow();
      tr_.innerHTML = "<th scope='row'></th><td></td><td></td><td></td>";
      tr_.cells[0].textContent = tr(...(names[r.policy] || [r.policy, r.policy]));
      tr_.cells[1].textContent = `${(100 * r.acceptance_rate).toFixed(1)}%`;
      tr_.cells[2].textContent = `${r.response_mean_min.toFixed(1)} ${tr("мин", "min")}`;
      tr_.cells[3].textContent = r.decision_ms_mean >= 100 ? `${(r.decision_ms_mean / 1000).toFixed(1)} ${tr("с", "s")}` : `${r.decision_ms_mean.toFixed(2)} ${tr("мс", "ms")}`;
    }
  };
  fill();
  rerender.push(fill);
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
