"""Required PyO3 native seam — greedy/beam/ALNS/online scoring is Rust-only."""

from __future__ import annotations

import importlib
import os
from collections.abc import Sequence
from typing import Any

from mobiroute.solvers.insertion_kernel import (
    DriverKernel,
    ProblemKernel,
    VehicleKernel,
    packed_trip_table,
    vehicle_payload,
)

NATIVE_REQUIRED = (
    "Greedy, beam, ALNS, and online insertion require mobiroute_native. "
    "Build: python -m maturin develop --release "
    "--manifest-path native/mobiroute_native/Cargo.toml"
)

_native: Any | None = None
_native_best_insert: Any | None = None
_engine_cls: Any | None = None

if os.getenv("MOBIROUTE_DISABLE_NATIVE") == "1":
    _native = None
else:
    try:
        _native = importlib.import_module("mobiroute_native")
        _native_best_insert = getattr(_native, "best_insert", None)
        _engine_cls = getattr(_native, "InsertionEngine", None)
    except Exception:
        _native = None
        _native_best_insert = None
        _engine_cls = None


def native_available() -> bool:
    return _engine_cls is not None or _native_best_insert is not None


def acceleration_status() -> dict[str, object]:
    return {
        "native_available": native_available(),
        "insertion_backend": "native" if native_available() else "missing",
        "disable_env": os.getenv("MOBIROUTE_DISABLE_NATIVE") == "1",
    }


def attach_native(k: ProblemKernel) -> ProblemKernel:
    """Keep travel + trip tables in Rust for the whole solve."""
    if _engine_cls is None:
        raise RuntimeError(NATIVE_REQUIRED)
    k.native_engine = _engine_cls(
        list(k.travel),
        k.n_zones,
        packed_trip_table(k),
        list(k.detour),
    )
    return k


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("native kernel must return ints")
    return value


def _coerce6(raw: object) -> tuple[int, int, int, int, int, int] | None:
    if raw is None or isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        return None
    if len(raw) != 6:
        return None
    return (
        _as_int(raw[0]),
        _as_int(raw[1]),
        _as_int(raw[2]),
        _as_int(raw[3]),
        _as_int(raw[4]),
        _as_int(raw[5]),
    )


def _coerce7(raw: object) -> tuple[int, int, int, int, int, int, int] | None:
    if raw is None or isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        return None
    if len(raw) != 7:
        return None
    return (
        _as_int(raw[0]),
        _as_int(raw[1]),
        _as_int(raw[2]),
        _as_int(raw[3]),
        _as_int(raw[4]),
        _as_int(raw[5]),
        _as_int(raw[6]),
    )


def best_insert(
    k: ProblemKernel,
    vk: VehicleKernel,
    dk: DriverKernel | None,
    stop_trip: list[int],
    stop_kind: list[int],
    new_idx: int,
) -> tuple[int, int, int, int, int, int] | None:
    eng = k.native_engine
    if eng is None:
        raise RuntimeError(NATIVE_REQUIRED)
    method = getattr(eng, "best_insert", None)
    if not callable(method):
        raise RuntimeError(NATIVE_REQUIRED)
    veh, unavail = vehicle_payload(vk, dk)
    raw = method(stop_trip, stop_kind, new_idx, veh, unavail)
    if raw is None:
        return None
    got = _coerce6(raw)
    if got is None:
        raise TypeError("native best_insert must return a 6-tuple of ints")
    return got


def score_fleet(
    k: ProblemKernel,
    stop_trips: list[list[int]],
    stop_kinds: list[list[int]],
    vehs: list[list[int]],
    unavails: list[list[int]],
    new_idx: int,
) -> list[tuple[int, int, int, int, int, int, int]]:
    """Per-vehicle best insert. Each row: (fleet_index, i, mid, j, dur, wait, max_load)."""
    eng = k.native_engine
    if eng is None:
        raise RuntimeError(NATIVE_REQUIRED)
    method = getattr(eng, "score_fleet", None)
    if not callable(method):
        raise RuntimeError(NATIVE_REQUIRED)
    raw = method(stop_trips, stop_kinds, vehs, unavails, new_idx)
    if raw is None or isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise TypeError("native score_fleet must return a sequence")
    out: list[tuple[int, int, int, int, int, int, int]] = []
    for row in raw:
        got = _coerce7(row)
        if got is None:
            raise TypeError("native score_fleet rows must be 7-tuples of ints")
        out.append(got)
    return out
