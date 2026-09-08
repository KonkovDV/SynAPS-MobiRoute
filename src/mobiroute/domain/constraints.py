"""Constraint catalog — normative list mirrored in docs/mathematical-formulation.md."""

from math import isfinite

HARD_CONSTRAINT_IDS = [
    "PAIRING_SAME_VEHICLE",
    "PICKUP_BEFORE_DROPOFF",
    "NO_DROPOFF_WITHOUT_PICKUP",
    "PICKUP_TIME_WINDOW",
    "DROPOFF_OR_APPOINTMENT_WINDOW",
    "MAX_RIDE_TIME",
    "MAX_WAIT_TIME",
    "HOUR_QUOTA",
    "PASSENGER_CAPACITY",
    "WHEELCHAIR_CAPACITY",
    "WHEELCHAIR_TYPE_COMPAT",
    "LIFT_RAMP_COMPAT",
    "COMPANION_CAPACITY",
    "DRIVER_QUALIFICATION",
    "DRIVER_SHIFT",
    "DRIVER_REST",
    "NO_VEHICLE_DOUBLE_BOOK",
    "TRAVEL_TIME",
    "BOARDING_ALIGHTING",
    "DEPOT_START",
    "DEPOT_RETURN_BY_SHIFT_END",
    "BLOCKED_LOCATIONS",
    "SERVICE_AREA",
    "STRETCHER_EXCLUSIVE",
    "VALID_POOLING",
    "VIA_BETWEEN_PICKUP_DROPOFF",
    "DROPOFF_EARLY_CAP",
    "CURB_WAIT",
    "CANCELLED_EXCLUDED",
    "URGENT_FEASIBILITY_GATE",
    "FROZEN_IMMUTABLE",
    "EXPLAINABLE_REJECT",
    "REPRODUCIBLE",
]

# DREDF OTP analogue (not Moscow law): drop-off window -30/0 around appointment_start.
EARLY_DROPOFF_SLACK = 30
# FTA/DREDF analogue: driver wait at pickup after the window opens.
CURB_WAIT_MINUTES = 5
# Native route times and returned caps use signed 32-bit integers.
MAX_NATIVE_MINUTES = 2**31 - 1


def pickup_service_minutes(boarding: int) -> int:
    return max(int(boarding), CURB_WAIT_MINUTES)


def earliest_alight_time(appointment_start: int | None) -> int | None:
    if appointment_start is None:
        return None
    return max(0, int(appointment_start) - EARLY_DROPOFF_SLACK)


def detour_limit(direct_minutes: int, ratio: float) -> int:
    """Ties-to-even milliratio; saturate caps at the native time maximum."""
    scaled = float(ratio) * 1000.0
    if not isfinite(scaled) or ratio <= 0:
        raise ValueError("DETOUR_RATIO_MUST_BE_POSITIVE_AND_FINITE_AFTER_SCALING")
    if (
        isinstance(direct_minutes, bool)
        or not isinstance(direct_minutes, int)
        or direct_minutes < 0
    ):
        raise ValueError("DIRECT_MINUTES_MUST_BE_A_NONNEGATIVE_INTEGER")
    milli = round(scaled)
    return min((direct_minutes * milli) // 1000 + 1, MAX_NATIVE_MINUTES)


def occupancy_overlaps(
    start: int, end: int, intervals: list[tuple[int, int]] | tuple[tuple[int, int], ...]
) -> bool:
    """True if [start, end) overlaps any unavailable interval."""
    return any(start < u1 and end > u0 for u0, u1 in intervals)


def combine_unavail(
    vehicle_intervals: list[tuple[int, int]] | tuple[tuple[int, int], ...],
    driver_intervals: list[tuple[int, int]] | tuple[tuple[int, int], ...] = (),
) -> tuple[tuple[int, int], ...]:
    """Union of vehicle shop windows and driver rest/unavail (policy data)."""
    merged = tuple((int(a), int(b)) for a, b in vehicle_intervals)
    if not driver_intervals:
        return merged
    return merged + tuple((int(a), int(b)) for a, b in driver_intervals)


def push_past_unavail(
    tnow: int, intervals: list[tuple[int, int]] | tuple[tuple[int, int], ...]
) -> int:
    """Wait at depot through shop/maintenance windows (empty vehicle only)."""
    moved = True
    while moved:
        moved = False
        for u0, u1 in intervals:
            if u0 <= tnow < u1:
                tnow = u1
                moved = True
    return tnow
