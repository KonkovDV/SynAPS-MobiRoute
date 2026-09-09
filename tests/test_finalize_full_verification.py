"""Finalize must verify the whole plan, not only the vehicles that changed."""

from __future__ import annotations

import unittest

from mobiroute.domain.models import SolutionStatus
from mobiroute.domain.requests import DayProblem
from mobiroute.solvers.finalize import finalize_result
from mobiroute.solvers.nearest import solve_nearest
from tests.factories import driver, problem, trip, vehicle


def one_route_day() -> DayProblem:
    return problem(
        [vehicle("v1"), vehicle("v2", depot="Z_DEPOT_2")],
        [driver("d1"), driver("d2", depot="Z_DEPOT_2")],
        [trip("a1", "Z_NORTH", "Z_SOUTH", earliest=60, latest=300, max_wait=120)],
    )


class FinalizeFullVerificationTest(unittest.TestCase):
    def test_a_violation_outside_the_changed_vehicles_is_still_reported(self) -> None:
        day = one_route_day()
        baseline = solve_nearest(day)
        self.assertEqual(len(baseline.route_plans), 1)
        broken = baseline.model_copy(
            update={
                "route_plans": [
                    plan.model_copy(update={"driver_id": None, "driver_assignment": None})
                    for plan in baseline.route_plans
                ],
            }
        )
        # The online caller reports that only the other vehicle changed; finalize
        # still notaries the planted driverless route.
        clean = finalize_result(day, baseline.model_copy())
        checked = finalize_result(day, broken)
        self.assertFalse(checked.verified_feasible, checked.objective_values)
        self.assertEqual(checked.status, SolutionStatus.NOT_VERIFIED.value)
        self.assertGreater(
            checked.objective_values["violations"],
            clean.objective_values["violations"],
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
