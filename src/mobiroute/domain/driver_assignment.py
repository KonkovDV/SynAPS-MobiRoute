"""First-class driver-vehicle assignment. Never infer a driver from depot_id alone."""

from __future__ import annotations

from mobiroute.domain.requests import DayProblem, Driver, DriverAssignment, Vehicle


def driver_compatible(
    driver: Driver,
    vehicle: Vehicle,
    *,
    needs_accessibility: bool,
) -> bool:
    if not driver.availability:
        return False
    if driver.depot_id != vehicle.depot_id:
        return False
    if driver.shift_end <= vehicle.shift_start or driver.shift_start >= vehicle.shift_end:
        return False
    if needs_accessibility and not driver.accessibility_training:
        return False
    qualified = driver.qualified_vehicle_types
    return not (qualified and vehicle.vehicle_type not in qualified)


def select_driver(
    problem: DayProblem,
    vehicle: Vehicle,
    *,
    needs_accessibility: bool = False,
    occupied_driver_ids: set[str] | None = None,
    preferred_id: str | None = None,
) -> str | None:
    """Pick a free compatible driver. Returns None — never a random fallback."""
    occupied = occupied_driver_ids or set()
    dmap = {d.id: d for d in problem.drivers}
    if preferred_id and preferred_id not in occupied:
        pref = dmap.get(preferred_id)
        if pref is not None and driver_compatible(
            pref, vehicle, needs_accessibility=needs_accessibility
        ):
            return pref.id
    candidates = [
        d
        for d in problem.drivers
        if d.id not in occupied
        and driver_compatible(d, vehicle, needs_accessibility=needs_accessibility)
    ]
    candidates.sort(key=lambda d: d.id)
    return candidates[0].id if candidates else None


def assignment_record(
    problem: DayProblem,
    vehicle_id: str,
    driver_id: str | None,
    *,
    needs_accessibility: bool,
) -> DriverAssignment | None:
    if driver_id is None:
        return None
    vmap = {v.id: v for v in problem.vehicles}
    dmap = {d.id: d for d in problem.drivers}
    vehicle = vmap.get(vehicle_id)
    driver = dmap.get(driver_id)
    if vehicle is None or driver is None:
        return None
    ok = driver_compatible(driver, vehicle, needs_accessibility=needs_accessibility)
    return DriverAssignment(
        driver_id=driver.id,
        vehicle_id=vehicle.id,
        shift_start=max(driver.shift_start, vehicle.shift_start),
        shift_end=min(driver.shift_end, vehicle.shift_end),
        qualification_match=ok,
        accessibility_training=driver.accessibility_training,
        assignment_status="ASSIGNED" if ok else "CONFLICT",
    )
