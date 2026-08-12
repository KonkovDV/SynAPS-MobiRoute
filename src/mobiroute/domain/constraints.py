"""Constraint catalog — normative list mirrored in docs/mathematical-formulation.md."""

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


def pickup_service_minutes(boarding: int) -> int:
    return max(int(boarding), CURB_WAIT_MINUTES)


def earliest_alight_time(appointment_start: int | None) -> int | None:
    if appointment_start is None:
        return None
    return max(0, int(appointment_start) - EARLY_DROPOFF_SLACK)


def detour_limit(direct_minutes: int, ratio: float) -> int:
    """Integer cap shared by Python SoA, Rust, CP-SAT, and the notary."""
    milli = round(float(ratio) * 1000.0)
    return (int(direct_minutes) * milli) // 1000 + 1


def occupancy_overlaps(
    start: int, end: int, intervals: list[tuple[int, int]] | tuple[tuple[int, int], ...]
) -> bool:
    """True if [start, end) overlaps any unavailable interval."""
    return any(start < u1 and end > u0 for u0, u1 in intervals)


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
