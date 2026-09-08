"""Native worlds belong to a solve, not to reusable plan/event identifiers."""

import gc
import unittest
import weakref

from mobiroute.dispatch.online_insertion import online_insert
from mobiroute.domain.requests import DayProblem, Driver, TravelMatrix, TripRequest, Vehicle
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.solvers.insertion_kernel import ProblemKernel
from mobiroute.solvers.native_accel import attach_native, kernel_for, stash_kernel


def trip(tid):
    return TripRequest(
        id=tid,
        pseudonymous_passenger_id=f"p-{tid}",
        pickup_zone="d",
        dropoff_zone="p",
        requested_at=0,
        earliest_pickup=0,
        latest_pickup=100,
        max_ride_time=100,
        max_wait_time=100,
    )


def problem():
    return DayProblem(
        problem_id="cache-contract",
        seed=1,
        passengers=[],
        requests=[trip("base")],
        vehicles=[
            Vehicle(
                id="v",
                vehicle_type="van",
                passenger_capacity=2,
                depot_id="d",
                shift_start=0,
                shift_end=100,
            )
        ],
        drivers=[Driver(id="driver", depot_id="d", shift_start=0, shift_end=100)],
        travel=TravelMatrix(zones=["d", "p"], minutes=[[0, 16], [16, 0]]),
    )


class WatchedKernel(ProblemKernel):
    """Add weak-reference support without changing the kernel's tables."""


class NativeCacheContractTests(unittest.TestCase):
    def test_plan_and_event_ids_neither_retrieve_nor_retain_kernels(self):
        p = problem()
        baseline = solve_greedy(p)
        kernel = attach_native(WatchedKernel.from_problem(p))
        retained = weakref.ref(kernel)
        for event_id in ("", "reused-event"):
            result = baseline.model_copy(update={"event_id": event_id})
            stash_kernel(result, kernel)
            self.assertIsNone(kernel_for(result))
        del kernel
        gc.collect()
        self.assertIsNone(retained())

    def test_current_matrix_is_used_despite_unchanged_baseline_ids(self):
        p = problem()
        baseline = solve_greedy(p)
        p.travel = TravelMatrix(zones=["d", "p"], minutes=[[0, 30], [30, 0]])
        _updated, result, _diff = online_insert(p, baseline, trip("new"), protect_frozen=False)
        self.assertTrue(result.verified_feasible)
        self.assertEqual(set(result.served_requests), {"base", "new"})
        for route in result.route_plans:
            for minutes in route.ride_times.values():
                self.assertGreaterEqual(minutes, 30)

    def test_current_capacity_is_used_despite_unchanged_baseline_ids(self):
        p = problem()
        baseline = solve_greedy(p)
        p.vehicles[0].passenger_capacity = 1
        _updated, result, _diff = online_insert(p, baseline, trip("new"), protect_frozen=False)
        self.assertTrue(result.verified_feasible)
        self.assertEqual(set(result.served_requests), {"base", "new"})
        for route in result.route_plans:
            self.assertLessEqual(max(route.passenger_load_after_stop.values()), 1)
