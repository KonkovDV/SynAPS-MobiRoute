"""Operator policy is versioned separately from solver search capability."""

import unittest

from mobiroute.adapters.fingerprint import fingerprint_problem
from mobiroute.dispatch.online_insertion import online_insert, recover_disruption
from mobiroute.domain.models import StopType
from mobiroute.domain.policy import (
    ChainMode,
    DispatchAuthority,
    OperatorPolicy,
    PoolingMode,
    QuotaDebitBasis,
)
from mobiroute.domain.requests import (
    DayProblem,
    Driver,
    PlanningResult,
    RoutePlan,
    Stop,
    TravelMatrix,
    TripRequest,
    Vehicle,
)
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.solvers.native_accel import acceleration_status
from mobiroute.validation.feasibility import (
    billable_service_minutes,
    check_plan,
    time_accounting_totals,
    used_quota_minutes,
)
from mobiroute.validation.input import validate_problem

from .test_native_cache_contract import problem, trip
from .test_quota_evidence import quota_case


def pooled_pair():
    requests = [
        TripRequest(
            id="a",
            pseudonymous_passenger_id="pa",
            pickup_zone="d",
            dropoff_zone="q",
            requested_at=0,
            earliest_pickup=0,
            latest_pickup=60,
            max_ride_time=80,
            max_wait_time=60,
            pooling_opt_in=False,
            fulfillment_group_id="pair",
        ),
        TripRequest(
            id="b",
            pseudonymous_passenger_id="pb",
            pickup_zone="d",
            dropoff_zone="q",
            requested_at=0,
            earliest_pickup=0,
            latest_pickup=60,
            max_ride_time=80,
            max_wait_time=60,
            pooling_opt_in=False,
            fulfillment_group_id="pair",
        ),
    ]
    problem = DayProblem(
        problem_id="policy-pool",
        seed=1,
        passengers=[],
        requests=requests,
        vehicles=[
            Vehicle(
                id="v",
                vehicle_type="van",
                passenger_capacity=4,
                depot_id="d",
                shift_start=0,
                shift_end=180,
            )
        ],
        drivers=[Driver(id="d1", depot_id="d", shift_start=0, shift_end=180)],
        travel=TravelMatrix(zones=["d", "q"], minutes=[[0, 10], [10, 0]]),
        operator_policy=OperatorPolicy(pooling_mode=PoolingMode.ALLOWED),
    )
    route = RoutePlan(
        vehicle_id="v",
        driver_id="d1",
        ordered_stops=[
            Stop(id="a:PU", trip_id="a", stop_type=StopType.PICKUP, location="d"),
            Stop(id="b:PU", trip_id="b", stop_type=StopType.PICKUP, location="d"),
            Stop(id="a:DO", trip_id="a", stop_type=StopType.DROPOFF, location="q"),
            Stop(id="b:DO", trip_id="b", stop_type=StopType.DROPOFF, location="q"),
        ],
        passenger_assignments=["a", "b"],
        arrival_times={"a:PU": 0, "b:PU": 5, "a:DO": 20, "b:DO": 22},
        departure_times={"a:PU": 5, "b:PU": 10, "a:DO": 22, "b:DO": 24},
        ride_times={"a": 15, "b": 12},
    )
    result = PlanningResult(
        status="NOT_VERIFIED",
        solution_type="TEST",
        verified_feasible=False,
        served_requests=["a", "b"],
        rejected_requests=[],
        route_plans=[route],
        input_hash="in",
        config_hash="cfg",
        mobiroute_version="test",
        synaps_commit="test",
    )
    return problem, result


