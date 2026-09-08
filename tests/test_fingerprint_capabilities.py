"""Changes to operative accessibility capabilities must change input identity."""

import unittest

from mobiroute.adapters.fingerprint import fingerprint_problem
from mobiroute.domain.models import WheelchairType
from mobiroute.domain.requests import DayProblem
from mobiroute.validation.feasibility import check_plan

from .test_quota_evidence import quota_case


class FingerprintCapabilitiesTests(unittest.TestCase):
    def test_wheelchair_type_change_can_invalidate_the_same_route(self):
        problem, result = quota_case(quota=None)
        problem.requests[0].wheelchair_requirement = WheelchairType.MANUAL
        vehicle = problem.vehicles[0]
        vehicle.wheelchair_capacity = 1
        vehicle.compatible_wheelchair_types = [WheelchairType.MANUAL]
        before = fingerprint_problem(problem)
        self.assertTrue(check_plan(problem, result).feasible)
        vehicle.compatible_wheelchair_types = [WheelchairType.POWER]
        self.assertFalse(check_plan(problem, result).feasible)
        self.assertNotEqual(fingerprint_problem(problem), before)

    def test_capability_fingerprint_survives_json_replay(self):
        problem, _ = quota_case(quota=None)
        problem.vehicles[0].compatible_wheelchair_types = [
            WheelchairType.POWER,
            WheelchairType.SCOOTER,
        ]
        replay = DayProblem.model_validate_json(problem.model_dump_json())
        self.assertEqual(fingerprint_problem(problem), fingerprint_problem(replay))

    def test_graph_cache_and_hashing_do_not_change_public_input(self):
        problem, _ = quota_case(quota=None)
        before = problem.model_dump_json()
        initial = fingerprint_problem(problem)
        problem.travel.shortest_path("d", "q")
        self.assertEqual(fingerprint_problem(problem), initial)
        self.assertEqual(problem.model_dump_json(), before)
