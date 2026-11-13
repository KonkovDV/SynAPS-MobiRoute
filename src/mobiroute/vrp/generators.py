"""Synthetic instances: randomized test cases and realistic operating days.

* :func:`random_instance` - small adversarial cases for property tests (mixed
  order kinds, capacity vector, skills, ride limits, shift caps, several
  vehicle types and profiles).
* :func:`cargo_day` - a city freight day: two depots, a mixed own and hired
  fleet of vans and trucks with a kg / m3 / pallet capacity vector, tail
  lift, refrigeration and ADR skills, slower truck profile, delivery windows,
  warehouse-to-customer transfers and a 10-hour shift cap.
* :func:`shuttle_day` - on-demand employee shuttle between stops: orders
  appear during the day, pickup within 30 minutes of the call, wait plus
  ride within 45 minutes, 8-seat minibuses.
* :func:`plant_day` - in-plant transport between workshops and warehouses:
  pallet moves with release times, tow tractors, flatbeds with a crane and a
  covered van; the operating metric is time from call to pickup.

Every generator is deterministic in its seed. The data are synthetic: they
exercise the model, they do not describe any real operator.
"""

from __future__ import annotations

import math
import random

from mobiroute.vrp.model import (
    Instance,
    Node,
    Profile,
    Request,
    VehicleType,
    euclidean_matrix,
    scaled_matrix,
)


def random_instance(
    seed: int,
    *,
    n_requests: int = 6,
    n_types: int = 2,
    dims: int = 2,
    ride_share: float = 0.3,
    pair_share: float = 0.6,
    tight: bool = False,
    max_duration: bool = True,
    penalty: float | None = None,
) -> Instance:
    """A small rich instance for property tests.

    ``penalty`` makes every order optional at that price, so an instance with
    an order no vehicle can carry still has an optimum to compare against.
    """
    rng = random.Random(seed)
    horizon = 300.0
    depot = Node(0, 0.0, horizon, 0.0, 50.0, 50.0, "depot")
    nodes: list[Node] = [depot]
    points = [(50.0, 50.0)]
    requests: list[Request] = []
    skills_pool = ["lift", "cold"]

    def add_node(lo: float, width: float) -> int:
        x, y = rng.uniform(0, 100), rng.uniform(0, 100)
        k = len(nodes)
        lo = min(lo, horizon - width)
        nodes.append(Node(k, lo, lo + width, float(rng.choice([0, 2, 5, 10])), x, y))
        points.append((x, y))
        return k

    for r in range(n_requests):
        width = rng.uniform(20, 60) if tight else rng.uniform(60, 240)
        start = rng.uniform(0, horizon - width)
        demand = tuple(float(rng.randint(1, 4)) for _ in range(dims))
        skills = frozenset(rng.sample(skills_pool, 1)) if rng.random() < 0.2 else frozenset()
        kind = rng.random()
        if kind < pair_share:
            p = add_node(start, width)
            d = add_node(start + rng.uniform(0, 60), width)
            ride = rng.uniform(40, 120) if rng.random() < ride_share else None
            requests.append(Request(f"r{r}", p, d, demand, skills, ride, penalty))
        elif kind < pair_share + (1 - pair_share) / 2:
            requests.append(
                Request(f"r{r}", None, add_node(start, width), demand, skills, None, penalty)
            )
        else:
            requests.append(
                Request(f"r{r}", add_node(start, width), None, demand, skills, None, penalty)
            )
    base = euclidean_matrix(points)
    profiles = {
        "car": Profile("car", base, base),
        "truck": Profile("truck", scaled_matrix(base, 1.3), base),
    }
    types = []
    for t in range(n_types):
        types.append(
            VehicleType(
                id=f"type{t}",
                capacity=tuple(float(rng.randint(6, 12)) for _ in range(dims)),
                count=rng.randint(1, 3),
                fixed_cost=float(rng.choice([0, 50, 120])),
                cost_per_distance=rng.choice([1.0, 1.5]),
                cost_per_time=rng.choice([0.0, 0.5]),
                max_duration=rng.uniform(150, 280) if max_duration and rng.random() < 0.6 else None,
                skills=frozenset(rng.sample(skills_pool, rng.randint(1, 2))),
                profile=rng.choice(["car", "truck"]),
                shift_start=0.0,
                shift_end=horizon,
            )
        )
    return Instance(
        name=f"random-{seed}",
        nodes=tuple(nodes),
        requests=tuple(requests),
        vehicle_types=tuple(types),
        profiles=profiles,
        dimensions=tuple(f"d{k}" for k in range(dims)),
    )


