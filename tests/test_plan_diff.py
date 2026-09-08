"""PlanDiff must report retiming, frozen clock breaks and add/remove-only routes."""

import unittest

from mobiroute.dispatch.online_insertion import compute_diff
from mobiroute.domain.requests import PlanDiff, PlanningResult

from .test_quota_evidence import quota_case


def replay(result: PlanningResult) -> PlanningResult:
    return PlanningResult.model_validate_json(result.model_dump_json())


class PlanDiffContractTests(unittest.TestCase):
    def test_same_vehicle_retiming_is_temporal_churn_not_a_move(self):
        _problem, baseline = quota_case()
        new = replay(baseline)
        new.input_hash = "new-input"
        new.route_plans[0].arrival_times["do"] += 7
        new.route_plans[0].departure_times["do"] += 7
        diff = compute_diff(baseline, new, frozen_ids=set())
        self.assertEqual(diff.moved_trips, [])
        self.assertEqual(diff.changed_vehicle_assignments, [])
        self.assertEqual(diff.retimed_trips, ["t"])
        self.assertEqual(diff.changed_routes, ["vehicle-t"])
        self.assertEqual(diff.retimed_routes, ["vehicle-t"])
        self.assertEqual(diff.plan_churn["changed_trips"], 0.0)
        self.assertEqual(diff.plan_churn["temporal_churn"], 1.0)
        self.assertGreater(diff.plan_churn["changed_routes"], 0.0)

    def test_frozen_clock_shift_is_broken_not_unchanged(self):
        _problem, baseline = quota_case()
        new = replay(baseline)
        new.route_plans[0].arrival_times["do"] += 4
        new.route_plans[0].departure_times["do"] += 4
        diff = compute_diff(baseline, new, frozen_ids={"t"})
        self.assertEqual(diff.unchanged_frozen_trips, [])
        self.assertEqual(diff.broken_frozen_trips, ["t"])
        self.assertEqual(diff.plan_churn["broken_frozen"], 1.0)

    def test_driver_change_without_vehicle_move(self):
        _problem, baseline = quota_case()
        new = replay(baseline)
        new.route_plans[0].driver_id = "other-driver"
        diff = compute_diff(baseline, new, frozen_ids={"t"})
        self.assertEqual(diff.moved_trips, [])
        self.assertEqual(diff.changed_driver_trips, ["t"])
        self.assertEqual(diff.broken_frozen_trips, ["t"])
        self.assertIn("vehicle-t", diff.changed_routes)

    def test_add_only_and_remove_only_routes_are_changed_routes(self):
        _problem, baseline = quota_case()
        _problem, added = quota_case(tid="u", offset=40)
        combined = replay(baseline)
        combined.served_requests.append("u")
        combined.route_plans.append(added.route_plans[0])
        add_diff = compute_diff(baseline, combined, frozen_ids=set())
        self.assertEqual(add_diff.added_trips, ["u"])
        self.assertEqual(add_diff.added_routes, ["vehicle-u"])
        self.assertIn("vehicle-u", add_diff.changed_routes)
        self.assertEqual(add_diff.plan_churn["changed_trips"], 1.0)

        remove_diff = compute_diff(combined, baseline, frozen_ids=set())
        self.assertEqual(remove_diff.removed_trips, ["u"])
        self.assertEqual(remove_diff.removed_routes, ["vehicle-u"])
        self.assertIn("vehicle-u", remove_diff.changed_routes)

    def test_lists_are_sorted_and_json_round_trip_preserves_diff(self):
        _problem, left = quota_case(tid="b")
        _second, right = quota_case(tid="a", offset=30)
        left.served_requests.append("a")
        left.route_plans.append(right.route_plans[0])
        new = replay(left)
        new.route_plans[0].arrival_times["do"] += 1
        new.route_plans[0].departure_times["do"] += 1
        new.route_plans[1].driver_id = "shifted"
        diff = compute_diff(left, new, frozen_ids={"b", "a"})
        self.assertEqual(diff.broken_frozen_trips, sorted(diff.broken_frozen_trips))
        self.assertEqual(diff.retimed_trips, sorted(diff.retimed_trips))
        self.assertEqual(diff.changed_routes, sorted(diff.changed_routes))
        replayed = PlanDiff.model_validate_json(diff.model_dump_json())
        self.assertEqual(replayed.model_dump(mode="json"), diff.model_dump(mode="json"))
