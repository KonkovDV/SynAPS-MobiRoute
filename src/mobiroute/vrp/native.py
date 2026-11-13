"""Bridge to the Rust repair kernel (``mobiroute_native.VrpKernel``).

The kernel is optional: without the compiled extension every solver falls
back to the Python reference in :mod:`mobiroute.vrp.insertion`, which gives
the same plans, only slower. ``MOBIROUTE_DISABLE_NATIVE=1`` forces the
fallback.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from mobiroute.vrp.insertion import Compiled
from mobiroute.vrp.solution import Route, Solution

NativeRepair = Callable[[Solution, int, float, int, "int | None"], Solution]


def _module() -> Any | None:
    if os.environ.get("MOBIROUTE_DISABLE_NATIVE") == "1":
        return None
    try:
        import mobiroute_native
    except ImportError:
        return None
    return mobiroute_native if hasattr(mobiroute_native, "VrpKernel") else None


def available() -> bool:
    return _module() is not None


def build_kernel(c: Compiled) -> Any | None:
    """Flatten the compiled instance into the kernel's arrays (shared matrices once)."""
    module = _module()
    if module is None:
        return None
    matrices: list[list[float]] = []
    index: dict[int, int] = {}

    def slot(matrix: tuple[tuple[float, ...], ...]) -> int:
        key = id(matrix)
        if key not in index:
            index[key] = len(matrices)
            matrices.append([value for row in matrix for value in row])
        return index[key]

    time_idx = [slot(m) for m in c.time]
    cost_idx = [slot(m) for m in c.cost]
    n_types = c.n_types
    allowed = [False] * (len(c.pick) * n_types)
    for r, types in enumerate(c.allowed):
        for t in types:
            allowed[r * n_types + t] = True
    return module.VrpKernel(
        c.n,
        c.dims,
        c.e,
        c.l,
        c.s,
        matrices,
        time_idx,
        cost_idx,
        c.svc_rate,
        c.open_cost,
        [q for cap in c.cap for q in cap],
        c.count,
        c.start,
        c.end,
        c.t_min,
        c.start_lim,
        c.end_lim,
        c.max_dur,
        c.pick,
        c.deliv,
        [q for demand in c.demand for q in demand],
        c.max_ride,
        allowed,
        c.node_req,
        c.max_cost,
    )


def native_repair(c: Compiled) -> NativeRepair | None:
    """Regret repair on the Rust kernel, or ``None`` if the kernel is unavailable."""
    kernel = build_kernel(c)
    if kernel is None:
        return None

    def repair(sol: Solution, regret: int, noise: float, seed: int, cap: int | None) -> Solution:
        routes, unassigned = kernel.repair(
            [(r.vehicle_type, r.nodes) for r in sol.routes if r.nodes],
            sorted(sol.unassigned),
            regret,
            noise,
            seed,
            cap,
        )
        return Solution([Route(t, list(nodes)) for t, nodes in routes], set(unassigned))

    return repair
