"""Driver rests and multi-trip days: the search's checks against the verifier.

The insertion module and the verifier implement the rest rule and the trip
loads separately; these tests hold them to the same answers on random routes
(property-based, Hypothesis) and on small cases solved by hand.
"""

from __future__ import annotations

import random
from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mobiroute.vrp.alns import AlnsConfig, solve
from mobiroute.vrp.generators import random_instance
from mobiroute.vrp.insertion import (
    Compiled,
    RouteState,
    apply_insertion,
    best_insertion,
    route_exact,
    route_loads,
    tidy_reloads,
)
from mobiroute.vrp.io import instance_from_json, instance_to_json
from mobiroute.vrp.model import (
    BreakRule,
    Instance,
    Node,
    Request,
    SpeedProfile,
    VehicleType,
    add_reload_stops,
    euclidean_matrix,
    single_profile,
)
from mobiroute.vrp.schedule import route_timing
from mobiroute.vrp.solution import Route, Solution
from mobiroute.vrp.traffic import arrive, depart_by, with_traffic
from mobiroute.vrp.verify import verify


def _with_rests(inst: Instance, drive: float, rest: float) -> Instance:
    types = tuple(replace(vt, breaks=BreakRule(drive, rest)) for vt in inst.vehicle_types)
    return replace(inst, vehicle_types=types)


def _random_sequence(inst: Instance, rng: random.Random, size: int) -> list[int]:
    """Request nodes in a random order that keeps every pickup before its delivery."""
    reqs = rng.sample(range(inst.n_requests), min(size, inst.n_requests))
    seq: list[int] = []
    for r in reqs:
        req = inst.requests[r]
        if req.is_pair:
            assert req.pickup is not None and req.delivery is not None
            i = rng.randint(0, len(seq))
            seq.insert(i, req.pickup)
            seq.insert(rng.randint(i + 1, len(seq)), req.delivery)
        else:
            seq.insert(rng.randint(0, len(seq)), req.nodes[0])
    return seq


@settings(max_examples=60, deadline=None)
@given(
    seed=st.integers(0, 10_000),
    drive=st.floats(30.0, 250.0),
    rest=st.floats(0.0, 60.0),
    size=st.integers(1, 6),
)
def test_rest_rule_check_agrees_with_the_verifier(
    seed: int, drive: float, rest: float, size: int
) -> None:
    inst = _with_rests(random_instance(seed, n_requests=7, ride_share=0.4), drive, rest)
    c = Compiled(inst)
    rng = random.Random(seed)
    for _ in range(6):
        nodes = _random_sequence(inst, rng, size)
        for t in range(len(inst.vehicle_types)):
            assert route_exact(c, t, nodes) == route_timing(inst, t, nodes).feasible


@settings(max_examples=40, deadline=None)
@given(seed=st.integers(0, 10_000), drive=st.floats(60.0, 250.0))
def test_insertion_under_the_rest_rule_gives_verified_routes(seed: int, drive: float) -> None:
    inst = _with_rests(random_instance(seed, n_requests=7, ride_share=0.3), drive, 30.0)
    c = Compiled(inst)
    rng = random.Random(seed)
    nodes: list[int] = []
    t = rng.randrange(len(inst.vehicle_types))
    for r in rng.sample(range(inst.n_requests), inst.n_requests):
        found = best_insertion(c, RouteState(c, t, nodes), r)
        if found is None:
            continue
        nodes = apply_insertion(c, nodes, r, found[1], found[2])
        served = c.requests_of(nodes)
        rest = set(range(inst.n_requests)) - served
        verdict = verify(inst, Solution([Route(t, nodes)], rest))
        assert verdict.feasible, verdict.violations


