"""Zone travel graph: shortest paths on the labelled synthetic matrix.

Not a live Moscow road network. Edges are the stored minute matrix;
``travel()`` returns the Floyd-Warshall closure so triangle inequality holds.
"""

from __future__ import annotations

INF = 10**9


def floyd_warshall(minutes: list[list[int]]) -> tuple[list[list[int]], list[list[int]]]:
    n = len(minutes)
    hop = [list(row) for row in minutes]
    nxt = [[(j if hop[i][j] < INF else -1) for j in range(n)] for i in range(n)]
    for i in range(n):
        if i < len(hop[i]):
            hop[i][i] = 0
            nxt[i][i] = i
    for k in range(n):
        for i in range(n):
            dik = hop[i][k]
            if dik >= INF:
                continue
            row_k = hop[k]
            row_i = hop[i]
            nxt_i = nxt[i]
            nxt_ik = nxt_i[k]
            for j in range(n):
                alt = dik + row_k[j]
                if alt < row_i[j]:
                    row_i[j] = alt
                    nxt_i[j] = nxt_ik
    return hop, nxt


def reconstruct_path(nxt: list[list[int]], i: int, j: int) -> list[int]:
    if not nxt or nxt[i][j] < 0:
        return []
    path = [i]
    cur = i
    guard = 0
    while cur != j:
        cur = nxt[cur][j]
        if cur < 0 or guard > len(nxt):
            return []
        path.append(cur)
        guard += 1
    return path
