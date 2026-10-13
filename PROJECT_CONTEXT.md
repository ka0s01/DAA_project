# Delivery Command Center — Complete Project Context

> **What this file is for.** This is a self-contained technical briefing on the whole
> project: what it does, how every part works, the exact algorithms and their
> complexity, the data it runs on, the measured results, and the honest caveats.
> It is written so that a project report can be generated from it against *any*
> required format, without needing to re-read the source.
>
> **How to use it.** Treat this file as the raw material / source of truth. Numbers
> in §13 and §16 were produced by actually running the code in this repository —
> cite them rather than inventing new ones. §20 is a ready-made mapping from common
> report sections to the sections of this file that supply them. §21 lists the
> personal details a report must fill in (name, course, date).
>
> **Related documents in the repo:** `README.md` (quick orientation), `REPORT.md`
> (an existing DAA write-up already in report prose), `GUIDE.md` (plain-English
> explainer of every control), `DEMO.md` (live demo script). This file is
> deliberately more exhaustive and more mechanical than all of them.

---

## 0. Table of contents

1. [One-paragraph summary](#1-one-paragraph-summary)
2. [The problem being solved](#2-the-problem-being-solved)
3. [Glossary and notation](#3-glossary-and-notation)
4. [Formal model](#4-formal-model)
5. [The dataset: the schematic city](#5-the-dataset-the-schematic-city)
6. [Algorithm 1 — 0/1 knapsack (exact DP)](#6-algorithm-1--01-knapsack-exact-dp)
7. [Algorithm 2 — Dijkstra shortest road time](#7-algorithm-2--dijkstra-shortest-road-time)
8. [Algorithm 3 — Held–Karp exact TSP with position-aware cost](#8-algorithm-3--heldkarp-exact-tsp-with-position-aware-cost)
9. [Algorithm 4 — Nearest neighbour + 2-opt fallback](#9-algorithm-4--nearest-neighbour--2-opt-fallback)
10. [The planning layer: how the algorithms are composed](#10-the-planning-layer-how-the-algorithms-are-composed)
11. [The simulation engine: live re-routing](#11-the-simulation-engine-live-re-routing)
12. [The web layer: Flask API](#12-the-web-layer-flask-api)
13. [The frontend: the three-panel dashboard](#13-the-frontend-the-three-panel-dashboard)
14. [Executable entry points](#14-executable-entry-points)
15. [Measured results: every experiment table](#15-measured-results-every-experiment-table)
16. [Verified end-to-end run (headless transcript)](#16-verified-end-to-end-run-headless-transcript)
17. [Test coverage](#17-test-coverage)
18. [Complexity summary and measured timings](#18-complexity-summary-and-measured-timings)
19. [Design decisions and trade-offs](#19-design-decisions-and-trade-offs)
20. [Known caveats, bugs and honest limitations](#20-known-caveats-bugs-and-honest-limitations)
21. [Numbers cheat-sheet](#21-numbers-cheat-sheet)
22. [Repository map](#22-repository-map)
23. [How to build, run and reproduce](#23-how-to-build-run-and-reproduce)
24. [Mapping to typical report sections](#24-mapping-to-typical-report-sections)
25. [Details the report must fill in](#25-details-the-report-must-fill-in)

---

## 1. One-paragraph summary

**Delivery Command Center** is a delivery-route optimiser built as a management
console for a delivery manager, submitted as a *Design & Analysis of Algorithms*
course project. It solves two classical optimisation problems and — this is the
point of the project — **couples them through priority** rather than stacking them
side by side:

* **What to load into the van** is an exact **0/1 knapsack** solved by dynamic
  programming in `O(n·W)`, where a manager-adjustable **priority premium** raises the
  effective value of critical goods so they win ties when the van cannot carry
  everything.
* **In what order to visit the stops** is a **priority-aware Travelling Salesman
  Problem** solved *exactly* by the **Held–Karp DP** in `O(k²·2^k)`, where serving a
  high-priority stop late in the run is priced into the objective via a
  **punctuality weight λ**. A **nearest-neighbour + 2-opt** heuristic is the
  polynomial fallback for oversized instances.
* **Every pair-wise travel time** between stops is a **Dijkstra** shortest road path
  over the actual road network, so a closed bridge or a traffic jam genuinely changes
  both the route and its cost.
* **Nothing stays static.** The van drives on a simulated clock; when a roadblock or
  traffic jam appears *ahead of the van* mid-run, the system re-plans **from the van's
  current position** over the remaining stops (Held–Karp with `start ≠ home`: an open
  path that must still finish at the depot) and the van visibly detours.

The world is a hand-drawn schematic street grid (42 nodes, 67 roads) cut by a river
crossed by **exactly two bridges**, so closing a bridge is guaranteed to produce a
dramatic, visible detour. Everything is deterministic — no randomness anywhere in the
dataset — so every demonstration and every number in this document is reproducible.

---

## 2. The problem being solved

### 2.1 The business framing

A delivery manager with one van has to answer, every morning:

1. **Which of the orders on the shelf actually go in the van today?** The van has a
   weight limit; orders have weights and business values; some orders are critical
   (hospital oxygen cylinders, fire-hydrant fittings) and some are ordinary stock.
   Leaving a critical order behind is much worse than leaving an ordinary one.
2. **In what order does the van visit the stops?** A route that returns to the depot
   must be chosen. The shortest possible route may serve a critical stop *last*,
   which is unacceptable when the load contains life-saving goods.
3. **What happens when the city gets in the way?** Roads close; roads slow down.
   A plan made at the depot is stale the moment the van meets a closed bridge. The
   route has to be re-decided **while the van is already driving**, from wherever it
   currently is.

The project is built as a **web dashboard** rather than a script so that the
algorithms are exercised through a realistic management workflow: plan the load,
see the route on a map, dispatch the van, close a bridge mid-run, watch it re-route.

### 2.2 Why this is an algorithms project (and not a CRUD app)

Three things make it a genuine Design & Analysis of Algorithms piece:

| Element | Algorithmic content |
| --- | --- |
| Load decision | 0/1 knapsack, exact DP, `O(n·W)` — NP-hard problem solved exactly by exploiting the integer capacity as a pseudo-polynomial parameter |
| Sequencing decision | Symmetric TSP, exact Held–Karp DP over subsets, `O(k²·2^k)` — NP-hard problem solved exactly for realistically small `k` |
| Distance between any two stops | Dijkstra, `O((V+E) log V)`, re-run over the *disrupted* graph |
| Mid-run re-planning | The same TSP DP re-invoked with a different start node and a shrinking stop set → an **open** path (van position → … → depot) rather than a closed tour |
| Fast fallback | Nearest neighbour + 2-opt local search, polynomial, measured gap against the exact optimum |

The two headline claims the course emphasises are:

* **Priority coupling** — the *same* priority tier data drives both the loading
  objective (premium) and the routing objective (λ), so the two algorithms are linked
  by a shared business concept, not just executed in sequence.
* **Live re-routing** — disruption handling happens *during* the run, from the van's
  actual position, not as a pre-computed "what if" table.

### 2.3 Scope and non-goals

* Simulated, deterministic city — no real map data, no map SDK; the map is drawn as
  inline SVG from generated coordinates.
* One van, one depot, one manager session.
* Priority tiers are fixed (P1/P2/P3), but their weights in both objectives are
  manager-adjustable sliders — which is exactly what exposes the trade-offs.
* Delivery **deadlines** exist in the data and are reported as lateness statistics,
  but are *not* part of the optimisation objective (see §20.6). This is an honest,
  stated limitation, not an oversight to hide.

---

## 3. Glossary and notation

| Term | Meaning in this project |
| --- | --- |
| **Depot** | Node 0, top-left corner of the map `(40, 0)`. Every route starts and ends here. |
| **Node** | One intersection of the street grid. Node id = `row * 7 + col`, 42 nodes total. |
| **Road** | An undirected edge between two adjacent nodes; has a name, a kind (`street` or `bridge`), a speed and a base travel time in minutes. |
| **Bridge** | One of exactly two roads that cross the river. Closing one is the dramatic demo event. |
| **Stop** | A delivery location (fire station, hospital, …), one per distinct grid node. 12 stops. |
| **Item** | A physical parcel with weight (kg), base value, priority tier and a destination stop. 48 items, 4 per stop. |
| **Priority tier** | `P1` = critical, `P2` = high, `P3` = normal. Encoded as `1/2/3`. |
| **Priority premium** (`π`, `premium`) | Loading-side knob. Effective value of item `i` is `v_i + π·(3 − p_i)`. Range 0–500, default 220. |
| **Punctuality λ** (`strictness`) | Routing-side knob. Objective adds `λ · Σ pw(stop) · position`. Range 0–12, default 4.0. |
| **Priority weight** (`pw`) | `{P1: 3, P2: 2, P3: 1}` — how much a tier cares about being early. |
| **Disruption** | A roadblock (`closed`) or a traffic slowdown (`slowed ×f`) applied to one road id. |
| **Re-route** | Re-solving the TSP from the van's current node over the remaining stops under the current disruptions. |
| **Ghost route** | The dashed polyline of a previous route kept on the map after a re-route (last 4 kept). |
| **Scope** | Which stops the route visits: `loaded` (only stops that received cargo), `critical` (only stops with P1/P2 cargo), `all` (every stop with a deliverable item). |

Notation used below: `G = (V, E)` graph, `k` = number of stops on the route,
`n` = number of candidate items, `W` = van capacity in kg, `d(a,b)` = shortest
effective travel time between nodes `a` and `b`.

---

## 4. Formal model

### 4.1 The road network

The city is an undirected weighted graph `G = (V, E)` with `|V| = 42` nodes and
`|E| = 67` roads (65 streets + 2 bridges). Each road `e` has a base travel time
`t(e)` = Euclidean length ÷ road speed.

A disruption map `D : E → {open, traffic(f), closed}` turns the base time into an
*effective* weight used by every shortest-path search:

```
w_D(e) = t(e)              if e is open
         t(e) · f          if e has traffic with slowdown factor f ≥ 1  (default f = 3)
         (edge removed)    if e is roadblocked
```

A roadblock is implemented by simply omitting both directed edges from the
adjacency list — which is precisely what makes Dijkstra take a detour
(`core/city.py:City.adjacency`).

### 4.2 The catalogue

A catalogue of `n = 48` items. Item `i` has:

* weight `w_i` (kg),
* base value `v_i`,
* priority tier `p_i ∈ {1, 2, 3}`,
* destination stop `s(i)`.

Because a loaded item must physically be delivered, **loading implies routing**: the
set of items chosen by the knapsack induces the set of stops the route must visit.

### 4.3 Loading decision — 0/1 knapsack with a priority premium

With capacity `W` and premium `π ≥ 0`, define the *effective value*

```
v_i' = v_i + π · (3 − p_i)          # P1 bonus = 2π,  P2 bonus = π,  P3 bonus = 0
```

and solve

```
maximise   Σ_i v_i' · x_i
subject to Σ_i w_i · x_i ≤ W,     x_i ∈ {0, 1}
```

The premium is what makes a critical item win a tie against a slightly more
valuable ordinary item when the van cannot take both. At `π = 0` the model is the
plain textbook knapsack (§15, table [3]).

### 4.4 Routing decision — priority-aware TSP

Let `S` be the stops to visit (`k = |S|`), `d(a,b)` the shortest effective travel
time (Dijkstra on `(G, w_D)`), the depot be node `0`, and `π` denote a visiting
permutation. With punctuality weight `λ ≥ 0` and priority weights
`pw = {P1: 3, P2: 2, P3: 1}`:

```
C(π) = d(0, π₁) + Σ_{t=1..k−1} d(π_t, π_{t+1}) + d(π_k, 0)      ← travel (closed tour)
       + λ · Σ_{t=1..k} pw(p(π_t)) · t                            ← priority penalty
```

The first line is the classical closed-tour travel cost. The second line prices
**how late** each stop is served: a stop served at position `t` pays its priority
weight times `t`. Pushing a P1 stop from position 1 to position 6 therefore costs
`3λ · 5` in objective units.

> **Unit note for the report:** `C(π)` is a *cost*, not a duration. The travel part
> is in minutes; the penalty part is in priority-cost units scaled by λ. Adding them
> is the modelling choice that makes priority tractable inside one objective. At
> λ = 4 the default route's total is `18.3 + 304.0 = 322.3`; the 304.0 is *not*
> 304 minutes (see §15 table [4] and §20.5).

### 4.5 Mid-run re-planning

Mid-run, at the van's current node `v`, with the set of still-undelivered stops
`S_rem ⊆ S`, under an *updated* disruption map `D'`, the same objective is solved but
with `d(v, ·)` as the start:

```
C'(π) = d(v, π₁) + Σ … + d(π_last, 0)  +  λ · Σ pw(p(π_t)) · t
```

i.e. the closed tour becomes an **open path** that starts at the van and must still
finish at the depot. This is exactly Held–Karp with `start ≠ home` (`§8.6`).

---

## 5. The dataset: the schematic city

Everything is generated in `core/city.py` by `build_city()`. **There is no
randomness** — every run of every script produces identical data, so the demo and the
report numbers are fully reproducible.

### 5.1 Geometry

* 7 north–south **avenues** (columns) at x = `40, 200, 360, 520, 680, 840, 1000`
  → `["Harbor Ave", "Cedar Ave", "Market Ave", "Central Ave", "Elm Ave", "Oak Ave", "Pine Ave"]`
* 6 east–west **streets** (rows) at y = `0, 125, 250, 375, 500, 625`
  → `["Union St", "Main St", "Church St", "State St", "Grand St", "Harbor St"]`
* Node id = `row * 7 + col` → `42` nodes. Node 0 = depot = `(40, 0)`, top-left.
* Roads are straight segments; travel time = Euclidean length ÷ speed.
* Speeds: `SPEED_STREET = 260` and `SPEED_BRIDGE = 380` map-units per minute.

Resulting road times (exact, from the dataset):

| Road kind | Count | Length (units) | Minutes per road |
| --- | --- | --- | --- |
| Horizontal street segment | — | 160 | `0.6154` |
| Vertical avenue segment | — | 125 | `0.4808` |
| Bridge span | 2 | 160 | `0.4211` (faster road) |
| **Total roads** | **67** (65 street + 2 bridge) | | |

### 5.2 The river and the two bridges

The river runs north–south in the gap between Central Ave (x = 520) and Elm Ave
(x = 680), occupying `x ∈ [578, 622]`. Horizontally, every street row would cross it
between column 3 and column 4 — **but on four of the six rows that edge simply does
not exist**. Only two rows bridge the river:

* **Main St Bridge** (row 1) — the north bridge
* **Grand St Bridge** (row 4) — the south bridge

This single design decision is the engine of the whole dynamic demo: because the
river *severs* the grid except at two points, closing the bridge the van was about to
use forces a long, visible detour (§15 table [5]: `+7.7 min / +42%` for Main St), and
closing **both** bridges makes far-bank stops genuinely unreachable — a case the code
detects and reports rather than crashing (§10.5).

### 5.3 Road inventory check

```
Horizontal: 6 rows × 6 spans − 4 missing river spans = 32
Vertical:   7 columns × 5 spans                    = 35
Total = 67 roads   (48 of the horizontal spans are ordinary street, 2 are bridges)
Nodes = 6 × 7 = 42
```

`algo_tests.py::test_city_invariants` asserts the network is fully connected, that
exactly two bridges exist, that roads have positive time, that adjacency is
symmetric and consistent with road times, and that every item points at a real stop.

### 5.4 Delivery stops (12)

One stop per distinct node; depot excluded. `dl` = latest arrival (minutes after
departure) that still counts as on time; `None` = no deadline. `svc` = service time
in minutes (the van dwells this long when it arrives).

| id | name | node | (row,col) | priority | service (min) | deadline (min) |
| --- | --- | --- | --- | --- | --- | --- |
| `fire` | City Fire Station #2 | 11 | (1,4) | **P1** | 2.0 | 12 |
| `hospital` | Central Hospital | 19 | (2,5) | **P1** | 3.0 | 20 |
| `clinic` | Community Clinic | 31 | (4,3) | P2 | 2.0 | 22 |
| `pharmacy` | Grand Pharmacy | 15 | (2,1) | P2 | 1.5 | 22 |
| `school` | Sunrise High School | 36 | (5,1) | P2 | 2.0 | 30 |
| `electronics` | Metro Electronics | 26 | (3,5) | P2 | 1.5 | 30 |
| `mall` | Central Mall | 39 | (5,4) | P2 | 2.5 | 34 |
| `grocery` | FreshCo Grocery | 21 | (3,0) | P3 | 1.5 | — |
| `market` | Northgate Market | 35 | (5,0) | P3 | 2.0 | — |
| `diner` | Harbor Diner | 41 | (5,6) | P3 | 1.5 | — |
| `bookstore` | Book Nook | 13 | (1,6) | P3 | 1.0 | — |
| `cafe` | Park Cafe | 5 | (0,5) | P3 | 1.0 | — |

Note that the two P1 stops (`fire`, `hospital`) are the two with the **tightest
deadlines** (12 and 20 minutes) — the dataset is built so that prioritisation and
punctuality point the same way, and so that running them late is visibly punished.

### 5.5 Item catalogue (48 items = 12 stops × 4 products)

Each stop "sells" four preset products; the item's priority tier equals its
destination stop's tier. Examples:

| category | items (name, kg, value) |
| --- | --- |
| fire | Fire extinguisher lot (30, 280), Rope coils (22, 170), First-response kit (26, 330), Hydrant fittings (40, 190) |
| hospital | Oxygen cylinder (55, 320), Vaccine cooler (28, 520), PPE kit box (18, 260), Surgical set (24, 300) |
| clinic | Diagnostics kit (14, 190), Bandage carton (9, 140), Sample cooler (20, 230), Glove case (12, 120) |
| pharmacy | Paracetamol carton (12, 180), First-aid kit (16, 220), Syrup batch (22, 200), Vitamins crate (10, 240) |
| school | Textbook crate (30, 140), Science kit (18, 200), Sports kit (22, 160), Stationery box (15, 110) |
| electronics | Smart TV (19, 540), Laptop carton (12, 520), Phone lot (8, 300), Router box (6, 260) |
| mall | Appliance unit (48, 420), Clothing rack (25, 180), Shoe lot (20, 230), Home gadget (16, 200) |
| grocery | Apple crates (28, 95), Veggie box (24, 80), Dairy cooler (40, 150), Juice pallet (55, 120) |
| market | Rice sack (50, 110), Pasta bulk box (45, 100), Frozen goods crate (30, 130), Detergent pallet (60, 90) |
| diner | Coffee bag (18, 140), Pastry box (15, 120), Frozen patties (35, 95), Drink crate (25, 85) |
| bookstore | Novel crates (22, 150), Magazine pack (7, 210), Kids' books box (18, 140), Art prints (9, 260) |
| cafe | Roast beans (16, 170), Cake box (10, 150), Cup supply (24, 90), Napkin carton (20, 70) |

Items are addressed as `I00 … I47`, in stop order then preset order. Total catalogue
weight is far above the van capacity, so the knapsack is a real decision at every
capacity setting (§15 table [2]).

### 5.6 Van and simulation configuration

From `CONFIG` in `core/city.py`:

| Key | Value | Meaning |
| --- | --- | --- |
| `van_capacity_kg` | 430 | default capacity |
| `capacity_min` / `capacity_max` | 80 / 900 | slider bounds |
| `priority_premium_min/max/default` | 0 / 500 / **220** | loading premium π |
| `strictness_min/max/default` | 0.0 / 12.0 / **4.0** | punctuality λ |
| `time_scale_default` | 1.0 | sim-minutes per real second at 1× (UI allows 1–6×) |
| `service_at_depot_min` | 3.0 | ⚠ declared but **never read** — see §20.4 |
| `tsp_dp_max_stops` | 12 | ⚠ declared but **never read**; the real cap is the `max_dp_stops=12` default argument of `solve_route`. See §20.4 |

---

## 6. Algorithm 1 — 0/1 knapsack (exact DP)

**Implementation:** `core/algorithms.py:knapsack_01(weights, values, capacity)`

**Purpose in the project:** decide which items fit in the van. Called from
`core/routing.py:plan_load`, which first maps each item to its *effective* value
`v_i + π·(3 − p_i)`.

### 6.1 Recurrence

Let `V[i][c]` be the best total value achievable using the first `i` items with a
knapsack of capacity `c`:

```
V[0][c] = 0                                              for all c
V[i][c] = V[i−1][c]                                      if w_i > c
V[i][c] = max( V[i−1][c],  v_i + V[i−1][c − w_i] )       otherwise
```

The answer is `V[n][W]`.

### 6.2 Pseudocode

```
KNAPSACK-01(w[1..n], v[1..n], W)
  allocate dp[(n+1) × (W+1)] = 0
  for i = 1 to n
      for c = 0 to W
          if w[i] > c:  dp[i][c] = dp[i−1][c]
          else:         dp[i][c] = max(dp[i−1][c], v[i] + dp[i−1][c − w[i]])
  # reconstruct the chosen subset by walking the table backwards
  chosen = []
  c = W
  for i = n down to 1
      if dp[i][c] != dp[i−1][c]:      # item i was taken
          chosen.append(i);  c = c − w[i]
  return dp[n][W], reverse(chosen)
```

### 6.3 Complexity

* Time `O(n·W)`, space `O(n·W)`.
* Here `n = 48` candidate items and `W ≤ 900` kg, so the DP table is at most
  `49 × 901 ≈ 44 000` cells — solved in well under a millisecond.
* The DP table is kept in full (rather than the usual two rolling rows) precisely so
  the chosen subset can be reconstructed by walking backwards.

### 6.4 Correctness argument

By induction on `i`: assume `V[i−1][·]` is optimal for the first `i−1` items. For
item `i` either it is excluded — then the optimum is `V[i−1][c]` — or it is included,
which is only possible if `w_i ≤ c`, and then the best value is `v_i` plus the
optimum for the remaining capacity `c − w_i`, which by the inductive hypothesis is
`V[i−1][c − w_i]`. Taking the maximum of the only two cases gives `V[i][c]`. ∎

### 6.5 Notes

* Weights, values and capacity are integers, so the DP is exact — no rounding.
* An item heavier than the whole capacity is never chosen (checked by a test).
* The premium only ever enters through the values array; the algorithm itself is
  completely unaware of "priority". This keeps the algorithm textbook-pure and puts
  the business modelling in `core/routing.py:item_score`.

---

## 7. Algorithm 2 — Dijkstra shortest road time

**Implementation:** `core/algorithms.py:dijkstra(adj, start)` and
`core/algorithms.py:shortest_path(adj, start, end)`

**Purpose in the project:** every distance the TSP ever sees is a Dijkstra shortest
road path over the *currently disrupted* network. It is also used to draw/simulate
the van actually following roads (`route_geometry`), and to test reachability when
the river is severed.

### 7.1 Pseudocode

```
DIJKSTRA(adj, start)
  dist[*] = ∞ ;  prev[*] = nil ;  dist[start] = 0
  PQ = min-heap containing (0, start)
  while PQ not empty
      (d, u) = extract-min(PQ)
      if d > dist[u]: continue                 # stale heap entry
      for each (v, w) in adj[u]
          nd = d + w
          if nd < dist[v] − ε:                 # ε = 1e−12 guards float noise
              dist[v] = nd ;  prev[v] = u
              push (nd, v) into PQ
  return dist, prev
```

`shortest_path` then walks `prev` backwards from `end` and reverses the result; it
raises `ValueError` if `end` is unreachable.

### 7.2 Complexity

* `O((V + E) log V)` with a binary heap: each edge is relaxed at most once and each
  vertex is popped at most once. On this city: `V = 42`, `E = 67` (134 directed
  edges) — sub-millisecond.

### 7.3 Correctness argument

Classic greedy invariant: when a vertex `u` is popped with tentative distance `d`,
`d` is final. All edge weights are non-negative, so any not-yet-final path to `u`
would have to leave the settled set through some frontier vertex whose distance is at
least `d`, and can only grow from there. ∎

### 7.4 Why Dijkstra here

* Weights are non-negative (travel times), so Dijkstra is optimal and faster than
  Bellman–Ford.
* All-pairs Floyd–Warshall (`O(V³) = 74k` operations) would also have worked for a
  42-node city, and would be simpler to cache — Dijkstra-per-source was chosen
  because it maps directly onto "one shortest-path tree per start node", reuses the
  same adjacency that honours disruptions, and keeps the graph layer honest
  (`build_matrix` runs exactly `k+2` Dijkstra calls per planning invocation).
* A* was not used: there is no meaningful admissible potential function beyond
  Euclidean distance, and the graph is tiny.

---

## 8. Algorithm 3 — Held–Karp exact TSP with position-aware cost

**Implementation:** `core/algorithms.py:tsp_held_karp(matrix, start, home, node_cost, return_to_start)`

**Purpose in the project:** choose the visiting order. This is the heart of the
routing decision and of the "priority is priced into the route" claim.

### 8.1 The state

With `others` = the `m` nodes to be visited (all stops that are neither the start nor
the finish), define a bitmask `mask` over `others` and

```
dp[mask][k] = minimum cost of a path that
              starts at `start`,
              visits exactly the set `mask` (bit k set ⇔ others[k] visited),
              and ends at others[k].
```

`c(mask) = popcount(mask)` is the number of stops already visited — which is also
exactly the **position** at which the next stop will be served.

### 8.2 Recurrence (including the priority penalty)

```
dp[{k}][k]        = d(start, others[k]) + cost(others[k], 1)

dp[mask | {j}][j] = min over k ∈ mask of
                      dp[mask][k] + d(others[k], others[j]) + cost(others[j], c(mask)+1)

answer            = min over k of  dp[full][k] + d(others[k], home)
```

where `cost(node, position)` is the optional additive **position cost** hook, set by
the routing layer to

```
cost(node, position) = λ · pw(priority(node)) · position
```

### 8.3 Why the position cost keeps the DP exact (the key insight)

The priority penalty depends on the visit position, which naively looks like it
breaks the "optimal substructure" requirement of a DP: the cost of a stop depends on
how many stops came before it. It does not break anything **because the position is a
function of the state alone** — when at state `(mask, k)`, the number of stops already
visited is `c(mask)` for every path that reaches that state, regardless of *which*
order produced it. So the added term is a well-defined function of `(mask, k)`, the
subproblem value is still uniquely defined, and the recurrence remains exact.

This is the single most interesting technical point in the project and is worth
stating explicitly in a report. It is also directly verified by
`algo_tests.py::test_held_karp_with_position_costs`, which checks the DP against
permutation brute force with an arbitrary position-dependent cost function.

### 8.4 Pseudocode

```
HELD-KARP(matrix, start, home, cost)
  others = all nodes except start and home ;  m = |others|
  full = (1 << m) − 1
  dp[1<<k][k] = d(start, others[k]) + cost(others[k], 1)        for each k
  for mask = 0 .. (1<<m)−1
      visited = popcount(mask)
      for k in mask
          for j not in mask
              candidate = dp[mask][k] + d(others[k], others[j]) + cost(others[j], visited+1)
              if candidate < dp[mask | 1<<j][j]:
                  dp[mask | 1<<j][j] = candidate ;  parent[mask | 1<<j][j] = (mask, k)
  best = min over k of dp[full][k] + d(others[k], home)
  reconstruct order by following `parent` backwards from (full, argmin k)
  return best, order
```

The `parent` table is what allows the actual order (not just the cost) to be
recovered. Reconstructed seed states (single-bit masks) have no parent, which is the
loop's stopping condition.

### 8.5 Complexity

* Time `O(m² · 2^m)`; space `O(m · 2^m)`. Since `m = k` for a depot-to-depot tour
  (start and home are the same node), this is the standard `O(k² · 2^k)` TSP DP.
* With `k ≤ 12` (the cap), the largest DP is `2^12 × 12 ≈ 49k` states — measured at
  `76.6 ms` for `k = 12` (§18). `k = 16` would already cost `3.2 s`, which is why the
  cap exists.
* Exactness is affordable here because a real delivery run visits a handful of stops;
  the exponential is in the number of *stops*, not in the size of the city.

### 8.6 The `start ≠ home` case (used by live re-routing)

`home` can name a *different* finish node than `start`. During a mid-run re-plan the
van is somewhere in the city, so `start` = the van's current node and `home` = the
depot. The DP handles this naturally: `others` excludes both `start` and `home`, the
seed edges come from `start`, and the closing edges go to `home`. Result: an **open
path** from the van back to the depot — no edge is ever added between the van's
position and itself.

`return_to_start` is kept for backwards compatibility and is shorthand for
`home = start`.

This is verified by `algo_tests.py::test_held_karp_open_route_home_different` against
brute force over random start/home pairs.

### 8.7 Correctness argument

Suppose an optimal route ends with `others[j]` at position `c(mask)+1` having visited
exactly `mask ∪ {j}`. The prefix of that route that visits `mask` and ends at
`others[k]` must itself be optimal for the subproblem `(mask, k)` — otherwise swapping
in the better prefix would strictly improve the whole route, contradicting
optimality. Therefore the recurrence, which takes the minimum over exactly these
optimal prefixes, produces the optimum. Induction over `|mask|` gives the base cases.
∎

---

## 9. Algorithm 4 — Nearest neighbour + 2-opt fallback

**Implementation:** `core/algorithms.py:tsp_nearest_neighbor_2opt(matrix, start, home, improvement_passes)`

**Purpose in the project:** a polynomial route builder for instances too large for the
exact DP (`k > max_dp_stops`, default 12) — the exactness guard required by §18's
growth measurements. On the current dataset the largest route is `k = 12` (scope
"every stop"), so the exact solver is always used in practice; the fallback exists
for correctness of the design and is measured in §15 table [6].

### 9.1 Stage 1 — nearest neighbour

```
seq = [start];  unvisited = others;  cur = start
while unvisited not empty
    nxt = argmin over j in unvisited of d(cur, j)
    append nxt to seq ;  remove nxt ;  cur = nxt
append home to seq
```

Greedy, `O(n²)`, and can be arbitrarily bad in the worst case.

### 9.2 Stage 2 — 2-opt local search

For a path `seq[0] = start … seq[L−1] = home`, a **2-opt move** reverses a contiguous
block `seq[i..k]`, replacing the two edges `(a,b)` and `(c,d)` with `(a,c)` and
`(b,d)`, where `a = seq[i−1], b = seq[i], c = seq[k], d = seq[k+1]`:

```
gain(i,k) = d(a,b) + d(c,d) − d(a,c) − d(b,d)      # > 0 ⇒ the move improves the path

for pass in 1..improvement_passes        # default 8
    improved = false
    for i = 1 .. L−2
        for k = i .. L−2
            if k > i and gain(i,k) > 1e−9:
                reverse seq[i..k] ;  improved = true
    if not improved: break
```

**Endpoints are fixed** (`start` and `home` never move), which is what makes it usable
for mid-run re-planning where the van is not at the depot.

### 9.3 Complexity

* Nearest neighbour: `O(k²)`. One 2-opt pass: `O(k²)`. Up to 8 passes: still `O(k²)`
  with a small constant (measured at `0.15 ms` for `k = 11`, i.e. ~200× faster than the
  exact DP at that size).
* Space `O(k)`.

### 9.4 Optimality caveat (important, and honest)

2-opt is a **local search**: it stops when no single reversal improves the path, which
is not a global optimum. Measured on random symmetric matrices it averages `2.3 %–
9.1 %` above the exact optimum and is as bad as `53.5 %` on some instances
(§15 table [6b]); on the real 9-stop instance the gap is `16.0 %` (§15 table [6a]).

**Also note:** the fallback has **no `node_cost` hook** — it minimises travel only, so
when it is used, priority ordering is *not* optimised; the reported penalty is simply
whatever the heuristic's order happens to incur. This is a real limitation of the
`k > 12` path (§20.3), and one reason the exact DP is the default.

---

## 10. The planning layer: how the algorithms are composed

**Implementation:** `core/routing.py`

### 10.1 `item_score(item, premium)` / `plan_load(city, capacity, premium, excluded)`

```
effective value = item["value"] + premium · (3 − item["priority"])
```

`plan_load` builds the `weights` / `values` arrays from the catalogue (minus any items
the manager unchecked in the UI), calls `knapsack_01`, and returns:

* `chosen` / `skipped` item lists,
* `total_value` (the *premium-adjusted* score), `total_weight`, `capacity`, `fill_pct`,
* `chosen_stop_counts` — how many loaded items go to each stop.

That last field is the mechanical link between the two algorithms: **the loading
result determines the routing input set.** A loaded item implies a visit.

### 10.2 `select_route_stops(city, loaded_ids, scope, open_ids)`

Turns "what was loaded" into "which stops to visit". Three scopes:

| scope | stops visited |
| --- | --- |
| `loaded` (default) | exactly the stops that received cargo from the knapsack |
| `critical` | only stops with P1 or P2 cargo among the loaded ones |
| `all` | every stop that still has at least one non-excluded item (a full-city circuit) |

`open_ids` is the set of stops that still have ≥ 1 non-excluded item: a location whose
items were all unchecked in the catalogue is dropped from **every** scope. This is the
mechanism behind the UI behaviour "unchecking an entire stop removes it from the run"
(see GUIDE.md §6.2).

### 10.3 `build_matrix(city, disruptions, nodes)`

Builds the `n × n` shortest-travel-time matrix between the route's nodes by running
**one Dijkstra per node** on the disruption-aware adjacency. `k + 2` nodes at most
(stops plus depot). All TSP inputs are already in "effective minutes" of the current,
disrupted world.

### 10.4 `solve_route(city, disruptions, stop_ids, strictness, start_node, home_node, max_dp_stops)`

The single entry point used by both the planning preview and the live re-planner.

1. **Reachability guard.** Run Dijkstra once from `start_node`; partition `stop_ids`
   into `reachable` and `unreachable`. Unreachable stops are dropped from the tour and
   returned in `unreachable` for the caller to surface. If the *depot itself* is
   unreachable from the van, return an empty plan with `method = "unreachable"` —
   no tour exists.
2. **Deduplicate the node universe** `[start] + [home] + stop nodes`.
3. **Build the matrix** on that universe (§10.3).
4. **Choose the solver:** `held_karp` if `k ≤ max_dp_stops` (12), else
   `nearest_neighbour+2opt`.
5. **Solve**, then **recompute** the objective split (`travel`, `penalty`, `total`)
   from the decided order via `_objective_parts` — so the numbers reported to the UI
   are always recomputed from the actual order rather than trusted from the solver.
6. Return `order` (stop ids), `order_nodes` (city node ids), `method`, `k`, the
   objective split, `unreachable`, plus the matrix and index bookkeeping.

The `node_cost` closure passed to Held–Karp is:

```python
def node_cost(row, position):
    sid = node2stop.get(nodes[row])
    return 0.0 if sid is None else strictness * PRIO_WEIGHT[city.stops[sid]["priority"]] * position
```

i.e. exactly `λ · pw · position` from §4.4.

### 10.5 The river-severance case (graceful degradation)

Because the city is cut by a river with only two bridges, roadblocking **both**
bridges severs the graph: far-bank stops have no road path from the van at all. Rather
than letting the TSP DP raise on `inf` distances, the reachability guard drops those
stops and reports them, and the Flask layer turns that into:

* a **warning** in the left panel listing the dropped stops, and
* a **popup alert** ("Both bridges are blocked … the river cuts the city in two, so
  stops on the far bank can't be reached. Reopen a bridge to plan again.").

This is a deliberate demonstration that the system degrades to a *diagnosis* rather
than a 500 error.

### 10.6 `route_geometry(city, disruptions, ordered_nodes)`

Converts an ordered node list into concrete road legs
`[{from, to, minutes, nodes:[...]}]` using `shortest_path` per consecutive pair. This
is what the van actually drives and what the map actually draws — the route is not a
straight line between stops but a sequence of real roads.

### 10.7 `_objective_parts(...)`

Recomputes `travel`, `penalty` and `total` for a decided order, using the current
matrix and the priority weights. Used both for the initial plan and (indirectly) to
report re-planned costs.

---

## 11. The simulation engine: live re-routing

**Implementation:** `core/engine.py:DeliverySim`. This is the second headline feature
and the part that turns a static optimiser into a dynamic one.

### 11.1 State and the simulated clock

`DeliverySim` owns:

| Field | Meaning |
| --- | --- |
| `phase` | `idle → paused → running → done` (reset returns to `idle`) |
| `clock` | simulated minutes since departure |
| `timescale` | simulated minutes per real second (UI exposes 1–6×) |
| `disruptions` | road id → `{kind, name, factor, source}` |
| `poly` / `offs` / `stops_at` | the planned road polyline (node ids), cumulative travel minutes at each polyline node, and which polyline index is a delivery stop |
| `pt` / `travel` | last reached polyline index / travel minutes consumed on the current polyline |
| `dwell`, `dwell_stop`, `_dwell_arrived`, `_dwell_until` | servicing state at a stop |
| `serve_order` | remaining stop ids in plan order |
| `delivered` | `[{stop, name, priority, arrived, left, late}]` |
| `history` | previous polylines (drawn as faint "ghost" routes) |
| `stats` | `{reroutes, travel_min, late_stops, late_min}` |
| `log` | the event log (capped at 400 entries, trimmed to the last 300) |

**Two time drivers, one deterministic core:**

* `tick()` — used by the web layer: advances the clock by
  `(real elapsed seconds) × timescale`.
* `advance(dt)` — a fully deterministic step of `dt` simulated minutes, used by
  `demo_cli.py` and tests. The whole run is reproducible headless.

`advance` loops over whatever budget it is given, alternately consuming travel along
the polyline and consuming service dwell, so a single large `dt` still lands exactly
on node boundaries, dwell boundaries and re-route checks.

### 11.2 Movement, arrival, service and lateness

* The van's position is interpolated along the polyline between `poly[pt]` and
  `poly[pt+1]` using the cumulative offsets.
* On reaching a polyline node that is a scheduled stop, the van enters **dwell** for
  that stop's `service` minutes.
* On finishing the dwell, the stop is appended to `delivered`, with arrival time,
  departure time, and **lateness** = `max(0, arrival − deadline)` for stops that have
  a deadline. Lateness accumulates into `stats.late_stops` / `stats.late_min` and is
  shown in the event log as `⚠ 0.9 min late`.
* Reaching the last polyline node finishes the run (`phase = "done"`, van back at the
  depot).

**ETA projection:** `etas()` forecasts the arrival time of every remaining stop as
`clock + (planned_offset − travel) + Σ service of earlier remaining stops`.

### 11.3 The disruption model

`add_disruption(rid, kind, factor, source)` records:

* `roadblock` → the road contributes no edges (Dijkstra must detour),
* `traffic` → the road's minutes are multiplied by `factor` (default 3.0).

Every disruption is logged, and — if a run is live — immediately triggers a
re-route check. `clear_disruption` reopens a road and likewise re-checks. Disruptions
can come from three sources, recorded in the `source` field: `manual` (a click on the
map), `script` (the auto-demo), or `reset` clearing everything.

### 11.4 The re-routing policy

`_disrupted_ahead()` computes the undirected endpoint pairs of the roads **still
ahead** of the van (from `pt` onward) and returns the first active disruption that
lies on one of them. Then `_maybe_reroute(reason)` branches on the kind:

| Kind | Policy | Rationale |
| --- | --- | --- |
| **roadblock** | **Mandatory** re-route — never skipped, no cooldown | The current route is literally infeasible; the van cannot drive through a closed road |
| **traffic** | Re-route **only if genuinely better**: a new plan is computed and used only if `new_travel < old_remaining − 0.6 min`; otherwise the log records "Traffic on X — current route still best" and nothing changes | Prevents the log and the van from churning every tick over a negligible saving |

Traffic re-routes additionally respect a small anti-churn cooldown of `0.4` simulated
minutes between heuristic re-plans.

**When is the check performed?**

1. Immediately when any disruption is added or cleared while `phase ∈ {running, paused}`.
2. On every polyline node arrival (`_step_node`), if any disruption is active —
   labelled in the log as "re-validating route at stop". This is what makes the system
   notice a closure that appeared after the last re-plan.

`_plan_from_current()` builds the re-plan request: `start_node = poly[pt]` (the van's
current node), `home_node = depot`, `stop_ids = serve_order` (with the currently
being-serviced stop removed if the van is dwelling there), and the *live* disruption
map.

`_reroute(reason, plan)` then:

1. increments `stats.reroutes`,
2. logs `Re-routing: <reason>`,
3. pushes the old polyline onto `history` (drawn as a ghost route),
4. rebuilds the polyline from `[van's current node] + new order + [depot]`,
5. replaces `serve_order`, `method` and the plan totals,
6. logs the new sequence plus `saves ~X min` or `detour adds ~X min`, computed as
   `old_remaining_travel − new_planned_travel`.

### 11.5 `_apply_plan`: polyline construction and delivery markers

Given an ordered node list `[start, stop…, home]`, it:

* asks `route_geometry` for the road legs,
* walks each leg's node sequence, appending nodes to `poly` and accumulating travel
  minutes into `offs` using the **effective** (disruption-aware) road times, so the
  van's speed on each road matches the plan,
* skips duplicate junction nodes shared between consecutive legs,
* marks the final node of each leg as a delivery point (`stops_at[i] = stop_id`) when
  its target is a scheduled stop, and records its offset for ETA projection.

**Known reporting nuance:** because `_apply_plan` resets `travel` and `offs` to start
from the van's current position, `stats["travel_min"]` after a re-route measures only
the travel of the *final* polyline, not the whole run. See §20.2.

### 11.6 `snapshot()`

The single UI-facing state object: phase, clock, timescale, van position, remaining
polyline, remaining stop order, ETAs, delivered stops, active disruptions, solver
method, plan totals, stats, the *new* events since the last call, total stop count and
the last 4 ghost paths. The Flask layer adds an `alert` field (§12.3).

### 11.7 The scripted auto-demo

`add_scripted_event(at, rid, kind, factor)` queues a disruption to fire at simulated
time `at`; `_fire_scripts()` drains due events on every `advance` iteration. The
`POST /api/demo/scenario` endpoint uses this to pick **the first bridge that still
lies ahead on the freshly-planned route** and schedule a roadblock on it `1.2` minutes
before the van would reach it — guaranteeing that the one-click demo produces a live,
visible detour. If the planned route crosses no bridge at all, the endpoint returns
`409` with "planned route crosses no bridge — manual demo only" instead of silently
doing nothing.

---

## 12. The web layer: Flask API

**Implementation:** `app.py`. Deliberately thin: **all algorithms and simulation live
in `core/`, which imports nothing from Flask**, so the core stays headless-testable
(`python algo_tests.py`, `python demo_cli.py`, `python experiments.py` all work with no
web server). `app.py` only translates HTTP ↔ core calls, clamps inputs, and adds
UI-facing wording.

Process-wide singletons:

```python
CITY = build_city()          # the immutable world
SIM  = DeliverySim(CITY)     # the one active run for the manager's session
```

### 12.1 Endpoint reference

| Method | Path | Request body | Response |
| --- | --- | --- | --- |
| `GET` | `/` | — | the dashboard HTML (`templates/index.html`) |
| `GET` | `/api/data` | — | config, grid coordinates, avenue/street names, bridge rows, river extent, depot, all 67 roads (with endpoint coordinates and rounded minutes), all 12 stops (with x/y), all 48 items. Fetched **once** at page load. |
| `POST` | `/api/plan` | `{capacity, premium, strictness, scope, excluded[]}` (all optional) | load summary + chosen items with their effective score, per-stop detail (priority, service, deadline, #items), route `{method, k, travel, penalty, total}`, the closed road-following polyline for preview, `warnings[]`, `alert`, `unreachable[]` |
| `GET` | `/api/sim/state` | — | full sim snapshot + `alert`. **Each call also advances the simulated clock** by real elapsed time × timescale — polling is what makes the run live. |
| `POST` | `/api/sim/start` | `{capacity, premium, strictness, scope, excluded[], autoplay, clear_disruptions}` | arms a fresh run from the depot (phase `paused`), returns the plan summary, `alert`, `unreachable[]` and a snapshot. `autoplay: true` immediately plays it. |
| `POST` | `/api/sim/control` | `{action: "play"\|"pause", timescale?}` | snapshot |
| `POST` | `/api/reset` | — | clears the run, every disruption and the event log; returns to `idle` |
| `GET` | `/api/roads` | — | `[{id, name, kind}]` for all roads |
| `POST` | `/api/disrupt` | `{id\|rid, kind: "roadblock"\|"traffic", factor?}` | `{ok, alert, sim}` — 404 for unknown road, 400 for bad kind |
| `POST` | `/api/disrupt/clear` | `{id\|rid}` | `{ok, sim}` |
| `POST` | `/api/demo/scenario` | — | resets to defaults, plans the default load, schedules a roadblock on the first bridge ahead, starts playing. `409` if the route crosses no bridge. |

### 12.2 Input handling

`_clamp(value, lo, hi, default)` coerces to float and clamps into the configured
range, falling back to the default on any type error — so a malformed request can
never crash the planner or inject an out-of-range capacity. `scope` is validated
against `{"loaded", "all", "critical"}` and silently falls back to `loaded`.

### 12.3 UI-facing diagnostics produced here

* `_warnings(load, scope)` — "N critical item(s) left behind (no room at this
  capacity/premium): …" (first 4 names).
* `_unreachable_names(plan)` — names of stops the solver had to drop.
* `_river_alert()` — the both-bridges-closed popup message. Attached to **every**
  snapshot by `_snap()` so the popup stays in sync with the map.
* `_blocked_bridges()` — display names of every roadblocked bridge.

### 12.4 Deliberate behaviours worth knowing

* **Disruptions survive a re-dispatch.** `/api/sim/start` does *not* clear
  disruptions unless `clear_disruptions: true` is passed. The comment in the source
  records why: clearing them silently made the van drive straight through roads the
  manager had just closed. Only `/api/reset` and the auto-demo wipe them.
* **The river alert is computed in the web layer, not the engine**, so the core stays
  free of UI wording.
* **One global `SIM`**: the app is single-session by design — see §20.7.

---

## 13. The frontend: the three-panel dashboard

**Implementation:** `templates/index.html` + `static/app.js` (vanilla JS, ~690 lines,
**no build step, no framework**) + `static/style.css`. The map is inline **SVG**
generated from `/api/data`; there is no map library.

### 13.1 Layout

```
┌─ header: logo · clock pill · phase pill · speed slider 1–6× · [▶ Run auto-demo] ─┐
│ 1 · Plan the load       │ 2 · Route map (SVG)      │ 3 · Dispatch & watch         │
│  capacity slider        │  roads (click → block)   │  Dispatch / Pause / Reset    │
│  premium slider         │  route preview + live    │  route sequence list         │
│  punctuality λ slider   │  ghost history routes    │  event log                   │
│  scope segment control  │  stops coloured by tier  │                              │
│  fill / weight / value  │  disruption badges       │                              │
│  warnings box           │  van + status bar        │                              │
│  item catalogue         │  alert popup             │                              │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 13.2 Controls

| Control | Range / default | Effect |
| --- | --- | --- |
| Van capacity | 80–900 step 10, default **430** kg | knapsack capacity |
| Priority premium | 0–500 step 10, default **220** | priority bonus in the loading objective |
| Punctuality λ | 0–12 step 0.5, default **4.0** | priority weight in the routing objective |
| Deliver to | `Loaded stops` / `Every stop` / `Critical only` | route scope |
| Item catalogue checkboxes | 48 checkboxes | unchecking adds the item to `excluded`; it can no longer be loaded and, if a stop loses all its items, that stop is dropped from every scope |
| Speed | 1–6× | simulated minutes per real second |
| **Re-plan load & route** | button | forces a fresh `/api/plan` |
| **Dispatch van** | button | `/api/sim/start` with `autoplay: true` |
| **Pause / Resume** | button | `/api/sim/control` |
| **Reset** | button | `/api/reset` — stops the run, clears disruptions and the log |
| **▶ Run auto-demo** | header button | `/api/demo/scenario` — the guaranteed live re-route |
| Road click | on the map | roadblock; clicking the same road again lifts it |
| Alt-click / Shift-click | on the map | traffic slowdown instead; switching kind replaces the existing disruption |

Slider changes are **debounced (160 ms)** and re-fetch the plan preview, so dragging a
slider shows the load and route change in near-real time. Planning is **locked while a
run is live** (`schedulePlan` returns early and controls are disabled) — you cannot
re-plan underneath a van that is already driving; you re-plan by dispatching again or
resetting.

### 13.3 Rendering behaviour

* **Route preview** (no run): a dashed `route-preview` polyline of the closed
  depot → stops → depot path.
* **Live run**: a solid `route-live` polyline from the van's current position through
  the remaining waypoints, plus a wide translucent "wrap" stroke underneath for a
  glow effect, plus faint `route-ghost` polylines for each previous route (last 4).
* **Stops**: circles coloured by priority tier, labelled, with a P1/P2/P3 chip. Stops
  **not** on the current plan/run are dimmed to 32 % opacity — so a stop the van merely
  drives past is never mistaken for a visit. Delivered stops get a "done" class; the
  next stop gets a "next" class.
* **Disruptions**: the road is repainted red (blocked) or amber (traffic) and an emoji
  badge (⛔ / 🐢) is placed at its midpoint; the transparent hit-target is kept on top
  so a blocked road can still be clicked to reopen it.
* **Status bar**: current target ("→ Central Hospital" or "heading home → DEPOT"),
  stops remaining, delivered count, re-route count, ETA of the next stop.
* **Alert popup**: shown whenever the server sends a non-null `alert` (both bridges
  closed). Dismissing remembers the exact message text, so the 450 ms poll does not
  immediately re-open it; the popup re-arms as soon as the condition clears and comes
  back.
* **Event log**: newline-free rows `time · message`, newest first, capped at 120 rows.
  The client **filters out `info`-kind events** (arrival/service chatter and pause
  messages) so the log shows only plan, disruption, re-route, delivery, done and
  warning events — the narration the manager cares about.

### 13.4 Data flow

```
page load → GET /api/data (once) → draw city, build catalogue
          → GET /api/sim/state (seed any surviving disruptions/phase)
any control change → debounced POST /api/plan → redraw preview
Dispatch → POST /api/sim/start {autoplay} → applyState
while running → setInterval(GET /api/sim/state, 450 ms) → applyState
```

Each poll advances the simulated clock server-side, so the animation is driven purely
by polling — no WebSockets, no client-side physics, no clock drift between client and
server.

---

## 14. Executable entry points

| Command | What it does | Verified output |
| --- | --- | --- |
| `python app.py` | starts the dashboard at `http://localhost:8000` (port overridable via `PORT`) | prints `Delivery Command Center → http://localhost:8000` |
| `python demo_cli.py` | headless narrative: load → plan → scripted bridge roadblock → live re-route → results, with assertions | ends `DEMO OK — all stops delivered with a live re-route on a closed bridge.` |
| `python algo_tests.py` | 13 sanity checks (no pytest dependency) | ends `ALL TESTS PASSED (13 checks)` |
| `python experiments.py` | regenerates every table cited in the report | see §15 — **run it with UTF-8 stdout on Windows**, §20.1 |

Dependencies: `flask>=3.0` only (`requirements.txt`). Python 3.10+ required (`from
__future__ import annotations`, `int.bit_count()`, `dict | dict` style typing);
developed on Python 3.14.

---

## 15. Measured results: every experiment table

All numbers below are the verbatim output of `python experiments.py` on this
repository (Windows console needs `PYTHONIOENCODING=utf-8`, see §20.1). Nothing is
hard-coded; re-running the script reproduces every value.

Header: `city: 67 roads · 12 stops · 48 items · van 430 kg`.

### [1] Default load — capacity 430 kg, premium 220, λ = 4

```
loaded 26 items / 428 kg (99.5% of 430 kg), score value 12920
priority mix loaded: P1=6 · route visits 9 stops via held_karp (k=9)
route objective: travel 18.3 min + priority penalty 304.0 = 322.3
critical items the van could not take: ['Hydrant fittings', 'Oxygen cylinder']
```

Interpretation: the knapsack fills the van to 99.5 % of capacity with 26 items
(6 P1, 17 P2, 3 P3). Only **2 of the 8 critical items** are left behind, and both are
the heaviest P1 parcels (40 kg and 55 kg) — which is exactly the trade-off the premium
exists to balance. The 9 loaded stops are `fire, hospital, clinic, pharmacy, school,
electronics, mall, bookstore, cafe`; the three P3 stops (`grocery`, `market`, `diner`)
receive no cargo and are therefore not visited under the default `loaded` scope.

### [2] Capacity sweep — what a bigger van buys

```
capacity | items | weight | fill   | score   | stops | critical left
-------- | ----- | ------ | ------ | ------- | ----- | -------------
     150 |   11  |   150  | 100.0% |     6190 |    5  | 5
     250 |   16  |   249  |  99.6% |     9030 |    7  | 3
     350 |   21  |   349  |  99.7% |    11410 |    8  | 2
     430 |   26  |   428  |  99.5% |    12920 |    9  | 2
     600 |   30  |   599  |  99.8% |    15350 |    9  | 0
     900 |   42  |   894  |  99.3% |    17055 |   12  | 0
```

Interpretation: monotone improvements in every column; the marginal value of capacity
flattens (150 → 900 kg buys 2.8× the score, not 6×). **Zero critical items are left
behind from 600 kg upward**, which is a clean, quotable business finding: at 430 kg the
premium cannot save every critical parcel, but +170 kg of capacity removes the problem
entirely. At 900 kg the route covers all 12 stops.

### [3] Priority premium — why critical goods win ties (capacity 430)

```
premium | score   | items | fill   | P1 loaded | P1 left behind
------- | ------- | ----- | ------ | --------- | --------------
      0 |    6670 |   25  | 100.0% |        5  | 3
    220 |   12920 |   26  |  99.5% |        6  | 2
    500 |   21190 |   24  |  99.1% |        7  | 1

raising premium 0 → 500 trades normal stock for critical stock:
  in  (critical/high): Hydrant fittings, Rope coils, Stationery box
  out (normal):        Appliance unit, Cake box, Magazine pack, Roast beans
```

Interpretation: this is the clearest single piece of evidence for the priority
coupling. Raising π from 0 to 500 does not change the *kind* of problem being solved —
it is still an exact 0/1 knapsack — but it changes *which* items are optimal: four
ordinary parcels (an appliance unit, a cake box, magazine packs, roast beans) are
traded for three higher-priority ones, and the number of critical items left behind
falls from 3 → 2 → 1. The raw "score" rises with π by construction, so the honest
metric to quote is the **P1 left behind** column.

### [4] Punctuality λ — reordering the run (the same 9 loaded stops)

```
λ=0 (pure shortest route):
   travel 13.7 min · priority penalty 0.0 · total 13.7 min
   order: Grand Pharmacy → Sunrise High School → Community Clinic → Central Mall
          → Metro Electronics → Central Hospital → Park Cafe → Book Nook
          → City Fire Station #2
   P1 stops land at positions [6, 9]

λ=8 (critical first):
   travel 18.3 min · priority penalty 608.0 · total 626.3 min
   order: City Fire Station #2 → Central Hospital → Metro Electronics → Central Mall
          → Community Clinic → Sunrise High School → Grand Pharmacy → Park Cafe
          → Book Nook
   P1 stops land at positions [1, 2]
```

Interpretation: the headline coupling result. With λ = 0 the optimiser minimises
distance only and both P1 stops land **last** (positions 6 and 9 — the fire station is
dead last). With λ = 8 both P1 stops move to positions **1 and 2**, at the cost of
`4.6` extra minutes of driving (`13.7 → 18.3`). The trade is explicit and quantified:
`+4.6 min` of travel buys serving the critical stops first. (Reminder: the "total" of
626.3 is a mixed-unit objective, dominated by the deliberately large λ = 8 penalty —
see §20.5.)

### [5] Roadblock penalty — a closed bridge at planning time (same load)

```
close Main St Bridge  : travel  26.0 min vs 18.3 intact  → +7.7 min (+42%)
close Grand St Bridge : travel  21.1 min vs 18.3 intact  → +2.9 min (+16%)
```

Interpretation: the river design paying off. Main St is the only bridge the default
route actually uses, so closing it costs **42 %** of the travel time; Grand St is on
the other side of the city, so closing it costs only 16 %. These are the *planning
time* figures; the live demo reproduces the same effect mid-drive (§16: "detour adds
~8.0 min").

### [6] Exact Held–Karp vs NN+2-opt fallback

```
6a. real 9-stop instance (exact vs forced NN+2-opt):
    exact total 322.26  ·  heuristic total 373.73  (gap 16.0%)

6b. random symmetric matrices — average / worst gap of NN+2-opt
    vs the exact DP over 25 trials per size:
    k | avg gap | worst gap | exact ms | heuristic ms
    6 |   4.99% |  27.36% |      0.3 |       0.03
    8 |   2.33% |  19.28% |      2.0 |       0.06
   10 |   5.43% |  29.24% |     13.6 |       0.11
   11 |   9.06% |  53.54% |     33.3 |       0.15
```

Interpretation: the heuristic is 100–200× faster but routinely 2–9 % worse, and can be
53 % worse on an unlucky instance; on the project's own 9-stop instance it is 16 %
worse. **This is the empirical justification for defaulting to the exact DP and using
the heuristic only when the instance is too large.** The script's own closing comment
("still within a few percent") understates its own worst-case numbers — quote the
table, not the comment (§20.3).

### [7] Exact DP cost growth (why the cap of 12 exists)

```
k stops | dp size 2^k | time
     10 |       1024 |    13.9 ms
     12 |       4096 |    76.6 ms
     14 |      16384 |   438.9 ms
     16 |      65536 |  3203.4 ms
```

Interpretation: clean exponential confirmation — roughly 6× the time per 2 extra
stops, matching the `O(k² · 2^k)` prediction (the `k²` factor is visible in the ratio
being slightly above 4× per 2 stops). At `k = 12` a solve is 77 ms (imperceptible);
at `k = 16` it is 3.2 s (perceptible) and would keep growing 4–6× per 2 stops. Hence
`max_dp_stops = 12`.

### [8] Route by scope (default load, λ = 4) — supplementary measurement

| scope | stops | k | method | travel | penalty | total |
| --- | --- | --- | --- | --- | --- | --- |
| `loaded` | 9 | 9 | held_karp | 18.3 min | 304.0 | 322.3 |
| `critical` | 7 | 7 | held_karp | 11.5 min | 236.0 | 247.5 |
| `all` | 12 | 12 | held_karp | 23.1 min | 436.0 | 459.1 |

`k = 12` is exactly the DP cap, so "every stop" is still solved **exactly**, not by the
fallback — the guard triggers only above 12.

---

## 16. Verified end-to-end run (headless transcript)

`python demo_cli.py` plans the default load, drives the van, and injects a roadblock on
the first bridge ahead once the clock passes 2.0 minutes. Verbatim events:

```
[2] ROUTE PLAN  method=held_karp · 9 stops
    travel 18.3 min · priority penalty 304.0 · total 322.3 min
      1. [P1 critical] City Fire Station #2
      2. [P1 critical] Central Hospital
      3. [P2 high] Metro Electronics
      4. [P2 high] Central Mall
      5. [P2 high] Community Clinic
      6. [P2 high] Sunrise High School
      7. [P2 high] Grand Pharmacy
      8. [P3 normal] Park Cafe
      9. [P3 normal] Book Nook

[3] LIVE RUN  (route uses bridge: Main St Bridge)

[4] EVENT LOG
   00:00  · Route planned · 9 stops · held_karp · travel 18.3 min · priority cost 304.0
   00:00  · Van loaded · depart from DEPOT · priority strictness λ=4
   00:00  » Delivery run started · van on the road
   00:02  ⚠ Main St Bridge closed (bridge)
   00:02  ↻ Re-routing: Main St Bridge closed
   00:02  ↻ New route: Central Hospital → City Fire Station #2 → Grand Pharmacy →
          Sunrise High School → Community Clinic → Central Mall → Metro Electronics →
          Book Nook → Park Cafe · detour adds ~8.0 min
   00:06  » Arrived at Central Hospital — servicing (P1)
   00:09  ✓ Delivered Central Hospital at 00:09
   00:10  » Arrived at City Fire Station #2 — servicing (P1)
   00:12  ✓ Delivered City Fire Station #2 at 00:12
   00:16  » Arrived at Grand Pharmacy — servicing (P2)
   00:18  ✓ Delivered Grand Pharmacy at 00:18
   00:19  » Arrived at Sunrise High School — servicing (P2)
   00:21  ✓ Delivered Sunrise High School at 00:21
   00:23  » Arrived at Community Clinic — servicing (P2)
   00:25  ✓ Delivered Community Clinic at 00:25 · ⚠ 0.9 min late
   00:26  » Arrived at Central Mall — servicing (P2)
   00:28  ✓ Delivered Central Mall at 00:28
   00:30  » Arrived at Metro Electronics — servicing (P2)
   00:31  ✓ Delivered Metro Electronics at 00:31
   00:33  » Arrived at Book Nook — servicing (P3)
   00:34  ✓ Delivered Book Nook at 00:34
   00:35  » Arrived at Park Cafe — servicing (P3)
   00:36  ✓ Delivered Park Cafe at 00:36
   00:43  ■ Run complete — van back at DEPOT · 9/9 stops · 00:43 total

[5] RESULTS
    delivered 9/9 · total 42.7 min · travel 24.2 min · re-routes 1 · late 1 (0.9 min)
```

**What this transcript demonstrates:**

1. **Priority ordering is real and it survives a re-route.** The initial plan puts both
   P1 stops first (Fire Station, Hospital). After the bridge closes, the re-plan from
   the van's position *reorders the whole remaining run* — Hospital first (the van had
   already moved toward it), Fire Station second, then the P2 block, then P3 — so the
   critical stops are still served first under a completely different route.
2. **The detour is quantified, not just visualised:** `detour adds ~8.0 min`, matching
   the +7.7 min planning-time penalty of closing Main St (§15 table [5]).
3. **Deadlines behave as designed:** the only late stop is Community Clinic
   (deadline 22 min, arrived ≈ 22.9 min) → `⚠ 0.9 min late`, counted once in
   `stats.late_stops` and `stats.late_min`.
4. **The run completes:** 9/9 delivered, van back at the depot, phase `done`.
5. **Timing decomposition:** the 42.7-minute run = ~2.0 min driven before the roadblock
   + 24.2 min of the final (post-re-route) polyline + 16.5 min of service dwell across
   the 9 stops. The `travel 24.2` figure is the post-re-route polyline only — see §20.2
   for why that is a reporting nuance rather than a bug.

---

## 17. Test coverage

`python algo_tests.py` runs 13 checks using plain `assert` (no pytest), on
deterministic or seed-fixed random instances:

| # | Check | What it proves |
| --- | --- | --- |
| 1 | `knapsack_01 == brute force` on 40 random instances | the DP matches exhaustive enumeration, and the reconstructed subset's weight is consistent with the capacity |
| 2 | classic knapsack instance `([10,20,30],[60,100,120],50) → items [1,2], value 220` | textbook case correctness |
| 3 | item heavier than the capacity is excluded | boundary handling |
| 4 | **priority premium flips the choice** (3 equal-weight items; the cheapest-but-critical one wins at π = 400) | the premium mechanism itself, in isolation |
| 5 | Dijkstra prefers a 2-edge path over a longer direct edge | shortest-path correctness |
| 6 | unreachable nodes get `inf` and `shortest_path` raises `ValueError` | the guard the river-severance case relies on |
| 7 | `tsp_held_karp == permutation brute force` for n = 3…7 (6 instances each) | exactness of the TSP DP, including that the reported cost equals the tour's travel |
| 8 | **`tsp_held_karp` exact with an additive position cost** | the priority-penalty mechanism keeps the DP exact (§8.3) |
| 9 | **`tsp_held_karp` exact when `start ≠ home`** over 20 random pairs | the open-path re-planning mode used mid-run |
| 10 | NN+2-opt never beats Held–Karp | sanity/optimality-direction of the heuristic |
| 11 | NN+2-opt returns a valid, correctly-costed tour | heuristic output integrity |
| 12 | city invariants: reproducibility, 42 nodes, connectivity, exactly 2 bridges, positive road times, symmetric adjacency, one stop per node, all items point at real stops, ≥ 3 items per stop | the dataset is well-formed |
| 13 | **closing the north bridge forces a strictly longer but finite detour** | the dramatic-detour premise, and that the south bridge still connects the city |

**What is *not* covered by tests** (worth stating honestly in a report): the simulation
engine's re-routing policy has no unit tests (it is covered by the `demo_cli.py`
smoke assertions: `injected`, `reroutes ≥ 1`, all stops delivered, phase `done`); the
Flask endpoints have no tests; the frontend has no tests. Testing is concentrated
where the algorithmic risk is — the four algorithms and the dataset.

---

## 18. Complexity summary and measured timings

| Problem | Algorithm | Time | Space | Exact? | Used when |
| --- | --- | --- | --- | --- | --- |
| What to load | 0/1 knapsack DP | `O(n·W)` | `O(n·W)` | exact | always (`n = 48`, `W ≤ 900`) |
| Distance between nodes | Dijkstra (binary heap) | `O((V+E) log V)` | `O(V)` | exact | per source node: `k+2` runs per plan |
| Route order | Held–Karp DP over subsets | `O(k²·2^k)` | `O(k·2^k)` | exact | `k ≤ 12` (always, in this city) |
| Route order (fallback) | nearest neighbour + 2-opt | `O(k²)` per pass, ≤ 8 passes | `O(k)` | approximate (measured 2–9 % avg, up to 53 % worst, 16 % on the real instance) | `k > 12` |
| Path reconstruction | predecessor walk | `O(V)` | `O(V)` | exact | with every Dijkstra |

Whole-system cost of one plan: `(k+2)` Dijkstra runs to build the matrix
(`≈ 11 × O(42+67 log 42)`, sub-millisecond each) plus one TSP DP (77 ms at `k = 12`,
0.3 ms at `k = 6`). One live re-plan is the same work with a smaller `k` — cheap
enough to run on every polyline node arrival.

Measured (from experiment [7], random symmetric matrices, one run per size):

| k | DP states `2^k` | exact DP time |
| --- | --- | --- |
| 10 | 1 024 | 13.9 ms |
| 12 | 4 096 | 76.6 ms |
| 14 | 16 384 | 438.9 ms |
| 16 | 65 536 | 3 203.4 ms |

---

## 19. Design decisions and trade-offs

Each of these is a defensible answer to a likely examiner question.

1. **Why exact algorithms when the problems are NP-hard?**
   Because the instance sizes are honestly small in the dimension that matters: the
   exponential is in the *number of delivery stops* (`k ≤ 12`), not in the size of the
   city. Measured growth (§15 [7]) shows exactness is affordable to `k = 12` (77 ms) and
   stops being so around `k = 14–16`. A polynomial heuristic is therefore *available and
   measured* (§15 [6]) but not the default — optimality is bought where it is cheap.

2. **Why couple priority through two knobs instead of hard-coding "P1 first"?**
   Hard-coding an order would make priority a constraint and destroy the optimisation
   (the route would be forced, not optimal). Pricing priority as a *cost* keeps both
   objectives pure optimisation problems, keeps the algorithms textbook-standard, and
   makes the trade-off visible and dialable: the manager chooses how much punctuality
   is worth. §15 tables [3] and [4] are the measured evidence that the knobs do exactly
   what they claim.

3. **Why does the position cost not break the Held–Karp DP?**
   Because the visit position is the popcount of the state's mask — a function of the
   DP state alone (§8.3). This is the project's most interesting technical point and is
   verified against brute force (test 8).

4. **Why a river with exactly two bridges?**
   It guarantees that a single roadblock can produce a *dramatic, legible* detour
   (+42 % for the north bridge), that the "both bridges closed" case is genuinely
   infeasible rather than merely expensive, and that the reachability guard has
   something real to detect. A generic grid would make most closures invisible.

5. **Why deterministic data?**
   So that every claim in the report and every demo in front of an examiner reproduces
   exactly. Randomness is confined to (a) the seeded `random.Random` objects inside the
   experiments/tests for synthetic matrices, and (b) nothing at all in the city.

6. **Why is `core/` free of Flask?**
   So the algorithmic content is headless-testable and auditable without a web server:
   `algo_tests.py`, `demo_cli.py` and `experiments.py` all run the same code the
   dashboard runs, with no HTTP involved. This also keeps the layering clean —
   algorithms → planning → simulation → HTTP → UI.

7. **Why simulate the van along a road polyline instead of teleporting between stops?**
   Because "the van is *already driving*" is the whole premise of the dynamic feature.
   Modelling position, per-road travel, dwell time, ETA projection and ghost routes is
   what makes the re-route visible and the lateness statistics meaningful. It also
   forces the engine to answer the real question — "is the disruption *ahead* of me?" —
   rather than re-planning indiscriminately.

8. **Why is a traffic jam allowed to be ignored?**
   The objective is re-solved only if it improves the remaining travel by more than
   0.6 min, with a 0.4-minute cooldown. Without this the log would churn on every tick
   and the van would jitter between near-equal routes. Roadblocks, by contrast, are
   *mandatory* because the current route is literally infeasible.

9. **Why use the integer capacity as a DP dimension?**
   Because it is small (≤ 900 kg), which is exactly the pseudo-polynomial condition
   that makes exact knapsack practical. Weights being integers is a modelling
   simplification (kg), and it is the reason the DP is exact rather than approximate.

10. **Why keep the full DP table in knapsack?**
    `O(n·W)` space instead of `O(W)` buys subset reconstruction — the manager must see
    *which* items were loaded, not just the optimal value.

---

## 20. Known caveats, bugs and honest limitations

Stating these is a strength in a report: it shows the analysis was actually performed.
Each is verified against the current code.

### 20.1 `experiments.py` crashes on a Windows console (encoding)

`experiments.py` prints `λ` (U+03BB) but — unlike `demo_cli.py`, which calls
`sys.stdout.reconfigure(encoding="utf-8")` — it never reconfigures stdout. On a
CP1252 console it therefore dies with:

```
UnicodeEncodeError: 'charmap' codec can't encode character 'λ' in position 47
```

**Workaround:** `set PYTHONIOENCODING=utf-8` (PowerShell: `$env:PYTHONIOENCODING="utf-8"`)
before running it, or run in a UTF-8 terminal. **Fix (one line, not yet applied):** add
the same `sys.stdout.reconfigure(encoding="utf-8")` guard that `demo_cli.py` already
has. Reported here so the report does not claim the script runs cleanly out of the box.

### 20.2 `stats["travel_min"]` measures only the final polyline after a re-route

`_apply_plan` resets `travel`/`offs` to zero and rebuilds the polyline from the van's
current position, so after a re-route `stats["travel_min"]` (reported as "travel" in
`demo_cli.py` §5) covers only the travel *after* the last re-route. In the verified run
this shows as `total 42.7 min` but `travel 24.2 min` — the missing ≈ 2.0 min is the
travel before the roadblock, and the rest of the difference is the 16.5 min of service
dwell. **The reliable whole-run figure is `clock` (the simulated wall clock), not
`travel_min`.** A derived field or a running total would make this unambiguous.

### 20.3 Two config keys are declared but never read

* `service_at_depot_min: 3.0` — no depot service is ever simulated.
* `tsp_dp_max_stops: 12` — the effective cap is the `max_dp_stops=12` **default
  argument** of `routing.solve_route`; changing the config key has no effect. Config
  and code agree on the value, so no behaviour is wrong, but the key is dead and
  misleading.

### 20.4 The `k > 12` fallback ignores the priority penalty

`tsp_nearest_neighbor_2opt` has no `node_cost` hook: when the fallback is selected, it
minimises travel only, so the priority-aware ordering guarantee is lost for that call
(the reported penalty is simply whatever the heuristic's order incurs). This is
currently unreachable on the shipped dataset (max `k = 12`), but it means the design
claim "the route is always priority-aware" is true only up to the DP cap.

### 20.5 The objective `total` mixes units and must not be read as minutes

`total = travel + penalty` adds minutes to `λ · Σ pw · position`. At the default
λ = 4 the C(π) for the default route is 322.3, of which 304.0 is penalty — not 304
minutes. At λ = 8 the "total" reaches 626.3, which is an objective value in
priority-cost units, not a 10-hour day. The *reportable* physical quantities are
`travel` (minutes), the arrival clock times, and the lateness statistics; the penalty
and total are comparative objective values only. (`demo_cli.py` labels this line
"total … min", which is a wording slip worth knowing about.)

### 20.6 Deadlines and service time are not part of the optimisation

Deadlines are used only to *measure* lateness after the fact (`late_stops`,
`late_min`), and service time is used only to advance the clock. Neither enters
`C(π)`. A true time-window VRP would need arrival-time state in the DP (which breaks
the simple `mask`-only state, since feasibility would depend on accumulated time, not
just position). This is the single biggest gap between the project and an industrial
solver, and it should be presented as "the natural next step", not hidden.

### 20.7 Other structural limitations

* **Single global `SIM`** in `app.py`: one shared run for the whole process. Two
  browser tabs share a van, and there is no per-session isolation. Fine for a
  single-manager demo; noted as a limitation.
* **No persistence**: nothing survives a process restart; `reset` clears everything.
  (Verified behaviour: disruptions *do* survive a page reload and a re-dispatch within
  the same process — only `reset`/auto-demo clear them.)
* **No time-dependent travel times**: the matrix is static for a given disruption set,
  so traffic is a multiplicative slowdown, not a peak-hour profile.
* **The heuristic gap is measured, not bounded**: 2-opt offers no worst-case guarantee;
  the measured worst case on random matrices was 53.5 % above optimal.
* **The auto-demo's `409` path** (route crosses no bridge → "manual demo only") is
  reachable in principle with unusual slider settings and is handled, but is easy to
  mistake for a broken button.
* **No unit tests for the engine or the API** (see §17).

---

## 21. Numbers cheat-sheet

Safe to quote directly; all reproducible from `python experiments.py` (plus
`python demo_cli.py` for the run transcript).

**Dataset**
* 42 nodes (6 rows × 7 columns), 67 roads (65 streets + 2 bridges), 12 stops, 48 items.
* Depot at node 0 `(40, 0)`; river between x = 578 and x = 622; bridges on Main St
  (row 1) and Grand St (row 4).
* Road times: 0.6154 min per horizontal street span, 0.4808 min per vertical avenue
  span, 0.4211 min per bridge span.

**Default plan (430 kg, π = 220, λ = 4)**
* 26 items loaded, 428 kg, **99.5 % fill**, score 12 920, mix P1 = 6 / P2 = 17 / P3 = 3.
* Critical items left behind: **2** (Hydrant fittings 40 kg, Oxygen cylinder 55 kg).
* 9 stops, solved exactly by Held–Karp (`k = 9`): travel **18.3 min**, penalty 304.0,
  total 322.3.

**Capacity sweep** — 150 kg → 900 kg gives 11 → 42 items, score 6 190 → 17 055, and
critical items left behind 5 → 0 (zero from 600 kg upward).

**Priority premium (π)** — 0 → 500 changes P1 loaded from 5 → 7 and P1 left behind from
**3 → 1**; it trades 4 ordinary parcels for 3 critical/high ones.

**Punctuality λ** — 0 → 8 moves both P1 stops from positions **{6, 9} → {1, 2}** for
`+4.6 min` of travel (13.7 → 18.3 min).

**Bridge closures (planning time)** — Main St **+7.7 min (+42 %)**, Grand St
**+2.9 min (+16 %)**.

**Live run (headless demo, default settings)** — 9/9 stops delivered, **42.7 min**
total, 1 re-route triggered at minute 2, detour **+8.0 min**, 1 late stop
(Community Clinic, **0.9 min** late).

**Exact vs heuristic** — on the real 9-stop instance the fallback is **16.0 %** worse;
on random matrices 2.33 %–9.06 % average, up to **53.54 %** worst.

**Solver cost** — `k = 12` → 4 096 DP states → **76.6 ms**; `k = 16` → 65 536 states →
**3 203 ms** (the reason for the cap at 12).

**Tests** — `algo_tests.py`: **13 checks, all pass**.

---

## 22. Repository map

```
DAA_project/
├── app.py                  Flask HTTP layer — endpoints only, no algorithms
├── demo_cli.py             headless narrative run + smoke assertions
├── algo_tests.py           13 algorithm/dataset sanity checks (no pytest)
├── experiments.py          regenerates every number in the report
├── requirements.txt        flask>=3.0
├── core/                   ← all algorithmic content, zero Flask imports
│   ├── __init__.py         re-exports the public algorithm API
│   ├── algorithms.py       knapsack_01 · dijkstra · shortest_path ·
│   │                       tsp_held_karp · tsp_nearest_neighbor_2opt · tour_cost
│   ├── city.py             deterministic city dataset + disruption-aware adjacency
│   ├── routing.py          plan_load · select_route_stops · build_matrix ·
│   │                       solve_route · route_geometry  (the objectives live here)
│   └── engine.py           DeliverySim — clock, movement, dwell, re-routing, log
├── templates/index.html    three-panel dashboard markup
├── static/app.js           dashboard logic (vanilla JS, no build step)
├── static/style.css        dashboard styling
├── README.md               quick orientation + "what the professor should look at"
├── REPORT.md               existing DAA write-up in report prose
├── GUIDE.md                plain-English guide to every control and algorithm
├── DEMO.md                 live demo script for the review session
└── PROJECT_CONTEXT.md      ← this file (source material for generating a report)
```

**Recommended reading order to understand the system:** `core/algorithms.py` →
`core/routing.py` → `core/engine.py` → `app.py` → `static/app.js`.

Repository: https://github.com/ka0s01/DAA_project

---

## 23. How to build, run and reproduce

```bash
# setup (Python 3.10+; developed on 3.14)
pip install -r requirements.txt          # flask only

# the dashboard
python app.py                            # → http://localhost:8000

# the headless story (load → plan → roadblock → live re-route → results)
python demo_cli.py                       # ends: DEMO OK — all stops delivered …

# correctness
python algo_tests.py                     # ends: ALL TESTS PASSED (13 checks)

# every report number
python experiments.py                    # Windows: prefix with PYTHONIOENCODING=utf-8
```

**Fastest way to see the headline features (under a minute):** start `app.py`, open
`http://localhost:8000`, click **▶ Run auto-demo** — a bridge closes ahead of the van,
the van re-routes live, and the event log narrates the detour cost.

**Suggested demonstration sequence** (detail in `DEMO.md`): run the auto-demo → drag λ
from 0 to 8 and watch the P1 stops jump to the front of the sequence → drag the priority
premium from 0 to 500 and watch the "critical items left behind" warning shrink → click
a bridge on the map mid-run to force a detour by hand.

---

## 24. Mapping to typical report sections

If the required report format uses different headings, draw the material from here:

| Typical report section | Source in this file |
| --- | --- |
| Abstract / executive summary | §1 |
| Introduction, motivation, problem statement | §2 |
| Scope, assumptions, non-goals | §2.3, §19 |
| Formal / mathematical model | §4 (graph `G`, `w_D`, knapsack, `C(π)`, re-plan variant) |
| Dataset description | §5 (geometry, bridges, stops table, item catalogue, config) |
| Algorithm design & analysis | §6 knapsack, §7 Dijkstra, §8 Held–Karp, §9 heuristic |
| NP-hardness / complexity discussion | §2.2, §18 |
| System architecture | §10 planning layer, §11 engine, §12 API, §13 UI |
| Implementation details | §10–§13, §22 (file map) |
| Key/novel contribution | §8.3 (position cost keeps the DP exact), §4.4–4.5 (coupling), §11.4 (re-route policy) |
| Experiments, results, tables | §15 (all seven tables) + §16 (end-to-end transcript) |
| Testing / verification | §17, §15 [6], §15 [7] |
| Discussion of trade-offs | §19 |
| Limitations / threats to validity | §20 (especially §20.5 units, §20.6 no time windows) |
| Future work | §20.6 (time windows), §20.7 (persistence, multi-van, predictive traffic), §9.4 (priority-aware heuristic) |
| Conclusion | §1 + §15 headline numbers |
| Appendix: how to run | §23, §14 |
| Appendix: repository map | §22 |

---

## 25. Details the report must fill in

The code and this document cannot supply these; they come from the student:

* Name, course code and section, institution, semester, submission date.
* Any course-specific formatting requirements (fonts, page limits, citation style).
* Declaration of originality / academic-integrity statement, if required.
* Whether figures should be screenshots of the running dashboard (recommended: one of
  the plan view and one mid-re-route with the event log visible) — the app renders
  these live at `http://localhost:8000`, they are not stored in the repository.

---

*Every number in this document was produced by running the code in this repository on
the deterministic dataset described in §5. Re-run §23's commands to reproduce them.*
