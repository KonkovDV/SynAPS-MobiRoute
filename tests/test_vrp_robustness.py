"""Hostile input: values a JSON file can carry, plans from elsewhere, refusals.

Each test here pins a defect that was found by trying to break the engine:
``NaN`` accepted as a service time (the verifier then passed the plan with a
cost of ``nan``), the verifier raising ``IndexError`` on a plan with an
unknown vehicle type, the reported shortest shift ignoring better places
for the driver's rest, exact solvers claiming ``OPTIMAL`` for a pricing they
do not model, and OR-Tools serving orders that are cheaper to refuse.
"""

from __future__ import annotations

import math
import random
from dataclasses import replace
from itertools import pairwise
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mobiroute.vrp.generators import random_instance
from mobiroute.vrp.model import (
    BreakRule,
    Instance,
    Node,
    Request,
    SpeedProfile,
    VehicleType,
    euclidean_matrix,
    single_profile,
)
from mobiroute.vrp.schedule import TIME_EPS, _timing_with, compact_schedule, route_timing
from mobiroute.vrp.solution import Route, Solution
from mobiroute.vrp.verify import verify

NAN, INF = math.nan, math.inf


def _line(**node_kw: float) -> Instance:
    """Depot and two customers on a line; ``node_kw`` overrides customer 1."""
    a = {"earliest": 0.0, "latest": 100.0, "service": 5.0, "x": 10.0, "y": 0.0}
    a.update(node_kw)
    nodes = (
        Node(0, 0.0, 1000.0, 0.0, 0.0, 0.0, "depot"),
        Node(1, a["earliest"], a["latest"], a["service"], a["x"], a["y"], "a"),
        Node(2, 0.0, 1000.0, 5.0, 20.0, 0.0, "b"),
    )
    matrix = euclidean_matrix([(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)])
    return Instance(
        "line",
        nodes,
        (Request("r1", None, 1, (1.0,)), Request("r2", None, 2, (1.0,))),
        (VehicleType("v", (10.0,), count=2),),
        single_profile(matrix),
    )


@pytest.mark.parametrize(
    ("override", "code"),
    [
        ({"service": NAN}, "VRP_NODE_WINDOW_INVALID"),
        ({"service": INF}, "VRP_NODE_WINDOW_INVALID"),
        ({"service": -1.0}, "VRP_NODE_WINDOW_INVALID"),
        ({"earliest": NAN}, "VRP_NODE_WINDOW_INVALID"),
        ({"earliest": -INF}, "VRP_NODE_WINDOW_INVALID"),
        ({"latest": NAN}, "VRP_NODE_WINDOW_INVALID"),
        ({"x": NAN}, "VRP_NODE_COORDINATES_INVALID"),
    ],
)
def test_nodes_reject_values_a_json_file_can_carry(override: dict[str, float], code: str) -> None:
    with pytest.raises(ValueError, match=code):
        _line(**override)


def test_an_open_window_and_an_open_shift_stay_allowed() -> None:
    inst = _line(latest=INF)
    assert verify(inst, Solution([Route(0, [1, 2])], set())).feasible


def _with(inst: Instance, **changes: Any) -> Instance:
    return replace(inst, **changes)


def _type(**changes: Any) -> VehicleType:
    return replace(VehicleType("v", (10.0,), count=2), **changes)


@pytest.mark.parametrize(
    ("vehicle", "code"),
    [
        (_type(capacity=(NAN,)), "VRP_CAPACITY_INVALID"),
        (_type(capacity=(INF,)), "VRP_CAPACITY_INVALID"),
        (_type(count=1.5), "VRP_COUNT_INVALID"),
        (_type(count=True), "VRP_COUNT_INVALID"),
        (_type(shift_start=NAN), "VRP_SHIFT_INVALID"),
        (_type(shift_end=NAN), "VRP_SHIFT_INVALID"),
        (_type(max_duration=NAN), "VRP_MAX_DURATION_INVALID"),
        (_type(max_duration=INF), "VRP_MAX_DURATION_INVALID"),
        (_type(fixed_cost=INF), "VRP_COST_INVALID"),
        (_type(cost_per_time=NAN), "VRP_COST_INVALID"),
        (_type(breaks=BreakRule(INF, 45.0)), "VRP_BREAK_RULE_INVALID"),
        (_type(breaks=BreakRule(270.0, NAN)), "VRP_BREAK_RULE_INVALID"),
        (_type(breaks=BreakRule(270.0, 45.0, (NAN, 30.0))), "VRP_BREAK_SPLIT_INVALID"),
    ],
)
def test_vehicle_types_reject_non_finite_numbers(vehicle: VehicleType, code: str) -> None:
    with pytest.raises(ValueError, match=code):
        _with(_line(), vehicle_types=(vehicle,))


