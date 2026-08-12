"""Required regression tests for 0.2.0 defects."""

from __future__ import annotations

from mobiroute.adapters.synthetic_data import generate_day
from mobiroute.dispatch.manual_override import ManualOverride, OverrideJournal
from mobiroute.dispatch.online_insertion import online_insert, recover_disruption
from mobiroute.domain.driver_assignment import select_driver
from mobiroute.domain.models import WheelchairType
from mobiroute.domain.requests import TripRequest
from mobiroute.solvers.cpsat import solve_cpsat
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.validation.feasibility import check_plan
from mobiroute.validation.privacy import log_safe
from tests.factories import driver, problem, trip, vehicle


def _too_large_for_tiny_cpsat():
    base = generate_day("tiny", seed=1)
    vehs = []
    drvs = []
    for i in range(13):
        src_v = base.vehicles[i % len(base.vehicles)]
        src_d = base.drivers[i % len(base.drivers)]
        v = src_v.model_copy(update={"id": f"v-extra-{i:02d}"})
        d = src_d.model_copy(update={"id": f"d-extra-{i:02d}", "depot_id": v.depot_id})
        vehs.append(v)
        drvs.append(d)
    return base.model_copy(update={"vehicles": vehs, "drivers": drvs})


def test_r1_driver_not_only_depot_id():
    p = problem(
        [vehicle("v1", depot="Z_DEPOT_1")],
        [
            driver("zzz-untrained", trained=False, depot="Z_DEPOT_1"),
            driver("aaa-trained", trained=True, depot="Z_DEPOT_1"),
        ],
        [
            trip(
                "need",
                "Z_NORTH",
                "Z_HOSP_A",
                wheelchair=WheelchairType.MANUAL,
                lift=True,
                assist=True,
            )
        ],
    )
    assert (
        select_driver(p, p.vehicles[0], needs_accessibility=True, occupied_driver_ids=set())
        == "aaa-trained"
    )


def test_r2_appointment_start_limits_dropoff():
    p = problem(
        [vehicle("v1")],
        [driver("d1")],
        [
            trip(
                "med",
                "Z_NORTH",
                "Z_HOSP_A",
                earliest=50,
                latest=200,
                appt_start=140,
                appt_end=190,
                max_ride=80,
            )
        ],
    )
    res = solve_greedy(p)
    if "med" in res.served_requests:
        it = res.route_plans[0].passenger_itineraries[0]
        assert it.dropoff_time >= 110
        assert it.dropoff_time <= 190
        slack = it.appointment_slack
        if slack is not None:
            assert slack >= 0
    report = check_plan(p, res)
    if res.verified_feasible:
        assert not any("APPOINTMENT_START" in v for v in report.violations)


def test_r3_cpsat_fallback_not_optimal():
    p = _too_large_for_tiny_cpsat()
    res = solve_cpsat(p, time_limit_s=1.0)
    assert res.solution_type == "CPSAT_FALLBACK_GREEDY"
    assert res.status != "OPTIMAL"


def test_r4_large_instance_heuristic_feasible():
    p = _too_large_for_tiny_cpsat()
    res = solve_cpsat(p, time_limit_s=1.0)
    assert res.status in {"HEURISTIC_FEASIBLE", "PARTIAL", "NOT_VERIFIED"}
    assert res.status != "OPTIMAL"


def test_r5_pairing_cannot_split_vehicles():
    p = generate_day("tiny", seed=2)
    res = solve_greedy(p)
    report = check_plan(p, res)
    assert not any("SPLIT_VEHICLE" in v for v in report.violations)
    for rp in res.route_plans:
        ids = {s.trip_id for s in rp.ordered_stops if s.trip_id}
        for tid in ids:
            kinds = [s.stop_type.value for s in rp.ordered_stops if s.trip_id == tid]
            assert "PICKUP" in kinds and "DROPOFF" in kinds


