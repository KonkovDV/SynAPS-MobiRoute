"""Literature-exact Cordeau (2006) DARP lane.

The operator kernel adapts open data to a Moscow-shaped algebra (integer
minutes, 5-minute curb wait, alighting up to 30 minutes before an appointment).
Its numbers are therefore never comparable with the literature. This module is
the comparable lane, and nothing else:

* the published algebra of Cordeau (2006): Euclidean distances are travel
  times, the published service times, hard time windows at both ends, maximum
  ride time ``L`` (end of pickup service to start of dropoff service), route
  duration ``T``, capacity ``Q``, at most ``K`` routes, routing-cost objective;
* :func:`solve_exact_cpsat`, an exact CP-SAT model with conservative integer
  travel times (``ceil`` on a fixed-point grid), so every model solution is
  also feasible with real-valued travel;
* :func:`verify_routes`, an independent verifier that never trusts the solver:
  for a fixed stop sequence the timing constraints are a system of difference
  constraints, which is feasible iff its constraint graph has no negative cycle
  (Bellman-Ford). An infeasible route returns the cycle as a certificate.

A published gap needs a verified full-service plan and the exact vendored
instance bytes; see :func:`build_literature_report`.
"""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise
from typing import Any

from mobiroute.domain.models import StrictModel

# Instance bytes this repository vendors (CRLF kept by .gitattributes `-text`).
CORDEAU_A2_16_SHA256 = "d25ab2609ad09a3ccbd533dbe8418e1ca6b65140114389d31aa8d6c111c0aa79"


@dataclass(frozen=True, slots=True)
class PublishedReference:
    """A published objective tied to exact instance bytes, not to a file name."""

    instance_id: str
    objective: float
    decimals: int
    source: str


REFERENCES: dict[str, PublishedReference] = {
    CORDEAU_A2_16_SHA256: PublishedReference(
        instance_id="a2-16",
        objective=294.25,
        decimals=2,
        source=(
            "Cordeau (2006), Operations Research 54(3):573-586, proven optimum; "
            "tabulated in Ho et al. (2018), Transp. Res. Part B 111:395-421"
        ),
    ),
}


@dataclass(frozen=True, slots=True)
class CordeauNode:
    node_id: int
    x: float
    y: float
    service: int
    load: int
    earliest: int
    latest: int


@dataclass(frozen=True, slots=True)
class CordeauInstance:
    """Header ``K n T Q L`` and ``2n+2`` nodes: depot, pickups, dropoffs, end depot."""

    instance_id: str
    n_vehicles: int
    n_requests: int
    max_route_duration: int
    capacity: int
    max_ride_time: int
    nodes: tuple[CordeauNode, ...]

    @property
    def end_depot(self) -> int:
        return 2 * self.n_requests + 1

    def distance(self, i: int, j: int) -> float:
        a, b = self.nodes[i], self.nodes[j]
        return math.hypot(a.x - b.x, a.y - b.y)


def parse_cordeau_instance(text: str, *, instance_id: str) -> CordeauInstance:
    """Strict parser: malformed files fail with a code instead of a silent guess."""
    lines = [ln.split() for ln in text.splitlines() if ln.strip()]
    if not lines or len(lines[0]) != 5:
        raise ValueError("CORDEAU_HEADER_MUST_BE_K_N_T_Q_L")
    k, n, t_max, cap, ride = (int(tok) for tok in lines[0])
    if k < 1 or n < 0 or t_max < 0 or cap < 1 or ride < 0:
        raise ValueError("CORDEAU_HEADER_OUT_OF_RANGE")
    rows = lines[1:]
    if len(rows) != 2 * n + 2:
        raise ValueError("CORDEAU_EXPECTED_2N_PLUS_2_NODES")
    nodes: list[CordeauNode] = []
    for idx, parts in enumerate(rows):
        if len(parts) != 7:
            raise ValueError("CORDEAU_NODE_LINE_MUST_HAVE_7_FIELDS")
        node = CordeauNode(
            node_id=int(parts[0]),
            x=float(parts[1]),
            y=float(parts[2]),
            service=int(parts[3]),
            load=int(parts[4]),
            earliest=int(parts[5]),
            latest=int(parts[6]),
        )
        if node.node_id != idx:
            raise ValueError("CORDEAU_NODE_IDS_MUST_BE_SEQUENTIAL")
        if not (math.isfinite(node.x) and math.isfinite(node.y)):
            raise ValueError("CORDEAU_COORDINATES_MUST_BE_FINITE")
        if node.service < 0 or node.earliest > node.latest:
            raise ValueError("CORDEAU_SERVICE_OR_WINDOW_INVALID")
        nodes.append(node)
    for i in range(1, n + 1):
        if nodes[i].load <= 0 or nodes[i + n].load != -nodes[i].load:
            raise ValueError("CORDEAU_PICKUP_DROPOFF_LOADS_MUST_PAIR")
        if nodes[i].load > cap:
            raise ValueError("CORDEAU_REQUEST_EXCEEDS_CAPACITY")
    return CordeauInstance(
        instance_id=instance_id,
        n_vehicles=k,
        n_requests=n,
        max_route_duration=t_max,
        capacity=cap,
        max_ride_time=ride,
        nodes=tuple(nodes),
    )


