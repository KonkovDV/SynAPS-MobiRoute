"""NEAREST_FEASIBLE must rank deadhead from the route tail, not from the depot."""

from __future__ import annotations

import unittest

from mobiroute.domain.requests import DayProblem, PlanningResult, TravelMatrix
from mobiroute.solvers.nearest import solve_nearest
from tests.factories import driver, problem, trip, vehicle

# NORTH: first pickup, SOUTH: first dropoff (far), EAST: second pickup, WEST: second dropoff.
ZONES = ("Z_DEPOT_1", "Z_DEPOT_2", "Z_NORTH", "Z_SOUTH", "Z_EAST", "Z_WEST")
MINUTES = (
    (0, 30, 5, 65, 5, 15),
    (30, 0, 35, 85, 25, 30),
    (5, 35, 0, 60, 10, 20),
    (65, 85, 60, 0, 65, 75),
    (5, 25, 10, 65, 0, 10),
    (15, 30, 20, 75, 10, 0),
)


def tail_case(*, second_trip: bool = True) -> DayProblem:
    vehicles = [vehicle("v-near", depot="Z_DEPOT_1"), vehicle("v-far", depot="Z_DEPOT_2")]
    drivers = [driver("d-near", depot="Z_DEPOT_1"), driver("d-far", depot="Z_DEPOT_2")]
    trips = [trip("a1", "Z_NORTH", "Z_SOUTH", earliest=60, latest=300, max_wait=120)]
    if second_trip:
        trips.append(trip("b2", "Z_EAST", "Z_WEST", earliest=240, latest=480, max_wait=120))
    day = problem(vehicles, drivers, trips)
    return day.model_copy(update={"travel": TravelMatrix(zones=ZONES, minutes=MINUTES)})


def vehicle_of(result: PlanningResult, trip_id: str) -> str | None:
    for plan in result.route_plans:
        if any(stop.trip_id == trip_id for stop in plan.ordered_stops):
            return plan.vehicle_id
    return None


class NearestTailAnchorTests(unittest.TestCase):
    def test_the_fixture_separates_the_depot_from_the_tail(self) -> None:
        matrix = tail_case().travel
        from_depot = matrix.travel("Z_DEPOT_1", "Z_EAST")
        from_tail = matrix.travel("Z_SOUTH", "Z_EAST")
        rival_depot = matrix.travel("Z_DEPOT_2", "Z_EAST")
        # The depot of v-near looks closest to the second pickup...
        self.assertLess(from_depot, rival_depot)
        # ...but after the first trip v-near actually stands far away.
        self.assertGreater(from_tail, rival_depot)

    def test_second_trip_goes_to_the_vehicle_that_is_really_closer(self) -> None:
        result = solve_nearest(tail_case())
        self.assertEqual(sorted(result.served_requests), ["a1", "b2"])
        self.assertEqual(vehicle_of(result, "a1"), "v-near")
        self.assertEqual(vehicle_of(result, "b2"), "v-far")

    def test_an_empty_vehicle_still_ranks_from_its_depot(self) -> None:
        result = solve_nearest(tail_case(second_trip=False))
        self.assertEqual(result.served_requests, ["a1"])
        self.assertEqual(vehicle_of(result, "a1"), "v-near")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
