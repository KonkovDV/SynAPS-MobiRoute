"""Adversarial and unit tests for MobiRoute core."""

from __future__ import annotations

import pytest

from mobiroute.adapters.fingerprint import fingerprint
from mobiroute.adapters.synthetic_data import generate_day
from mobiroute.dispatch.online_insertion import online_insert, recover_disruption
from mobiroute.domain.models import StopType, WheelchairType
from mobiroute.domain.requests import RoutePlan, Stop, TripRequest
from mobiroute.solvers.cpsat import solve_cpsat
from mobiroute.solvers.greedy import solve_fifo, solve_greedy
from mobiroute.validation.feasibility import check_plan
from mobiroute.validation.privacy import assert_no_pii_fields, log_safe, redact_problem_for_open


def test_deterministic_generation():
    a = generate_day("tiny", seed=42)
    b = generate_day("tiny", seed=42)
    assert fingerprint(a.model_dump(mode="json")) == fingerprint(b.model_dump(mode="json"))
    assert a.requests[0].id == b.requests[0].id


def test_greedy_tiny_feasible_or_partial():
    problem = generate_day("tiny", seed=42)
    result = solve_greedy(problem)
    assert result.solution_type == "GREEDY_INSERTION"
    assert result.status != "OPTIMAL"  # never claim optimal for greedy
    assert result.claim_level == "synthetic_benchmark"
    report = check_plan(problem, result)
    assert report.feasible == result.verified_feasible
    for r in result.rejected_requests:
        assert r.reason_code


def test_fifo_runs():
    problem = generate_day("tiny", seed=1)
    result = solve_fifo(problem)
    assert result.solution_type == "FIFO"


def test_cpsat_tiny():
    problem = generate_day("tiny", seed=7)
    # shrink for speed
    problem = problem.model_copy(update={"requests": problem.requests[:8]})
    result = solve_cpsat(problem, time_limit_s=5.0)
    assert result.solution_type in {"CPSAT_TINY", "CPSAT_FALLBACK_GREEDY"}
    if result.solution_type == "CPSAT_TINY" and result.status == "OPTIMAL":
        assert result.verified_feasible


def test_adversarial_split_vehicle_detected():
    problem = generate_day("tiny", seed=2)
    trip = problem.requests[0]
    # craft illegal plan: pickup on v0 dropoff on v1
    v0, v1 = problem.vehicles[0], problem.vehicles[1]
    pu = Stop(
        id="x:PU",
        trip_id=trip.id,
        stop_type=StopType.PICKUP,
        location=trip.pickup_zone,
        load_delta=1,
    )
    do = Stop(
        id="x:DO",
        trip_id=trip.id,
        stop_type=StopType.DROPOFF,
        location=trip.dropoff_zone,
        load_delta=-1,
    )
    r0 = RoutePlan(
        vehicle_id=v0.id,
        driver_id=problem.drivers[0].id,
        ordered_stops=[pu],
        passenger_assignments=[trip.id],
        arrival_times={pu.id: trip.earliest_pickup},
        departure_times={pu.id: trip.earliest_pickup + 3},
    )
    r1 = RoutePlan(
        vehicle_id=v1.id,
        driver_id=problem.drivers[1].id,
        ordered_stops=[do],
        passenger_assignments=[trip.id],
        arrival_times={do.id: trip.earliest_pickup + 20},
        departure_times={do.id: trip.earliest_pickup + 22},
    )
    from mobiroute.domain.requests import PlanningResult

    bad = PlanningResult(
        status="FEASIBLE",
        solution_type="ADVERSARIAL",
        verified_feasible=False,
        served_requests=[trip.id],
        rejected_requests=[],
        route_plans=[r0, r1],
        input_hash="x",
        config_hash="y",
        mobiroute_version="0",
        synaps_commit="0",
    )
    report = check_plan(problem, bad)
    assert not report.feasible
    assert any(
        "SPLIT_VEHICLE" in v or "DUPLICATE" in v or "MISSING" in v for v in report.violations
    )


