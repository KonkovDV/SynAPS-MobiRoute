"""Rolling-horizon window edges: a pickup on a window end is not lost."""

import unittest

from mobiroute.solvers.rolling_horizon import _window_ends, solve_rolling_horizon

from .factories import driver, problem, trip, vehicle


class WindowEndsTest(unittest.TestCase):
    def test_the_last_end_is_strictly_past_the_last_visible_pickup(self) -> None:
        cases = ((180, 30, 600), (60, 0, 60), (45, 44, 200), (1, 0, 3), (0, 5, 12))
        for window, overlap, t_last in cases:
            with self.subTest(window=window, overlap=overlap, t_last=t_last):
                ends = _window_ends(0, t_last, window, overlap)
                self.assertTrue(ends)
                self.assertGreater(ends[-1], t_last)
                self.assertEqual(ends, sorted(set(ends)))

    def test_overlap_at_or_above_the_window_still_advances(self) -> None:
        ends = _window_ends(0, 300, 60, 90)
        self.assertGreater(ends[-1], 300)
        steps = {b - a for a, b in zip(ends, ends[1:], strict=False)}
        self.assertTrue(steps)
        self.assertGreaterEqual(min(steps), 1)

    def test_a_pickup_on_the_edge_needs_the_next_window(self) -> None:
        # Visibility is `earliest_pickup < window_end`, so a pickup exactly on
        # the end is deferred; the last window is open by construction.
        self.assertEqual(_window_ends(60, 120, 60, 0), [120, 180])


class RollingHorizonBoundaryTest(unittest.TestCase):
    def test_pickup_on_a_window_edge_is_still_accounted(self) -> None:
        day = problem(
            [vehicle("veh-1"), vehicle("veh-2", depot="Z_DEPOT_2")],
            [driver("drv-1"), driver("drv-2", depot="Z_DEPOT_2")],
            [
                trip("t1", "Z_NORTH", "Z_SOUTH", earliest=60, latest=180),
                trip("t2", "Z_EAST", "Z_WEST", earliest=120, latest=240),
            ],
        )
        out = solve_rolling_horizon(day, window_minutes=60, overlap_minutes=0)
        accounted = set(out.served_requests) | {r.trip_id for r in out.rejected_requests}
        self.assertEqual(accounted, {"t1", "t2"})
        self.assertEqual(out.solution_type, "RHC")
        self.assertEqual(out.solver_config["windows"], 2)
        self.assertTrue(out.verified_feasible)
