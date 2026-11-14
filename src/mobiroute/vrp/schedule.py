"""Timing of a fixed stop sequence as a system of difference constraints.

For a route with a fixed order of stops, every timing rule is a constraint
of the form ``B[head] - B[tail] <= weight`` on service-start times ``B``:

* window ``e <= B[k] <= l`` (through a zero clock ``z``),
* travel ``B[k+1] >= B[k] + service[k] + travel(k, k+1)``,
* ride limit ``B[delivery] - (B[pickup] + service[pickup]) <= L``,
* shift length ``B[end] - B[start] <= T``,
* a driver's rest of ``b`` minutes in the gap after stop ``k``:
  ``B[k+1] >= B[k] + service[k] + travel(k, k+1) + b``.

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
from dataclasses import dataclass, replace
from itertools import pairwise

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
    #: Gap holding the driver's rest (between stops ``k`` and ``k+1`` of
    #: ``start + nodes + end``), ``None`` when the route needs no rest.
    rest_gap: int | None = None
    driving: float = 0.0
    #: Departure of a shortest schedule (``nan`` when infeasible). Without
    #: traffic it also reaches the end depot at the earliest possible time.
    departure: float = math.nan
    #: With a split break: the gap of its first part (``rest_gap`` then holds
    #: the second part); ``None`` for a single break or none.
    first_gap: int | None = None


def route_arcs(
    inst: Instance,
    vehicle_type: int,
    nodes: Sequence[int],
    *,
    slack: float = 0.0,
    rest_gap: int | None = None,
    first_gap: int | None = None,
) -> tuple[int, list[Arc]]:
    """Constraint graph of ``start depot + nodes + end depot``.

    Vertices ``0..m+1`` are stops in order and ``m+2`` is the zero clock.
    ``slack`` widens every upper window bound; :mod:`mobiroute.vrp.lateness`
    uses it to price a late schedule. ``rest_gap`` puts the type's driver
    rest between stops ``rest_gap`` and ``rest_gap + 1``.
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
        rule = vt.breaks
        if rule is not None and k in (rest_gap, first_gap):
            # A split break puts its first part in first_gap, its second in
            # rest_gap; a single break puts the whole rest in rest_gap.
            if first_gap is None or rule.split is None:
                pause = rule.duration
            else:
                pause = rule.split[1] if k == rest_gap else rule.split[0]
            arcs.append(Arc(k + 1, k, -(gap + pause), f"TRAVEL+REST:{a}->{b}"))
        else:
            arcs.append(Arc(k + 1, k, -gap, f"TRAVEL:{a}->{b}"))
    position = {node: k for k, node in enumerate(seq) if 0 < k < m - 1}
    for k, node in enumerate(seq):
        if not 0 < k < m - 1 or inst.request_of(node) < 0:
            continue
        req = inst.requests[inst.request_of(node)]
        if req.max_ride is None or req.pickup != node or req.delivery not in position:
            continue
        limit = req.max_ride + inst.nodes[node].service
        arcs.append(Arc(k, position[req.delivery], limit, f"RIDE:{req.id}"))
    if vt.max_duration is not None:
        arcs.append(Arc(0, m - 1, vt.max_duration, "DURATION"))
    return z, arcs


def _timing_with(
    inst: Instance,
    vehicle_type: int,
    nodes: Sequence[int],
    rest_gap: int | None,
    driving: float,
    first_gap: int | None = None,
) -> RouteTiming:
    z, arcs = route_arcs(inst, vehicle_type, nodes, rest_gap=rest_gap, first_gap=first_gap)
    m = z
    n_vertices = m + 1
    to_zero, cycle = shortest_paths(n_vertices, arcs, z, to_root=True)
    if to_zero is None:
        cert = certificate(cycle)
        return RouteTiming(False, (), (), math.inf, cert, rest_gap, driving, math.nan, first_gap)
    from_zero, _ = shortest_paths(n_vertices, arcs, z, to_root=False)
    from_end, _ = shortest_paths(n_vertices, arcs, m - 1, to_root=False)
    assert from_zero is not None and from_end is not None
    earliest = tuple(-to_zero[k] for k in range(m))
    latest = tuple(from_zero[k] for k in range(m))
    shortest = -from_end[0]
    # Projected onto (t_0, t_end) the system keeps its difference form, so the
    # earliest finish minus the shortest duration is an admissible departure.
    departure = min(max(earliest[-1] - shortest, earliest[0]), latest[0])
    return RouteTiming(
        True, earliest, latest, shortest, None, rest_gap, driving, departure, first_gap
    )


