"""Schematic city dataset for the Delivery Command Center.

Everything is generated deterministically (no randomness), so the demo is fully
reproducible. The city is a simple street grid cut by a river: the only roads that
cross the river are two *bridges*. That single bottleneck is what makes roadblock
re-routing dramatic — close the only nearby bridge and the whole route has to
detour around the river.

Coordinate space is a schematic 0..1000 × 0..625 map. Roads are straight segments;
travel minutes = Euclidean length / road speed, so all geometry is exactly the
space the algorithms run on.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

# --------------------------------------------------------------------------- #
# Grid geometry
# --------------------------------------------------------------------------- #
# 7 north-south avenues (columns) and 6 east-west streets (rows).
COL_X = [40, 200, 360, 520, 680, 840, 1000]   # c0 .. c6
ROW_Y = [0, 125, 250, 375, 500, 625]          # r0 .. r5 (r0 = top)
N_COLS = len(COL_X)
N_ROWS = len(ROW_Y)

# Avenue (column) and street (row) display names, west -> east / top -> bottom.
AVENUES = ["Harbor Ave", "Cedar Ave", "Market Ave", "Central Ave",
           "Elm Ave", "Oak Ave", "Pine Ave"]
STREETS = ["Union St", "Main St", "Church St", "State St",
           "Grand St", "Harbor St"]

# The river runs north-south in the gap between Central Ave (c3, x=520) and
# Elm Ave (c4, x=680). Only these two street rows bridge it.
RIVER_LEFT, RIVER_RIGHT = 578.0, 622.0
BRIDGE_ROWS = {1, 4}          # Main St (north bridge) and Grand St (south bridge)

# Road speeds in schematic map-units per minute (higher = faster road).
SPEED_STREET = 260.0
SPEED_BRIDGE = 380.0

# Indexing helper: node id = row * N_COLS + col.
def _nid(row: int, col: int) -> int:
    return row * N_COLS + col


def _dist(a: Sequence[float], b: Sequence[float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


# --------------------------------------------------------------------------- #
# City object
# --------------------------------------------------------------------------- #
class City:
    """Immutable-by-convention description of the road network + delivery world."""

    def __init__(self) -> None:
        self.n: int = N_COLS * N_ROWS
        self.col_x = COL_X
        self.row_y = ROW_Y
        self.avenues = AVENUES
        self.streets = STREETS
        self.bridge_rows = BRIDGE_ROWS
        self.river_left = RIVER_LEFT
        self.river_right = RIVER_RIGHT

        # node coordinates, index == node id
        self.coords: List[tuple] = [
            (COL_X[c], ROW_Y[r]) for r in range(N_ROWS) for c in range(N_COLS)
        ]

        # roads: road_id -> {a, b, name, speed, kind, minutes}
        self.roads: Dict[str, dict] = {}
        self._build_roads()

        # delivery stops and van configuration are added in build_city() so the
        # constructor stays reusable; see build_city() below.
        self.stops: Dict[str, dict] = {}
        self.stop_ids: List[str] = []
        self.items: List[dict] = []
        self.depot: int = 0
        self.config: dict = {}

    # ------------------------------------------------------------------ #
    def _add_road(self, a: int, b: int, name: str, speed: float, kind: str) -> None:
        rid = f"R{len(self.roads)}"
        self.roads[rid] = {
            "id": rid, "a": a, "b": b, "name": name,
            "speed": speed, "kind": kind,
            "minutes": _dist(self.coords[a], self.coords[b]) / speed,
        }

    def _build_roads(self) -> None:
        # Horizontal streets (bridges replace the single edge that would cross the
        # river on non-bridge rows).
        for r in range(N_ROWS):
            for c in range(N_COLS - 1):
                if c == 3 and r not in BRIDGE_ROWS:
                    # river gap: no road on this row
                    continue
                if c == 3:  # this is the bridge span
                    self._add_road(_nid(r, c), _nid(r, c + 1),
                                   f"{STREETS[r]} Bridge", SPEED_BRIDGE, "bridge")
                else:
                    self._add_road(_nid(r, c), _nid(r, c + 1),
                                   STREETS[r], SPEED_STREET, "street")
        # Vertical avenues.
        for c in range(N_COLS):
            for r in range(N_ROWS - 1):
                self._add_road(_nid(r, c), _nid(r + 1, c),
                               AVENUES[c], SPEED_STREET, "street")

    # ------------------------------------------------------------------ #
    def adjacency(self, disruptions: Optional[Dict[str, dict]] = None):
        """Effective adjacency list honouring active disruptions.

        ``disruptions`` maps a road id -> dict with at least ``{"kind": ...}`` where
        kind is ``"roadblock"`` (road unusable) or ``"traffic"`` (road slowed by
        ``disruptions[rid]["factor"]``, default 3.0). Returns ``adj`` where
        ``adj[u] = [(v, minutes), ...]``. A roadblock simply omits both directed
        edges, which is exactly what makes Dijkstra take a detour.
        """
        disruptions = disruptions or {}
        adj: List[List[tuple]] = [[] for _ in range(self.n)]
        for rid, road in self.roads.items():
            d = disruptions.get(rid)
            if d is not None and d.get("kind") == "roadblock":
                continue  # closed: contributes no edges
            minutes = road["minutes"]
            if d is not None and d.get("kind") == "traffic":
                minutes *= float(d.get("factor", 3.0))
            adj[road["a"]].append((road["b"], minutes))
            adj[road["b"]].append((road["a"], minutes))
        return adj


# --------------------------------------------------------------------------- #
# Items attached to each stop (so a loaded item implies a delivery stop)
# --------------------------------------------------------------------------- #
# Each preset is (name, weight kg, value). Every stop offers these four products.
_PRESETS: Dict[str, List[tuple]] = {
    "fire": [("Fire extinguisher lot", 30, 280), ("Rope coils", 22, 170),
             ("First-response kit", 26, 330), ("Hydrant fittings", 40, 190)],
    "hospital": [("Oxygen cylinder", 55, 320), ("Vaccine cooler", 28, 520),
                 ("PPE kit box", 18, 260), ("Surgical set", 24, 300)],
    "clinic": [("Diagnostics kit", 14, 190), ("Bandage carton", 9, 140),
               ("Sample cooler", 20, 230), ("Glove case", 12, 120)],
    "pharmacy": [("Paracetamol carton", 12, 180), ("First-aid kit", 16, 220),
                 ("Syrup batch", 22, 200), ("Vitamins crate", 10, 240)],
    "school": [("Textbook crate", 30, 140), ("Science kit", 18, 200),
               ("Sports kit", 22, 160), ("Stationery box", 15, 110)],
    "electronics": [("Smart TV", 19, 540), ("Laptop carton", 12, 520),
                    ("Phone lot", 8, 300), ("Router box", 6, 260)],
    "mall": [("Appliance unit", 48, 420), ("Clothing rack", 25, 180),
             ("Shoe lot", 20, 230), ("Home gadget", 16, 200)],
    "grocery": [("Apple crates", 28, 95), ("Veggie box", 24, 80),
                ("Dairy cooler", 40, 150), ("Juice pallet", 55, 120)],
    "market": [("Rice sack", 50, 110), ("Pasta bulk box", 45, 100),
               ("Frozen goods crate", 30, 130), ("Detergent pallet", 60, 90)],
    "diner": [("Coffee bag", 18, 140), ("Pastry box", 15, 120),
              ("Frozen patties", 35, 95), ("Drink crate", 25, 85)],
    "bookstore": [("Novel crates", 22, 150), ("Magazine pack", 7, 210),
                  ("Kids' books box", 18, 140), ("Art prints", 9, 260)],
    "cafe": [("Roast beans", 16, 170), ("Cake box", 10, 150),
             ("Cup supply", 24, 90), ("Napkin carton", 20, 70)],
}

# (id, name, row, col, priority, service_min, deadline_min, category)
# priority: 1 = critical, 2 = high, 3 = normal. deadline_min = latest arrival after
# departure that still counts as "on time" (None = no deadline, normal stops).
_STOP_SPECS: List[tuple] = [
    ("fire",    "City Fire Station #2", 1, 4, 1, 2.0, 12, "fire"),
    ("hospital","Central Hospital",     2, 5, 1, 3.0, 20, "hospital"),
    ("clinic",  "Community Clinic",     4, 3, 2, 2.0, 22, "clinic"),
    ("pharmacy","Grand Pharmacy",       2, 1, 2, 1.5, 22, "pharmacy"),
    ("school",  "Sunrise High School",  5, 1, 2, 2.0, 30, "school"),
    ("electronics","Metro Electronics", 3, 5, 2, 1.5, 30, "electronics"),
    ("mall",    "Central Mall",         5, 4, 2, 2.5, 34, "mall"),
    ("grocery", "FreshCo Grocery",      3, 0, 3, 1.5, None, "grocery"),
    ("market",  "Northgate Market",     5, 0, 3, 2.0, None, "market"),
    ("diner",   "Harbor Diner",         5, 6, 3, 1.5, None, "diner"),
    ("bookstore","Book Nook",           1, 6, 3, 1.0, None, "bookstore"),
    ("cafe",    "Park Cafe",            0, 5, 3, 1.0, None, "cafe"),
]

CONFIG = {
    # Van
    "van_capacity_kg": 430,
    "capacity_min": 80,
    "capacity_max": 900,
    # Knapsack objective: score = value + premium * (3 - priority)  [P1 bonus 2*premium]
    "priority_premium_min": 0,
    "priority_premium_max": 500,
    "priority_premium_default": 220,
    # Routing objective: cost = travel + strictness * sum(pw * position)
    "strictness_min": 0.0,
    "strictness_max": 12.0,
    "strictness_default": 4.0,
    # Simulation clock: sim-minutes advanced per real second at 1x
    "time_scale_default": 1.0,
    "service_at_depot_min": 3.0,
    # Exactness guard for the Held-Karp DP (route stops beyond this -> NN+2-opt).
    "tsp_dp_max_stops": 12,
}


def build_city() -> City:
    """Construct the full demo world: roads, depot, stops, items, van config."""
    city = City()
    city.depot = _nid(0, 0)  # top-left corner

    # Stops
    city.stop_ids = [s[0] for s in _STOP_SPECS]
    for sid, name, row, col, prio, svc, dl, cat in _STOP_SPECS:
        city.stops[sid] = {
            "id": sid, "name": name, "node": _nid(row, col),
            "priority": prio, "service": svc, "deadline": dl, "category": cat,
        }

    # Items — every stop offers its four preset products. A loaded item therefore
    # implies a visit to its destination stop.
    idx = 0
    for sid, name, row, col, prio, svc, dl, cat in _STOP_SPECS:
        for pname, w, v in _PRESETS[cat]:
            city.items.append({
                "id": f"I{idx:02d}", "name": pname, "to": sid,
                "weight": w, "value": v, "priority": prio,
            })
            idx += 1

    city.config = dict(CONFIG)
    return city
