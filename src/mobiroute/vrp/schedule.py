"""Timing of a fixed stop sequence as a system of difference constraints.

For a route with a fixed order of stops, every timing rule is a constraint
of the form ``B[head] - B[tail] <= weight`` on service-start times ``B``:

* window ``e <= B[k] <= l`` (through a zero clock ``z``),
* travel ``B[k+1] >= B[k] + service[k] + travel(k, k+1)``,
* ride limit ``B[delivery] - (B[pickup] + service[pickup]) <= L``,
* shift length ``B[end] - B[start] <= T``.

Such a system is feasible iff its constraint graph has no negative cycle
(CLRS 24.4). Bellman-Ford then gives, from one source, the earliest schedule,
the latest schedule and the shortest feasible route duration
(``-dist(end -> start)``). A negative cycle is a certificate: the named
constraints cannot hold together, and minus its weight is the number of
minutes they are short by. No solver is involved, which is the point.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from mobiroute.vrp.model import Instance

#: Tolerance for comparing clock values computed along different paths.
TIME_EPS = 1e-6


@dataclass(frozen=True, slots=True)
class Arc:
    """``B[head] - B[tail] <= weight``, labelled for certificates."""

    tail: int
    head: int
    weight: float
    label: str


@dataclass(frozen=True, slots=True)
class Infeasibility:
    """A negative cycle: the constraints that conflict and the minutes missing."""

    short_by: float
    labels: tuple[str, ...]


def _relax_cycle(n: int, pred: list[Arc | None], start: int, backwards: bool) -> list[Arc]:
    """Walk predecessors ``n`` steps to land on the cycle, then collect it."""
    vertex = start
    for _ in range(n):
        step = pred[vertex]
        if step is None:
            return []
        vertex = step.head if backwards else step.tail
    cycle: list[Arc] = []
    first = vertex
    for _ in range(n + 1):
        step = pred[vertex]
        if step is None:
            return []
        cycle.append(step)
        vertex = step.head if backwards else step.tail
        if vertex == first:
            break
    return cycle


def shortest_paths(
    n: int, arcs: Sequence[Arc], root: int, *, to_root: bool
) -> tuple[list[float] | None, list[Arc]]:
    """Bellman-Ford distances from ``root`` (or to it), or a negative cycle.

    With ``to_root`` the arcs are relaxed head-to-tail, so ``dist[k]`` is the
    shortest path from ``k`` to ``root`` in the constraint graph.
    """
    dist = [math.inf] * n
    pred: list[Arc | None] = [None] * n
    dist[root] = 0.0
    for _ in range(n - 1):
        changed = False
        for arc in arcs:
            src, dst = (arc.head, arc.tail) if to_root else (arc.tail, arc.head)
            candidate = dist[src] + arc.weight
            if candidate < dist[dst] - 1e-12:
                dist[dst] = candidate
                pred[dst] = arc
                changed = True
        if not changed:
            return dist, []
    for arc in arcs:
        src, dst = (arc.head, arc.tail) if to_root else (arc.tail, arc.head)
        if dist[src] + arc.weight < dist[dst] - TIME_EPS:
            pred[dst] = arc
            return None, _relax_cycle(n, pred, dst, to_root)
    return dist, []


def certificate(cycle: Sequence[Arc]) -> Infeasibility:
    labels = list(dict.fromkeys(arc.label for arc in reversed(cycle)))
    return Infeasibility(short_by=round(-sum(arc.weight for arc in cycle), 6), labels=tuple(labels))


@dataclass(frozen=True, slots=True)
class RouteTiming:
    """Exact timing facts of one route; ``None`` fields mean infeasible."""

    feasible: bool
    earliest: tuple[float, ...]
    latest: tuple[float, ...]
    min_duration: float
    infeasibility: Infeasibility | None


def route_arcs(
    inst: Instance, vehicle_type: int, nodes: Sequence[int], *, slack: float = 0.0
) -> tuple[int, list[Arc]]:
    """Constraint graph of ``start depot + nodes + end depot``.

    Vertices ``0..m+1`` are stops in order and ``m+2`` is the zero clock.
    ``slack`` widens every upper window bound; :mod:`mobiroute.vrp.lateness`
    uses it to price a late schedule.
    """
    vt = inst.vehicle_types[vehicle_type]
    profile = inst.profiles[vt.profile]
    seq = [vt.start_depot, *nodes, vt.end_depot]
    m = len(seq)
    z = m
    arcs: list[Arc] = []
    for k, node in enumerate(seq):
        info = inst.nodes[node]
        lo, hi = info.earliest, info.latest
        if k == 0:
            lo, hi = max(lo, vt.shift_start), min(hi, vt.shift_end)
        elif k == m - 1:
            hi = min(hi, vt.shift_end)
        if math.isfinite(hi):
            arcs.append(Arc(z, k, hi + slack, f"LATEST:{node}"))
        arcs.append(Arc(k, z, -lo, f"EARLIEST:{node}"))
    for k in range(m - 1):
        a, b = seq[k], seq[k + 1]
        gap = inst.nodes[a].service + profile.time[a][b]
        arcs.append(Arc(k + 1, k, -gap, f"TRAVEL:{a}->{b}"))
    position = {node: k for k, node in enumerate(seq) if 0 < k < m - 1}
    for k, node in enumerate(seq):
        if not 0 < k < m - 1:
            continue
        req = inst.requests[inst.request_of(node)]
        if req.max_ride is None or req.pickup != node or req.delivery not in position:
            continue
        limit = req.max_ride + inst.nodes[node].service
        arcs.append(Arc(k, position[req.delivery], limit, f"RIDE:{req.id}"))
    if vt.max_duration is not None:
        arcs.append(Arc(0, m - 1, vt.max_duration, "DURATION"))
    return z, arcs


def route_timing(inst: Instance, vehicle_type: int, nodes: Sequence[int]) -> RouteTiming:
    """Earliest and latest schedules and the shortest feasible duration."""
    z, arcs = route_arcs(inst, vehicle_type, nodes)
    m = z
    n_vertices = m + 1
    to_zero, cycle = shortest_paths(n_vertices, arcs, z, to_root=True)
    if to_zero is None:
        return RouteTiming(False, (), (), math.inf, certificate(cycle))
    from_zero, _ = shortest_paths(n_vertices, arcs, z, to_root=False)
    from_end, _ = shortest_paths(n_vertices, arcs, m - 1, to_root=False)
    assert from_zero is not None and from_end is not None
    earliest = tuple(-to_zero[k] for k in range(m))
    latest = tuple(from_zero[k] for k in range(m))
    return RouteTiming(True, earliest, latest, -from_end[0], None)


def describe(inst: Instance, labels: Sequence[str], *, lang: str = "en") -> list[str]:
    """Plain-language reading of certificate labels (Russian or English)."""
    ru = lang == "ru"
    out: list[str] = []
    for label in labels:
        kind, _, ref = label.partition(":")
        if kind in {"LATEST", "EARLIEST"}:
            node = inst.nodes[int(ref)]
            name = node.name or f"#{node.id}"
            if kind == "LATEST":
                out.append(
                    f"{name}: начало не позже {node.latest:g}"
                    if ru
                    else f"{name} must start by {node.latest:g}"
                )
            else:
                out.append(
                    f"{name}: начало не раньше {node.earliest:g}"
                    if ru
                    else f"{name} cannot start before {node.earliest:g}"
                )
        elif kind == "TRAVEL":
            a, b = (int(x) for x in ref.split("->"))
            na = inst.nodes[a].name or f"#{a}"
            nb = inst.nodes[b].name or f"#{b}"
            out.append(f"{na} -> {nb}: переезд и обслуживание" if ru else f"{na} -> {nb}: travel")
        elif kind == "RIDE":
            out.append(f"заявка {ref}: лимит времени в пути" if ru else f"order {ref}: ride limit")
        else:
            out.append("лимит длительности смены" if ru else "shift length limit")
    return out
