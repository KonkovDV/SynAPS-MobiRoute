"""Required PyO3 native seam — greedy/beam/ALNS/online scoring is Rust-only."""

from __future__ import annotations

import importlib
import os
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from mobiroute.domain.requests import PlanningResult, TripRequest
from mobiroute.solvers.insertion_kernel import (
    DriverKernel,
    ProblemKernel,
    VehicleKernel,
    append_trip_soa,
    packed_trip_table,
    vehicle_payload,
)

NativeEval = tuple[
    int,
    int,
    list[tuple[int, int]],
    list[tuple[int, int]],
    list[tuple[int, int, int, int]],
]

_KERNELS: dict[str, ProblemKernel] = {}

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


def set_fleet(
    k: ProblemKernel,
    stop_trips: list[list[int]],
    stop_kinds: list[list[int]],
    vehs: list[list[int]],
    unavails: list[list[int]],
) -> None:
    eng = k.native_engine
    if eng is None:
        raise RuntimeError(NATIVE_REQUIRED)
    method = getattr(eng, "set_fleet", None)
    if not callable(method):
        raise RuntimeError(NATIVE_REQUIRED)
    method(stop_trips, stop_kinds, vehs, unavails)


def set_vehicle(k: ProblemKernel, fleet_i: int, veh: list[int], unavail: list[int]) -> None:
    eng = k.native_engine
    if eng is None:
        raise RuntimeError(NATIVE_REQUIRED)
    method = getattr(eng, "set_vehicle", None)
    if not callable(method):
        raise RuntimeError(NATIVE_REQUIRED)
    method(fleet_i, veh, unavail)


def score_stored(k: ProblemKernel, new_idx: int) -> list[tuple[int, int, int, int, int, int, int]]:
    eng = k.native_engine
    if eng is None:
        raise RuntimeError(NATIVE_REQUIRED)
    method = getattr(eng, "score_stored", None)
    if not callable(method):
        raise RuntimeError(NATIVE_REQUIRED)
    raw = method(new_idx)
    if raw is None or isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise TypeError("native score_stored must return a sequence")
    out: list[tuple[int, int, int, int, int, int, int]] = []
    for row in raw:
        got = _coerce7(row)
        if got is None:
            raise TypeError("native score_stored rows must be 7-tuples of ints")
        out.append(got)
    return out


def commit_insert(k: ProblemKernel, fleet_i: int, i: int, mid: int, j: int, new_idx: int) -> None:
    eng = k.native_engine
    if eng is None:
        raise RuntimeError(NATIVE_REQUIRED)
    method = getattr(eng, "commit_insert", None)
    if not callable(method):
        raise RuntimeError(NATIVE_REQUIRED)
    method(fleet_i, i, mid, j, new_idx)


def trial_rides(
    k: ProblemKernel, fleet_i: int, i: int, mid: int, j: int, new_idx: int
) -> list[tuple[int, int]] | None:
    eng = k.native_engine
    if eng is None:
        raise RuntimeError(NATIVE_REQUIRED)
    method = getattr(eng, "trial_rides", None)
    if not callable(method):
        raise RuntimeError(NATIVE_REQUIRED)
    raw = method(fleet_i, i, mid, j, new_idx)
    if raw is None:
        return None
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise TypeError("native trial_rides must return a sequence or None")
    out: list[tuple[int, int]] = []
    for row in raw:
        if not isinstance(row, Sequence) or len(row) != 2:
            raise TypeError("native trial_rides rows must be (trip_idx, ride) ints")
        out.append((_as_int(row[0]), _as_int(row[1])))
    return out


def _pair_list(raw: object, label: str) -> list[tuple[int, int]]:
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise TypeError(f"native {label} must be a sequence")
    out: list[tuple[int, int]] = []
    for row in raw:
        if not isinstance(row, Sequence) or len(row) != 2:
            raise TypeError(f"native {label} rows must be 2-tuples of ints")
        out.append((_as_int(row[0]), _as_int(row[1])))
    return out


