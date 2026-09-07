"""Generate the experiment tables cited in REPORT.md.

Run:  python experiments.py          (deterministic, no network)

Every number below is produced by actually running the algorithms in core/ on
the city dataset from core/city.py — nothing is hard-coded — so the report can
be re-verified by re-running this file.
"""
from __future__ import annotations

import random
import time

from core import algorithms as alg
from core.city import build_city
from core import routing as R

city = build_city()
cfg = city.config
CAP = cfg["van_capacity_kg"]
PREM = cfg["priority_premium_default"]
LAM = cfg["strictness_default"]
BRIDGES = {rd["name"]: rid for rid, rd in city.roads.items()
           if rd["kind"] == "bridge"}


def default_load():
    return R.plan_load(city, CAP, PREM)


def loaded_stops():
    load = default_load()
    return R.select_route_stops(city, load["chosen_stop_counts"].keys(), "loaded")


def critical_left(load):
    return sorted(it["name"] for it in load["skipped"] if it["priority"] == 1)


def names(sids):
    return " → ".join(city.stops[s]["name"] for s in sids)


def main() -> None:
    print("=" * 78)
    print("DELIVERY COMMAND CENTER — experiment tables (deterministic)")
    print(f"city: {len(city.roads)} roads · {len(city.stop_ids)} stops · "
          f"{len(city.items)} items · van {CAP} kg")
    print("=" * 78)

    # ---------------------------------------------------------- #
    print("\n[1] DEFAULT LOAD (capacity 430, premium 220, λ=4)\n")
    load = default_load()
    stops = loaded_stops()
    plan = R.solve_route(city, {}, stops, LAM)
    p1 = sum(1 for it in load["chosen"] if it["priority"] == 1)
    print(f"  loaded {len(load['chosen'])} items / {load['total_weight']} kg "
          f"({load['fill_pct']:.1f}% of {CAP} kg), score value "
          f"{load['total_value']:.0f}")
    print(f"  priority mix loaded: P1={p1} · route visits {len(stops)} stops "
          f"via {plan['method']} (k={plan['k']})")
    print(f"  route objective: travel {plan['travel']:.1f} min + priority "
          f"penalty {plan['penalty']:.1f} = {plan['total']:.1f}")
    print("  critical items the van could not take:",
          critical_left(load) or "none")

    # ---------------------------------------------------------- #
    print("\n[2] CAPACITY SWEEP — what a bigger van buys (premium 220, λ=4)\n")
    print("  capacity | items | weight | fill   | score   | stops | critical left")
    print("  -------- | ----- | ------ | ------ | ------- | ----- | -------------")
    for cap in [150, 250, 350, 430, 600, 900]:
        l = R.plan_load(city, cap, PREM)
        s = R.select_route_stops(city, l["chosen_stop_counts"].keys(), "loaded")
        cl = critical_left(l)
        print(f"  {cap:>7} | {len(l['chosen']):>4}  | {l['total_weight']:>5}  | "
              f"{l['fill_pct']:>5.1f}% | {l['total_value']:>8.0f} | {len(s):>4}  | "
              f"{len(cl)}")

    # ---------------------------------------------------------- #
    print("\n[3] PRIORITY PREMIUM — why critical goods win ties (capacity 430)\n")
    print("  premium | score   | items | fill   | P1 loaded | P1 left behind")
    print("  ------- | ------- | ----- | ------ | --------- | --------------")
    sets = {}
    for pr in [0, 220, 500]:
        l = R.plan_load(city, CAP, pr)
        sets[pr] = {it["id"] for it in l["chosen"]}
        n1 = sum(1 for it in l["chosen"] if it["priority"] == 1)
        left = critical_left(l)
        print(f"  {pr:>6} | {l['total_value']:>7.0f} | {len(l['chosen']):>4}  | "
              f"{l['fill_pct']:>5.1f}% | {n1:>8}  | {len(left)}")
    gained = {city.items[int(i[1:])]["name"] for i in (sets[500] - sets[0])}
    lost = {city.items[int(i[1:])]["name"] for i in (sets[0] - sets[500])}
    print(f"\n  raising premium 0 → 500 trades normal stock for critical stock:")
    print(f"    in  (critical/high): {', '.join(sorted(gained))}")
    print(f"    out (normal):        {', '.join(sorted(lost))}")

    # ---------------------------------------------------------- #
    print("\n[4] PUNCTUALITY λ — reordering the run (9 loaded stops)\n")
    for lam, tag in [(0.0, "pure shortest route"),
                     (8.0, "critical first")]:
        p = R.solve_route(city, {}, stops, lam)
        p1pos = [i + 1 for i, s in enumerate(p["order"])
                 if city.stops[s]["priority"] == 1]
        print(f"  λ={lam:g} ({tag}):")
        print(f"     travel {p['travel']:.1f} min · priority penalty "
              f"{p['penalty']:.1f} · total {p['total']:.1f} min")
        print(f"     order: {names(p['order'])}")
        print(f"     P1 stops land at positions {p1pos}")
        print()

    # ---------------------------------------------------------- #
    print("[5] ROADBLOCK PENALTY — a closed bridge at planning time (same load)\n")
    intact = R.solve_route(city, {}, stops, LAM)
    for bname in ["Main St Bridge", "Grand St Bridge"]:
        rid = BRIDGES[bname]
        blocked = R.solve_route(city, {rid: {"kind": "roadblock"}}, stops, LAM)
        d = blocked["travel"] - intact["travel"]
        print(f"  close {bname:16s}: travel {blocked['travel']:5.1f} min vs "
              f"{intact['travel']:.1f} intact  → +{d:.1f} min (+{100*d/intact['travel']:.0f}%)")
    print("\n  (live demo: the van detects the closure mid-run and re-plans from its")
    print("   current node — the log shows 'detour adds ~+7.7 min' for Main St.)")

    # ---------------------------------------------------------- #
    print("\n[6] EXACT HELD–KARP vs NN+2-OPT FALLBACK\n")
    # 6a. on the real instance, force the heuristic to see what it would cost
    forced = R.solve_route(city, {}, stops, LAM, max_dp_stops=6)  # k=9 > 6
    print("  6a. real 9-stop instance (exact vs forced NN+2-opt):")
    print(f"      exact total {plan['total']:.2f}  ·  heuristic total "
          f"{forced['total']:.2f}  (gap {100*(forced['total']-plan['total'])/plan['total']:.1f}%)")
    # 6b. random matrices, averaged gap
    print("  6b. random symmetric matrices — average / worst gap of NN+2-opt")
    print("      vs the exact DP over 25 trials per size:")
    print("      k | avg gap | worst gap | exact ms | heuristic ms")
    rnd = random.Random(42)
    for k in [6, 8, 10, 11]:
        gaps, t1, t2 = [], [], []
        for _ in range(25):
            n = k + 1
            m = [[0.0] * n for _ in range(n)]
            for i in range(n):
                for j in range(i + 1, n):
                    v = float(rnd.randint(1, 99))
                    m[i][j] = m[j][i] = v
            s0 = time.perf_counter(); exact, _ = alg.tsp_held_karp(m); t1.append(time.perf_counter() - s0)
            s0 = time.perf_counter(); heur, _ = alg.tsp_nearest_neighbor_2opt(m); t2.append(time.perf_counter() - s0)
            gaps.append(100 * (heur - exact) / exact)
        print(f"      {k:2} | {sum(gaps)/len(gaps):6.2f}% | "
              f"{max(gaps):6.2f}% | {1000*sum(t1)/len(t1):8.1f} | "
              f"{1000*sum(t2)/len(t2):10.2f}")
    print("\n      → exact is affordable up to k≈12; past that the 2-opt fallback is")
    print("        still within a few percent on these instances.")

    # ---------------------------------------------------------- #
    print("\n[7] EXACT DP COST GROWTH (random matrix, 1 run per k)\n")
    print("  k stops | dp size 2^k | time")
    rnd2 = random.Random(7)
    for k in [10, 12, 14, 16]:
        n = k + 1
        m = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                v = float(rnd2.randint(1, 99))
                m[i][j] = m[j][i] = v
        s0 = time.perf_counter(); alg.tsp_held_karp(m); ms = 1000 * (time.perf_counter() - s0)
        print(f"  {k:>6} | {1 << k:>10} | {ms:7.1f} ms")

    print("\n" + "=" * 78)


if __name__ == "__main__":
    main()
