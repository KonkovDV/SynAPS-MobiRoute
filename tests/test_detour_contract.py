"""Integer detour arithmetic at ties and native representation boundaries."""

import unittest
from math import inf, nextafter

from mobiroute.domain.constraints import MAX_NATIVE_MINUTES, detour_limit


class DetourContractTests(unittest.TestCase):
    def test_ties_round_to_even(self):
        self.assertEqual(detour_limit(16, 1.0625), 17)
        self.assertEqual(detour_limit(16, nextafter(1.0625, 0.0)), 17)
        self.assertEqual(detour_limit(16, nextafter(1.0625, inf)), 18)

    def test_large_finite_ratios_saturate_without_overflow(self):
        self.assertEqual(detour_limit(16, 1e300), MAX_NATIVE_MINUTES)
        self.assertEqual(detour_limit(MAX_NATIVE_MINUTES, 1.0), MAX_NATIVE_MINUTES)

    def test_invalid_ratios_are_rejected(self):
        for ratio in (0.0, -1.0, inf, -inf, float("nan"), 1e308):
            with self.subTest(ratio=ratio), self.assertRaises(ValueError):
                detour_limit(16, ratio)

    def test_invalid_direct_minutes_are_rejected(self):
        for direct in (-1, True, 1.5, "16"):
            with self.subTest(direct=direct), self.assertRaises(ValueError):
                detour_limit(direct, 1.0)

    def test_zero_distance_and_tiny_positive_ratio(self):
        self.assertEqual(detour_limit(0, 1e300), 1)
        self.assertEqual(detour_limit(16, 1e-300), 1)

    def test_ordinary_caps_are_unchanged(self):
        for direct in (1, 16, 60, 1000):
            for ratio in (0.5, 1.0, 1.25, 3.0):
                with self.subTest(direct=direct, ratio=ratio):
                    self.assertEqual(detour_limit(direct, ratio), direct * ratio // 1 + 1)
