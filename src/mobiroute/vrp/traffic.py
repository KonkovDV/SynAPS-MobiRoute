"""Time-dependent travel: speeds that change over the day.

The model is Ichoua, Gendreau & Potvin (2003): a road profile has a speed
factor per period of the day, and a trip that takes ``t`` minutes in free
flow progresses ``factor`` free-flow minutes per minute. Arrival time is then
a continuous, strictly increasing, piecewise-linear function of departure
time, so leaving later never means arriving earlier (FIFO). Two consequences
carry the rest of the module:

* for a fixed stop sequence the earliest schedule is still the best one for
  time windows: each service starts at ``max(e_k, arrive(prev departure))``;
* the latest start that keeps the rest of the route on time is computed
  backwards with the inverse function ``depart_by``.

So the insertion test of the static model carries over unchanged, with
``arrive``/``depart_by`` in place of ``+ t``/``- t`` (exact for windows).
What does not carry over is the closed-form shortest route duration: with a
shift cap the search uses a sound test (departing at the earliest or the
latest feasible time), while the verifier computes the exact minimum over
the finitely many departure times at which the duration function bends.
Time costs are charged on free-flow minutes.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Sequence
from typing import TYPE_CHECKING

from mobiroute.vrp.model import SpeedProfile

if TYPE_CHECKING:
    from mobiroute.vrp.insertion import Compiled, RouteState
    from mobiroute.vrp.model import Instance

EPS = 1e-9


def arrive(speed: SpeedProfile, depart: float, free_flow: float) -> float:
    """Arrival time of a trip of ``free_flow`` minutes leaving at ``depart``.

    Period ``k`` runs from ``starts[k]`` to ``starts[k+1]``; the first one
    also covers all earlier times and the last one all later times.
    """
    if free_flow <= 0.0:
        return depart
    starts, factors = speed.starts, speed.factors
    k = max(0, bisect.bisect_right(starts, depart) - 1)
    x, rest = depart, free_flow
    while k + 1 < len(starts):
        f = factors[k]
        room = (starts[k + 1] - x) * f
        if room >= rest:
            return x + rest / f
        rest -= room
        x = starts[k + 1]
        k += 1
    return x + rest / factors[k]


def depart_by(speed: SpeedProfile, arrive_at: float, free_flow: float) -> float:
    """Latest departure that arrives by ``arrive_at`` (inverse of :func:`arrive`)."""
    if free_flow <= 0.0 or math.isinf(arrive_at):
        return arrive_at
    starts, factors = speed.starts, speed.factors
    k = max(0, bisect.bisect_left(starts, arrive_at) - 1)
    x, rest = arrive_at, free_flow
    while k > 0:
        f = factors[k]
        room = (x - starts[k]) * f
        if room >= rest:
            return x - rest / f
        rest -= room
        x = starts[k]
        k -= 1
    return x - rest / factors[0]


def forward(
    speed: SpeedProfile,
    seq: Sequence[int],
    depart: float,
    e: Sequence[float],
    s: Sequence[float],
    time: Sequence[Sequence[float]],
) -> list[float]:
    """Earliest service starts along ``seq`` when leaving ``seq[0]`` at ``depart``."""
    out = [depart]
    for k in range(1, len(seq)):
        a, b = seq[k - 1], seq[k]
        arr = arrive(speed, out[-1] + s[a], time[a][b])
        out.append(arr if arr > e[b] else e[b])
    return out


def backward(
    speed: SpeedProfile,
    seq: Sequence[int],
    lim: Sequence[float],
    s: Sequence[float],
    time: Sequence[Sequence[float]],
) -> list[float]:
    """Latest service starts along ``seq`` that keep every later stop on time."""
    late = [0.0] * len(seq)
    late[-1] = lim[-1]
    for k in range(len(seq) - 2, -1, -1):
        a, b = seq[k], seq[k + 1]
        back = depart_by(speed, late[k + 1], time[a][b]) - s[a]
        late[k] = lim[k] if lim[k] < back else back
    return late


def duration_candidates(
    speed: SpeedProfile,
    seq: Sequence[int],
    e: Sequence[float],
    s: Sequence[float],
    time: Sequence[Sequence[float]],
) -> list[float]:
    """Departure times at which the route's duration function can bend.

    The arrival at the end is a piecewise-linear function of the departure;
    it bends only where some service start meets its window opening, or a
    leg starts or ends on a speed-period boundary. Each such event, mapped
    back to the depot as if nobody waited before it, is a candidate (where
    somebody does wait, later events do not move with the departure and
    cannot bend the function). The minimum duration over an interval of
    departures is therefore at a candidate or at an end point.
    """
    bounds = speed.starts[1:]
    out: list[float] = []
    for k in range(len(seq)):
        events: list[float] = []
        if k > 0:
            events.append(e[seq[k]])
            events += bounds  # the leg into k ends on a boundary
        if k < len(seq) - 1:
            events += [b - s[seq[k]] for b in bounds]  # the leg out of k starts on one
        for x in events:
            t = x
            for j in range(k, 0, -1):
                a, b = seq[j - 1], seq[j]
                t = depart_by(speed, t, time[a][b]) - s[a]
            if math.isfinite(t):
                out.append(t)
    return out


def route_ok(c: Compiled, t: int, nodes: Sequence[int]) -> bool:
    """Feasibility of a fixed sequence under time-dependent travel (search side).

    Windows are decided exactly by the earliest schedule. A shift cap is
    tested soundly: the route passes if leaving at the earliest or at the
    latest on-time departure keeps it within the cap (both are schedules);
    the verifier checks the exact minimum.
    """
    speed = c.speed[t]
    assert speed is not None
    seq = [c.start[t], *nodes, c.end[t]]
    time = c.time[t]
    lim = [c.l[node] for node in seq]
    lim[0] = c.start_lim[t]
    lim[-1] = c.end_lim[t]
    begin = forward(speed, seq, c.t_min[t], c.e, c.s, time)
    if any(b > hi + EPS for b, hi in zip(begin, lim, strict=True)):
        return False
    cap = c.max_dur[t]
    if cap == math.inf:
        return True
    if begin[-1] - begin[0] <= cap + EPS:
        return True
    latest = backward(speed, seq, lim, c.s, time)[0]
    late_run = forward(speed, seq, latest, c.e, c.s, time)
    return late_run[-1] - latest <= cap + EPS


def candidates(
    c: Compiled,
    st: RouteState,
    r: int,
    fits: list[bool],
    extra: float,
    positions: Sequence[int],
) -> list[tuple[float, int, int]]:
    """Every insertion of request ``r`` that keeps the windows (search side).

    The static scan of :mod:`mobiroute.vrp.insertion` with ``arrive`` in
    place of adding a travel time; ``positions`` are the admissible spots of
    a single-node order (trip loads). The shift cap is left to the exact
    check that follows.
    """
    t = st.t
    speed = c.speed[t]
    assert speed is not None
    seq, begin, late = st.seq, st.begin, st.late
    time, cost = c.time[t], c.cost[t]
    e, lat, s = c.e, c.l, c.s
    p, d = c.pick[r], c.deliv[r]
    m = len(seq) - 2
    out: list[tuple[float, int, int]] = []
    if p < 0 or d < 0:
        u = p if p >= 0 else d
        for i in positions:
            a, b = seq[i], seq[i + 1]
            arr = arrive(speed, begin[i] + s[a], time[a][u])
            bu = arr if arr > e[u] else e[u]
            if bu > lat[u] + EPS:
                continue
            if arrive(speed, bu + s[u], time[u][b]) > late[i + 1] + EPS:
                continue
            out.append(((cost[a][u] + cost[u][b] - cost[a][b]) + extra, i, i))
        return out
    for i in range(m + 1):
        if not fits[i]:
            continue
        a, b = seq[i], seq[i + 1]
        arr = arrive(speed, begin[i] + s[a], time[a][p])
        bp = arr if arr > e[p] else e[p]
        if bp > lat[p] + EPS:
            continue
        arr_d = arrive(speed, bp + s[p], time[p][d])
        bd = arr_d if arr_d > e[d] else e[d]
        if bd <= lat[d] + EPS and arrive(speed, bd + s[d], time[d][b]) <= late[i + 1] + EPS:
            out.append(((cost[a][p] + cost[p][d] + cost[d][b] - cost[a][b]) + extra, i, i))
        detour_p = cost[a][p] + cost[p][b] - cost[a][b]
        tcur = arrive(speed, bp + s[p], time[p][b])
        for j in range(i + 1, m + 1):
            cj = seq[j]
            bj = tcur if tcur > e[cj] else e[cj]
            if bj > lat[cj] + EPS or not fits[j]:
                break
            nx = seq[j + 1]
            arr_d = arrive(speed, bj + s[cj], time[cj][d])
            bd = arr_d if arr_d > e[d] else e[d]
            if bd <= lat[d] + EPS and arrive(speed, bd + s[d], time[d][nx]) <= late[j + 1] + EPS:
                out.append((detour_p + (cost[cj][d] + cost[d][nx] - cost[cj][nx]) + extra, i, j))
            tcur = arrive(speed, bj + s[cj], time[cj][nx])
    return out


#: Two rush hours: 07:30-10:00 at 55% of free-flow speed, 17:00-19:30 at 60%.
RUSH_HOURS = SpeedProfile(
    starts=(0.0, 450.0, 600.0, 1020.0, 1170.0), factors=(1.0, 0.55, 1.0, 0.6, 1.0)
)


def with_traffic(inst: Instance, speed: SpeedProfile = RUSH_HOURS) -> Instance:
    """Copy of ``inst`` whose every road profile follows ``speed``."""
    from dataclasses import replace

    profiles = {name: replace(p, speed=speed) for name, p in inst.profiles.items()}
    return replace(inst, profiles=profiles, name=inst.name + "-traffic")


def lateness(inst: Instance, vehicle_type: int, nodes: Sequence[int]) -> list[float]:
    """Minutes late at every stop when the route is driven as early as possible.

    Diagnostic for plans made on free-flow times: the earliest schedule is
    propagated through late stops instead of stopping at the first one.
    """
    vt = inst.vehicle_types[vehicle_type]
    profile = inst.profiles[vt.profile]
    speed = profile.speed or SpeedProfile((0.0,), (1.0,))
    seq = [vt.start_depot, *nodes, vt.end_depot]
    e_all = [nd.earliest for nd in inst.nodes]
    s_all = [nd.service for nd in inst.nodes]
    lo0 = max(inst.nodes[vt.start_depot].earliest, vt.shift_start)
    begin = forward(speed, seq, lo0, e_all, s_all, profile.time)
    lim = [inst.nodes[node].latest for node in seq]
    lim[-1] = min(lim[-1], vt.shift_end)
    return [max(0.0, b - hi) for b, hi in zip(begin, lim, strict=True)]
