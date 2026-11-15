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
policy is measured. OR-Tools has no driving-time break, so that policy
refuses a day with a rest rule.

Driver rests
------------
A vehicle type with a rest rule (4.5 h of driving, then a 45-minute break or
15 + 30 minutes) keeps its driver's state through the day. The part of a
route already driven fixes how long the driver has been at the wheel and
whether the break, or its first part, is behind them; an order is inserted
only where the rest of the route still has a legal place for the break, and
the plan carries the break with its start. A break once started is never
moved. ALNS re-optimisation sees the open stops from the current position
with that driving already on the counter (Lemma 1c), so a suffix that would
only be legal for a fresh driver is not a candidate. A proposal is kept only
when the independent verifier accepts the whole day and the verified cost
falls; a break already begun stays where it is.

KPIs: acceptance, time from call to pickup (vehicle arrival lead time), ride
time, distance and the part of it driven empty, vehicles used, decision
latency, orders no vehicle type can carry and breaks planned.
"""

from __future__ import annotations

import itertools
import math
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from mobiroute.vrp.alns import AlnsConfig, search_objective
from mobiroute.vrp.alns import solve as alns_solve
from mobiroute.vrp.insertion import (
    EPS,
    Compiled,
    RouteState,
    apply_insertion,
    best_insertion,
    route_loads,
)
from mobiroute.vrp.model import BreakRule, Instance, Node, Profile, Request, VehicleType
from mobiroute.vrp.sheets import LOADED_EPS
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


@dataclass(frozen=True, slots=True)
class Rest:
    """A driver's break planned on a route."""

    #: The break comes before ``plan[gap]`` (``gap == len(plan)``: before the return).
    gap: int
    start: float
    minutes: float
    #: Driving since the start of the shift when the break begins.
    driven: float
    #: ``True`` for the whole break or the last part of a split one: the
    #: count of driving starts again after it.
    final: bool


@dataclass(frozen=True, slots=True)
class _Placement:
    """Service starts of a route suffix and the breaks that make it legal."""

    starts: tuple[float, ...]
    rests: tuple[tuple[int, float, float, float, bool], ...]  # arc, start, minutes, driven, final


