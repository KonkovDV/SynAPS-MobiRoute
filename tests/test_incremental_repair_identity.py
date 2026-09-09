"""The repair lane publishes its own identity, not the recovery lane's."""

import unittest

from mobiroute.dispatch.online_insertion import recover_disruption
from mobiroute.solvers.finalize import plan_identity
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.solvers.incremental_repair import solve_incremental_repair

from .factories import driver, problem, trip, vehicle


def _day():
    return problem(
        [vehicle("veh-1"), vehicle("veh-2", depot="Z_DEPOT_2")],
        [driver("drv-1"), driver("drv-2", depot="Z_DEPOT_2")],
        [
            trip("t1", "Z_NORTH", "Z_SOUTH"),
            trip("t2", "Z_EAST", "Z_WEST"),
        ],
    )


class IncrementalRepairIdentityTest(unittest.TestCase):
    def test_published_plan_id_matches_the_published_configuration(self) -> None:
        day = _day()
        base = solve_greedy(day)
        _updated, out, _diff = solve_incremental_repair(day, base, traffic_delay_minutes=5)
        self.assertEqual(out.solution_type, "INCREMENTAL_REPAIR")
        self.assertEqual(out.solver_config["name"], "INCREMENTAL_REPAIR")
        self.assertTrue(out.input_hash)
        self.assertEqual(out.plan_id, plan_identity(out))

    def test_the_repair_lane_does_not_reuse_the_recovery_identity(self) -> None:
        day_a = _day()
        base_a = solve_greedy(day_a)
        _u1, recovered, _d1 = recover_disruption(day_a, base_a, traffic_delay_minutes=5)
        day_b = _day()
        base_b = solve_greedy(day_b)
        _u2, repaired, _d2 = solve_incremental_repair(day_b, base_b, traffic_delay_minutes=5)
        self.assertEqual(recovered.input_hash, repaired.input_hash)
        self.assertNotEqual(recovered.config_hash, repaired.config_hash)
        self.assertNotEqual(recovered.plan_id, repaired.plan_id)
        self.assertEqual(recovered.served_requests, repaired.served_requests)

    def test_replay_of_the_repair_lane_is_deterministic(self) -> None:
        day_a = _day()
        _u1, first, _d1 = solve_incremental_repair(
            day_a, solve_greedy(day_a), traffic_delay_minutes=5
        )
        day_b = _day()
        _u2, second, _d2 = solve_incremental_repair(
            day_b, solve_greedy(day_b), traffic_delay_minutes=5
        )
        self.assertEqual(first.input_hash, second.input_hash)
        self.assertEqual(first.config_hash, second.config_hash)
        self.assertEqual(first.plan_id, second.plan_id)
        self.assertEqual(first.served_requests, second.served_requests)
