"""Real Rust evaluation versus the independent Python detour contract."""

import unittest
from math import inf, nextafter

import mobiroute_native as native

from mobiroute.domain.constraints import detour_limit

TRAVEL = [0, 16, 16, 0]
VEHICLE = [0, 0, 100, 2, 0, 0, 0, 0, 100, 0, 1, 0]


def trip_row(ride):
    # Pickup leaves at 5. Appointment lobby snap forces arrival at 5 + ride.
    return [0, 1, 0, 100, 100, 100, 5, 0, 35 + ride, -1, 1, 0, 0, 0, -1, 0]


class NativeNumericContractTests(unittest.TestCase):
    def assert_native_boundary(self, ratio, ride):
        row = trip_row(ride)
        expected = ride <= detour_limit(16, ratio)
        constructed = native.InsertionEngine(TRAVEL, 2, row, [ratio])
        appended = native.InsertionEngine(TRAVEL, 2, [], [])
        self.assertEqual(appended.append_trip(row, ratio), 0)
        engines = (constructed, appended, constructed.fork())
        for mode, engine in enumerate(engines):
            with self.subTest(ratio=ratio, ride=ride, mode=mode):
                engine.set_fleet([[0, 0]], [[0, 1]], [VEHICLE], [[]])
                evaluated = engine.eval_route(0)
                self.assertEqual(evaluated is not None, expected)
                if evaluated is not None:
                    self.assertEqual(evaluated[2], [(0, ride)])
                inserted = engine.best_insert([], [], 0, VEHICLE, [])
                self.assertEqual(inserted is not None, expected)
        with self.subTest(ratio=ratio, ride=ride, mode="free-function"):
            inserted = native.best_insert(TRAVEL, 2, row, [ratio], [], [], 0, VEHICLE, [])
            self.assertEqual(inserted is not None, expected)

    def test_ties_and_neighbors(self):
        for ratio in (nextafter(1.0625, 0.0), 1.0625, nextafter(1.0625, inf)):
            for ride in (17, 18, 19):
                self.assert_native_boundary(ratio, ride)

    def test_large_finite_ratio(self):
        self.assert_native_boundary(1e300, 18)

    def test_invalid_ratios_fail_before_native_mutation(self):
        row = trip_row(18)
        for ratio in (0.0, -1.0, inf, -inf, float("nan"), 1e308):
            with self.subTest(ratio=ratio, mode="constructor"), self.assertRaises(ValueError):
                native.InsertionEngine(TRAVEL, 2, row, [ratio])
            engine = native.InsertionEngine(TRAVEL, 2, [], [])
            with self.subTest(ratio=ratio, mode="append"), self.assertRaises(ValueError):
                engine.append_trip(row, ratio)
            self.assertEqual(engine.append_trip(row, 3.0), 0)
            self.assertIsNone(native.best_insert(TRAVEL, 2, row, [ratio], [], [], 0, VEHICLE, []))
