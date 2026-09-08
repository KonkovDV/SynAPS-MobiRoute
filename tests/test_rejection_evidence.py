"""Search failure is not a proof of time-window or appointment infeasibility."""

import unittest

from mobiroute.domain.models import ReasonCode, WheelchairType
from mobiroute.validation.feasibility import check_plan
from mobiroute.validation.reasons import diagnose_rejection

from .test_quota_evidence import quota_case


class RejectionEvidenceTests(unittest.TestCase):
    def test_feasible_singleton_has_no_proven_rejection_cause(self):
        problem, result = quota_case(quota=None)
        self.assertTrue(check_plan(problem, result).feasible)
        self.assertEqual(
            diagnose_rejection(problem, problem.requests[0]),
            ReasonCode.MANUAL_REVIEW_REQUIRED,
        )

    def test_appointment_metadata_is_not_conflict_evidence(self):
        problem, result = quota_case(quota=None)
        problem.requests[0].appointment_end = 100
        self.assertTrue(check_plan(problem, result).feasible)
        self.assertEqual(
            diagnose_rejection(problem, problem.requests[0]),
            ReasonCode.MANUAL_REVIEW_REQUIRED,
        )

    def test_first_driver_failure_does_not_rule_out_other_drivers(self):
        problem, result = quota_case(quota=None)
        problem.requests[0].appointment_end = 100
        blocked = problem.drivers[0].model_copy(update={"id": "a", "shift_end": 10})
        problem.drivers.insert(0, blocked)
        self.assertTrue(check_plan(problem, result).feasible)
        self.assertEqual(
            diagnose_rejection(problem, problem.requests[0]),
            ReasonCode.MANUAL_REVIEW_REQUIRED,
        )

    def test_failed_simulation_does_not_identify_the_failed_constraint(self):
        problem, _ = quota_case(quota=None)
        problem.requests[0].max_ride_time = 1
        problem.requests[0].appointment_end = 100
        self.assertEqual(
            diagnose_rejection(problem, problem.requests[0]),
            ReasonCode.MANUAL_REVIEW_REQUIRED,
        )

    def test_mixed_vehicle_failures_do_not_select_an_arbitrary_cause(self):
        problem, _ = quota_case(quota=None)
        request = problem.requests[0]
        request.wheelchair_requirement = WheelchairType.MANUAL
        request.companion_count = 1
        problem.vehicles.append(
            problem.vehicles[0].model_copy(
                update={
                    "id": "small",
                    "wheelchair_capacity": 1,
                    "passenger_capacity": 1,
                },
            )
        )
        first = diagnose_rejection(problem, request)
        problem.vehicles.reverse()
        self.assertEqual(first, ReasonCode.NO_COMPATIBLE_VEHICLE)
        self.assertEqual(diagnose_rejection(problem, request), first)

    def test_quota_lower_bound_includes_via_dwell(self):
        problem, _ = quota_case(quota=22, via=True)
        self.assertEqual(
            diagnose_rejection(problem, problem.requests[0]),
            ReasonCode.QUOTA_EXCEEDED,
        )

    def test_zero_quota_does_not_prove_excess_for_zero_ride(self):
        problem, result = quota_case(quota=0)
        problem.requests[0].dropoff_zone = "d"
        route = result.route_plans[0]
        route.ordered_stops[-1].location = "d"
        route.arrival_times["do"] = 5
        route.departure_times["do"] = 7
        route.ride_times["t"] = 0
        self.assertTrue(check_plan(problem, result).feasible)
        self.assertEqual(
            diagnose_rejection(problem, problem.requests[0]),
            ReasonCode.MANUAL_REVIEW_REQUIRED,
        )

    def test_proven_resource_failures_and_input_immutability(self):
        for unavailable in ("vehicles", "drivers"):
            with self.subTest(unavailable=unavailable):
                problem, _ = quota_case(quota=None)
                setattr(problem, unavailable, [])
                before = problem.model_dump_json()
                expected = (
                    ReasonCode.NO_COMPATIBLE_VEHICLE
                    if unavailable == "vehicles"
                    else ReasonCode.NO_DRIVER
                )
                self.assertEqual(diagnose_rejection(problem, problem.requests[0]), expected)
                self.assertEqual(problem.model_dump_json(), before)