def test_rest_placement_and_certificates() -> None:
    # Depot at 0, three stops 100 apart on a line: legs of 100 minutes.
    pts = [(0.0, 0.0), (100.0, 0.0), (200.0, 0.0), (300.0, 0.0)]
    nodes = [Node(0, 0.0, 2000.0)] + [
        Node(k, 0.0, 2000.0, 0.0, x, y) for k, (x, y) in enumerate(pts) if k
    ]
    time = euclidean_matrix(pts)
    reqs = tuple(Request(f"o{k}", None, k, (1.0,)) for k in (1, 2, 3))
    rule = BreakRule(max_driving=350.0, duration=45.0)
    van = VehicleType("van", (10.0,), breaks=rule)
    inst = Instance("line", tuple(nodes), reqs, (van,), single_profile(time))
    # 1 -> 2 -> 3 and back drives 600 minutes: one rest, 250..350 driven before it.
    timing = route_timing(inst, 0, [1, 2, 3])
    assert timing.feasible and timing.rest_gap is not None
    assert timing.earliest[-1] == pytest.approx(600.0 + 45.0)
    verdict = verify(inst, Solution([Route(0, [1, 2, 3])]))
    assert verdict.feasible and verdict.routes[0].rest_after is not None
    # The depot closes at 620: wherever the rest goes, the van is 25 minutes late.
    tight = replace(inst, nodes=(replace(inst.nodes[0], latest=620.0), *inst.nodes[1:]))
    late = route_timing(tight, 0, [1, 2, 3])
    assert not late.feasible and late.infeasibility is not None
    assert any(label.startswith("TRAVEL+REST") for label in late.infeasibility.labels)
    assert late.infeasibility.short_by == pytest.approx(25.0)
    # More than twice the driving limit cannot be split by one rest.
    short = replace(inst, vehicle_types=(replace(van, breaks=BreakRule(250.0, 45.0)),))
    over = route_timing(short, 0, [1, 2, 3])
    assert not over.feasible and over.infeasibility is not None
    assert over.infeasibility.labels == ("DRIVING",)
    assert over.infeasibility.short_by == pytest.approx(100.0)


def _two_wave_day(trips: int) -> Instance:
    """Four deliveries, two in the morning and two in the afternoon; a van takes two."""
    pts = [(0.0, 0.0), (10.0, 0.0), (0.0, 10.0), (-10.0, 0.0), (0.0, -10.0)]
    windows = [(0.0, 600.0), (30.0, 90.0), (30.0, 90.0), (300.0, 360.0), (300.0, 360.0)]
    nodes = tuple(
        Node(k, lo, hi, 0.0 if k == 0 else 10.0, x, y)
        for k, ((x, y), (lo, hi)) in enumerate(zip(pts, windows, strict=True))
    )
    reqs = tuple(Request(f"o{k}", None, k, (1.0,)) for k in range(1, 5))
    own = VehicleType("van", (2.0,), count=1, fixed_cost=0.0)
    hired = VehicleType("van-hired", (2.0,), count=2, fixed_cost=500.0)
    inst = Instance("two-waves", nodes, reqs, (own, hired), single_profile(euclidean_matrix(pts)))
    return add_reload_stops(inst, "van", trips, 15.0) if trips > 1 else inst


def test_a_second_trip_replaces_a_hired_van() -> None:
    single = solve(_two_wave_day(1), AlnsConfig(iterations=200, seed=1))
    multi = solve(_two_wave_day(2), AlnsConfig(iterations=200, seed=1))
    assert single.verdict.feasible and multi.verdict.feasible
    assert single.verdict.cost.vehicles_by_type == {"van": 1, "van-hired": 1}
    assert multi.verdict.cost.vehicles_by_type == {"van": 1}
    (day,) = multi.verdict.routes
    assert day.trips == 2 and day.peak_load == (2.0,)


def test_trip_loads_reset_at_the_reload_stop() -> None:
    inst = _two_wave_day(2)
    c = Compiled(inst)
    stop = inst.vehicle_types[0].reload_nodes[0]
    loads = route_loads(c, [1, 2, stop, 3, 4])
    assert [row[0] for row in loads] == [2.0, 1.0, 0.0, 2.0, 1.0, 0.0]
    # Three deliveries in one trip exceed the van; split by the stop they fit.
    over = verify(inst, Solution([Route(0, [1, 2, 3, stop, 4])]))
    assert not over.feasible and any(v.startswith("CAPACITY") for v in over.violations)
    ok = verify(inst, Solution([Route(0, [1, 2, stop, 3, 4])]))
    assert ok.feasible, ok.violations


