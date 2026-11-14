"""Routes, solutions and their cost.

A route is a vehicle type and an ordered list of service nodes (depots are
implied). Cost is computed from the instance only, so every solver and the
verifier price a plan the same way:

``fixed_cost + cost_per_distance * distance + cost_per_time * (driving + service)``

per used vehicle, plus the instance's ``vehicle_penalty`` per used vehicle and
each unserved request's penalty in the search objective.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from itertools import pairwise

from mobiroute.vrp.model import Instance

#: Penalty for an unserved request that must be served (``penalty is None``).
MUST_SERVE_PENALTY = 1e9


@dataclass(slots=True)
class Route:
    vehicle_type: int
    nodes: list[int] = field(default_factory=list)

    def copy(self) -> Route:
        return Route(self.vehicle_type, list(self.nodes))


@dataclass(slots=True)
class Solution:
    routes: list[Route] = field(default_factory=list)
    unassigned: set[int] = field(default_factory=set)

    def copy(self) -> Solution:
        return Solution([r.copy() for r in self.routes], set(self.unassigned))

    def used_routes(self) -> list[Route]:
        return [r for r in self.routes if r.nodes]

    def vehicles_used(self) -> int:
        return sum(1 for r in self.routes if r.nodes)

    def as_lists(self) -> list[tuple[int, list[int]]]:
        return [(r.vehicle_type, list(r.nodes)) for r in self.routes if r.nodes]

    def to_json(self, inst: Instance) -> str:
        data = {
            "instance": inst.name,
            "routes": [
                {"vehicle_type": inst.vehicle_types[t].id, "nodes": nodes}
                for t, nodes in self.as_lists()
            ],
            "unassigned": sorted(inst.requests[r].id for r in self.unassigned),
        }
        return json.dumps(data, indent=2)

    @staticmethod
    def from_lists(
        routes: Iterable[tuple[int, Sequence[int]]], unassigned: Iterable[int] = ()
    ) -> Solution:
        return Solution([Route(t, list(nodes)) for t, nodes in routes], set(unassigned))


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    vehicles: int
    vehicles_by_type: dict[str, int]
    distance: float
    driving_time: float
    service_time: float
    fixed: float
    variable: float
    unassigned: int
    penalty: float

    @property
    def total(self) -> float:
        """Money: fixed plus variable cost of the routes (no search penalties)."""
        return self.fixed + self.variable


def route_cost(
    inst: Instance, vehicle_type: int, nodes: Sequence[int]
) -> tuple[float, float, float]:
    """``(distance, driving time, service time)`` of one non-empty route."""
    vt = inst.vehicle_types[vehicle_type]
    profile = inst.profiles[vt.profile]
    seq = [vt.start_depot, *nodes, vt.end_depot]
    distance = sum(profile.distance[a][b] for a, b in pairwise(seq))
    driving = sum(profile.time[a][b] for a, b in pairwise(seq))
    service = sum(inst.nodes[n].service for n in nodes)
    return distance, driving, service


#: Memo of route costs keyed by vehicle type and stop sequence: distance,
#: driving, service and the minutes charged at the time rate.
RouteCosts = dict[tuple[int, tuple[int, ...]], tuple[float, float, float, float]]


def _route_charge(
    inst: Instance, vehicle_type: int, nodes: Sequence[int]
) -> tuple[float, float, float, float]:
    d, t, s = route_cost(inst, vehicle_type, nodes)
    paid = t + s if inst.time_cost != "duty" else charged_time(inst, vehicle_type, nodes)
    return d, t, s, paid


def charged_time(inst: Instance, vehicle_type: int, nodes: Sequence[int]) -> float:
    """Minutes ``cost_per_time`` pays for on this route.

    ``operating``: driving plus service. ``duty``: the shortest feasible
    duration from departure to return (waiting included), the shift of the
    route sheet; a route with no feasible schedule falls back to operating
    time (the verifier reports it anyway).
    """
    _d, driving, service = route_cost(inst, vehicle_type, nodes)
    if inst.time_cost != "duty":
        return driving + service
    from mobiroute.vrp.schedule import route_timing

    timing = route_timing(inst, vehicle_type, nodes)
    return timing.min_duration if timing.feasible else driving + service


def evaluate(
    inst: Instance, solution: Solution, *, costs: RouteCosts | None = None
) -> CostBreakdown:
    """Cost of a plan. ``costs`` memoizes route costs between calls (the search
    changes two or three routes per iteration); the sums and their order are
    the same with or without it."""
    by_type: dict[str, int] = {}
    distance = driving = service = fixed = variable = 0.0
    for route in solution.routes:
        if not route.nodes:
            continue
        vt = inst.vehicle_types[route.vehicle_type]
        if costs is None:
            d, t, s, paid = _route_charge(inst, route.vehicle_type, route.nodes)
        else:
            key = (route.vehicle_type, tuple(route.nodes))
            hit = costs.get(key)
            if hit is None:
                if len(costs) > 200_000:
                    costs.clear()
                hit = costs[key] = _route_charge(inst, route.vehicle_type, route.nodes)
            d, t, s, paid = hit
        distance += d
        driving += t
        service += s
        fixed += vt.fixed_cost
        variable += vt.cost_per_distance * d + vt.cost_per_time * paid
        by_type[vt.id] = by_type.get(vt.id, 0) + 1
    penalty = 0.0
    for r in solution.unassigned:
        p = inst.requests[r].penalty
        penalty += MUST_SERVE_PENALTY if p is None else p
    return CostBreakdown(
        vehicles=sum(by_type.values()),
        vehicles_by_type=by_type,
        distance=distance,
        driving_time=driving,
        service_time=service,
        fixed=fixed,
        variable=variable,
        unassigned=len(solution.unassigned),
        penalty=penalty,
    )


def objective(inst: Instance, solution: Solution) -> float:
    """What the search minimizes: money, vehicle penalty and unserved penalties."""
    cost = evaluate(inst, solution)
    return cost.total + inst.vehicle_penalty * cost.vehicles + cost.penalty
