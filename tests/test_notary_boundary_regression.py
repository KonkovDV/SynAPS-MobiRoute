"""Independent notary guards, including legacy routes without depot stops."""

import pytest

from mobiroute.domain.models import StopType
from mobiroute.domain.requests import RoutePlan, Stop, TravelMatrix
from mobiroute.validation.feasibility import check_route
from tests.factories import driver, problem, trip, vehicle


def _case():
    request = trip("t", "P", "Q", earliest=10, latest=40, via="V")
    p = problem([vehicle("v", depot="D")], [driver("d", depot="D")], [request])
    positions = [0, 10, 15, 20]
    p.travel = TravelMatrix(
        zones=["D", "P", "V", "Q"],
        minutes=[[abs(a - b) for b in positions] for a in positions],
    )
    r = RoutePlan(
        vehicle_id="v",
        driver_id="d",
        ordered_stops=[
            Stop(id=sid, trip_id="t", stop_type=kind, location=zone)
            for sid, kind, zone in [
                ("pu", StopType.PICKUP, "P"),
                ("via", StopType.VIA, "V"),
                ("do", StopType.DROPOFF, "Q"),
            ]
        ],
        passenger_assignments=["t"],
        arrival_times={"pu": 10, "via": 20, "do": 27},
        departure_times={"pu": 15, "via": 22, "do": 29},
    )
    return p, r


def _issues(p, r):
    return check_route(p, r, {t.id: t for t in p.requests})


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda p, r: r.ordered_stops.clear(), "ASSIGNMENT_STOP_MISMATCH"),
        (lambda p, r: r.passenger_assignments.clear(), "ASSIGNMENT_STOP_MISMATCH"),
        (lambda p, r: setattr(r, "driver_id", None), "NO_DRIVER"),
        (lambda p, r: r.departure_times.update(do=26), "DEPARTURE_BEFORE_ARRIVAL"),
        (lambda p, r: setattr(r.ordered_stops[0], "location", "D"), "PICKUP_LOCATION"),
        (lambda p, r: setattr(r.ordered_stops[2], "location", "V"), "DROPOFF_LOCATION"),
        (lambda p, r: setattr(p.requests[0], "earliest_pickup", 11), "EARLY_PICKUP"),
        (lambda p, r: r.departure_times.update(pu=14), "CURB_WAIT"),
        (lambda p, r: r.departure_times.update(do=28), "ALIGHTING_SERVICE"),
        (lambda p, r: r.departure_times.update(via=21), "VIA_SERVICE"),
        (lambda p, r: r.ordered_stops.insert(1, r.ordered_stops[0]), "DUPLICATE_PICKUP"),
        (lambda p, r: r.ordered_stops.append(r.ordered_stops[-1]), "DUPLICATE_DROPOFF"),
    ],
)
def test_notary_rejects_broken_service_contract(mutate, code):
    p, r = _case()
    assert _issues(p, r) == []
    mutate(p, r)
    assert any(v.startswith(f"{code}:") for v in _issues(p, r))


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize(
    "owner,code", [("driver", "DRIVER_REST"), ("vehicle", "VEHICLE_UNAVAILABLE")]
)
@pytest.mark.parametrize("interval,blocked", [((35, 40), True), ((49, 55), False)])
def test_depot_return_unavailability(explicit, owner, code, interval, blocked):
    p, r = _case()
    if explicit:
        r.ordered_stops.append(
            Stop(id="end", trip_id=None, stop_type=StopType.DEPOT_END, location="D")
        )
        r.arrival_times["end"] = r.departure_times["end"] = 49
    assert _issues(p, r) == []
    resource = p.drivers[0] if owner == "driver" else p.vehicles[0]
    resource.unavailable_intervals = [interval]
    issues = _issues(p, r)
    assert any(v.startswith(f"{code}:") for v in issues) is blocked
    if not blocked:
        assert issues == []


def test_empty_vehicle_needs_no_driver():
    p, r = _case()
    r.ordered_stops.clear()
    r.passenger_assignments.clear()
    r.arrival_times.clear()
    r.departure_times.clear()
    r.driver_id = None
    assert _issues(p, r) == []
