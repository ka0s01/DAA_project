"""Live delivery-run simulation.

``DeliverySim`` owns the state of one van run: a simulated clock, the van's
position along a planned road polyline, active disruptions, delivered stops and an
event log. The clock advances in *simulated minutes* and only moves while the run is
in ``"running"`` phase, so the whole thing is deterministic and testable headless
(``advance()``) while the web layer drives it from wall-clock time × a timescale.

**Dynamic re-routing.** A disruption (roadblock / traffic) is injected on a road.
If that road lies ahead on the current route the engine re-plans *from the van's
current node* with the road removed from the graph — Dijkstra + priority-aware TSP
are simply re-run over the remaining stops. Roadblocks are mandatory re-routes
(the old route is infeasible); traffic re-routes only when a genuinely better route
exists, so the log never churns.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Sequence, Tuple

from . import routing as R

PRIO_LABEL = {1: "P1", 2: "P2", 3: "P3"}


class DeliverySim:
    def __init__(self, city) -> None:
        self.city = city
        self.cfg = city.config
        self.disruptions: Dict[str, dict] = {}     # road id -> details
        self.phase: str = "idle"                   # idle | paused | running | done
        self.clock: float = 0.0                    # simulated minutes since departure
        self.timescale: float = self.cfg["time_scale_default"]
        self._last_wall: Optional[float] = None

        # planning context (what this run is about)
        self.load_plan: Optional[dict] = None
        self.scope: str = "loaded"
        self.strictness: float = self.cfg["strictness_default"]
        self.route_stop_ids: List[str] = []        # full intended stop set

        # live run state
        self.poly: List[int] = []                  # planned node sequence (roads)
        self.offs: List[float] = []                # cumulative travel minutes at poly[i]
        self.stops_at: List[Optional[str]] = []    # stop delivered when reaching poly[i]
        self.serve_order: List[str] = []           # remaining stop ids, in plan order
        self.delivered: List[dict] = []            # {stop, arrived, left, late}
        self.pt: int = 0                           # last reached poly index
        self.travel: float = 0.0                   # travel minutes consumed on poly
        self.dwell: bool = False                   # servicing a stop right now
        self.dwell_stop: Optional[str] = None
        self._dwell_arrived: float = 0.0
        self._dwell_until: float = 0.0

        self.method: Optional[str] = None
        self.plan_total: Optional[float] = None
        self.plan_travel: Optional[float] = None
        self.history: List[List[int]] = []         # previous route polylines (ghost)
        self.stats: dict = {"reroutes": 0, "travel_min": 0.0,
                            "late_stops": 0, "late_min": 0.0}
        self._script: List[dict] = []              # {at, rid, kind} scripted events
        self._last_reroute_clock: float = -10.0
        self._ev_id = 0
        self.log: List[dict] = []
        self._seen = 0
        self._stop_node = R.stop_by_node(city)

    # ------------------------------------------------------------------ #
    # events
    # ------------------------------------------------------------------ #
    def _log(self, message: str, kind: str = "info") -> None:
        self._ev_id += 1
        self.log.append({"id": self._ev_id, "clock": round(self.clock, 1),
                         "message": message, "kind": kind})
        if len(self.log) > 400:
            self.log = self.log[-300:]

    def _clock_str(self) -> str:
        m, s = divmod(int(round(self.clock)), 60)
        return f"{m:02d}:{s:02d}"

    # ------------------------------------------------------------------ #
    # disruption management
    # ------------------------------------------------------------------ #
    def add_disruption(self, rid: str, kind: str, factor: Optional[float] = None,
                       source: str = "manual") -> None:
        road = self.city.roads[rid]
        d = {"id": rid, "kind": kind, "name": road["name"],
             "factor": float(factor) if factor else (3.0 if kind == "traffic" else 1.0),
             "source": source}
        self.disruptions[rid] = d
        word = "closed" if kind == "roadblock" else f"slowed ×{d['factor']:g}"
        self._log(f"{road['name']} {word} ({road['kind']})", "disruption")
        if self.phase in ("running", "paused") and self.poly:
            self._maybe_reroute(f"{road['name']} {word}")

    def clear_disruption(self, rid: str) -> None:
        if rid in self.disruptions:
            road = self.city.roads[rid]
            del self.disruptions[rid]
            self._log(f"All clear on {road['name']}", "info")
            if self.phase in ("running", "paused") and self.poly:
                self._maybe_reroute(f"{road['name']} reopened")

    def disruption_list(self) -> List[dict]:
        return list(self.disruptions.values())

    # ------------------------------------------------------------------ #
    # routing helpers
    # ------------------------------------------------------------------ #
    def _pair_min(self) -> Dict[Tuple[int, int], float]:
        """Effective travel minutes keyed by unordered endpoint pair."""
        adj = self.city.adjacency(self.disruptions)
        pair: Dict[Tuple[int, int], float] = {}
        for rid, road in self.city.roads.items():
            d = self.disruptions.get(rid)
            if d is not None and d["kind"] == "roadblock":
                continue
            m = road["minutes"]
            if d is not None and d["kind"] == "traffic":
                m *= d["factor"]
            pair[(min(road["a"], road["b"]), max(road["a"], road["b"]))] = m
        return pair

    def _apply_plan(self, ordered_nodes: Sequence[int],
                    stop_order: Sequence[str]) -> dict:
        """Build polyline geometry from ``ordered_nodes`` and remember delivery pts.

        ``ordered_nodes`` = [start_node, stop.. , home_node]. Returns a map
        ``stop_id -> poly offset`` used for ETA projection. Travel minutes along each
        shortest-path edge come from the effective (disruption-aware) road times so
        movement matches the plan.
        """
        pair = self._pair_min()
        legs = R.route_geometry(self.city, self.disruptions, ordered_nodes)

        poly: List[int] = []
        offs: List[float] = []
        stops_at: List[Optional[str]] = []
        marker_offs: Dict[str, float] = {}
        t = 0.0
        for leg in legs:
            for x in leg["nodes"]:
                if not poly:
                    poly.append(x); offs.append(0.0); stops_at.append(None)
                    continue
                if x == poly[-1]:          # junction node shared with previous leg
                    continue
                key = (min(poly[-1], x), max(poly[-1], x))
                if key not in pair:
                    raise KeyError(f"no road between {poly[-1]} and {x}")
                t += pair[key]
                poly.append(x); offs.append(t); stops_at.append(None)
            # the end of a leg is a delivery point when its target is a scheduled stop
            target = leg["to"]
            sid = self._stop_node.get(target)
            if sid is not None and sid in stop_order:
                stops_at[len(poly) - 1] = sid
                marker_offs[sid] = offs[len(poly) - 1]

        self.poly, self.offs, self.stops_at = poly, offs, stops_at
        self.pt, self.travel = 0, 0.0
        self.dwell = False
        self._marker_offs = marker_offs
        return marker_offs

    def start(self, stop_ids: Sequence[str], strictness: float,
              capacity: Optional[int] = None, premium: Optional[float] = None,
              scope: str = "loaded", run_script: Optional[List[dict]] = None) -> dict:
        """Plan + arm a fresh run from the depot (clock reset to 0, paused)."""
        self.route_stop_ids = list(dict.fromkeys(stop_ids))
        self.strictness = float(strictness)
        self.scope = scope
        plan = R.solve_route(self.city, self.disruptions, self.route_stop_ids,
                             self.strictness)
        if not plan["order"]:
            self._log("No stops to visit — nothing to deliver", "warn")
            return plan
        self.method = plan["method"]
        self.plan_total = plan["total"]
        self.plan_travel = plan["travel"]
        ordered_nodes = [self.city.depot] + plan["order_nodes"] + [self.city.depot]
        self._apply_plan(ordered_nodes, plan["order"])
        self.serve_order = list(plan["order"])
        self.delivered = []
        self.history = []
        self.clock = 0.0
        self.phase = "paused"
        self.stats = {"reroutes": 0, "travel_min": 0.0, "late_stops": 0, "late_min": 0.0}
        self._script = list(run_script or [])
        self._log(f"Route planned · {len(self.serve_order)} stops · {plan['method']} · "
                  f"travel {plan['travel']:.1f} min · priority cost {plan['penalty']:.1f}",
                  "plan")
        self._log(f"Van loaded · depart from DEPOT · priority strictness λ={strictness:g}",
                  "plan")
        return plan

    # ------------------------------------------------------------------ #
    # clock / movement
    # ------------------------------------------------------------------ #
    def control(self, action: str, timescale: Optional[float] = None) -> None:
        if timescale is not None:
            self.timescale = float(timescale)
        if action == "play":
            if self.phase == "done":
                return
            self._last_wall = time.monotonic()
            self.phase = "running"
            self._log("Delivery run started · van on the road", "info")
        elif action == "pause":
            self.phase = "paused"
            self._log("Run paused", "info")

    def tick(self) -> None:
        """Advance the clock by real elapsed time × timescale."""
        if self.phase != "running":
            return
        now = time.monotonic()
        if self._last_wall is None:
            self._last_wall = now
        dt = (now - self._last_wall) * self.timescale
        self._last_wall = now
        if dt > 0:
            self.advance(dt)

    def advance(self, dt: float) -> None:
        """Deterministic simulation step of ``dt`` simulated minutes."""
        if self.phase != "running":
            return
        budget = float(dt)
        while budget > 1e-9:
            self._fire_scripts()
            if self.phase != "running":
                break
            if self.dwell:
                need = self._dwell_until - self.clock
                take = min(budget, need)
                self.clock += take
                budget -= take
                if need - take <= 1e-9:
                    self._finish_dwell()
                else:
                    break
            else:
                if self.pt >= len(self.poly) - 1:
                    self._finish_run()
                    break
                need = self.offs[self.pt + 1] - self.travel
                if need <= 1e-9:
                    self._step_node()
                    continue
                take = min(budget, need)
                self.travel += take
                self.clock += take
                budget -= take
                if need - take <= 1e-9:
                    self._step_node()
                else:
                    break

    def _step_node(self) -> None:
        self.pt += 1
        if self.pt < len(self.offs):
            self.travel = self.offs[self.pt]
        if self.pt >= len(self.poly) - 1:
            self._finish_run()
            return
        sid = self.stops_at[self.pt] if self.pt < len(self.stops_at) else None
        if sid is not None:
            self.dwell = True
            self.dwell_stop = sid
            self._dwell_arrived = self.clock
            self._dwell_until = self.clock + self.city.stops[sid]["service"]
            self._log(f"Arrived at {self.city.stops[sid]['name']} — servicing "
                      f"({PRIO_LABEL[self.city.stops[sid]['priority']]})", "info")
        if self.disruptions:
            self._maybe_reroute("re-validating route at stop")

    def _finish_dwell(self) -> None:
        sid = self.dwell_stop
        stop = self.city.stops[sid]
        late = 0.0
        if stop["deadline"] is not None:
            late = max(0.0, self._dwell_arrived - stop["deadline"])
            if late > 0:
                self.stats["late_stops"] += 1
                self.stats["late_min"] += late
        self.delivered.append({"stop": sid, "name": stop["name"],
                               "priority": stop["priority"],
                               "arrived": self._dwell_arrived, "left": self.clock,
                               "late": late})
        if self.serve_order and self.serve_order[0] == sid:
            self.serve_order.pop(0)
        self.dwell, self.dwell_stop = False, None
        late_note = f" · ⚠ {late:.1f} min late" if late > 0 else ""
        self._log(f"Delivered {stop['name']} at {self._clock_str()}{late_note}",
                  "deliver")

    def _finish_run(self) -> None:
        if self.phase == "done":
            return
        self.phase = "done"
        self.travel = self.offs[-1] if self.offs else self.travel
        self.stats["travel_min"] = self.offs[-1] if self.offs else self.travel
        self._log(f"Run complete — van back at DEPOT · "
                  f"{len(self.delivered)}/{len(self.route_stop_ids)} stops · "
                  f"{self._clock_str()} total", "done")

    # ------------------------------------------------------------------ #
    # dynamic re-routing
    # ------------------------------------------------------------------ #
    def _future_edges(self) -> List[Tuple[int, int]]:
        """Undirected endpoint pairs of roads still ahead of the van."""
        a0 = self.pt if (self.travel - self.offs[self.pt]) <= 1e-9 else self.pt + 1
        edges = []
        for i in range(max(a0, 0), len(self.poly) - 1):
            edges.append((min(self.poly[i], self.poly[i + 1]),
                          max(self.poly[i], self.poly[i + 1])))
        return edges

    def _disrupted_ahead(self) -> Optional[str]:
        future = set(self._future_edges())
        for rid, d in self.disruptions.items():
            road = self.city.roads[rid]
            if (min(road["a"], road["b"]), max(road["a"], road["b"])) in future:
                return rid
        return None

    def _maybe_reroute(self, reason: str) -> None:
        rid = self._disrupted_ahead()
        if rid is None:
            return
        d = self.disruptions[rid]
        if self.clock - self._last_reroute_clock < 0.4:
            return
        if d["kind"] == "traffic":
            # only bother if a genuinely better route exists
            old_remaining = self.offs[-1] - self.travel
            plan = self._plan_from_current()
            if plan["travel"] >= old_remaining - 0.6:
                self._log(f"Traffic on {d['name']} — current route still best "
                          f"({old_remaining:.1f} min)", "reroute")
                return
            self._reroute(reason, plan)
        else:  # roadblock: mandatory
            self._reroute(reason, self._plan_from_current())

    def _plan_from_current(self) -> dict:
        start_node = self.poly[self.pt] if self.pt < len(self.poly) else self.city.depot
        remaining = list(self.serve_order)
        if self.dwell and self.serve_order and self.serve_order[0] == self.dwell_stop:
            remaining = self.serve_order[1:]  # already at that stop, being serviced
        return R.solve_route(self.city, self.disruptions, remaining, self.strictness,
                             start_node=start_node, home_node=self.city.depot)

    def _reroute(self, reason: str, plan: dict) -> None:
        if not plan["order"]:
            self._log("Nothing left to re-route — heading back to DEPOT", "reroute")
            return
        self.stats["reroutes"] += 1
        old_travel = self.offs[-1] - self.travel
        self._log(f"Re-routing: {reason}", "reroute")
        self.history.append(list(self.poly))
        ordered_nodes = [self.poly[self.pt]] + plan["order_nodes"] + [self.city.depot]
        self._apply_plan(ordered_nodes, plan["order"])
        self.serve_order = list(plan["order"])
        self.method = plan["method"]
        self.plan_total = plan["total"]
        self.plan_travel = plan["travel"]
        delta = old_travel - plan["travel"]
        note = (f" · saves ~{abs(delta):.1f} min" if delta > 0.5
                else f" · detour adds ~{abs(delta):.1f} min")
        self._log(f"New route: {' → '.join(self.city.stops[s]['name']
                                           for s in self.serve_order)}{note}",
                  "reroute")
        self._last_reroute_clock = self.clock

    # ------------------------------------------------------------------ #
    # scripted auto-demo
    # ------------------------------------------------------------------ #
    def add_scripted_event(self, at: float, rid: str, kind: str,
                           factor: Optional[float] = None) -> None:
        """Queue a disruption to appear at simulated time ``at`` (auto-demo)."""
        self._script.append({"at": at, "rid": rid, "kind": kind, "factor": factor})
        self._script.sort(key=lambda e: e["at"])

    def _fire_scripts(self) -> None:
        while self._script and self._script[0]["at"] <= self.clock:
            ev = self._script.pop(0)
            if ev["rid"] in self.city.roads:
                self.add_disruption(ev["rid"], ev["kind"], factor=ev.get("factor"),
                                    source="script")

    # ------------------------------------------------------------------ #
    # snapshot for the UI
    # ------------------------------------------------------------------ #
    def position(self) -> Tuple[float, float]:
        coords = self.city.coords
        if not self.poly:
            return coords[self.city.depot]
        if self.pt >= len(self.poly) - 1:
            return coords[self.poly[-1]]
        lo, hi = self.offs[self.pt], self.offs[self.pt + 1]
        span = hi - lo
        frac = 0.0 if span <= 1e-9 else (self.travel - lo) / span
        frac = max(0.0, min(1.0, frac))
        a, b = coords[self.poly[self.pt]], coords[self.poly[self.pt + 1]]
        return (a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac)

    def remaining_polyline(self) -> List[Tuple[float, float]]:
        """Node coords still ahead (starting from the van's current spot)."""
        coords = self.city.coords
        if not self.poly:
            return []
        pts = [self.position()]
        start_i = self.pt + 1 if (self.travel - self.offs[self.pt]) > 1e-9 else self.pt
        for i in range(start_i, len(self.poly)):
            pts.append(coords[self.poly[i]])
        return pts

    def etas(self) -> List[dict]:
        """Projected arrival for each remaining stop (service of earlier stops added)."""
        result = []
        marker = getattr(self, "_marker_offs", {})
        svc = 0.0
        for sid in self.serve_order:
            off = marker.get(sid, self.offs[-1])
            eta = self.clock + max(0.0, off - self.travel) + svc
            result.append({"stop": sid, "name": self.city.stops[sid]["name"],
                           "priority": self.city.stops[sid]["priority"],
                           "eta_min": eta})
            svc += self.city.stops[sid]["service"]
        return result

    def snapshot(self) -> dict:
        self.tick()
        new_events = self.log[self._seen:]
        self._seen = len(self.log)
        return {
            "phase": self.phase,
            "clock": self.clock,
            "clock_str": self._clock_str(),
            "timescale": self.timescale,
            "pos": self.position(),
            "remaining_path": self.remaining_polyline(),
            "serve_order": self.serve_order,
            "etas": self.etas(),
            "delivered": list(self.delivered),
            "disruptions": self.disruption_list(),
            "method": self.method,
            "plan_total": self.plan_total,
            "plan_travel": self.plan_travel,
            "stats": dict(self.stats),
            "events": new_events,
            "route_stop_total": len(self.route_stop_ids),
            "history_paths": [[self.city.coords[n] for n in poly]
                              for poly in self.history[-4:]],
        }
