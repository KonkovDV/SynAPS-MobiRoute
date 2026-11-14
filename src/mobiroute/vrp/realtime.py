"""Real-time dispatch: orders appear during the day and get an answer at once.

The simulator replays an instance in release order. Every vehicle follows its
plan as early as possible; at each new order the part of the plan already
driven (and the stop a vehicle is heading to) is frozen, and the order is
inserted into the remaining part of one vehicle's plan, or refused with the
reason. One decision costs a constant-time insertion test per vehicle, so it
takes about a millisecond on a fleet of tens of vehicles.

Re-optimisation policy
----------------------
With ``reoptimize_every`` set, the live state is periodically written as an
ordinary static instance and improved by ALNS:

* each vehicle in service becomes a vehicle type of one unit whose start
  depot is a copy of its current position and whose shift starts when it is
  free again;
* orders on board become deliveries loaded at that start, locked to their
  vehicle by a private skill only it provides;
* orders assigned but not picked up become free pickup-and-delivery pairs;
* idle vehicles at the depot keep their type and fixed cost.

The current plan seeds the search, so the result is never worse. The same
snapshot can be handed to OR-Tools, which is how the re-solve-per-order
policy is measured.

KPIs: acceptance, time from call to pickup (vehicle arrival lead time), ride
time, distance, vehicles used, decision latency.
"""

from __future__ import annotations

import math
import statistics
import time
from dataclasses import dataclass, field
from typing import Literal

from mobiroute.vrp.alns import AlnsConfig, search_objective
from mobiroute.vrp.alns import solve as alns_solve
from mobiroute.vrp.insertion import Compiled, RouteState, apply_insertion, best_insertion
from mobiroute.vrp.model import Instance, Node, Profile, Request, VehicleType
from mobiroute.vrp.solution import Route, Solution
from mobiroute.vrp.verify import verify

Policy = Literal["insertion", "insertion+alns", "ortools-resolve"]


@dataclass(frozen=True, slots=True)
class Decision:
    request: str
    released: float
    accepted: bool
    vehicle: int | None
    pickup_start: float | None
    latency_ms: float
    reason: str = ""


@dataclass(slots=True)
class _Unit:
    t: int
    plan: list[int] = field(default_factory=list)
    starts: list[float] = field(default_factory=list)
    used: bool = False
    #: When the vehicle left the depot; its shift cap runs from here.
    left: float | None = None


@dataclass(frozen=True, slots=True)
class RealtimeReport:
    policy: str
    instance: str
    decisions: tuple[Decision, ...]
    kpi: dict[str, float]
    plans: tuple[tuple[int, tuple[int, ...], tuple[float, ...]], ...]
    verified: bool
    violations: tuple[str, ...]


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))
    return ordered[k]


