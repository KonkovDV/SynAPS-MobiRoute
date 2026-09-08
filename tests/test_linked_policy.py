"""Linked-trip ownership, adjacency and dependency contracts."""

import unittest

from mobiroute.domain.linked_trips import (
    allowed_vehicles,
    dependency_order,
    dependent_ids,
    link_issues,
    prune_linked_stops,
)
from mobiroute.domain.models import StopType
from mobiroute.domain.requests import (
    DayProblem,
    Driver,
    PlanningResult,
    RoutePlan,
    Stop,
    TripRequest,
    Vehicle,
)


def trip(tid, *, same=None, after=None):
    return TripRequest(
        id=tid,
        pseudonymous_passenger_id=f"p-{tid}",
        pickup_zone="z",
        dropoff_zone="z",
        requested_at=0,
        earliest_pickup=0,
        latest_pickup=100,
        max_ride_time=100,
        max_wait_time=100,
        same_vehicle_as=same,
        insert_immediately_after=after,
    )


def stop(tid, kind):
    return Stop(
        id=f"{tid}:{kind.value}",
        trip_id=tid,
        stop_type=kind,
        location="z",
        service_duration=3 if kind == StopType.PICKUP else 2,
        load_delta=1 if kind == StopType.PICKUP else -1 if kind == StopType.DROPOFF else 0,
    )


def core(*ids):
    return [stop(tid, kind) for tid in ids for kind in (StopType.PICKUP, StopType.DROPOFF)]


class LinkedPolicyTests(unittest.TestCase):
    def test_both_parent_fields_are_enforced(self):
        trips = {t.id: t for t in (trip("a"), trip("b"), trip("c", same="a", after="b"))}
        routes = {"v1": core("a"), "v2": core("b", "c")}
        self.assertIn(("c", "LINKED_VEHICLE:c:a"), link_issues(trips, routes))
        self.assertEqual(allowed_vehicles(trips["c"], trips, routes), set())

    def test_missing_parent_is_not_silently_ignored(self):
        child = trip("child", same="missing")
        trips = {child.id: child}
        self.assertIn(
            ("child", "LINK_PARENT_MISSING:child:missing"), link_issues(trips, {"v": core("child")})
        )
        self.assertEqual(link_issues(trips, {}), [])

    def test_via_is_an_intervening_service_stop(self):
        trips = {t.id: t for t in (trip("a"), trip("b", after="a"), trip("other"))}
        routes = {
            "v": [
                stop("other", StopType.PICKUP),
                *core("a"),
                stop("other", StopType.VIA),
                *core("b"),
                stop("other", StopType.DROPOFF),
            ]
        }
        self.assertIn(("b", "IMMEDIATE_AFTER:b:a"), link_issues(trips, routes))
        self.assertEqual(link_issues(trips, {"v": core("a", "b")}), [])

    def test_equality_cycles_are_not_temporal_cycles(self):
        a, b = trip("a", same="b"), trip("b", same="a")
        trips = {t.id: t for t in (a, b)}
        self.assertEqual(link_issues(trips, {"v": core("a", "b")}), [])
        self.assertEqual([t.id for t in dependency_order([a, b])], ["a", "b"])
        self.assertIsNone(allowed_vehicles(a, trips, {}, pending={"b"}))
        self.assertEqual(allowed_vehicles(b, trips, {"v": core("a")}), {"v"})
        self.assertEqual(allowed_vehicles(a, trips, {}), set())
        own = trip("self", same="self")
        self.assertIsNone(allowed_vehicles(own, {own.id: own}, {}))

    def test_immediate_order_wins_over_an_equality_cycle(self):
        a, b = trip("a", same="b"), trip("b", after="a")
        trips = {t.id: t for t in (a, b)}
        self.assertEqual([t.id for t in dependency_order([b, a])], ["a", "b"])
        self.assertEqual(link_issues(trips, {"v": core("a", "b")}), [])
        self.assertEqual(allowed_vehicles(b, trips, {}, pending={"a"}), set())

    def test_pruning_and_cancellation_follow_both_parent_fields(self):
        trips = {
            t.id: t
            for t in (trip("a"), trip("b"), trip("c", same="a", after="b"), trip("d", same="c"))
        }
        self.assertEqual(dependent_ids(trips.values(), {"b"}), {"b", "c", "d"})
        routes = {"v1": core("a"), "v2": core("b", "c", "d")}
        self.assertEqual(prune_linked_stops(trips, routes), {"c", "d"})
        self.assertEqual(link_issues(trips, routes), [])
        self.assertEqual({s.trip_id for s in routes["v1"]}, {"a"})
        self.assertEqual({s.trip_id for s in routes["v2"]}, {"b"})


