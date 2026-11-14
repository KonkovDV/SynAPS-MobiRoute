// Prices of the Naberezhnye Chelny day: what each order costs (LP duals over the
// ALNS route pool, next to the saving if the order is simply dropped) and what
// one more own vehicle is worth (the LP rent next to the day solved again with
// one more unit). Data: site/data/prices.json, written by
// benchmark/export_vrp_site_data.py from the same plan as the route sheets.

const PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#c98500", "#e87ba4", "#008300", "#6250d6"];
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

export function initPrices(ctx) {
  ctx.load("data/prices.json").then((d) => prices(ctx, d)).catch((e) => console.error(e));
}

function prices({ $, tr, lang, svgEl, rerender }, data) {
  const orders = data.orders;
  const num = (v, digits = 0) =>
    v.toLocaleString(lang() === "en" ? "en-US" : "ru-RU", { maximumFractionDigits: digits }).replace(/ /g, " ");
  const money = (v) => `${num(v)} ${data.currency}`;
  const color = (i) => PALETTE[i % PALETTE.length];
  const top = Math.max(...orders.map((o) => o.price), 1);
  const ranked = orders.map((o, i) => i).sort((a, b) => orders[b].price - orders[a].price);
  let sel = ranked[0];

  /* ---------- map: one circle per order, area proportional to its price ---------- */
  const map = $("prices-map");
  const pts = [...orders.map((o) => [o.lat, o.lon]), [data.depot.lat, data.depot.lon]];
  const k = Math.cos((pts.reduce((s, p) => s + p[0], 0) / pts.length) * (Math.PI / 180));
  const xs = pts.map((p) => p[1] * k);
  const ys = pts.map((p) => p[0]);
  const x0 = Math.min(...xs);
  const y0 = Math.min(...ys);
  const xSpan = Math.max(...xs) - x0;
  const ySpan = Math.max(...ys) - y0;
  const span = Math.max(xSpan, ySpan) || 1;
  const W = 600;
  const pad = 44;
  const px = (lon) => pad + ((lon * k - x0 + (span - xSpan) / 2) / span) * (W - 2 * pad);
  const py = (lat) => W - pad - ((lat - y0 + (span - ySpan) / 2) / span) * (W - 2 * pad);
  const radius = (price) => 4 + 20 * Math.sqrt(Math.max(price, 0) / top);
  const grid = svgEl("g", { stroke: "var(--grid)", "stroke-width": 1 }, map);
  for (let g = 0; g <= 6; g++) {
    const v = pad + (g / 6) * (W - 2 * pad);
    svgEl("line", { x1: v, y1: pad, x2: v, y2: W - pad }, grid);
    svgEl("line", { x1: pad, y1: v, x2: W - pad, y2: v }, grid);
  }
  const layer = svgEl("g", {}, map);
  // Largest first, so a small circle is never hidden under a large one.
  const dots = new Map();
  for (const i of ranked) {
    const o = orders[i];
    const g = svgEl("g", { class: "price-dot", tabindex: 0, role: "button" }, layer);
    const c = svgEl("circle", { cx: px(o.lon), cy: py(o.lat), r: radius(o.price), fill: color(o.veh), "fill-opacity": 0.3, stroke: color(o.veh), "stroke-width": 1.6 }, g);
    const title = svgEl("title", {}, g);
    g.addEventListener("click", () => select(i));
    g.addEventListener("mouseenter", () => select(i));
    g.addEventListener("focus", () => select(i));
    g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(i); } });
    dots.set(i, { g, c, title });
  }
  const dep = data.depot;
  svgEl("rect", { x: px(dep.lon) - 9, y: py(dep.lat) - 9, width: 18, height: 18, rx: 4, fill: "var(--ink)" }, map);
  const depLabel = svgEl("text", { x: px(dep.lon) + 14, y: py(dep.lat) + 5, "font-size": 14, "font-weight": 700, fill: "var(--ink)" }, map);
  depLabel.textContent = dep.label;

  /* ---------- the selected order ---------- */
  function detail() {
    const o = orders[sel];
    $("prices-order").textContent = `${o.id} · ${o.label}`;
    const load = data.dimensions.map((d, j) => `${num(o.q[j], 1)} ${d}`).join(" · ");
    $("prices-kpis").innerHTML = [
      [tr("цена заказа", "price of the order"), money(o.price)],
      [tr("экономия при отказе", "saving if dropped"), o.saving === null ? "—" : money(o.saving)],
      [tr("место по цене", "rank by price"), `${ranked.indexOf(sel) + 1} / ${orders.length}`],
      [tr("груз", "load"), esc(load)],
    ].map(([a, b]) => `<div><dt>${a}</dt><dd>${b}</dd></div>`).join("");
    for (const [i, d] of dots) {
      const on = i === sel;
      d.c.setAttribute("fill-opacity", on ? 0.85 : 0.3);
      d.c.setAttribute("stroke-width", on ? 3 : 1.6);
      d.g.setAttribute("aria-pressed", on ? "true" : "false");
    }
    document.querySelectorAll("#prices-top .vs-row").forEach((row) => row.classList.toggle("on", Number(row.dataset.i) === sel));
  }
  function select(i) {
    if (i === sel) return;
    sel = i;
    detail();
  }

  /* ---------- text, rents and the most expensive orders ---------- */
  function render() {
    for (const [i, d] of dots) {
      const o = orders[i];
      d.title.textContent = `${o.id} · ${tr("цена", "price")} ${money(o.price)}`;
    }
    const gapPct = (100 * data.gap) / data.plan;
    $("prices-summary").innerHTML = [
      [tr("стоимость плана", "plan cost"), money(data.plan)],
      [tr("LP-оценка по пулу", "LP bound over the pool"), money(data.lp)],
      [tr("разрыв", "gap"), `${num(gapPct, 1)}%`],
      [tr("маршрутов в пуле", "routes in the pool"), num(data.columns)],
    ].map(([a, b]) => `<div><dt>${a}</dt><dd>${b}</dd></div>`).join("");
    const scarce = data.rents.filter((r) => r.rent > 0);
    const rentTop = Math.max(...scarce.map((r) => Math.max(r.rent, r.resolved ?? 0)), 1);
    $("prices-rents").innerHTML = scarce.length
      ? scarce.map((r) => {
          const solved = r.resolved ?? 0;
          return `<div class="vs-row"><span><b>${esc(r.type)}</b><br><small>${tr("своих", "own")}: ${r.units}</small></span><div class="tracks">` +
            `<div class="track" title="${tr("LP-рента", "LP rent")}"><div class="fill a" style="width:${(100 * r.rent) / rentTop}%"></div></div>` +
            `<div class="track" title="${tr("пересчёт дня", "day solved again")}"><div class="fill b" style="width:${(100 * Math.max(solved, 0)) / rentTop}%"></div></div>` +
            `<small>${tr("LP-рента", "LP rent")} <b>${money(r.rent)}</b> · ${tr("пересчёт с ещё одной", "solved again with one more")} <b>${money(solved)}</b></small></div></div>`;
        }).join("")
      : `<p class="fine">${tr("Машин каждого типа хватает: ренты нет.", "No vehicle type ran out: no rent.")}</p>`;
    $("prices-top").innerHTML = ranked.slice(0, 6).map((i) => {
      const o = orders[i];
      return `<div class="vs-row" data-i="${i}" tabindex="0" role="button"><span>${esc(o.id)}</span><div class="tracks">` +
        `<div class="track"><div class="fill a" style="width:${(100 * o.price) / top}%;background:${color(o.veh)}"></div></div>` +
        `<div class="track"><div class="fill b" style="width:${(100 * Math.max(o.saving ?? 0, 0)) / top}%"></div></div>` +
        `<small>${money(o.price)} · ${tr("отказ", "dropped")}: ${o.saving === null ? "—" : money(o.saving)}</small></div></div>`;
    }).join("");
    document.querySelectorAll("#prices-top .vs-row").forEach((row) => {
      const pick = () => select(Number(row.dataset.i));
      row.addEventListener("click", pick);
      row.addEventListener("mouseenter", pick);
      row.addEventListener("focus", pick);
    });
    detail();
  }
  rerender.push(render);
  render();
}