def test_tidy_reloads_drops_empty_trips() -> None:
    inst = _two_wave_day(2)
    c = Compiled(inst)
    stop = inst.vehicle_types[0].reload_nodes[0]
    assert tidy_reloads(c, [stop, 1, 2]) == [1, 2]
    assert tidy_reloads(c, [1, stop]) == [1]
    assert tidy_reloads(c, [stop]) == []
    assert tidy_reloads(c, [1, stop, 3]) == [1, stop, 3]


def test_verifier_rejects_foreign_or_extra_reload_stops() -> None:
    inst = _two_wave_day(2)
    stop = inst.vehicle_types[0].reload_nodes[0]
    foreign = verify(inst, Solution([Route(1, [1, stop, 3])], {1, 3}))
    assert any(v.startswith("NOT_A_SERVICE_NODE") for v in foreign.violations)


def test_json_round_trip_keeps_rests_and_trips() -> None:
    inst = _with_rests(_two_wave_day(2), 270.0, 45.0)
    back = instance_from_json(instance_to_json(inst))
    assert back.vehicle_types == inst.vehicle_types
    assert back.reload_type_of(inst.vehicle_types[0].reload_nodes[0]) == 0


def test_lanes_without_rules_say_so() -> None:
    from mobiroute.vrp.exact import solve_exact
    from mobiroute.vrp.ortools_lane import solve_ortools
    from mobiroute.vrp.realtime import Dispatcher

    rested = _with_rests(_two_wave_day(1), 270.0, 45.0)
    with pytest.raises(ValueError, match="ORTOOLS_LANE_REST_RULES_UNSUPPORTED"):
        solve_ortools(rested, time_limit=1.0)
    with pytest.raises(ValueError, match="EXACT_MULTI_TRIP_UNSUPPORTED"):
        solve_exact(_two_wave_day(2), time_limit=1.0)
    with pytest.raises(ValueError, match="REALTIME_REST_RULES_UNSUPPORTED"):
        Dispatcher(rested)


def test_model_validates_rules() -> None:
    inst = _two_wave_day(1)
    with pytest.raises(ValueError, match="VRP_BREAK_RULE_INVALID"):
        _with_rests(inst, 0.0, 45.0)
    van = inst.vehicle_types[0]
    with pytest.raises(ValueError, match="VRP_TRIPS_INVALID"):
        replace(inst, vehicle_types=(replace(van, max_trips=2), inst.vehicle_types[1]))
    with pytest.raises(ValueError, match="VRP_RELOAD_NODE_INVALID"):
        replace(
            inst,
            vehicle_types=(replace(van, max_trips=2, reload_nodes=(0,)), inst.vehicle_types[1]),
        )


# -- time-dependent travel ----------------------------------------------------

_SPEED = st.lists(st.floats(0.3, 1.5), min_size=1, max_size=5)


def _profile(factors: list[float]) -> SpeedProfile:
    starts = tuple(0.0 + 180.0 * k for k in range(len(factors)))
    return SpeedProfile(starts, tuple(factors))


@settings(max_examples=200, deadline=None)
@given(factors=_SPEED, depart=st.floats(-100.0, 1200.0), free=st.floats(0.0, 400.0))
def test_travel_function_is_fifo_and_invertible(
    factors: list[float], depart: float, free: float
) -> None:
    sp = _profile(factors)
    a = arrive(sp, depart, free)
    assert a >= depart
    assert depart_by(sp, a, free) == pytest.approx(depart, abs=1e-6)
    assert arrive(sp, depart + 7.5, free) >= a - 1e-9


def _traffic_instance(seed: int, factors: list[float], cap: float | None) -> Instance:
    base = random_instance(seed, n_requests=7, ride_share=0.0, max_duration=False)
    types = tuple(replace(vt, max_duration=cap) for vt in base.vehicle_types)
    return with_traffic(replace(base, vehicle_types=types), _profile(factors))