def _quad_list(raw: object, label: str) -> list[tuple[int, int, int, int]]:
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise TypeError(f"native {label} must be a sequence")
    out: list[tuple[int, int, int, int]] = []
    for row in raw:
        if not isinstance(row, Sequence) or len(row) != 4:
            raise TypeError(f"native {label} rows must be 4-tuples of ints")
        out.append((_as_int(row[0]), _as_int(row[1]), _as_int(row[2]), _as_int(row[3])))
    return out


def _coerce_eval(raw: object) -> NativeEval | None:
    if raw is None:
        return None
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence) or len(raw) != 5:
        raise TypeError("native eval must return a 5-tuple or None")
    return (
        _as_int(raw[0]),
        _as_int(raw[1]),
        _pair_list(raw[2], "eval.rides"),
        _pair_list(raw[3], "eval.waits"),
        _quad_list(raw[4], "eval.stops"),
    )


def set_route(k: ProblemKernel, fleet_i: int, stop_trip: list[int], stop_kind: list[int]) -> None:
    eng = k.native_engine
    if eng is None:
        raise RuntimeError(NATIVE_REQUIRED)
    method = getattr(eng, "set_route", None)
    if not callable(method):
        raise RuntimeError(NATIVE_REQUIRED)
    method(fleet_i, stop_trip, stop_kind)


def fleet_len(k: ProblemKernel) -> int:
    eng = k.native_engine
    if eng is None:
        raise RuntimeError(NATIVE_REQUIRED)
    method = getattr(eng, "fleet_len", None)
    if not callable(method):
        raise RuntimeError(NATIVE_REQUIRED)
    return _as_int(method())


def eval_route(k: ProblemKernel, fleet_i: int) -> NativeEval | None:
    eng = k.native_engine
    if eng is None:
        raise RuntimeError(NATIVE_REQUIRED)
    method = getattr(eng, "eval_route", None)
    if not callable(method):
        raise RuntimeError(NATIVE_REQUIRED)
    return _coerce_eval(method(fleet_i))


def eval_fleet(k: ProblemKernel) -> list[NativeEval | None]:
    eng = k.native_engine
    if eng is None:
        raise RuntimeError(NATIVE_REQUIRED)
    method = getattr(eng, "eval_fleet", None)
    if not callable(method):
        raise RuntimeError(NATIVE_REQUIRED)
    raw = method()
    if raw is None or isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise TypeError("native eval_fleet must return a sequence")
    return [_coerce_eval(row) for row in raw]


def trial_eval(
    k: ProblemKernel, fleet_i: int, i: int, mid: int, j: int, new_idx: int
) -> NativeEval | None:
    eng = k.native_engine
    if eng is None:
        raise RuntimeError(NATIVE_REQUIRED)
    method = getattr(eng, "trial_eval", None)
    if not callable(method):
        raise RuntimeError(NATIVE_REQUIRED)
    return _coerce_eval(method(fleet_i, i, mid, j, new_idx))


def fork_kernel(k: ProblemKernel) -> ProblemKernel:
    eng = k.native_engine
    if eng is None:
        raise RuntimeError(NATIVE_REQUIRED)
    method = getattr(eng, "fork", None)
    if not callable(method):
        raise RuntimeError(NATIVE_REQUIRED)
    return replace(k, native_engine=method(), id_to_idx=dict(k.id_to_idx), _pickup_dep_buf=[])


def append_trip(k: ProblemKernel, trip: TripRequest, zmap: dict[str, int]) -> int:
    idx, row, det = append_trip_soa(k, trip, zmap)
    if not row:
        return idx
    eng = k.native_engine
    if eng is None:
        raise RuntimeError(NATIVE_REQUIRED)
    method = getattr(eng, "append_trip", None)
    if not callable(method):
        raise RuntimeError(NATIVE_REQUIRED)
    native_idx = _as_int(method(row, det))
    if native_idx != idx:
        raise RuntimeError("native append_trip index drifted from Python kernel")
    return idx


def stash_kernel(result: PlanningResult, k: ProblemKernel) -> None:
    key = result.plan_id or result.input_hash
    if key:
        _KERNELS[key] = k


def kernel_for(result: PlanningResult) -> ProblemKernel | None:
    key = result.plan_id or result.input_hash
    if not key:
        return None
    return _KERNELS.get(key)
