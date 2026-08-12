"""Stable hashing — never use Python built-in hash() for fingerprints."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def fingerprint(obj: Any) -> str:
    payload = canonical_json(obj)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fingerprint_problem(problem: Any) -> str:
    """Hash planning inputs without a full Pydantic JSON dump."""
    return fingerprint(
        [
            problem.travel.zones,
            problem.travel.minutes,
            [
                (
                    t.id,
                    t.pseudonymous_passenger_id,
                    t.pickup_zone,
                    t.dropoff_zone,
                    t.via_zone,
                    t.earliest_pickup,
                    t.latest_pickup,
                    t.appointment_start,
                    t.appointment_end,
                    t.max_ride_time,
                    t.max_wait_time,
                    t.boarding_duration,
                    t.alighting_duration,
                    t.via_service_duration,
                    t.max_detour_ratio,
                    t.wheelchair_requirement.value,
                    t.companion_count,
                    t.needs_lift,
                    t.needs_ramp,
                    t.needs_boarding_assistance,
                    t.booking_status.value,
                    t.frozen,
                    t.same_vehicle_as,
                    t.insert_immediately_after,
                    t.quota_minutes_remaining,
                    t.service_priority.value,
                    t.medical_priority,
                    t.eligibility_class.value,
                    t.trip_purpose,
                    t.requested_at,
                )
                for t in problem.requests
            ],
            [
                (
                    v.id,
                    v.depot_id,
                    v.shift_start,
                    v.shift_end,
                    v.passenger_capacity,
                    v.wheelchair_capacity,
                    v.lift_available,
                    v.ramp_available,
                    v.vehicle_type,
                    list(v.unavailable_intervals),
                    list(v.service_area),
                )
                for v in problem.vehicles
            ],
            [
                (
                    d.id,
                    d.depot_id,
                    d.shift_start,
                    d.shift_end,
                    d.availability,
                    d.accessibility_training,
                    tuple(d.qualified_vehicle_types),
                )
                for d in problem.drivers
            ],
            [(p.pseudonymous_id, p.quota_minutes_remaining) for p in problem.passengers],
        ]
    )
