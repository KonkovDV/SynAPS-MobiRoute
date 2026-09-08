"""Synthetic-only export guard and limited phone/email log redaction."""

from __future__ import annotations

import re

from mobiroute.domain.models import DataProvenance, PrivacyClass
from mobiroute.domain.requests import DayProblem, TripRequest

_PHONE = re.compile(r"\+?\d[\d\-()\s]{7,}\d")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def redact_trip_for_open(trip: TripRequest) -> TripRequest:
    """Strip synthetic coordinates; never turn real trips into synthetic data."""
    if trip.data_provenance != DataProvenance.SYNTHETIC:
        raise ValueError("OPEN_EXPORT_REQUIRES_SYNTHETIC_TRIP")
    data = trip.model_dump()
    data["pickup_coordinates"] = None
    data["dropoff_coordinates"] = None
    return TripRequest.model_validate(data)


def redact_problem_for_open(problem: DayProblem) -> DayProblem:
    """Prepare synthetic fixtures, not customer-data anonymization."""
    if problem.data_provenance != DataProvenance.SYNTHETIC:
        raise ValueError("OPEN_EXPORT_REQUIRES_SYNTHETIC_PROBLEM")
    public = {PrivacyClass.OPEN_SYNTHETIC, PrivacyClass.PUBLIC_SYNTHETIC}
    if any(
        p.data_provenance != DataProvenance.SYNTHETIC or p.privacy_class not in public
        for p in problem.passengers
    ):
        raise ValueError("OPEN_EXPORT_REQUIRES_SYNTHETIC_PASSENGERS")
    reqs = [redact_trip_for_open(t) for t in problem.requests]
    passengers = []
    for p in problem.passengers:
        d = p.model_dump()
        d["privacy_class"] = PrivacyClass.OPEN_SYNTHETIC
        passengers.append(type(p).model_validate(d))
    return problem.model_copy(update={"requests": reqs, "passengers": passengers})


def log_safe(message: str) -> str:
    """Strip phone/email-like patterns from log lines."""
    msg = _EMAIL.sub("[REDACTED_EMAIL]", message)
    return _PHONE.sub("[REDACTED_PHONE]", msg)


def assert_no_pii_fields(obj: dict[str, object]) -> list[str]:
    """Find banned field paths in JSON-like payloads; not a PII detector."""
    banned = {
        "full_name",
        "fio",
        "phone",
        "email",
        "passport",
        "diagnosis",
        "address",
        "snils",
        "oms",
    }
    found: list[str] = []
    pending: list[tuple[str, object]] = [("", obj)]
    seen: set[int] = set()
    while pending:
        path, value = pending.pop()
        if not isinstance(value, (dict, list, tuple)) or id(value) in seen:
            continue
        seen.add(id(value))
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if str(key).strip().lower() in banned:
                    found.append(child_path)
                pending.append((child_path, child))
        else:
            pending.extend((f"{path}[{i}]", child) for i, child in enumerate(value))
    return sorted(found)
