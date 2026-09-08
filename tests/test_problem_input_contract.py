"""Malformed data versus valid-but-infeasible planning inputs."""

import unittest

from mobiroute.domain.models import BookingStatus
from mobiroute.domain.requests import DayProblem, Driver, TravelMatrix, TripRequest, Vehicle
from mobiroute.validation.input import validate_problem, validate_trip


def trip():
    return TripRequest(
        id="t",
        pseudonymous_passenger_id="p",
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
        problem_id="input-contract",
        seed=1,
        passengers=[],
        requests=[trip()],
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


class ProblemInputContractTests(unittest.TestCase):
    def test_copy_and_list_mutation_return_canonical_detached_snapshots(self):
        original = problem()
        copied = original.model_copy(
            update={"travel": {"zones": ["d", "p"], "minutes": [[0, 30], [30, 0]]}}
        )
        copied.requests = [trip().model_copy(update={"booking_status": "CONFIRMED"})]
        copied.requests.append(trip().model_dump() | {"id": "second"})
        snapshot = validate_problem(copied)
        self.assertIsInstance(snapshot.travel, TravelMatrix)
        self.assertEqual(snapshot.travel.travel("d", "p"), 30)
        self.assertIs(snapshot.requests[0].booking_status, BookingStatus.CONFIRMED)
        self.assertIsInstance(snapshot.requests[1], TripRequest)
        self.assertIsInstance(copied.requests[1], dict)
        self.assertEqual(original.travel.travel("d", "p"), 16)
        snapshot.requests[0].latest_pickup = 90
        self.assertEqual(copied.requests[0].latest_pickup, 100)

    def test_strict_numeric_constructor_fields(self):
        for value in (True, "1", 1.5):
            for field in ("earliest_pickup", "companion_count"):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    TripRequest.model_validate(trip().model_dump() | {field: value})
        for value in (True, "3", float("inf"), float("nan")):
            with self.subTest(ratio=value), self.assertRaises(ValueError):
                TripRequest.model_validate(trip().model_dump() | {"max_detour_ratio": value})

    def test_copied_malformed_trip_values_are_rejected(self):
        updates = (
            {"earliest_pickup": -1},
            {"earliest_pickup": 101},
            {"boarding_duration": -1},
            {"max_wait_time": True},
            {"max_ride_time": 2**31},
            {"companion_count": 2**31 - 1},
            {"max_detour_ratio": 1e308},
            {"booking_status": "NOT_A_STATUS"},
            {"pickup_coordinates": (91.0, 0.0)},
        )
        for update in updates:
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate_trip(trip().model_copy(update=update))

    def test_duplicate_ids_and_bad_references(self):
        p = problem()
        updates = (
            {"requests": [trip(), trip()]},
            {"vehicles": [p.vehicles[0], p.vehicles[0]]},
            {"drivers": [p.drivers[0], p.drivers[0]]},
            {"vehicles": [p.vehicles[0].model_copy(update={"depot_id": "missing"})]},
            {"vehicles": [p.vehicles[0].model_copy(update={"service_area": ["missing"]})]},
            {"requests": [trip().model_copy(update={"pickup_zone": "missing"})]},
            {"requests": [trip().model_copy(update={"via_zone": "missing"})]},
        )
        for update in updates:
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate_problem(p.model_copy(update=update))

    def test_windows_and_native_intermediate_bounds(self):
        p = problem()
        for update in (
            {"shift_start": 101},
            {"shift_end": 2**31 - 1},
            {"unavailable_intervals": [(20, 10)]},
        ):
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate_problem(
                    p.model_copy(update={"vehicles": [p.vehicles[0].model_copy(update=update)]})
                )
        p.travel = TravelMatrix(
            zones=["d", "via", "p"],
            minutes=[[0, 10**9, 10**9], [10**9, 0, 10**9], [10**9, 10**9, 0]],
        )
        p.requests = [trip().model_copy(update={"via_zone": "via", "via_service_duration": 10**9})]
        with self.assertRaisesRegex(ValueError, "via_direct_minutes"):
            validate_problem(p)

    def test_valid_infeasible_and_empty_inputs_stay_valid(self):
        p = problem()
        p.vehicles[0].unavailable_intervals = [(5, 5)]
        p.vehicles[0].shift_end = 0
        p.requests[0].companion_count = 1000
        p.requests[0].appointment_start = 60
        p.requests[0].appointment_end = 45
        p.requests[0].quota_minutes_remaining = -1
        self.assertEqual(validate_problem(p).requests[0].companion_count, 1000)
        p.vehicles = []
        p.drivers = []
        validate_problem(p)
        p.requests = []
        p.travel = TravelMatrix(zones=[], minutes=[])
        self.assertEqual(validate_problem(p).requests, [])
