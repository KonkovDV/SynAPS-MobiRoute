"""Quota debit must match the service dwell the plan actually holds."""

import importlib.util
import unittest

from mobiroute.domain.models import ReasonCode
from mobiroute.domain.policy import OperatorPolicy, QuotaDebitBasis
from mobiroute.validation.feasibility import (
    billable_service_minutes,
    check_plan,
    used_quota_minutes,
)
from mobiroute.validation.reasons import diagnose_rejection

from .test_quota_evidence import quota_case

# quota_case: travel d->q is 20, pickup dwell 0->5, dropoff 25->27.
RIDE = 20
CURB = 5
ALIGHT = 2
SERVICE = CURB + RIDE + ALIGHT


def curb_wait_case(
    quota: int = SERVICE - 1,
    basis: QuotaDebitBasis = QuotaDebitBasis.BILLABLE_SERVICE,
):
    """Declared boarding below the enforced curb wait; the plan still holds 5."""
    problem, result = quota_case(quota=quota)
    trip = problem.requests[0]
    trip.boarding_duration = 1
    trip.alighting_duration = ALIGHT
    problem.operator_policy = OperatorPolicy(
        quota_debit_basis=basis,
        provenance="laboratory:curb-wait-debit",
    )
    return problem, result


class CurbWaitDebitTests(unittest.TestCase):
    def test_billable_service_matches_the_planned_service_window(self):
        problem, result = curb_wait_case()
        route = result.route_plans[0]
        window = route.departure_times["do"] - route.arrival_times["pu"]
        self.assertEqual(window, SERVICE)
        self.assertEqual(billable_service_minutes(problem.requests[0], RIDE), window)

    def test_declared_boarding_cannot_understate_the_debit(self):
        problem, result = curb_wait_case()
        self.assertEqual(used_quota_minutes(problem, result), {"p": SERVICE})
        self.assertIn("QUOTA:p", check_plan(problem, result).violations)

    def test_sufficient_entitlement_and_ride_basis_stay_feasible(self):
        problem, result = curb_wait_case(quota=SERVICE)
        report = check_plan(problem, result)
        self.assertTrue(report.feasible, report.violations)
        ride_only, ride_result = curb_wait_case(quota=RIDE, basis=QuotaDebitBasis.RIDE_DURATION)
        self.assertEqual(used_quota_minutes(ride_only, ride_result), {"p": RIDE})
        self.assertTrue(check_plan(ride_only, ride_result).feasible)

    def test_debit_basis_makes_the_quota_lower_bound_provable(self):
        problem, _result = curb_wait_case()
        self.assertEqual(
            diagnose_rejection(problem, problem.requests[0]),
            ReasonCode.QUOTA_EXCEEDED,
        )
        ride_only, _ = curb_wait_case(quota=RIDE, basis=QuotaDebitBasis.RIDE_DURATION)
        self.assertEqual(
            diagnose_rejection(ride_only, ride_only.requests[0]),
            ReasonCode.MANUAL_REVIEW_REQUIRED,
        )

    def test_cpsat_quota_gate_agrees_with_the_notary(self):
        if importlib.util.find_spec("ortools") is None:
            self.skipTest("ortools not installed")
        from mobiroute.solvers.cpsat import solve_cpsat

        problem, _result = curb_wait_case()
        result = solve_cpsat(problem)
        self.assertTrue(result.verified_feasible, result.objective_values)
        self.assertNotIn("t", result.served_requests)