def assembled(trips, sequences):
    vehicles = [
        Vehicle(
            id=f"v{i}",
            vehicle_type="van",
            passenger_capacity=2,
            depot_id="z",
            shift_start=0,
            shift_end=100,
        )
        for i in range(1, len(sequences) + 1)
    ]
    drivers = [
        Driver(id=f"d{i}", depot_id="z", shift_start=0, shift_end=100)
        for i in range(1, len(sequences) + 1)
    ]
    problem = DayProblem(
        problem_id="linked-notary",
        seed=1,
        passengers=[],
        requests=trips,
        vehicles=vehicles,
        drivers=drivers,
        travel={"zones": ["z"], "minutes": [[0]]},
    )
    plans = []
    for i, ids in enumerate(sequences, 1):
        stops = core(*ids)
        arrivals, departures = {}, {}
        clock = 0
        for s in stops:
            arrivals[s.id] = clock
            clock += 5 if s.stop_type == StopType.PICKUP else 2
            departures[s.id] = clock
        plans.append(
            RoutePlan(
                vehicle_id=f"v{i}",
                driver_id=f"d{i}",
                ordered_stops=stops,
                passenger_assignments=list(ids),
                arrival_times=arrivals,
                departure_times=departures,
            )
        )
    result = PlanningResult(
        status="HEURISTIC_FEASIBLE",
        solution_type="TEST",
        verified_feasible=True,
        served_requests=[tid for ids in sequences for tid in ids],
        rejected_requests=[],
        route_plans=plans,
        input_hash="test",
        config_hash="test",
        mobiroute_version="test",
        synaps_commit="test",
    )
    return problem, result


class LinkedNotaryTests(unittest.TestCase):
    def test_notary_rejects_wrong_vehicle_and_broken_adjacency(self):
        from mobiroute.validation.feasibility import check_plan

        trips = [trip("a"), trip("b", same="a", after="a"), trip("other")]
        problem, result = assembled(trips, [["a", "b", "other"]])
        self.assertTrue(check_plan(problem, result).feasible)
        for sequences, code in (
            ([["a", "other"], ["b"]], "LINKED_VEHICLE:b:a"),
            ([["a", "other", "b"]], "IMMEDIATE_AFTER:b:a"),
        ):
            with self.subTest(code=code):
                problem, result = assembled(trips, sequences)
                report = check_plan(problem, result)
                self.assertFalse(report.feasible)
                self.assertIn(code, report.violations)

    def test_notary_rejects_missing_parent(self):
        from mobiroute.validation.feasibility import check_plan

        problem, result = assembled([trip("child", same="missing")], [["child"]])
        report = check_plan(problem, result)
        self.assertFalse(report.feasible)
        self.assertIn("LINK_PARENT_MISSING:child:missing", report.violations)

    def test_vehicle_subset_cannot_hide_a_broken_route(self):
        from mobiroute.validation.feasibility import check_plan

        problem, result = assembled([trip("a"), trip("b")], [["a"], ["b"]])
        self.assertTrue(check_plan(problem, result).feasible)
        route = result.route_plans[1]
        route.departure_times["b:DROPOFF"] = route.arrival_times["b:DROPOFF"] - 1
        report = check_plan(problem, result, only_vehicles={"v1"})
        self.assertFalse(report.feasible)
        self.assertIn("DEPARTURE_BEFORE_ARRIVAL:b:DROPOFF", report.violations)