class Dispatcher:
    """Replays an instance in release order and dispatches every order on arrival."""

    def __init__(
        self,
        inst: Instance,
        *,
        policy: Policy = "insertion",
        reoptimize_every: float = 30.0,
        alns_iterations: int = 400,
        ortools_time_limit: float = 1.0,
        seed: int = 0,
    ) -> None:
        if any(r.max_ride is not None for r in inst.requests):
            raise ValueError("REALTIME_RIDE_LIMITS_AS_DEADLINES")
        inst.require_core_model("REALTIME")
        self.inst = inst
        self.c = Compiled(inst)
        self.policy = policy
        self.every = reoptimize_every
        self.alns_iterations = alns_iterations
        self.ortools_time_limit = ortools_time_limit
        self.seed = seed
        self.units: list[_Unit] = [
            _Unit(t) for t, vt in enumerate(inst.vehicle_types) for _ in range(vt.count)
        ]
        self.reopt_seconds = 0.0
        self.reopt_runs = 0
        self.reopt_gain = 0.0

    # -- state of one vehicle at time tau ------------------------------------
    def _frozen(self, u: _Unit, tau: float) -> int:
        f = sum(1 for st in u.starts if st <= tau)
        if u.plan and f < len(u.plan):
            if f == 0:
                f = 1  # the vehicle left the depot when it got its first order
            elif u.starts[f - 1] + self.c.s[u.plan[f - 1]] <= tau:
                f += 1  # already driving to the next stop
        return min(f, len(u.plan))

    def _origin(self, u: _Unit, f: int, tau: float) -> tuple[int, float]:
        vt = self.inst.vehicle_types[u.t]
        if f == 0:
            return vt.start_depot, max(
                tau, vt.shift_start, self.inst.nodes[vt.start_depot].earliest
            )
        last = u.plan[f - 1]
        return last, max(tau, u.starts[f - 1] + self.c.s[last])

    def _end_by(self, u: _Unit, ready: float) -> float | None:
        cap = self.inst.vehicle_types[u.t].max_duration
        if cap is None:
            return None
        return (ready if u.left is None else u.left) + cap

    def _times(self, t: int, origin: int, ready: float, nodes: list[int]) -> list[float]:
        time_m = self.c.time[t]
        out: list[float] = []
        clock, at = ready, origin
        for node in nodes:
            clock = max(clock + time_m[at][node], self.c.e[node])
            out.append(clock)
            clock += self.c.s[node]
            at = node
        return out

    # -- one decision --------------------------------------------------------
    def _insert(self, r: int, tau: float) -> Decision:
        began = time.perf_counter()
        best: tuple[float, int, int, int] | None = None
        context: dict[int, tuple[int, int, float, list[int]]] = {}
        for k, u in enumerate(self.units):
            f = self._frozen(u, tau)
            origin, ready = self._origin(u, f, tau)
            suffix = u.plan[f:]
            st = RouteState(
                self.c,
                u.t,
                suffix,
                origin=origin,
                ready=ready,
                fresh=not u.used,
                end_by=self._end_by(u, ready),
            )
            found = best_insertion(self.c, st, r)
            if found is None:
                continue
            context[k] = (f, origin, ready, suffix)
            key = (found[0], k, found[1], found[2])
            if best is None or key < best:
                best = key
        req = self.inst.requests[r]
        if best is None:
            latency = (time.perf_counter() - began) * 1000
            return Decision(
                req.id, req.release, False, None, None, round(latency, 3), self._why_not(r, tau)
            )
        _, k, i, j = best
        u = self.units[k]
        f, origin, ready, suffix = context[k]
        new_suffix = apply_insertion(self.c, suffix, r, i, j)
        u.plan = u.plan[:f] + new_suffix
        u.starts = u.starts[:f] + self._times(u.t, origin, ready, new_suffix)
        if u.left is None:
            u.left = ready
        u.used = True
        latency = (time.perf_counter() - began) * 1000
        first = req.nodes[0]
        return Decision(
            req.id, req.release, True, k, u.starts[u.plan.index(first)], round(latency, 3)
        )

    def _why_not(self, r: int, tau: float) -> str:
        """Earliest any compatible vehicle could reach the first stop, vs its deadline."""
        req = self.inst.requests[r]
        first = req.pickup if req.pickup is not None else req.delivery
        assert first is not None
        best_arrival = math.inf
        for u in self.units:
            if u.t not in self.c.allowed[r]:
                continue
            f = self._frozen(u, tau)
            origin, ready = self._origin(u, f, tau)
            best_arrival = min(best_arrival, ready + self.c.time[u.t][origin][first])
        if not math.isfinite(best_arrival):
            return "no vehicle type can carry this order (skills or size)"
        late = best_arrival - self.c.l[first]
        if late > 0:
            return (
                f"the nearest free vehicle reaches the pickup {late:.1f} min "
                "after its window closes"
            )
        return (
            "every vehicle that could reach it in time is full "
            "or would break a promise already given"
        )

    # -- re-optimisation -----------------------------------------------------
    def snapshot(self, tau: float) -> tuple[Instance, Solution, list[tuple[int, int]]]:
        """The live state at ``tau`` as a static instance plus the current plan.

        Returns ``(instance, plan, owners)`` where ``owners[t]`` maps snapshot
        vehicle type ``t`` to ``(kind, payload)``: ``(0, unit)`` for a vehicle
        in service, ``(1, original type)`` for idle vehicles at the depot.
        """
        inst = self.inst
        n = inst.n_nodes
        frozen_nodes: set[int] = set()
        state: list[tuple[int, int, float, list[int]]] = []
        for u in self.units:
            f = self._frozen(u, tau)
            origin, ready = self._origin(u, f, tau)
            frozen_nodes.update(u.plan[:f])
            state.append((f, origin, ready, u.plan[f:]))

        def shift_over(k: int) -> bool:
            end_by = self._end_by(self.units[k], state[k][2])
            limit = self.inst.vehicle_types[self.units[k].t].shift_end
            limit = limit if end_by is None else min(limit, end_by)
            return state[k][2] > limit

        # A vehicle whose shift is over and has nothing left to do drops out.
        active = [
            k for k, u in enumerate(self.units) if u.used and (state[k][3] or not shift_over(k))
        ]
        position = {k: n + x for x, k in enumerate(active)}
        nodes = list(inst.nodes)
        for k in active:
            _, origin, ready, _ = state[k]
            src = inst.nodes[origin]
            nodes.append(Node(position[k], ready, math.inf, 0.0, src.x, src.y, f"veh{k}"))
        index = [*range(n), *(state[k][1] for k in active)]
        profiles = {
            name: Profile(
                name,
                tuple(tuple(p.time[a][b] for b in index) for a in index),
                tuple(tuple(p.distance[a][b] for b in index) for a in index),
            )
            for name, p in inst.profiles.items()
        }
        types: list[VehicleType] = []
        owners: list[tuple[int, int]] = []
        for k in active:
            u = self.units[k]
            vt = inst.vehicle_types[u.t]
            end_by = self._end_by(u, state[k][2])
            types.append(
                VehicleType(
                    id=f"veh{k}",
                    capacity=vt.capacity,
                    count=1,
                    start_depot=position[k],
                    end_depot=vt.end_depot,
                    shift_start=state[k][2],
                    shift_end=vt.shift_end if end_by is None else min(vt.shift_end, end_by),
                    fixed_cost=0.0,
                    cost_per_distance=vt.cost_per_distance,
                    cost_per_time=vt.cost_per_time,
                    skills=vt.skills | {f"lock{k}"},
                    profile=vt.profile,
                    hired=vt.hired,
                )
            )
            owners.append((0, k))
        for t, vt in enumerate(inst.vehicle_types):
            idle = sum(1 for u in self.units if u.t == t and not u.used)
            if idle:
                types.append(
                    VehicleType(
                        id=f"{vt.id}-idle",
                        capacity=vt.capacity,
                        count=idle,
                        start_depot=vt.start_depot,
                        end_depot=vt.end_depot,
                        shift_start=max(tau, vt.shift_start),
                        shift_end=vt.shift_end,
                        fixed_cost=vt.fixed_cost,
                        cost_per_distance=vt.cost_per_distance,
                        cost_per_time=vt.cost_per_time,
                        max_duration=vt.max_duration,
                        skills=vt.skills,
                        profile=vt.profile,
                        hired=vt.hired,
                    )
                )
                owners.append((1, t))
        requests: list[Request] = []
        remap: dict[int, int] = {}
        routes: list[Route] = []
        type_of_unit = {k: x for x, (kind, k) in enumerate(owners) if kind == 0}
        for k in active:
            suffix = state[k][3]
            for node in suffix:
                r = inst.request_of(node)
                if r in remap:
                    continue
                req = inst.requests[r]
                remap[r] = len(requests)
                if req.pickup is not None and req.pickup in frozen_nodes:
                    # On board (or being picked up now): a delivery locked to this vehicle.
                    requests.append(
                        Request(req.id, None, req.delivery, req.demand, req.skills | {f"lock{k}"})
                    )
                else:
                    requests.append(
                        Request(req.id, req.pickup, req.delivery, req.demand, req.skills)
                    )
            routes.append(Route(type_of_unit[k], list(suffix)))
        snap = Instance(
            name=f"{inst.name}@{tau:.0f}",
            nodes=tuple(nodes),
            requests=tuple(requests),
            vehicle_types=tuple(types),
            profiles=profiles,
            dimensions=inst.dimensions,
            source="live snapshot",
        )
        return snap, Solution([r for r in routes if r.nodes], set()), owners

    def _apply_snapshot(
        self, tau: float, snap: Instance, plan: Solution, owners: list[tuple[int, int]]
    ) -> None:
        idle_pool: dict[int, list[int]] = {}
        for k, u in enumerate(self.units):
            if not u.used:
                idle_pool.setdefault(u.t, []).append(k)
        frozen = {k: self._frozen(u, tau) for k, u in enumerate(self.units)}
        new_suffix: dict[int, list[int]] = {ref: [] for kind, ref in owners if kind == 0}
        for route in plan.routes:
            kind, ref = owners[route.vehicle_type]
            if kind == 0:
                new_suffix[ref] = list(route.nodes)
            else:
                k = idle_pool[ref].pop(0)
                new_suffix[k] = list(route.nodes)
        for k, suffix in new_suffix.items():
            u = self.units[k]
            f = frozen[k]
            origin, ready = self._origin(u, f, tau)
            u.plan = u.plan[:f] + suffix
            u.starts = u.starts[:f] + self._times(u.t, origin, ready, suffix)
            if suffix:
                u.used = True
                if u.left is None:
                    u.left = ready

    def _reoptimize(self, tau: float) -> None:
        began = time.perf_counter()
        snap, plan, owners = self.snapshot(tau)
        if not plan.routes:
            return
        before = search_objective(snap, plan)
        res = alns_solve(
            snap,
            AlnsConfig(iterations=self.alns_iterations, seed=self.seed, fleet_phase=0.0),
            initial=plan,
        )
        if res.verdict.feasible and not res.solution.unassigned and res.objective < before - 1e-9:
            self._apply_snapshot(tau, snap, res.solution, owners)
            self.reopt_gain += before - res.objective
        self.reopt_runs += 1
        self.reopt_seconds += time.perf_counter() - began

    def _ortools_insert(self, r: int, tau: float) -> Decision:
        """Re-solve the whole live state with OR-Tools for every new order."""
        from mobiroute.vrp.ortools_baseline import solve_ortools

        began = time.perf_counter()
        req = self.inst.requests[r]
        snap, _current, owners = self.snapshot(tau)
        extra = [
            *snap.requests,
            Request(req.id, req.pickup, req.delivery, req.demand, req.skills, penalty=1e6),
        ]
        snap2 = Instance(
            snap.name, snap.nodes, tuple(extra), snap.vehicle_types, snap.profiles, snap.dimensions
        )
        run = solve_ortools(snap2, time_limit=self.ortools_time_limit, max_units_per_type=None)
        latency = (time.perf_counter() - began) * 1000
        new_idx = len(extra) - 1
        if (
            run.verdict.feasible
            and new_idx not in run.solution.unassigned
            and not (run.solution.unassigned - {new_idx})
        ):
            self._apply_snapshot(tau, snap2, run.solution, owners)
            first = req.pickup if req.pickup is not None else req.delivery
            for k, u in enumerate(self.units):
                if first in u.plan:
                    return Decision(
                        req.id,
                        req.release,
                        True,
                        k,
                        u.starts[u.plan.index(first)],
                        round(latency, 3),
                    )
        return Decision(
            req.id, req.release, False, None, None, round(latency, 3), "OR-Tools dropped the order"
        )

    # -- the day -------------------------------------------------------------
    def run(self) -> RealtimeReport:
        order = sorted(
            range(self.inst.n_requests), key=lambda r: (self.inst.requests[r].release, r)
        )
        decisions: list[Decision] = []
        next_reopt = None
        for r in order:
            tau = self.inst.requests[r].release
            if self.policy == "insertion+alns":
                if next_reopt is None:
                    next_reopt = tau + self.every
                while tau >= next_reopt:
                    self._reoptimize(next_reopt)
                    next_reopt += self.every
            if self.policy == "ortools-resolve":
                decisions.append(self._ortools_insert(r, tau))
            else:
                decisions.append(self._insert(r, tau))
        return self._report(decisions)

    def _report(self, decisions: list[Decision]) -> RealtimeReport:
        inst = self.inst
        accepted = [d for d in decisions if d.accepted]
        response = [d.pickup_start - d.released for d in accepted if d.pickup_start is not None]
        rides: list[float] = []
        routes: list[Route] = []
        for u in self.units:
            if u.plan:
                routes.append(Route(u.t, list(u.plan)))
            where = {node: k for k, node in enumerate(u.plan)}
            for node in u.plan:
                req = inst.requests[inst.request_of(node)]
                if req.is_pair and node == req.pickup and req.delivery in where:
                    out = u.starts[where[node]] + self.c.s[node]
                    rides.append(u.starts[where[req.delivery]] - out)
        served = {inst.request_of(n) for r in routes for n in r.nodes}
        solution = Solution(routes, set(range(inst.n_requests)) - served)
        verdict = verify(inst, solution)
        latency = [d.latency_ms for d in decisions]
        kpi = {
            "orders": float(len(decisions)),
            "accepted": float(len(accepted)),
            "acceptance_rate": round(len(accepted) / max(1, len(decisions)), 4),
            "response_mean_min": round(statistics.fmean(response), 2) if response else 0.0,
            "response_p95_min": round(_pct(response, 0.95), 2),
            "ride_mean_min": round(statistics.fmean(rides), 2) if rides else 0.0,
            "ride_p95_min": round(_pct(rides, 0.95), 2),
            "distance": round(verdict.cost.distance, 2),
            "cost": round(verdict.cost.total, 2),
            "vehicles_used": float(verdict.cost.vehicles),
            "decision_ms_mean": round(statistics.fmean(latency), 3) if latency else 0.0,
            "decision_ms_p95": round(_pct(latency, 0.95), 3),
            "decision_ms_max": round(max(latency), 3) if latency else 0.0,
            "reoptimizations": float(self.reopt_runs),
            "reoptimize_seconds": round(self.reopt_seconds, 2),
            "reoptimize_gain": round(self.reopt_gain, 2),
        }
        return RealtimeReport(
            policy=self.policy,
            instance=inst.name,
            decisions=tuple(decisions),
            kpi=kpi,
            plans=tuple(
                (u.t, tuple(u.plan), tuple(round(x, 2) for x in u.starts))
                for u in self.units
                if u.plan
            ),
            verified=verdict.feasible,
            violations=verdict.violations[:10],
        )


def simulate(inst: Instance, policy: Policy = "insertion", **kwargs: float | int) -> RealtimeReport:
    return Dispatcher(inst, policy=policy, **kwargs).run()  # type: ignore[arg-type]
