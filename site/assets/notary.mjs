// Route notary for the Cordeau (2006) DARP algebra, in the browser.
// A line-by-line port of verify_routes in src/mobiroute/benchmarks/cordeau_exact.py:
// the timing constraints of a fixed stop sequence are difference constraints
// B[v] - B[u] <= w, feasible iff the constraint graph has no negative cycle
// (Bellman-Ford). tests/test_site_notary_parity.py keeps both in lockstep.

const dist = (inst, i, j) =>
  Math.hypot(inst.nodes[i].x - inst.nodes[j].x, inst.nodes[i].y - inst.nodes[j].y);

function routeConstraints(inst, seq) {
  const n = inst.n;
  const m = seq.length;
  const z = m; // the zero clock
  const edges = [];
  const pos = new Map(seq.map((node, k) => [node, k]));
  seq.forEach((node, k) => {
    const info = inst.nodes[node];
    edges.push({ tail: z, head: k, weight: info.latest, label: `LATEST:${node}` });
    edges.push({ tail: k, head: z, weight: -info.earliest, label: `EARLIEST:${node}` });
  });
  for (let k = 0; k < m - 1; k++) {
    const a = seq[k];
    const b = seq[k + 1];
    const gap = inst.nodes[a].service + dist(inst, a, b);
    edges.push({ tail: k + 1, head: k, weight: -gap, label: `TRAVEL:${a}->${b}` });
  }
  seq.forEach((node, k) => {
    if (node >= 1 && node <= n && pos.has(node + n)) {
      const cap = inst.maxRide + inst.nodes[node].service;
      edges.push({ tail: k, head: pos.get(node + n), weight: cap, label: `RIDE:${node}` });
    }
  });
  edges.push({ tail: 0, head: m - 1, weight: inst.maxDuration, label: "DURATION" });
  return { z, edges };
}

function earliestSchedule(nVertices, z, edges, eps) {
  const d = new Array(nVertices).fill(Infinity);
  const pred = new Array(nVertices).fill(null);
  d[z] = 0;
  for (let round = 0; round < nVertices - 1; round++) {
    let changed = false;
    for (const e of edges) {
      // reversed edge: head -> tail with the same weight
      if (d[e.head] + e.weight < d[e.tail] - 1e-12) {
        d[e.tail] = d[e.head] + e.weight;
        pred[e.tail] = e;
        changed = true;
      }
    }
    if (!changed) break;
  }
  const culprit = edges.find((e) => d[e.head] + e.weight < d[e.tail] - eps);
  if (!culprit) return { times: d.map((v) => -v), cycle: [] };
  d[culprit.tail] = d[culprit.head] + culprit.weight;
  pred[culprit.tail] = culprit;
  let vertex = culprit.tail;
  for (let i = 0; i < nVertices; i++) {
    const step = pred[vertex];
    if (!step) break;
    vertex = step.head;
  }
  const cycle = [];
  const start = vertex;
  for (let i = 0; i < nVertices + 1; i++) {
    const step = pred[vertex];
    if (!step) break;
    cycle.push(step);
    vertex = step.head;
    if (vertex === start) break;
  }
  return { times: null, cycle };
}

/** Verify one route (service node ids, depots excluded). */
export function verifyRoute(inst, route, eps = 1e-6) {
  const n = inst.n;
  const end = 2 * n + 1;
  const seq = [0, ...route, end];
  const violations = [];
  const pos = new Map(seq.map((node, k) => [node, k]));
  let load = 0;
  for (const node of route) {
    load += inst.nodes[node].load;
    if (load > inst.capacity) violations.push(`CAPACITY:${node}`);
    if (load < 0) violations.push(`NEGATIVE_LOAD:${node}`);
    if (node <= n && pos.has(node + n) && pos.get(node + n) < pos.get(node)) {
      violations.push(`DROPOFF_BEFORE_PICKUP:${node}`);
    }
  }
  let cost = 0;
  for (let k = 0; k < seq.length - 1; k++) cost += dist(inst, seq[k], seq[k + 1]);
  const { z, edges } = routeConstraints(inst, seq);
  const { times, cycle } = earliestSchedule(seq.length + 1, z, edges, eps);
  let certificate = null;
  let starts = null;
  let maxRide = 0;
  if (times === null) {
    const shortBy = -cycle.reduce((sum, e) => sum + e.weight, 0);
    const labels = [...new Set(cycle.map((e) => e.label).reverse())];
    certificate = { shortBy, constraints: labels };
    violations.push("SCHEDULE_INFEASIBLE");
  } else {
    starts = times.slice(0, seq.length);
    for (const node of route) {
      if (node <= n && pos.has(node + n)) {
        const ride = starts[pos.get(node + n)] - starts[pos.get(node)] - inst.nodes[node].service;
        if (ride > maxRide) maxRide = ride;
      }
    }
  }
  return { feasible: violations.length === 0, violations, cost, seq, starts, maxRide, certificate };
}

const nodeName = (inst, node, lang) => {
  const en = lang === "en";
  if (node === 0 || node === 2 * inst.n + 1) return en ? "depot" : "депо";
  if (node <= inst.n) return en ? `pickup ${node}` : `подача ${node}`;
  return en ? `dropoff ${node - inst.n}` : `высадка ${node - inst.n}`;
};

/** One human sentence per conflicting constraint, as the Python certificate does. */
export function phrase(inst, label, lang) {
  const en = lang === "en";
  const [kind, ref] = label.split(/:(.*)/s);
  if (kind === "LATEST" || kind === "EARLIEST") {
    const node = Number(ref);
    const info = inst.nodes[node];
    const name = nodeName(inst, node, lang);
    if (kind === "LATEST") {
      return en ? `${name} must start by ${info.latest}` : `${name} — начало не позже ${info.latest}`;
    }
    return en
      ? `${name} cannot start before ${info.earliest}`
      : `${name} — начало не раньше ${info.earliest}`;
  }
  if (kind === "TRAVEL") {
    const [a, b] = ref.split("->").map(Number);
    const service = inst.nodes[a].service;
    const travel = dist(inst, a, b).toFixed(2);
    const src = nodeName(inst, a, lang);
    const dst = nodeName(inst, b, lang);
    return en
      ? `${src} → ${dst} takes ${service} + ${travel} min (service + travel)`
      : `${src} → ${dst}: обслуживание ${service} + переезд ${travel} мин`;
  }
  if (kind === "RIDE") {
    return en
      ? `request ${ref} may ride at most ${inst.maxRide} min`
      : `заявка ${ref} в пути не дольше ${inst.maxRide} мин`;
  }
  if (kind === "CAPACITY") {
    return en
      ? `more than ${inst.capacity} passengers on board at ${nodeName(inst, Number(ref), lang)}`
      : `больше ${inst.capacity} пассажиров в салоне: ${nodeName(inst, Number(ref), lang)}`;
  }
  if (kind === "DROPOFF_BEFORE_PICKUP") {
    return en ? `request ${ref} is dropped off before it is picked up` : `заявка ${ref}: высадка раньше подачи`;
  }
  return en
    ? `the route may last at most ${inst.maxDuration} min`
    : `маршрут не дольше ${inst.maxDuration} мин`;
}

export { nodeName };
