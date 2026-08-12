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
