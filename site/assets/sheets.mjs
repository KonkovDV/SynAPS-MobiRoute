// Route sheets of a synthetic day in Naberezhnye Chelny: the map, a Gantt chart of
// every vehicle, the sheet of the selected one, and the departure slider behind
// Lemma 4 (the latest departure that still returns earliest is a shortest shift).
// Data: site/data/route-sheets.json, written by benchmark/export_vrp_site_data.py.

const PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#c98500", "#e87ba4", "#008300", "#6250d6"];
const KIND = {
  depart: ["загрузка и выезд", "loading, departure"],
  pickup: ["погрузка", "pickup"],
  delivery: ["выгрузка", "delivery"],
  reload: ["загрузка на складе", "reload"],
  rest: ["перерыв", "break"],
  rest_first: ["перерыв, 1-я часть", "break, first part"],
  return: ["возврат", "return"],
};
const EPS = 1e-6;
// Exported minutes are rounded to 0.01: windows are compared with that slack.
const TOL = 0.02;

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const hhmm = (t) => {
  const m = Math.round(t);
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
};
export function initSheets(ctx) {
  ctx.load("data/route-sheets.json").then((d) => sheets(ctx, d)).catch((e) => console.error(e));
}

/** Earliest schedule of a route when it leaves at ``d`` (no traffic, no ride limits). */
export function forward(L, d) {
  const n = L.e.length;
  const B = [d];
  const A = [d];
  for (let i = 1; i < n; i++) {
    const a = B[i - 1] + L.svc[i - 1] + L.tt[i - 1] + (i - 1 === L.gap ? L.rest : 0);
    A.push(a);
    B.push(Math.max(L.e[i], a));
  }
  let late = null;
  for (let i = 0; i < n; i++) {
    const hi = L.l[i];
    if (hi !== null && B[i] > hi + TOL && (!late || B[i] - hi > late.by)) late = { i, by: B[i] - hi };
  }
  const duration = B[n - 1] - d;
  const wait = B.reduce((s, b, i) => s + (i ? b - A[i] : 0), 0);
  const over = L.cap !== null && duration > L.cap + TOL ? duration - L.cap : 0;
  return { B, A, late, duration, wait, over };
}