class OperatorPolicyTests(unittest.TestCase):
    def test_laboratory_default_is_explicit_and_unapproved(self):
        problem, _result = quota_case(quota=None)
        policy = problem.operator_policy
        self.assertEqual(policy.provenance, "laboratory:implicit_default")
        self.assertIsNone(policy.approved_by)
        self.assertEqual(policy.dispatch_authority, DispatchAuthority.NONE)
        self.assertEqual(policy.pooling_mode, PoolingMode.ALLOWED)

    def test_policy_and_opt_in_change_input_identity(self):
        problem, _result = quota_case(quota=None)
        before = fingerprint_problem(problem)
        problem.operator_policy = OperatorPolicy(pooling_mode=PoolingMode.FORBIDDEN)
        self.assertNotEqual(fingerprint_problem(problem), before)
        replay = DayProblem.model_validate_json(problem.model_dump_json())
        self.assertEqual(fingerprint_problem(problem), fingerprint_problem(replay))
        problem.requests[0].pooling_opt_in = True
        self.assertNotEqual(fingerprint_problem(problem), fingerprint_problem(replay))

    def test_blank_provenance_is_rejected(self):
        problem, _result = quota_case(quota=None)
        problem.operator_policy = OperatorPolicy(provenance="  ")
        with self.assertRaisesRegex(ValueError, "EMPTY_POLICY_PROVENANCE"):
            validate_problem(problem)

    def test_forbidden_pooling_rejects_shared_onboard_service(self):
        problem, result = pooled_pair()
        self.assertTrue(check_plan(problem, result).feasible)
        problem.operator_policy = OperatorPolicy(pooling_mode=PoolingMode.FORBIDDEN)
        report = check_plan(problem, result)
        self.assertFalse(report.feasible)
        self.assertTrue(any(v.startswith("POOLING_FORBIDDEN:") for v in report.violations))

    def test_opt_in_requires_every_shared_passenger(self):
        problem, result = pooled_pair()
        problem.operator_policy = OperatorPolicy(pooling_mode=PoolingMode.OPT_IN)
        self.assertTrue(
            any(
                v.startswith("POOLING_NOT_OPTED_IN:")
                for v in check_plan(problem, result).violations
            )
        )
        problem.requests[0].pooling_opt_in = True
        problem.requests[1].pooling_opt_in = True
        self.assertTrue(check_plan(problem, result).feasible)

    def test_ride_quota_and_billable_are_distinct(self):
        problem, result = quota_case()
        ride = 20
        billable = billable_service_minutes(problem.requests[0], ride)
        self.assertGreater(billable, ride)
        self.assertEqual(used_quota_minutes(problem, result), {"p": ride})
        totals = time_accounting_totals(problem, result)
        self.assertEqual(totals["ride_duration"], float(ride))
        self.assertEqual(totals["quota_debit"], float(ride))
        self.assertEqual(totals["billable_service"], float(billable))
        problem.operator_policy = OperatorPolicy(quota_debit_basis=QuotaDebitBasis.BILLABLE_SERVICE)
        self.assertEqual(used_quota_minutes(problem, result), {"p": billable})
        self.assertIn("QUOTA:p", check_plan(problem, result).violations)

    def test_mandatory_group_is_not_a_directional_link(self):
        from mobiroute.domain.requests import RejectedTrip

        problem, result = pooled_pair()
        problem.operator_policy = OperatorPolicy(chain_mode=ChainMode.MANDATORY)
        self.assertTrue(check_plan(problem, result).feasible)
        route = result.route_plans[0]
        route.passenger_assignments = ["a"]
        route.ordered_stops = [stop for stop in route.ordered_stops if stop.trip_id == "a"]
        route.ride_times = {"a": 15}
        result.served_requests = ["a"]
        result.rejected_requests = [RejectedTrip(trip_id="b", reason_code="TIME_WINDOW_CONFLICT")]
        result.reason_codes = {"b": "TIME_WINDOW_CONFLICT"}
        report = check_plan(problem, result)
        self.assertIn("CHAIN_PARTIAL:pair", report.violations)
        self.assertFalse(any("LINK" in item for item in report.violations))

    def test_shadow_dispatch_never_authorizes_operations(self):
        if not acceleration_status().get("native_available"):
            self.skipTest("mobiroute_native not built")
        p = problem()
        baseline = solve_greedy(p)
        _updated, result, _diff = online_insert(
            p, baseline, trip("new"), protect_frozen=False, dispatch_mode="SHADOW"
        )
        self.assertEqual(result.solver_config["dispatch_mode"], "SHADOW")
        self.assertFalse(result.solver_config["operational_authorization"])
        _u2, recovered, _d2 = recover_disruption(
            p, baseline, cancel_trip_id="base", dispatch_mode="SHADOW"
        )
        self.assertEqual(recovered.solver_config["dispatch_mode"], "SHADOW")
        self.assertFalse(recovered.solver_config["operational_authorization"])

    def test_every_solver_executes_a_forbidden_pooling_profile(self):
        if not acceleration_status().get("native_available"):
            self.skipTest("mobiroute_native not built")
        from mobiroute.solvers.alns import solve_alns
        from mobiroute.solvers.beam import solve_beam
        from mobiroute.solvers.cpsat import solve_cpsat
        from mobiroute.solvers.greedy import solve_fifo
        from mobiroute.solvers.nearest import solve_nearest
        from mobiroute.solvers.rolling_horizon import solve_rolling_horizon

        p = problem()
        p.operator_policy = OperatorPolicy(
            pooling_mode=PoolingMode.FORBIDDEN,
            chain_mode=ChainMode.MANDATORY,
            provenance="laboratory:forbidden-pooling-fixture",
        )
        p.requests[0].fulfillment_group_id = "solo"
        solvers = (
            solve_fifo,
            solve_greedy,
            solve_nearest,
            solve_beam,
            solve_alns,
            solve_rolling_horizon,
            solve_cpsat,
        )
        for solve in solvers:
            with self.subTest(solver=solve.__name__):
                result = solve(p)
                self.assertTrue(result.verified_feasible, result.objective_values)
                self.assertEqual(result.served_requests, ["base"])
                for route in result.route_plans:
                    self.assertLessEqual(len(route.passenger_assignments), 1)
