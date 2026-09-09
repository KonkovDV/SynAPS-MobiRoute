"""Published explanations must agree with the served and rejected sets."""

import unittest

from mobiroute.domain.models import ReasonCode
from mobiroute.domain.requests import RejectedTrip, TripExplanation
from mobiroute.solvers.finalize import finalize_result

from .test_quota_evidence import quota_case


class ExplanationReconcileTest(unittest.TestCase):
    def test_served_trip_cannot_publish_a_rejection_explanation(self) -> None:
        problem, result = quota_case(quota=None)
        tid = problem.requests[0].id
        base = result.model_copy(update={"served_requests": [tid], "rejected_requests": []})
        out = finalize_result(
            problem,
            base,
            explanations=[
                TripExplanation(
                    trip_id=tid,
                    accepted=False,
                    why_this_route="stale peel record",
                    reason_code=ReasonCode.QUOTA_EXCEEDED.value,
                )
            ],
        )
        self.assertIn(tid, out.served_requests)
        hit = [e for e in out.explanations if e.trip_id == tid]
        self.assertEqual(len(hit), 1)
        self.assertTrue(hit[0].accepted)
        self.assertEqual(hit[0].reason_code, ReasonCode.ACCEPTED.value)

    def test_a_trip_on_both_sides_keeps_the_rejection(self) -> None:
        problem, result = quota_case(quota=None)
        tid = problem.requests[0].id
        planted = result.model_copy(
            update={
                "served_requests": [tid],
                "rejected_requests": [
                    RejectedTrip(trip_id=tid, reason_code=ReasonCode.QUOTA_EXCEEDED.value)
                ],
            }
        )
        out = finalize_result(
            problem,
            planted,
            explanations=[
                TripExplanation(
                    trip_id=tid,
                    accepted=True,
                    why_this_route="lex insert succeeded",
                    reason_code=ReasonCode.ACCEPTED.value,
                )
            ],
        )
        hit = [e for e in out.explanations if e.trip_id == tid]
        self.assertEqual(len(hit), 1)
        self.assertFalse(hit[0].accepted)
        self.assertEqual(hit[0].reason_code, ReasonCode.QUOTA_EXCEEDED.value)
