"""Planning layer: turn the raw city data into a load plan and a stop order.

This is where the *objective functions* live, so it is the most report-relevant
file. Two linked decisions are made:

1. **Loading (0/1 knapsack).** Every item has a base *value*; a manager-adjustable
   *priority premium* adds ``premium * (3 - priority)`` so critical goods win ties.
2. **Sequencing (priority-aware TSP).** Route cost is
   ``travel + strictness * Σ p_weight(stop) * position(stop)`` — pushing a
   high-priority stop late in the run costs more. Because ``position`` is known per
   DP state, Held–Karp solves this objective exactly.

All travel times are shortest-road-path minutes computed with Dijkstra over the
(possibly disrupted) road network, so a closed bridge or traffic jam really changes
the numbers.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set

from . import algorithms as alg
from .city import City

# Priority tier -> weight used when sequencing (higher tier must be earlier).
PRIO_WEIGHT: Dict[int, int] = {1: 3, 2: 2, 3: 1}


# --------------------------------------------------------------------------- #
# Loading decision
# --------------------------------------------------------------------------- #
def item_score(item: dict, premium: float) -> float:
    """Effective value of one item under a priority premium."""
    return item["value"] + premium * (3 - item["priority"])


def plan_load(city: City, capacity: int, premium: float,
              excluded: Optional[Set[str]] = None) -> dict:
    """Fill the van with a 0/1-knapsack subset of the item catalogue.

    Returns a dict with the chosen/skipped items, totals and which stops would get
    deliveries (so the manager sees load and route as one decision).
    """
    excluded = excluded or set()
    refs = [it for it in city.items if it["id"] not in excluded]
    weights = [it["weight"] for it in refs]
    values = [item_score(it, premium) for it in refs]
    res = alg.knapsack_01(weights, values, int(capacity))

    chosen_ids = {refs[i]["id"] for i in res["indices"]}
    chosen = [it for it in refs if it["id"] in chosen_ids]
    skipped = [it for it in refs if it["id"] not in chosen_ids]

    stop_counts: Dict[str, int] = {}
    for it in chosen:
        stop_counts[it["to"]] = stop_counts.get(it["to"], 0) + 1

    return {
        "chosen": chosen,
        "skipped": skipped,
        "total_value": round(res["max_value"], 1),
        "total_weight": res["total_weight"],
        "capacity": int(capacity),
        "fill_pct": round(100.0 * res["total_weight"] / capacity, 1) if capacity else 0.0,
        "chosen_stop_counts": stop_counts,
    }


def select_route_stops(city: City, loaded_ids: Sequence[str], scope: str) -> List[str]:
    """Which stops a route should visit, depending on the manager's scope choice."""
    if scope == "all":
        return list(city.stop_ids)
    if scope == "critical":
        # every stop that has at least one P1/P2 item loaded, plus all P1 stops
        want = {s for s in loaded_ids if city.stops[s]["priority"] <= 2}
        want |= {s for s in city.stop_ids if city.stops[s]["priority"] == 1}
        order = [s for s in city.stop_ids if s in want]
        return order
    # 'loaded' (default)
    return [s for s in city.stop_ids if s in set(loaded_ids)]


# --------------------------------------------------------------------------- #
# Distance matrix over the road network
# --------------------------------------------------------------------------- #
def build_matrix(city: City, disruptions: Dict[str, dict], nodes: Sequence[int]):
    """n x n shortest travel-time matrix between ``nodes`` under ``disruptions``."""
    adj = city.adjacency(disruptions)
    n = len(nodes)
    matrix = [[0.0] * n for _ in range(n)]
    for i, src in enumerate(nodes):
        dist, _ = alg.dijkstra(adj, src)
        for j in range(n):
            matrix[i][j] = dist[nodes[j]]
    return matrix


def stop_by_node(city: City) -> Dict[int, str]:
    return {s["node"]: sid for sid, s in city.stops.items()}


