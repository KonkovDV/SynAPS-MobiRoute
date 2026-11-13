"""Request insertion with constant-time feasibility tests, and regret-k repair.

Route state (Savelsbergh 1992; Campbell & Savelsbergh 2004)
------------------------------------------------------------
For a route ``seq = [start depot, v1 .. vm, end depot]`` the state keeps

* ``begin[k]`` - earliest service start (vehicle leaves as early as allowed),
* ``late[k]`` - latest service start that keeps the rest of the route on time,
* per-dimension loads after every stop.

Putting node ``u`` between positions ``i`` and ``i+1`` is on time iff
``b_u = max(begin[i] + s_i + t(i, u), e_u) <= l_u`` and the arrival at
``i+1`` is ``<= late[i+1]``. A pickup-and-delivery pair scans the delivery
position forward from the pickup and propagates the push only through the
stops in between, so a route of ``m`` stops costs ``O(m^2)`` tests of ``O(1)``.

Shift length
------------
With windows and travel only, the earliest arrival at the end depot when
leaving at ``t`` is ``max(t + G0, A)`` with ``G0`` the pure driving and
service time and ``A = max_k(e_k + G_k)``; the latest departure is
``min_k(l_k - H_k)``. The shortest feasible duration is
``max(G0, A - latest departure)``. Prefix and suffix extrema of
``e_k + G_k`` and ``l_k - H_k`` make it ``O(1)`` per candidate.

Ride limits
-----------
A ride limit couples two stops, so it is not decided by local slack. Routes
that carry one are checked lazily: candidates that pass the fast tests are
sorted by cost and the cheapest ones are timed exactly with Bellman-Ford
(:mod:`mobiroute.vrp.schedule`).

This module is the reference implementation. ``mobiroute_native`` mirrors it
operation for operation, and the parity tests hold both to identical output.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from mobiroute.vrp.model import Instance
from mobiroute.vrp.schedule import TIME_EPS
from mobiroute.vrp.solution import MUST_SERVE_PENALTY, Route, Solution

EPS = 1e-9
#: Cheapest candidates timed exactly per route when a ride limit is involved.
LAZY_CHECKS = 32
#: Stand-in cost of a missing option in regret sums.
MISSING = 1e15
NEG_INF = -math.inf


class SplitMix64:
    """Tiny portable PRNG (Steele, Lea & Flood 2014), identical in Rust."""

    __slots__ = ("state",)
    _MASK = (1 << 64) - 1

    def __init__(self, seed: int) -> None:
        self.state = seed & self._MASK

    def next_u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & self._MASK
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & self._MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & self._MASK
        return z ^ (z >> 31)

    def uniform(self) -> float:
        """Uniform in ``[0, 1)`` with 53 random bits."""
        return (self.next_u64() >> 11) * (1.0 / 9007199254740992.0)


class Compiled:
    """Flat per-node, per-request and per-type lists for the hot loops."""

    def __init__(self, inst: Instance) -> None:
        self.inst = inst
        self.n = inst.n_nodes
        self.dims = len(inst.dimensions)
        self.e = [nd.earliest for nd in inst.nodes]
        self.l = [nd.latest for nd in inst.nodes]
        self.s = [nd.service for nd in inst.nodes]
        types = inst.vehicle_types
        self.n_types = len(types)
        cost_cache: dict[tuple[str, float, float], tuple[tuple[float, ...], ...]] = {}
        self.time: list[tuple[tuple[float, ...], ...]] = []
        self.cost: list[tuple[tuple[float, ...], ...]] = []
        for vt in types:
            profile = inst.profiles[vt.profile]
            self.time.append(profile.time)
            key = (vt.profile, vt.cost_per_distance, vt.cost_per_time)
            if key not in cost_cache:
                cd, ct = vt.cost_per_distance, vt.cost_per_time
                if ct == 0.0 and cd == 1.0:
                    cost_cache[key] = profile.distance
                else:
                    cost_cache[key] = tuple(
                        tuple(cd * dv + ct * tv for dv, tv in zip(drow, trow, strict=True))
                        for drow, trow in zip(profile.distance, profile.time, strict=True)
                    )
            self.cost.append(cost_cache[key])
        self.svc_rate = [vt.cost_per_time for vt in types]
        self.open_cost = [vt.fixed_cost + inst.vehicle_penalty for vt in types]
        self.cap = [vt.capacity for vt in types]
        self.count = [vt.count for vt in types]
        self.start = [vt.start_depot for vt in types]
        self.end = [vt.end_depot for vt in types]
        self.t_min = [max(inst.nodes[vt.start_depot].earliest, vt.shift_start) for vt in types]
        self.start_lim = [min(inst.nodes[vt.start_depot].latest, vt.shift_end) for vt in types]
        self.end_lim = [min(inst.nodes[vt.end_depot].latest, vt.shift_end) for vt in types]
        self.max_dur = [math.inf if vt.max_duration is None else vt.max_duration for vt in types]
        reqs = inst.requests
        self.pick = [-1 if r.pickup is None else r.pickup for r in reqs]
        self.deliv = [-1 if r.delivery is None else r.delivery for r in reqs]
        self.demand = [r.demand for r in reqs]
        self.max_ride = [math.inf if r.max_ride is None else r.max_ride for r in reqs]
        self.penalty = [MUST_SERVE_PENALTY if r.penalty is None else r.penalty for r in reqs]
        self.has_ride = any(r.max_ride is not None for r in reqs)
        usable = [self.t_min[t] <= self.start_lim[t] + EPS for t in range(self.n_types)]
        self.allowed = [
            [
                t
                for t, vt in enumerate(types)
                if usable[t]
                and r.skills <= vt.skills
                and all(q <= c + EPS for q, c in zip(r.demand, vt.capacity, strict=True))
            ]
            for r in reqs
        ]
        self.node_req = [inst.request_of(k) for k in range(self.n)]
        self.max_cost = max(max(max(row) for row in m) for m in self.cost)


class RouteState:
    """Cached schedule and load data of one route (see module docstring)."""

    __slots__ = (
        "a_max",
        "a_pre",
        "a_suf",
        "begin",
        "dynamic",
        "fits_cache",
        "fresh",
        "g_total",
        "h",
        "has_ride",
        "late",
        "lm_pre",
        "lm_suf",
        "load",
        "nodes",
        "seq",
        "t",
    )

    def __init__(
        self,
        c: Compiled,
        t: int,
        nodes: Sequence[int],
        *,
        origin: int | None = None,
        ready: float | None = None,
        fresh: bool = True,
        end_by: float | None = None,
    ) -> None:
        """State of ``nodes`` driven by a vehicle of type ``t``.

        By default the vehicle leaves its start depot as early as its shift
        allows. Dispatch passes ``origin``/``ready`` instead: the vehicle is
        at (or bound for) node ``origin`` and free from time ``ready``, and
        ``nodes`` is the part of its plan that may still change. Orders
        whose delivery is in ``nodes`` but whose pickup is not are on board
        from the start. ``fresh`` says whether using the vehicle still costs
        its fixed cost (an idle vehicle already in service does not).
        ``end_by`` is a return deadline; once a vehicle has left the depot its
        shift cap is exactly such a deadline (departure plus the cap).
        """
        self.t = t
        self.nodes = list(nodes)
        self.dynamic = origin is not None
        self.fresh = fresh
        seq = [c.start[t] if origin is None else origin, *nodes, c.end[t]]
        self.seq = seq
        m2 = len(seq)
        time = c.time[t]
        e, lat, s = c.e, c.l, c.s
        begin = [0.0] * m2
        begin[0] = c.t_min[t] if ready is None else ready
        for k in range(1, m2):
            a, b = seq[k - 1], seq[k]
            arr = begin[k - 1] + s[a] + time[a][b]
            eb = e[b]
            begin[k] = arr if arr > eb else eb
        lim = [lat[node] for node in seq]
        lim[0] = c.start_lim[t] if origin is None else math.inf
        lim[-1] = c.end_lim[t] if end_by is None else min(c.end_lim[t], end_by)
        late = [0.0] * m2
        late[-1] = lim[-1]
        for k in range(m2 - 2, -1, -1):
            a, b = seq[k], seq[k + 1]
            back = late[k + 1] - s[a] - time[a][b]
            late[k] = lim[k] if lim[k] < back else back
        self.begin = begin
        self.late = late
        dims = c.dims
        initial = [0.0] * dims
        present = set(nodes)
        for node in nodes:
            r = c.node_req[node]
            if node == c.deliv[r] and c.pick[r] not in present:
                q = c.demand[r]
                for d in range(dims):
                    initial[d] += q[d]
        load: list[list[float]] = [list(initial)]
        cur = initial
        for node in nodes:
            r = c.node_req[node]
            q = c.demand[r]
            sign = 1.0 if node == c.pick[r] else -1.0
            cur = [cur[d] + sign * q[d] for d in range(dims)]
            load.append(cur)
        self.load = load  # positions 0..m (the end depot adds nothing)
        self.fits_cache: dict[int, list[bool]] = {}
        # Shift-length data (module docstring): H, G0, extrema of l - H and e + G.
        h = [0.0] * m2
        for k in range(1, m2):
            a, b = seq[k - 1], seq[k]
            h[k] = h[k - 1] + s[a] + time[a][b]
        self.h = h
        g_total = h[-1]
        self.g_total = g_total
        lm_pre = [0.0] * m2
        lm_suf = [0.0] * m2
        cur_min = math.inf
        for k in range(m2):
            v = lim[k] - h[k]
            cur_min = v if v < cur_min else cur_min
            lm_pre[k] = cur_min
        cur_min = math.inf
        for k in range(m2 - 1, -1, -1):
            v = lim[k] - h[k]
            cur_min = v if v < cur_min else cur_min
            lm_suf[k] = cur_min
        a_pre = [NEG_INF] * m2
        a_suf = [NEG_INF] * (m2 + 1)
        cur_max = NEG_INF
        for k in range(1, m2):
            v = e[seq[k]] + (g_total - h[k])
            cur_max = v if v > cur_max else cur_max
            a_pre[k] = cur_max
        cur_max = NEG_INF
        for k in range(m2 - 1, 0, -1):
            v = e[seq[k]] + (g_total - h[k])
            cur_max = v if v > cur_max else cur_max
            a_suf[k] = cur_max
        self.lm_pre = lm_pre
        self.lm_suf = lm_suf
        self.a_pre = a_pre
        self.a_suf = a_suf
        self.a_max = a_pre[-1]
        self.has_ride = c.has_ride and any(c.max_ride[c.node_req[n]] < math.inf for n in nodes)

    @property
    def feasible(self) -> bool:
        return all(b <= lt + EPS for b, lt in zip(self.begin, self.late, strict=True))

    def fits(self, c: Compiled, r: int) -> list[bool]:
        """Whether request ``r`` fits on board after each position 0..m."""
        cached = self.fits_cache.get(r)
        if cached is not None:
            return cached
        q = c.demand[r]
        cap = c.cap[self.t]
        if c.dims == 1:
            room = cap[0] - q[0] + EPS
            out = [row[0] <= room for row in self.load]
        else:
            out = [all(row[d] + q[d] <= cap[d] + EPS for d in range(c.dims)) for row in self.load]
        self.fits_cache[r] = out
        return out


def _min_duration_ok(
    c: Compiled,
    st: RouteState,
    i: int,
    j: int,
    p: int,
    d: int,
    mid_min: float,
    mid_amax: float,
) -> bool:
    """Shortest feasible duration after inserting ``p`` (and ``d``) is within the cap.

    ``j < 0`` means a single node ``p`` after position ``i``. For a pair,
    ``j == i`` puts ``d`` right after ``p``; ``j > i`` puts it after position
    ``j``, with ``mid_min``/``mid_amax`` the extrema over positions ``i+1..j``.
    """
    t = st.t
    seq = st.seq
    time = c.time[t]
    s, e, lat = c.s, c.e, c.l
    h = st.h
    a = seq[i]
    b = seq[i + 1]
    hp = h[i] + s[a] + time[a][p]
    if j < 0:
        delta = (s[a] + time[a][p] + s[p] + time[p][b]) - (s[a] + time[a][b])
        g0 = st.g_total + delta
        dep = min(st.lm_pre[i], st.lm_suf[i + 1] - delta, lat[p] - hp)
        amax = max(st.a_pre[i] + delta, st.a_suf[i + 1], e[p] + (g0 - hp))
    elif j == i:
        hd = hp + s[p] + time[p][d]
        delta = (s[a] + time[a][p] + s[p] + time[p][d] + s[d] + time[d][b]) - (s[a] + time[a][b])
        g0 = st.g_total + delta
        dep = min(st.lm_pre[i], st.lm_suf[i + 1] - delta, lat[p] - hp, lat[d] - hd)
        amax = max(st.a_pre[i] + delta, st.a_suf[i + 1], e[p] + (g0 - hp), e[d] + (g0 - hd))
    else:
        cj = seq[j]
        nx = seq[j + 1]
        d1 = (s[a] + time[a][p] + s[p] + time[p][b]) - (s[a] + time[a][b])
        d2 = (s[cj] + time[cj][d] + s[d] + time[d][nx]) - (s[cj] + time[cj][nx])
        delta = d1 + d2
        hd = h[j] + d1 + s[cj] + time[cj][d]
        g0 = st.g_total + delta
        dep = min(st.lm_pre[i], mid_min - d1, st.lm_suf[j + 1] - delta, lat[p] - hp, lat[d] - hd)
        amax = max(
            st.a_pre[i] + delta,
            mid_amax + d2,
            st.a_suf[j + 1],
            e[p] + (g0 - hp),
            e[d] + (g0 - hd),
        )
    duration = g0 if g0 > amax - dep else amax - dep
    return duration <= c.max_dur[t] + EPS


def exact_feasible(c: Compiled, t: int, nodes: Sequence[int]) -> bool:
    """Exact timing test of a fixed sequence, ride and shift limits included.

    Same constraint graph as :func:`mobiroute.vrp.schedule.route_arcs`, kept
    in three flat lists instead of labelled objects: Bellman-Ford from the
    zero clock over arcs relaxed head to tail, so travel arcs in route order
    settle the earliest schedule in one pass and the loop usually stops after
    two or three. A negative cycle means no schedule exists.
    """
    seq = [c.start[t], *nodes, c.end[t]]
    m = len(seq)
    z = m
    time = c.time[t]
    e, lat, s = c.e, c.l, c.s
    tails: list[int] = []
    heads: list[int] = []
    weights: list[float] = []
    last = m - 1
    for k in range(m):
        node = seq[k]
        if k == 0:
            lo, hi = c.t_min[t], c.start_lim[t]
        elif k == last:
            lo, hi = e[node], c.end_lim[t]
        else:
            lo, hi = e[node], lat[node]
        if hi < math.inf:
            tails.append(z)
            heads.append(k)
            weights.append(hi)
        tails.append(k)
        heads.append(z)
        weights.append(-lo)
    for k in range(m - 1):
        a, b = seq[k], seq[k + 1]
        tails.append(k + 1)
        heads.append(k)
        weights.append(-(s[a] + time[a][b]))
    where = {node: k for k, node in enumerate(seq) if 0 < k < last}
    for k in range(1, last):
        node = seq[k]
        r = c.node_req[node]
        if c.pick[r] == node and c.max_ride[r] < math.inf:
            kd = where.get(c.deliv[r])
            if kd is not None:
                tails.append(k)
                heads.append(kd)
                weights.append(c.max_ride[r] + s[node])
    if c.max_dur[t] < math.inf:
        tails.append(0)
        heads.append(last)
        weights.append(c.max_dur[t])
    n_vertices = m + 1
    dist = [math.inf] * n_vertices
    dist[z] = 0.0
    n_arcs = len(tails)
    for _ in range(n_vertices - 1):
        changed = False
        for x in range(n_arcs):
            cand = dist[heads[x]] + weights[x]
            if cand < dist[tails[x]] - 1e-12:
                dist[tails[x]] = cand
                changed = True
        if not changed:
            return True
    return all(dist[heads[x]] + weights[x] >= dist[tails[x]] - TIME_EPS for x in range(n_arcs))


def _splice(nodes: list[int], i: int, j: int, p: int, d: int) -> list[int]:
    """Nodes after inserting ``p`` after position ``i`` and ``d`` after ``j``.

    Positions count the start depot as 0, so position ``i`` is ``nodes[i-1]``.
    ``d < 0`` inserts the single node ``p``.
    """
    if d < 0:
        return [*nodes[:i], p, *nodes[i:]]
    if j == i:
        return [*nodes[:i], p, d, *nodes[i:]]
    return [*nodes[:i], p, *nodes[i:j], d, *nodes[j:]]


Candidate = tuple[float, int, int]


def best_insertion(c: Compiled, st: RouteState, r: int) -> Candidate | None:
    """Cheapest feasible ``(delta cost, i, j)`` of request ``r`` in this route."""
    t = st.t
    if t not in c.allowed[r]:
        return None
    p, d = c.pick[r], c.deliv[r]
    lazy = c.has_ride and (st.has_ride or c.max_ride[r] < math.inf)
    check_dur = not lazy and not st.dynamic and c.max_dur[t] < math.inf
    fits = st.fits(c, r)
    m = len(st.seq) - 2
    extra = c.svc_rate[t] * ((c.s[p] if p >= 0 else 0.0) + (c.s[d] if d >= 0 else 0.0))
    if m == 0 and st.fresh:
        extra += c.open_cost[t]
    if p >= 0 and d >= 0:
        found = _pair_candidates(c, st, p, d, fits, extra, check_dur, lazy)
    elif d >= 0:
        found = _single_candidates(c, st, d, fits, extra, check_dur, lazy, prefix=True)
    else:
        found = _single_candidates(c, st, p, fits, extra, check_dur, lazy, prefix=False)
    if not lazy:
        return found[0] if found else None
    found.sort()
    for cand in found[:LAZY_CHECKS]:
        _, i, j = cand
        if d >= 0 and p >= 0:
            nodes = _splice(st.nodes, i, j, p, d)
        else:
            nodes = _splice(st.nodes, i, -1, p if p >= 0 else d, -1)
        if exact_feasible(c, t, nodes):
            return cand
    return None


def _single_candidates(
    c: Compiled,
    st: RouteState,
    u: int,
    fits: list[bool],
    extra: float,
    check_dur: bool,
    lazy: bool,
    *,
    prefix: bool,
) -> list[Candidate]:
    t = st.t
    seq, begin, late = st.seq, st.begin, st.late
    time, cost = c.time[t], c.cost[t]
    s = c.s
    eu, lu, su = c.e[u], c.l[u], c.s[u]
    tu, cu = time[u], cost[u]
    m = len(seq) - 2
    best: Candidate | None = None
    out: list[Candidate] = []
    # A delivery loaded at the depot rides every leg before its stop; a
    # collection rides every leg after it. ``first`` is the first position
    # from which every later load still has room for a collection.
    first = 0
    if not prefix:
        first = m + 1
        while first > 0 and fits[first - 1]:
            first -= 1
    for i in range(first, m + 1):
        if prefix and not fits[i]:
            break
        a, b = seq[i], seq[i + 1]
        arr = begin[i] + s[a] + time[a][u]
        bu = arr if arr > eu else eu
        if bu > lu + EPS or bu + su + tu[b] > late[i + 1] + EPS:
            continue
        if check_dur and not _min_duration_ok(c, st, i, -1, u, -1, 0.0, 0.0):
            continue
        cand = ((cost[a][u] + cu[b] - cost[a][b]) + extra, i, i)
        if lazy:
            out.append(cand)
        elif best is None or cand < best:
            best = cand
    if lazy:
        return out
    return [] if best is None else [best]


def _pair_candidates(
    c: Compiled,
    st: RouteState,
    p: int,
    d: int,
    fits: list[bool],
    extra: float,
    check_dur: bool,
    lazy: bool,
) -> list[Candidate]:
    t = st.t
    seq, begin, late = st.seq, st.begin, st.late
    time, cost = c.time[t], c.cost[t]
    e, lat, s = c.e, c.l, c.s
    ep, lp, sp = e[p], lat[p], s[p]
    ed, ld, sd = e[d], lat[d], s[d]
    tp, td, cp, cd = time[p], time[d], cost[p], cost[d]
    tpd, cpd = tp[d], cp[d]
    m = len(seq) - 2
    best: Candidate | None = None
    out: list[Candidate] = []
    for i in range(m + 1):
        if not fits[i]:
            continue
        a, b = seq[i], seq[i + 1]
        arr = begin[i] + s[a] + time[a][p]
        bp = arr if arr > ep else ep
        if bp > lp + EPS:
            continue
        # Delivery right after the pickup.
        arr_d = bp + sp + tpd
        bd = arr_d if arr_d > ed else ed
        if (
            bd <= ld + EPS
            and bd + sd + td[b] <= late[i + 1] + EPS
            and (not check_dur or _min_duration_ok(c, st, i, i, p, d, 0.0, 0.0))
        ):
            cand = ((cost[a][p] + cpd + cd[b] - cost[a][b]) + extra, i, i)
            if lazy:
                out.append(cand)
            elif best is None or cand < best:
                best = cand
        # Delivery after a later stop: push the pickup's delay through i+1..j.
        detour_p = cost[a][p] + cp[b] - cost[a][b]
        tcur = bp + sp + tp[b]
        mid_min = math.inf
        mid_amax = NEG_INF
        for j in range(i + 1, m + 1):
            cj = seq[j]
            ej = e[cj]
            bj = tcur if tcur > ej else ej
            if bj > lat[cj] + EPS or not fits[j]:
                break  # stop j rides with the order for every later delivery spot
            if check_dur:
                v = lat[cj] - st.h[j]
                mid_min = v if v < mid_min else mid_min
                w = ej + (st.g_total - st.h[j])
                mid_amax = w if w > mid_amax else mid_amax
            nx = seq[j + 1]
            arr_d = bj + s[cj] + time[cj][d]
            bd = arr_d if arr_d > ed else ed
            if (
                bd <= ld + EPS
                and bd + sd + td[nx] <= late[j + 1] + EPS
                and (not check_dur or _min_duration_ok(c, st, i, j, p, d, mid_min, mid_amax))
            ):
                cand = (detour_p + (cost[cj][d] + cd[nx] - cost[cj][nx]) + extra, i, j)
                if lazy:
                    out.append(cand)
                elif best is None or cand < best:
                    best = cand
            tcur = bj + s[cj] + time[cj][nx]
    if lazy:
        return out
    return [] if best is None else [best]


def apply_insertion(c: Compiled, nodes: list[int], r: int, i: int, j: int) -> list[int]:
    p, d = c.pick[r], c.deliv[r]
    if p >= 0 and d >= 0:
        return _splice(nodes, i, j, p, d)
    return _splice(nodes, i, -1, p if p >= 0 else d, -1)


def remove_requests(c: Compiled, solution: Solution, requests: Iterable[int]) -> Solution:
    """Take requests out of their routes; emptied routes disappear."""
    drop = set(requests)
    nodes_out = {n for r in drop for n in (c.pick[r], c.deliv[r]) if n >= 0}
    routes = []
    for route in solution.routes:
        kept = [n for n in route.nodes if n not in nodes_out]
        if kept:
            routes.append(Route(route.vehicle_type, kept))
    return Solution(routes, set(solution.unassigned) | drop)


class _Slot:
    __slots__ = ("empty", "offered", "state")

    def __init__(self, state: RouteState, empty: bool) -> None:
        self.state = state
        self.empty = empty
        self.offered = True


def regret_repair(
    c: Compiled,
    solution: Solution,
    *,
    regret: int = 2,
    noise: float = 0.0,
    seed: int = 0,
    max_vehicles: int | None = None,
) -> Solution:
    """Insert every unassigned request by regret-k (Potvin & Rousseau 1993).

    ``regret == 1`` is greedy cheapest insertion. Each step inserts the order
    whose best and k-th best routes differ most, so orders with few good
    options go first. An empty vehicle of every type with spare units is an
    option too, priced with its fixed cost; ``max_vehicles`` caps the number
    of routes in total. ``noise > 0`` perturbs every evaluated cost by
    ``noise * max_arc_cost * U(-1, 1)`` (Ropke & Pisinger 2006). Orders with
    no feasible option stay unassigned.

    Evaluation order is part of the contract: requests in increasing index,
    slots in creation order, one random draw per evaluation. The native
    kernel follows the same order, so both produce identical plans.
    """
    rng = SplitMix64(seed) if noise > 0 else None
    amp = noise * c.max_cost
    slots: list[_Slot] = []
    used = [0] * c.n_types
    for route in solution.routes:
        if route.nodes:
            slots.append(_Slot(RouteState(c, route.vehicle_type, route.nodes), False))
            used[route.vehicle_type] += 1
    limit = sum(c.count) if max_vehicles is None else max_vehicles
    if sum(used) < limit:
        for t in range(c.n_types):
            if used[t] < c.count[t]:
                slots.append(_Slot(RouteState(c, t, []), True))
    pending = sorted(solution.unassigned)
    unserved: set[int] = set()

    def evaluate(r: int, slot: _Slot) -> float:
        if not slot.offered:
            return MISSING
        found = best_insertion(c, slot.state, r)
        if rng is not None:
            jitter = amp * (2.0 * rng.uniform() - 1.0)
            if found is None:
                return MISSING
            value = found[0] + jitter
            return value if value > 0.0 else 0.0
        return MISSING if found is None else found[0]

    table: dict[int, list[float]] = {r: [evaluate(r, slot) for slot in slots] for r in pending}
    k = max(1, regret)
    while pending:
        pick_r = -1
        pick_key: tuple[float, float, int] | None = None
        for r in pending:
            row = sorted(table[r])
            c1 = row[0] if row else MISSING
            if c1 >= MISSING:
                continue
            if k == 1:
                key = (0.0, c1, r)
            else:
                rg = 0.0
                for h in range(1, k):
                    ch = row[h] if h < len(row) else MISSING
                    rg += ch - c1
                key = (-rg, c1, r)
            if pick_key is None or key < pick_key:
                pick_key = key
                pick_r = r
        if pick_r < 0:
            unserved.update(pending)
            break
        values = table[pick_r]
        best_slot = 0
        for x in range(1, len(slots)):
            if values[x] < values[best_slot]:
                best_slot = x
        slot = slots[best_slot]
        found = best_insertion(c, slot.state, pick_r)
        assert found is not None
        _, i, j = found
        t = slot.state.t
        slot.state = RouteState(c, t, apply_insertion(c, slot.state.nodes, pick_r, i, j))
        pending.remove(pick_r)
        del table[pick_r]
        refresh = [best_slot]
        if slot.empty:
            slot.empty = False
            used[t] += 1
            if sum(used) >= limit:
                for other in slots:
                    if other.empty:
                        other.offered = False
                for row in table.values():
                    for x, other in enumerate(slots):
                        if other.empty:
                            row[x] = MISSING
            elif used[t] < c.count[t]:
                slots.append(_Slot(RouteState(c, t, []), True))
                refresh.append(len(slots) - 1)
        for r in pending:
            row = table[r]
            for x in refresh:
                value = evaluate(r, slots[x])
                if x < len(row):
                    row[x] = value
                else:
                    row.append(value)
    routes = [Route(s.state.t, list(s.state.nodes)) for s in slots if s.state.nodes]
    return Solution(routes, unserved)
