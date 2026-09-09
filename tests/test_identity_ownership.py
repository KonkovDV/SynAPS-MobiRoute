"""One signer for `input_hash`; one identity per published configuration."""

import unittest

from mobiroute.solvers.alns import solve_alns
from mobiroute.solvers.finalize import plan_identity
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.solvers.rolling_horizon import solve_rolling_horizon

from .factories import driver, problem, trip, vehicle


def _trips():
    return [
        trip("t1", "Z_NORTH", "Z_SOUTH"),
        trip("t2", "Z_EAST", "Z_WEST"),
    ]


def _day(trips):
    return problem(
        [vehicle("veh-1"), vehicle("veh-2", depot="Z_DEPOT_2")],
        [driver("drv-1"), driver("drv-2", depot="Z_DEPOT_2")],
        trips,
    )


class InputHashOwnershipTest(unittest.TestCase):
    def test_every_solver_publishes_the_same_problem_identity(self) -> None:
        day = _day(_trips())
        published = {
            "GREEDY": solve_greedy(day),
            "ALNS": solve_alns(day, iterations=2),
            "RHC": solve_rolling_horizon(day, window_minutes=60, overlap_minutes=0),
        }
        hashes = {name: r.input_hash for name, r in published.items()}
        self.assertEqual(len(set(hashes.values())), 1, hashes)
        for name, result in published.items():
            with self.subTest(solver=name):
                self.assertTrue(result.input_hash)
                self.assertEqual(result.plan_id, plan_identity(result))
        plan_ids = {r.plan_id for r in published.values()}
        self.assertEqual(len(plan_ids), len(published))

    def test_a_different_problem_cannot_keep_the_same_input_hash(self) -> None:
        base = solve_greedy(_day(_trips()))
        more = solve_greedy(_day([*_trips(), trip("t3", "Z_NORTH", "Z_EAST")]))
        self.assertNotEqual(base.input_hash, more.input_hash)


class ReplayDeterminismTest(unittest.TestCase):
    def _assert_same_identity(self, first, second) -> None:
        self.assertEqual(first.input_hash, second.input_hash)
        self.assertEqual(first.config_hash, second.config_hash)
        self.assertEqual(first.plan_id, second.plan_id)
        self.assertEqual(first.served_requests, second.served_requests)

    def test_greedy_replays_to_one_identity(self) -> None:
        day = _day(_trips())
        self._assert_same_identity(solve_greedy(day), solve_greedy(day))

    def test_alns_replays_to_one_identity(self) -> None:
        day = _day(_trips())
        first = solve_alns(day, iterations=3, rng_seed=7)
        second = solve_alns(day, iterations=3, rng_seed=7)
        self._assert_same_identity(first, second)

    def test_rhc_replays_to_one_identity(self) -> None:
        day = _day(_trips())
        first = solve_rolling_horizon(day, window_minutes=60, overlap_minutes=0)
        second = solve_rolling_horizon(day, window_minutes=60, overlap_minutes=0)
        self._assert_same_identity(first, second)
