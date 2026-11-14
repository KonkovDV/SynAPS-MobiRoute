"""Rich vehicle routing model.

One instance format covers the problem classes the engine is tested on:

* VRPTW (Solomon): every order is a delivery loaded at the depot;
* PDPTW (Li & Lim, Sartori & Buriol): paired pickup and delivery;
* DARP (Cordeau): PDPTW with a ride-time limit per request;
* cargo days: several vehicle types with a capacity vector (kg, m3, pallets),
  fixed and variable costs, own and hired units, skills (tail lift,
  refrigeration, ADR), shift windows and a maximum shift length, and separate
  travel profiles for vans and trucks.

Times are minutes from the planning origin and distances are in the unit of
the travel matrices. Nothing here depends on a solver: the model is plain
frozen data with validation, so a plan can be checked against it independently.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

INF = math.inf

Matrix = tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class Node:
    """A place a vehicle visits: service-start window and service duration."""

    id: int
    earliest: float = 0.0
    latest: float = INF
    service: float = 0.0
    x: float = 0.0
    y: float = 0.0
    name: str = ""


@dataclass(frozen=True, slots=True)
class Request:
    """A transport order.

    A pickup-and-delivery pair sets both nodes. A VRPTW customer sets only
    ``delivery``: the goods are loaded at the start depot. A collection sets
    only ``pickup``: the goods stay on board until the end depot.
    """

    id: str
    pickup: int | None
    delivery: int | None
    demand: tuple[float, ...]
    skills: frozenset[str] = frozenset()
    #: Limit on time on board: end of pickup service to start of delivery service.
    max_ride: float | None = None
    #: Cost of leaving the order unserved. ``None`` means it must be served.
    penalty: float | None = None
    #: When the order becomes known (dynamic dispatch). Static solvers ignore it.
    release: float = 0.0

    @property
    def is_pair(self) -> bool:
        return self.pickup is not None and self.delivery is not None

    @property
    def nodes(self) -> tuple[int, ...]:
        return tuple(n for n in (self.pickup, self.delivery) if n is not None)


@dataclass(frozen=True, slots=True)
class BreakRule:
    """Driver rest rule: at most ``max_driving`` minutes of driving between rests.

    The 4.5 h / 45 min norm (EU Regulation 561/2006, art. 7; the Russian
    order on drivers' working time sets the same limits) with a daily
    driving limit of ``2 * max_driving``: a route that drives more than
    ``max_driving`` minutes needs one rest of ``duration`` minutes, taken
    between two services so that neither side drives more than
    ``max_driving``. A rest is not work: it is not priced, and idle time in
    its gap can hold it.

    ``split`` allows the break in two parts, the first of at least
    ``split[0]`` and the second of at least ``split[1]`` minutes, in this
    order (15 + 30 under art. 7 of the EU regulation and Order No. 424). The
    driving counter resets only after the second part.
    """

    max_driving: float = 270.0
    duration: float = 45.0
    split: tuple[float, float] | None = None


@dataclass(frozen=True, slots=True)
class VehicleType:
    """A class of identical vehicles.

    ``cost_per_time`` is charged on operating time (driving plus service),
    not on idle waiting, so an insertion changes it by a closed-form amount.
    ``max_duration`` caps the time from leaving the start depot to arriving at
    the end depot (a shift length); the departure time is free within the
    shift, so the cap is checked against the shortest feasible duration.

    Multi-trip vehicles list ``reload_nodes``: stops at a depot where the
    vehicle unloads what it collected and loads the deliveries of its next
    trip (the node's service time is the reload time). A route may visit at
    most ``max_trips - 1`` of them; capacity holds per trip, while windows,
    the shift cap and the rest rule hold for the whole day.
    """

    id: str
    capacity: tuple[float, ...]
    count: int = 1
    start_depot: int = 0
    end_depot: int = 0
    shift_start: float = 0.0
    shift_end: float = INF
    fixed_cost: float = 0.0
    cost_per_distance: float = 1.0
    cost_per_time: float = 0.0
    max_duration: float | None = None
    skills: frozenset[str] = frozenset()
    profile: str = "default"
    hired: bool = False
    breaks: BreakRule | None = None
    reload_nodes: tuple[int, ...] = ()
    max_trips: int = 1


@dataclass(frozen=True, slots=True)
class SpeedProfile:
    """Speed by time of day (Ichoua, Gendreau & Potvin 2003).

    ``factors[k]`` is the speed, relative to free flow, from ``starts[k]``
    until the next start; the first factor also covers everything before
    ``starts[0]`` and the last one everything after. A trip that would take
    ``t`` minutes in free flow covers ``factor`` free-flow minutes per minute,
    so travel time depends on the departure time and never lets a later
    departure arrive earlier (FIFO).
    """

    starts: tuple[float, ...]
    factors: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class Profile:
    """Travel time and distance matrices of one road profile (car, truck, ...).

    ``time`` holds free-flow minutes; with ``speed`` set, the minutes of a
    trip depend on when it starts (:mod:`mobiroute.vrp.traffic`).
    """

    name: str
    time: Matrix
    distance: Matrix
    speed: SpeedProfile | None = None


@dataclass(frozen=True)
class Instance:
    """A complete routing problem.

    ``vehicle_penalty`` is added to the search objective for every used
    vehicle on top of the type's fixed cost. Benchmarks with the hierarchical
    objective (fewest vehicles, then distance) set it far above any routing
    cost; cargo instances leave it at zero and price vehicles through
    ``fixed_cost``.
    """

    name: str
    nodes: tuple[Node, ...]
    requests: tuple[Request, ...]
    vehicle_types: tuple[VehicleType, ...]
    profiles: Mapping[str, Profile]
    dimensions: tuple[str, ...] = ("load",)
    vehicle_penalty: float = 0.0
    source: str = ""
    #: What ``cost_per_time`` pays for: ``"operating"`` (driving and service,
    #: the default) or ``"duty"`` (the whole shift from departure to return,
    #: waiting included: the shortest feasible duration of the route).
    time_cost: str = "operating"
    _owner: tuple[int, ...] = field(init=False, repr=False, compare=False)

    _reload_owner: tuple[int, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        owner, reload_owner = _validate(self)
        object.__setattr__(self, "_owner", owner)
        object.__setattr__(self, "_reload_owner", reload_owner)

    @property
    def n_nodes(self) -> int:
        return len(self.nodes)

    def reload_type_of(self, node: int) -> int:
        """Vehicle type that reloads at ``node``, or ``-1`` if it is no reload stop."""
        return self._reload_owner[node]

    @property
    def has_rest_rules(self) -> bool:
        return any(vt.breaks is not None for vt in self.vehicle_types)

    @property
    def has_reloads(self) -> bool:
        return any(vt.reload_nodes for vt in self.vehicle_types)

    @property
    def has_traffic(self) -> bool:
        return any(p.speed is not None for p in self.profiles.values())

    def require_core_model(self, who: str) -> None:
        """Reject rules a solver lane does not model (rests, multi-trip days)."""
        if self.has_rest_rules:
            raise ValueError(f"{who}_REST_RULES_UNSUPPORTED")
        if self.has_reloads:
            raise ValueError(f"{who}_MULTI_TRIP_UNSUPPORTED")
        if self.has_traffic:
            raise ValueError(f"{who}_TIME_DEPENDENT_TRAVEL_UNSUPPORTED")

    @property
    def n_requests(self) -> int:
        return len(self.requests)

    def request_of(self, node: int) -> int:
        """Index of the request served at ``node``, or ``-1`` for a depot."""
        return self._owner[node]

    def profile_of(self, vehicle_type: int) -> Profile:
        return self.profiles[self.vehicle_types[vehicle_type].profile]

    def total_units(self) -> int:
        return sum(vt.count for vt in self.vehicle_types)


def _check_matrix(name: str, matrix: Matrix, n: int) -> None:
    if len(matrix) != n or any(len(row) != n for row in matrix):
        raise ValueError(f"VRP_MATRIX_SHAPE:{name}")
    for row in matrix:
        for value in row:
            if not (value >= 0.0) or math.isinf(value) or math.isnan(value):
                raise ValueError(f"VRP_MATRIX_VALUE:{name}")


def _validate(inst: Instance) -> tuple[tuple[int, ...], tuple[int, ...]]:
    n = len(inst.nodes)
    dims = len(inst.dimensions)
    if n == 0:
        raise ValueError("VRP_NO_NODES")
    if inst.time_cost not in ("operating", "duty"):
        raise ValueError(f"VRP_TIME_COST_INVALID:{inst.time_cost}")
    if dims == 0 or len(set(inst.dimensions)) != dims:
        raise ValueError("VRP_DIMENSIONS_INVALID")
    for k, node in enumerate(inst.nodes):
        if node.id != k:
            raise ValueError("VRP_NODE_IDS_MUST_BE_SEQUENTIAL")
        if node.service < 0 or math.isnan(node.earliest) or node.earliest > node.latest:
            raise ValueError(f"VRP_NODE_WINDOW_INVALID:{k}")
    if not inst.profiles:
        raise ValueError("VRP_NO_PROFILES")
    for name, profile in inst.profiles.items():
        if profile.name != name:
            raise ValueError(f"VRP_PROFILE_NAME_MISMATCH:{name}")
        _check_matrix(f"{name}.time", profile.time, n)
        _check_matrix(f"{name}.distance", profile.distance, n)
        sp = profile.speed
        if sp is not None and (
            not sp.factors
            or len(sp.starts) != len(sp.factors)
            or any(not (f > 0 and math.isfinite(f)) for f in sp.factors)
            or any(b <= a for a, b in zip(sp.starts, sp.starts[1:], strict=False))
        ):
            raise ValueError(f"VRP_SPEED_PROFILE_INVALID:{name}")
    if not inst.vehicle_types:
        raise ValueError("VRP_NO_VEHICLE_TYPES")
    depots: set[int] = set()
    type_ids: set[str] = set()
    for vt in inst.vehicle_types:
        if vt.id in type_ids:
            raise ValueError(f"VRP_DUPLICATE_VEHICLE_TYPE:{vt.id}")
        type_ids.add(vt.id)
        if len(vt.capacity) != dims or any(c < 0 for c in vt.capacity):
            raise ValueError(f"VRP_CAPACITY_INVALID:{vt.id}")
        if vt.count < 0:
            raise ValueError(f"VRP_COUNT_INVALID:{vt.id}")
        if not (0 <= vt.start_depot < n and 0 <= vt.end_depot < n):
            raise ValueError(f"VRP_DEPOT_OUT_OF_RANGE:{vt.id}")
        if vt.profile not in inst.profiles:
            raise ValueError(f"VRP_UNKNOWN_PROFILE:{vt.id}:{vt.profile}")
        if vt.shift_start > vt.shift_end:
            raise ValueError(f"VRP_SHIFT_INVALID:{vt.id}")
        if vt.max_duration is not None and vt.max_duration < 0:
            raise ValueError(f"VRP_MAX_DURATION_INVALID:{vt.id}")
        for value in (vt.fixed_cost, vt.cost_per_distance, vt.cost_per_time):
            if value < 0 or math.isnan(value):
                raise ValueError(f"VRP_COST_INVALID:{vt.id}")
        if vt.breaks is not None and not (vt.breaks.max_driving > 0 and vt.breaks.duration >= 0):
            raise ValueError(f"VRP_BREAK_RULE_INVALID:{vt.id}")
        if vt.breaks is not None and vt.breaks.split is not None:
            first, second = vt.breaks.split
            if not (first > 0 and second > 0 and first + second >= vt.breaks.duration - 1e-9):
                raise ValueError(f"VRP_BREAK_SPLIT_INVALID:{vt.id}")
        if vt.max_trips < 1 or (vt.max_trips > 1) != bool(vt.reload_nodes):
            raise ValueError(f"VRP_TRIPS_INVALID:{vt.id}")
        depots.update((vt.start_depot, vt.end_depot))
    if inst.vehicle_penalty < 0:
        raise ValueError("VRP_VEHICLE_PENALTY_INVALID")
    if any(p.speed is not None for p in inst.profiles.values()) and (
        any(r.max_ride is not None for r in inst.requests)
        or any(vt.breaks is not None for vt in inst.vehicle_types)
    ):
        raise ValueError("VRP_TRAFFIC_WITH_RIDE_LIMITS_OR_RESTS_UNSUPPORTED")
    reload_owner = [-1] * n
    for t, vt in enumerate(inst.vehicle_types):
        for nid in vt.reload_nodes:
            if not 0 <= nid < n or nid in depots or reload_owner[nid] != -1:
                raise ValueError(f"VRP_RELOAD_NODE_INVALID:{vt.id}:{nid}")
            reload_owner[nid] = t
    owner = [-1] * n
    ids: set[str] = set()
    for r, req in enumerate(inst.requests):
        if req.id in ids:
            raise ValueError(f"VRP_DUPLICATE_REQUEST:{req.id}")
        ids.add(req.id)
        if not req.nodes:
            raise ValueError(f"VRP_REQUEST_WITHOUT_NODES:{req.id}")
        if len(req.demand) != dims or any(q < 0 for q in req.demand):
            raise ValueError(f"VRP_DEMAND_INVALID:{req.id}")
        if req.max_ride is not None and (not req.is_pair or req.max_ride < 0):
            raise ValueError(f"VRP_MAX_RIDE_NEEDS_A_PAIR:{req.id}")
        if req.penalty is not None and req.penalty < 0:
            raise ValueError(f"VRP_PENALTY_INVALID:{req.id}")
        for nid in req.nodes:
            if not 0 <= nid < n:
                raise ValueError(f"VRP_REQUEST_NODE_OUT_OF_RANGE:{req.id}")
            if nid in depots or reload_owner[nid] != -1:
                raise ValueError(f"VRP_REQUEST_AT_DEPOT:{req.id}")
            if owner[nid] != -1:
                raise ValueError(f"VRP_NODE_SHARED:{nid}")
            owner[nid] = r
        if req.pickup is not None and req.pickup == req.delivery:
            raise ValueError(f"VRP_PICKUP_EQUALS_DELIVERY:{req.id}")
    return tuple(owner), tuple(reload_owner)


def add_reload_stops(inst: Instance, type_id: str, max_trips: int, reload_time: float) -> Instance:
    """Copy of ``inst`` whose vehicle type ``type_id`` may run ``max_trips`` trips.

    Appends ``count * (max_trips - 1)`` reload stops: copies of the type's
    start depot (same place, same opening hours) whose service time is the
    reload time. Every profile matrix gains the depot's rows and columns.
    """
    from dataclasses import replace

    t = next(k for k, vt in enumerate(inst.vehicle_types) if vt.id == type_id)
    vt = inst.vehicle_types[t]
    if max_trips < 2:
        raise ValueError("VRP_TRIPS_INVALID")
    depot = vt.start_depot
    n = inst.n_nodes
    extra = vt.count * (max_trips - 1)
    new_ids = tuple(range(n, n + extra))
    base = inst.nodes[depot]
    nodes = list(inst.nodes)
    for k, nid in enumerate(new_ids):
        nodes.append(
            Node(
                nid,
                max(base.earliest, vt.shift_start),
                min(base.latest, vt.shift_end),
                reload_time,
                base.x,
                base.y,
                f"reload {vt.id} #{k + 1}",
            )
        )
    src = [*range(n), *([depot] * extra)]

    def grow(matrix: Matrix) -> Matrix:
        return tuple(tuple(matrix[a][b] for b in src) for a in src)

    # ``replace`` keeps every other field of the profile: a rush-hour speed
    # profile must survive, or the day would be planned on free-flow times.
    profiles = {
        name: replace(p, time=grow(p.time), distance=grow(p.distance))
        for name, p in inst.profiles.items()
    }
    types = list(inst.vehicle_types)
    types[t] = replace(vt, reload_nodes=vt.reload_nodes + new_ids, max_trips=max_trips)
    return replace(inst, nodes=tuple(nodes), vehicle_types=tuple(types), profiles=profiles)


def euclidean_matrix(points: Sequence[tuple[float, float]]) -> Matrix:
    """Euclidean distances in double precision (the Solomon / Li & Lim convention)."""
    return tuple(tuple(math.hypot(ax - bx, ay - by) for bx, by in points) for ax, ay in points)


def scaled_matrix(matrix: Matrix, factor: float) -> Matrix:
    """A slower or faster copy of a matrix (truck profile from a car profile)."""
    return tuple(tuple(value * factor for value in row) for row in matrix)


def single_profile(time: Matrix, distance: Matrix | None = None) -> dict[str, Profile]:
    """The common case: one road profile named ``default``."""
    return {"default": Profile("default", time, time if distance is None else distance)}


def skills_ok(request: Request, vehicle: VehicleType) -> bool:
    return request.skills <= vehicle.skills


def as_frozenset(values: Iterable[str] | None) -> frozenset[str]:
    return frozenset(values or ())