function sheets({ $, tr, lang, svgEl, reduce, rerender }, data) {
  const vehicles = data.vehicles;
  const num = (v, digits = 0) =>
    v.toLocaleString(lang() === "en" ? "en-US" : "ru-RU", { maximumFractionDigits: digits }).replace(/\u00a0/g, " ");
  const color = (i) => PALETTE[i % PALETTE.length];
  const dur = (m) => {
    const v = Math.round(m);
    const h = Math.floor(v / 60);
    return h ? `${h} ${tr("ч", "h")} ${String(v % 60).padStart(2, "0")} ${tr("мин", "min")}` : `${v} ${tr("мин", "min")}`;
  };
  let sel = 0;

  /* ---------- map ---------- */
  const map = $("sheets-map");
  const pts = vehicles.flatMap((v) => v.rows.map((r) => [r.lat, r.lon]));
  const lat0 = pts.reduce((s, p) => s + p[0], 0) / pts.length;
  const k = Math.cos((lat0 * Math.PI) / 180);
  const xs = pts.map((p) => p[1] * k);
  const ys = pts.map((p) => p[0]);
  const x0 = Math.min(...xs);
  const y0 = Math.min(...ys);
  const xSpan = Math.max(...xs) - x0;
  const ySpan = Math.max(...ys) - y0;
  const span = Math.max(xSpan, ySpan) || 1;
  const W = 600;
  const pad = 30;
  // Equal scale on both axes, the shorter one centred.
  const px = (lon) => pad + ((lon * k - x0 + (span - xSpan) / 2) / span) * (W - 2 * pad);
  const py = (lat) => W - pad - ((lat - y0 + (span - ySpan) / 2) / span) * (W - 2 * pad);
  const grid = svgEl("g", { stroke: "var(--grid)", "stroke-width": 1 }, map);
  for (let g = 0; g <= 6; g++) {
    const v = pad + (g / 6) * (W - 2 * pad);
    svgEl("line", { x1: v, y1: pad, x2: v, y2: W - pad }, grid);
    svgEl("line", { x1: pad, y1: v, x2: W - pad, y2: v }, grid);
  }
  const routeLayer = svgEl("g", {}, map);
  const top = svgEl("g", {}, map);
  const routes = vehicles.map((v, i) => {
    const g = svgEl("g", { class: "sheet-route", tabindex: 0, role: "button" }, routeLayer);
    const stops = v.rows.filter((r) => r.k !== "rest");
    const d = stops.map((r, j) => `${j ? "L" : "M"}${px(r.lon).toFixed(1)} ${py(r.lat).toFixed(1)}`).join(" ");
    const title = svgEl("title", {}, g);
    const path = svgEl("path", { d, fill: "none", stroke: color(i), "stroke-width": 2.4, "stroke-linejoin": "round", "stroke-dasharray": v.hired ? "7 5" : "none" }, g);
    for (const r of stops) {
      if (r.k !== "pickup" && r.k !== "delivery") continue;
      svgEl("circle", { cx: px(r.lon), cy: py(r.lat), r: 4, fill: r.k === "pickup" ? color(i) : "var(--card-on-bg)", stroke: color(i), "stroke-width": 2 }, g);
    }
    g.addEventListener("click", () => select(i));
    g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(i); } });
    return { g, path, title };
  });
  for (const s of data.suppliers) {
    const x = px(s.lon);
    const y = py(s.lat);
    const dm = svgEl("path", { d: `M${x} ${y - 8}L${x + 8} ${y}L${x} ${y + 8}L${x - 8} ${y}Z`, fill: "var(--ink)", opacity: 0.85 }, top);
    svgEl("title", {}, dm).textContent = s.label;
  }
  const dep = data.depot;
  svgEl("rect", { x: px(dep.lon) - 9, y: py(dep.lat) - 9, width: 18, height: 18, rx: 4, fill: "var(--ink)" }, top);
  const depLabel = svgEl("text", { x: px(dep.lon) + 14, y: py(dep.lat) + 5, "font-size": 14, "font-weight": 700, fill: "var(--ink)" }, top);
  depLabel.textContent = dep.label;

  /* ---------- Gantt chart ---------- */
  const gantt = $("sheets-gantt");
  const t0 = Math.floor(Math.min(...vehicles.map((v) => v.rows[0].s)) / 60) * 60;
  const t1 = Math.ceil(Math.max(...vehicles.map((v) => v.rows[v.rows.length - 1].s)) / 60) * 60;
  const GW = 960;
  const left = 132;
  const rowH = 34;
  const gTop = 12;
  const GH = gTop + rowH * vehicles.length + 30;
  gantt.setAttribute("viewBox", `0 0 ${GW} ${GH}`);
  const gx = (t) => left + ((t - t0) / Math.max(t1 - t0, 1)) * (GW - left - 16);
  const hours = svgEl("g", {}, gantt);
  for (let t = t0; t <= t1; t += 60) {
    svgEl("line", { x1: gx(t), y1: gTop - 4, x2: gx(t), y2: GH - 26, stroke: "var(--grid)", "stroke-width": 1 }, hours);
    const lbl = svgEl("text", { x: gx(t), y: GH - 8, "font-size": 12, "text-anchor": "middle", fill: "var(--muted)" }, hours);
    lbl.textContent = hhmm(t);
  }
  const rows = vehicles.map((v, i) => {
    const y = gTop + i * rowH + rowH / 2;
    const g = svgEl("g", { class: "gantt-row", tabindex: 0, role: "button" }, gantt);
    svgEl("rect", { class: "bg", x: 0, y: y - rowH / 2, width: GW, height: rowH, rx: 8 }, g);
    const name = svgEl("text", { x: 12, y: y - 1, "font-size": 13, "font-weight": 700, fill: "var(--ink)" }, g);
    name.textContent = v.id;
    const sub = svgEl("text", { class: "g-sub", x: 12, y: y + 13, "font-size": 11, fill: "var(--muted)" }, g);
    const bars = svgEl("g", {}, g);
    g.addEventListener("click", () => select(i));
    g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(i); } });
    return { g, y, sub, bars };
  });

  function drawBars() {
    vehicles.forEach((v, i) => {
      const { y, sub, bars } = rows[i];
      bars.textContent = "";
      sub.textContent = `${v.hired ? tr("наёмная", "hired") : tr("своя", "own")} · ${tripsText(v.trips)}`;
      let prev = v.rows[0];
      for (const r of v.rows.slice(1)) {
        if (r.a > prev.e + EPS) {
          svgEl("line", { x1: gx(prev.e), y1: y, x2: gx(r.a), y2: y, stroke: "var(--muted)", "stroke-width": 2.5, "stroke-linecap": "round" }, bars);
        }
        if (r.s > r.a + 0.5) {
          svgEl("rect", { x: gx(r.a), y: y - 8, width: gx(r.s) - gx(r.a), height: 16, rx: 3, fill: "var(--muted)", opacity: 0.18 }, bars);
        }
        if (r.e > r.s + EPS) {
          const fill = r.k === "rest" || r.k === "rest_first" ? "#eda100" : r.k === "reload" ? "var(--ink2)" : color(i);
          const bar = svgEl("rect", { x: gx(r.s), y: y - 8, width: Math.max(gx(r.e) - gx(r.s), 2), height: 16, rx: 3, fill, opacity: r.k === "pickup" ? 0.55 : 1 }, bars);
          svgEl("title", {}, bar).textContent = `${tr(...KIND[r.k])} ${r.o} · ${r.p} · ${hhmm(r.s)}–${hhmm(r.e)}`;
        }
        prev = r;
      }
    });
  }

  /* ---------- the selected vehicle's sheet ---------- */
  const tripsText = (n) => {
    if (lang() === "en") return `${n} trip${n > 1 ? "s" : ""}`;
    const m10 = n % 10;
    const m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return `${n} рейс`;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return `${n} рейса`;
    return `${n} рейсов`;
  };
  function sheet() {
    const v = vehicles[sel];
    const first = v.rows[0];
    const last = v.rows[v.rows.length - 1];
    $("sheets-title").textContent = v.id;
    $("sheet-name").textContent = v.id;
    loadChart(v);
    $("sheets-tag").textContent = `${v.hired ? tr("наёмная", "hired") : tr("своя", "own")} · ${tripsText(v.trips)}`;
    $("sheets-tag").style.color = color(sel);
    $("sheets-kpis").innerHTML = [
      [tr("начало → выезд → возврат", "start → out → back"), `${hhmm(first.s)} → ${hhmm(first.e)} → ${hhmm(last.s)}`],
      [tr("пробег", "distance"), `${num(v.distance, 1)} ${tr("км", "km")}`],
      [tr("за рулём / ожидание", "driving / waiting"), `${Math.round(v.driving)} / ${Math.round(v.waiting)} ${tr("мин", "min")}`],
      [tr("стоимость", "cost"), `${num(v.cost)} ${data.currency}`],
    ].map(([a, b]) => `<div><dt>${a}</dt><dd>${b}</dd></div>`).join("");
    const [d0, d2] = [data.dimensions[0], data.dimensions[2] ?? data.dimensions[0]];
    const head = [tr("Рейс", "Trip"), tr("Что", "What"), tr("Заказ", "Order"), tr("Где", "Where"), tr("Окно", "Window"), tr("Прибытие", "Arrive"), tr("Начало", "Start"), tr("Конец", "End"), d0, d2];
    const table = $("sheets-table");
    table.tHead.innerHTML = `<tr>${head.map((h) => `<th scope="col">${h}</th>`).join("")}</tr>`;
    table.tBodies[0].innerHTML = v.rows.map((r) => {
      const w = r.w ? `${r.w[0] ? hhmm(r.w[0]) : ""}–${r.w[1] !== null ? hhmm(r.w[1]) : ""}` : "";
      const waits = r.s > r.a + 0.5 ? ` class="waits" title="${tr("ожидание", "waiting")} ${Math.round(r.s - r.a)} ${tr("мин", "min")}"` : "";
      const q2 = r.q[2] ?? r.q[0];
      return `<tr class="k-${r.k}"><td>${r.t}</td><td class="txt">${tr(...KIND[r.k])}</td><td class="txt">${esc(r.o)}</td><td class="txt">${esc(r.p)}</td><td>${w}</td><td>${hhmm(r.a)}</td><td${waits}>${hhmm(r.s)}</td><td>${hhmm(r.e)}</td><td>${num(r.q[0], 1)}</td><td>${num(q2, 2)}</td></tr>`;
    }).join("");
    routes.forEach((r, i) => {
      const on = i === sel;
      r.g.style.opacity = on ? 1 : 0.2;
      r.path.setAttribute("stroke-width", on ? 3.6 : 2.4);
      r.title.textContent = `${vehicles[i].id} · ${tripsText(vehicles[i].trips)}`;
      r.g.setAttribute("aria-pressed", String(on));
      r.g.setAttribute("aria-label", `${vehicles[i].id}`);
      if (on) routeLayer.appendChild(r.g);
    });
    rows.forEach((r, i) => {
      r.g.classList.toggle("on", i === sel);
      r.g.setAttribute("aria-pressed", String(i === sel));
    });
  }

  /* ---------- load on board along the route ---------- */
  function loadChart(v) {
    const svg = $("sheets-load");
    svg.textContent = "";
    const LW = 520;
    const LH = 200;
    const l0 = 52;
    const r0 = 12;
    const t0c = 22;
    const b0 = 26;
    const stops = v.rows.filter((r) => r.k !== "rest");
    const cap = v.capacity[0];
    const top = Math.max(cap, ...stops.map((r) => r.q[0])) * 1.1 || 1;
    const lx = (j) => l0 + (j / Math.max(stops.length - 1, 1)) * (LW - l0 - r0);
    const ly = (q) => LH - b0 - (q / top) * (LH - t0c - b0);
    for (const f of [0, 0.5, 1]) {
      svgEl("line", { x1: l0, y1: ly(cap * f), x2: LW - r0, y2: ly(cap * f), stroke: "var(--grid)" }, svg);
      const t = svgEl("text", { x: l0 - 6, y: ly(cap * f) + 4, "font-size": 11, "text-anchor": "end", fill: "var(--muted)" }, svg);
      t.textContent = num(cap * f);
    }
    svgEl("line", { x1: l0, y1: ly(cap), x2: LW - r0, y2: ly(cap), stroke: "var(--bad)", "stroke-dasharray": "5 4" }, svg);
    const capLabel = svgEl("text", { x: LW - r0, y: ly(cap) - 6, "font-size": 11.5, "text-anchor": "end", fill: "var(--bad)" }, svg);
    capLabel.textContent = tr(`ёмкость ${num(cap)} ${data.dimensions[0]}`, `capacity ${num(cap)} ${data.dimensions[0]}`);
    const head = svgEl("text", { x: l0, y: 13, "font-size": 12, "font-weight": 700, fill: "var(--ink2)" }, svg);
    head.textContent = tr(`На борту, ${data.dimensions[0]}`, `On board, ${data.dimensions[0]}`);
    let d = "";
    stops.forEach((r, j) => {
      const q = r.q[0];
      d += j ? `H${lx(j).toFixed(1)}V${ly(q).toFixed(1)}` : `M${lx(0).toFixed(1)} ${ly(q).toFixed(1)}`;
    });
    const area = `${d}V${ly(0).toFixed(1)}H${lx(0).toFixed(1)}Z`;
    svgEl("path", { d: area, fill: color(sel), opacity: 0.12 }, svg);
    svgEl("path", { d, fill: "none", stroke: color(sel), "stroke-width": 2.5, "stroke-linejoin": "round" }, svg);
    stops.forEach((r, j) => {
      if (r.k === "reload") {
        svgEl("line", { x1: lx(j), y1: t0c, x2: lx(j), y2: ly(0), stroke: "var(--ink2)", "stroke-dasharray": "3 3" }, svg);
        const t = svgEl("text", { x: lx(j) + 4, y: t0c + 10, "font-size": 11, fill: "var(--ink2)" }, svg);
        t.textContent = tr(`рейс ${r.t}`, `trip ${r.t}`);
      }
      const dot = svgEl("circle", { cx: lx(j), cy: ly(r.q[0]), r: 3.5, fill: r.k === "pickup" ? color(sel) : "var(--card-on-bg)", stroke: color(sel), "stroke-width": 2 }, svg);
      svgEl("title", {}, dot).textContent = `${tr(...KIND[r.k])} ${r.o} · ${num(r.q[0], 1)} ${data.dimensions[0]}`;
    });
  }

  /* ---------- Lemma 4: when to leave ---------- */
  const slider = $("dep");
  const curve = $("dep-curve");
  const CW = 600;
  const CH = 400;
  const cl = 64;
  const cr = 20;
  const ct = 34;
  const cb = 44;

  function lemma(reset) {
    const v = vehicles[sel];
    const L = v.lemma;
    const lo = L.lo;
    const hi = Math.min(L.hi + 45, lo + 13 * 60);
    if (reset) {
      slider.min = String(Math.floor(lo));
      slider.max = String(Math.ceil(hi));
      slider.value = String(Math.round(L.best));
    }
    const d = Number(slider.value);
    const now = forward(L, d);
    const base = forward(L, lo);
    $("dep-val").textContent = hhmm(d);
    // The curve: shift length D(t0) = max(E - t0, c) while every window holds.
    curve.textContent = "";
    const samples = [];
    for (let t = Math.floor(lo); t <= hi; t += 1) samples.push([t, forward(L, t)]);
    // Zoom on the interesting band: from just below c to the longest shift.
    const dmin = Math.max(0, Math.floor((L.c - 40) / 30) * 30);
    const dmax = Math.ceil((Math.max(...samples.map(([, s]) => s.duration), L.c) + 20) / 30) * 30;
    const cx = (t) => cl + ((t - lo) / Math.max(hi - lo, 1)) * (CW - cl - cr);
    const cy = (m) => CH - cb - ((m - dmin) / Math.max(dmax - dmin, 1)) * (CH - ct - cb);
    for (let m = Math.ceil(dmin / 60) * 60; m <= dmax; m += 60) {
      svgEl("line", { x1: cl, y1: cy(m), x2: CW - cr, y2: cy(m), stroke: "var(--grid)" }, curve);
      const lbl = svgEl("text", { x: cl - 8, y: cy(m) + 4, "font-size": 11, "text-anchor": "end", fill: "var(--muted)" }, curve);
      lbl.textContent = `${m / 60} ${tr("ч", "h")}`;
    }
    for (let t = Math.ceil(lo / 60) * 60; t <= hi; t += 60) {
      const lbl = svgEl("text", { x: cx(t), y: CH - cb + 20, "font-size": 11.5, "text-anchor": "middle", fill: "var(--muted)" }, curve);
      lbl.textContent = hhmm(t);
    }
    const yTitle = svgEl("text", { x: cl, y: 16, "font-size": 12, "font-weight": 700, fill: "var(--ink2)" }, curve);
    yTitle.textContent = tr("длительность смены D(t₀)", "shift length D(t₀)");
    const xTitle = svgEl("text", { x: CW - cr, y: CH - 6, "font-size": 12, "font-weight": 700, "text-anchor": "end", fill: "var(--ink2)" }, curve);
    xTitle.textContent = tr("начало смены t₀", "shift start t₀");
    const ok = samples.filter(([, s]) => !s.late && !s.over);
    const bad = samples.filter(([t]) => t >= L.hi);
    const line = (list) => list.map(([t, s], j) => `${j ? "L" : "M"}${cx(t).toFixed(1)} ${cy(s.duration).toFixed(1)}`).join(" ");
    svgEl("rect", { x: cx(L.hi), y: ct, width: Math.max(cx(hi) - cx(L.hi), 0), height: CH - ct - cb, fill: "var(--bad)", opacity: 0.08 }, curve);
    svgEl("line", { x1: cl, y1: cy(L.c), x2: CW - cr, y2: cy(L.c), stroke: "var(--muted)", "stroke-dasharray": "4 4" }, curve);
    const cLabel = svgEl("text", { x: CW - cr - 4, y: cy(L.c) - 8, "font-size": 12, "text-anchor": "end", fill: "var(--muted)" }, curve);
    cLabel.textContent = tr(`c = ${dur(L.c)} — кратчайшая смена`, `c = ${dur(L.c)}, the shortest shift`);
    if (bad.length > 1) svgEl("path", { d: line(bad), fill: "none", stroke: "var(--bad)", "stroke-width": 2, "stroke-dasharray": "5 4" }, curve);
    svgEl("path", { d: line(ok), fill: "none", stroke: color(sel), "stroke-width": 3, "stroke-linejoin": "round" }, curve);
    svgEl("circle", { cx: cx(L.best), cy: cy(L.c), r: 6, fill: "var(--card-on-bg)", stroke: color(sel), "stroke-width": 3 }, curve);
    const starX = Math.min(Math.max(cx(L.best), cl + 80), CW - cr - 80);
    const star = svgEl("text", { x: starX, y: cy(L.c) + 26, "font-size": 12.5, "font-weight": 700, "text-anchor": "middle", fill: "var(--ink)" }, curve);
    star.textContent = `t₀* = E − c = ${hhmm(L.best)}`;
    const cur = svgEl("circle", { cx: cx(d), cy: cy(now.duration), r: 7, fill: now.late || now.over ? "var(--bad)" : color(sel) }, curve);
    if (!reduce.matches) cur.animate([{ r: 11, opacity: 0.6 }, { r: 7, opacity: 1 }], { duration: 300 });
    const saved = base.duration - L.c;
    let text;
    if (now.late) {
      const name = esc(L.names[now.late.i]);
      text = tr(
        `<b class="bad">Нельзя.</b> Начало смены в ${hhmm(d)}: «${name}» — работа начнётся позже окна на ${Math.ceil(now.late.by)} мин. Начать позже ${hhmm(L.hi)} нельзя: это самое позднее расписание.`,
        `<b class="bad">Infeasible.</b> Starting at ${hhmm(d)}: work at "${name}" begins ${Math.ceil(now.late.by)} min after its window. ${hhmm(L.hi)} is the latest start: the latest schedule.`,
      );
    } else {
      const back = now.B[now.B.length - 1];
      text = tr(
        `Начало ${hhmm(d)}, выезд ${hhmm(d + L.svc[0])}, возврат ${hhmm(back)}: смена <b>${dur(now.duration)}</b>, из них ожидание ${dur(now.wait)}.`,
        `Start ${hhmm(d)}, out ${hhmm(d + L.svc[0])}, back ${hhmm(back)}: a <b>${dur(now.duration)}</b> shift, ${dur(now.wait)} of it waiting.`,
      );
      if (Math.abs(d - L.best) < 0.5) text += tr(" Это начало по лемме 4: смена кратчайшая, возврат самый ранний.", " This is the Lemma 4 start: the shortest shift and the earliest return.");
    }
    text += tr(
      ` <span class="fine">Если начинать сразу в ${hhmm(lo)} — те же точки и тот же возврат, но смена ${dur(base.duration)}: на ${dur(saved)} дольше.</span>`,
      ` <span class="fine">Starting as soon as possible (${hhmm(lo)}): the same stops and the same return, but a ${dur(base.duration)} shift, ${dur(saved)} longer.</span>`,
    );
    $("dep-text").innerHTML = text;
  }

  function totals() {
    let saved = 0;
    for (const v of vehicles) saved += forward(v.lemma, v.lemma.lo).duration - v.lemma.c;
    $("sheets-saved").textContent = `${num(saved / 60, 1)} ${tr("ч", "h")}`;
    $("sheets-day").textContent = tr(
      `${vehicles.length} машин · ${data.orders} заказов · ${num(data.distance, 0)} км · ${num(data.cost)} ${data.currency}`,
      `${vehicles.length} vehicles · ${data.orders} orders · ${num(data.distance, 0)} km · ${num(data.cost)} ${data.currency}`,
    );
  }

  function select(i) {
    sel = i;
    sheet();
    lemma(true);
  }

  slider.addEventListener("input", () => lemma(false));
  rerender.push(() => { drawBars(); sheet(); lemma(false); totals(); });
  drawBars();
  totals();
  select(0);
}
