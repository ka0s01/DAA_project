"""Plain-assert sanity tests for the algorithm core.

Run with:  python algo_tests.py

No pytest dependency — every test raises ``AssertionError`` on failure and prints a
line on success. Uses deterministic/random-seeded instances only.
"""
from __future__ import annotations

import itertools
import math
import random

from core import (
    build_city,
    dijkstra,
    knapsack_01,
    shortest_path,
    tour_cost,
    tsp_held_karp,
    tsp_nearest_neighbor_2opt,
)

_TESTS_RUN = 0


def ok(name: str) -> None:
    global _TESTS_RUN
    _TESTS_RUN += 1
    print(f"  ok  {name}")


# --------------------------------------------------------------------------- #
# 0/1 Knapsack
# --------------------------------------------------------------------------- #
def brute_knapsack(weights, values, capacity):
    best = 0
    for mask in range(1 << len(weights)):
        w = v = 0
        for i in range(len(weights)):
            if (mask >> i) & 1:
                w += weights[i]
                v += values[i]
        if w <= capacity and v > best:
            best = v
    return best


def test_knapsack_vs_bruteforce():
    rng = random.Random(42)
    for _ in range(40):
        n = rng.randint(1, 12)
        weights = [rng.randint(1, 10) for _ in range(n)]
        values = [rng.randint(1, 100) for _ in range(n)]
        cap = rng.randint(0, 20)
        res = knapsack_01(weights, values, cap)
        assert res["max_value"] == brute_knapsack(weights, values, cap), (
            f"DP={res['max_value']} brute={brute_knapsack(weights, values, cap)}")
        total_w = sum(weights[i] for i in res["indices"])
        assert total_w <= cap and total_w == res["total_weight"]
    ok("knapsack_01 == brute force on 40 random instances")


def test_knapsack_classic():
    res = knapsack_01([10, 20, 30], [60, 100, 120], 50)
    assert res["indices"] == [1, 2] and res["max_value"] == 220
    ok("knapsack_01 classic instance (20+30, value 220)")


def test_knapsack_overweight_item_never_fits_alone():
    res = knapsack_01([50], [999], 10)
    assert res["indices"] == [] and res["max_value"] == 0
    ok("knapsack_01 item heavier than capacity is excluded")


def test_knapsack_priority_premium_changes_choice():
    # Three items, same weight; the critical (P1) one is the *least* valuable on
    # raw value but becomes competitive once a priority premium is added.
    weights = [20, 20, 20]
    raw = [150, 160, 60]      # priority 3, 3, 1  -> P1 is index 2
    prio = [3, 3, 1]

    def eff(premium):
        return [raw[i] + premium * (3 - prio[i]) for i in range(3)]

    cap = 40
    no = knapsack_01(weights, eff(0), cap)["indices"]
    yes = knapsack_01(weights, eff(400), cap)["indices"]
    assert no == [0, 1], f"expected [0,1], got {no}"
    assert yes == [1, 2], f"expected [1,2] (critical prioritized), got {yes}"
    ok("knapsack_01 priority premium flips choice to the critical item")


# --------------------------------------------------------------------------- #
# Dijkstra
# --------------------------------------------------------------------------- #
def test_dijkstra_chain():
    # 0 -1- 2 with a longer direct 0-2 edge: shortest 0->2 goes via 1 (cost 2).
    adj = [[(1, 1.0), (2, 3.0)], [(0, 1.0), (2, 1.0)], [(1, 1.0), (0, 3.0)]]
    d, path = shortest_path(adj, 0, 2)
    assert abs(d - 2.0) < 1e-9 and path == [0, 1, 2], (d, path)
    ok("dijkstra finds shorter 2-edge path over direct edge")


def test_dijkstra_unreachable_raises():
    adj = [[(1, 1.0)], [(0, 1.0)], []]
    dist, _ = dijkstra(adj, 0)
    assert math.isinf(dist[2])
    try:
        shortest_path(adj, 0, 2)
        raise AssertionError("expected ValueError for unreachable node")
    except ValueError:
        pass
    ok("dijkstra marks unreachable nodes and shortest_path raises")


# --------------------------------------------------------------------------- #
# TSP: Held-Karp exact vs brute force (with and without position costs)
# --------------------------------------------------------------------------- #
def brute_tsp(matrix, start=0, node_cost=None, home=None):
    if home is None:
        home = start
    others = [i for i in range(len(matrix)) if i not in (start, home)]
    best = math.inf
    for perm in itertools.permutations(others):
        cost = matrix[start][perm[0]] if perm else 0.0
        for a, b in zip(perm, perm[1:]):
            cost += matrix[a][b]
        for pos, node in enumerate(perm, start=1):
            cost += (node_cost(node, pos) if node_cost else 0.0)
        if perm:
            cost += matrix[perm[-1]][home]
        best = min(best, cost)
    return best


def random_matrix(rng, n):
    mat = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            w = rng.uniform(1, 30)
            mat[i][j] = mat[j][i] = w
    return mat


def test_held_karp_vs_bruteforce():
    rng = random.Random(7)
    for n in (3, 4, 5, 6, 7):
        for _ in range(6):
            mat = random_matrix(rng, n)
            best, order = tsp_held_karp(mat)
            assert len(set(order)) == n - 1 and set(order) == set(range(1, n))
            assert abs(best - brute_tsp(mat)) < 1e-6, (n, best, brute_tsp(mat))
            # reported cost must equal travel of the returned tour
            assert abs(tour_cost(mat, order) - best) < 1e-6
    ok("tsp_held_karp == permutation brute force (n=3..7)")