@pytest.mark.parametrize(
    ("request_", "code"),
    [
        (Request("r1", None, 1, (NAN,)), "VRP_DEMAND_INVALID"),
        (Request("r1", None, 1, (INF,)), "VRP_DEMAND_INVALID"),
        (Request("r1", None, 1, (1.0,), penalty=NAN), "VRP_PENALTY_INVALID"),
        (Request("r1", None, 1, (1.0,), penalty=INF), "VRP_PENALTY_INVALID"),
        (Request("r1", None, 1, (1.0,), release=NAN), "VRP_RELEASE_INVALID"),
        (Request("r1", 1, 2, (1.0,), max_ride=NAN), "VRP_MAX_RIDE_NEEDS_A_PAIR"),
        (Request("r1", None, True, (1.0,)), "VRP_REQUEST_NODE_OUT_OF_RANGE"),  # type: ignore[arg-type]
    ],
)
def test_requests_reject_non_finite_numbers(request_: Request, code: str) -> None:
    with pytest.raises(ValueError, match=code):
        _with(_line(), requests=(request_,))


def test_instance_rejects_a_nan_vehicle_penalty_and_bad_speed_profiles() -> None:
    with pytest.raises(ValueError, match="VRP_VEHICLE_PENALTY_INVALID"):
        _with(_line(), vehicle_penalty=NAN)
    base = _line()
    profile = base.profiles["default"]
    for speed in (SpeedProfile((0.0, NAN), (1.0, 0.5)), SpeedProfile((0.0, INF), (1.0, 0.5))):
        with pytest.raises(ValueError, match="VRP_SPEED_PROFILE_INVALID"):
            _with(base, profiles={"default": replace(profile, speed=speed)})


# -- the verifier on plans from elsewhere ------------------------------------------


@pytest.mark.parametrize(
    ("plan", "violation"),
    [
        (Solution([Route(5, [1, 2])], set()), "UNKNOWN_VEHICLE_TYPE:0"),
        (Solution([Route(-1, [1, 2])], set()), "UNKNOWN_VEHICLE_TYPE:0"),
        (Solution([Route(0, [1, 99])], {1}), "NOT_A_SERVICE_NODE:99"),
        (Solution([Route(0, [1, -1])], {1}), "NOT_A_SERVICE_NODE:-1"),
        (Solution([Route(0, [1, 2])], {7}), "UNKNOWN_REQUEST_INDEX:7"),
        (Solution([Route(0, [1, 2])], {-3}), "UNKNOWN_REQUEST_INDEX:-3"),
    ],
)
def test_verifier_reports_malformed_plans_instead_of_raising(
    plan: Solution, violation: str
) -> None:
    verdict = verify(_line(), plan)
    assert not verdict.feasible
    assert violation in verdict.violations
    # The cost prices only the well-formed part of the plan, never a wrong type.
    assert math.isfinite(verdict.cost.total)


@settings(max_examples=150, deadline=None)
@given(
    routes=st.lists(
        st.tuples(st.integers(-3, 5), st.lists(st.integers(-4, 12), max_size=6)), max_size=4
    ),
    unassigned=st.sets(st.integers(-3, 9), max_size=4),
)
def test_verifier_never_raises_on_arbitrary_plans(
    routes: list[tuple[int, list[int]]], unassigned: set[int]
) -> None:
    inst = random_instance(3, n_requests=5)
    plan = Solution([Route(t, list(nodes)) for t, nodes in routes], set(unassigned))
    verdict = verify(inst, plan)
    assert isinstance(verdict.feasible, bool)
    assert math.isfinite(verdict.cost.total)


# -- the shortest shift over all places of the driver's rest ------------------------


def _brute_shortest(inst: Instance, t: int, nodes: list[int]) -> float:
    """Shortest feasible duration over every admissible rest place, by enumeration."""
    vt = inst.vehicle_types[t]
    rule = vt.breaks
    assert rule is not None
    time = inst.profiles[vt.profile].time
    seq = [vt.start_depot, *nodes, vt.end_depot]
    legs = [time[a][b] for a, b in pairwise(seq)]
    driving = math.fsum(legs)
    if driving <= rule.max_driving + TIME_EPS:
        return _timing_with(inst, t, nodes, None, driving).min_duration
    best, done, admissible = math.inf, 0.0, []
    for k, leg in enumerate(legs):
        before, after = done, done + leg
        done = after
        if any(
            driving - rule.max_driving - TIME_EPS <= x <= rule.max_driving + TIME_EPS
            for x in (before, after)
        ):
            admissible.append(k)
            timing = _timing_with(inst, t, nodes, k, driving)
            if timing.feasible:
                best = min(best, timing.min_duration)
    if rule.split is not None:
        for k in admissible:
            for first in range(k):
                timing = _timing_with(inst, t, nodes, k, driving, first)
                if timing.feasible:
                    best = min(best, timing.min_duration)
    return best