def load_cordeau_bytes(raw: bytes, *, instance_id: str) -> tuple[CordeauInstance, str]:
    """Parse and fingerprint the same bytes, so the stamp names what was solved."""
    return parse_cordeau_instance(raw.decode("utf-8"), instance_id=instance_id), hashlib.sha256(
        raw
    ).hexdigest()


class RouteSchedule(StrictModel):
    """Earliest feasible service start per stop, depots included."""

    sequence: list[int]
    service_start: list[float]
    cost: float
    duration: float


class ExactVerdict(StrictModel):
    feasible: bool
    violations: list[str]
    cost: float
    requests_total: int
    served_requests: list[int]
    full_service: bool
    routes: list[RouteSchedule]
    ride_times: dict[int, float]
    alight_slack: int


@dataclass(frozen=True, slots=True)
class _Edge:
    tail: int
    head: int
    weight: float
    label: str


def _route_constraints(
    instance: CordeauInstance, seq: list[int], alight_slack: int
) -> tuple[int, list[_Edge]]:
    """Edges ``tail -> head`` meaning ``B[head] - B[tail] <= weight``."""
    n = instance.n_requests
    m = len(seq)
    z = m  # the zero clock
    edges: list[_Edge] = []
    pos = {node: k for k, node in enumerate(seq)}
    for k, node in enumerate(seq):
        info = instance.nodes[node]
        earliest = info.earliest
        if alight_slack and n < node <= 2 * n:
            earliest = max(0, earliest - alight_slack)
        edges.append(_Edge(z, k, float(info.latest), f"LATEST:{node}"))
        edges.append(_Edge(k, z, -float(earliest), f"EARLIEST:{node}"))
    for k in range(m - 1):
        a, b = seq[k], seq[k + 1]
        gap = instance.nodes[a].service + instance.distance(a, b)
        edges.append(_Edge(k + 1, k, -gap, f"TRAVEL:{a}->{b}"))
    for k, node in enumerate(seq):
        if 1 <= node <= n and node + n in pos:
            cap = float(instance.max_ride_time + instance.nodes[node].service)
            edges.append(_Edge(k, pos[node + n], cap, f"RIDE:{node}"))
    edges.append(_Edge(0, m - 1, float(instance.max_route_duration), "DURATION"))
    return z, edges


def _earliest_schedule(
    n_vertices: int, z: int, edges: list[_Edge], eps: float
) -> tuple[list[float] | None, list[str]]:
    """Earliest solution ``B[k] = -dist(k, z)`` or a negative-cycle certificate.

    Bellman-Ford runs on the reversed graph from ``z``; a constraint system of
    differences is feasible iff the graph has no negative cycle (CLRS 24.4).
    """
    dist = [math.inf] * n_vertices
    pred: list[_Edge | None] = [None] * n_vertices
    dist[z] = 0.0
    for _ in range(n_vertices - 1):
        changed = False
        for e in edges:
            # reversed edge: head -> tail with the same weight
            if dist[e.head] + e.weight < dist[e.tail] - 1e-12:
                dist[e.tail] = dist[e.head] + e.weight
                pred[e.tail] = e
                changed = True
        if not changed:
            break
    culprit = next((e for e in edges if dist[e.head] + e.weight < dist[e.tail] - eps), None)
    if culprit is None:
        return [-value for value in dist], []
    # Walk predecessors long enough to land inside the cycle, then collect it.
    dist[culprit.tail] = dist[culprit.head] + culprit.weight
    pred[culprit.tail] = culprit
    vertex = culprit.tail
    for _ in range(n_vertices):
        step = pred[vertex]
        if step is None:
            break
        vertex = step.head
    labels: list[str] = []
    start = vertex
    for _ in range(n_vertices + 1):
        step = pred[vertex]
        if step is None:
            break
        labels.append(step.label)
        vertex = step.head
        if vertex == start:
            break
    return None, sorted(set(labels))


