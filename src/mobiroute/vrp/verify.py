"""Independent verifier for rich VRP plans.

Shares no code with the heuristics: it rebuilds loads from demands, timing
from the difference-constraint graph (:mod:`mobiroute.vrp.schedule`) and cost
from the matrices. A solver's own bookkeeping is never trusted. An infeasible
schedule comes back with a certificate (the conflicting constraints and the
minutes missing), not a bare "infeasible".
"""

from __future__ import annotations

from dataclasses import dataclass

from mobiroute.vrp.model import Instance
from mobiroute.vrp.schedule import Infeasibility, route_timing
from mobiroute.vrp.solution import CostBreakdown, Solution, evaluate

LOAD_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class VerifiedRoute:
    vehicle_type: str
    nodes: tuple[int, ...]
    #: Earliest service start at every stop, depots included.
    start_times: tuple[float, ...]
    #: Highest load per dimension along the route.
    peak_load: tuple[float, ...]
    #: Shortest feasible time from leaving the start depot to reaching the end.
    min_duration: float
    #: Trips of the day (reload stops plus one).
    trips: int = 1
    #: Driving minutes, and the stop whose following gap holds the driver's
    #: rest (``None``: no rest); the rest comes before or after that gap's drive.
    driving: float = 0.0
    rest_after: int | None = None


@dataclass(frozen=True, slots=True)
class Verdict:
    feasible: bool
    complete: bool
    violations: tuple[str, ...]
    served: tuple[str, ...]
    unassigned: tuple[str, ...]
    cost: CostBreakdown
    routes: tuple[VerifiedRoute, ...]
    certificates: tuple[tuple[int, Infeasibility], ...]

    def summary(self) -> str:
        state = "feasible" if self.feasible else f"INFEASIBLE ({len(self.violations)} violations)"
        return (
            f"{state}; served {len(self.served)}/{len(self.served) + len(self.unassigned)}; "
            f"vehicles {self.cost.vehicles}; distance {self.cost.distance:.2f}; "
            f"cost {self.cost.total:.2f}"
        )


