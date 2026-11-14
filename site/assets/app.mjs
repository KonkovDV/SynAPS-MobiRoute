// Page behaviour. Everything here is progressive: the content is in the HTML,
// this file adds motion and the interactive notary.
import { nodeName, phrase, verifyRoute } from "./notary.mjs";
import { initVrp } from "./vrp.mjs";
import { initSheets } from "./sheets.mjs";
import { initPrices } from "./prices.mjs";

const root = document.documentElement;
const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
const reduce = matchMedia("(prefers-reduced-motion: reduce)");
const lang = () => root.dataset.lang || "ru";
const tr = (ru, en) => (lang() === "en" ? en : ru);
const svgEl = (name, attrs = {}, parent) => {
  const el = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (parent) parent.appendChild(el);
  return el;
};
const store = {
  get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
};
const rerender = [];

/* ---------- language and theme ---------- */
function setLang(next) {
  root.dataset.lang = next;
  root.lang = next;
  const btn = $("lang");
  btn.textContent = next === "ru" ? "EN" : "RU";
  btn.setAttribute("aria-label", next === "ru" ? "Switch language to English" : "Переключить язык на русский");
  document.title = next === "ru"
    ? "SynAPS-MobiRoute — маршруты, которые можно доказать"
    : "SynAPS-MobiRoute — routes you can prove";
  store.set("mr-lang", next);
  rerender.forEach((fn) => fn());
}
// Theme and language switch with a cross-fade where the browser supports
// view transitions and the reader has not asked for less motion.
const transition = (fn) =>
  document.startViewTransition && !reduce.matches ? document.startViewTransition(fn) : fn();
$("lang").addEventListener("click", () => transition(() => setLang(lang() === "ru" ? "en" : "ru")));
$("theme").addEventListener("click", () => transition(() => {
  const dark = root.dataset.theme
    ? root.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = dark ? "light" : "dark";
  store.set("mr-theme", root.dataset.theme);
}));
if (store.get("mr-theme")) root.dataset.theme = store.get("mr-theme");