def test_wheelchair_capacity_reject():
    problem = generate_day("infeasible", seed=3)
    result = solve_greedy(problem)
    # many wheelchair / no accessible fleet → rejects with reason
    assert result.rejected_requests
    assert all(r.reason_code for r in result.rejected_requests)


def test_cancellation_in_diff():
    problem = generate_day("tiny", seed=4)
    baseline = solve_greedy(problem)
    if not baseline.served_requests:
        pytest.skip("no served")
    tid = baseline.served_requests[0]
    _, new, diff = recover_disruption(problem, baseline, cancel_trip_id=tid)
    assert tid in diff.removed_trips or tid not in new.served_requests
    assert diff.reason_codes.get(tid) == "CANCELLED"


def test_online_medical_insert():
    problem = generate_day("tiny", seed=5)
    baseline = solve_greedy(problem)
    medical = TripRequest(
        id="med-test-1",
        pseudonymous_passenger_id="p-med",
        pickup_zone="Z_CENTER",
        dropoff_zone="Z_HOSP_A",
        requested_at=0,
        earliest_pickup=100,
        latest_pickup=140,
        appointment_end=180,
        max_ride_time=55,
        max_wait_time=20,
        wheelchair_requirement=WheelchairType.MANUAL,
        needs_lift=True,
        medical_priority=True,
    )
    _, res, diff = online_insert(problem, baseline, medical)
    assert "med-test-1" in res.served_requests or "med-test-1" in {
        r.trip_id for r in res.rejected_requests
    }
    assert diff.plan_churn


def test_privacy_redaction_and_logs():
    problem = generate_day("tiny", seed=6)
    # inject coordinates then redact
    t0 = problem.requests[0].model_copy(
        update={"pickup_coordinates": (55.75, 37.61), "dropoff_coordinates": (55.76, 37.62)}
    )
    problem = problem.model_copy(update={"requests": [t0, *problem.requests[1:]]})
    open_p = redact_problem_for_open(problem)
    assert open_p.requests[0].pickup_coordinates is None
    assert "[REDACTED_PHONE]" in log_safe("call +7 495 129-03-30 please")
    assert assert_no_pii_fields({"id": "x", "phone": "1"}) == ["phone"]


def test_no_builtin_hash_in_fingerprint():
    a = fingerprint({"a": 1, "b": [2, 3]})
    b = fingerprint({"b": [2, 3], "a": 1})
    assert a == b
    assert len(a) == 64


def test_greedy_pooling_can_interleave_stops():
    problem = generate_day("pooled_rides", seed=42)
    greedy = solve_greedy(problem)
    fifo = solve_fifo(problem)
    assert greedy.verified_feasible
    assert fifo.verified_feasible
    assert greedy.status != "OPTIMAL"
    assert greedy.solver_config.get("pooling") is True
    # Pooling is allowed; sequential FIFO is the no-share baseline.
    assert fifo.solver_config.get("pooling") is False


def test_beam_never_optimal():
    from mobiroute.solvers.beam import solve_beam

    problem = generate_day("tiny", seed=9)
    result = solve_beam(problem, beam_width=2)
    assert result.solution_type == "BEAM"
    assert result.status != "OPTIMAL"


def test_online_insert_preserves_other_vehicle_assignments():
    problem = generate_day("tiny", seed=5)
    baseline = solve_greedy(problem)
    before = {tid: rp.vehicle_id for rp in baseline.route_plans for tid in rp.passenger_assignments}
    medical = TripRequest(
        id="med-preserve-1",
        pseudonymous_passenger_id="p-med",
        pickup_zone="Z_CENTER",
        dropoff_zone="Z_HOSP_A",
        requested_at=0,
        earliest_pickup=100,
        latest_pickup=140,
        appointment_end=180,
        max_ride_time=55,
        max_wait_time=20,
        wheelchair_requirement=WheelchairType.NONE,
        medical_priority=True,
    )
    _, res, diff = online_insert(problem, baseline, medical)
    after = {tid: rp.vehicle_id for rp in res.route_plans for tid in rp.passenger_assignments}
    for tid, vid in before.items():
        assert after.get(tid) == vid
    if "med-preserve-1" in res.served_requests:
        assert "med-preserve-1" in diff.added_trips
