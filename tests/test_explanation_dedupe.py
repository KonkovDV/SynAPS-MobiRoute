"""One trip publishes one explanation, even when two records reach finalize."""

from __future__ import annotations

import unittest

from mobiroute.domain.models import ReasonCode
from mobiroute.domain.requests import TripExplanation
from mobiroute.solvers.finalize import _reconcile_explanations
from mobiroute.solvers.greedy import solve_greedy

from .factories import driver, problem, trip, vehicle


def _day():
    return problem(
        [vehicle("veh-1"), vehicle("veh-2", depot="Z_DEPOT_2")],
        [driver("drv-1"), driver("drv-2", depot="Z_DEPOT_2")],
        [trip("t1", "Z_NORTH", "Z_SOUTH"), trip("t2", "Z_EAST", "Z_WEST")],
    )


class ExplanationDedupeTest(unittest.TestCase):
    def setUp(self):
        self.base = solve_greedy(_day())

    def test_a_served_trip_keeps_one_record(self):
        served = list(self.base.served_requests)
        if not served:
            self.skipTest("nothing served to explain")
        tid = served[0]
        stale = TripExplanation(
            trip_id=tid,
            accepted=False,
            why_this_route="stale record from an earlier pass",
            reason_code=ReasonCode.MANUAL_REVIEW_REQUIRED.value,
        )
        fresh = TripExplanation(
            trip_id=tid,
            accepted=True,
            why_this_route="Served in the published plan; see the route.",
            reason_code=ReasonCode.ACCEPTED.value,
        )
        doubled = self.base.model_copy(update={"explanations": [stale, fresh]})
        records = [e for e in _reconcile_explanations(doubled) if e.trip_id == tid]
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0].accepted)

    def test_reconciled_ids_are_unique(self):
        both = list(self.base.explanations) + list(self.base.explanations)
        doubled = self.base.model_copy(update={"explanations": both})
        ids = [e.trip_id for e in _reconcile_explanations(doubled)]
        self.assertEqual(len(ids), len(set(ids)))
        expected = {e.trip_id for e in self.base.explanations}
        expected |= {r.trip_id for r in self.base.rejected_requests}
        self.assertEqual(set(ids), expected)


if __name__ == "__main__":
    unittest.main()
