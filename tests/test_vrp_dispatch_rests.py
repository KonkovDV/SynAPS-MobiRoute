"""Live dispatch with drivers' breaks, and what the dispatcher reports.

The rule is the static one (one break per shift; at most 4.5 h of driving on
each side of it; a split break restarts the count only after its last part),
carried over the part of a route already driven. Every plan is checked by
the independent verifier, which knows nothing about the dispatcher.
"""

from __future__ import annotations

import json
from dataclasses import replace
from itertools import pairwise
from pathlib import Path

import pytest

from mobiroute.cli import main
from mobiroute.vrp.generators import plant_day
from mobiroute.vrp.model import (
    BreakRule,
    Instance,
    Node,
    Request,
    VehicleType,
    euclidean_matrix,
    single_profile,
)
from mobiroute.vrp.realtime import Dispatcher, simulate

RULE = BreakRule(270.0, 45.0, split=(15.0, 30.0))


def _with_rule(inst: Instance, rule: BreakRule = RULE) -> Instance:
    return replace(inst, vehicle_types=tuple(replace(vt, breaks=rule) for vt in inst.vehicle_types))


def _driving_around_breaks(d: Dispatcher) -> list[tuple[float, float]]:
    """Per used vehicle: driving before its final break and after it."""
    out = []
    for u in d.units:
        if not u.plan:
            continue
        time = d.c.time[u.t]
        seq = [d.c.start[u.t], *u.plan, d.c.end[u.t]]
        total = sum(time[a][b] for a, b in pairwise(seq))
        finals = [rest.driven for rest in u.rests if rest.final]
        before = finals[0] if finals else total
        out.append((before, total - before))
    return out


@pytest.mark.parametrize("area", [4.0, 12.0])
def test_breaks_keep_every_route_legal(area: float) -> None:
    inst = _with_rule(plant_day(5, n_moves=140, area_km=area))
    d = Dispatcher(inst)
    report = d.run()
    assert report.verified, report.violations
    assert report.kpi["breaks"] >= 1
    for before, after in _driving_around_breaks(d):
        assert before <= 270.0 + 1e-6 and after <= 270.0 + 1e-6
    plain = simulate(plant_day(5, n_moves=140, area_km=area))
    assert report.kpi["accepted"] <= plain.kpi["accepted"]


def test_a_break_once_begun_is_never_moved() -> None:
    inst = _with_rule(plant_day(5, n_moves=140, area_km=12.0))
    d = Dispatcher(inst)
    order = sorted(range(inst.n_requests), key=lambda r: (inst.requests[r].release, r))
    for r in order:
        tau = inst.requests[r].release
        begun = {(k, rest) for k, u in enumerate(d.units) for rest in u.rests if rest.start <= tau}
        d._insert(r, tau)
        kept = {(k, rest) for k, u in enumerate(d.units) for rest in u.rests}
        assert begun <= kept


def _one_far_order(shift_end: float) -> Instance:
    """One delivery 40 min away with a one-minute window; 60 min of driving allowed."""
    pts = [(0.0, 0.0), (40.0, 0.0)]
    nodes = (
        Node(0, 0.0, shift_end, 0.0, *pts[0], "depot"),
        Node(1, 40.0, 41.0, 5.0, *pts[1], "far"),
    )
    van = VehicleType("van", (1.0,), count=1, shift_end=shift_end, breaks=BreakRule(60.0, 30.0))
    return Instance(
        "far", nodes, (Request("o1", None, 1, (1.0,)),), (van,),
        single_profile(euclidean_matrix(pts)),
    )  # fmt: skip


def test_an_order_with_no_legal_place_for_the_break_is_refused() -> None:
    # 80 min of driving needs a break; it cannot come before the stop (the
    # window would close) and on the way back the shift would end first.
    refused = simulate(_one_far_order(100.0))
    (decision,) = refused.decisions
    assert not decision.accepted and "driver's break" in decision.reason
    # With a longer shift the break goes on the way back.
    taken = simulate(_one_far_order(200.0))
    assert taken.decisions[0].accepted and taken.verified
    ((unit, gap, start, minutes, final),) = taken.rests
    assert (unit, gap, minutes, final) == (0, 1, 30.0, True) and start >= 45.0