#: Vehicle classes of a city freight day: capacity (kg, m3, pallets), costs in
#: roubles. Own units cost only their running cost (the vehicle and its driver
#: are paid for anyway); a hired unit costs a hire fee per day plus a dearer
#: tariff, so the plan hires only when the own fleet cannot cover the day.
FREIGHT_FLEET = (
    # id,           capacity,        hire fee, per km, per h, own, hired, skills
    ("van_1.5t", (1500.0, 9.0, 4.0), 2500.0, 18.0, 450.0, 6, 6, ("tail_lift",)),
    ("truck_5t", (5000.0, 30.0, 12.0), 4200.0, 26.0, 600.0, 4, 5, ("tail_lift", "cold")),
    ("truck_10t", (10000.0, 45.0, 16.0), 5600.0, 34.0, 700.0, 2, 3, ("cold", "adr")),
    ("tractor_20t", (20000.0, 82.0, 33.0), 7800.0, 48.0, 900.0, 1, 2, ("adr",)),
)


def _clustered_points(rng: random.Random, count: int, size: float) -> list[tuple[float, float]]:
    centers = [(rng.uniform(0.15, 0.85) * size, rng.uniform(0.15, 0.85) * size) for _ in range(5)]
    out = []
    for _ in range(count):
        if rng.random() < 0.7:
            cx, cy = rng.choice(centers)
            out.append((cx + rng.gauss(0, size * 0.06), cy + rng.gauss(0, size * 0.06)))
        else:
            out.append((rng.uniform(0, size), rng.uniform(0, size)))
    return [(min(size, max(0.0, x)), min(size, max(0.0, y))) for x, y in out]


