"""Hostile input: values a JSON file can carry, plans from elsewhere, refusals.

Each test here pins a defect that was found by trying to break the engine:
``NaN`` accepted as a service time (the verifier then passed the plan with a
cost of ``nan``), the verifier raising ``IndexError`` on a plan with an
unknown vehicle type, the reported shortest shift ignoring better places
for the driver's rest, exact solvers claiming ``OPTIMAL`` for a pricing they
do not model, and OR-Tools serving orders that are cheaper to refuse.
"""

from __future__ import annotations

import contextlib
import copy
import json
import math
import random
from collections.abc import Callable, Iterator
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mobiroute.vrp import geo
from mobiroute.vrp.generators import cargo_day, random_instance
from mobiroute.vrp.io import instance_from_dict, instance_to_dict
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


# -- input files: one broken field at a time ---------------------------------------

ROOT = Path(__file__).resolve().parents[1]
JUNK: tuple[Any, ...] = (None, "x", -1, 0, 1e308, NAN, INF, [], {}, [1, 2], "25:00", True)


def _paths(obj: Any, prefix: tuple[Any, ...] = ()) -> Iterator[tuple[Any, ...]]:
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield (*prefix, key)
            yield from _paths(value, (*prefix, key))
    elif isinstance(obj, list):
        for i, value in enumerate(obj[:3]):
            yield (*prefix, i)
            yield from _paths(value, (*prefix, i))


