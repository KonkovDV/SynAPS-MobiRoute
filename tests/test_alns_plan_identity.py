"""ALNS must publish its own identity, not the greedy seed's plan_id."""

import unittest

from mobiroute.solvers.alns import solve_alns
from mobiroute.solvers.finalize import plan_identity
from mobiroute.solvers.greedy import solve_greedy

from .factories import driver, problem, trip, vehicle


def _day():
    return problem(
        [vehicle("veh-1"), vehicle("veh-2")],
        [driver("drv-1"), driver("drv-2")],
        [
            trip("t1", "Z_NORTH", "Z_SOUTH"),
            trip("t2", "Z_EAST", "Z_WEST"),
            trip("t3", "Z_NORTH", "Z_EAST"),
        ],
    )


class AlnsPlanIdentityTest(unittest.TestCase):
    def test_alns_does_not_inherit_the_greedy_seed_identity(self) -> None:
        day = _day()
        greedy = solve_greedy(day)
        alns = solve_alns(day, iterations=2)
        self.assertTrue(alns.plan_id)
        self.assertNotEqual(alns.plan_id, greedy.plan_id)
        self.assertEqual(alns.plan_id, plan_identity(alns))

    def test_two_alns_configurations_do_not_share_one_identity(self) -> None:
        day = _day()
        light = solve_alns(day, iterations=2)
        heavy = solve_alns(day, iterations=6, destroy_frac=0.5)
        self.assertNotEqual(light.config_hash, heavy.config_hash)
        self.assertNotEqual(light.plan_id, heavy.plan_id)

    def test_one_configuration_replays_to_one_identity(self) -> None:
        day = _day()
        first = solve_alns(day, iterations=2)
        second = solve_alns(day, iterations=2)
        self.assertEqual(first.input_hash, second.input_hash)
        self.assertEqual(first.config_hash, second.config_hash)
        self.assertEqual(first.plan_id, second.plan_id)