def _timing_traffic(inst: Instance, vehicle_type: int, nodes: Sequence[int]) -> RouteTiming:
    """Exact timing under time-dependent travel (FIFO).

    The earliest schedule decides the windows; the first stop it reaches
    too late is the certificate. The shortest duration is the minimum over
    the departures at which the duration function can bend
    (:func:`mobiroute.vrp.traffic.duration_candidates`).
    """
    from mobiroute.vrp.traffic import arrive, backward, duration_candidates, forward

    vt = inst.vehicle_types[vehicle_type]
    profile = inst.profiles[vt.profile]
    speed = profile.speed
    assert speed is not None
    seq = [vt.start_depot, *nodes, vt.end_depot]
    e_all = [nd.earliest for nd in inst.nodes]
    s_all = [nd.service for nd in inst.nodes]
    start = inst.nodes[vt.start_depot]
    lo0 = max(start.earliest, vt.shift_start)
    lim = [inst.nodes[node].latest for node in seq]
    lim[0] = min(start.latest, vt.shift_end)
    lim[-1] = min(lim[-1], vt.shift_end)
    begin = forward(speed, seq, lo0, e_all, s_all, profile.time)
    driving = math.fsum(
        arrive(speed, begin[k] + s_all[a], profile.time[a][b]) - (begin[k] + s_all[a])
        for k, (a, b) in enumerate(pairwise(seq))
    )
    for k, (start_k, hi) in enumerate(zip(begin, lim, strict=True)):
        if start_k > hi + TIME_EPS:
            late_by = Infeasibility(round(start_k - hi, 6), (f"LATEST:{seq[k]}", "TRAFFIC"))
            return RouteTiming(False, (), (), math.inf, late_by, None, driving)
    latest = backward(speed, seq, lim, s_all, profile.time)
    options = [lo0, latest[0]] + [
        x
        for x in duration_candidates(speed, seq, e_all, s_all, profile.time)
        if lo0 <= x <= latest[0]
    ]
    # Shortest duration; among equally short departures the earliest one.
    shortest, departure = min(
        (forward(speed, seq, x, e_all, s_all, profile.time)[-1] - x, x) for x in options
    )
    if vt.max_duration is not None and shortest > vt.max_duration + TIME_EPS:
        over = Infeasibility(round(shortest - vt.max_duration, 6), ("DURATION", "TRAFFIC"))
        return RouteTiming(False, (), (), math.inf, over, None, driving)
    return RouteTiming(True, tuple(begin), tuple(latest), shortest, None, None, driving, departure)


def compact_schedule(inst: Instance, vehicle_type: int, nodes: Sequence[int]) -> RouteTiming:
    """The schedule a dispatcher would hand out: no idle start.

    The earliest schedule leaves the depot at the shift start and may wait an
    hour at the first window. This one leaves at :attr:`RouteTiming.departure`
    and is the earliest schedule from there: the shortest duration, and
    without traffic also the earliest return (both follow from the
    difference form of the constraints projected onto departure and
    return). ``earliest`` of the result holds these service starts; the
    other fields are those of :func:`route_timing`.
    """
    from mobiroute.vrp.traffic import forward

    timing = route_timing(inst, vehicle_type, nodes)
    if not timing.feasible or timing.departure <= timing.earliest[0]:
        return timing
    vt = inst.vehicle_types[vehicle_type]
    profile = inst.profiles[vt.profile]
    if profile.speed is not None:
        seq = [vt.start_depot, *nodes, vt.end_depot]
        e_all = [nd.earliest for nd in inst.nodes]
        s_all = [nd.service for nd in inst.nodes]
        starts = forward(profile.speed, seq, timing.departure, e_all, s_all, profile.time)
        return replace(timing, earliest=tuple(starts))
    z, arcs = route_arcs(
        inst, vehicle_type, nodes, rest_gap=timing.rest_gap, first_gap=timing.first_gap
    )
    arcs.append(Arc(0, z, -timing.departure, "DEPARTURE"))
    to_zero, _cycle = shortest_paths(z + 1, arcs, z, to_root=True)
    if to_zero is None:  # rounding at the boundary; the earliest schedule stays valid
        return timing
    return replace(timing, earliest=tuple(-to_zero[k] for k in range(z)))


def route_timing(inst: Instance, vehicle_type: int, nodes: Sequence[int]) -> RouteTiming:
    """Earliest and latest schedules and the shortest feasible duration.

    With a rest rule and more driving than it allows without a rest, every
    gap whose driving split is admissible is tried in order and the first
    one that admits a schedule is reported. If none does, the certificate is
    the one of the gap that misses by the fewest minutes; a route that
    drives more than twice the limit gets a ``DRIVING`` certificate.
    """
    vt = inst.vehicle_types[vehicle_type]
    if inst.profiles[vt.profile].speed is not None:
        return _timing_traffic(inst, vehicle_type, nodes)
    time = inst.profiles[vt.profile].time
    seq = [vt.start_depot, *nodes, vt.end_depot]
    legs = [time[a][b] for a, b in pairwise(seq)]
    driving = math.fsum(legs)
    rule = vt.breaks
    if rule is None or driving <= rule.max_driving + TIME_EPS:
        return _timing_with(inst, vehicle_type, nodes, None, driving)
    if driving > 2 * rule.max_driving + TIME_EPS:
        short = Infeasibility(round(driving - 2 * rule.max_driving, 6), ("DRIVING",))
        return RouteTiming(False, (), (), math.inf, short, None, driving)
    best: RouteTiming | None = None
    admissible: list[int] = []
    done = 0.0
    for k, leg in enumerate(legs):
        before, after = done, done + leg
        done = after
        if not any(
            driving - rule.max_driving - TIME_EPS <= x <= rule.max_driving + TIME_EPS
            for x in (before, after)
        ):
            continue
        admissible.append(k)
        timing = _timing_with(inst, vehicle_type, nodes, k, driving)
        if timing.feasible:
            return timing
        assert timing.infeasibility is not None
        if best is None or (
            best.infeasibility is not None
            and timing.infeasibility.short_by < best.infeasibility.short_by
        ):
            best = timing
    if best is None:  # no gap splits the driving (a single leg longer than the limit)
        short = Infeasibility(round(max(legs) - rule.max_driving, 6), ("DRIVING",))
        return RouteTiming(False, (), (), math.inf, short, None, driving)
    if rule.split is not None:
        # Two parts: the second goes where a whole break could go (the driving
        # counter resets only after it), the first in any earlier gap.
        for k in admissible:
            for first in range(k):
                timing = _timing_with(inst, vehicle_type, nodes, k, driving, first)
                if timing.feasible:
                    return timing
    return best


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
