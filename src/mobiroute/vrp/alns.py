"""Adaptive large neighbourhood search for the rich VRP.

Ropke & Pisinger (2006) structure with one destroy operator from Christiaens
& Vanden Berghe (2020):

* destroy - random, worst (largest saving), related (Shaw 1998: distance,
  time and size), string (SISR: short strings cut from neighbouring routes),
  route (a whole small route, which is how vehicles get saved);
* repair - regret-1/2/3 insertion (:func:`~mobiroute.vrp.insertion.regret_repair`),
  with or without noise;
* adaptive operator weights over segments of iterations;
* simulated annealing acceptance with a temperature set so that a 5% worse
  plan is accepted with probability 1/2 at the start.

When the instance ranks vehicles first (``vehicle_penalty > 0``) a fleet
reduction phase runs first: drop the smallest route, cap the fleet one below
the current count and search until every order fits again or the phase
budget runs out (Ropke & Pisinger's route-minimisation stage).

The repair step is the hot path. It runs in the Rust kernel when
``mobiroute_native`` is installed and falls back to the reference Python
implementation otherwise; both give the same plans for the same seed.
"""

from __future__ import annotations

import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any, Literal

from mobiroute.vrp.fleet import TypeAssigner
from mobiroute.vrp.insertion import (
    Compiled,
    RouteState,
    apply_insertion,
    best_insertion,
    regret_repair,
    remove_requests,
    route_exact,
)
from mobiroute.vrp.local_search import LocalSearch
from mobiroute.vrp.local_search import applies as local_search_applies
from mobiroute.vrp.merge import RouteMerger
from mobiroute.vrp.model import Instance
from mobiroute.vrp.setpart import RoutePool, solve_set_partitioning
from mobiroute.vrp.solution import MUST_SERVE_PENALTY, RouteCosts, Solution, evaluate
from mobiroute.vrp.verify import Verdict, verify

Backend = Literal["auto", "python", "native"]
RepairFn = Callable[[Solution, int, float, int, "int | None"], Solution]

DESTROY_OPERATORS = ("random", "worst", "related", "string", "route")
REPAIR_OPERATORS = ("greedy", "regret2", "regret3")


@dataclass(frozen=True, slots=True)
class AlnsConfig:
    iterations: int = 2000
    time_limit: float | None = None
    seed: int = 0
    remove_min: int = 4
    remove_max: int = 60
    #: Upper share of served orders removed per iteration (Ropke & Pisinger's xi).
    remove_share: float = 0.4
    start_worse: float = 0.05
    end_temperature_ratio: float = 0.002
    segment: int = 100
    reaction: float = 0.1
    score_best: float = 33.0
    score_better: float = 9.0
    score_accepted: float = 13.0
    noise: float = 0.025
    #: Share of the budget for fleet reduction when vehicles rank first.
    fleet_phase: float = 0.35
    #: Merge route pairs onto one vehicle (:mod:`mobiroute.vrp.merge`).
    #: ``None`` means on for fleets with more than one vehicle type.
    merge: bool | None = None
    #: The merge scan runs on every new best plan and every ``merge_every`` iterations.
    merge_every: int = 25
    #: Relocate / swap / 2-opt* / 2-opt descent on every new best plan of a
    #: VRPTW instance (:mod:`mobiroute.vrp.local_search`).
    local_search: bool = True
    #: Recombine the routes of accepted plans by set partitioning
    #: (:mod:`mobiroute.vrp.setpart`) during the search and once at the end.
    setpart: bool = False
    #: Iterations between set-partitioning solves; 0 means an eighth of the budget.
    sp_every: int = 0
    #: Budget of one set-partitioning solve (CP-SAT deterministic seconds).
    sp_time: float = 2.0
    #: Solve the set-partitioning model once more after the last phase.
    sp_final: bool = True
    backend: Backend = "auto"


@dataclass(slots=True)
class TracePoint:
    iteration: int
    seconds: float
    objective: float
    vehicles: int
    cost: float
    unassigned: int


@dataclass(slots=True)
class SolveResult:
    instance: str
    solution: Solution
    verdict: Verdict
    objective: float
    iterations: int
    seconds: float
    backend: str
    seed: int
    trace: list[TracePoint] = field(default_factory=list)
    destroy_weights: dict[str, float] = field(default_factory=dict)
    repair_weights: dict[str, float] = field(default_factory=dict)
    #: Set-partitioning solves, how many improved the best plan, and their time.
    sp_calls: int = 0
    sp_improved: int = 0
    sp_seconds: float = 0.0
    pool_size: int = 0