def cargo_day(
    seed: int = 7,
    *,
    n_orders: int = 120,
    transfer_share: float = 0.35,
    area_km: float = 60.0,
    hired_markup: float = 1.35,
) -> Instance:
    """A synthetic city freight day with a heterogeneous own and hired fleet.

    Times are minutes after midnight; distances are road kilometres (straight
    line times a detour factor of 1.3). Vans average 32 km/h, trucks 26 km/h.
    Two depots: a central DC for vans and small trucks, a ring-road terminal
    for heavy units. Orders are deliveries from the DC (loaded at the start)
    or transfers from a supplier warehouse to a customer.
    """
    rng = random.Random(seed)
    depots = [(area_km * 0.5, area_km * 0.5), (area_km * 0.9, area_km * 0.15)]
    customers = _clustered_points(rng, n_orders * 2, area_km)
    nodes: list[Node] = [
        Node(0, 360.0, 1320.0, 0.0, *depots[0], "DC"),
        Node(1, 360.0, 1320.0, 0.0, *depots[1], "terminal"),
    ]
    points = list(depots)
    requests: list[Request] = []
    used = 0

    def new_node(lo: float, hi: float, service: float, label: str) -> int:
        nonlocal used
        x, y = customers[used]
        used += 1
        k = len(nodes)
        nodes.append(Node(k, lo, hi, service, x, y, label))
        points.append((x, y))
        return k

    for o in range(n_orders):
        size = rng.random()
        if size < 0.65:
            kg = rng.uniform(50, 600)
        elif size < 0.93:
            kg = rng.uniform(600, 2500)
        else:
            kg = rng.uniform(2500, 7000)
        m3 = kg / rng.uniform(230, 380)
        pallets = float(max(1, math.ceil(kg / 600.0)))
        demand = (round(kg, 1), round(m3, 2), pallets)
        skills: set[str] = set()
        roll = rng.random()
        if roll < 0.15:
            skills.add("cold")
        elif roll < 0.22:
            skills.add("adr")
        if kg < 1500 and rng.random() < 0.25 and "adr" not in skills:
            skills.add("tail_lift")
        slot = rng.choice(
            [(480, 720), (540, 780), (600, 900), (720, 1020), (840, 1080), (480, 1080)]
        )
        service = round(10 + 4 * pallets, 1)
        if rng.random() < transfer_share:
            open_at = rng.choice([420, 480, 540])
            p = new_node(float(open_at), float(open_at + 240), service, f"S{o}")
            # A customer slot that a truck can still make from the supplier.
            (px_, py_), (dx_, dy_) = points[p], customers[used]
            drive = math.hypot(px_ - dx_, py_ - dy_) * 1.3 * 60.0 / 26.0
            ready = open_at + service + drive + 30.0
            if slot[1] < ready:
                slot = (int(ready) - 120, int(ready) + 120)
            d = new_node(float(slot[0]), float(slot[1]), service, f"C{o}")
            requests.append(Request(f"T{o:03d}", p, d, demand, frozenset(skills)))
        else:
            d = new_node(float(slot[0]), float(slot[1]), service, f"C{o}")
            requests.append(Request(f"D{o:03d}", None, d, demand, frozenset(skills)))
    straight = euclidean_matrix(points)
    road = scaled_matrix(straight, 1.3)
    van_time = scaled_matrix(road, 60.0 / 32.0)
    truck_time = scaled_matrix(road, 60.0 / 26.0)
    profiles = {
        "van": Profile("van", van_time, road),
        "truck": Profile("truck", truck_time, road),
    }
    types: list[VehicleType] = []
    for vid, cap, fixed, per_km, per_h, own, hired, skills_v in FREIGHT_FLEET:
        depot = 1 if vid.startswith(("truck_10", "tractor")) else 0
        profile = "van" if vid.startswith("van") else "truck"
        for is_hired, count in ((False, own), (True, hired)):
            mark = hired_markup if is_hired else 1.0
            types.append(
                VehicleType(
                    id=f"{vid}{'-hired' if is_hired else ''}",
                    capacity=cap,
                    count=count,
                    start_depot=depot,
                    end_depot=depot,
                    shift_start=360.0,
                    shift_end=1320.0,
                    fixed_cost=fixed if is_hired else 0.0,
                    cost_per_distance=per_km * mark,
                    cost_per_time=per_h * mark / 60.0,
                    max_duration=600.0,
                    skills=frozenset(skills_v),
                    profile=profile,
                    hired=is_hired,
                )
            )
    return Instance(
        name=f"cargo-day-{seed}-{n_orders}",
        nodes=tuple(nodes),
        requests=tuple(requests),
        vehicle_types=tuple(types),
        profiles=profiles,
        dimensions=("kg", "m3", "pallets"),
        source="synthetic cargo day",
    )


def _grid_stops(rng: random.Random, count: int, size: float) -> list[tuple[float, float]]:
    return [(rng.uniform(0, size), rng.uniform(0, size)) for _ in range(count)]


def shuttle_day(
    seed: int = 11,
    *,
    n_orders: int = 160,
    n_stops: int = 40,
    n_buses: int = 10,
    area_km: float = 14.0,
    max_wait: float = 30.0,
    max_wait_plus_ride: float = 45.0,
) -> Instance:
    """On-demand employee shuttle: dynamic DARP with stop-to-stop orders.

    An order placed at ``t`` asks for a pickup in ``[t + 5, t + max_wait]``
    and an arrival within ``max_wait_plus_ride`` of the call: a delivery
    deadline expresses "wait plus ride" exactly. Buses run at 25 km/h.
    """
    rng = random.Random(seed)
    stops = _grid_stops(rng, n_stops, area_km)
    depot_xy = (area_km / 2, area_km / 2)
    nodes: list[Node] = [Node(0, 360.0, 1380.0, 0.0, *depot_xy, "garage")]
    points = [depot_xy]
    requests: list[Request] = []
    peaks = [(450, 40), (1020, 45), (750, 120)]
    for o in range(n_orders):
        center, spread = rng.choice(peaks)
        call = min(1260.0, max(380.0, rng.gauss(center, spread)))
        a, b = rng.sample(range(n_stops), 2)
        k = len(nodes)
        board = 1.0
        nodes.append(Node(k, call + 5.0, call + max_wait, board, *stops[a], f"stop{a}"))
        nodes.append(Node(k + 1, call + 5.0, call + max_wait_plus_ride, 1.0, *stops[b], f"stop{b}"))
        points.extend([stops[a], stops[b]])
        seats = 1.0 if rng.random() < 0.85 else 2.0
        # The delivery deadline already caps wait plus ride, so no separate ride limit.
        requests.append(Request(f"P{o:03d}", k, k + 1, (seats,), release=round(call, 1)))
    road = scaled_matrix(euclidean_matrix(points), 1.25)
    time = scaled_matrix(road, 60.0 / 25.0)
    bus = VehicleType(
        id="minibus_8",
        capacity=(8.0,),
        count=n_buses,
        shift_start=360.0,
        shift_end=1380.0,
        cost_per_distance=1.0,
        max_duration=None,
        profile="bus",
    )
    return Instance(
        name=f"shuttle-{seed}-{n_orders}",
        nodes=tuple(nodes),
        requests=tuple(requests),
        vehicle_types=(bus,),
        profiles={"bus": Profile("bus", time, road)},
        dimensions=("seats",),
        source="synthetic shuttle day",
    )