@dataclass(slots=True)
class _Unit:
    t: int
    plan: list[int] = field(default_factory=list)
    starts: list[float] = field(default_factory=list)
    used: bool = False
    #: When the vehicle left the depot; its shift cap runs from here.
    left: float | None = None
    rests: list[Rest] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RealtimeReport:
    policy: str
    instance: str
    decisions: tuple[Decision, ...]
    kpi: dict[str, float]
    plans: tuple[tuple[int, tuple[int, ...], tuple[float, ...]], ...]
    verified: bool
    violations: tuple[str, ...]
    #: Breaks on the routes: ``(unit, before plan[gap], start, minutes, final)``.
    rests: tuple[tuple[int, int, float, float, bool], ...] = ()


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
        if inst.has_reloads:
            raise ValueError("REALTIME_MULTI_TRIP_UNSUPPORTED")
        if inst.has_traffic:
            raise ValueError("REALTIME_TIME_DEPENDENT_TRAVEL_UNSUPPORTED")
        if inst.has_rest_rules and policy == "ortools-resolve":
            # OR-Tools Routing has no driving-time break. Applying its routes
            # would drop the breaks already planned.
            raise ValueError("REALTIME_ORTOLS_HAS_NO_BREAK_RULE")
        self.inst = inst
        self.c = Compiled(inst)
        self.policy = policy
        self.every = reoptimize_every
        self.alns_iterations = alns_iterations
        self.ortools_time_limit = ortools_time_limit
        self.seed = seed
        # A day never uses more vehicles than it has orders.
        cap = max(1, inst.n_requests)
        self.units: list[_Unit] = [
            _Unit(t) for t, vt in enumerate(inst.vehicle_types) for _ in range(min(vt.count, cap))
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

    # -- driver rests ----------------------------------------------------------
    def _resting(self, t: int) -> bool:
        return self.c.brk_drive[t] < math.inf

    @staticmethod
    def _behind(u: _Unit, f: int, tau: float) -> list[Rest]:
        """Breaks the driver has taken or begun by ``tau``: never moved again."""
        return [rest for rest in u.rests if rest.gap < f or rest.start <= tau]

    def _state(self, u: _Unit, tau: float) -> tuple[int, int, float]:
        """``(frozen stops, origin, ready)``; a break under way delays ``ready``."""
        f = self._frozen(u, tau)
        origin, ready = self._origin(u, f, tau)
        for rest in self._behind(u, f, tau):
            if rest.gap >= f:
                ready = max(ready, rest.start + rest.minutes)
        return f, origin, ready

    def _driver(self, u: _Unit, f: int, tau: float) -> tuple[float, bool, bool]:
        """``(driving, rested, first_part_taken)`` once ``plan[:f]`` is driven.

        ``driving`` counts from the start of the shift, or from the end of the
        break when the break (or its last part) is behind the driver.
        """
        time = self.c.time[u.t]
        at = self.c.start[u.t]
        driving = 0.0
        for node in u.plan[:f]:
            driving += time[at][node]
            at = node
        behind = self._behind(u, f, tau)
        finals = [rest.driven for rest in behind if rest.final]
        if finals:
            return driving - max(finals), True, True
        return driving, False, any(not rest.final for rest in behind)

    def _residual_rule(
        self, u: _Unit, f: int, tau: float, vt: VehicleType
    ) -> tuple[BreakRule | None, float, bool]:
        """Break rule of a snapshot vehicle, with the driving already counted.

        The offset is ``R`` after a final break and ``Φ`` otherwise: the
        partial sum at which a scan of the open suffix starts (Lemma 1c).
        A first part already taken leaves only the second part to place.
        The counter has not reset, and that part is no longer an open gap.
        """
        rule = vt.breaks
        if rule is None:
            return None, 0.0, False
        driving, rested, first_taken = self._driver(u, f, tau)
        if rested:
            return rule, driving, True
        if first_taken and rule.split is not None:
            return BreakRule(rule.max_driving, rule.split[1]), driving, False
        return rule, driving, False

    def _run(
        self,
        t: int,
        seq: list[int],
        ready: float,
        end_by: float | None,
        breaks: dict[int, tuple[float, bool]],
    ) -> tuple[list[float], dict[int, float]] | None:
        """Earliest service starts along ``seq`` from ``ready``, with breaks on arcs.

        ``breaks[k] = (minutes, before)`` puts a break on the arc from
        ``seq[k]`` to ``seq[k + 1]``, before or after its drive. Service at
        ``seq[0]`` is over at ``ready``. Returns the starts of ``seq[1:-1]``
        and the start of each break, or ``None`` if a window or the shift
        end is missed.
        """
        c = self.c
        time = c.time[t]
        e, lat, s = c.e, c.l, c.s
        last = len(seq) - 1
        clock = ready
        starts: list[float] = []
        rest_at: dict[int, float] = {}
        for k in range(1, len(seq)):
            a, b = seq[k - 1], seq[k]
            minutes, before = breaks.get(k - 1, (0.0, False))
            if minutes and before:
                rest_at[k - 1] = clock
                clock += minutes
            clock += time[a][b]
            if minutes and not before:
                rest_at[k - 1] = clock
                clock += minutes
            begin = max(clock, e[b])
            if k == last:
                limit = c.end_lim[t] if end_by is None else min(c.end_lim[t], end_by)
            else:
                limit = lat[b]
            if begin > limit + EPS:
                return None
            if k < last:
                starts.append(begin)
            clock = begin + s[b]
        return starts, rest_at

    def _place(
        self,
        u: _Unit,
        f: int,
        tau: float,
        origin: int,
        ready: float,
        nodes: list[int],
        end_by: float | None,
    ) -> _Placement | None:
        """Schedule of ``nodes`` after ``origin`` with a legal break, or ``None``.

        The same rule as :func:`mobiroute.vrp.insertion.route_exact`, carried
        over the part already driven: one break per shift, at most ``D``
        minutes of driving on each side of it, the 4.5 h count restarting
        only after the whole break or its last part. Among the admissible
        gaps the earliest that keeps every window wins, as in the static
        search; inside a gap the later side of the drive is preferred, since
        it leaves more driving after the break.
        """
        c, t = self.c, u.t
        seq = [origin, *nodes, c.end[t]]
        limit = c.brk_drive[t]
        driving, rested, first_taken = self._driver(u, f, tau)
        time = c.time[t]
        legs = [time[seq[k]][seq[k + 1]] for k in range(len(seq) - 1)]
        total = driving + math.fsum(legs)
        split = c.brk_split[t]
        if rested or total <= limit + EPS:
            if total > limit + EPS:
                return None
            run = self._run(t, seq, ready, end_by, {})
            if run is None:
                return None
            ahead: tuple[tuple[int, float, float, float, bool], ...] = ()
            if split is not None and not rested and not first_taken:
                ahead = self._first_part_in_a_wait(t, seq, ready, run[0], driving, split[0])
            return _Placement(tuple(run[0]), ahead)
        if total > 2.0 * limit + EPS:
            return None
        low, high = total - limit - EPS, limit + EPS
        places: list[tuple[int, float, bool]] = []  # arc, driving at the break, before the drive
        done = driving
        for k, leg in enumerate(legs):
            after = done + leg
            if low <= after <= high:
                places.append((k, after, False))
            elif low <= done <= high:
                places.append((k, done, True))
            done = after
        last = split[1] if split is not None and first_taken else c.brk_len[t]
        for k, at_break, before in places:
            run = self._run(t, seq, ready, end_by, {k: (last, before)})
            if run is not None:
                return _Placement(tuple(run[0]), ((k, run[1][k], last, at_break, True),))
        if split is None or first_taken:
            return None
        for k, at_break, before in places:
            for j in range(k):
                parts = {j: (split[0], False), k: (split[1], before)}
                run = self._run(t, seq, ready, end_by, parts)
                if run is not None:
                    first_at = driving + math.fsum(legs[: j + 1])
                    both = (
                        (j, run[1][j], split[0], first_at, False),
                        (k, run[1][k], split[1], at_break, True),
                    )
                    return _Placement(tuple(run[0]), both)
        return None

    def _first_part_in_a_wait(
        self,
        t: int,
        seq: list[int],
        ready: float,
        starts: list[float],
        driving: float,
        minutes: float,
    ) -> tuple[tuple[int, float, float, float, bool], ...]:
        """The first part of a split break, in the first wait long enough for it.

        A vehicle that stands for ``minutes`` anyway, waiting for a window,
        gives its driver the first 15 minutes of the break at no cost; the
        route sheet shows them as a break, set before the wait comes, never
        counted after it. The day then needs only the last 30 minutes later.
        """
        c = self.c
        time = c.time[t]
        depart = ready
        for k, begin in enumerate(starts):
            arrive = depart + time[seq[k]][seq[k + 1]]
            driving += time[seq[k]][seq[k + 1]]
            if begin - arrive >= minutes - EPS:
                return ((k, arrive, minutes, driving, False),)
            depart = begin + c.s[seq[k + 1]]
        return ()

    def _rest_check(
        self, u: _Unit, f: int, tau: float, origin: int, ready: float, end_by: float | None
    ) -> Callable[[list[int]], bool]:
        def check(nodes: list[int]) -> bool:
            return self._place(u, f, tau, origin, ready, nodes, end_by) is not None

        return check

    # -- one decision --------------------------------------------------------
    def _insert(self, r: int, tau: float) -> Decision:
        began = time.perf_counter()
        best: tuple[float, int, int, int] | None = None
        context: dict[int, tuple[int, int, float, list[int], float | None]] = {}
        for k, u in enumerate(self.units):
            f, origin, ready = self._state(u, tau)
            suffix = u.plan[f:]
            end_by = self._end_by(u, ready)
            # RouteState adds the service time of its first stop; ``ready`` is
            # when that service is already over, so it gets the service start.
            st = RouteState(
                self.c,
                u.t,
                suffix,
                origin=origin,
                ready=ready - self.c.s[origin],
                fresh=not u.used,
                end_by=end_by,
            )
            if self._resting(u.t):
                driving, rested, _ = self._driver(u, f, tau)
                allowance = self.c.brk_drive[u.t] * (1.0 if rested else 2.0)
                found = best_insertion(
                    self.c,
                    st,
                    r,
                    exact=self._rest_check(u, f, tau, origin, ready, end_by),
                    drive_room=allowance - driving - st.drive,
                )
            else:
                found = best_insertion(self.c, st, r)
            if found is None:
                continue
            context[k] = (f, origin, ready, suffix, end_by)
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
        f, origin, ready, suffix, end_by = context[k]
        new_suffix = apply_insertion(self.c, suffix, r, i, j)
        u.plan = u.plan[:f] + new_suffix
        if self._resting(u.t):
            placed = self._place(u, f, tau, origin, ready, new_suffix, end_by)
            assert placed is not None  # the exact check accepted this candidate
            u.starts = u.starts[:f] + list(placed.starts)
            u.rests = self._behind(u, f, tau) + [
                Rest(f + arc, start, minutes, driven, final)
                for arc, start, minutes, driven, final in placed.rests
            ]
        else:
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
            _, origin, ready = self._state(u, tau)
            best_arrival = min(best_arrival, ready + self.c.time[u.t][origin][first])
        if not math.isfinite(best_arrival):
            return "no vehicle type can carry this order (skills or size)"
        late = best_arrival - self.c.l[first]
        if late > 0:
            return (
                f"the nearest free vehicle reaches the pickup {late:.1f} min "
                "after its window closes"
            )
        if any(self._resting(u.t) for u in self.units if u.t in self.c.allowed[r]):
            return (
                "every vehicle that could reach it in time is full, would break a "
                "promise already given or has no legal place left for the driver's break"
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
            rule, prior, taken = self._residual_rule(u, state[k][0], tau, vt)
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
                    breaks=rule,
                    prior_driving=prior,
                    break_taken=taken,
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
                        breaks=vt.breaks,
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

    def _suffixes(self, plan: Solution, owners: list[tuple[int, int]]) -> dict[int, list[int]]:
        """Open stops per unit in a snapshot plan. Idle units are taken in order."""
        idle_pool: dict[int, list[int]] = {}
        for k, u in enumerate(self.units):
            if not u.used:
                idle_pool.setdefault(u.t, []).append(k)
        new_suffix: dict[int, list[int]] = {ref: [] for kind, ref in owners if kind == 0}
        for route in plan.routes:
            kind, ref = owners[route.vehicle_type]
            if kind == 0:
                new_suffix[ref] = list(route.nodes)
            else:
                new_suffix[idle_pool[ref].pop(0)] = list(route.nodes)
        return new_suffix

    def _live_cost(self) -> float | None:
        """Verified money cost of the current routes, or ``None`` if one breaks a rule."""
        routes = [Route(u.t, list(u.plan)) for u in self.units if u.plan]
        served = {self.inst.request_of(n) for route in routes for n in route.nodes}
        verdict = verify(self.inst, Solution(routes, set(range(self.inst.n_requests)) - served))
        if not verdict.feasible:
            return None
        return verdict.cost.total

    def _remember(self) -> list[tuple[list[int], list[float], list[Rest], bool, float | None]]:
        return [(u.plan.copy(), u.starts.copy(), list(u.rests), u.used, u.left) for u in self.units]

    def _recall(
        self, saved: list[tuple[list[int], list[float], list[Rest], bool, float | None]]
    ) -> None:
        for u, (plan, starts, rests, used, left) in zip(self.units, saved, strict=True):
            u.plan, u.starts, u.rests, u.used, u.left = plan, starts, rests, used, left

    def _apply_if_breaks_hold(
        self, tau: float, plan: Solution, owners: list[tuple[int, int]]
    ) -> bool:
        """Keep ``plan`` only when Lemma 1c holds and the verified cost falls.

        The snapshot already times the open stops with the driving done so
        far. ``_place`` repeats that test on the original day, and the
        verifier prices it. A rejected proposal is not applied. A break that
        has started is not an open gap, so it stays.
        """
        before = self._live_cost()
        if before is None:
            return False
        new_suffix = self._suffixes(plan, owners)
        prepared: list[tuple[int, int, list[int], _Placement | None, float]] = []
        for k, suffix in new_suffix.items():
            u = self.units[k]
            f, origin, ready = self._state(u, tau)
            if self._resting(u.t):
                placed = self._place(u, f, tau, origin, ready, suffix, self._end_by(u, ready))
                if placed is None:
                    return False
            else:
                placed = None
            prepared.append((k, f, suffix, placed, ready))
        saved = self._remember()
        for k, f, suffix, placed, ready in prepared:
            u = self.units[k]
            u.plan = u.plan[:f] + suffix
            if placed is None:
                origin, _ = self._origin(u, f, tau)
                u.starts = u.starts[:f] + self._times(u.t, origin, ready, suffix)
            else:
                u.starts = u.starts[:f] + list(placed.starts)
                u.rests = self._behind(u, f, tau) + [
                    Rest(f + arc, start, minutes, driven, final)
                    for arc, start, minutes, driven, final in placed.rests
                ]
            if suffix:
                u.used = True
                if u.left is None:
                    u.left = ready
        after = self._live_cost()
        if after is None or after > before - 1e-6:
            self._recall(saved)
            return False
        self.reopt_gain += before - after
        return True

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
            if self.inst.has_rest_rules:
                # The snapshot already carries the residual driving. The
                # original day is checked again, and only a cheaper verified
                # plan replaces the one the vehicles are driving.
                self._apply_if_breaks_hold(tau, res.solution, owners)
            else:
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
        fleet = {u.t for u in self.units}
        uncarriable = sum(1 for r in range(inst.n_requests) if not set(self.c.allowed[r]) & fleet)
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
        # Empty running: legs with nothing on board (from a drop to the next pickup).
        empty_km = 0.0
        for route in routes:
            vt = inst.vehicle_types[route.vehicle_type]
            dist = inst.profiles[vt.profile].distance
            seq = [vt.start_depot, *route.nodes, vt.end_depot]
            loads = route_loads(self.c, route.nodes)
            empty_km += math.fsum(
                dist[a][b]
                for k, (a, b) in enumerate(itertools.pairwise(seq))
                if not any(q > LOADED_EPS for q in loads[k])
            )
        total_km = verdict.cost.distance
        kpi = {
            "orders": float(len(decisions)),
            "accepted": float(len(accepted)),
            "acceptance_rate": round(len(accepted) / max(1, len(decisions)), 4),
            "response_mean_min": round(statistics.fmean(response), 2) if response else 0.0,
            "response_p95_min": round(_pct(response, 0.95), 2),
            "ride_mean_min": round(statistics.fmean(rides), 2) if rides else 0.0,
            "ride_p95_min": round(_pct(rides, 0.95), 2),
            "distance": round(total_km, 2),
            "empty_km": round(empty_km, 2),
            "mileage_utilisation": round(1.0 - empty_km / total_km, 4) if total_km > 0 else 0.0,
            "cost": round(verdict.cost.total, 2),
            "vehicles_used": float(verdict.cost.vehicles),
            "decision_ms_mean": round(statistics.fmean(latency), 3) if latency else 0.0,
            "decision_ms_p95": round(_pct(latency, 0.95), 3),
            "decision_ms_max": round(max(latency), 3) if latency else 0.0,
            "reoptimizations": float(self.reopt_runs),
            "reoptimize_seconds": round(self.reopt_seconds, 2),
            "reoptimize_gain": round(self.reopt_gain, 2),
            # Orders no vehicle type of the fleet can take (skills or size):
            # refused whatever the policy, so acceptance is also given
            # against the orders the fleet could carry at all.
            "uncarriable": float(uncarriable),
            "acceptance_of_carriable": (
                round(len(accepted) / (len(decisions) - uncarriable), 4)
                if len(decisions) > uncarriable
                else 0.0
            ),
            "breaks": float(sum(1 for u in self.units for rest in u.rests if rest.final)),
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
            rests=tuple(
                (k, rest.gap, round(rest.start, 2), rest.minutes, rest.final)
                for k, u in enumerate(self.units)
                for rest in u.rests
            ),
        )


def simulate(inst: Instance, policy: Policy = "insertion", **kwargs: float | int) -> RealtimeReport:
    return Dispatcher(inst, policy=policy, **kwargs).run()  # type: ignore[arg-type]
