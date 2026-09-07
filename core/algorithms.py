"""Algorithm core for the Delivery Command Center.

Every function here is deliberately *pure* (no I/O, no globals) and annotated with
its asymptotic complexity and a short correctness argument, so it can be defended
directly in a Design & Analysis of Algorithms report.

Algorithms implemented:
  - ``knapsack_01``  : exact 0/1 knapsack by dynamic programming, O(n * W).
  - ``dijkstra``     : single-source shortest paths on a weighted graph, O((V+E) log V).
  - ``shortest_path``: reconstruction of one concrete shortest path.
  - ``tsp_held_karp``: exact symmetric TSP (return-to-start tour) by DP over subsets,
                       O(n^2 2^n), with an optional additive *position cost* hook that
                       is how delivery priority is priced into the objective.
  - ``tsp_nearest_neighbor_2opt``: fast O(n^2)-style approximation used when the tour
                       is too large for the DP, or when a fast re-plan is wanted.
"""
from __future__ import annotations

import heapq
from typing import Callable, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "knapsack_01",
    "dijkstra",
    "shortest_path",
    "tsp_held_karp",
    "tsp_nearest_neighbor_2opt",
    "tour_cost",
]


# --------------------------------------------------------------------------- #
# 0/1 Knapsack — exact dynamic programming                                    #
# --------------------------------------------------------------------------- #
def knapsack_01(
    weights: Sequence[int], values: Sequence[int], capacity: int
) -> Dict[str, object]:
    """Solve the 0/1 knapsack problem exactly.

    Given ``n`` items each with an integer ``weight`` and integer ``value`` and a
    knapsack of integer ``capacity``, choose a subset whose total weight is at most
    ``capacity`` and whose total value is maximum.

    **Recurrence** (let ``V[i][c]`` = best value using the first ``i`` items and a
    knapsack of capacity ``c``)::

        V[0][c]   = 0
        V[i][c]   = V[i-1][c]                                   if w_i > c
        V[i][c]   = max(V[i-1][c], v_i + V[i-1][c - w_i])       otherwise

    **Complexity:** O(n * W) time, O(n * W) space for the DP table used to
    reconstruct the chosen subset.

    **Correctness:** by induction, ``V[i][c]`` is optimal for the first ``i`` items:
    item ``i`` is either excluded (first term) or included only if it fits and then
    only improves on the optimum for the remaining capacity (second term).

    Args:
        weights:  item weights (non-negative ints).
        values:   item values (non-negative ints).
        capacity: knapsack capacity (non-negative int).

    Returns:
        dict with keys ``max_value`` (best achievable value),
        ``total_weight`` (weight of the chosen subset) and
        ``indices`` (sorted list of chosen item indices).
    """
    n = len(weights)
    cap = capacity
    if n == 0 or cap <= 0:
        return {"max_value": 0, "total_weight": 0, "indices": []}

    # dp[i][c] keeps the table row after considering items [0 .. i-1].
    dp: List[List[int]] = [[0] * (cap + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        w, v = weights[i - 1], values[i - 1]
        row_prev, row_cur = dp[i - 1], dp[i]
        for c in range(cap + 1):
            if w > c:
                row_cur[c] = row_prev[c]
            else:
                take = v + row_prev[c - w]
                row_cur[c] = take if take > row_prev[c] else row_prev[c]

    # Reconstruct the subset by walking the table backwards.
    chosen: List[int] = []
    c = cap
    for i in range(n, 0, -1):
        if dp[i][c] != dp[i - 1][c]:  # item i-1 was taken
            chosen.append(i - 1)
            c -= weights[i - 1]
    chosen.reverse()
    total_weight = sum(weights[i] for i in chosen)
    return {"max_value": dp[n][cap], "total_weight": total_weight, "indices": chosen}


# --------------------------------------------------------------------------- #
# Dijkstra — single source shortest paths                                     #
# --------------------------------------------------------------------------- #
def dijkstra(
    adj: Sequence[Sequence[Tuple[int, float]]], start: int
) -> Tuple[List[float], List[Optional[int]]]:
    """Single-source shortest paths (Dijkstra) on a non-negative weighted graph.

    ``adj[u]`` is a list of ``(v, weight)`` neighbours. Returns ``(dist, prev)``
    where ``dist[v]`` is the shortest distance from ``start`` to ``v`` and
    ``prev[v]`` is the predecessor of ``v`` on such a path (``None`` for ``start``,
    and for nodes that are unreachable).

    **Complexity:** O((V + E) log V) with a binary heap (each edge relaxed once,
    each vertex popped once).

    **Correctness:** classic greedy invariant — when a vertex is popped from the
    heap its tentative distance is final, because all edge weights are non-negative
    so no later, longer path can improve it.
    """
    n = len(adj)
    INF = float("inf")
    dist = [INF] * n
    prev: List[Optional[int]] = [None] * n
    dist[start] = 0.0
    pq: List[Tuple[float, int]] = [(0.0, start)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist[u]:  # stale entry
            continue
        for v, w in adj[u]:
            nd = d + w
            if nd < dist[v] - 1e-12:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    return dist, prev


def shortest_path(
    adj: Sequence[Sequence[Tuple[int, float]]], start: int, end: int
) -> Tuple[float, List[int]]:
    """Shortest path from ``start`` to ``end`` as a list of node ids.

    Returns ``(distance, path)``. The path always starts at ``start``; if ``end`` is
    unreachable a ``ValueError`` is raised.
    """
    dist, prev = dijkstra(adj, start)
    if dist[end] == float("inf"):
        raise ValueError(f"node {end} unreachable from {start}")
    path: List[int] = []
    cur = end
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    return dist[end], path


# --------------------------------------------------------------------------- #
# Exact TSP — Held–Karp dynamic program over subsets                          #
# --------------------------------------------------------------------------- #
# Optional hook: node_cost(node, position) returns an extra additive cost for
# visiting ``node`` as the ``position``-th stop (1-based). Because ``position`` is
# exactly the number of already-visited stops + 1, i.e. the popcount of the subset
# mask, the term is a function of the DP *state* alone and the recurrence stays
# perfectly exact. This is how delivery priority prices "how late in the run a stop
# happens".
NodeCost = Callable[[int, int], float]


def tsp_held_karp(
    matrix: Sequence[Sequence[float]],
    start: int = 0,
    home: Optional[int] = None,
    node_cost: Optional[NodeCost] = None,
    return_to_start: bool = True,
) -> Tuple[float, List[int]]:
    """Solve symmetric TSP *exactly* with the Held–Karp DP.

    Visits every node except ``start`` exactly once and, by default, returns to
    ``start`` (a closed tour). Returns ``(best_cost, order)`` where ``order`` lists
    the visited nodes in the order they are reached.

    ``home`` optionally names a *different* finish node than ``start`` (used when a
    mid-run re-plan starts at the van's current position but must still come back to
    the depot); ``return_to_start`` is shorthand for ``home = start`` and is kept
    for backwards compatibility.

    With ``others`` = the n-1 non-start nodes, define ``m = |others|`` and let
    ``dp[mask][k]`` = minimum cost of a path that starts at ``start``, visits
    exactly the set ``mask`` (bit ``k`` set ⇔ ``others[k]`` visited) and ends at
    ``others[k]``.

    **Recurrence** (``c(mask)`` = popcount of mask)::

        dp[{k}][k]        = d(start, others[k]) + cost(others[k], 1)
        dp[mask | {j}][j] = min_k dp[mask][k] + d(others[k], others[j])
                            + cost(others[j], c(mask) + 1)

    and the route closes with ``min_k dp[full][k] + d(others[k], home)``.

    **Complexity:** O(m^2 2^m) time, O(m 2^m) space. Since m = n-1 this is the
    standard O(n^2 2^n) TSP DP — exponential, exact, and ideal for the small
    stop-counts of a real delivery run.

    **Correctness:** an optimal route restricted to a prefix ending at ``k`` must
    itself be optimal for its subset and endpoint (otherwise swap in the better
    prefix and improve the whole route), so the DP is exact.

    Args:
        matrix: n x n symmetric distance (time) matrix between nodes.
        start: the node the route starts from (e.g. the van's current position).
        home: the node the route must end at (e.g. the depot). Defaults to ``start``.
        node_cost: optional ``cost(node, position)`` additive term.
        return_to_start: kept for compatibility; True ⇔ ``home = start``.

    Returns:
        ``(best_cost, order)``.
    """
    if home is None:
        home = start
    if not return_to_start:
        home = start  # backward-compat: no-return meant "finish at start"
    n = len(matrix)
    if n == 0:
        return 0.0, []
    others = [i for i in range(n) if i != start and i != home]
    m = len(others)
    if m == 0:
        return 0.0, []
    if n == 1:
        return 0.0, []

    INF = float("inf")
    full = (1 << m) - 1
    size = 1 << m
    dp = [[INF] * m for _ in range(size)]
    parent = [[(-1, -1)] * m for _ in range(size)]

    # seed: single-step paths start -> others[k]
    for k in range(m):
        extra = node_cost(others[k], 1) if node_cost else 0.0
        dp[1 << k][k] = matrix[start][others[k]] + extra

    for mask in range(size):
        visited = mask.bit_count()
        for k in range(m):
            cur = dp[mask][k]
            if cur == INF:
                continue
            for j in range(m):
                if (mask >> j) & 1:
                    continue
                extra = node_cost(others[j], visited + 1) if node_cost else 0.0
                nmask = mask | (1 << j)
                cand = cur + matrix[others[k]][others[j]] + extra
                if cand < dp[nmask][j] - 1e-12:
                    dp[nmask][j] = cand
                    parent[nmask][j] = (mask, k)

    # close the route back at home
    best_last, best = -1, INF
    for k in range(m):
        cand = dp[full][k] + matrix[others[k]][home]
        if cand < best - 1e-12:
            best, best_last = cand, k

    if best_last == -1:
        raise ValueError("TSP instance could not be solved")

    # reconstruct order (walk parents backwards; single-bit seed states have no
    # recorded parent, so stop when the parent marker is -1)
    order_rev: List[int] = []
    mask, k = full, best_last
    while True:
        order_rev.append(others[k])
        pm, pk = parent[mask][k]
        if pm == -1:
            break
        mask, k = pm, pk
    order_rev.reverse()
    return best, order_rev


# --------------------------------------------------------------------------- #
# Approximate TSP — nearest neighbour + 2-opt improvement                     #
# --------------------------------------------------------------------------- #
def tsp_nearest_neighbor_2opt(
    matrix: Sequence[Sequence[float]],
    start: int = 0,
    home: Optional[int] = None,
    improvement_passes: int = 8,
) -> Tuple[float, List[int]]:
    """Fast approximation for symmetric TSP: nearest neighbour + 2-opt.

    Nearest neighbour greedily builds a route (always polynomial, O(n^2)); a local
    search then repeatedly applies the classic **2-opt** move — reverse a contiguous
    block of the route when the two edges ``(a,b),(c,d)`` can be replaced by the
    non-crossing pair ``(a,c),(b,d)`` with a saving::

        gain = d(a,b) + d(c,d) - d(a,c) - d(b,d)     # > 0 ⇒ improvement

    The route starts at ``start`` and ends at ``home`` (default ``start`` ⇒ closed
    tour). Endpoints are fixed during 2-opt, so the heuristic works for mid-run
    re-planning where the van is *not* at the depot. A single 2-opt pass is O(n^2);
    the routine runs up to ``improvement_passes`` passes. The result is not
    guaranteed optimal so it is used as an *approximation* — the UI/report compare
    it against the exact Held–Karp result.

    Returns ``(cost, order)`` where ``order`` is the visited-node sequence
    (excluding ``start`` and ``home``).
    """
    n = len(matrix)
    if n <= 1:
        return 0.0, []
    if home is None:
        home = start
    fixed = {start, home} if home != start else {start}
    others = [i for i in range(n) if i not in fixed]

    # --- nearest neighbour ---
    seq: List[int] = [start]
    unvisited = set(others)
    cur = start
    while unvisited:
        nxt = min(unvisited, key=lambda j: matrix[cur][j])
        seq.append(nxt)
        unvisited.remove(nxt)
        cur = nxt
    seq.append(home)

    # --- 2-opt on the path seq[0]=start .. seq[-1]=home (endpoints fixed) ---
    L = len(seq)

    def gain(i: int, k: int) -> float:
        # reverse segment seq[i..k]; new edges (seq[i-1], seq[k]) & (seq[i], seq[k+1])
        a, b, c, d = seq[i - 1], seq[i], seq[k], seq[k + 1]
        return matrix[a][b] + matrix[c][d] - matrix[a][c] - matrix[b][d]

    for _ in range(max(1, improvement_passes)):
        improved = False
        for i in range(1, L - 1):
            for k in range(i, L - 1):
                if k > i and gain(i, k) > 1e-9:
                    seq[i : k + 1] = reversed(seq[i : k + 1])
                    improved = True
        if not improved:
            break

    order = seq[1:-1]
    cost = sum(matrix[seq[i]][seq[i + 1]] for i in range(L - 1))
    return cost, order


def tour_cost(
    matrix: Sequence[Sequence[float]],
    order: Sequence[int],
    return_to_start: bool = True,
    start: int = 0,
) -> float:
    """Total travel cost of visiting ``order`` starting from ``start`` (and, by
    default, coming back to ``start``)."""
    total = matrix[start][order[0]] if order else 0.0
    for a, b in zip(order, order[1:]):
        total += matrix[a][b]
    if return_to_start and order:
        total += matrix[order[-1]][start]
    return total