def search_objective(inst: Instance, sol: Solution, costs: RouteCosts | None = None) -> float:
    cost = evaluate(inst, sol, costs=costs)
    return cost.total + inst.vehicle_penalty * cost.vehicles + cost.penalty


def _python_repair(c: Compiled) -> RepairFn:
    def repair(sol: Solution, regret: int, noise: float, seed: int, cap: int | None) -> Solution:
        return regret_repair(c, sol, regret=regret, noise=noise, seed=seed, max_vehicles=cap)

    return repair


def _kernel_for(c: Compiled) -> Any:
    from mobiroute.vrp.native import build_kernel

    return build_kernel(c)


def make_repair(c: Compiled, backend: Backend) -> tuple[RepairFn, str]:
    """Pick the repair implementation: native kernel if present, else Python."""
    if backend != "python":
        from mobiroute.vrp.native import native_repair

        fn = native_repair(c)
        if fn is not None:
            return fn, "native"
        if backend == "native":
            raise RuntimeError("NATIVE_VRP_KERNEL_UNAVAILABLE")
    return _python_repair(c), "python"


def _by_distance(row: tuple[float, ...], n: int) -> list[int]:
    """Node indices sorted by distance from the row's node (ties by index)."""
    return sorted(range(n), key=lambda b: (row[b], b))


#: From this many requests on the search runs in granular mode: worst removal
#: prices a request by the arcs around its stops instead of re-summing its
#: route, and local search on a new best plan starts only from the routes that
#: changed (don't-look bits). Smaller instances keep the full scans, so every
#: published table reproduces bit for bit.
GRANULAR_FROM = 400


def _kth_in(order: list[int], pool: set[int], k: int) -> int:
    """The ``k``-th element of ``order`` that is in ``pool`` (0-based)."""
    for r in order:
        if r in pool:
            if k == 0:
                return r
            k -= 1
    raise IndexError(k)