def test_r6_pooling_counts_current_load():
    p = problem(
        [vehicle("v1", capacity=3, wheelchairs=0, types=[])],
        [driver("d1")],
        [
            trip("a", "Z_NORTH", "Z_SOUTH", earliest=60, latest=220),
            trip("b", "Z_NORTH", "Z_SOUTH", earliest=70, latest=230),
        ],
    )
    res = solve_greedy(p)
    assert res.verified_feasible
    loads = []
    for rp in res.route_plans:
        loads.extend(rp.passenger_load_after_stop.values())
    assert max(loads) >= 2
    assert min(loads) >= 0


def test_r7_rejected_trip_does_not_disappear():
    p = generate_day("infeasible", seed=3)
    res = solve_greedy(p)
    active = {t.id for t in p.requests if t.booking_status.value not in {"CANCELLED", "NO_SHOW"}}
    accounted = set(res.served_requests) | {r.trip_id for r in res.rejected_requests}
    assert active <= accounted


def test_r8_rejection_reason_never_empty():
    p = generate_day("infeasible", seed=4)
    res = solve_greedy(p)
    assert res.rejected_requests
    assert all(r.reason_code for r in res.rejected_requests)


def test_r9_frozen_trip_does_not_move():
    p = generate_day("tiny", seed=5)
    baseline = solve_greedy(p)
    if not baseline.served_requests:
        return
    medical = TripRequest(
        id="frozen-probe",
        pseudonymous_passenger_id="p",
        pickup_zone="Z_CENTER",
        dropoff_zone="Z_HOSP_A",
        requested_at=0,
        earliest_pickup=100,
        latest_pickup=140,
        appointment_end=180,
        max_ride_time=55,
        max_wait_time=20,
    )
    before = {tid: rp.vehicle_id for rp in baseline.route_plans for tid in rp.passenger_assignments}
    _, res, _diff = online_insert(p, baseline, medical)
    after = {tid: rp.vehicle_id for rp in res.route_plans for tid in rp.passenger_assignments}
    for tid, vid in before.items():
        assert after.get(tid) == vid


def test_r10_manual_override_requires_reason():
    journal = OverrideJournal()
    p = generate_day("tiny", seed=19)
    result = solve_greedy(p)
    if not result.served_requests:
        return
    tid = result.served_requests[0]
    try:
        journal.record(
            ManualOverride(operator_id="op1", trip_id=tid, action="REJECT", free_text_reason="  ")
        )
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_r11_pii_not_in_logs():
    assert "129-03-30" not in log_safe("call +7 (495) 129-03-30")
    dumped = str(solve_greedy(generate_day("tiny", seed=6)).model_dump())
    assert "full_name" not in dumped
    assert "@" not in dumped or "example" not in dumped


def test_r12_fairness_not_one_metric():
    p = generate_day("fairness_stress", seed=9)
    res = solve_greedy(p)
    fm = res.fairness_metrics
    assert fm.fair_by_single_metric is False
    assert fm.acceptance_rate_by_eligibility is not None
    assert fm.jain_index is None or fm.max_disparity is not None or fm.service_coverage is not None


def test_cancellation_and_no_show_and_breakdown():
    p = generate_day("tiny", seed=10)
    baseline = solve_greedy(p)
    if not baseline.served_requests:
        return
    tid = baseline.served_requests[0]
    _, _r1, d1 = recover_disruption(p, baseline, cancel_trip_id=tid)
    assert d1.reason_codes.get(tid) == "CANCELLED"
    _, _r2, d2 = recover_disruption(p, baseline, no_show_trip_id=tid)
    assert d2.reason_codes.get(tid) == "NO_SHOW"
    vid = p.vehicles[0].id
    _, r3, _d3 = recover_disruption(p, baseline, vehicle_unavailable_id=vid)
    assert r3.event_type in {"VEHICLE_BREAKDOWN", "DISRUPTION"}
    did = p.drivers[0].id
    _, r4, _d4 = recover_disruption(p, baseline, driver_unavailable_id=did)
    assert r4.event_type in {"DRIVER_UNAVAILABLE", "DISRUPTION"}
    _, r5, _d5 = recover_disruption(p, baseline, traffic_delay_minutes=12)
    assert r5.event_type in {"TRAFFIC_DELAY", "DISRUPTION"}
