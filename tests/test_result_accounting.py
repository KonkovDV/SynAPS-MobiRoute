"""Malformed result partitions must not acquire a feasible/notary status."""

import unittest

from mobiroute.domain.models import BookingStatus
from mobiroute.domain.requests import PlanningResult, RejectedTrip
from mobiroute.validation.completeness import incomplete_plan_issues
from mobiroute.validation.feasibility import check_plan

from .test_quota_evidence import quota_case


def reject(result, tid="t", code="MANUAL_REVIEW_REQUIRED"):
    result.served_requests = []
    result.route_plans = []
    result.rejected_requests = [RejectedTrip(trip_id=tid, reason_code=code)]


class ResultAccountingTests(unittest.TestCase):
    def assert_invalid(self, problem, result, violation):
        restored = PlanningResult.model_validate_json(result.model_dump_json())
        report = check_plan(problem, restored)
        self.assertFalse(report.feasible, report.violations)
        self.assertIn(violation, report.violations)

    def test_duplicate_served_ids_cannot_inflate_service_counts(self):
        problem, result = quota_case()
        result.served_requests.append("t")
        self.assert_invalid(problem, result, "DUPLICATE_SERVED:t")

    def test_duplicate_rejections_are_not_a_partition(self):
        problem, result = quota_case()
        reject(result)
        result.rejected_requests.append(result.rejected_requests[0].model_copy())
        self.assert_invalid(problem, result, "DUPLICATE_REJECTED:t")

    def test_served_and_rejected_are_disjoint(self):
        problem, result = quota_case()
        result.rejected_requests = [RejectedTrip(trip_id="t", reason_code="NO_CAPACITY")]
        self.assert_invalid(problem, result, "SERVED_AND_REJECTED:t")

    def test_unknown_rejections_are_not_counted(self):
        problem, result = quota_case()
        result.rejected_requests = [RejectedTrip(trip_id="ghost", reason_code="NO_DRIVER")]
        self.assert_invalid(problem, result, "UNKNOWN_REJECTED:ghost")

    def test_unknown_served_ids_are_rejected_by_accounting(self):
        problem, result = quota_case()
        result.served_requests.append("ghost")
        self.assertIn("UNKNOWN_SERVED:ghost", incomplete_plan_issues(problem, result))
        self.assert_invalid(problem, result, "UNKNOWN_SERVED:ghost")

    def test_inactive_requests_must_not_be_served(self):
        for status in (BookingStatus.CANCELLED, BookingStatus.NO_SHOW):
            with self.subTest(status=status):
                problem, result = quota_case()
                problem.requests[0].booking_status = status
                self.assert_invalid(problem, result, "INACTIVE_SERVED:t")

    def test_active_rejections_cannot_masquerade_as_inactive(self):
        for code in ("CANCELLED", "NO_SHOW"):
            with self.subTest(code=code):
                problem, result = quota_case()
                reject(result, code=code)
                self.assert_invalid(problem, result, "REJECTION_STATUS_MISMATCH:t")

    def test_valid_service_and_rejection_remain_valid(self):
        problem, result = quota_case()
        self.assertTrue(check_plan(problem, result).feasible)
        reject(result)
        self.assertTrue(check_plan(problem, result).feasible)

    def test_inactive_accounting_is_optional_but_cannot_lie(self):
        for status in (BookingStatus.CANCELLED, BookingStatus.NO_SHOW):
            with self.subTest(status=status):
                problem, result = quota_case()
                problem.requests[0].booking_status = status
                reject(result, code=status.value)
                self.assertTrue(check_plan(problem, result).feasible)
                result.rejected_requests = []
                self.assertTrue(check_plan(problem, result).feasible)
                wrong = "CANCELLED" if status == BookingStatus.NO_SHOW else "NO_SHOW"
                reject(result, code=wrong)
                self.assert_invalid(problem, result, "REJECTION_STATUS_MISMATCH:t")

    def test_missing_active_requests_are_still_diagnosed(self):
        problem, result = quota_case()
        result.served_requests = []
        result.route_plans = []
        self.assert_invalid(problem, result, "UNACCOUNTED:t")

    def test_accounting_is_deterministic_and_non_mutating(self):
        problem, result = quota_case()
        result.served_requests.extend(["z", "a", "t"])
        before = result.model_dump_json()
        first = incomplete_plan_issues(problem, result)
        result.served_requests.reverse()
        self.assertEqual(incomplete_plan_issues(problem, result), first)
        result.served_requests.reverse()
        self.assertEqual(result.model_dump_json(), before)