def test_a_split_break_is_used_when_a_whole_one_does_not_fit() -> None:
    """Waits of 15 and 30 minutes, no gap of 45: the break is split 15 + 30.

    Stops at 20, 50 and 80 minutes from the depot with one-minute windows at
    35, 65 and 125; 160 minutes of driving against a limit of 100.
    """
    pts = [(0.0, 0.0), (20.0, 0.0), (50.0, 0.0), (80.0, 0.0)]
    windows = [(0.0, 210.0), (35.0, 36.0), (65.0, 66.0), (125.0, 126.0)]
    nodes = tuple(
        Node(k, lo, hi, 0.0, x, y)
        for k, ((x, y), (lo, hi)) in enumerate(zip(pts, windows, strict=True))
    )
    reqs = tuple(Request(f"o{k}", None, k, (1.0,)) for k in (1, 2, 3))
    van = VehicleType("van", (5.0,), count=1, shift_end=210.0,
                      breaks=BreakRule(100.0, 45.0, split=(15.0, 30.0)))  # fmt: skip
    inst = Instance("split", nodes, reqs, (van,), single_profile(euclidean_matrix(pts)))
    report = simulate(inst)
    assert all(d.accepted for d in report.decisions) and report.verified
    parts = sorted((gap, minutes, final) for _, gap, _, minutes, final in report.rests)
    assert parts == [(0, 15.0, False), (2, 30.0, True)]
    # Without the split the third stop cannot be served.
    whole = replace(inst, vehicle_types=(replace(van, breaks=BreakRule(100.0, 45.0)),))
    assert [d.accepted for d in simulate(whole).decisions] == [True, True, False]


def test_rest_days_run_on_the_insertion_policy_only() -> None:
    inst = _with_rule(plant_day(5, n_moves=20))
    for policy in ("insertion+alns", "ortools-resolve"):
        with pytest.raises(ValueError, match="REALTIME_RESTS_NEED_THE_INSERTION_POLICY"):
            Dispatcher(inst, policy=policy)  # type: ignore[arg-type]


def test_the_service_at_the_current_stop_counts_once() -> None:
    """A vehicle finishing a stop at 20 reaches a stop 10 min away by 30.

    The dispatcher used to add the service time of the stop the vehicle was
    at a second time and refused an order it could serve.
    """
    pts = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
    nodes = (
        Node(0, 0.0, 500.0, 0.0, *pts[0], "depot"),
        Node(1, 0.0, 100.0, 10.0, *pts[1], "a"),
        Node(2, 0.0, 31.0, 1.0, *pts[2], "b"),
    )
    reqs = (Request("a", None, 1, (1.0,)), Request("b", None, 2, (1.0,), release=15.0))
    van = VehicleType("van", (5.0,), count=1)
    inst = Instance("once", nodes, reqs, (van,), single_profile(euclidean_matrix(pts)))
    report = simulate(inst)
    assert [d.accepted for d in report.decisions] == [True, True] and report.verified


def test_the_report_counts_orders_no_vehicle_type_can_carry() -> None:
    report = simulate(plant_day(11, n_moves=140))
    k = report.kpi
    assert k["uncarriable"] == 2.0
    assert k["acceptance_of_carriable"] == pytest.approx(k["accepted"] / 138, abs=1e-4)


def test_cli_dispatch_with_breaks(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "out"
    code = main(["vrp-dispatch", "--day", "plant", "--orders", "60", "--rests",
                 "--out-dir", str(out)])  # fmt: skip
    assert code == 0
    data = json.loads((out / "dispatch.json").read_text(encoding="utf-8"))
    assert data["verified"] and "breaks" in data["kpi"] and isinstance(data["rests"], list)
    assert "breaks" in capsys.readouterr().out
    code = main(["vrp-dispatch", "--day", "plant", "--orders", "20", "--rests",
                 "--policy", "insertion+alns", "--out-dir", str(out)])  # fmt: skip
    assert code == 2
    assert "REALTIME_RESTS_NEED_THE_INSERTION_POLICY" in capsys.readouterr().err