class _Destroy:
    """Destroy operators; each returns the set of request indices to remove."""

    def __init__(self, c: Compiled, rng: random.Random) -> None:
        self.c = c
        self.rng = rng
        inst = c.inst
        dist = inst.profiles[inst.vehicle_types[0].profile].distance
        self.dist = dist
        self.max_dist = max(max(row) for row in dist) or 1.0
        finite = [nd.latest for nd in inst.nodes if math.isfinite(nd.latest)]
        self.horizon = (max(finite) if finite else 1.0) or 1.0
        dims = c.dims
        self.max_q = [
            max((r.demand[d] for r in inst.requests), default=1.0) or 1.0 for d in range(dims)
        ]
        # Each request is represented by its first and last node.
        self.first = [c.pick[r] if c.pick[r] >= 0 else c.deliv[r] for r in range(inst.n_requests)]
        self.last = [c.deliv[r] if c.deliv[r] >= 0 else c.pick[r] for r in range(inst.n_requests)]
        n = inst.n_nodes
        self.neighbours = [_by_distance(dist[a], n) for a in range(n)]
        self._ranked: dict[int, list[int]] = {}

    def related(self, a: int, b: int) -> float:
        c = self.c
        fa, la, fb, lb = self.first[a], self.last[a], self.first[b], self.last[b]
        spatial = (self.dist[fa][fb] + self.dist[la][lb]) / self.max_dist
        temporal = (abs(c.e[fa] - c.e[fb]) + abs(c.e[la] - c.e[lb])) / self.horizon
        qa, qb = c.demand[a], c.demand[b]
        size = sum(abs(x - y) / m for x, y, m in zip(qa, qb, self.max_q, strict=True)) / c.dims
        return 9.0 * spatial + 3.0 * temporal + 2.0 * size

    def random(self, sol: Solution, served: list[int], q: int) -> set[int]:
        return set(self.rng.sample(served, q))

    def worst(self, sol: Solution, served: list[int], q: int) -> set[int]:
        c = self.c
        saving: dict[int, float] = {}
        if c.inst.n_requests >= GRANULAR_FROM:
            # Removal gain from the arcs around each stop: O(1) per stop.
            for route in sol.routes:
                t = route.vehicle_type
                cost = c.cost[t]
                seq = [c.start[t], *route.nodes, c.end[t]]
                first_at: dict[int, int] = {}
                for k in range(1, len(seq) - 1):
                    node = seq[k]
                    r = c.node_req[node]
                    if r < 0:  # a reload stop belongs to no request
                        continue
                    a, b = seq[k - 1], seq[k + 1]
                    i = first_at.get(r)
                    if i is None:
                        first_at[r] = k
                        saving[r] = cost[a][node] + cost[node][b] - cost[a][b]
                    elif i == k - 1:  # pickup right before its delivery: cut both
                        p0, pick = seq[i - 1], seq[i]
                        saving[r] = cost[p0][pick] + cost[pick][node] + cost[node][b] - cost[p0][b]
                    else:
                        saving[r] += cost[a][node] + cost[node][b] - cost[a][b]
            return self._pick_worst(served, saving, q)
        for route in sol.routes:
            cost = c.cost[route.vehicle_type]
            seq = [c.start[route.vehicle_type], *route.nodes, c.end[route.vehicle_type]]
            base = sum(cost[a][b] for a, b in pairwise(seq))
            requests = c.requests_of(route.nodes)
            for r in requests:
                drop = {c.pick[r], c.deliv[r]}
                rest = [n for n in seq if n not in drop]
                saving[r] = base - sum(cost[a][b] for a, b in pairwise(rest))
        return self._pick_worst(served, saving, q)

    def _pick_worst(self, served: list[int], saving: dict[int, float], q: int) -> set[int]:
        ranked = sorted(served, key=lambda r: (-saving.get(r, 0.0), r))
        out: set[int] = set()
        while len(out) < q and ranked:
            k = int(len(ranked) * self.rng.random() ** 3)
            out.add(ranked.pop(k))
        return out

    def ranked(self, ref: int) -> list[int]:
        """All requests ordered by relatedness to ``ref`` (computed once, then cached)."""
        order = self._ranked.get(ref)
        if order is None:
            order = sorted(range(self.c.inst.n_requests), key=lambda r: (self.related(ref, r), r))
            self._ranked[ref] = order
        return order

    def shaw(self, sol: Solution, served: list[int], q: int, focus: list[int]) -> set[int]:
        pool = set(served)
        if focus:
            # Make room next to an order that is still waiting for a vehicle.
            ranked = self.ranked(self.rng.choice(focus))
            first = _kth_in(ranked, pool, int(len(pool) * self.rng.random() ** 6))
        else:
            first = self.rng.choice(served)
        out = {first}
        pool.discard(first)
        while len(out) < q and pool:
            ref = self.rng.choice(sorted(out))
            # ranked() lists every request, so the filtered list has len(pool)
            # items; walking to the k-th is enough (k is small: random() ** 6).
            pick = _kth_in(self.ranked(ref), pool, int(len(pool) * self.rng.random() ** 6))
            out.add(pick)
            pool.discard(pick)
        return out

    def string(self, sol: Solution, served: list[int], q: int, focus: list[int]) -> set[int]:
        """SISR-style ruin: cut strings from the routes nearest to a seed stop."""
        c = self.c
        routes = [r for r in sol.routes if r.nodes]
        where: dict[int, int] = {}
        for idx, route in enumerate(routes):
            for n in route.nodes:
                where[n] = idx
        avg_len = sum(len(r.nodes) for r in routes) / max(1, len(routes))
        l_max = max(1.0, min(10.0, avg_len))
        k_max = max(1.0, 4.0 * q / (1.0 + l_max) - 1.0)
        k_routes = int(self.rng.uniform(1.0, k_max + 1.0))
        seed_req = self.rng.choice(focus) if focus else self.rng.choice(served)
        seed_node = self.first[seed_req]
        out: set[int] = set()
        cut: set[int] = set()
        for node in self.neighbours[seed_node]:
            if len(cut) >= k_routes or len(out) >= 2 * q:
                break
            hit = where.get(node)
            if hit is None or hit in cut:
                continue
            cut.add(hit)
            nodes = routes[hit].nodes
            length = int(self.rng.uniform(1.0, min(l_max, len(nodes)) + 1.0))
            at = nodes.index(node)
            begin = max(0, min(at - self.rng.randrange(length), len(nodes) - length))
            out.update(c.requests_of(nodes[begin : begin + length]))
        return out or {self.rng.choice(served)}

    def route(self, sol: Solution, served: list[int], q: int) -> set[int]:
        routes = sorted(
            (r for r in sol.routes if r.nodes), key=lambda r: (len(r.nodes), r.nodes[0])
        )
        if not routes:
            return set()
        pick = routes[int(len(routes) * self.rng.random() ** 3)]
        return self.c.requests_of(pick.nodes)


