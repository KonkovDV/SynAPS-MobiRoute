"""SoA insertion kernel: Python always-on fast path (SynAPS-style AoS→SoA).

The Pydantic object graph is not used in the O(m²) insertion loop.
Optional Rust (`mobiroute_native.best_insert`) may replace scoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict

from mobiroute.domain.constraints import (
    CURB_WAIT_MINUTES,
    EARLY_DROPOFF_SLACK,
    detour_limit,
    occupancy_overlaps,
    push_past_unavail,
)
from mobiroute.domain.models import StopType, WheelchairType
from mobiroute.domain.requests import DayProblem, Stop, TripRequest, Vehicle
from mobiroute.domain.route_graph import service_stops
from mobiroute.validation.feasibility import default_wheelchair_types

FLAG_LIFT = 1
FLAG_RAMP = 2
FLAG_ASSIST = 4
FLAG_STRETCHER = 8
WT_NONE = 0
WT_MANUAL = 1
WT_POWER = 2
WT_SCOOTER = 3
WT_STRETCHER = 4
TRIP_STRIDE = 16


class NativePack(TypedDict):
    travel: list[int]
    n_zones: int
    trip_table: list[int]
    detour: list[float]
    stop_trip: list[int]
    stop_kind: list[int]
    new_idx: int
    veh: list[int]
    unavail: list[int]


def _wt_code(wt: WheelchairType) -> int:
    return {
        WheelchairType.NONE: WT_NONE,
        WheelchairType.MANUAL: WT_MANUAL,
        WheelchairType.POWER: WT_POWER,
        WheelchairType.SCOOTER: WT_SCOOTER,
        WheelchairType.STRETCHER: WT_STRETCHER,
    }[wt]


def _wt_mask(vehicle: Vehicle) -> int:
    allowed = default_wheelchair_types(vehicle)
    mask = 0
    for wt in allowed:
        mask |= 1 << _wt_code(wt)
    return mask


@dataclass(slots=True)
class VehicleKernel:
    depot: int
    shift_start: int
    shift_end: int
    cap_p: int
    cap_w: int
    flags: int
    wmask: int
    unavail: tuple[tuple[int, int], ...]
    area: tuple[int, ...]


@dataclass(slots=True)
class DriverKernel:
    shift_start: int
    shift_end: int
    assist: bool


@dataclass(slots=True)
class ProblemKernel:
    n_zones: int
    travel: tuple[int, ...]
    trip_ids: tuple[str, ...]
    id_to_idx: dict[str, int]
    pu: tuple[int, ...]
    do: tuple[int, ...]
    earliest: tuple[int, ...]
    latest: tuple[int, ...]
    max_wait: tuple[int, ...]
    max_ride: tuple[int, ...]
    board: tuple[int, ...]
    alight: tuple[int, ...]
    appt_s: tuple[int, ...]
    appt_e: tuple[int, ...]
    seats: tuple[int, ...]
    wunits: tuple[int, ...]
    flags: tuple[int, ...]
    wt: tuple[int, ...]
    via: tuple[int, ...]
    via_svc: tuple[int, ...]
    detour: tuple[float, ...]
    vehicles: dict[str, VehicleKernel]
    drivers: dict[str, DriverKernel]
    native_engine: object | None = None
    _pickup_dep_buf: list[int] = field(default_factory=list, repr=False)

    @classmethod
    def from_problem(cls, problem: DayProblem) -> ProblemKernel:
        zmap = {z: i for i, z in enumerate(problem.travel.zones)}
        n = len(problem.travel.zones)
        travel: list[int] = []
        for a in problem.travel.zones:
            for b in problem.travel.zones:
                travel.append(int(problem.travel.travel(a, b)))
        ids: list[str] = []
        id_to_idx: dict[str, int] = {}
        pu: list[int] = []
        do: list[int] = []
        earliest: list[int] = []
        latest: list[int] = []
        max_wait: list[int] = []
        max_ride: list[int] = []
        board: list[int] = []
        alight: list[int] = []
        appt_s: list[int] = []
        appt_e: list[int] = []
        seats: list[int] = []
        wunits: list[int] = []
        flags: list[int] = []
        wt: list[int] = []
        via: list[int] = []
        via_svc: list[int] = []
        detour: list[float] = []
        for t in problem.requests:
            idx = len(ids)
            ids.append(t.id)
            id_to_idx[t.id] = idx
            pu.append(zmap.get(t.pickup_zone, -1))
            do.append(zmap.get(t.dropoff_zone, -1))
            earliest.append(t.earliest_pickup)
            latest.append(t.latest_pickup)
            max_wait.append(t.max_wait_time)
            max_ride.append(t.max_ride_time)
            board.append(t.boarding_duration)
            alight.append(t.alighting_duration)
            appt_s.append(-1 if t.appointment_start is None else t.appointment_start)
            appt_e.append(-1 if t.appointment_end is None else t.appointment_end)
            seats.append(1 + t.companion_count)
            wunits.append(0 if t.wheelchair_requirement == WheelchairType.NONE else 1)
            fl = 0
            if t.needs_lift:
                fl |= FLAG_LIFT
            if t.needs_ramp:
                fl |= FLAG_RAMP
            if t.needs_boarding_assistance:
                fl |= FLAG_ASSIST
            if t.wheelchair_requirement == WheelchairType.STRETCHER:
                fl |= FLAG_STRETCHER
            flags.append(fl)
            wt.append(_wt_code(t.wheelchair_requirement))
            via.append(zmap[t.via_zone] if t.via_zone and t.via_zone in zmap else -1)
            via_svc.append(t.via_service_duration)
            detour.append(float(t.max_detour_ratio))
        vehicles: dict[str, VehicleKernel] = {}
        for v in problem.vehicles:
            vf = 0
            if v.lift_available:
                vf |= FLAG_LIFT
            if v.ramp_available:
                vf |= FLAG_RAMP
            if v.depot_id not in zmap:
                raise ValueError(f"vehicle {v.id} depot {v.depot_id!r} is not in the travel matrix")
            vehicles[v.id] = VehicleKernel(
                depot=zmap[v.depot_id],
                shift_start=v.shift_start,
                shift_end=v.shift_end,
                cap_p=v.passenger_capacity,
                cap_w=v.wheelchair_capacity,
                flags=vf,
                wmask=_wt_mask(v),
                unavail=tuple((int(a), int(b)) for a, b in v.unavailable_intervals),
                area=tuple(zmap[z] for z in v.service_area if z in zmap),
            )
        drivers: dict[str, DriverKernel] = {}
        for d in problem.drivers:
            drivers[d.id] = DriverKernel(
                shift_start=d.shift_start,
                shift_end=d.shift_end,
                assist=d.accessibility_training,
            )
        return cls(
            n_zones=n,
            travel=tuple(travel),
            trip_ids=tuple(ids),
            id_to_idx=id_to_idx,
            pu=tuple(pu),
            do=tuple(do),
            earliest=tuple(earliest),
            latest=tuple(latest),
            max_wait=tuple(max_wait),
            max_ride=tuple(max_ride),
            board=tuple(board),
            alight=tuple(alight),
            appt_s=tuple(appt_s),
            appt_e=tuple(appt_e),
            seats=tuple(seats),
            wunits=tuple(wunits),
            flags=tuple(flags),
            wt=tuple(wt),
            via=tuple(via),
            via_svc=tuple(via_svc),
            detour=tuple(detour),
            vehicles=vehicles,
            drivers=drivers,
        )

    def tt(self, a: int, b: int) -> int:
        return self.travel[a * self.n_zones + b]

    def stops_to_arrays(self, stops: list[Stop]) -> tuple[list[int], list[int]]:
        trips: list[int] = []
        kinds: list[int] = []
        for s in service_stops(stops):
            if s.trip_id is None:
                continue
            trips.append(self.id_to_idx[s.trip_id])
            if s.stop_type == StopType.PICKUP:
                kinds.append(0)
            elif s.stop_type == StopType.VIA:
                kinds.append(2)
            else:
                kinds.append(1)
        return trips, kinds


def append_trip_soa(
    k: ProblemKernel, trip: TripRequest, zmap: dict[str, int]
) -> tuple[int, list[int], float]:
    """Append one trip to the Python SoA tables. Empty row means already present."""
    existing = k.id_to_idx.get(trip.id)
    if existing is not None:
        return existing, [], 0.0
    fl = 0
    if trip.needs_lift:
        fl |= FLAG_LIFT
    if trip.needs_ramp:
        fl |= FLAG_RAMP
    if trip.needs_boarding_assistance:
        fl |= FLAG_ASSIST
    if trip.wheelchair_requirement == WheelchairType.STRETCHER:
        fl |= FLAG_STRETCHER
    pu = zmap.get(trip.pickup_zone, -1)
    do = zmap.get(trip.dropoff_zone, -1)
    via = zmap[trip.via_zone] if trip.via_zone and trip.via_zone in zmap else -1
    det = float(trip.max_detour_ratio)
    row = [
        pu,
        do,
        trip.earliest_pickup,
        trip.latest_pickup,
        trip.max_wait_time,
        trip.max_ride_time,
        trip.boarding_duration,
        trip.alighting_duration,
        -1 if trip.appointment_start is None else trip.appointment_start,
        -1 if trip.appointment_end is None else trip.appointment_end,
        1 + trip.companion_count,
        0 if trip.wheelchair_requirement == WheelchairType.NONE else 1,
        fl,
        _wt_code(trip.wheelchair_requirement),
        via,
        trip.via_service_duration,
    ]
    idx = len(k.trip_ids)
    k.id_to_idx[trip.id] = idx
    k.trip_ids = (*k.trip_ids, trip.id)
    k.pu = (*k.pu, pu)
    k.do = (*k.do, do)
    k.earliest = (*k.earliest, trip.earliest_pickup)
    k.latest = (*k.latest, trip.latest_pickup)
    k.max_wait = (*k.max_wait, trip.max_wait_time)
    k.max_ride = (*k.max_ride, trip.max_ride_time)
    k.board = (*k.board, trip.boarding_duration)
    k.alight = (*k.alight, trip.alighting_duration)
    k.appt_s = (*k.appt_s, row[8])
    k.appt_e = (*k.appt_e, row[9])
    k.seats = (*k.seats, row[10])
    k.wunits = (*k.wunits, row[11])
    k.flags = (*k.flags, fl)
    k.wt = (*k.wt, row[13])
    k.via = (*k.via, via)
    k.via_svc = (*k.via_svc, trip.via_service_duration)
    k.detour = (*k.detour, det)
    return idx, row, det


def _compat(k: ProblemKernel, vk: VehicleKernel, idx: int) -> bool:
    if k.pu[idx] < 0 or k.do[idx] < 0:
        return False
    if vk.area:
        if k.pu[idx] not in vk.area or k.do[idx] not in vk.area:
            return False
        if k.via[idx] >= 0 and k.via[idx] not in vk.area:
            return False
    fl = k.flags[idx]
    if k.wt[idx] != WT_NONE:
        if vk.cap_w < 1:
            return False
        if (vk.wmask & (1 << k.wt[idx])) == 0:
            return False
    if (fl & FLAG_LIFT) and not (vk.flags & FLAG_LIFT):
        return False
    if (fl & FLAG_RAMP) and not (vk.flags & (FLAG_RAMP | FLAG_LIFT)):
        return False
    if k.seats[idx] > vk.cap_p:
        return False
    return vk.shift_end > vk.shift_start


def simulate_score(
    k: ProblemKernel,
    vk: VehicleKernel,
    dk: DriverKernel | None,
    stop_trip: list[int],
    stop_kind: list[int],
    nstop: int | None = None,
) -> tuple[int, int, int] | None:
    """Return (duration, wait_sum, max_load) or None if infeasible."""
    loc = vk.depot
    tnow = vk.shift_start
    end = vk.shift_end
    if dk is not None:
        if tnow < dk.shift_start:
            tnow = dk.shift_start
        if end > dk.shift_end:
            end = dk.shift_end
    load = 0
    wload = 0
    wait_sum = 0
    max_load = 0
    if nstop is None:
        nstop = len(stop_trip)
    n_trips = len(k.trip_ids)
    buf = k._pickup_dep_buf
    if len(buf) < n_trips:
        buf.extend([-1] * (n_trips - len(buf)))
        k._pickup_dep_buf = buf
    pickup_dep = buf
    for i in range(n_trips):
        pickup_dep[i] = -1
    stretcher_on = 0
    travel = k.travel
    nz = k.n_zones
    pu = k.pu
    do = k.do
    earliest = k.earliest
    latest = k.latest
    max_wait = k.max_wait
    max_ride = k.max_ride
    board = k.board
    alight = k.alight
    appt_s = k.appt_s
    appt_e = k.appt_e
    seats = k.seats
    wunits = k.wunits
    flags = k.flags
    via = k.via
    via_svc = k.via_svc
    detour = k.detour
    cap_p = vk.cap_p
    cap_w = vk.cap_w
    depot = vk.depot
    unavail = vk.unavail
    assist_ok = dk is not None and dk.assist
    for s in range(nstop):
        idx = stop_trip[s]
        kind = stop_kind[s]
        if kind == 0:
            dest = pu[idx]
        elif kind == 2:
            dest = via[idx]
            if dest < 0:
                return None
        else:
            dest = do[idx]
        if load == 0 and loc == depot:
            tnow = push_past_unavail(tnow, unavail)
        t_begin = tnow
        arrive = tnow + travel[loc * nz + dest]
        if kind == 0:
            hold = 0
            pwait = 0
            if arrive < earliest[idx]:
                hold = earliest[idx] - arrive
                arrive = earliest[idx]
            else:
                pwait = arrive - earliest[idx]
            if hold > max_wait[idx] and load > 0:
                return None
            if pwait > max_wait[idx]:
                return None
            if arrive > latest[idx]:
                return None
            if not _compat(k, vk, idx):
                return None
            if (flags[idx] & FLAG_ASSIST) and not assist_ok:
                return None
            if (flags[idx] & FLAG_STRETCHER) and load > 0:
                return None
            if stretcher_on:
                return None
            if flags[idx] & FLAG_STRETCHER:
                stretcher_on += 1
            wait_sum += pwait
            svc = max(board[idx], CURB_WAIT_MINUTES)
            load += seats[idx]
            wload += wunits[idx]
            if load > cap_p or wload > cap_w:
                return None
            if load > max_load:
                max_load = load
        elif kind == 2:
            if pickup_dep[idx] < 0:
                return None
            svc = via_svc[idx]
        else:
            if pickup_dep[idx] < 0:
                return None
            if appt_s[idx] >= 0:
                early_do = appt_s[idx] - EARLY_DROPOFF_SLACK
                if early_do < 0:
                    early_do = 0
                if arrive < early_do:
                    if load > seats[idx]:
                        return None
                    arrive = early_do
            ride = arrive - pickup_dep[idx]
            if ride > max_ride[idx]:
                return None
            if via[idx] >= 0:
                direct = (
                    travel[pu[idx] * nz + via[idx]] + via_svc[idx] + travel[via[idx] * nz + do[idx]]
                )
            else:
                direct = travel[pu[idx] * nz + do[idx]]
            if direct > 0 and ride > detour_limit(direct, detour[idx]):
                return None
            if appt_e[idx] >= 0 and arrive > appt_e[idx]:
                return None
            svc = alight[idx]
            load -= seats[idx]
            wload -= wunits[idx]
            if load < 0 or wload < 0:
                return None
            if flags[idx] & FLAG_STRETCHER:
                stretcher_on -= 1
        leave = arrive + svc
        if leave > end:
            return None
        if occupancy_overlaps(t_begin, leave, unavail):
            return None
        if kind == 0:
            pickup_dep[idx] = leave
        loc = dest
        tnow = leave
    t_ret = tnow
    tnow += travel[loc * nz + depot]
    if tnow > end:
        return None
    if occupancy_overlaps(t_ret, tnow, unavail):
        return None
    return tnow - vk.shift_start, wait_sum, max_load


def best_insert_python(
    k: ProblemKernel,
    vk: VehicleKernel,
    dk: DriverKernel | None,
    stop_trip: list[int],
    stop_kind: list[int],
    new_idx: int,
) -> tuple[int, int, int, int, int, int] | None:
    """Best (i, mid, j, duration, wait_sum, max_load). mid=-1 when the trip has no VIA."""
    if k.via[new_idx] >= 0:
        return _best_insert_via(k, vk, dk, stop_trip, stop_kind, new_idx)
    m = len(stop_trip)
    seq_t = [0] * (m + 2)
    seq_k = [0] * (m + 2)
    best: tuple[int, int, int, int, int, int] | None = None
    best_key: tuple[int, int, int, int, int] | None = None
    for i in range(m + 1):
        for j in range(i, m + 1):
            p = 0
            for t in range(i):
                seq_t[p] = stop_trip[t]
                seq_k[p] = stop_kind[t]
                p += 1
            seq_t[p] = new_idx
            seq_k[p] = 0
            p += 1
            for t in range(i, j):
                seq_t[p] = stop_trip[t]
                seq_k[p] = stop_kind[t]
                p += 1
            seq_t[p] = new_idx
            seq_k[p] = 1
            p += 1
            for t in range(j, m):
                seq_t[p] = stop_trip[t]
                seq_k[p] = stop_kind[t]
                p += 1
            scored = simulate_score(k, vk, dk, seq_t, seq_k, nstop=p)
            if scored is None:
                continue
            dur, wait, mx = scored
            key = (dur, wait, -mx, i, j)
            if best_key is None or key < best_key:
                best_key = key
                best = (i, -1, j, dur, wait, mx)
    return best


def _best_insert_via(
    k: ProblemKernel,
    vk: VehicleKernel,
    dk: DriverKernel | None,
    stop_trip: list[int],
    stop_kind: list[int],
    new_idx: int,
) -> tuple[int, int, int, int, int, int] | None:
    m = len(stop_trip)
    seq_t = [0] * (m + 3)
    seq_k = [0] * (m + 3)
    best: tuple[int, int, int, int, int, int] | None = None
    best_key: tuple[int, int, int, int, int, int] | None = None
    for i in range(m + 1):
        for mid in range(i, m + 1):
            for j in range(mid, m + 1):
                p = 0
                for t in range(i):
                    seq_t[p] = stop_trip[t]
                    seq_k[p] = stop_kind[t]
                    p += 1
                seq_t[p] = new_idx
                seq_k[p] = 0
                p += 1
                for t in range(i, mid):
                    seq_t[p] = stop_trip[t]
                    seq_k[p] = stop_kind[t]
                    p += 1
                seq_t[p] = new_idx
                seq_k[p] = 2
                p += 1
                for t in range(mid, j):
                    seq_t[p] = stop_trip[t]
                    seq_k[p] = stop_kind[t]
                    p += 1
                seq_t[p] = new_idx
                seq_k[p] = 1
                p += 1
                for t in range(j, m):
                    seq_t[p] = stop_trip[t]
                    seq_k[p] = stop_kind[t]
                    p += 1
                scored = simulate_score(k, vk, dk, seq_t, seq_k, nstop=p)
                if scored is None:
                    continue
                dur, wait, mx = scored
                key = (dur, wait, -mx, i, mid, j)
                if best_key is None or key < best_key:
                    best_key = key
                    best = (i, mid, j, dur, wait, mx)
    return best


def packed_trip_table(k: ProblemKernel) -> list[int]:
    n = len(k.trip_ids)
    table: list[int] = []
    for i in range(n):
        table.extend(
            (
                k.pu[i],
                k.do[i],
                k.earliest[i],
                k.latest[i],
                k.max_wait[i],
                k.max_ride[i],
                k.board[i],
                k.alight[i],
                k.appt_s[i],
                k.appt_e[i],
                k.seats[i],
                k.wunits[i],
                k.flags[i],
                k.wt[i],
                k.via[i],
                k.via_svc[i],
            )
        )
    if len(table) != n * TRIP_STRIDE:
        raise RuntimeError("trip table stride mismatch")
    return table


def vehicle_payload(vk: VehicleKernel, dk: DriverKernel | None) -> tuple[list[int], list[int]]:
    unavail: list[int] = []
    for a, b in vk.unavail:
        unavail.extend((a, b))
    veh = [
        vk.depot,
        vk.shift_start,
        vk.shift_end,
        vk.cap_p,
        vk.cap_w,
        vk.flags,
        vk.wmask,
        dk.shift_start if dk else vk.shift_start,
        dk.shift_end if dk else vk.shift_end,
        1 if (dk is not None and dk.assist) else 0,
        0 if dk is None else 1,
        len(vk.area),
        *vk.area,
    ]
    return veh, unavail


def pack_for_native(
    k: ProblemKernel,
    vk: VehicleKernel,
    dk: DriverKernel | None,
    stop_trip: list[int],
    stop_kind: list[int],
    new_idx: int,
) -> NativePack:
    veh, unavail = vehicle_payload(vk, dk)
    return {
        "travel": list(k.travel),
        "n_zones": k.n_zones,
        "trip_table": packed_trip_table(k),
        "detour": list(k.detour),
        "stop_trip": stop_trip,
        "stop_kind": stop_kind,
        "new_idx": new_idx,
        "veh": veh,
        "unavail": unavail,
    }