def verify_routes(
    instance: CordeauInstance,
    routes: Sequence[Sequence[int]],
    *,
    alight_slack: int = 0,
    eps: float = 1e-6,
) -> ExactVerdict:
    """Independent literature-algebra notary for a fixed route set.

    ``routes`` lists service node ids per vehicle, depots excluded. A nonzero
    ``alight_slack`` opens dropoff windows that many minutes early; it exists
    to diagnose operator-algebra plans and never yields a literature verdict.
    """
    n = instance.n_requests
    violations: list[str] = []
    non_empty = [list(route) for route in routes if route]
    if len(non_empty) > instance.n_vehicles:
        violations.append("TOO_MANY_ROUTES")
    owner: dict[int, int] = {}
    for r, route in enumerate(non_empty):
        for node in route:
            if not 1 <= node <= 2 * n:
                violations.append(f"NOT_A_SERVICE_NODE:{node}")
            elif node in owner:
                violations.append(f"DUPLICATE_VISIT:{node}")
            else:
                owner[node] = r
    served: list[int] = []
    for i in range(1, n + 1):
        has_pick, has_drop = i in owner, i + n in owner
        if not has_pick and not has_drop:
            continue
        if has_pick != has_drop:
            violations.append(f"UNPAIRED_REQUEST:{i}")
        elif owner[i] != owner[i + n]:
            violations.append(f"SPLIT_REQUEST:{i}")
        else:
            served.append(i)
    schedules: list[RouteSchedule] = []
    rides: dict[int, float] = {}
    total = 0.0
    for r, route in enumerate(non_empty):
        if any(not 1 <= node <= 2 * n for node in route):
            continue  # already reported; an unknown node has no cost or clock
        seq = [0, *route, instance.end_depot]
        cost = sum(instance.distance(a, b) for a, b in pairwise(seq))
        total += cost
        load = 0
        pos = {node: k for k, node in enumerate(seq)}
        for node in route:
            load += instance.nodes[node].load
            if load > instance.capacity:
                violations.append(f"CAPACITY:{r}:{node}")
            if load < 0:
                violations.append(f"NEGATIVE_LOAD:{r}:{node}")
            if node <= n and node + n in pos and pos[node + n] < pos[node]:
                violations.append(f"DROPOFF_BEFORE_PICKUP:{node}")
        z, edges = _route_constraints(instance, seq, alight_slack)
        times, certificate = _earliest_schedule(len(seq) + 1, z, edges, eps)
        if times is None:
            violations.append(f"SCHEDULE_INFEASIBLE:{r}:{'|'.join(certificate)}")
            continue
        starts = times[: len(seq)]
        for node in route:
            if node <= n and node + n in pos:
                ride = starts[pos[node + n]] - starts[pos[node]] - instance.nodes[node].service
                rides[node] = round(ride, 6)
        schedules.append(
            RouteSchedule(
                sequence=seq,
                service_start=[round(value, 6) for value in starts],
                cost=round(cost, 6),
                duration=round(starts[-1] - starts[0], 6),
            )
        )
    full = len(served) == n and not violations
    return ExactVerdict(
        feasible=not violations,
        violations=violations,
        cost=round(total, 6),
        requests_total=n,
        served_requests=sorted(served),
        full_service=full,
        routes=schedules,
        ride_times=rides,
        alight_slack=alight_slack,
    )


class ExactSolveResult(StrictModel):
    solver: str
    status: str
    routes: list[list[int]]
    model_objective: float | None
    model_bound: float | None
    scale: int
    time_limit_s: float
    workers: int
    wall_clock_seconds: float
    arcs: int
    ortools_version: str


