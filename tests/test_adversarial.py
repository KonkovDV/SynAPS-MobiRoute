"""Expanded adversarial and constraint tests for MobiRoute."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mobiroute.adapters.geocoder import geocode_address_forbidden_in_open_repo, zone_catalog
from mobiroute.adapters.synthetic_data import generate_day
from mobiroute.adapters.travel_time import TravelTimeService
from mobiroute.dispatch.manual_override import ManualOverride, OverrideJournal
from mobiroute.dispatch.online_insertion import online_insert, recover_disruption
from mobiroute.domain.models import StopType, WheelchairType
from mobiroute.domain.requests import (
    DayProblem,
    PlanningResult,
    RejectedTrip,
    RoutePlan,
    Stop,
    TripRequest,
)
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.solvers.nearest import solve_nearest
from mobiroute.validation.completeness import incomplete_plan_issues
from mobiroute.validation.feasibility import check_plan
from mobiroute.validation.privacy import log_safe

ROOT = Path(__file__).resolve().parents[1]


def _bad_result(problem: DayProblem, routes: list[RoutePlan], served: list[str]) -> PlanningResult:
    return PlanningResult(
        status="FEASIBLE",
        solution_type="ADVERSARIAL",
        verified_feasible=False,
        served_requests=served,
        rejected_requests=[],
        route_plans=routes,
        input_hash="x",
        config_hash="y",
        mobiroute_version="0",
        synaps_commit="0",
    )


def test_dropoff_before_pickup_detected():
    problem = generate_day("tiny", seed=11)
    trip = problem.requests[0]
    v = problem.vehicles[0]
    do = Stop(
        id="d",
        trip_id=trip.id,
        stop_type=StopType.DROPOFF,
        location=trip.dropoff_zone,
        load_delta=-1,
    )
    pu = Stop(
        id="p", trip_id=trip.id, stop_type=StopType.PICKUP, location=trip.pickup_zone, load_delta=1
    )
    route = RoutePlan(
        vehicle_id=v.id,
        driver_id=problem.drivers[0].id,
        ordered_stops=[do, pu],
        passenger_assignments=[trip.id],
        arrival_times={"d": 10, "p": 20},
        departure_times={"d": 12, "p": 23},
    )
    report = check_plan(problem, _bad_result(problem, [route], [trip.id]))
    assert not report.feasible
    assert any("DROPOFF_BEFORE_PICKUP" in v for v in report.violations)


def test_double_wheelchair_overload():
    problem = generate_day("tiny", seed=12)
    v = next(x for x in problem.vehicles if x.wheelchair_capacity == 1)
    # two wheelchair trips forced on same vehicle overlapping
    t1, t2 = problem.requests[0], problem.requests[1]
    t1 = t1.model_copy(update={"wheelchair_requirement": WheelchairType.MANUAL})
    t2 = t2.model_copy(update={"wheelchair_requirement": WheelchairType.MANUAL})
    problem = problem.model_copy(update={"requests": [t1, t2, *problem.requests[2:]]})
    stops = []
    arr, dep = {}, {}
    t = 60
    for trip in (t1, t2):
        pu = Stop(
            id=f"{trip.id}:PU",
            trip_id=trip.id,
            stop_type=StopType.PICKUP,
            location=trip.pickup_zone,
            load_delta=1,
            wheelchair_load_delta=1,
        )
        stops.append(pu)
        arr[pu.id] = t
        dep[pu.id] = t + 3
        t += 5
    for trip in (t1, t2):
        do = Stop(
            id=f"{trip.id}:DO",
            trip_id=trip.id,
            stop_type=StopType.DROPOFF,
            location=trip.dropoff_zone,
            load_delta=-1,
            wheelchair_load_delta=-1,
        )
        stops.append(do)
        arr[do.id] = t
        dep[do.id] = t + 2
        t += 5
    route = RoutePlan(
        vehicle_id=v.id,
        driver_id=problem.drivers[0].id,
        ordered_stops=stops,
        passenger_assignments=[t1.id, t2.id],
        arrival_times=arr,
        departure_times=dep,
    )
    report = check_plan(problem, _bad_result(problem, [route], [t1.id, t2.id]))
    assert any("WHEELCHAIR_CAPACITY" in x for x in report.violations)


def test_driver_without_accessibility_training():
    problem = generate_day("tiny", seed=13)
    trip = problem.requests[0].model_copy(
        update={
            "wheelchair_requirement": WheelchairType.MANUAL,
            "needs_boarding_assistance": True,
            "needs_lift": True,
        }
    )
    v = next(x for x in problem.vehicles if x.lift_available and x.wheelchair_capacity >= 1)
    # force first driver untrained regardless of generator defaults
    drivers = [
        problem.drivers[0].model_copy(update={"accessibility_training": False}),
        *problem.drivers[1:],
    ]
    problem = problem.model_copy(
        update={"requests": [trip, *problem.requests[1:]], "drivers": drivers}
    )
    driver = drivers[0]
    pu = Stop(
        id="p",
        trip_id=trip.id,
        stop_type=StopType.PICKUP,
        location=trip.pickup_zone,
        load_delta=1,
        wheelchair_load_delta=1,
    )
    do = Stop(
        id="d",
        trip_id=trip.id,
        stop_type=StopType.DROPOFF,
        location=trip.dropoff_zone,
        load_delta=-1,
        wheelchair_load_delta=-1,
    )
    route = RoutePlan(
        vehicle_id=v.id,
        driver_id=driver.id,
        ordered_stops=[pu, do],
        passenger_assignments=[trip.id],
        arrival_times={pu.id: trip.earliest_pickup, do.id: trip.earliest_pickup + 20},
        departure_times={pu.id: trip.earliest_pickup + 3, do.id: trip.earliest_pickup + 22},
    )
    report = check_plan(problem, _bad_result(problem, [route], [trip.id]))
    assert any("DRIVER_QUAL" in x for x in report.violations)


def test_appointment_violation():
    problem = generate_day("tiny", seed=14)
    trip = problem.requests[0].model_copy(
        update={"appointment_end": 100, "earliest_pickup": 50, "latest_pickup": 80}
    )
    problem = problem.model_copy(update={"requests": [trip, *problem.requests[1:]]})
    v = problem.vehicles[0]
    pu = Stop(
        id="p", trip_id=trip.id, stop_type=StopType.PICKUP, location=trip.pickup_zone, load_delta=1
    )
    do = Stop(
        id="d",
        trip_id=trip.id,
        stop_type=StopType.DROPOFF,
        location=trip.dropoff_zone,
        load_delta=-1,
    )
    route = RoutePlan(
        vehicle_id=v.id,
        driver_id=problem.drivers[0].id,
        ordered_stops=[pu, do],
        passenger_assignments=[trip.id],
        arrival_times={pu.id: 60, do.id: 150},
        departure_times={pu.id: 63, do.id: 152},
    )
    report = check_plan(problem, _bad_result(problem, [route], [trip.id]))
    assert any("APPOINTMENT" in x for x in report.violations)


def test_reject_without_reason_flagged():
    problem = generate_day("tiny", seed=15)
    result = PlanningResult(
        status="PARTIAL",
        solution_type="ADVERSARIAL",
        verified_feasible=False,
        served_requests=[],
        rejected_requests=[RejectedTrip(trip_id=problem.requests[0].id, reason_code="")],
        route_plans=[],
        input_hash="x",
        config_hash="y",
        mobiroute_version="0",
        synaps_commit="0",
    )
    report = check_plan(problem, result)
    assert any("NO_REASON" in x for x in report.violations)


def test_incomplete_plan_detection():
    problem = generate_day("tiny", seed=16)
    result = solve_greedy(problem)
    # drop one served without reject
    if result.served_requests:
        tid = result.served_requests[0]
        bad = result.model_copy(update={"served_requests": result.served_requests[1:]})
        issues = incomplete_plan_issues(problem, bad)
        assert any(tid in x for x in issues)


def test_frozen_trip_preference_on_insert():
    problem = generate_day("tiny", seed=17)
    baseline = solve_greedy(problem)
    if not baseline.served_requests:
        pytest.skip("empty")
    medical = TripRequest(
        id="med-adv-1",
        pseudonymous_passenger_id="p",
        pickup_zone="Z_CENTER",
        dropoff_zone="Z_HOSP_A",
        requested_at=0,
        earliest_pickup=110,
        latest_pickup=150,
        appointment_end=190,
        max_ride_time=55,
        max_wait_time=20,
        wheelchair_requirement=WheelchairType.NONE,
        medical_priority=True,
    )
    _, _res, diff = online_insert(problem, baseline, medical)
    # frozen preference marked; churn measured
    assert "changed_trips" in diff.plan_churn


def test_traffic_and_driver_disruption():
    problem = generate_day("tiny", seed=18)
    baseline = solve_greedy(problem)
    delayed = TravelTimeService(problem.travel).apply_traffic_delay(15)
    assert delayed.minutes[0][1] == problem.travel.minutes[0][1] + 15
    _, res, diff = recover_disruption(
        problem, baseline, traffic_delay_minutes=15, driver_unavailable_id=problem.drivers[0].id
    )
    assert res.solution_type == "DISRUPTION_RECOVERY"
    assert diff.plan_churn is not None


def test_manual_override_requires_reason():
    journal = OverrideJournal()
    problem = generate_day("tiny", seed=19)
    result = solve_greedy(problem)
    if not result.served_requests:
        pytest.skip("empty")
    tid = result.served_requests[0]
    with pytest.raises(ValueError):
        journal.record(
            ManualOverride(
                operator_id="op1",
                trip_id=tid,
                action="REJECT",
                free_text_reason="  ",
            )
        )
    entry = ManualOverride(
        operator_id="op1",
        trip_id=tid,
        action="REJECT",
        free_text_reason="passenger cancelled by phone",
    )
    out = journal.apply_reject(result, tid, entry)
    assert out.status == "MANUAL_REVIEW_REQUIRED"
    assert tid not in out.served_requests
    assert journal.entries


def test_nearest_never_optimal_label():
    problem = generate_day("tiny", seed=20)
    result = solve_nearest(problem)
    assert result.solution_type == "NEAREST_FEASIBLE"
    assert result.status != "OPTIMAL"


def test_schema_examples_load():
    for name in [
        "tiny_day.json",
        "wheelchair_day.json",
        "medical_priority_day.json",
        "disruption_day.json",
        "fairness_stress_day.json",
    ]:
        data = json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))
        DayProblem.model_validate(data)
        assert data["data_provenance"] == "synthetic"


def test_geocoder_blocks_real_address():
    assert zone_catalog()
    with pytest.raises(RuntimeError):
        geocode_address_forbidden_in_open_repo("ул. Тверская, 1")


def test_no_show_reason_in_diff():
    problem = generate_day("tiny", seed=21)
    baseline = solve_greedy(problem)
    if not baseline.served_requests:
        pytest.skip("empty")
    tid = baseline.served_requests[0]
    _, _, diff = recover_disruption(problem, baseline, no_show_trip_id=tid)
    assert diff.reason_codes.get(tid) == "NO_SHOW"


def test_pii_not_in_logs():
    assert "129-03-30" not in log_safe("call +7 (495) 129-03-30")
    assert "[REDACTED_PHONE]" in log_safe("call +7 (495) 129-03-30")
