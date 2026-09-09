"""CP-SAT fallback must not inherit the greedy seed's plan identity."""

from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