@settings(max_examples=60, deadline=None)
@given(seed=st.integers(0, 10_000), factors=_SPEED, size=st.integers(1, 6))
def test_search_check_under_traffic_is_exact_for_windows(
    seed: int, factors: list[float], size: int
) -> None:
    inst = _traffic_instance(seed, factors, None)
    c = Compiled(inst)
    rng = random.Random(seed)
    for _ in range(6):
        nodes = _random_sequence(inst, rng, size)
        for t in range(len(inst.vehicle_types)):
            assert route_exact(c, t, nodes) == route_timing(inst, t, nodes).feasible


@settings(max_examples=40, deadline=None)
@given(seed=st.integers(0, 10_000), factors=_SPEED, cap=st.floats(60.0, 300.0))
def test_search_check_under_traffic_is_sound_with_a_shift_cap(
    seed: int, factors: list[float], cap: float
) -> None:
    inst = _traffic_instance(seed, factors, cap)
    c = Compiled(inst)
    rng = random.Random(seed)
    for _ in range(6):
        nodes = _random_sequence(inst, rng, rng.randint(1, 6))
        for t in range(len(inst.vehicle_types)):
            if route_exact(c, t, nodes):
                assert route_timing(inst, t, nodes).feasible


@settings(max_examples=30, deadline=None)
@given(seed=st.integers(0, 10_000), factors=_SPEED)
def test_shortest_duration_under_traffic_beats_a_fine_grid(seed: int, factors: list[float]) -> None:
    from mobiroute.vrp.traffic import backward, forward

    inst = _traffic_instance(seed, factors, None)
    rng = random.Random(seed)
    nodes = _random_sequence(inst, rng, 4)
    vt = inst.vehicle_types[0]
    timing = route_timing(inst, 0, nodes)
    if not timing.feasible:
        return
    speed = inst.profiles[vt.profile].speed
    assert speed is not None
    seq = [vt.start_depot, *nodes, vt.end_depot]
    e_all = [nd.earliest for nd in inst.nodes]
    s_all = [nd.service for nd in inst.nodes]
    time = inst.profiles[vt.profile].time
    lim = [inst.nodes[n].latest for n in seq]
    lo, hi = timing.earliest[0], backward(speed, seq, lim, s_all, time)[0]
    grid = min(
        forward(speed, seq, x, e_all, s_all, time)[-1] - x
        for x in (lo + (hi - lo) * k / 400 for k in range(401))
    )
    assert timing.min_duration <= grid + 1e-6
    assert timing.min_duration >= grid - (hi - lo) / 400 * 2 - 1e-6


def test_rush_hour_breaks_a_free_flow_plan_and_the_aware_plan_holds() -> None:
    from mobiroute.vrp.generators import cargo_day

    base = cargo_day(1, n_orders=40)
    jam = with_traffic(base)
    free_flow = solve(base, AlnsConfig(iterations=300, seed=1))
    assert free_flow.verdict.feasible
    assert not verify(jam, free_flow.solution).feasible
    aware = solve(jam, AlnsConfig(iterations=300, seed=1))
    assert aware.verdict.feasible and not aware.verdict.unassigned


def test_traffic_round_trip_and_unsupported_mixes() -> None:
    jam = with_traffic(_two_wave_day(1))
    back = instance_from_json(instance_to_json(jam))
    assert back.profiles["default"].speed == jam.profiles["default"].speed
    with pytest.raises(ValueError, match="VRP_TRAFFIC_WITH_RIDE_LIMITS_OR_RESTS"):
        _with_rests(jam, 270.0, 45.0)
    with pytest.raises(ValueError, match="VRP_SPEED_PROFILE_INVALID"):
        with_traffic(_two_wave_day(1), SpeedProfile((0.0, 0.0), (1.0, 0.5)))


# -- split break (15 + 30) ------------------------------------------------------


