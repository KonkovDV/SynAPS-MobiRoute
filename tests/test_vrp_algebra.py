"""The algebra in the formulation, checked against the code that claims it.

Lemma 1: a rest is a cut of the driving, and the cut is admissible exactly when
both stints are within the limit. A leg longer than the limit cannot be cut.
The shortest-duration identity of section 2 is the latest feasible departure.
Lemma 1c is the same cut on a route that has already left the depot: a
re-optimisation proposal is kept only when the open suffix still admits it.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mobiroute.vrp.generators import random_instance
from mobiroute.vrp.io import instance_from_json, instance_to_json
from mobiroute.vrp.model import (
    BreakRule,
    Instance,
    Node,
    Request,
    VehicleType,
    euclidean_matrix,
    single_profile,
)
from mobiroute.vrp.realtime import Dispatcher, Rest
from mobiroute.vrp.schedule import route_timing
from mobiroute.vrp.solution import Route, Solution


def _stints_allow(
    legs: list[float], limit: float, *, prior: float = 0.0, taken: bool = False
) -> bool:
    """Lemma 1 as a statement about partial sums, with no schedule in it.

    ``prior`` is driving already done. ``taken`` means the one final break is
    behind the driver, so the remaining budget is ``limit - prior`` and no
    new break is placed.
    """
    total = prior + math.fsum(legs)
    if taken or total <= limit:
        return total <= limit
    if total > 2.0 * limit:
        return False
    done = prior
    for leg in legs:
        before, after = done, done + leg
        if limit >= before >= total - limit or limit >= after >= total - limit:
            return True
        done = after
    return False


def _line(
    legs: list[float], limit: float, *, prior: float = 0.0, taken: bool = False
) -> tuple[Instance, list[int]]:
    """Stops on a line, so each leg is exactly the distance written down."""
    xs = [0.0]
    for leg in legs:
        xs.append(xs[-1] + leg)
    nodes = tuple(Node(k, 0.0, 1.0e7, 0.0, x, 0.0) for k, x in enumerate(xs))
    last = len(xs) - 1
    requests = tuple(Request(f"r{k}", None, k, (1.0,)) for k in range(1, last))
    van = VehicleType(
        "van",
        (9.0,),
        count=1,
        end_depot=last,
        shift_end=1.0e7,
        breaks=BreakRule(limit, 5.0),
        prior_driving=prior,
        break_taken=taken,
    )
    inst = Instance(
        "line", nodes, requests, (van,), single_profile(euclidean_matrix([(x, 0.0) for x in xs]))
    )
    return inst, list(range(1, last))


@settings(max_examples=80, deadline=None)
@given(
    # Whole minutes, so the cut is exact arithmetic and not a tolerance.
    legs=st.lists(st.integers(1, 80), min_size=2, max_size=6),
    limit=st.integers(10, 120),
)
def test_a_rest_is_admissible_exactly_when_both_stints_fit(legs: list[int], limit: int) -> None:
    inst, nodes = _line(legs, limit)
    assert route_timing(inst, 0, nodes).feasible == _stints_allow(legs, limit)


@settings(max_examples=60, deadline=None)
@given(
    legs=st.lists(st.integers(1, 40), min_size=2, max_size=5),
    limit=st.integers(15, 80),
    prior=st.integers(0, 70),
    taken=st.booleans(),
)
def test_driving_already_done_shifts_the_cut(
    legs: list[int], limit: int, prior: int, taken: bool
) -> None:
    """The same cut, started at the driving the driver has already done."""
    inst, nodes = _line(legs, limit, prior=float(prior), taken=taken)
    assert route_timing(inst, 0, nodes).feasible == _stints_allow(
        legs, limit, prior=float(prior), taken=taken
    )


@settings(max_examples=40, deadline=None)
@given(
    short=st.floats(0.5, 30.0),
    over=st.floats(0.1, 40.0),
    limit=st.floats(15.0, 80.0),
    first=st.booleans(),
)
def test_a_leg_longer_than_the_limit_cannot_be_cut(
    short: float, over: float, limit: float, first: bool
) -> None:
    """The long leg lies wholly on one side of every cut, so that side exceeds D."""
    long = limit + over
    legs = [long, short] if first else [short, long]
    # Keep the total inside the two-stint budget, or the refusal would be the
    # 2D cap rather than the unsplittable leg.
    if sum(legs) > 2.0 * limit:
        return
    inst, nodes = _line(legs, limit)
    timing = route_timing(inst, 0, nodes)
    assert not timing.feasible
    assert timing.infeasibility is not None
    assert "DRIVING" in timing.infeasibility.labels


def _duration_by_latest_departure(inst: Instance, vehicle: int, nodes: list[int]) -> float:
    """Section 2: max(G0, A - t*) with depot windows tightened to the shift."""
    vt = inst.vehicle_types[vehicle]
    time = inst.profiles[vt.profile].time
    seq = [vt.start_depot, *nodes, vt.end_depot]
    earliest = [inst.nodes[k].earliest for k in seq]
    latest = [inst.nodes[k].latest for k in seq]
    service = [inst.nodes[k].service for k in seq]
    earliest[0] = max(earliest[0], vt.shift_start)
    latest[0] = min(latest[0], vt.shift_end)
    latest[-1] = min(latest[-1], vt.shift_end)
    ahead = [0.0]
    for k in range(len(seq) - 1):
        a, b = seq[k], seq[k + 1]
        ahead.append(ahead[-1] + service[k] + time[a][b])
    total = ahead[-1]
    depart = min(latest[k] - ahead[k] for k in range(len(seq)))
    forced = max(earliest[k] + (total - ahead[k]) for k in range(1, len(seq)))
    return max(total, forced - depart)


@settings(max_examples=40, deadline=None)
@given(seed=st.integers(0, 10_000), size=st.integers(1, 5))
def test_shortest_duration_is_attained_at_the_latest_departure(seed: int, size: int) -> None:
    inst = random_instance(seed, n_requests=6, ride_share=0.0, pair_share=0.0, max_duration=False)
    if any(r.max_ride is not None for r in inst.requests):
        return
    if any(vt.breaks is not None or vt.max_duration is not None for vt in inst.vehicle_types):
        return
    if inst.has_traffic:
        return
    deliveries = [r.delivery for r in inst.requests if r.delivery is not None][:size]
    if not deliveries:
        return
    timing = route_timing(inst, 0, deliveries)
    if not timing.feasible:
        return
    assert timing.min_duration == pytest.approx(
        _duration_by_latest_departure(inst, 0, deliveries), abs=1e-6
    )


def test_reoptimisation_keeps_only_a_legal_cheaper_continuation() -> None:
    """Lemma 1c, by hand. The driver has already taken the break at A.

    The open stops are B then C. C then B is shorter and still within the
    residual allowance; the far stop is not, and that proposal is declined
    with the begun break left untouched.
    """
    pts = [(0.0, 0.0), (20.0, 0.0), (20.0, 30.0), (20.0, 5.0), (20.0, 200.0)]
    nodes = (
        Node(0, 0.0, 1.0e6, 0.0, *pts[0], "depot"),
        Node(1, 0.0, 1.0e6, 30.0, *pts[1], "A"),
        Node(2, 0.0, 1.0e6, 0.0, *pts[2], "B"),
        Node(3, 0.0, 1.0e6, 0.0, *pts[3], "C"),
        Node(4, 0.0, 1.0e6, 0.0, *pts[4], "far"),
    )
    reqs = tuple(Request(name, None, k, (1.0,)) for k, name in enumerate("ABCD", start=1))
    van = VehicleType("van", (5.0,), count=1, shift_end=1.0e6, breaks=BreakRule(100.0, 10.0))
    inst = Instance("continuation", nodes, reqs, (van,), single_profile(euclidean_matrix(pts)))
    dispatcher = Dispatcher(inst, policy="insertion+alns", reoptimize_every=1.0e9)
    unit = dispatcher.units[0]
    unit.used = True
    unit.left = 0.0
    unit.plan = [1, 2, 3]
    unit.starts = [20.0, 400.0, 500.0]
    begun = Rest(gap=1, start=25.0, minutes=10.0, driven=20.0, final=True)
    unit.rests = [begun]
    tau = 40.0
    snap, plan, owners = dispatcher.snapshot(tau)
    # The break at A has reset the counter, so the open route starts at R = 0
    # and may not take another break. The far stop then exceeds the allowance
    # inside the snapshot itself, before any proposal is filtered.
    (snap_type,) = (vt for vt in snap.vehicle_types if vt.break_taken)
    assert snap_type.prior_driving == pytest.approx(0.0)
    assert snap_type.breaks is not None and snap_type.breaks.max_driving == pytest.approx(100.0)
    seeded = next(route.nodes for route in plan.routes)
    assert route_timing(snap, 0, seeded).feasible
    assert not route_timing(snap, 0, [4]).feasible
    restored = instance_from_json(instance_to_json(snap)).vehicle_types[0]
    assert restored.break_taken and restored.prior_driving == pytest.approx(snap_type.prior_driving)
    (kind, ref) = owners[0]
    assert (kind, ref) == (0, 0)
    before = dispatcher._live_cost()
    assert before is not None

    assert dispatcher._apply_if_breaks_hold(tau, Solution([Route(0, [4])], set()), owners) is False
    assert unit.plan == [1, 2, 3] and unit.rests == [begun]
    assert dispatcher._live_cost() == pytest.approx(before)

    assert dispatcher._apply_if_breaks_hold(tau, Solution([Route(0, [3, 2])], set()), owners)
    assert unit.plan == [1, 3, 2]
    assert begun in unit.rests
    after = dispatcher._live_cost()
    assert after is not None and after < before - 1e-6
