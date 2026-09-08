"""Immutable travel snapshots: copies must never inherit stale graph caches."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from pydantic import ValidationError

from mobiroute.domain.requests import TravelMatrix
from mobiroute.domain.travel_graph import INF, floyd_warshall


class MatrixContractTests(unittest.TestCase):
    def test_copy_rebuilds_cached_travel(self):
        matrix = TravelMatrix(zones=["A", "B"], minutes=[[0, 5], [5, 0]])
        self.assertEqual(matrix.travel("A", "B"), 5)
        for deep in (False, True):
            with self.subTest(deep=deep):
                copied = matrix.model_copy(update={"minutes": [[0, 30], [30, 0]]}, deep=deep)
                self.assertEqual(copied.travel("A", "B"), 30)
                self.assertEqual(matrix.travel("A", "B"), 5)

    def test_copy_rebuilds_shortest_path(self):
        matrix = TravelMatrix(
            zones=["A", "B", "C"], minutes=[[0, 3, 20], [3, 0, 3], [20, 3, 0]]
        )
        self.assertEqual(matrix.shortest_path("A", "C"), ["A", "B", "C"])
        copied = matrix.model_copy(update={"minutes": [[0, 30, 10], [30, 0, 30], [10, 30, 0]]})
        self.assertEqual(copied.shortest_path("A", "C"), ["A", "C"])
        self.assertEqual(copied.travel("A", "C"), 10)
        self.assertEqual(matrix.travel("A", "C"), 6)

    def test_input_lists_are_detached(self):
        zones = ["A", "B"]
        minutes = [[0, 5], [5, 0]]
        matrix = TravelMatrix(zones=zones, minutes=minutes)
        zones[1] = "C"
        minutes[0][1] = 30
        self.assertEqual(matrix.travel("A", "B"), 5)

    def test_snapshot_cannot_be_mutated(self):
        matrix = TravelMatrix(zones=["A", "B"], minutes=[[0, 5], [5, 0]])
        with self.assertRaises(TypeError):
            matrix.minutes[0][1] = 30
        with self.assertRaises(TypeError):
            matrix.zones[1] = "C"
        with self.assertRaises(ValidationError):
            matrix.minutes = ((0, 30), (30, 0))

    def test_invalid_shapes_and_values_are_rejected(self):
        cases = [
            (["A", "B"], [[0]]),
            (["A"], [[0, 1]]),
            (["A", "A"], [[0, 1], [1, 0]]),
            ([""], [[0]]),
            (["A"], [[1]]),
            (["A", "B"], [[0, -1], [1, 0]]),
            (["A", "B"], [[0, True], [1, 0]]),
            (["A", "B"], [[0, 1.5], [1, 0]]),
            (["A", "B"], [[0, "5"], [1, 0]]),
            (["A", "B"], [[0, float("inf")], [1, 0]]),
            (["A", "B"], [[0, INF + 1], [1, 0]]),
        ]
        for zones, minutes in cases:
            with self.subTest(zones=zones, minutes=minutes):
                with self.assertRaises(ValidationError):
                    TravelMatrix(zones=zones, minutes=minutes)

    def test_invalid_copy_is_rejected(self):
        matrix = TravelMatrix(zones=["A", "B"], minutes=[[0, 5], [5, 0]])
        with self.assertRaises(ValidationError):
            matrix.model_copy(update={"minutes": [[0]]})
        with self.assertRaises(ValidationError):
            matrix.model_copy(update={"zones": ["A", "A"]})

    def test_empty_and_unreachable_graphs_are_valid(self):
        empty = TravelMatrix(zones=[], minutes=[])
        self.assertEqual(empty.model_dump(mode="json"), {"zones": [], "minutes": []})
        matrix = TravelMatrix(zones=["A", "B"], minutes=[[0, INF], [INF, 0]])
        self.assertEqual(matrix.travel("A", "B"), INF)
        self.assertEqual(matrix.shortest_path("A", "B"), [])

    def test_graph_is_built_once_per_snapshot(self):
        matrix = TravelMatrix(zones=["A", "B"], minutes=[[0, 5], [5, 0]])
        with patch("mobiroute.domain.requests.floyd_warshall", wraps=floyd_warshall) as build:
            for _ in range(10):
                matrix.travel("A", "B")
                matrix.shortest_path("A", "B")
            self.assertEqual(build.call_count, 1)

    def test_json_round_trip_preserves_snapshot(self):
        matrix = TravelMatrix(zones=["A", "B"], minutes=[[0, 5], [5, 0]])
        restored = TravelMatrix.model_validate_json(matrix.model_dump_json())
        self.assertEqual(restored.travel("A", "B"), 5)
        self.assertEqual(restored.model_dump(mode="json"), matrix.model_dump(mode="json"))