def test_held_karp_with_position_costs():
    # node_cost depends on the position the stop is visited in -> verifies the
    # priority-penalty mechanism is handled exactly by the DP.
    def cost(node, pos):
        return node * pos * 1.5

    rng = random.Random(11)
    for n in (4, 5, 6):
        for _ in range(5):
            mat = random_matrix(rng, n)
            best, order = tsp_held_karp(mat, node_cost=cost)
            assert abs(best - brute_tsp(mat, node_cost=cost)) < 1e-6
    ok("tsp_held_karp exact with additive position cost (priority penalty)")


def test_held_karp_open_route_home_different():
    # Re-planning mid-run: route STARTS at a non-depot node but must still finish at
    # the depot. Held-Karp must treat start and home independently.
    rng = random.Random(5)
    for _ in range(20):
        n = rng.randint(4, 6)
        mat = random_matrix(rng, n)
        start = rng.randrange(n)
        home = rng.randrange(n)
        while home == start:
            home = rng.randrange(n)
        best, order = tsp_held_karp(mat, start=start, home=home)
        assert len(set(order)) == len(order) == n - 2
        assert abs(best - brute_tsp(mat, start=start, home=home)) < 1e-6
    ok("tsp_held_karp exact when start != home (mid-run re-plan)")


def test_nn_2opt_never_beats_exact():
    rng = random.Random(3)
    for n in (5, 6, 7, 8):
        for _ in range(6):
            mat = random_matrix(rng, n)
            exact, _ = tsp_held_karp(mat)
            approx, _ = tsp_nearest_neighbor_2opt(mat)
            assert approx >= exact - 1e-9, (n, approx, exact)
    ok("nearest-neighbour+2-opt never beats exact Held-Karp (sanity)")


def test_nn_2opt_returns_valid_tour():
    rng = random.Random(99)
    mat = random_matrix(rng, 8)
    cost, order = tsp_nearest_neighbor_2opt(mat)
    assert set(order) == set(range(1, 8)) and len(order) == 7
    assert abs(tour_cost(mat, order) - cost) < 1e-6
    ok("nearest-neighbour+2-opt returns a valid, well-costed tour")


# --------------------------------------------------------------------------- #
# City dataset invariants
# --------------------------------------------------------------------------- #
def test_city_invariants():
    city = build_city()
    # reproducibility
    assert [r["id"] for r in city.roads.values()] == \
           [r["id"] for r in build_city().roads.values()]

    n_expected = len(city.col_x) * len(city.row_y)   # 42
    assert city.n == n_expected and len(city.coords) == n_expected
    assert len(city.roads) >= n_expected             # dense enough to be a real grid

    # the whole road network must be connected (depot reaches everything)
    from collections import deque
    seen, stack = {0}, [0]
    adj0 = city.adjacency()
    while stack:
        u = stack.pop()
        for v, _w in adj0[u]:
            if v not in seen:
                seen.add(v)
                stack.append(v)
    assert len(seen) == city.n, "road network not connected"

    # exactly the two bridges exist
    bridges = [r for r in city.roads.values() if r["kind"] == "bridge"]
    assert len(bridges) == 2, f"expected 2 bridges, got {len(bridges)}"
    for r in city.roads.values():
        assert r["minutes"] > 0

    # adjacency symmetric & road minutes consistent
    adj = city.adjacency()
    for rid, r in city.roads.items():
        assert any(v == r["b"] and abs(w - r["minutes"]) < 1e-9 for v, w in adj[r["a"]])
        assert any(v == r["a"] and abs(w - r["minutes"]) < 1e-9 for v, w in adj[r["b"]])

    # stops & items consistent
    nodes = set(range(city.n))
    for sid, s in city.stops.items():
        assert s["node"] in nodes and s["node"] != city.depot
    stop_nodes = {s["node"] for s in city.stops.values()}
    assert len(stop_nodes) == len(city.stop_ids)   # one stop per distinct node
    for item in city.items:
        assert item["to"] in city.stops

    # enough items so a capacity-limited load is a real decision
    assert len(city.items) >= 3 * len(city.stop_ids)
    ok("city dataset invariants hold (42 nodes, 2 bridges, 12 stops, items valid)")
    return city


def test_bridge_roadblock_detour():
    city = test_city_invariants()
    # A pair of nodes: far west bank (Central Ave side, col 3) and far east (col 6).
    from core import city as citymod
    west = citymod._nid(2, 3)     # mid-west, just west of river
    east = citymod._nid(2, 6)     # mid-east
    adj_open = city.adjacency({})
    d_open, _ = shortest_path(adj_open, west, east)

    # close the NORTH bridge only -> the only crossing left is the south one.
    north_bridge = next(r["id"] for r in city.roads.values()
                        if r["kind"] == "bridge" and "Main St" in r["name"])
    blocked = {north_bridge: {"kind": "roadblock"}}
    d_closed, _ = shortest_path(city.adjacency(blocked), west, east)
    assert d_closed > d_open + 0.1, (d_open, d_closed)
    assert not math.isinf(d_closed)   # south bridge still connects the banks
    ok("closing the north bridge forces a strictly longer detour")
    return blocked


if __name__ == "__main__":
    test_knapsack_vs_bruteforce()
    test_knapsack_classic()
    test_knapsack_overweight_item_never_fits_alone()
    test_knapsack_priority_premium_changes_choice()
    test_dijkstra_chain()
    test_dijkstra_unreachable_raises()
    test_held_karp_vs_bruteforce()
    test_held_karp_with_position_costs()
    test_held_karp_open_route_home_different()
    test_nn_2opt_never_beats_exact()
    test_nn_2opt_returns_valid_tour()
    test_bridge_roadblock_detour()
    print(f"\nALL TESTS PASSED ({_TESTS_RUN} checks)")
