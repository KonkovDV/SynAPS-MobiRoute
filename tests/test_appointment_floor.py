"""Time-window tightening: an appointment trip may wait for its pickup floor.

Before 0.2.8 every simulator scheduled pickups as early as possible and never
delayed one to respect a later appointment, so a passenger ready long before
the appointment was rejected even alone in an empty fleet (Cordeau a2-16: 7 of
16 requests). The floor ``alight - min(max_ride, detour cap) - curb`` is implied
by the hard constraints; search, oracle and notary must agree on it.
"""

from __future__ import annotations

import pytest

from mobiroute.adapters.cordeau import load_cordeau_a2_16
from mobiroute.domain.constraints import (
    detour_limit,
    earliest_alight_time,
    pickup_service_floor,
    pickup_service_minutes,
)
from mobiroute.domain.route_graph import service_stops
from mobiroute.solvers.greedy import _pair_stops, simulate_stop_sequence, solve_greedy
from mobiroute.solvers.insertion_kernel import ProblemKernel, best_insert_python
from mobiroute.solvers.native_accel import attach_native, best_insert, native_available
from mobiroute.validation.feasibility import check_plan, trip_pickup_floor
from tests.factories import driver, problem, trip, vehicle

APPT = 300


def _appointment_problem(*, max_wait: int = 600, max_ride: int = 30):
    late = trip(
        "appt",
        "Z_NORTH",
        "Z_HOSP_A",
        earliest=0,
        latest=600,
        max_ride=max_ride,
        max_wait=max_wait,
        appt_start=APPT,
        appt_end=APPT + 20,
    )
    return problem([vehicle("v1")], [driver("d1")], [late])


def test_floor_formula_is_the_tightened_window() -> None:
    assert pickup_service_floor(10, None, 30, 3) == 10
    # alight 270, ride cap 30, curb max(3, 5) = 5
    assert pickup_service_floor(0, APPT, 30, 3) == 235
    # a detour cap tighter than max ride tightens the floor further
    assert pickup_service_floor(0, APPT, 30, 3, detour_cap=12) == 253
    # the floor never undercuts the passenger's own earliest pickup
    assert pickup_service_floor(260, APPT, 30, 3) == 260
    # a negative or missing cap means "no detour cap"
    assert pickup_service_floor(0, APPT, 30, 3, detour_cap=-1) == 235


def test_single_appointment_trip_waits_for_its_floor_and_is_served() -> None:
    p = _appointment_problem()
    late = p.requests[0]
    res = solve_greedy(p)

    assert res.served_requests == ["appt"]
    assert res.verified_feasible, check_plan(p, res).violations
    route = res.route_plans[0]
    it = route.passenger_itineraries[0]
    floor = trip_pickup_floor(p, late)
    direct = p.travel.travel(late.pickup_zone, late.dropoff_zone)
    expected = pickup_service_floor(
        0, APPT, late.max_ride_time, late.boarding_duration, detour_limit(direct, 3.0)
    )
    assert floor == expected
    assert it.pickup_time == floor
    # Delay is measured from the ready time the passenger asked for.
    assert route.waiting_times["appt"] == floor - late.earliest_pickup
    assert it.ride_time <= late.max_ride_time
    assert it.dropoff_time >= earliest_alight_time(APPT)


def test_floor_beyond_max_wait_is_still_refused() -> None:
    # Ready at 0 but may wait at most 60 minutes: no pickup time satisfies both.
    p = _appointment_problem(max_wait=60)
    res = solve_greedy(p)
    assert res.served_requests == []
    assert res.verified_feasible


def test_oracle_native_and_pydantic_agree_on_the_floor() -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    p = _appointment_problem()
    late = p.requests[0]
    k = ProblemKernel.from_problem(p)
    vk = k.vehicles["v1"]
    dk = k.drivers["d1"]
    idx = k.id_to_idx["appt"]
    oracle = best_insert_python(k, vk, dk, [], [], idx)
    native = best_insert(attach_native(ProblemKernel.from_problem(p)), vk, dk, [], [], idx)
    assert oracle is not None
    assert native == oracle

    pu, do = _pair_stops(late)
    plan = simulate_stop_sequence(p, p.vehicles[0], "d1", [pu, do], {"appt": late})
    assert plan is not None
    assert plan.route_duration == oracle[3]
    assert sum(plan.waiting_times.values()) == oracle[4]


def test_notary_holds_the_line_on_both_sides_of_the_floor() -> None:
    p = _appointment_problem()
    res = solve_greedy(p)
    route = res.route_plans[0]
    core = service_stops(list(route.ordered_stops))
    pick, drop = core[0], core[1]

    late = {**route.arrival_times, pick.id: route.arrival_times[pick.id] + 1}
    moved = {pick.id, drop.id}
    late_dep = {k: v + (1 if k in moved else 0) for k, v in route.departure_times.items()}
    late_arr = {**late, drop.id: route.arrival_times[drop.id] + 1}
    delayed = route.model_copy(update={"arrival_times": late_arr, "departure_times": late_dep})
    report = check_plan(p, res.model_copy(update={"route_plans": [delayed]}))
    assert "UNEXPLAINED_WAIT:appt" in report.violations

    curb = pickup_service_minutes(p.requests[0].boarding_duration)
    early_arr = {**route.arrival_times, pick.id: route.arrival_times[pick.id] - 1}
    early_dep = {**route.departure_times, pick.id: route.arrival_times[pick.id] - 1 + curb}
    early = route.model_copy(update={"arrival_times": early_arr, "departure_times": early_dep})
    report = check_plan(p, res.model_copy(update={"route_plans": [early]}))
    assert not report.feasible
    assert any(v.startswith(("MAX_RIDE_TIME:appt", "DETOUR:appt")) for v in report.violations)


def test_every_a2_16_request_alone_is_served() -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    p = load_cordeau_a2_16()
    refused = []
    for request in p.requests:
        alone = p.model_copy(
            update={
                "requests": [request],
                "passengers": [
                    x
                    for x in p.passengers
                    if x.pseudonymous_id == request.pseudonymous_passenger_id
                ],
            }
        )
        if solve_greedy(alone).served_requests != [request.id]:
            refused.append(request.id)
    assert refused == []


@pytest.mark.parametrize("lane", ["greedy", "beam", "alns", "rhc", "cpsat"])
def test_a2_16_kernel_lanes_serve_every_request(lane: str) -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    from mobiroute.solvers.alns import solve_alns
    from mobiroute.solvers.beam import solve_beam
    from mobiroute.solvers.cpsat import solve_cpsat
    from mobiroute.solvers.rolling_horizon import solve_rolling_horizon

    solvers = {
        "greedy": solve_greedy,
        "beam": solve_beam,
        "alns": solve_alns,
        "rhc": solve_rolling_horizon,
        "cpsat": solve_cpsat,
    }
    p = load_cordeau_a2_16()
    res = solvers[lane](p)
    assert check_plan(p, res).feasible
    assert res.verified_feasible
    assert sorted(res.served_requests) == sorted(t.id for t in p.requests)
    # Max-served optimum with every request served; never a routing-cost claim.
    assert res.status == ("OPTIMAL" if lane == "cpsat" else "HEURISTIC_FEASIBLE")
