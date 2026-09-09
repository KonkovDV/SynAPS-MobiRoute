"""A manual override republishes reasons, explanations and identity."""

from __future__ import annotations

import unittest

from mobiroute.dispatch.manual_override import ManualOverride, OverrideJournal
from mobiroute.domain.models import ReasonCode
from mobiroute.solvers.finalize import plan_identity
from mobiroute.solvers.greedy import solve_greedy

from .factories import driver, problem, trip, vehicle


def _day():
    return problem(
        [vehicle("veh-1"), vehicle("veh-2", depot="Z_DEPOT_2")],
        [driver("drv-1"), driver("drv-2", depot="Z_DEPOT_2")],
        [trip("t1", "Z_NORTH", "Z_SOUTH"), trip("t2", "Z_EAST", "Z_WEST")],
    )


def _entry(trip_id="t1"):
    return ManualOverride(
        operator_id="op-7",
        trip_id=trip_id,
        action="REJECT",
        free_text_reason="passenger refused the ride at the curb",
    )


class ManualOverrideIdentityTest(unittest.TestCase):
    def setUp(self):
        self.day = _day()
        self.base = solve_greedy(self.day)

    def _reject_first_served(self):
        served = list(self.base.served_requests)
        if not served:
            self.skipTest("nothing served to override")
        tid = served[0]
        return tid, OverrideJournal().apply_reject(self.base, tid, _entry(tid))

    def test_the_override_publishes_its_own_identity(self):
        tid, out = self._reject_first_served()
        self.assertNotIn(tid, out.served_requests)
        self.assertIn(tid, {r.trip_id for r in out.rejected_requests})
        self.assertEqual(out.input_hash, self.base.input_hash)
        self.assertNotEqual(out.config_hash, self.base.config_hash)
        self.assertNotEqual(out.plan_id, self.base.plan_id)
        self.assertEqual(out.plan_id, plan_identity(out))

    def test_the_override_cannot_keep_an_accepted_explanation(self):
        tid, out = self._reject_first_served()
        records = [e for e in out.explanations if e.trip_id == tid]
        self.assertTrue(records)
        for ex in records:
            self.assertFalse(ex.accepted)
            self.assertEqual(ex.reason_code, ReasonCode.MANUAL_REVIEW_REQUIRED.value)

    def test_the_entry_must_name_the_overridden_trip(self):
        journal = OverrideJournal()
        with self.assertRaises(ValueError):
            journal.apply_reject(self.base, "t1", _entry("t2"))
        self.assertEqual(journal.entries, [])

    def test_an_empty_reason_is_still_refused(self):
        blank = _entry().model_copy(update={"free_text_reason": "   "})
        with self.assertRaises(ValueError):
            OverrideJournal().record(blank)


if __name__ == "__main__":
    unittest.main()