def _split_day(split: tuple[float, float] | None) -> Instance:
    """Depot, A, B, C on a loop; gap slacks 0, 18, 32 and 2.6 minutes.

    Driving 40 + 40 + 40 + 89.4 = 209.4 > D = 120 needs a break; no gap has
    the 45 minutes a whole break takes, but 18 >= 15 and 32 >= 30.
    """
    pts = [(0.0, 0.0), (40.0, 0.0), (80.0, 0.0), (80.0, 40.0)]
    windows = [(0.0, 262.0), (40.0, 40.0), (98.0, 98.0), (170.0, 170.0)]
    nodes = tuple(
        Node(k, lo, hi, 0.0, x, y)
        for k, ((x, y), (lo, hi)) in enumerate(zip(pts, windows, strict=True))
    )
    requests = tuple(Request(str(k), None, k, (1.0,)) for k in (1, 2, 3))
    vt = VehicleType(
        id="truck",
        capacity=(10.0,),
        count=1,
        shift_start=0.0,
        shift_end=262.0,
        breaks=BreakRule(120.0, 45.0, split),
    )
    return Instance(
        name="split",
        nodes=nodes,
        requests=requests,
        vehicle_types=(vt,),
        profiles=single_profile(euclidean_matrix(pts)),
    )


def test_split_break_fits_where_a_whole_break_does_not() -> None:
    from mobiroute.vrp.native import build_kernel
    from mobiroute.vrp.schedule import compact_schedule, route_arcs
    from mobiroute.vrp.sheets import route_sheets, sheets_markdown

    whole, split = _split_day(None), _split_day((15.0, 30.0))
    route = [1, 2, 3]
    assert not route_timing(whole, 0, route).feasible
    assert not route_exact(Compiled(whole), 0, route)
    timing = route_timing(split, 0, route)
    assert timing.feasible and (timing.first_gap, timing.rest_gap) == (1, 2)
    assert route_exact(Compiled(split), 0, route)
    # The dispatcher's schedule keeps every constraint with both parts in place.
    tight = compact_schedule(split, 0, route)
    _z, arcs = route_arcs(split, 0, route, rest_gap=tight.rest_gap, first_gap=tight.first_gap)
    b = [*tight.earliest, 0.0]
    assert all(b[a.head] - b[a.tail] <= a.weight + 1e-6 for a in arcs)
    plan = Solution([Route(0, route)], set())
    verdict = verify(split, plan)
    assert verdict.feasible
    (sheet,) = route_sheets(split, plan, verdict)
    breaks = [(row.kind, row.end - row.start) for row in sheet.rows if row.kind.startswith("rest")]
    assert breaks == [("rest_first", pytest.approx(15.0)), ("rest", pytest.approx(30.0))]
    # The first part does not reset the counter: 40 + 40 + 40 = 120 before the second.
    assert sheet.longest_stint == pytest.approx(120.0) and sheet.compliant()
    assert "перерыв, 1-я часть" in sheets_markdown([sheet], ("load",))
    assert build_kernel(Compiled(split)) is None  # split breaks run on the reference
    back = instance_from_json(instance_to_json(split))
    assert back.vehicle_types[0].breaks == BreakRule(120.0, 45.0, (15.0, 30.0))
    with pytest.raises(ValueError, match="VRP_BREAK_SPLIT_INVALID"):
        _split_day((0.0, 30.0))


@settings(max_examples=60, deadline=None)
@given(seed=st.integers(0, 10_000), drive=st.floats(30.0, 250.0), size=st.integers(1, 6))
def test_split_break_check_agrees_with_the_verifier(seed: int, drive: float, size: int) -> None:
    base = random_instance(seed, n_requests=7, ride_share=0.4)
    types = tuple(
        replace(vt, breaks=BreakRule(drive, 45.0, (15.0, 30.0))) for vt in base.vehicle_types
    )
    inst = replace(base, vehicle_types=types)
    c = Compiled(inst)
    rng = random.Random(seed)
    for _ in range(6):
        nodes = _random_sequence(inst, rng, size)
        for t in range(len(inst.vehicle_types)):
            assert route_exact(c, t, nodes) == route_timing(inst, t, nodes).feasible