/* ---------- reveal, counters, scroll progress, card spotlight ---------- */
const seen = new WeakSet();
function countUp(el) {
  // The target is read on every frame: measured data may replace the static
  // number while the animation runs.
  const dec = Number(el.dataset.dec || 0);
  const suf = () => (lang() === "en" && el.dataset.sufEn !== undefined ? el.dataset.sufEn : el.dataset.suf || "");
  const paint = (k) => {
    el.textContent = (el.dataset.pre || "") + (Number(el.dataset.count) * k).toFixed(dec) + suf();
  };
  el._final = () => paint(1);
  if (reduce.matches) return paint(1);
  const t0 = performance.now();
  const tick = (t) => {
    const k = Math.min(1, (t - t0) / 1400);
    paint(1 - (1 - k) ** 4);
    if (k < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}
const onReveal = new Map();
const io = new IntersectionObserver((entries) => {
  for (const e of entries) {
    if (!e.isIntersecting) continue;
    e.target.classList.add("in");
    io.unobserve(e.target);
    if (seen.has(e.target)) continue;
    seen.add(e.target);
    e.target.querySelectorAll("[data-count]").forEach(countUp);
    onReveal.get(e.target)?.();
  }
}, { threshold: 0.18, rootMargin: "0px 0px -6% 0px" });
const reveals = [...document.querySelectorAll(".reveal")];
reveals.forEach((el) => {
  const r = el.getBoundingClientRect();
  if (r.top < innerHeight && r.bottom > 0) el.classList.add("in");
});
root.classList.add("anim");
reveals.forEach((el) => io.observe(el));
rerender.push(() => document.querySelectorAll("[data-count]").forEach((el) => el._final?.()));

const progress = document.createElement("div");
progress.className = "progress";
progress.setAttribute("aria-hidden", "true");
document.body.prepend(progress);
let ticking = false;
addEventListener("scroll", () => {
  if (ticking) return;
  ticking = true;
  requestAnimationFrame(() => {
    const max = document.documentElement.scrollHeight - innerHeight;
    progress.style.transform = `scaleX(${max > 0 ? scrollY / max : 0})`;
    ticking = false;
  });
}, { passive: true });

document.querySelectorAll(".card, .ba, .insight").forEach((card) => {
  card.addEventListener("pointermove", (e) => {
    const r = card.getBoundingClientRect();
    card.style.setProperty("--mx", `${e.clientX - r.left}px`);
    card.style.setProperty("--my", `${e.clientY - r.top}px`);
  });
});

const sup = document.querySelector(".big-num .mega sup");
if (sup) {
  onReveal.set(sup.closest(".reveal"), () => {
    if (reduce.matches) return;
    const t0 = performance.now();
    const tick = (t) => {
      const k = Math.min(1, (t - t0) / 1600);
      sup.textContent = String(Math.round(30 * (1 - (1 - k) ** 3)));
      if (k < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

document.querySelectorAll("[data-copy]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText($(btn.dataset.copy).textContent);
      btn.textContent = "✓";
    } catch {
      btn.textContent = "⌘C";
    }
    setTimeout(() => { btn.textContent = "copy"; }, 1400);
  });
});

/* ---------- before / after ---------- */
{
  const refused = new Set([1, 2, 3, 4, 5, 7, 8]); // a2-16 requests refused by the 0.2.7 schedule
  const dots = $("ba-dots");
  for (let i = 1; i <= 16; i++) {
    const li = document.createElement("li");
    li.textContent = String(i);
    li.dataset.i = String(i);
    dots.appendChild(li);
  }
  const setMode = (after) => {
    $("ba-before").setAttribute("aria-pressed", String(!after));
    $("ba-after").setAttribute("aria-pressed", String(after));
    let delay = 0;
    dots.querySelectorAll("li").forEach((li) => {
      const off = !after && refused.has(Number(li.dataset.i));
      li.style.transitionDelay = reduce.matches ? "0ms" : `${refused.has(Number(li.dataset.i)) ? (delay += 70) : 0}ms`;
      li.classList.toggle("off", off);
      li.setAttribute("aria-label", `${li.dataset.i}: ${off ? tr("отклонён", "refused") : tr("обслужен", "served")}`);
    });
    $("ba-num").textContent = after ? "16" : "9";
    $("ba").classList.toggle("fixed", after);
  };
  $("ba-before").addEventListener("click", () => setMode(false));
  $("ba-after").addEventListener("click", () => setMode(true));
  setMode(false);
  onReveal.set($("ba"), () => { if (!reduce.matches) setTimeout(() => setMode(true), 1500); });
}

/* ---------- speed bars ---------- */
function renderSpeed() {
  const rows = [
    [tr("3200 заказов, план на день", "3,200 orders, day plan"), 47.9, 2.8],
    [tr("День со сбоями и срочными заказами", "Day with disruptions and urgent orders"), 67.6, 13.1],
    [tr("ALNS, 1000 заказов", "ALNS, 1,000 orders"), 10.1, 2.6],
  ];
  const host = $("speed");
  host.textContent = "";
  const s = tr("с", "s");
  for (const [label, was, now] of rows) {
    const row = document.createElement("div");
    row.className = "bar";
    row.innerHTML = `<span class="lbl"></span><div class="tracks"><div class="track"><div class="fill was"></div></div><div class="track"><div class="fill"></div></div></div><span class="v">${now} ${s}<small>${tr("было", "was")} ${was}</small></span>`;
    row.querySelector(".lbl").textContent = label;
    host.appendChild(row);
    const [a, b] = row.querySelectorAll(".fill");
    requestAnimationFrame(() => setTimeout(() => {
      a.style.width = `${(was / 67.6) * 100}%`;
      b.style.width = `${(now / 67.6) * 100}%`;
    }, 120));
  }
}
onReveal.set($("speed").closest(".reveal"), renderSpeed);
rerender.push(() => { if ($("speed").childElementCount) renderSpeed(); });

/* ---------- geometry helpers ---------- */
const mapper = (size, pad, ox = 0, oy = 0) => ({
  x: (v) => ox + pad + ((v + 10) / 20) * (size - 2 * pad),
  y: (v) => oy + pad + (1 - (v + 10) / 20) * (size - 2 * pad),
});
const COLORS = ["var(--s1)", "var(--s2)"];
const STRONG = ["var(--s1-strong)", "var(--s2-strong)"];

/* ---------- hero: the optimal day, replayed on the verifier's clock ---------- */
function hero(inst) {
  const svg = $("hero-map");
  const m = mapper(560, 34);
  const n = inst.n;
  const pt = (k) => [m.x(inst.nodes[k].x), m.y(inst.nodes[k].y)];
  const g = svgEl("g", { stroke: "var(--grid)", "stroke-width": 1 }, svg);
  for (let v = -10; v <= 10; v += 5) {
    svgEl("line", { x1: m.x(v), y1: m.y(-10), x2: m.x(v), y2: m.y(10) }, g);
    svgEl("line", { x1: m.x(-10), y1: m.y(v), x2: m.x(10), y2: m.y(v) }, g);
  }
  const tracks = inst.routes.map((route, r) => {
    const seq = [0, ...route, 2 * n + 1];
    const pts = seq.map(pt);
    const starts = inst.starts[r];
    const legs = [];
    let total = 0;
    for (let k = 0; k < seq.length - 1; k++) {
      const a = inst.nodes[seq[k]];
      const b = inst.nodes[seq[k + 1]];
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      const px = Math.hypot(pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1]);
      const depart = k === 0 ? starts[1] - d : starts[k] + a.service;
      legs.push({ depart, d, px, from: total });
      total += px;
    }
    const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
    svgEl("path", { d, fill: "none", stroke: COLORS[r], "stroke-width": 1.4, opacity: 0.28, "stroke-linejoin": "round" }, svg);
    const trail = svgEl("path", { d, fill: "none", stroke: COLORS[r], "stroke-width": 3, "stroke-linejoin": "round", "stroke-linecap": "round", "stroke-dasharray": `0 ${total}` }, svg);
    return { r, seq, pts, starts, legs, total, trail, done: new Set() };
  });
  const stops = [];
  for (const t of tracks) {
    t.seq.slice(1, -1).forEach((node, i) => {
      const [cx, cy] = t.pts[i + 1];
      const pickup = node <= n;
      const c = svgEl("circle", { cx, cy, r: 5.5, fill: pickup ? COLORS[t.r] : "var(--card-on-bg)", stroke: COLORS[t.r], "stroke-width": 2.2, opacity: 0.4 }, svg);
      svgEl("title", {}, c).textContent = `${nodeName(inst, node, "en")} · [${inst.nodes[node].earliest}, ${inst.nodes[node].latest}]`;
      stops.push({ c, t, at: t.starts[i + 1], node, cx, cy });
    });
  }
  const [dx, dy] = pt(0);
  svgEl("rect", { x: dx - 8, y: dy - 8, width: 16, height: 16, rx: 4, fill: "var(--ink)" }, svg);
  const cars = tracks.map((t) => svgEl("circle", { r: 8.5, fill: COLORS[t.r], stroke: "#fff", "stroke-width": 2.5, class: "car" }, svg));
  const endTime = Math.max(...tracks.map((t) => t.starts[t.starts.length - 1])) + 6;
  const beginTime = Math.min(...tracks.map((t) => t.legs[0].depart)) - 6;

  function paint(time, live) {
    for (const t of tracks) {
      let pos = t.pts[0];
      let len = 0;
      for (let k = 0; k < t.legs.length; k++) {
        const leg = t.legs[k];
        if (time < leg.depart) break;
        const f = leg.d > 0 ? Math.min(1, (time - leg.depart) / leg.d) : 1;
        pos = [t.pts[k][0] + (t.pts[k + 1][0] - t.pts[k][0]) * f, t.pts[k][1] + (t.pts[k + 1][1] - t.pts[k][1]) * f];
        len = leg.from + leg.px * f;
      }
      cars[t.r].setAttribute("cx", pos[0]);
      cars[t.r].setAttribute("cy", pos[1]);
      t.trail.setAttribute("stroke-dasharray", `${len} ${t.total}`);
    }
    let served = 0;
    for (const s of stops) {
      const on = time >= s.at;
      if (on && s.node > n) served++;
      const was = s.t.done.has(s.node);
      if (on === was) continue;
      if (on) {
        s.t.done.add(s.node);
        s.c.setAttribute("opacity", 1);
        if (live) {
          const ring = svgEl("circle", { cx: s.cx, cy: s.cy, r: 6, fill: "none", stroke: COLORS[s.t.r], "stroke-width": 2 }, svg);
          ring.animate([{ r: 6, opacity: 0.9 }, { r: 26, opacity: 0 }], { duration: 900, easing: "ease-out" }).onfinish = () => ring.remove();
        }
      } else {
        s.t.done.delete(s.node);
        s.c.setAttribute("opacity", 0.4);
      }
    }
    const minutes = Math.max(0, Math.round(time));
    $("hud-clock").textContent = `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}`;
    $("hud-served").textContent = `${served} / ${n}`;
  }

  const LOOP = 30000;
  const HOLD = 2600;
  let playing = !reduce.matches;
  let visible = true;
  let offset = 0;
  let last = performance.now();
  const frame = (now) => {
    if (playing && visible && !document.hidden) offset = (offset + now - last) % (LOOP + HOLD);
    last = now;
    const k = Math.min(1, offset / LOOP);
    paint(beginTime + (endTime - beginTime) * k, true);
    if (playing) requestAnimationFrame(frame);
  };
  const btn = $("hero-play");
  const sync = () => btn.setAttribute("aria-pressed", String(playing));
  btn.addEventListener("click", () => {
    playing = !playing;
    sync();
    if (playing) { last = performance.now(); requestAnimationFrame(frame); }
  });
  new IntersectionObserver(([e]) => { visible = e.isIntersecting; }, { threshold: 0.05 }).observe(svg);
  sync();
  if (playing) requestAnimationFrame(frame);
  else paint(endTime, false);
}

/* ---------- solver race ---------- */
function race(lab) {
  const rows = lab.literature.filter((x) => x.status !== "BOUND");
  const host = $("race");
  const s = () => tr("с", "s");
  const SPEED = 12;
  const horizon = Math.max(...rows.map((x) => x.seconds));
  let raf = 0;
  const build = () => {
    host.textContent = "";
    return rows.map((x) => {
      const row = document.createElement("div");
      row.className = "bar";
      row.innerHTML = '<span class="lbl"></span><div class="track"><div class="fill"></div></div><span class="v"></span>';
      row.querySelector(".lbl").textContent = x.solver.replace("MIP · ", "MIP ").replace(", rich-VRP engine (10k it)", "").replace(" Routing PCI+GLS (10 s)", "");
      host.appendChild(row);
      const proven = x.status === "OPTIMAL";
      const matched = !proven && x.verified && x.gap_to_published_pct != null && Math.abs(x.gap_to_published_pct) < 0.01;
      return { x, fill: row.querySelector(".fill"), v: row.querySelector(".v"), proven, matched };
    });
  };
  // ✓ proven, = published optimum reached, n/N a plan that leaves requests
  // out (cheaper, but not an answer), +x% the gap of a complete plan.
  const mark = (b) => {
    if (b.proven) return "✓";
    if (b.matched) return "=";
    if (b.x.feasible && !b.x.verified && b.x.served) return b.x.served;
    if (b.x.gap_to_published_pct != null) return `+${b.x.gap_to_published_pct.toFixed(1)}%`;
    return "✕";
  };
  const finish = (b) => {
    b.fill.style.width = `${Math.max(0.8, (b.x.seconds / horizon) * 100)}%`;
    b.fill.classList.toggle("alt", !b.proven);
    b.v.textContent = `${b.x.seconds.toFixed(1)} ${s()} ${mark(b)}`;
  };
  const run = () => {
    cancelAnimationFrame(raf);
    const bars = build();
    if (reduce.matches) return bars.forEach(finish);
    const t0 = performance.now();
    const tick = (now) => {
      const sim = ((now - t0) / 1000) * SPEED;
      let alive = false;
      for (const b of bars) {
        if (sim >= b.x.seconds) { finish(b); continue; }
        alive = true;
        b.fill.style.width = `${(sim / horizon) * 100}%`;
        b.v.textContent = `${sim.toFixed(1)} ${s()}`;
      }
      if (alive) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
  };
  $("race-run").addEventListener("click", run);
  onReveal.set(host.closest(".reveal"), run);
  if (host.closest(".reveal").classList.contains("in")) run();

  const body = document.querySelector("#lab-table tbody");
  for (const x of lab.literature) {
    const ok = x.status === "OPTIMAL";
    const row = body.insertRow();
    const cost = x.cost == null ? (x.bound == null ? "—" : `≥ ${x.bound.toFixed(2)}`) : x.cost.toFixed(2);
    row.innerHTML = `<th scope="row"></th><td><span class="pill ${ok ? "ok" : "mid"}"></span></td><td class="num"></td><td class="num"></td>`;
    row.cells[0].textContent = x.solver;
    const partial = x.feasible && !x.verified && x.served;
    row.cells[1].firstChild.textContent = partial ? `${x.status} · ${x.served}` : x.status;
    row.cells[2].textContent = cost;
    row.cells[3].textContent = x.seconds.toFixed(1);
  }
}

/* ---------- the lab: edit a route, the notary answers ---------- */
function laboratory(inst) {
  const n = inst.n;
  const original = inst.routes.map((r) => [...r]);
  let routes = original.map((r) => [...r]);
  let active = 0;
  let selected = null; // node id
  const chips = $("chips");
  const map = $("lab-map");
  const m = mapper(340, 16, 110, 10);
  const pt = (k) => [m.x(inst.nodes[k].x), m.y(inst.nodes[k].y)];

  function drawMap(verdict) {
    map.textContent = "";
    const hot = new Set();
    const hotEdges = new Set();
    for (const label of verdict.certificate?.constraints ?? []) {
      const [kind, ref] = label.split(/:(.*)/s);
      if (kind === "TRAVEL") { hotEdges.add(ref); ref.split("->").forEach((x) => hot.add(Number(x))); }
      else if (kind === "RIDE") { hot.add(Number(ref)); hot.add(Number(ref) + n); }
      else if (kind !== "DURATION") hot.add(Number(ref));
    }
    routes.forEach((route, r) => {
      const seq = [0, ...route, 2 * n + 1];
      const d = seq.map((k, i) => `${i ? "L" : "M"}${pt(k).map((v) => v.toFixed(1)).join(" ")}`).join(" ");
      svgEl("path", { d, fill: "none", stroke: COLORS[r], "stroke-width": r === active ? 2.4 : 1.2, opacity: r === active ? 1 : 0.22, "stroke-linejoin": "round" }, map);
    });
    const seq = [0, ...routes[active], 2 * n + 1];
    for (let k = 0; k < seq.length - 1; k++) {
      if (!hotEdges.has(`${seq[k]}->${seq[k + 1]}`)) continue;
      const [x1, y1] = pt(seq[k]);
      const [x2, y2] = pt(seq[k + 1]);
      svgEl("line", { x1, y1, x2, y2, stroke: "var(--bad)", "stroke-width": 5, "stroke-linecap": "round", class: "hot" }, map);
    }
    for (const node of routes[active]) {
      const [cx, cy] = pt(node);
      const pickup = node <= n;
      const isHot = hot.has(node);
      if (isHot) svgEl("circle", { cx, cy, r: 13, fill: "none", stroke: "var(--bad)", "stroke-width": 2.5, class: "hot" }, map);
      if (node === selected) svgEl("circle", { cx, cy, r: 11, fill: "none", stroke: "var(--ink)", "stroke-width": 2 }, map);
      svgEl("circle", { cx, cy, r: 5.5, fill: pickup ? COLORS[active] : "var(--card-on-alt)", stroke: COLORS[active], "stroke-width": 2.2 }, map);
      if (isHot || node === selected) {
        const text = svgEl("text", { x: cx + 12, y: cy - 10, "font-size": 12, "font-weight": 700, fill: isHot ? "var(--bad)" : "var(--ink)" }, map);
        text.textContent = nodeName(inst, node, lang());
      }
    }
    const [dx, dy] = pt(0);
    svgEl("rect", { x: dx - 6, y: dy - 6, width: 12, height: 12, rx: 3, fill: "var(--ink)" }, map);
  }

  function drawVerdict(verdict, planCost) {
    const box = $("verdict");
    const was = box.dataset.state;
    const delta = planCost - inst.cost;
    const structural = verdict.violations.filter((v) => !v.startsWith("SCHEDULE") && !v.startsWith("NEGATIVE"));
    const stats = `<dl><div><dt>${tr("план", "plan")}</dt><dd>${planCost.toFixed(2)}</dd></div><div><dt>${tr("маршрут", "route")}</dt><dd>${verdict.cost.toFixed(2)}</dd></div><div><dt>${tr("макс. поездка", "longest ride")}</dt><dd>${verdict.starts ? `${verdict.maxRide.toFixed(1)} ${tr("мин", "min")}` : "—"}</dd></div></dl>`;
    let html;
    let state;
    if (verdict.feasible && Math.abs(delta) < 1e-6) {
      state = "ok";
      html = `<p class="state">✓ ${tr("выполним · доказанный оптимум", "feasible · proven optimum")}</p><h3>${tr("Дешевле не бывает", "It cannot get cheaper")}</h3><p>${tr("CP-SAT доказал, что план со стоимостью меньше 294.25 не существует. Не верите? Сдвиньте любую остановку и попробуйте найти.", "CP-SAT proved that no plan costs less than 294.25. Do not take our word for it: move any stop and try.")}</p>${stats}`;
    } else if (verdict.feasible) {
      state = "ok";
      html = `<p class="state">✓ ${tr("выполним", "feasible")}</p><h3>${tr("Расписание существует, но план стал дороже", "A schedule exists, but the plan got more expensive")}</h3><p class="deficit">+${delta.toFixed(2)}</p><p>${tr("к стоимости оптимального плана", "over the optimal plan")} (+${((delta / inst.cost) * 100).toFixed(1)}%)</p>${stats}`;
    } else {
      state = "bad";
      const items = [...structural, ...(verdict.certificate?.constraints ?? [])].map((label) => `<li>${phrase(inst, label, lang())}</li>`).join("");
      const head = verdict.certificate
        ? `<h3>${tr("Никакое расписание не спасёт эту последовательность", "No schedule can save this sequence")}</h3><p class="deficit">${verdict.certificate.shortBy.toFixed(2)}</p><p>${tr("минут не хватает. Конфликтуют:", "minutes short. In conflict:")}</p>`
        : `<h3>${tr("Нарушена структура маршрута", "The route structure is broken")}</h3>`;
      html = `<p class="state">✕ ${tr("невыполним", "infeasible")}</p>${head}<ul>${items}</ul>${stats}`;
    }
    box.className = `verdict ${state}`;
    box.dataset.state = state;
    box.innerHTML = html;
    if (was && was !== state && !reduce.matches) {
      box.animate([{ transform: "scale(.985)" }, { transform: "scale(1.012)" }, { transform: "scale(1)" }], { duration: 420, easing: "ease-out" });
    }
  }

  function render(focusNode) {
    $("veh-0").setAttribute("aria-pressed", String(active === 0));
    $("veh-1").setAttribute("aria-pressed", String(active === 1));
    chips.textContent = "";
    routes[active].forEach((node) => {
      const li = document.createElement("li");
      const b = document.createElement("button");
      b.type = "button";
      b.className = `chip ${node <= n ? "pick" : "drop"}`;
      b.style.setProperty("--c", STRONG[active]);
      b.textContent = String(node <= n ? node : node - n);
      b.setAttribute("aria-label", nodeName(inst, node, lang()));
      b.setAttribute("aria-pressed", String(node === selected));
      b.dataset.node = String(node);
      li.appendChild(b);
      chips.appendChild(li);
    });
    const idx = routes[active].indexOf(selected);
    $("mv-left").disabled = idx <= 0;
    $("mv-right").disabled = idx < 0 || idx >= routes[active].length - 1;
    const verdict = verifyRoute(inst, routes[active]);
    const other = verifyRoute(inst, routes[1 - active]);
    drawMap(verdict);
    drawVerdict(verdict, verdict.cost + other.cost);
    if (focusNode != null) chips.querySelector(`[data-node="${focusNode}"]`)?.focus();
  }

  function move(step, keepFocus) {
    const route = routes[active];
    const i = route.indexOf(selected);
    const j = i + step;
    if (i < 0 || j < 0 || j >= route.length) return;
    [route[i], route[j]] = [route[j], route[i]];
    render(keepFocus ? selected : null);
  }

  chips.addEventListener("click", (e) => {
    const b = e.target.closest(".chip");
    if (!b) return;
    selected = Number(b.dataset.node);
    render(selected);
  });
  chips.addEventListener("keydown", (e) => {
    const b = e.target.closest(".chip");
    if (!b || (e.key !== "ArrowLeft" && e.key !== "ArrowRight")) return;
    e.preventDefault();
    selected = Number(b.dataset.node);
    move(e.key === "ArrowLeft" ? -1 : 1, true);
  });
  $("mv-left").addEventListener("click", () => move(-1, false));
  $("mv-right").addEventListener("click", () => move(1, false));
  $("veh-0").addEventListener("click", () => { active = 0; selected = null; render(); });
  $("veh-1").addEventListener("click", () => { active = 1; selected = null; render(); });
  $("lab-reset").addEventListener("click", () => { routes = original.map((r) => [...r]); selected = null; render(); });
  $("lab-break").addEventListener("click", () => {
    routes = original.map((r) => [...r]);
    const target = 12 + n;
    const r = routes.findIndex((route) => route.includes(target));
    routes[r] = [...routes[r].filter((x) => x !== target), target];
    active = r;
    selected = target;
    render();
  });
  rerender.push(() => render());
  render();
}

/* ---------- boot ---------- */
const load = (url) => fetch(url).then((r) => { if (!r.ok) throw new Error(`${url}: ${r.status}`); return r.json(); });
setLang(new URLSearchParams(location.search).get("lang") || store.get("mr-lang") || "ru");
load("data/a2-16.json").then((inst) => { hero(inst); laboratory(inst); }).catch((err) => console.error(err));
load("data/solver-lab.json").then(race).catch((err) => console.error(err));
initVrp({ $, tr, lang, svgEl, reduce, rerender, onReveal, load });
initSheets({ $, tr, lang, svgEl, reduce, rerender, onReveal, load });
initPrices({ $, tr, lang, svgEl, reduce, rerender, onReveal, load });
