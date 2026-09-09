"""A seated driver is not a licence: online insert re-checks every new need."""

import unittest

from mobiroute.dispatch.online_insertion import online_insert
from mobiroute.solvers.greedy import solve_greedy

from .factories import driver, problem, trip, vehicle


class OnlineDriverQualificationTest(unittest.TestCase):
    def test_untrained_seated_driver_cannot_take_a_boarding_assistance_trip(self) -> None:
        veh = vehicle("veh-1")
        drv = driver("drv-1", trained=False)
        seated = trip("t1", "Z_NORTH", "Z_SOUTH")
        urgent = trip("t2", "Z_EAST", "Z_WEST", assist=True)
        day = problem([veh], [drv], [seated])
        base = solve_greedy(day)
        self.assertIn("t1", base.served_requests)

        _updated, result, _diff = online_insert(day, base, urgent)

        self.assertNotIn("t2", result.served_requests)
        hit = [r for r in result.rejected_requests if r.trip_id == "t2"]
        self.assertEqual(len(hit), 1)
        self.assertTrue(hit[0].reason_code)
        # The refusal names the vehicle it refused on, and the plan stays verified.
        self.assertIn("NO_QUALIFIED_DRIVER", hit[0].detail or "")
        self.assertTrue(result.verified_feasible)
        self.assertIn("t1", result.served_requests)

    def test_trained_seated_driver_still_serves_the_new_trip(self) -> None:
        veh = vehicle("veh-1")
        drv = driver("drv-1", trained=True)
        seated = trip("t1", "Z_NORTH", "Z_SOUTH")
        urgent = trip("t2", "Z_EAST", "Z_WEST", assist=True)
        day = problem([veh], [drv], [seated])
        base = solve_greedy(day)
        self.assertIn("t1", base.served_requests)

        _updated, result, _diff = online_insert(day, base, urgent)

        self.assertIn("t2", result.served_requests)
        self.assertTrue(result.verified_feasible)

    def test_rejection_detail_has_no_dangling_separator(self) -> None:
        veh = vehicle("veh-1")
        drv = driver("drv-1", trained=False)
        seated = trip("t1", "Z_NORTH", "Z_SOUTH")
        urgent = trip("t2", "Z_EAST", "Z_WEST", assist=True)
        day = problem([veh], [drv], [seated])
        base = solve_greedy(day)

        _updated, result, _diff = online_insert(day, base, urgent)

        hit = [r for r in result.rejected_requests if r.trip_id == "t2"]
        detail = hit[0].detail or ""
        self.assertFalse(detail.endswith("; "))
        self.assertFalse(detail.endswith(";"))