def _roulette(weights: list[float], rng: random.Random) -> int:
    total = sum(weights)
    x = rng.random() * total
    acc = 0.0
    for k, w in enumerate(weights):
        acc += w
        if x <= acc:
            return k
    return len(weights) - 1


class Alns:
    """One ALNS run. Deterministic for a given seed and iteration budget."""

    def __init__(self, inst: Instance, config: AlnsConfig | None = None) -> None:
        self.inst = inst
        self.cfg = config or AlnsConfig()
        self.c = Compiled(inst)
        self.rng = random.Random(self.cfg.seed)
        self._costs: RouteCosts = {}
        self._polished_routes: set[tuple[int, ...]] = set()
        self.repair, self.backend = make_repair(self.c, self.cfg.backend)
        self.kernel = _kernel_for(self.c) if self.backend == "native" else None
        self.assigner = TypeAssigner(self.c, self._route_ok)
        use_merge = (
            self.cfg.merge
            if self.cfg.merge is not None
            else self.c.n_types > 1 or self.c.has_reload
        )
        self.merger = (
            RouteMerger(self.c, self._insertion, self._route_ok, self.assigner)
            if use_merge
            else None
        )
        self.local = (
            LocalSearch(self.c) if self.cfg.local_search and local_search_applies(self.c) else None
        )
        self.pool = RoutePool(self.c) if self.cfg.setpart else None
        self._sp_every = self.cfg.sp_every or max(250, self.cfg.iterations // 8)
        self.sp_calls = self.sp_improved = 0
        self.sp_seconds = 0.0
        self.destroy = _Destroy(self.c, self.rng)
        self.d_weights = [1.0] * len(DESTROY_OPERATORS)
        self.r_weights = [1.0] * len(REPAIR_OPERATORS)
        self.n_weights = [1.0, 1.0]
        self.trace: list[TracePoint] = []
        self.started = 0.0
        self.iteration = 0

    # -- helpers ---------------------------------------------------------
    def _elapsed(self) -> float:
        return time.perf_counter() - self.started

    def _out_of_time(self, limit: float | None) -> bool:
        return limit is not None and self._elapsed() >= limit

    def _record(self, sol: Solution, obj: float) -> None:
        cost = evaluate(self.inst, sol)
        self.trace.append(
            TracePoint(
                self.iteration,
                round(self._elapsed(), 4),
                obj,
                cost.vehicles,
                cost.total,
                cost.unassigned,
            )
        )

    def _served(self, sol: Solution) -> list[int]:
        """Served requests in ascending order: marks instead of a set and a sort."""
        req = self.c.node_req
        mark = bytearray(self.c.inst.n_requests)
        for route in sol.routes:
            for n in route.nodes:
                r = req[n]
                if r >= 0:
                    mark[r] = 1
        return [r for r, hit in enumerate(mark) if hit]

    def _removal_count(self, n_served: int) -> int:
        cfg = self.cfg
        lo = min(cfg.remove_min, n_served)
        hi = min(cfg.remove_max, max(lo, int(cfg.remove_share * n_served)))
        return self.rng.randint(lo, hi) if hi > 0 else 0

    def _destroy(self, op: int, sol: Solution) -> Solution:
        served = self._served(sol)
        if not served:
            return sol.copy()
        q = max(1, self._removal_count(len(served)))
        focus = sorted(sol.unassigned)
        name = DESTROY_OPERATORS[op]
        if name == "random":
            drop = self.destroy.random(sol, served, q)
        elif name == "worst":
            drop = self.destroy.worst(sol, served, q)
        elif name == "related":
            drop = self.destroy.shaw(sol, served, q, focus)
        elif name == "string":
            drop = self.destroy.string(sol, served, q, focus)
        else:
            drop = self.destroy.route(sol, served, q)
        return remove_requests(self.c, sol, drop)

    def _step(self, cur: Solution, cap: int | None) -> tuple[Solution, int, int, int]:
        d_op = _roulette(self.d_weights, self.rng)
        r_op = _roulette(self.r_weights, self.rng)
        n_op = _roulette(self.n_weights, self.rng)
        partial = self._destroy(d_op, cur)
        noise = self.cfg.noise if n_op == 1 else 0.0
        cand = self.assigner.improve(
            self.repair(partial, r_op + 1, noise, self.rng.getrandbits(63), cap)
        )
        if self.merger is not None and self.iteration % max(1, self.cfg.merge_every) == 0:
            cand = self.merger.improve(cand)
        return cand, d_op, r_op, n_op

    def _polish(self, sol: Solution) -> Solution:
        """Merge scan and local search on a plan about to become the best one."""
        if self.merger is not None:
            sol = self.merger.improve(sol)
        if self.local is not None:
            if self.c.inst.n_requests >= GRANULAR_FROM:
                seen = self._polished_routes
                focus = {n for r in sol.routes if tuple(r.nodes) not in seen for n in r.nodes}
                sol = self.local.improve(sol, focus)
                self._polished_routes = {tuple(r.nodes) for r in sol.routes}
            else:
                sol = self.local.improve(sol)
        return sol

    def _setpart(self, best: Solution) -> tuple[Solution, float] | None:
        """Best recombination of pool routes, if it beats ``best``."""
        assert self.pool is not None
        res = solve_set_partitioning(self.pool, best, time_limit=self.cfg.sp_time)
        self.sp_calls += 1
        self.sp_seconds += res.seconds
        if res.solution is None:
            return None
        sol = self._polish(self.assigner.improve(res.solution))
        obj = search_objective(self.inst, sol, self._costs)
        if obj >= search_objective(self.inst, best, self._costs) - 1e-9:
            return None
        self.sp_improved += 1
        self.pool.add(sol)
        self._record(sol, obj)
        return sol, obj

    def _money(self, sol: Solution) -> float:
        return evaluate(self.inst, sol).total

    # -- phases ----------------------------------------------------------
    def _anneal(
        self,
        start: Solution,
        *,
        iterations: int,
        limit: float | None,
        cap: int | None,
        stop_when_complete: bool,
    ) -> Solution:
        cfg = self.cfg
        cur = start
        cur_obj = search_objective(self.inst, cur, self._costs)
        best, best_obj = cur, cur_obj
        base = self._money(start) or 1.0
        t0 = -cfg.start_worse * base / math.log(0.5)
        t_end = t0 * cfg.end_temperature_ratio
        scores_d = [0.0] * len(self.d_weights)
        uses_d = [0] * len(self.d_weights)
        scores_r = [0.0] * len(self.r_weights)
        uses_r = [0] * len(self.r_weights)
        scores_n = [0.0, 0.0]
        uses_n = [0, 0]
        began = self._elapsed()
        for k in range(iterations):
            if self._out_of_time(limit):
                break
            if stop_when_complete and not best.unassigned:
                break
            self.iteration += 1
            progress = k / max(1, iterations)
            if limit is not None:
                span = max(1e-9, limit - began)
                progress = max(progress, (self._elapsed() - began) / span)
            temp = t0 * (t_end / t0) ** min(1.0, progress)
            cand, d_op, r_op, n_op = self._step(cur, cap)
            obj = search_objective(self.inst, cand, self._costs)
            score = 0.0
            if obj < best_obj - 1e-9:
                polished = self._polish(cand)
                if polished is not cand:
                    cand, obj = polished, search_objective(self.inst, polished, self._costs)
                best, best_obj = cand, obj
                cur, cur_obj = cand, obj
                score = cfg.score_best
                self._record(best, best_obj)
            elif obj < cur_obj - 1e-9:
                cur, cur_obj = cand, obj
                score = cfg.score_better
            elif obj > cur_obj + 1e-9 and self.rng.random() < math.exp(-(obj - cur_obj) / temp):
                cur, cur_obj = cand, obj
                score = cfg.score_accepted
            if score > 0.0 and self.pool is not None:
                self.pool.add(cand)
            if self.pool is not None and self.iteration % self._sp_every == 0:
                found = self._setpart(best)
                if found is not None:
                    best, best_obj = found
                    cur, cur_obj = found
            scores_d[d_op] += score
            uses_d[d_op] += 1
            scores_r[r_op] += score
            uses_r[r_op] += 1
            scores_n[n_op] += score
            uses_n[n_op] += 1
            if (k + 1) % cfg.segment == 0:
                for weights, scores, uses in (
                    (self.d_weights, scores_d, uses_d),
                    (self.r_weights, scores_r, uses_r),
                    (self.n_weights, scores_n, uses_n),
                ):
                    for x in range(len(weights)):
                        if uses[x]:
                            weights[x] = max(
                                0.05,
                                weights[x] * (1 - cfg.reaction)
                                + cfg.reaction * scores[x] / uses[x],
                            )
                        scores[x] = 0.0
                        uses[x] = 0
        return best

    def _insertion(self, t: int, nodes: list[int], r: int) -> tuple[float, int, int] | None:
        if self.kernel is not None:
            found: tuple[float, int, int] | None = self.kernel.best_insertion(t, nodes, r)
            return found
        return best_insertion(self.c, RouteState(self.c, t, nodes), r)

    def _route_ok(self, t: int, nodes: list[int]) -> bool:
        if self.kernel is not None:
            ok: bool = self.kernel.exact_feasible_route(t, nodes)
            return ok
        return route_exact(self.c, t, nodes)

    def _eject_insert(self, sol: Solution, v: int, penalty: list[int]) -> Solution | None:
        """Guided ejection (Nagata & Braysy 2009): fit ``v`` by ejecting <= 2 orders.

        Among all routes and ejection sets of at most two orders, take the
        one whose penalty counters sum lowest, then the cheapest insertion.
        Orders that keep coming back to the bank get high counters, so the
        search learns to eject the easy ones. Sets are scanned in increasing
        penalty, and the scan stops once the penalty exceeds the first fit.
        """
        c = self.c
        if self.kernel is not None:
            hit = self.kernel.eject_insert(
                [(r.vehicle_type, r.nodes) for r in sol.routes], v, penalty
            )
            if hit is None:
                return None
            ri, nodes, ejected = hit
            fast = sol.copy()
            fast.routes[ri].nodes = list(nodes)
            fast.unassigned.discard(v)
            fast.unassigned.update(ejected)
            return fast
        options: list[tuple[int, int, tuple[int, ...]]] = []
        for ri, route in enumerate(sol.routes):
            if route.vehicle_type not in c.allowed[v]:
                continue
            on = sorted(c.requests_of(route.nodes))
            options.append((0, ri, ()))
            options += [(penalty[a], ri, (a,)) for a in on]
            options += [
                (penalty[a] + penalty[b], ri, (a, b)) for x, a in enumerate(on) for b in on[x + 1 :]
            ]
        options.sort()
        best: tuple[int, float, int, tuple[int, ...], int, int] | None = None
        for score, ri, eject in options:
            if best is not None and score > best[0]:
                break
            route = sol.routes[ri]
            gone = {n for e in eject for n in (c.pick[e], c.deliv[e]) if n >= 0}
            nodes = [n for n in route.nodes if n not in gone]
            if eject and not self._route_ok(route.vehicle_type, nodes):
                continue  # matrices without the triangle inequality
            found = self._insertion(route.vehicle_type, nodes, v)
            if found is None:
                continue
            key = (score, found[0], ri, eject, found[1], found[2])
            if best is None or key[:3] < best[:3]:
                best = key
        if best is None:
            return None
        _, _, ri, eject, i, j = best
        out = sol.copy()
        route = out.routes[ri]
        gone = {n for e in eject for n in (c.pick[e], c.deliv[e]) if n >= 0}
        route.nodes = apply_insertion(c, [n for n in route.nodes if n not in gone], v, i, j)
        out.unassigned.discard(v)
        out.unassigned.update(eject)
        return out

    def _reduce_fleet(
        self, best: Solution, *, iterations: int, limit: float | None
    ) -> tuple[Solution, int]:
        """Route elimination: drop a small route, then eject and perturb until all fit.

        An attempt gives up after ``stall`` steps without a smaller bank; the
        phase stops at the first failed attempt or when its budget runs out.
        """
        stall = 3000
        attempts_per_size = 3
        budget = iterations
        failures = 0
        while not self._out_of_time(limit) and iterations > 0:
            used = [r for r in best.routes if r.nodes]
            if len(used) <= 1:
                return best, budget - iterations
            target = len(used) - 1
            # Try the smallest route first, then the next ones after a failure.
            ranked = sorted(used, key=lambda r: (len(r.nodes), r.nodes[0]))
            victim = ranked[min(failures, len(ranked) - 1)]
            drop = self.c.requests_of(victim.nodes)
            cur = self.assigner.improve(
                self.repair(
                    remove_requests(self.c, best, drop), 2, 0.0, self.rng.getrandbits(63), target
                )
            )
            penalty = [1] * self.inst.n_requests
            steps = since_better = 0
            smallest_bank = len(cur.unassigned)
            while cur.unassigned and steps < iterations and since_better < stall:
                if self._out_of_time(limit):
                    break
                steps += 1
                since_better += 1
                self.iteration += 1
                v = self.rng.choice(sorted(cur.unassigned))
                moved = self._eject_insert(cur, v, penalty)
                penalty[v] += 1
                if moved is not None:
                    cur = moved
                # Perturb: one ruin-and-recreate step under the fleet cap; keep it
                # unless it leaves more orders in the bank.
                cand, *_ = self._step(cur, target)
                if len(cand.unassigned) <= len(cur.unassigned):
                    cur = cand
                if len(cur.unassigned) < smallest_bank:
                    smallest_bank = len(cur.unassigned)
                    since_better = 0
            iterations -= steps
            if cur.unassigned:
                failures += 1
                if failures >= attempts_per_size:
                    return best, budget - iterations
                continue
            failures = 0
            best = cur
            if self.pool is not None:
                self.pool.add(best)
            self._record(best, search_objective(self.inst, best, self._costs))
        return best, budget - iterations

    def solve(self, initial: Solution | None = None) -> SolveResult:
        cfg = self.cfg
        self.started = time.perf_counter()
        empty = Solution([], set(range(self.inst.n_requests)))
        start = (
            initial.copy() if initial is not None else self.repair(empty, 2, 0.0, cfg.seed, None)
        )
        if start.unassigned:
            start = self.repair(start, 2, 0.0, cfg.seed, None)
        start = self._polish(self.assigner.improve(start))
        self._record(start, search_objective(self.inst, start, self._costs))
        if self.pool is not None:
            self.pool.add(start)
        best = start
        total = cfg.iterations
        limit = cfg.time_limit
        if self.inst.vehicle_penalty > 0 and cfg.fleet_phase > 0:
            # Anneal first: most instances reach their fleet size this way and
            # keep a good structure. Then try to eliminate a route, and anneal
            # again from the best plan with whatever budget is left.
            share = (1.0 - cfg.fleet_phase) / 2.0
            first = int(total * share)
            first_limit = None if limit is None else limit * share
            best = self._anneal(
                best, iterations=first, limit=first_limit, cap=None, stop_when_complete=False
            )
            fleet_limit = None if limit is None else limit * (share + cfg.fleet_phase)
            best, used = self._reduce_fleet(
                best, iterations=int(total * cfg.fleet_phase), limit=fleet_limit
            )
            total -= first + used
        best = self._anneal(
            best, iterations=max(0, total), limit=limit, cap=None, stop_when_complete=False
        )
        if self.pool is not None and cfg.sp_final:
            found = self._setpart(best)
            if found is not None:
                best = found[0]
        objective = search_objective(self.inst, best, self._costs)
        return SolveResult(
            instance=self.inst.name,
            solution=best,
            verdict=verify(self.inst, best),
            objective=objective,
            iterations=self.iteration,
            seconds=round(self._elapsed(), 3),
            backend=self.backend,
            seed=cfg.seed,
            trace=self.trace,
            destroy_weights={
                n: round(w, 3) for n, w in zip(DESTROY_OPERATORS, self.d_weights, strict=True)
            },
            repair_weights={
                n: round(w, 3) for n, w in zip(REPAIR_OPERATORS, self.r_weights, strict=True)
            },
            sp_calls=self.sp_calls,
            sp_improved=self.sp_improved,
            sp_seconds=round(self.sp_seconds, 3),
            pool_size=0 if self.pool is None else len(self.pool),
        )


def solve(
    inst: Instance, config: AlnsConfig | None = None, initial: Solution | None = None
) -> SolveResult:
    """Construct with regret-2, reduce the fleet if vehicles rank first, then anneal."""
    return Alns(inst, config).solve(initial)


__all__ = [
    "DESTROY_OPERATORS",
    "MUST_SERVE_PENALTY",
    "REPAIR_OPERATORS",
    "AlnsConfig",
    "SolveResult",
    "TracePoint",
    "search_objective",
    "solve",
]