def verify(inst: Instance, solution: Solution) -> Verdict:
    violations: list[str] = []
    dims = len(inst.dimensions)
    n_req = inst.n_requests
    owner_route: dict[int, int] = {}
    position: dict[int, int] = {}
    depots = {vt.start_depot for vt in inst.vehicle_types} | {
        vt.end_depot for vt in inst.vehicle_types
    }
    used_by_type = [0] * len(inst.vehicle_types)
    reload_seen: set[int] = set()
    for r_idx, route in enumerate(solution.routes):
        if not 0 <= route.vehicle_type < len(inst.vehicle_types):
            violations.append(f"UNKNOWN_VEHICLE_TYPE:{r_idx}")
            continue
        if route.nodes:
            used_by_type[route.vehicle_type] += 1
        reloads = 0
        for k, node in enumerate(route.nodes):
            if 0 <= node < inst.n_nodes and inst.reload_type_of(node) == route.vehicle_type:
                reloads += 1
                if node in reload_seen:
                    violations.append(f"DUPLICATE_VISIT:{node}")
                reload_seen.add(node)
                continue
            if not 0 <= node < inst.n_nodes or node in depots or inst.request_of(node) < 0:
                violations.append(f"NOT_A_SERVICE_NODE:{node}")
                continue
            if node in owner_route:
                violations.append(f"DUPLICATE_VISIT:{node}")
                continue
            owner_route[node] = r_idx
            position[node] = k
        vt_route = inst.vehicle_types[route.vehicle_type]
        if reloads > vt_route.max_trips - 1:
            violations.append(f"TOO_MANY_TRIPS:{r_idx}:{reloads + 1}>{vt_route.max_trips}")
    for t, used in enumerate(used_by_type):
        vt = inst.vehicle_types[t]
        if used > vt.count:
            violations.append(f"TOO_MANY_VEHICLES:{vt.id}:{used}>{vt.count}")

    served: list[str] = []
    missing: list[str] = []
    for r, req in enumerate(inst.requests):
        on = [owner_route.get(node) for node in req.nodes]
        if all(x is None for x in on):
            if r not in solution.unassigned:
                violations.append(f"UNACCOUNTED:{req.id}")
            missing.append(req.id)
            continue
        if r in solution.unassigned:
            violations.append(f"SERVED_AND_UNASSIGNED:{req.id}")
        if any(x is None for x in on):
            violations.append(f"PARTIAL_REQUEST:{req.id}")
            continue
        if len(set(on)) != 1:
            violations.append(f"SPLIT_REQUEST:{req.id}")
            continue
        route = solution.routes[on[0]]  # type: ignore[index]
        vt = inst.vehicle_types[route.vehicle_type]
        if not req.skills <= vt.skills:
            violations.append(f"SKILL:{req.id}:{','.join(sorted(req.skills - vt.skills))}")
        if req.is_pair:
            assert req.pickup is not None and req.delivery is not None
            if position[req.pickup] > position[req.delivery]:
                violations.append(f"DELIVERY_BEFORE_PICKUP:{req.id}")
        served.append(req.id)
    for r in solution.unassigned:
        if not 0 <= r < n_req:
            violations.append(f"UNKNOWN_REQUEST_INDEX:{r}")
    complete = all(
        inst.requests[r].penalty is not None for r in range(n_req) if inst.requests[r].id in missing
    )

    routes: list[VerifiedRoute] = []
    certificates: list[tuple[int, Infeasibility]] = []
    for r_idx, route in enumerate(solution.routes):
        if not route.nodes or not 0 <= route.vehicle_type < len(inst.vehicle_types):
            continue
        if any(
            owner_route.get(node) != r_idx
            for node in route.nodes
            if inst.reload_type_of(node) != route.vehicle_type
        ):
            continue  # malformed route already reported; no load or clock for it
        vt = inst.vehicle_types[route.vehicle_type]
        # Split the day into trips at reload stops; each trip loads its own
        # depot deliveries and unloads its collections at its end.
        trips: list[list[int]] = [[]]
        for node in route.nodes:
            if inst.reload_type_of(node) == route.vehicle_type:
                trips.append([])
            else:
                trips[-1].append(node)
        on_board = [0.0] * dims  # pairs picked up and not yet delivered
        peak = [0.0] * dims
        for trip in trips:
            load = list(on_board)
            for node in trip:
                req = inst.requests[inst.request_of(node)]
                if req.pickup is None:  # delivery from the depot: loaded at trip start
                    load = [a + b for a, b in zip(load, req.demand, strict=True)]
            peak = [max(a, b) for a, b in zip(peak, load, strict=True)]
            for node in trip:
                req = inst.requests[inst.request_of(node)]
                if node == req.pickup:
                    load = [a + b for a, b in zip(load, req.demand, strict=True)]
                    if req.is_pair:
                        on_board = [a + b for a, b in zip(on_board, req.demand, strict=True)]
                else:
                    load = [a - b for a, b in zip(load, req.demand, strict=True)]
                    if req.is_pair:
                        on_board = [a - b for a, b in zip(on_board, req.demand, strict=True)]
                peak = [max(a, b) for a, b in zip(peak, load, strict=True)]
                if any(value < -LOAD_EPS for value in load):
                    violations.append(f"NEGATIVE_LOAD:{r_idx}:{node}")
        for d, (value, cap) in enumerate(zip(peak, vt.capacity, strict=True)):
            if value > cap + LOAD_EPS:
                violations.append(f"CAPACITY:{r_idx}:{inst.dimensions[d]}:{value:g}>{cap:g}")
        timing = route_timing(inst, route.vehicle_type, route.nodes)
        if not timing.feasible:
            assert timing.infeasibility is not None
            certificates.append((r_idx, timing.infeasibility))
            violations.append(
                f"SCHEDULE:{r_idx}:short_by={timing.infeasibility.short_by:.2f}:"
                + "|".join(sorted(timing.infeasibility.labels))
            )
            continue
        rest_after = None
        if timing.rest_gap is not None:
            seq = [vt.start_depot, *route.nodes, vt.end_depot]
            rest_after = seq[timing.rest_gap]
        routes.append(
            VerifiedRoute(
                vehicle_type=vt.id,
                nodes=tuple(route.nodes),
                start_times=timing.earliest,
                peak_load=tuple(peak),
                min_duration=timing.min_duration,
                trips=len(trips),
                driving=timing.driving,
                rest_after=rest_after,
            )
        )
    return Verdict(
        feasible=not violations,
        complete=complete,
        violations=tuple(violations),
        served=tuple(served),
        unassigned=tuple(missing),
        cost=evaluate(inst, solution),
        routes=tuple(routes),
        certificates=tuple(certificates),
    )