# --------------------------------------------------------------------------- #
# Route sequencing
# --------------------------------------------------------------------------- #
def _objective_parts(city: City, matrix, nodes: Sequence[int],
                     order: Sequence[int], strictness: float,
                     start_i: int, home_i: int) -> dict:
    """Recompute travel / penalty / total for a decided visit order.

    ``nodes`` are the matrix's underlying city nodes (``order`` holds row indices
    into ``matrix`` of the visited stops); ``start_i``/``home_i`` are the row
    indices of where the route begins and must end (the depot normally).
    """
    if not order:
        return {"travel": 0.0, "penalty": 0.0, "total": 0.0}
    travel = matrix[start_i][order[0]]
    for a, b in zip(order, order[1:]):
        travel += matrix[a][b]
    travel += matrix[order[-1]][home_i]
    penalty = 0.0
    node2stop = stop_by_node(city)
    for pos, idx in enumerate(order, start=1):
        pw = PRIO_WEIGHT.get(city.stops[node2stop[nodes[idx]]]["priority"], 0)
        penalty += strictness * pw * pos
    return {"travel": travel, "penalty": penalty, "total": travel + penalty}


def solve_route(city: City, disruptions: Dict[str, dict],
                stop_ids: Sequence[str], strictness: float,
                start_node: Optional[int] = None,
                home_node: Optional[int] = None,
                max_dp_stops: int = 12) -> dict:
    """Choose a delivery order for ``stop_ids`` (priority-aware TSP).

    ``start_node`` defaults to the depot (initial plan). During a live re-route the
    engine passes the van's current node so the route is re-planned from where it
    actually is, while ``home_node`` stays the depot.

    Returns plan details including visit order (stop ids), the objective split and
    which solver produced the answer.
    """
    depot = city.depot
    if start_node is None:
        start_node = depot
    if home_node is None:
        home_node = depot
    node2stop = stop_by_node(city)

    # Deduplicated node universe: [start] + [home] + each stop's node.
    nodes: List[int] = []
    for n in (start_node, home_node, *(city.stops[s]["node"] for s in stop_ids)):
        if n not in nodes:
            nodes.append(n)
    pos_of = {n: i for i, n in enumerate(nodes)}

    matrix = build_matrix(city, disruptions, nodes)
    stop_node_ids = [n for s in stop_ids for n in [city.stops[s]["node"]]]
    # indices of the stops (nodes) among the matrix rows that are actual stops
    order_candidates = [pos_of[n] for n in stop_node_ids]

    start_i, home_i = pos_of[start_node], pos_of[home_node]
    k = len(order_candidates)
    method = "held_karp"
    if k > max_dp_stops:
        method = "nearest_neighbour+2opt"

    if k == 0:
        return {"order": [], "order_nodes": [], "method": method, "k": 0,
                "travel": 0.0, "penalty": 0.0, "total": 0.0,
                "matrix": matrix, "nodes": nodes, "start_i": start_i, "home_i": home_i}

    if method == "held_karp":
        def node_cost(row: int, position: int) -> float:
            # row is an index into the matrix; recover the city node, then its stop
            sid = node2stop.get(nodes[row])
            if sid is None:
                return 0.0
            return strictness * PRIO_WEIGHT[city.stops[sid]["priority"]] * position

        best, order_idx = alg.tsp_held_karp(matrix, start=start_i, home=home_i,
                                            node_cost=node_cost)
        order = order_idx
    else:
        _cost, order = alg.tsp_nearest_neighbor_2opt(matrix, start=start_i, home=home_i)

    order_nodes = [nodes[i] for i in order]
    parts = _objective_parts(city, matrix, nodes, order, strictness, start_i, home_i)

    # map order back to stop ids (each visited matrix node that is a stop)
    order_stop_ids = [node2stop[n] for n in order_nodes if n in node2stop]
    return {
        "order": order_stop_ids,
        "order_nodes": order_nodes,
        "method": method,
        "k": k,
        "travel": parts["travel"],
        "penalty": parts["penalty"],
        "total": parts["total"],
        "matrix": matrix,
        "nodes": nodes,
        "start_i": start_i,
        "home_i": home_i,
    }


def route_geometry(city: City, disruptions: Dict[str, dict],
                   ordered_nodes: Sequence[int]):
    """Consecutive shortest-road paths between ``ordered_nodes``.

    Returns a list of legs ``[{"from","to","minutes","nodes":[...]}, ...]`` used to
    draw and simulate the van following actual roads.
    """
    adj = city.adjacency(disruptions)
    legs = []
    for a, b in zip(ordered_nodes, ordered_nodes[1:]):
        minutes, path = alg.shortest_path(adj, a, b)
        legs.append({"from": a, "to": b, "minutes": minutes, "nodes": path})
    return legs
