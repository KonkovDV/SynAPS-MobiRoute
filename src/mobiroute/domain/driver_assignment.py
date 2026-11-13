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


class DriverIndex:
    """Per-solve cache: driver compatibility is static input, so compute it once.

    ``select_driver`` scanned and sorted every driver for every (trip, vehicle)
    probe; on 2000 requests x 180 vehicles that was 11 million compatibility
    checks. The index keeps the same answer: the preferred driver if free and
    compatible, else the free compatible driver with the smallest id.
    """

    def __init__(self, problem: DayProblem) -> None:
        self._by_id = {d.id: d for d in problem.drivers}
        self._ordered = sorted(problem.drivers, key=lambda d: d.id)
        self._compatible: dict[tuple[str, bool], tuple[str, ...]] = {}

    def compatible_ids(self, vehicle: Vehicle, needs_accessibility: bool) -> tuple[str, ...]:
        key = (vehicle.id, needs_accessibility)
        found = self._compatible.get(key)
        if found is None:
            found = tuple(
                d.id
                for d in self._ordered
                if driver_compatible(d, vehicle, needs_accessibility=needs_accessibility)
            )
            self._compatible[key] = found
        return found

    def pick(
        self,
        vehicle: Vehicle,
        *,
        needs_accessibility: bool,
        occupied: set[str],
        preferred_id: str | None,
    ) -> str | None:
        if preferred_id and preferred_id not in occupied:
            pref = self._by_id.get(preferred_id)
            if pref is not None and driver_compatible(
                pref, vehicle, needs_accessibility=needs_accessibility
            ):
                return pref.id
        for did in self.compatible_ids(vehicle, needs_accessibility):
            if did not in occupied:
                return did
        return None


def select_driver(
    problem: DayProblem,
    vehicle: Vehicle,
    *,
    needs_accessibility: bool = False,
    occupied_driver_ids: set[str] | None = None,
    preferred_id: str | None = None,
    index: DriverIndex | None = None,
) -> str | None:
    """Pick a free compatible driver. Returns None — never a random fallback."""
    return (index or DriverIndex(problem)).pick(
        vehicle,
        needs_accessibility=needs_accessibility,
        occupied=occupied_driver_ids or set(),
        preferred_id=preferred_id,
    )


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