def _broken(doc: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    """The document with one field replaced by junk or removed."""
    doc = copy.deepcopy(doc)
    path = rng.choice(list(_paths(doc)))
    parent: Any = doc
    for key in path[:-1]:
        parent = parent[key]
    if isinstance(parent, dict) and rng.random() < 0.3:
        del parent[path[-1]]
    else:
        parent[path[-1]] = rng.choice(JUNK)
    return doc


@pytest.mark.parametrize("loader", ["geo", "json"])
def test_a_broken_input_file_ends_in_a_value_error(loader: str) -> None:
    """Whatever field is wrong, the loader answers with ``ValueError``.

    Before the fix one mutation in three escaped as ``TypeError``,
    ``KeyError`` or ``OverflowError`` from deep inside the loader.
    """
    if loader == "geo":
        base = json.loads((ROOT / "examples" / "chelny-day.geo.json").read_text(encoding="utf-8"))
        load: Callable[[dict[str, Any]], object] = geo.build
    else:
        base = instance_to_dict(cargo_day(3, n_orders=8))
        load = instance_from_dict
    rng = random.Random(1)
    for _ in range(600):
        with contextlib.suppress(ValueError):
            load(_broken(base, rng))


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


def test_json_and_geo_refuse_a_fractional_fleet_count() -> None:
    data = json.loads(json.dumps(instance_to_dict(cargo_day(1, n_orders=2))))
    data["vehicle_types"][0]["count"] = 2.7
    with pytest.raises(ValueError, match="VRP_COUNT_INVALID"):
        instance_from_dict(data)
    data["vehicle_types"][0]["count"] = True
    with pytest.raises(ValueError, match="VRP_COUNT_INVALID"):
        instance_from_dict(data)

    example = Path(__file__).resolve().parents[1] / "examples" / "chelny-day.geo.json"
    raw = json.loads(example.read_text(encoding="utf-8"))
    raw["vehicle_types"][0]["count"] = 1.5
    with pytest.raises(ValueError, match="VRP_COUNT_INVALID"):
        geo.build(raw)
    raw["vehicle_types"][0]["count"] = 4
    raw["traffic"] = {"starts": ["00:00", "08:00"], "factors": [1.0, 0.6]}
    with pytest.raises(ValueError, match="VRP_TRAFFIC_WITH_RIDE_LIMITS_OR_RESTS"):
        geo.build(raw)


def test_the_cli_fails_when_a_mandatory_order_is_left_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import mobiroute.vrp.alns as alns
    from mobiroute.cli import main
    from mobiroute.vrp.alns import SolveResult

    def fake(inst: Instance, config: object = None, initial: object = None) -> SolveResult:
        sol = Solution([], set(range(inst.n_requests)))
        verdict = verify(inst, sol)
        assert verdict.feasible and not verdict.complete
        assert "INCOMPLETE" in verdict.summary()
        return SolveResult(inst.name, sol, verdict, 0.0, 1, 0.0, "python", 1)

    monkeypatch.setattr(alns, "solve", fake)
    out = tmp_path / "out"
    code = main(
        [
            "vrp-solve",
            "--generate",
            "cargo",
            "--orders",
            "4",
            "--iterations",
            "1",
            "--out-dir",
            str(out),
        ]
    )
    # 3, not 2: the plan is legal and written; 2 is kept for refused input
    # and broken plans, so a script can tell the two apart.
    assert code == 3
    report = json.loads((out / "verdict.json").read_text(encoding="utf-8"))
    assert report["feasible"] is True and report["complete"] is False
    assert report["unassigned"]
    printed = capsys.readouterr().out
    assert "mandatory orders left out: T000, D001, D002, D003" in printed
    assert "no vehicle type can carry" not in printed  # every order of the day fits a type


@pytest.mark.parametrize(
    ("path", "value", "code"),
    [
        (("vehicle_types", 0, "start_depot"), 0.5, "start_depot"),
        (("vehicle_types", 0, "start_depot"), True, "start_depot"),
        (("vehicle_types", 0, "end_depot"), "0", "end_depot"),
        (("vehicle_types", 0, "max_trips"), 2.5, "VRP_TRIPS_INVALID"),
        (("vehicle_types", 0, "max_trips"), 0, "VRP_TRIPS_INVALID"),
        (("vehicle_types", 0, "reload_nodes"), [1.5], "reload_nodes"),
        (("vehicle_types", 0, "reload_nodes"), "12", "reload_nodes"),
        (("requests", 0, "delivery"), 2.0, "delivery"),
        (("nodes", 1, "id"), 1.0, "nodes.id"),
    ],
)
def test_json_whole_numbers_are_not_rounded(path: tuple[Any, ...], value: Any, code: str) -> None:
    """Every whole-number field follows the fleet count: ``int()`` would change the file."""
    data = json.loads(json.dumps(instance_to_dict(cargo_day(1, n_orders=2))))
    node: Any = data
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(ValueError, match=code):
        instance_from_dict(data)


@pytest.mark.parametrize("value", [2.5, True, "2", 0])
def test_geo_trip_limit_is_a_whole_number(value: Any) -> None:
    example = Path(__file__).resolve().parents[1] / "examples" / "chelny-day.geo.json"
    raw = json.loads(example.read_text(encoding="utf-8"))
    raw["vehicle_types"][0]["trips"] = {"max": value, "reload_min": 30}
    with pytest.raises(ValueError, match="VRP_TRIPS_INVALID"):
        geo.build(raw)


def test_a_huge_fleet_does_not_grow_the_instance() -> None:
    """Reload stops, OR-Tools vehicles and live units stop at the number of orders.

    Before the cap a geo file with 20,000 vans and three trips asked for
    40,000 reload stops and matrices of 1.6e9 cells per profile, and the
    live dispatcher built a billion units. OR-Tools already capped its own.
    """
    from mobiroute.vrp.ortools_baseline import solve_ortools
    from mobiroute.vrp.realtime import Dispatcher

    example = Path(__file__).resolve().parents[1] / "examples" / "chelny-day.geo.json"
    raw = json.loads(example.read_text(encoding="utf-8"))
    raw["vehicle_types"][0]["count"] = 20_000
    raw["vehicle_types"][0]["trips"] = {"max": 3, "reload_min": 30}
    built = geo.build(raw)
    inst = built.instance
    van = next(vt for vt in inst.vehicle_types if vt.reload_nodes)
    assert len(van.reload_nodes) == inst.n_requests
    assert inst.n_nodes <= 3 * inst.n_requests + 10

    day = cargo_day(1, n_orders=6)
    huge = replace(day, vehicle_types=tuple(replace(vt, count=10**9) for vt in day.vehicle_types))
    run = solve_ortools(huge, time_limit=1.0)
    assert run.verdict.feasible
    assert len(Dispatcher(huge).units) == 6 * len(huge.vehicle_types)
