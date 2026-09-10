"""CP-SAT fallback must not inherit the greedy seed's plan identity."""

from __future__ import annotations

import sys
import unittest
from unittest import mock

from mobiroute.domain.models import SolutionStatus
from mobiroute.solvers.cpsat import solve_cpsat
from mobiroute.solvers.finalize import plan_identity
from mobiroute.solvers.greedy import solve_greedy

from .factories import driver, problem, trip, vehicle


class CpsatFallbackIdentityTest(unittest.TestCase):
    def test_too_large_fallback_publishes_its_own_identity(self) -> None:
        reqs = [
            trip(
                f"t{i:02d}",
                "Z_NORTH",
                "Z_SOUTH",
                earliest=60,
                latest=480,
                max_wait=200,
                max_ride=200,
            )
            for i in range(41)
        ]
        day = problem([vehicle("v1")], [driver("d1")], reqs)
        greedy = solve_greedy(day)
        fallback = solve_cpsat(day)
        self.assertEqual(fallback.solution_type, "CPSAT_FALLBACK_GREEDY")
        self.assertEqual(fallback.input_hash, greedy.input_hash)
        self.assertNotEqual(fallback.config_hash, greedy.config_hash)
        self.assertNotEqual(fallback.plan_id, greedy.plan_id)
        self.assertEqual(fallback.plan_id, plan_identity(fallback))
        self.assertEqual(
            fallback.solver_config.get("reason"),
            "instance_too_large_for_tiny_cpsat",
        )

    def test_a_missing_engine_is_not_a_verdict_on_the_published_plan(self) -> None:
        day = problem([vehicle("v1")], [driver("d1")], [trip("t1", "Z_NORTH", "Z_SOUTH")])
        greedy = solve_greedy(day)
        # None in sys.modules makes the lazy OR-Tools import raise ImportError.
        with mock.patch.dict(sys.modules, {"ortools.sat.python": None}):
            fallback = solve_cpsat(day)
        self.assertEqual(fallback.solution_type, "CPSAT_FALLBACK_GREEDY")
        self.assertEqual(fallback.solver_config.get("reason"), "ortools_missing")
        self.assertEqual(fallback.solver_config.get("error"), "ortools_missing")
        self.assertEqual(fallback.verified_feasible, greedy.verified_feasible)
        self.assertEqual(fallback.served_requests, greedy.served_requests)
        # A verified plan is not published as an error, and a fallback is never exact.
        self.assertNotIn(
            fallback.status,
            {
                SolutionStatus.ERROR.value,
                SolutionStatus.OPTIMAL.value,
                SolutionStatus.FEASIBLE.value,
            },
        )
        self.assertFalse(fallback.solver_config["proven_optimal"])
        self.assertNotEqual(fallback.config_hash, greedy.config_hash)
        self.assertEqual(fallback.plan_id, plan_identity(fallback))


if __name__ == "__main__":
    unittest.main()
