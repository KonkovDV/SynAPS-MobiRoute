"""Every dispatch exit must publish a freshly verified, replayable child plan."""

import unittest
from unittest.mock import patch

from mobiroute.adapters.fingerprint import fingerprint, fingerprint_problem
from mobiroute.dispatch.online_insertion import online_insert, recover_disruption
from mobiroute.domain.requests import DayProblem, PlanningResult, TravelMatrix
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.validation.feasibility import check_plan

from .test_native_cache_contract import problem, trip


class OnlineResultLineageTests(unittest.TestCase):
    def assert_version(self, updated, baseline, result, diff):
        report = check_plan(updated, result)
        config = {
            k: v
            for k, v in result.solver_config.items()
            if k not in {"verified_feasible", "proven_optimal"}
        }
        self.assertEqual(result.input_hash, fingerprint_problem(updated))
        self.assertEqual(result.config_hash, fingerprint(config))
        self.assertEqual(result.verified_feasible, report.feasible)
        self.assertEqual(result.objective_values["violations"], len(report.violations))
        self.assertEqual(result.objective_values["served"], len(result.served_requests))
        self.assertEqual(result.objective_values["rejected"], len(result.rejected_requests))
        self.assertEqual(result.base_plan_id, baseline.plan_id)
        self.assertNotEqual(result.plan_id, baseline.plan_id)
        self.assertNotEqual(result.status, "OPTIMAL")
        self.assertEqual(diff.new_fingerprint, result.input_hash + ":" + result.config_hash)

    def test_accepted_insertion_has_current_input_and_config(self):
        p = problem()
        baseline = solve_greedy(p)
        updated, result, diff = online_insert(p, baseline, trip("new"), protect_frozen=False)
        self.assertTrue(result.verified_feasible)
        self.assertEqual(set(result.served_requests), {"base", "new"})
        self.assert_version(updated, baseline, result, diff)
        self.assertFalse(result.solver_config["protect_frozen"])

    def test_rejected_insertion_is_also_finalized(self):
        p = problem()
        baseline = solve_greedy(p)
        request = trip("new").model_copy(update={"max_ride_time": 1})
        updated, result, diff = online_insert(p, baseline, request)
        self.assertTrue(result.verified_feasible)
        self.assertEqual(result.status, "PARTIAL")
        self.assertEqual([r.trip_id for r in result.rejected_requests], ["new"])
        self.assert_version(updated, baseline, result, diff)
        self.assertTrue(any(e.trip_id == "new" and not e.accepted for e in result.explanations))

    def test_rejection_cannot_inherit_forged_baseline_verification(self):
        p = problem()
        baseline = solve_greedy(p)
        baseline.route_plans[0].ride_times["base"] = 999
        before = baseline.model_dump_json()
        request = trip("new").model_copy(update={"max_ride_time": 1})
        updated, result, diff = online_insert(p, baseline, request)
        self.assertFalse(result.verified_feasible)
        self.assertEqual(result.status, "NOT_VERIFIED")
        self.assert_version(updated, baseline, result, diff)
        self.assertEqual(baseline.model_dump_json(), before)

    def test_rejection_rechecks_unchanged_routes_against_current_matrix(self):
        p = problem()
        baseline = solve_greedy(p)
        p.travel = TravelMatrix(zones=["d", "p"], minutes=[[0, 30], [30, 0]])
        request = trip("new").model_copy(update={"max_ride_time": 1})
        updated, result, diff = online_insert(p, baseline, request)
        self.assertFalse(result.verified_feasible)
        self.assert_version(updated, baseline, result, diff)

    def test_same_id_different_rejected_payloads_have_distinct_events(self):
        p = problem()
        baseline = solve_greedy(p)
        a = trip("new").model_copy(update={"max_ride_time": 1})
        b = a.model_copy(update={"max_ride_time": 2})
        _, first, _ = online_insert(p, baseline, a)
        _, second, _ = online_insert(p, baseline, b)
        self.assertNotEqual(first.event_id, second.event_id)
        self.assertNotEqual(first.plan_id, second.plan_id)

    def test_json_replay_and_input_immutability_on_both_outcomes(self):
        for max_ride in (1, 100):
            with self.subTest(max_ride=max_ride):
                p = problem()
                baseline = solve_greedy(p)
                request = trip("new").model_copy(update={"max_ride_time": max_ride})
                before = (p.model_dump_json(), baseline.model_dump_json(), request.model_dump_json())
                _, first, _ = online_insert(p, baseline, request, protect_frozen=False)
                _, second, _ = online_insert(
                    DayProblem.model_validate_json(before[0]),
                    PlanningResult.model_validate_json(before[1]),
                    request.model_copy(deep=True),
                    protect_frozen=False,
                )
                self.assertEqual(first.model_dump(mode="json"), second.model_dump(mode="json"))
                self.assertEqual(
                    before,
                    (p.model_dump_json(), baseline.model_dump_json(), request.model_dump_json()),
                )

    def test_rejected_child_does_not_share_mutable_routes_with_parent(self):
        p = problem()
        baseline = solve_greedy(p)
        before = baseline.model_dump_json()
        request = trip("new").model_copy(update={"max_ride_time": 1})
        _, result, _ = online_insert(p, baseline, request)
        result.route_plans[0].ride_times["base"] = 888
        self.assertEqual(baseline.model_dump_json(), before)

    def test_freeze_policy_is_part_of_execution_config(self):
        p = problem()
        baseline = solve_greedy(p)
        request = trip("new").model_copy(update={"max_ride_time": 1})
        _, protected, _ = online_insert(p, baseline, request, protect_frozen=True)
        _, flexible, _ = online_insert(p, baseline, request, protect_frozen=False)
        self.assertNotEqual(protected.config_hash, flexible.config_hash)
        self.assertNotEqual(protected.event_id, flexible.event_id)

    def test_frozen_rollback_is_finalized_too(self):
        p = problem()
        baseline = solve_greedy(p)
        # Inject a materialization fault at the guard, not a substitute native engine.
        maps = [{"base": "v"}, {"base": "other", "new": "v"}, {"base": "v"}, {"base": "v"}]
        with patch("mobiroute.dispatch.online_insertion._trip_vehicle", side_effect=maps):
            updated, result, diff = online_insert(p, baseline, trip("new"))
        self.assertTrue(any("frozen" in r.detail for r in result.rejected_requests))
        self.assert_version(updated, baseline, result, diff)

    def test_appointment_payload_and_compound_disruptions_are_distinct(self):
        p = problem()
        baseline = solve_greedy(p)
        _, first, _ = recover_disruption(
            p,
            baseline,
            appointment_trip_id="base",
            appointment_end=80,
        )
        updated, second, diff = recover_disruption(
            p,
            baseline,
            appointment_trip_id="base",
            appointment_end=90,
        )
        _, compound, _ = recover_disruption(
            p,
            baseline,
            cancel_trip_id="base",
            appointment_trip_id="base",
            appointment_end=90,
        )
        self.assertEqual(len({first.event_id, second.event_id, compound.event_id}), 3)
        self.assertEqual(len({first.plan_id, second.plan_id, compound.plan_id}), 3)
        self.assert_version(updated, baseline, second, diff)
