"""Headless narrative run of the whole system (no browser needed).

Usage:  python demo_cli.py

Demonstrates the full arc the professor will see in the web UI:
  1. 0/1-knapsack load planning (with priority premium)
  2. Priority-aware TSP route planning (Held–Karp exact)
  3. A scripted roadblock appears mid-run -> live re-route
  4. All stops delivered back at the depot

Ends with assertions so it doubles as a smoke test.
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console is cp1252 by default

from core.city import build_city
from core.routing import plan_load, select_route_stops, solve_route
from core.engine import DeliverySim

P = {1: "P1 critical", 2: "P2 high", 3: "P3 normal"}


def fmt_min(m: float) -> str:
    mm, ss = divmod(int(round(m)), 60)
    return f"{mm:02d}:{ss:02d}"


def find_ahead_bridge(sim: DeliverySim):
    """Return the road id of the first bridge still ahead on the current route."""
    reverse = {}
    for rid, road in sim.city.roads.items():
        if road["kind"] == "bridge":
            reverse[(min(road["a"], road["b"]), max(road["a"], road["b"]))] = rid
    for i in range(sim.pt + 1, len(sim.poly) - 1):
        key = (min(sim.poly[i], sim.poly[i + 1]), max(sim.poly[i], sim.poly[i + 1]))
        if key in reverse:
            return reverse[key]
    return None


def main() -> None:
    city = build_city()
    print("=" * 74)
    print("DELIVERY COMMAND CENTER — headless run")
    print(f"  city: {len(city.roads)} roads, {len(city.stop_ids)} candidate stops, "
          f"{len(city.items)} items")
    print("=" * 74)

    # ---- 1. plan the load (0/1 knapsack + priority premium) ----
    capacity = city.config["van_capacity_kg"]
    premium = city.config["priority_premium_default"]
    load = plan_load(city, capacity, premium)
    print(f"\n[1] LOAD PLAN   capacity {capacity} kg · premium {premium}")
    print(f"    loaded {len(load['chosen'])} items ({load['total_weight']} kg, "
          f"fill {load['fill_pct']}%) value {load['total_value']}")
    stops = select_route_stops(city, load["chosen_stop_counts"].keys(), "loaded")
    print(f"    → {len(stops)} destination stops: "
          f"{', '.join(city.stops[s]['name'] for s in stops)}")

    # ---- 2. plan the route (priority-aware TSP) ----
    strictness = city.config["strictness_default"]
    plan = solve_route(city, {}, stops, strictness)
    print(f"\n[2] ROUTE PLAN  method={plan['method']} · {plan['k']} stops")
    print(f"    travel {plan['travel']:.1f} min · priority penalty "
          f"{plan['penalty']:.1f} · total {plan['total']:.1f} min")
    for i, sid in enumerate(plan["order"], start=1):
        st = city.stops[sid]
        print(f"      {i}. [{P[st['priority']]}] {st['name']}")

    # ---- 3. start the sim and block a bridge mid-run ----
    sim = DeliverySim(city)
    sim.start(stops, strictness)
    sim.control("play")
    bridge_rid = find_ahead_bridge(sim)
    injected = False
    print(f"\n[3] LIVE RUN  (route uses bridge: "
          f"{sim.city.roads[bridge_rid]['name'] if bridge_rid else 'none'})")

    guard = 0
    while sim.phase != "done" and guard < 20000:
        sim.advance(0.1)
        guard += 1
        if not injected and sim.clock > 2.0 and sim.phase == "running":
            rid = find_ahead_bridge(sim)
            if rid:
                sim.add_disruption(rid, "roadblock", source="script")
                injected = True

    print("\n[4] EVENT LOG")
    for ev in sim.log:
        marker = {"plan": "·", "disruption": "⚠", "reroute": "↻",
                  "deliver": "✓", "done": "■", "info": "»",
                  "warn": "!"}.get(ev["kind"], "·")
        print(f"   {fmt_min(ev['clock'])}  {marker} {ev['message']}")

    print(f"\n[5] RESULTS")
    print(f"    delivered {len(sim.delivered)}/{len(sim.route_stop_ids)} · "
          f"total {sim.clock:.1f} min · travel {sim.stats['travel_min']:.1f} min · "
          f"re-routes {sim.stats['reroutes']} · late {sim.stats['late_stops']} "
          f"({sim.stats['late_min']:.1f} min)")

    # assertions (smoke test)
    assert injected, "scripted bridge disruption never fired"
    assert sim.stats["reroutes"] >= 1, "expected at least one dynamic re-route"
    assert len(sim.delivered) == len(sim.route_stop_ids), "not all stops delivered"
    assert sim.phase == "done"
    print("\nDEMO OK — all stops delivered with a live re-route on a closed bridge.")


if __name__ == "__main__":
    main()