def solve_exact_cpsat(
    instance: CordeauInstance,
    *,
    time_limit_s: float = 60.0,
    workers: int = 1,
    scale: int = 1000,
) -> ExactSolveResult:
    """Exact DARP model (Cordeau 2006 algebra) on a fixed-point time grid.

    Travel times are rounded **up** on the ``1/scale`` grid, so every model
    solution is feasible with real-valued travel; arc costs are rounded to the
    nearest grid unit for the objective. ``OPTIMAL`` therefore means optimal for
    this conservative integer model; :func:`verify_routes` recomputes the
    real-valued cost. Route duration must be implied by the depot window.
    """
    import ortools
    from ortools.sat.python import cp_model

    n = instance.n_requests
    end = instance.end_depot
    nodes = instance.nodes
    if instance.max_route_duration < nodes[end].latest - nodes[0].earliest:
        raise ValueError("ROUTE_DURATION_NOT_IMPLIED_BY_DEPOT_WINDOW")
    if scale < 1 or workers < 1 or time_limit_s <= 0:
        raise ValueError("SOLVER_PARAMETERS_OUT_OF_RANGE")

    def target(j: int) -> int:
        return end if j == 0 else j

    def travel_up(i: int, j: int) -> int:
        return math.ceil(instance.distance(i, target(j)) * scale - 1e-9)

    def arc_cost(i: int, j: int) -> int:
        return round(instance.distance(i, target(j)) * scale)

    model: Any = cp_model.CpModel()
    service = range(1, 2 * n + 1)
    start: dict[int, Any] = {
        i: model.new_int_var(nodes[i].earliest * scale, nodes[i].latest * scale, f"b{i}")
        for i in service
    }
    route_of: dict[int, Any] = {i: model.new_int_var(1, 2 * n, f"r{i}") for i in service}
    load: dict[int, Any] = {
        i: model.new_int_var(max(0, nodes[i].load), instance.capacity, f"q{i}") for i in service
    }

    def arc_allowed(i: int, j: int) -> bool:
        if i == j:
            return False
        if i == 0:
            return 1 <= j <= n  # a route starts with a pickup
        if j == 0:
            return i > n  # and ends with a dropoff
        if i > n and j == i - n:
            return False  # own dropoff before own pickup
        if 1 <= i <= n and 1 <= j <= n and nodes[i].load + nodes[j].load > instance.capacity:
            return False
        ready = (nodes[i].earliest + nodes[i].service) * scale + travel_up(i, j)
        return ready <= nodes[j].latest * scale

    arcs: list[tuple[int, int, Any]] = []
    lits: dict[tuple[int, int], Any] = {}
    for i in range(0, 2 * n + 1):
        for j in range(0, 2 * n + 1):
            if arc_allowed(i, j):
                lit = model.new_bool_var(f"x{i}_{j}")
                lits[(i, j)] = lit
                arcs.append((i, j, lit))
    if n > 0:
        model.add_multiple_circuit(arcs)
        model.add(sum(lits[(0, j)] for j in service if (0, j) in lits) <= instance.n_vehicles)
    for (i, j), lit in lits.items():
        if i == 0:
            depart = (nodes[0].earliest + nodes[0].service) * scale
            model.add(start[j] >= depart + travel_up(0, j)).only_enforce_if(lit)
            model.add(route_of[j] == j).only_enforce_if(lit)
            model.add(load[j] == nodes[j].load).only_enforce_if(lit)
        elif j == 0:
            back = nodes[i].service * scale + travel_up(i, 0)
            model.add(start[i] + back <= nodes[end].latest * scale).only_enforce_if(lit)
        else:
            gap = nodes[i].service * scale + travel_up(i, j)
            model.add(start[j] >= start[i] + gap).only_enforce_if(lit)
            model.add(route_of[j] == route_of[i]).only_enforce_if(lit)
            model.add(load[j] == load[i] + nodes[j].load).only_enforce_if(lit)
    for i in range(1, n + 1):
        model.add(route_of[i] == route_of[i + n])
        model.add(start[i + n] >= start[i] + nodes[i].service * scale + travel_up(i, i + n))
        model.add(
            start[i + n] - start[i] - nodes[i].service * scale <= instance.max_ride_time * scale
        )
    model.minimize(sum(lit * arc_cost(i, j) for (i, j), lit in lits.items()))

    solver: Any = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_s)
    solver.parameters.num_workers = int(workers)
    solver.parameters.random_seed = 0
    began = time.perf_counter()
    status = solver.solve(model)
    elapsed = time.perf_counter() - began
    name = str(solver.status_name(status))
    routes: list[list[int]] = []
    objective: float | None = None
    bound: float | None = None
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        objective = float(solver.objective_value) / scale
        bound = float(solver.best_objective_bound) / scale
        chosen = [(i, j) for (i, j), lit in lits.items() if solver.value(lit)]
        # The depot has one outgoing arc per route; every other node has one.
        firsts = sorted(j for i, j in chosen if i == 0)
        succ = {i: j for i, j in chosen if i != 0}
        for first in firsts:
            route = [first]
            node = first
            while succ.get(node, 0) != 0 and len(route) <= 2 * n:
                node = succ[node]
                route.append(node)
            routes.append(route)
    return ExactSolveResult(
        solver="EXACT_CPSAT_CORDEAU",
        status=name,
        routes=routes,
        model_objective=objective,
        model_bound=bound,
        scale=scale,
        time_limit_s=float(time_limit_s),
        workers=int(workers),
        wall_clock_seconds=round(elapsed, 3),
        arcs=len(arcs),
        ortools_version=str(getattr(ortools, "__version__", "unknown")),
    )