def plant_day(
    seed: int = 5,
    *,
    n_moves: int = 140,
    n_sites: int = 24,
    area_km: float = 4.0,
) -> Instance:
    """In-plant transport: pallet moves between workshops and warehouses.

    A move becomes known at its release time and should be picked up within
    40 minutes and delivered within 90. Tow tractors are cheap and slow (12
    km/h), flatbeds with a crane carry heavy parts (20 km/h), a covered van
    takes moisture-sensitive cargo (25 km/h).
    """
    rng = random.Random(seed)
    sites = _grid_stops(rng, n_sites, area_km)
    garage = (0.1 * area_km, 0.1 * area_km)
    nodes: list[Node] = [Node(0, 420.0, 1380.0, 0.0, *garage, "garage")]
    points = [garage]
    requests: list[Request] = []
    for o in range(n_moves):
        release = rng.uniform(430.0, 1290.0)
        a, b = rng.sample(range(n_sites), 2)
        pallets = float(rng.choice([1, 1, 2, 2, 3, 4, 6]))
        kg = pallets * rng.uniform(250, 700)
        skills: set[str] = set()
        if kg > 2500 or rng.random() < 0.08:
            skills.add("crane")
        elif rng.random() < 0.12:
            skills.add("covered")
        k = len(nodes)
        handling = 4.0 + 1.5 * pallets
        nodes.append(Node(k, release, release + 40.0, handling, *sites[a], f"W{a}"))
        nodes.append(Node(k + 1, release, release + 90.0, handling, *sites[b], f"W{b}"))
        points.extend([sites[a], sites[b]])
        requests.append(
            Request(
                f"M{o:03d}",
                k,
                k + 1,
                (pallets, round(kg, 1)),
                frozenset(skills),
                release=round(release, 1),
            )
        )
    road = scaled_matrix(euclidean_matrix(points), 1.4)
    profiles = {
        "tractor": Profile("tractor", scaled_matrix(road, 60.0 / 12.0), road),
        "flatbed": Profile("flatbed", scaled_matrix(road, 60.0 / 20.0), road),
        "van": Profile("van", scaled_matrix(road, 60.0 / 25.0), road),
    }
    fleet = (
        # id, capacity (pallets, kg), units, fixed, per km, per minute, skills, profile
        ("tow_tractor", (6.0, 3000.0), 5, 900.0, 20.0, 5.0, (), "tractor"),
        ("flatbed_crane", (8.0, 8000.0), 2, 2400.0, 45.0, 10.0, ("crane",), "flatbed"),
        ("covered_van", (4.0, 1500.0), 2, 1500.0, 25.0, 8.0, ("covered",), "van"),
    )
    types = tuple(
        VehicleType(
            id=vid,
            capacity=cap,
            count=units,
            fixed_cost=fixed,
            cost_per_distance=per_km,
            cost_per_time=per_min,
            skills=frozenset(skills_v),
            profile=profile,
            shift_start=420.0,
            shift_end=1380.0,
            max_duration=720.0,
        )
        for vid, cap, units, fixed, per_km, per_min, skills_v, profile in fleet
    )
    return Instance(
        name=f"plant-{seed}-{n_moves}",
        nodes=tuple(nodes),
        requests=tuple(requests),
        vehicle_types=types,
        profiles=profiles,
        dimensions=("pallets", "kg"),
        source="synthetic plant day",
    )
