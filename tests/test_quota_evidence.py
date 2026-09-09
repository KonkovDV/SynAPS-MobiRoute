"""Quota evidence comes from stop clocks, not optional cached summaries."""

import unittest

from mobiroute.domain.models import StopType
from mobiroute.domain.requests import (
    DayProblem,
    Driver,
    PassengerProfile,
    PlanningResult,
    RoutePlan,
    Stop,
    TravelMatrix,
    TripRequest,
    Vehicle,
)
from mobiroute.validation.feasibility import (
    check_plan,
    passenger_rides,
    trial_exceeds_quota,
    used_quota_minutes,
)


def quota_case(*, quota=20, via=False, tid="t", offset=0):
    request = TripRequest(
        id=tid,
        pseudonymous_passenger_id="p",
        pickup_zone="d",
        dropoff_zone="q",
        requested_at=0,
        earliest_pickup=offset,
        latest_pickup=offset + 60,
        max_ride_time=100,
        max_wait_time=60,
        quota_minutes_remaining=quota,
        via_zone="v" if via else None,
        via_service_duration=3,
    )
    vid, did = f"vehicle-{tid}", f"driver-{tid}"
    problem = DayProblem(
        problem_id="quota-evidence",
        seed=1,
        passengers=[],
        requests=[request],
        vehicles=[
            Vehicle(
                id=vid,
                vehicle_type="van",
                passenger_capacity=2,
                depot_id="d",
                shift_start=0,
                shift_end=180,
            )
        ],
        drivers=[Driver(id=did, depot_id="d", shift_start=0, shift_end=180)],
        travel=TravelMatrix(
            zones=["d", "q", "v"],
            minutes=[[0, 20, 8], [20, 0, 12], [8, 12, 0]],
        ),
    )
    stops = [Stop(id="pu", trip_id=tid, stop_type=StopType.PICKUP, location="d")]
    arrival = {"pu": offset}
    departure = {"pu": offset + 5}
    if via:
        stops.append(Stop(id="via", trip_id=tid, stop_type=StopType.VIA, location="v"))
        arrival["via"] = offset + 13
        departure["via"] = offset + 16
    stops.append(Stop(id="do", trip_id=tid, stop_type=StopType.DROPOFF, location="q"))
    ride = 23 if via else 20
    arrival["do"] = offset + 5 + ride
    departure["do"] = arrival["do"] + 2
    route = RoutePlan(
        vehicle_id=vid,
        driver_id=did,
        ordered_stops=stops,
        passenger_assignments=[tid],
        arrival_times=arrival,
        departure_times=departure,
        ride_times={tid: ride},
    )
    result = PlanningResult(
        status="NOT_VERIFIED",
        solution_type="TEST",
        verified_feasible=False,
        served_requests=[tid],
        rejected_requests=[],
        route_plans=[route],
        input_hash="test-input",
        config_hash="test-config",
        mobiroute_version="test",
        synaps_commit="test",
    )
    return problem, result


class QuotaEvidenceTests(unittest.TestCase):
    def test_valid_routes_do_not_require_cached_ride_times(self):
        for cache in ({"t": 20}, {}):
            with self.subTest(cache=cache):
                problem, result = quota_case()
                result.route_plans[0].ride_times = cache
                report = check_plan(problem, result)
                self.assertTrue(report.feasible, report.violations)
                self.assertEqual(used_quota_minutes(problem, result), {"p": 20})

    def test_forged_or_absent_cache_cannot_hide_over_quota_service(self):
        for cache in ({}, {"t": 0}, {"t": -100}, {"unknown": 0}):
            with self.subTest(cache=cache):
                problem, result = quota_case(quota=19)
                result.route_plans[0].ride_times = cache
                restored = PlanningResult.model_validate_json(result.model_dump_json())
                report = check_plan(problem, restored)
                self.assertFalse(report.feasible)
                self.assertIn("QUOTA:p", report.violations)

    def test_incorrect_cache_is_diagnosed_even_without_a_quota(self):
        problem, result = quota_case(quota=None)
        result.route_plans[0].ride_times = {"t": 0}
        report = check_plan(problem, result)
        self.assertIn("RIDE_TIME_MISMATCH:t", report.violations)
        self.assertFalse(report.feasible)

    def test_stale_high_cache_is_not_quota_evidence(self):
        problem, result = quota_case()
        result.route_plans[0].ride_times = {"t": 1000}
        report = check_plan(problem, result)
        self.assertNotIn("QUOTA:p", report.violations)
        self.assertIn("RIDE_TIME_MISMATCH:t", report.violations)
        self.assertEqual(used_quota_minutes(problem, result), {"p": 20})

    def test_profile_quota_accumulates_across_vehicles(self):
        problem, result = quota_case(quota=None)
        other, other_result = quota_case(quota=None, tid="return", offset=60)
        problem.requests.extend(other.requests)
        problem.vehicles.extend(other.vehicles)
        problem.drivers.extend(other.drivers)
        problem.passengers = [PassengerProfile(pseudonymous_id="p", quota_minutes_remaining=35)]
        result.served_requests.extend(other_result.served_requests)
        result.route_plans.extend(other_result.route_plans)
        for route in result.route_plans:
            route.ride_times = {}
        self.assertEqual(used_quota_minutes(problem, result), {"p": 40})
        self.assertIn("QUOTA:p", check_plan(problem, result).violations)

    def test_via_dwell_counts_between_pickup_departure_and_dropoff_arrival(self):
        problem, result = quota_case(quota=23, via=True)
        result.route_plans[0].ride_times = {}
        self.assertTrue(check_plan(problem, result).feasible)
        self.assertEqual(used_quota_minutes(problem, result), {"p": 23})
        problem.requests[0].quota_minutes_remaining = 22
        self.assertIn("QUOTA:p", check_plan(problem, result).violations)

    def test_missing_clock_is_not_replaced_by_a_cached_summary(self):
        problem, result = quota_case()
        del result.route_plans[0].departure_times["pu"]
        report = check_plan(problem, result)
        self.assertFalse(report.feasible)
        self.assertIn("MISSING_TIMES:pu", report.violations)

    def test_trial_replaces_previous_route_usage_using_stop_clocks(self):
        problem, result = quota_case()
        route = result.route_plans[0]
        route.ride_times = {}
        trips = {t.id: t for t in problem.requests}
        self.assertEqual(passenger_rides(route, trips), {"p": 20})
        self.assertTrue(
            trial_exceeds_quota(
                route,
                quota_cap={"p": 30},
                used_now={"p": 25},
                previous_on_vehicle={"p": 10},
                problem=problem,
            )
        )
        self.assertFalse(
            trial_exceeds_quota(
                route,
                quota_cap={"p": 35},
                used_now={"p": 25},
                previous_on_vehicle={"p": 10},
                problem=problem,
            )
        )

    def test_quota_evaluation_does_not_mutate_input(self):
        problem, result = quota_case(quota=19)
        result.route_plans[0].ride_times = {"t": 0}
        before = result.model_dump_json()
        used_quota_minutes(problem, result)
        check_plan(problem, result)
        self.assertEqual(result.model_dump_json(), before)
