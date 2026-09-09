"""Search failure is not a proof of time-window or appointment infeasibility."""

import unittest
from pathlib import Path

from mobiroute.dispatch.online_insertion import online_insert
from mobiroute.domain.models import ReasonCode, WheelchairType
from mobiroute.domain.policy import OperatorPolicy, QuotaDebitBasis
from mobiroute.domain.requests import RejectedTrip, TripExplanation
from mobiroute.solvers.finalize import finalize_result
from mobiroute.solvers.greedy import (
    _quota_lower_bound_exceeds,
    _unresolved_insert_code,
    _unserve_leftover,
)
from mobiroute.validation.feasibility import check_plan
from mobiroute.validation.reasons import diagnose_rejection

from .test_quota_debit_basis import ALIGHT, RIDE, SERVICE
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

    def test_diagnose_never_returns_time_window_conflict(self):
        problem, _ = quota_case(quota=None)
        self.assertNotEqual(
            diagnose_rejection(problem, problem.requests[0]),
            ReasonCode.TIME_WINDOW_CONFLICT,
        )
        problem.requests[0].max_ride_time = 1
        problem.requests[0].appointment_end = 100
        self.assertNotEqual(
            diagnose_rejection(problem, problem.requests[0]),
            ReasonCode.TIME_WINDOW_CONFLICT,
        )

    def test_unresolved_insert_necessary_conditions_beat_wait_return(self):
        problem, _ = quota_case(quota=None)
        trip = problem.requests[0]
        self.assertEqual(
            _unresolved_insert_code(problem, trip, quota_blocked=True),
            ReasonCode.QUOTA_EXCEEDED.value,
        )
        wait = trip.model_copy(update={"insert_immediately_after": "outbound"})
        self.assertEqual(
            _unresolved_insert_code(problem, wait),
            ReasonCode.WAIT_RETURN_INFEASIBLE.value,
        )
        self.assertEqual(
            _unresolved_insert_code(problem, wait, frozen_blocked=True),
            ReasonCode.MANUAL_REVIEW_REQUIRED.value,
        )
        tight, _ = quota_case(quota=1, via=True)
        wait_quota = tight.requests[0].model_copy(update={"insert_immediately_after": "outbound"})
        self.assertEqual(
            _unresolved_insert_code(tight, wait_quota),
            ReasonCode.QUOTA_EXCEEDED.value,
        )
        empty, _ = quota_case(quota=None)
        empty.vehicles = []
        wait_fleet = empty.requests[0].model_copy(update={"insert_immediately_after": "outbound"})
        self.assertEqual(
            _unresolved_insert_code(empty, wait_fleet),
            ReasonCode.NO_COMPATIBLE_VEHICLE.value,
        )
        self.assertEqual(
            _unresolved_insert_code(problem, trip),
            ReasonCode.MANUAL_REVIEW_REQUIRED.value,
        )

    def test_leftover_unserve_diagnoses_each_trip(self):
        problem, _ = quota_case(quota=1, via=True)
        extra, _ = quota_case(quota=None, tid="u")
        problem.requests.append(extra.requests[0])
        served = ["t", "u"]
        rejected: list = []
        reasons = {"t": ReasonCode.ACCEPTED.value, "u": ReasonCode.ACCEPTED.value}
        explanations = [
            TripExplanation(
                trip_id="t",
                accepted=True,
                why_this_route="lex insert succeeded",
                reason_code=ReasonCode.ACCEPTED.value,
            ),
            TripExplanation(
                trip_id="u",
                accepted=True,
                why_this_route="lex insert succeeded",
                reason_code=ReasonCode.ACCEPTED.value,
            ),
        ]
        trips_by_id = {t.id: t for t in problem.requests}
        _unserve_leftover(
            problem,
            trips_by_id,
            served,
            rejected,
            reasons,
            {"t", "u"},
            explanations=explanations,
        )
        by_id = {r.trip_id: r.reason_code for r in rejected}
        self.assertEqual(by_id["t"], ReasonCode.QUOTA_EXCEEDED.value)
        self.assertEqual(by_id["u"], ReasonCode.MANUAL_REVIEW_REQUIRED.value)
        self.assertEqual(served, [])
        self.assertNotIn(ReasonCode.TIME_WINDOW_CONFLICT.value, by_id.values())
        by_ex = {e.trip_id: e for e in explanations}
        self.assertFalse(by_ex["t"].accepted)
        self.assertEqual(by_ex["t"].reason_code, ReasonCode.QUOTA_EXCEEDED.value)
        self.assertFalse(by_ex["u"].accepted)
        self.assertEqual(by_ex["u"].reason_code, ReasonCode.MANUAL_REVIEW_REQUIRED.value)

    def test_finalize_drops_accepted_explanation_for_unserved_trip(self):
        problem, result = quota_case(quota=None)
        planted = result.model_copy(
            update={
                "served_requests": [],
                "rejected_requests": [
                    RejectedTrip(trip_id="t", reason_code=ReasonCode.QUOTA_EXCEEDED.value)
                ],
                "reason_codes": {"t": ReasonCode.QUOTA_EXCEEDED.value},
                "route_plans": [],
            }
        )
        out = finalize_result(
            problem,
            planted,
            explanations=[
                TripExplanation(
                    trip_id="t",
                    accepted=True,
                    why_this_route="lex insert succeeded",
                    reason_code=ReasonCode.ACCEPTED.value,
                )
            ],
        )
        hit = [e for e in out.explanations if e.trip_id == "t"]
        self.assertTrue(hit)
        self.assertFalse(hit[0].accepted)
        self.assertEqual(hit[0].reason_code, ReasonCode.QUOTA_EXCEEDED.value)

    def test_billable_presearch_gate_uses_debit_not_ride_alone(self):
        problem, _ = quota_case(quota=SERVICE - 1)
        problem.requests[0].boarding_duration = 1
        problem.requests[0].alighting_duration = ALIGHT
        problem.operator_policy = OperatorPolicy(
            quota_debit_basis=QuotaDebitBasis.BILLABLE_SERVICE,
            provenance="laboratory:presearch-debit",
        )
        self.assertGreater(SERVICE - 1, RIDE)
        self.assertTrue(_quota_lower_bound_exceeds(problem, problem.requests[0], SERVICE - 1))
        ride_only, _ = quota_case(quota=RIDE)
        ride_only.operator_policy = OperatorPolicy(
            quota_debit_basis=QuotaDebitBasis.RIDE_DURATION,
            provenance="laboratory:presearch-ride",
        )
        self.assertFalse(_quota_lower_bound_exceeds(ride_only, ride_only.requests[0], RIDE))

    def test_online_exhausted_entitlement_is_refused_as_quota(self):
        # The baseline already spent the whole cap on the same passenger.
        problem, base = quota_case(quota=RIDE)
        again = problem.requests[0].model_copy(update={"id": "t2"})
        _updated, out, _diff = online_insert(problem, base, again)
        codes = {r.trip_id: r.reason_code for r in out.rejected_requests}
        self.assertEqual(codes.get("t2"), ReasonCode.QUOTA_EXCEEDED.value)
        self.assertNotIn("t2", out.served_requests)
        self.assertTrue(out.verified_feasible)

    def test_online_quota_gate_uses_the_debit_not_ride_alone(self):
        # Remaining entitlement is positive for the ride alone, short for the
        # billable dwell the plan would actually hold.
        problem, base = quota_case(quota=SERVICE - 1)
        newcomer = problem.requests[0].model_copy(
            update={"id": "t2", "boarding_duration": 1, "alighting_duration": ALIGHT}
        )
        unserved = base.model_copy(
            update={
                "served_requests": [],
                "rejected_requests": [
                    RejectedTrip(trip_id="t", reason_code=ReasonCode.MANUAL_REVIEW_REQUIRED.value)
                ],
                "reason_codes": {"t": ReasonCode.MANUAL_REVIEW_REQUIRED.value},
                "route_plans": [],
            }
        )
        problem.operator_policy = OperatorPolicy(
            quota_debit_basis=QuotaDebitBasis.BILLABLE_SERVICE,
            provenance="laboratory:online-debit",
        )
        _u, billable, _d = online_insert(problem, unserved, newcomer)
        billable_codes = {r.trip_id: r.reason_code for r in billable.rejected_requests}
        self.assertEqual(billable_codes.get("t2"), ReasonCode.QUOTA_EXCEEDED.value)
        problem.operator_policy = OperatorPolicy(
            quota_debit_basis=QuotaDebitBasis.RIDE_DURATION,
            provenance="laboratory:online-ride",
        )
        _u2, ride_basis, _d2 = online_insert(problem, unserved, newcomer)
        ride_codes = {r.trip_id: r.reason_code for r in ride_basis.rejected_requests}
        self.assertNotEqual(ride_codes.get("t2"), ReasonCode.QUOTA_EXCEEDED.value)

    def test_search_producers_do_not_hardcode_time_window_conflict(self):
        root = Path(__file__).resolve().parents[1] / "src" / "mobiroute"
        greedy = (root / "solvers" / "greedy.py").read_text(encoding="utf-8")
        online = (root / "dispatch" / "online_insertion.py").read_text(encoding="utf-8")
        self.assertNotIn("TIME_WINDOW_CONFLICT", greedy)
        self.assertNotIn("TIME_WINDOW_CONFLICT", online)
