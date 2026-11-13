"""Local search for routes of deliveries from the depot (VRPTW).

Ruin-and-recreate moves orders one at a time and never reverses a stretch
of a route, so long routes (Solomon's R2 and RC2: two or three vehicles for
a hundred customers) keep crossings that one 2-opt move would remove. This
module adds the classic neighbourhoods, evaluated in constant time:

* relocate one customer next to a neighbour (same or another route);
* swap two customers of different routes;
* 2-opt* - exchange the tails of two routes;
* 2-opt - reverse a stretch of one route.

Time windows are checked by concatenating *segments* (Kindervater &
Savelsbergh 1997; Vidal, Crainic, Gendreau & Prins 2013): a stop sequence is
summarised by its shortest duration ``D``, its time warp ``TW`` (zero iff it
can be timed without lateness), and the earliest and latest feasible start
``E``, ``L`` of its first service. For ``A`` followed by ``B`` with travel
``t`` from the last stop of ``A`` to the first of ``B``::

    delta = D_A - TW_A + t
    wait  = max(E_B - delta - L_A, 0)
    warp  = max(E_A + delta - L_B, 0)
    D  = D_A + D_B + t + wait          TW = TW_A + TW_B + warp
    E  = max(E_B - delta, E_A) - wait  L  = min(L_B - delta, L_A) + warp

Prefix and suffix segments of every route make any move made of three
pieces an ``O(1)`` test. Loads are prefix sums (every order rides from the
depot). Only moves to one of the ``neighbours`` nearest customers are tried
(granular neighbourhoods, Toth & Vigo 2003). The search applies to
instances whose orders are all deliveries from the depot and that use no
reload stops or rest rules; between routes it moves customers only across
routes of the same vehicle type.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from mobiroute.vrp.insertion import EPS, Compiled
from mobiroute.vrp.solution import Route, Solution

#: (duration, time warp, earliest start, latest start, first node, last node)
Seg = tuple[float, float, float, float, int, int]


def applies(c: Compiled) -> bool:
    """Whether every order is a depot delivery and no extended rule is in play."""
    return (
        all(p < 0 for p in c.pick)
        and not c.has_reload
        and all(math.isinf(x) for x in c.brk_drive)
        and not c.has_ride
        and not c.has_traffic
    )


class LocalSearch:
    """First-improvement descent over the four neighbourhoods."""

    def __init__(self, c: Compiled, *, neighbours: int = 20, max_passes: int = 50) -> None:
        self.c = c
        self.max_passes = max_passes
        inst = c.inst
        customers = [n for r in range(inst.n_requests) for n in (c.deliv[r],)]
        cost0 = c.cost[0]
        self.near = {
            u: [v for _, v in sorted((cost0[u][v] + cost0[v][u], v) for v in customers if v != u)][
                :neighbours
            ]
            for u in customers
        }
        self.symmetric = [
            all(m[a][b] == m[b][a] for a in range(c.n) for b in range(a + 1, c.n)) for m in c.cost
        ]

    # -- segments ----------------------------------------------------------
    def _node(self, t: int, node: int, k: int, last: int) -> Seg:
        c = self.c
        if k == 0:
            return (0.0, 0.0, c.t_min[t], c.start_lim[t], node, node)
        if k == last:
            return (0.0, 0.0, c.e[node], c.end_lim[t], node, node)
        return (c.s[node], 0.0, c.e[node], c.l[node], node, node)

    @staticmethod
    def _cat(a: Seg, b: Seg, time: Sequence[Sequence[float]]) -> Seg:
        d1, tw1, e1, l1, f1, z1 = a
        d2, tw2, e2, l2, f2, z2 = b
        tt = time[z1][f2]
        delta = d1 - tw1 + tt
        wait = e2 - delta - l1
        wait = wait if wait > 0.0 else 0.0
        warp = e1 + delta - l2
        warp = warp if warp > 0.0 else 0.0
        e = e2 - delta if e2 - delta > e1 else e1
        lat = l2 - delta if l2 - delta < l1 else l1
        return (d1 + d2 + tt + wait, tw1 + tw2 + warp, e - wait, lat + warp, f1, z2)

    def _build(self, t: int, nodes: list[int]) -> tuple[list[Seg], list[Seg], list[float]]:
        c = self.c
        seq = [c.start[t], *nodes, c.end[t]]
        last = len(seq) - 1
        time = c.time[t]
        segs = [self._node(t, node, k, last) for k, node in enumerate(seq)]
        pre = [segs[0]]
        for k in range(1, last + 1):
            pre.append(self._cat(pre[-1], segs[k], time))
        suf = [segs[last]]
        for k in range(last - 1, -1, -1):
            suf.append(self._cat(segs[k], suf[-1], time))
        suf.reverse()
        load = [0.0]
        for node in nodes:
            load.append(load[-1] + c.demand[c.node_req[node]][0])
        return pre, suf, load

    def _ok(self, t: int, seg: Seg) -> bool:
        return seg[1] <= EPS and seg[0] <= self.c.max_dur[t] + EPS

    def _fits(self, t: int, load: float) -> bool:
        return load <= self.c.cap[t][0] + EPS

    # -- the search --------------------------------------------------------
    def improve(self, sol: Solution) -> Solution:
        c = self.c
        if c.dims != 1:
            return sol
        routes = [Route(r.vehicle_type, list(r.nodes)) for r in sol.routes if r.nodes]
        data = [self._build(r.vehicle_type, r.nodes) for r in routes]
        where: dict[int, tuple[int, int]] = {}

        def index() -> None:
            where.clear()
            for ri, r in enumerate(routes):
                for k, node in enumerate(r.nodes, start=1):
                    where[node] = (ri, k)

        index()
        improved_any = False
        for _ in range(self.max_passes):
            improved = False
            for u in sorted(where):
                if u not in where:
                    continue
                for v in self.near.get(u, ()):
                    if v not in where or u not in where:
                        continue
                    move = self._best_move(routes, data, where, u, v)
                    if move is None:
                        continue
                    for ri, nodes in move:
                        routes[ri] = Route(routes[ri].vehicle_type, nodes)
                        data[ri] = self._build(routes[ri].vehicle_type, nodes)
                    index()
                    improved = improved_any = True
            if not improved:
                break
        if not improved_any:
            return sol
        kept = [r for r in routes if r.nodes]
        return Solution(kept, set(sol.unassigned))

    def _arc(self, t: int, a: int, b: int) -> float:
        return self.c.cost[t][a][b]

    def _best_move(
        self,
        routes: list[Route],
        data: list[tuple[list[Seg], list[Seg], list[float]]],
        where: dict[int, tuple[int, int]],
        u: int,
        v: int,
    ) -> list[tuple[int, list[int]]] | None:
        """First improving move that puts ``u`` next to ``v`` (or exchanges tails)."""
        c = self.c
        ru, iu = where[u]
        rv, iv = where[v]
        tu, tv = routes[ru].vehicle_type, routes[rv].vehicle_type
        if ru != rv and tu != tv:
            return None
        t = tu
        time = c.time[t]
        nu, nv = routes[ru].nodes, routes[rv].nodes
        seq_u = [c.start[t], *nu, c.end[t]]
        seq_v = [c.start[tv], *nv, c.end[tv]]
        pre_u, suf_u, load_u = data[ru]
        pre_v, suf_v, load_v = data[rv]
        q = c.demand[c.node_req[u]][0]
        open_u = c.open_cost[t] if len(nu) == 1 else 0.0
        arc = self._arc
        su = self._node(t, u, iu, len(seq_u) - 1)
        if ru != rv:
            # Relocate u after v.
            gain = (
                arc(t, seq_u[iu - 1], u)
                + arc(t, u, seq_u[iu + 1])
                - arc(t, seq_u[iu - 1], seq_u[iu + 1])
                + open_u
            )
            add = arc(t, v, u) + arc(t, u, seq_v[iv + 1]) - arc(t, v, seq_v[iv + 1])
            if add < gain - 1e-9 and self._fits(t, load_v[-1] + q):
                new_v = self._cat(self._cat(pre_v[iv], su, time), suf_v[iv + 1], time)
                rest_u = self._cat(pre_u[iu - 1], suf_u[iu + 1], time)
                if self._ok(t, new_v) and self._ok(t, rest_u):
                    return [
                        (ru, [*nu[: iu - 1], *nu[iu:]]),
                        (rv, [*nv[:iv], u, *nv[iv:]]),
                    ]
            # Relocate u before v.
            add = arc(t, seq_v[iv - 1], u) + arc(t, u, v) - arc(t, seq_v[iv - 1], v)
            if add < gain - 1e-9 and self._fits(t, load_v[-1] + q):
                new_v = self._cat(self._cat(pre_v[iv - 1], su, time), suf_v[iv], time)
                rest_u = self._cat(pre_u[iu - 1], suf_u[iu + 1], time)
                if self._ok(t, new_v) and self._ok(t, rest_u):
                    return [
                        (ru, [*nu[: iu - 1], *nu[iu:]]),
                        (rv, [*nv[: iv - 1], u, *nv[iv - 1 :]]),
                    ]
            # Swap u and v.
            qv = c.demand[c.node_req[v]][0]
            sv = self._node(t, v, iv, len(seq_v) - 1)
            delta = (
                arc(t, seq_u[iu - 1], v)
                + arc(t, v, seq_u[iu + 1])
                - arc(t, seq_u[iu - 1], u)
                - arc(t, u, seq_u[iu + 1])
                + arc(t, seq_v[iv - 1], u)
                + arc(t, u, seq_v[iv + 1])
                - arc(t, seq_v[iv - 1], v)
                - arc(t, v, seq_v[iv + 1])
            )
            if (
                delta < -1e-9
                and self._fits(t, load_u[-1] - q + qv)
                and self._fits(t, load_v[-1] - qv + q)
            ):
                new_u = self._cat(self._cat(pre_u[iu - 1], sv, time), suf_u[iu + 1], time)
                new_v = self._cat(self._cat(pre_v[iv - 1], su, time), suf_v[iv + 1], time)
                if self._ok(t, new_u) and self._ok(t, new_v):
                    a, b = list(nu), list(nv)
                    a[iu - 1], b[iv - 1] = v, u
                    return [(ru, a), (rv, b)]
            # 2-opt*: u -> succ(v) and v -> succ(u).
            delta = (
                arc(t, u, seq_v[iv + 1])
                + arc(t, v, seq_u[iu + 1])
                - arc(t, u, seq_u[iu + 1])
                - arc(t, v, seq_v[iv + 1])
            )
            new_u_nodes = [*nu[:iu], *nv[iv:]]
            new_v_nodes = [*nv[:iv], *nu[iu:]]
            freed = (c.open_cost[t] if not new_u_nodes else 0.0) + (
                c.open_cost[t] if not new_v_nodes else 0.0
            )
            if delta - freed < -1e-9:
                load_a = load_u[iu] + (load_v[-1] - load_v[iv])
                load_b = load_v[iv] + (load_u[-1] - load_u[iu])
                if self._fits(t, load_a) and self._fits(t, load_b):
                    new_u = self._cat(pre_u[iu], suf_v[iv + 1], time)
                    new_v = self._cat(pre_v[iv], suf_u[iu + 1], time)
                    if self._ok(t, new_u) and self._ok(t, new_v):
                        return [(ru, new_u_nodes), (rv, new_v_nodes)]
            return None
        # Same route: 2-opt making u adjacent to v (reverse the stretch between).
        if abs(iu - iv) < 2:
            return None
        i, j = (iu, iv) if iu < iv else (iv, iu)
        # Reverse positions i+1..j so that seq[i] is followed by seq[j].
        pa, pb = seq_u[i], seq_u[i + 1]
        qx, qy = seq_u[j], seq_u[j + 1]
        delta = arc(t, pa, qx) + arc(t, pb, qy) - arc(t, pa, pb) - arc(t, qx, qy)
        if not self.symmetric[t]:
            for k in range(i + 1, j):
                delta += arc(t, seq_u[k + 1], seq_u[k]) - arc(t, seq_u[k], seq_u[k + 1])
        if delta >= -1e-9:
            return None
        last = len(seq_u) - 1
        rev = self._node(t, seq_u[j], j, last)
        for k in range(j - 1, i, -1):
            rev = self._cat(rev, self._node(t, seq_u[k], k, last), time)
        whole = self._cat(self._cat(pre_u[i], rev, time), suf_u[j + 1], time)
        if not self._ok(t, whole):
            return None
        nodes = [*nu[:i], *reversed(nu[i:j]), *nu[j:]]
        return [(ru, nodes)]
