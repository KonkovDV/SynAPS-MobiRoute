"""Policy-shaped ops scenarios: Moscow social-taxi rules + world paratransit practice."""

from __future__ import annotations

from collections import Counter

from mobiroute.adapters.ops_scenarios import OPS_MODES, generate_ops_day
from mobiroute.adapters.synthetic_data import generate_day
from mobiroute.dispatch.online_insertion import recover_disruption
from mobiroute.domain.models import StopType
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.validation.feasibility import check_plan


def test_ops_modes_deterministic() -> None:
    for mode in OPS_MODES:
        a = generate_day(mode, seed=7)
        b = generate_day(mode, seed=7)
        assert a.model_dump(mode="json") == b.model_dump(mode="json")
        assert a.claim_level == "synthetic_benchmark"
        assert a.vehicles
        assert a.drivers
        assert a.requests


def test_wait_return_same_vehicle_no_interleave() -> None:
    p = generate_ops_day("ops_wait_return", seed=42)
    out = next(t for t in p.requests if t.trip_purpose == "MEDICAL" and t.same_vehicle_as is None)
    ret = next(t for t in p.requests if t.same_vehicle_as == out.id)
    res = solve_greedy(p)
    report = check_plan(p, res)
    assert report.feasible or not res.verified_feasible
    if out.id in res.served_requests and ret.id in res.served_requests:
        host = None
        for rp in res.route_plans:
            ids = [s.trip_id for s in rp.ordered_stops if s.trip_id]
            if out.id in ids and ret.id in ids:
                host = rp
                break
        assert host is not None
        core = [
            s
            for s in host.ordered_stops
            if s.stop_type in {StopType.PICKUP, StopType.DROPOFF} and s.trip_id
        ]
        out_do = next(
            i for i, s in enumerate(core) if s.trip_id == out.id and s.stop_type == StopType.DROPOFF
        )
        ret_pu = next(
            i for i, s in enumerate(core) if s.trip_id == ret.id and s.stop_type == StopType.PICKUP
        )
        assert ret_pu == out_do + 1


def test_wav_shortage_explains_rejects() -> None:
    p = generate_ops_day("ops_wav_shortage", seed=42)
    res = solve_greedy(p)
    assert res.status != "OPTIMAL"
    assert res.claim_level == "synthetic_benchmark"
    wc = [t.id for t in p.requests if t.wheelchair_requirement.value != "NONE"]
    if len(res.served_requests) < len(wc):
        codes = {r.reason_code for r in res.rejected_requests}
        assert "" not in codes
        assert codes


def test_companions_fit_sedan() -> None:
    p = generate_ops_day("ops_companions", seed=42)
    res = solve_greedy(p)
    assert p.requests[0].companion_count == 2
    report = check_plan(p, res)
    if res.verified_feasible:
        assert report.feasible
        assert p.requests[0].id in res.served_requests


def test_palliative_not_dropped_silently() -> None:
    p = generate_ops_day("ops_palliative", seed=42)
    pal = next(t for t in p.requests if t.channel == "PALLIATIVE_ID")
    res = solve_greedy(p)
    if pal.id not in res.served_requests:
        assert res.reason_codes.get(pal.id)
    else:
        assert pal.id in res.served_requests


def test_group_bus_can_pool() -> None:
    p = generate_ops_day("ops_group", seed=42)
    res = solve_greedy(p)
    assert res.verified_feasible
    assert len(res.served_requests) >= 4
    loads = []
    for rp in res.route_plans:
        if rp.passenger_load_after_stop:
            loads.append(max(rp.passenger_load_after_stop.values()))
    assert loads
    assert max(loads) >= 2


def test_shift_close_does_not_claim_optimal() -> None:
    p = generate_ops_day("ops_shift_close", seed=42)
    res = solve_greedy(p)
    assert res.status != "OPTIMAL"
    report = check_plan(p, res)
    if res.verified_feasible:
        assert report.feasible


def test_subscription_frozen_then_cancel_recovery() -> None:
    p = generate_ops_day("ops_subscription_vs_nextday", seed=42)
    res = solve_greedy(p)
    assert res.status != "OPTIMAL"
    if not res.served_requests:
        return
    _u, rec, diff = recover_disruption(p, res, cancel_trip_id=res.served_requests[0])
    assert rec.event_type == "CANCELLATION"
    assert rec.claim_level == "synthetic_benchmark"
    assert "changed_trips" in diff.plan_churn


def test_ops_suite_greedy_never_optimal() -> None:
    from mobiroute.reporting.ops_benchmark import run_suite

    rows = run_suite(seed=42)
    greedy = [r for r in rows if r["algorithm"] == "GREEDY"]
    assert greedy
    assert all(r["optimal_claimed"] is False for r in greedy)
    assert all(r["claim_level"] == "synthetic_benchmark" for r in rows)
    hist = Counter(str(r["scenario"]) for r in greedy)
    assert set(hist) == set(OPS_MODES)


def test_stretcher_exclusive_on_ops_script() -> None:
    p = generate_ops_day("ops_stretcher", seed=42)
    res = solve_greedy(p)
    assert res.status != "OPTIMAL"
    st = next(t for t in p.requests if t.wheelchair_requirement.value == "STRETCHER")
    if st.id in res.served_requests:
        for rp in res.route_plans:
            if st.id not in rp.passenger_assignments:
                continue
            for sid, w in (rp.wheelchair_load_after_stop or {}).items():
                if w >= 1:
                    assert (rp.passenger_load_after_stop or {}).get(sid, 0) <= 1


def test_scooter_rejected_on_default_wav() -> None:
    p = generate_ops_day("ops_scooter", seed=42)
    res = solve_greedy(p)
    assert p.requests[0].id not in res.served_requests
    assert res.reason_codes[p.requests[0].id] == "NO_COMPATIBLE_VEHICLE"


def test_medical_outranks_dacha_when_tight() -> None:
    p = generate_ops_day("ops_medical_vs_dacha", seed=42)
    med = next(t for t in p.requests if t.trip_purpose == "MEDICAL")
    dacha = next(t for t in p.requests if t.trip_purpose == "DACHA")
    res = solve_greedy(p)
    assert med.id in res.served_requests
    assert dacha.id not in res.served_requests


def test_service_area_ops_rejects() -> None:
    p = generate_ops_day("ops_service_area", seed=42)
    res = solve_greedy(p)
    assert p.requests[0].id not in res.served_requests
    assert res.reason_codes[p.requests[0].id]


def test_untrained_driver_cannot_board_wheelchair() -> None:
    p = generate_ops_day("ops_untrained_driver", seed=42)
    res = solve_greedy(p)
    assert p.requests[0].id not in res.served_requests
    assert res.reason_codes[p.requests[0].id] in {"NO_DRIVER", "DRIVER_SHIFT_CONFLICT"}


def test_agency_missed_is_not_passenger_no_show() -> None:
    p = generate_ops_day("ops_agency_missed", seed=42)
    res = solve_greedy(p)
    if not res.served_requests:
        return
    vid = p.vehicles[0].id
    _u, rec, diff = recover_disruption(p, res, vehicle_unavailable_id=vid)
    assert rec.event_type == "VEHICLE_BREAKDOWN"
    assert rec.claim_level == "synthetic_benchmark"
    assert "changed_trips" in diff.plan_churn
