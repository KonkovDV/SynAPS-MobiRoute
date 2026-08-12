"""Privacy redaction — never log PII; open mode strips coordinates."""

from __future__ import annotations

import re

from mobiroute.domain.models import DataProvenance, PrivacyClass
from mobiroute.domain.requests import DayProblem, TripRequest

_PHONE = re.compile(r"\+?\d[\d\-()\s]{7,}\d")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def redact_trip_for_open(trip: TripRequest) -> TripRequest:
    data = trip.model_dump()
    data["pickup_coordinates"] = None
    data["dropoff_coordinates"] = None
    data["data_provenance"] = DataProvenance.SYNTHETIC
    return TripRequest.model_validate(data)


def redact_problem_for_open(problem: DayProblem) -> DayProblem:
    reqs = [redact_trip_for_open(t) for t in problem.requests]
    passengers = []
    for p in problem.passengers:
        d = p.model_dump()
        d["privacy_class"] = PrivacyClass.OPEN_SYNTHETIC
        d["data_provenance"] = DataProvenance.SYNTHETIC
        passengers.append(type(p).model_validate(d))
    return problem.model_copy(update={"requests": reqs, "passengers": passengers})


def log_safe(message: str) -> str:
    """Strip phone/email-like patterns from log lines."""
    msg = _PHONE.sub("[REDACTED_PHONE]", message)
    msg = _EMAIL.sub("[REDACTED_EMAIL]", msg)
    return msg


def assert_no_pii_fields(obj: dict[str, object]) -> list[str]:
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
    found = []
    for k in obj:
        if k.lower() in banned:
            found.append(k)
    return found