class LiteratureGapBlocker(StrEnum):
    """Why a gap against a published objective may not be quoted."""

    INSTANCE_NOT_REFERENCE = "INSTANCE_NOT_REFERENCE"
    PLAN_NOT_VERIFIED = "PLAN_NOT_VERIFIED"
    SERVICE_INCOMPLETE = "SERVICE_INCOMPLETE"
    NO_SOLUTION = "NO_SOLUTION"


class LiteratureReport(StrictModel):
    instance_id: str
    instance_sha256: str
    algebra: str
    solver: str
    solver_status: str
    verified_feasible: bool
    violations: list[str]
    requests_total: int
    served_count: int
    full_service: bool
    cost: float | None
    model_bound: float | None
    reference_objective: float | None
    reference_source: str | None
    gap_percent: float | None
    within_reference_rounding: bool | None
    gap_blockers: list[str]
    allowed_claim: str


LITERATURE_ALGEBRA = (
    "Cordeau (2006): Euclidean real-valued travel, published service times, "
    "hard pickup and dropoff windows, ride <= L, duration <= T, load <= Q, <= K routes"
)


def build_literature_report(
    instance: CordeauInstance,
    instance_sha256: str,
    run: ExactSolveResult,
    verdict: ExactVerdict,
) -> LiteratureReport:
    """Gap only for a verified full-service plan on the exact vendored bytes."""
    reference = REFERENCES.get(instance_sha256)
    blockers: list[str] = []
    if reference is None:
        blockers.append(LiteratureGapBlocker.INSTANCE_NOT_REFERENCE.value)
    if not run.routes:
        blockers.append(LiteratureGapBlocker.NO_SOLUTION.value)
    if not verdict.feasible or verdict.alight_slack:
        blockers.append(LiteratureGapBlocker.PLAN_NOT_VERIFIED.value)
    if not verdict.full_service:
        blockers.append(LiteratureGapBlocker.SERVICE_INCOMPLETE.value)
    cost = verdict.cost if run.routes else None
    gap: float | None = None
    within: bool | None = None
    if not blockers and reference is not None and cost is not None:
        gap = 100.0 * (cost - reference.objective) / reference.objective
        within = abs(cost - reference.objective) <= 0.5 * 10 ** (-reference.decimals)
    if gap is None:
        claim = (
            f"literature algebra, {instance.instance_id}: run recorded, no publishable gap "
            f"({', '.join(blockers)})"
        )
    else:
        assert reference is not None and cost is not None
        match = " (matches within the reference's rounding)" if within else ""
        # A reference printed to two decimals cannot carry a sign below its rounding.
        shown = 0.0 if within else gap
        claim = (
            f"literature algebra, {instance.instance_id}: verified full-service plan, "
            f"cost {cost:.{reference.decimals}f} vs published {reference.objective:.2f}, "
            f"gap {shown:.2f}%{match}; solver status {run.status} on a conservative "
            f"integer model"
        )
    return LiteratureReport(
        instance_id=instance.instance_id,
        instance_sha256=instance_sha256,
        algebra=LITERATURE_ALGEBRA,
        solver=run.solver,
        solver_status=run.status,
        verified_feasible=verdict.feasible and not verdict.alight_slack,
        violations=list(verdict.violations),
        requests_total=verdict.requests_total,
        served_count=len(verdict.served_requests),
        full_service=verdict.full_service,
        cost=cost,
        model_bound=run.model_bound,
        reference_objective=None if reference is None else reference.objective,
        reference_source=None if reference is None else reference.source,
        gap_percent=None if gap is None else round(gap, 6),
        within_reference_rounding=within,
        gap_blockers=blockers,
        allowed_claim=claim,
    )
