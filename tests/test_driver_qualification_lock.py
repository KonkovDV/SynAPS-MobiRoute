"""Search must not keep an untrained driver once a trip needs assistance."""

from __future__ import annotations

import unittest

from mobiroute.domain.requests import DayProblem, PlanningResult
from mobiroute.solvers.beam import solve_beam
from mobiroute.solvers.nearest import solve_nearest
from mobiroute.validation.feasibility import check_plan
from tests.factories import driver, problem, trip, vehicle

PLAIN = "aa-plain"
TRAINED = "zz-trained"


def mixed_assistance_case() -> DayProblem:
    """One van, an untrained driver that sorts first, then a later assist trip."""
    return problem(
        [vehicle("v1")],
        [driver(PLAIN, trained=False), driver(TRAINED, trained=True)],
        [
            trip("a1", "Z_NORTH", "Z_SOUTH", earliest=60, latest=300, max_wait=120),
            trip(
                "b2",
                "Z_NORTH",
                "Z_SOUTH",
                earliest=240,
                latest=480,
                max_wait=120,
                assist=True,
            ),
        ],
    )


class DriverQualificationLockTest(unittest.TestCase):
    def _assert_trained_driver_holds_it(self, day: DayProblem, res: PlanningResult) -> None:
        self.assertIn("b2", res.served_requests)
        for plan in res.route_plans:
            onboard = {s.trip_id for s in plan.ordered_stops if s.trip_id}
            if "b2" in onboard:
                self.assertEqual(plan.driver_id, TRAINED)
        report = check_plan(day, res)
        self.assertEqual(
            [v for v in report.violations if "DRIVER" in v or "ASSIST" in v],
            [],
            report.violations,
        )

    def test_nearest_reassigns_a_trained_driver(self) -> None:
        day = mixed_assistance_case()
        self._assert_trained_driver_holds_it(day, solve_nearest(day))

    def test_beam_reassigns_a_trained_driver(self) -> None:
        day = mixed_assistance_case()
        self._assert_trained_driver_holds_it(day, solve_beam(day))

    def test_a_trip_without_assistance_keeps_the_first_free_driver(self) -> None:
        day = problem(
            [vehicle("v1")],
            [driver(PLAIN, trained=False), driver(TRAINED, trained=True)],
            [trip("a1", "Z_NORTH", "Z_SOUTH", earliest=60, latest=300, max_wait=120)],
        )
        result = solve_nearest(day)
        self.assertEqual([plan.driver_id for plan in result.route_plans], [PLAIN])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