def _rest_day(seed: int, split: bool) -> tuple[Instance, list[int]]:
    rng = random.Random(seed)
    n = rng.randint(3, 7)
    pts = [(0.0, 0.0)] + [(rng.uniform(-80, 80), rng.uniform(-80, 80)) for _ in range(n)]
    nodes = [Node(0, 0.0, 2000.0, 0.0, 0.0, 0.0, "depot")]
    for k in range(1, n + 1):
        lo = rng.uniform(0.0, 600.0)
        nodes.append(Node(k, lo, lo + rng.uniform(30.0, 400.0), rng.choice([5.0, 10.0, 20.0])))
    rule = BreakRule(120.0, 45.0, (15.0, 30.0) if split else None)
    inst = Instance(
        "rest",
        tuple(nodes),
        tuple(Request(f"r{k}", None, k, (1.0,)) for k in range(1, n + 1)),
        (VehicleType("v", (99.0,), count=1, breaks=rule),),
        single_profile(euclidean_matrix(pts)),
    )
    order = list(range(1, n + 1))
    rng.shuffle(order)
    return inst, order


@pytest.mark.parametrize("split", [False, True], ids=["whole", "split"])
def test_reported_shift_is_the_shortest_over_every_rest_place(split: bool) -> None:
    checked = 0
    for seed in range(600):
        inst, order = _rest_day(seed, split)
        timing = route_timing(inst, 0, order)
        if not timing.feasible:
            continue
        assert timing.min_duration == pytest.approx(_brute_shortest(inst, 0, order), abs=1e-6)
        # The dispatcher's schedule realises that duration with the chosen place.
        tight = compact_schedule(inst, 0, order)
        assert tight.earliest[-1] - tight.earliest[0] == pytest.approx(
            timing.min_duration, abs=1e-6
        )
        checked += 1
    assert checked >= 5


def _first_feasible_place(inst: Instance, order: list[int]) -> float:
    """What the reported shift used to be: the first admissible gap that fits."""
    vt = inst.vehicle_types[0]
    assert vt.breaks is not None
    time = inst.profiles[vt.profile].time
    seq = [vt.start_depot, *order, vt.end_depot]
    legs = [time[a][b] for a, b in pairwise(seq)]
    driving, done = math.fsum(legs), 0.0
    for k, leg in enumerate(legs):
        before, after = done, done + leg
        done = after
        if any(driving - 120.0 - TIME_EPS <= x <= 120.0 + TIME_EPS for x in (before, after)):
            timing = _timing_with(inst, 0, order, k, driving)
            if timing.feasible:
                return timing.min_duration
    return math.inf


def test_a_rest_hidden_in_waiting_time_shortens_the_reported_shift() -> None:
    """Days where the first admissible gap adds the whole 45 minutes and a later
    one hides the rest in waiting: the shift must be the shorter one, which is
    what a duty-time tariff pays for and what the route sheet shows."""
    gains = []
    for seed in range(600):
        inst, order = _rest_day(seed, False)
        timing = route_timing(inst, 0, order)
        if not timing.feasible:
            continue
        old = _first_feasible_place(inst, order)
        assert timing.min_duration <= old + 1e-6
        if timing.min_duration < old - 1.0:
            no_rest = _timing_with(inst, 0, order, None, timing.driving)
            assert no_rest.feasible and timing.min_duration >= no_rest.min_duration - 1e-6
            gains.append(old - timing.min_duration)
    # One more rest constraint moves the shortest duration by at most the
    # rest's length, so no place can be more than 45 minutes worse than another.
    assert gains and max(gains) > 10.0 and max(gains) <= 45.0 + 1e-6


# -- solvers refuse what they do not model -------------------------------------------


def test_exact_and_ortools_refuse_a_paid_shift() -> None:
    from mobiroute.vrp.exact import solve_exact
    from mobiroute.vrp.ortools_baseline import solve_ortools

    duty = replace(random_instance(4, n_requests=4), time_cost="duty")
    with pytest.raises(ValueError, match="EXACT_DUTY_TIME_COST_UNSUPPORTED"):
        solve_exact(duty, time_limit=1.0)
    with pytest.raises(ValueError, match="ORTOOLS_DUTY_TIME_COST_UNSUPPORTED"):
        solve_ortools(duty, time_limit=1.0)


def test_ortools_refuses_an_order_that_costs_more_than_its_penalty() -> None:
    """A far pair with a small penalty: refusing it is cheaper, and OR-Tools,
    given the order's own penalty, does refuse it (before the fix every order
    carried the must-serve penalty, so OR-Tools drove out to it)."""
    from mobiroute.vrp.ortools_baseline import solve_ortools

    pts = [(0.0, 0.0), (5.0, 0.0), (6.0, 0.0), (400.0, 0.0), (401.0, 0.0)]
    nodes = tuple(Node(k, 0.0, 5000.0, 0.0, x, y) for k, (x, y) in enumerate(pts))
    requests = (
        Request("near", 1, 2, (1.0,)),
        Request("far", 3, 4, (1.0,), penalty=50.0),
    )
    inst = Instance(
        "far-order",
        nodes,
        requests,
        (VehicleType("v", (5.0,), count=2),),
        single_profile(euclidean_matrix(pts)),
    )
    run = solve_ortools(inst, time_limit=2.0)
    assert run.verdict.feasible
    assert run.solution.unassigned == {1}
    assert run.verdict.cost.total + 50.0 < 800.0
