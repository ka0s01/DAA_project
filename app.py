"""Delivery Command Center — Flask HTTP layer.

This module is deliberately *thin*: all algorithms and simulation live in the
``core`` package (which has zero Flask dependency, so it stays headless-testable).
Here we only translate browser requests into core calls and core results back
into JSON.

Run with ``python app.py`` then open http://localhost:8000
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Set

from flask import Flask, jsonify, render_template, request

from core import routing as R
from core.city import build_city
from core.engine import DeliverySim

app = Flask(__name__)

# A single shared world + one active DeliverySim for the manager's session.
CITY = build_city()
SIM = DeliverySim(CITY)


# --------------------------------------------------------------------------- #
# helpers shared by the plan and start endpoints
# --------------------------------------------------------------------------- #
def _clamp(value, lo: float, hi: float, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _load_stops(capacity, premium, scope: str, excluded: Set[str]):
    """Knapsack loading + stop selection → (load dict, ordered stop ids)."""
    load = R.plan_load(CITY, int(capacity), premium, excluded)
    stops = R.select_route_stops(CITY, load["chosen_stop_counts"].keys(), scope)
    return load, stops


def _closed_path(plan: dict, disruptions: Dict[str, dict]) -> List[Dict[str, float]]:
    """Road-following polyline coords for [depot → order → depot], as {x,y}."""
    ordered = [CITY.depot] + list(plan["order_nodes"]) + [CITY.depot]
    legs = R.route_geometry(CITY, disruptions, ordered)
    pts: List[Dict[str, float]] = []
    for leg in legs:
        for n in leg["nodes"]:
            x, y = CITY.coords[n]
            if pts and pts[-1]["x"] == x and pts[-1]["y"] == y:
                continue
            pts.append({"x": x, "y": y})
    return pts


def _warnings(load: dict, scope: str) -> List[str]:
    warns: List[str] = []
    left = [it for it in load["skipped"] if it["priority"] == 1]
    if left:
        names = ", ".join(it["name"] for it in left[:4])
        warns.append(f"{len(left)} critical item(s) left behind (no room at this "
                    f"capacity/premium): {names}")
    return warns


# --------------------------------------------------------------------------- #
# data + planning
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/data")
def api_data():
    """Everything the dashboard needs to draw the city and its catalog once."""
    return jsonify({
        "config": CITY.config,
        "col_x": CITY.col_x,
        "row_y": CITY.row_y,
        "avenues": CITY.avenues,
        "streets": CITY.streets,
        "bridge_rows": sorted(CITY.bridge_rows),
        "river": {"left": CITY.river_left, "right": CITY.river_right},
        "depot": {"node": CITY.depot, "x": CITY.coords[CITY.depot][0],
                  "y": CITY.coords[CITY.depot][1]},
        "roads": [{
            "id": rd["id"], "name": rd["name"], "kind": rd["kind"],
            "minutes": round(rd["minutes"], 2),
            "a": {"node": rd["a"], "x": CITY.coords[rd["a"]][0],
                  "y": CITY.coords[rd["a"]][1]},
            "b": {"node": rd["b"], "x": CITY.coords[rd["b"]][0],
                  "y": CITY.coords[rd["b"]][1]},
        } for rd in CITY.roads.values()],
        "stops": [{
            **s, "x": CITY.coords[s["node"]][0], "y": CITY.coords[s["node"]][1],
        } for s in CITY.stops.values()],
        "items": list(CITY.items),
    })


@app.post("/api/plan")
def api_plan():
    """Preview the load (0/1 knapsack) + the route (priority-aware TSP).

    Body (all optional, defaults to the city config):
        capacity, premium, strictness, scope ("loaded"|"all"|"critical"), excluded
    The route reacts to *currently active* disruptions, so closing a road before
    planning visibly forces a detour.
    """
    data = request.get_json(silent=True) or {}
    cfg = CITY.config
    capacity = int(_clamp(data.get("capacity"), cfg["capacity_min"],
                          cfg["capacity_max"], cfg["van_capacity_kg"]))
    premium = _clamp(data.get("premium"), cfg["priority_premium_min"],
                     cfg["priority_premium_max"], cfg["priority_premium_default"])
    strictness = _clamp(data.get("strictness"), cfg["strictness_min"],
                        cfg["strictness_max"], cfg["strictness_default"])
    scope = data.get("scope", "loaded")
    if scope not in ("loaded", "all", "critical"):
        scope = "loaded"
    excluded: Set[str] = set(data.get("excluded") or [])

    load, stop_ids = _load_stops(capacity, premium, scope, excluded)
    disruptions = SIM.disruptions
    plan = R.solve_route(CITY, disruptions, stop_ids, strictness)

    stop_details = []
    for sid in plan["order"]:
        st = CITY.stops[sid]
        stop_details.append({
            "id": sid, "name": st["name"], "node": st["node"],
            "priority": st["priority"], "service": st["service"],
            "deadline": st["deadline"],
            "items": load["chosen_stop_counts"].get(sid, 0),
            "x": CITY.coords[st["node"]][0], "y": CITY.coords[st["node"]][1],
        })

    return jsonify({
        "scope": scope,
        "load": {
            "total_value": load["total_value"],
            "total_weight": load["total_weight"],
            "capacity": load["capacity"],
            "fill_pct": load["fill_pct"],
            "chosen_count": len(load["chosen"]),
            "skipped_count": len(load["skipped"]),
            "chosen": [{
                "id": it["id"], "name": it["name"], "to": it["to"],
                "to_name": CITY.stops[it["to"]]["name"],
                "weight": it["weight"], "value": it["value"],
                "priority": it["priority"],
                "score": round(R.item_score(it, premium), 1),
            } for it in load["chosen"]],
        },
        "stops": stop_details,
        "route": {
            "method": plan["method"], "k": plan["k"],
            "travel": round(plan["travel"], 1),
            "penalty": round(plan["penalty"], 1),
            "total": round(plan["total"], 1),
        },
        "path": _closed_path(plan, disruptions),
        "warnings": _warnings(load, scope),
    })


# --------------------------------------------------------------------------- #
# live simulation
# --------------------------------------------------------------------------- #
@app.get("/api/sim/state")
def api_sim_state():
    """Full sim snapshot; each poll also advances the simulated clock by the real
    wall-clock time elapsed × timescale, which is what makes the demo run live."""
    return jsonify(SIM.snapshot())


@app.post("/api/sim/start")
def api_sim_start():
    """Arm a fresh run from the depot (phase "paused" until the UI plays it)."""
    data = request.get_json(silent=True) or {}
    cfg = CITY.config
    capacity = int(_clamp(data.get("capacity"), cfg["capacity_min"],
                          cfg["capacity_max"], cfg["van_capacity_kg"]))
    premium = _clamp(data.get("premium"), cfg["priority_premium_min"],
                     cfg["priority_premium_max"], cfg["priority_premium_default"])
    strictness = _clamp(data.get("strictness"), cfg["strictness_min"],
                        cfg["strictness_max"], cfg["strictness_default"])
    scope = data.get("scope", "loaded")
    if scope not in ("loaded", "all", "critical"):
        scope = "loaded"
    excluded: Set[str] = set(data.get("excluded") or [])
    autoplay = bool(data.get("autoplay", False))

    if data.get("clear_disruptions", True):
        SIM.disruptions.clear()

    _load, stop_ids = _load_stops(capacity, premium, scope, excluded)
    plan = SIM.start(stop_ids, strictness, capacity=capacity, premium=premium,
                     scope=scope)
    if autoplay:
        SIM.control("play")
    return jsonify({
        "ok": True,
        "plan": {"method": plan["method"], "k": plan["k"],
                 "travel": round(plan["travel"], 1),
                 "penalty": round(plan["penalty"], 1),
                 "total": round(plan["total"], 1)},
        "sim": SIM.snapshot(),
    })


@app.post("/api/sim/control")
def api_sim_control():
    data = request.get_json(silent=True) or {}
    action = data.get("action", "play")
    timescale = data.get("timescale")
    if timescale is not None:
        try:
            timescale = float(timescale)
        except (TypeError, ValueError):
            timescale = None
    SIM.control(action, timescale)
    return jsonify(SIM.snapshot())


# --------------------------------------------------------------------------- #
# disruptions (the dynamic part)
# --------------------------------------------------------------------------- #
@app.get("/api/roads")
def api_roads():
    """Road catalog — id/name/kind per road, for the disruption dropdown."""
    return jsonify({
        "roads": [{"id": rd["id"], "name": rd["name"], "kind": rd["kind"]}
                  for rd in CITY.roads.values()],
    })


@app.post("/api/disrupt")
def api_disrupt():
    """Inject a roadblock or a traffic slowdown on one road (id, kind, factor?)."""
    data = request.get_json(silent=True) or {}
    rid = data.get("id") or data.get("rid")
    kind = data.get("kind", "roadblock")
    if rid not in CITY.roads:
        return jsonify({"ok": False, "error": f"unknown road {rid!r}"}), 404
    if kind not in ("roadblock", "traffic"):
        return jsonify({"ok": False, "error": "kind must be roadblock|traffic"}), 400
    SIM.add_disruption(rid, kind, factor=data.get("factor"))
    return jsonify({"ok": True, "sim": SIM.snapshot()})


@app.post("/api/disrupt/clear")
def api_disrupt_clear():
    data = request.get_json(silent=True) or {}
    rid = data.get("id") or data.get("rid")
    if rid not in CITY.roads:
        return jsonify({"ok": False, "error": f"unknown road {rid!r}"}), 404
    SIM.clear_disruption(rid)
    return jsonify({"ok": True, "sim": SIM.snapshot()})


# --------------------------------------------------------------------------- #
# seeded auto-demo: manager clicks one button, gets a guaranteed live re-route
# --------------------------------------------------------------------------- #
@app.post("/api/demo/scenario")
def api_demo_scenario():
    """Reset to defaults, plan the busiest load, and schedule a roadblock on the
    first bridge still ahead on the initial route so a re-route is guaranteed."""
    cfg = CITY.config
    capacity = cfg["van_capacity_kg"]
    premium = cfg["priority_premium_default"]
    strictness = cfg["strictness_default"]
    SIM.disruptions.clear()

    load, stop_ids = _load_stops(capacity, premium, "loaded", set())
    SIM.start(stop_ids, strictness, capacity=capacity, premium=premium, scope="loaded")

    # pick the first bridge edge that lies ahead in the planned polyline
    bridge_key = {}
    for rid, road in CITY.roads.items():
        if road["kind"] == "bridge":
            bridge_key[(min(road["a"], road["b"]), max(road["a"], road["b"]))] = rid
    chosen = None
    for i in range(len(SIM.poly) - 1):
        key = (min(SIM.poly[i], SIM.poly[i + 1]), max(SIM.poly[i], SIM.poly[i + 1]))
        if key in bridge_key and i + 1 < len(SIM.offs):
            at = max(0.6, SIM.offs[i + 1] - 1.2)   # hit it just before arrival
            chosen = (bridge_key[key], at)
            break

    if chosen is None:
        return jsonify({"ok": False,
                        "error": "planned route crosses no bridge — manual demo only",
                        "sim": SIM.snapshot()}), 409

    rid, at = chosen
    SIM.add_scripted_event(at, rid, "roadblock")
    SIM.control("play")
    return jsonify({"ok": True, "roadblock": {"rid": rid, "at": at,
                                              "name": CITY.roads[rid]["name"]},
                    "sim": SIM.snapshot()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Delivery Command Center → http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
