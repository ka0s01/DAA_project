# Delivery Command Center

A **Design & Analysis of Algorithms** course project: a delivery-route optimizer
framed as a *management console for delivery managers*. It is deliberately more
than a textbook *knapsack + TSP* demo — the two algorithms are coupled through
**priority** and routing is **dynamic**:

* **Load planning** uses an exact **0/1-knapsack DP**, where a *priority premium*
  makes critical goods (P1) win ties when the van can't fit everything.
* **Route planning** solves a *priority-aware TSP* with the exact **Held–Karp DP**
  (falling back to **nearest-neighbour + 2-opt** for oversized instances), where
  serving a high-priority stop late costs more in the objective.
* **Every pair-wise travel time** is a Dijkstra shortest road path, so closed
  bridges and traffic jams genuinely change the numbers.
* **Live re-routing** — the dashboard watches the run and, if a road ahead gets
  blocked (or a traffic jam makes a better route available), it re-plans *from
  the van's current position* over the remaining stops and visibly detours.

The city is a hand-drawn schematic grid cut by a **river with exactly two
bridges**, so closing a bridge is guaranteed to produce a dramatic detour.

---

## Quick start

Requires Python 3.10+ (developed on 3.14). Flask is the only dependency.

```
pip install -r requirements.txt
python app.py
```

Open **http://localhost:8000** in a browser. Then, to see the whole story in
under a minute: click **▶ Run auto-demo** in the top bar.

Other entry points (no browser needed):

```
python demo_cli.py        # headless narrative: load → plan → roadblock → re-route
python algo_tests.py      # 13 sanity tests, prints ALL TESTS PASSED
python experiments.py     # regenerates every table used in REPORT.md
```

---

## What the professor should look at

1. **The priority coupling** — drag the *priority premium* (loading) and
   *punctuality λ* (routing) sliders in the left panel and watch what the van
   picks and in what order it visits. `REPORT.md` §7.3–7.4 give the exact tables.
2. **A live re-route** — click **Run auto-demo**, or during any run click any
   road on the map (⛔ roadblock, alt-click 🐢 traffic). The event log narrates
   `Re-routing … detour adds ~7.7 min`.
3. **The tests / experiments prove it, not just the UI** — `algo_tests.py`
   checks Held–Karp against permutation brute force and knapsack against brute
   force; `experiments.py` prints reproducible numbers.

The DAA-relevant code is in `core/` and each function's docstring records its
asymptotic complexity and a short correctness argument.

---

## Reading map

```
core/algorithms.py   knapsack_01 O(n·W) · dijkstra O((V+E)log V) ·
                     tsp_held_karp O(k²·2^k) · tsp_nearest_neighbor_2opt O(k²)
core/routing.py      the objectives: load plan + priority-aware route
core/city.py         deterministic schematic city: 42 nodes, 67 roads, 2 bridges,
                     12 stops (P1/P2/P3), 48 items, van config
core/engine.py       DeliverySim — simulated clock, check-while-driving re-route,
                     ETA accounting, event log
app.py               thin Flask API over the engine
templates/,static/   three-panel dashboard (load · SVG map · route & events)
REPORT.md            full DAA write-up with generated experiment numbers
```

Algorithms → `core/algorithms.py` → `core/routing.py` → `core/engine.py` is the
recommended reading order for the defence.

---

## A note on the numbers

`REPORT.md` §7 quotes values like *26 items / 428 kg / 99.5% fill*, *P1 stops
move from positions {6,9} to {1,2} when λ goes 0→8*, and *closing Main St Bridge
adds +7.7 min (+42%)*. Every one of these is produced by `python experiments.py`
running the actual code on the actual city — none are hand-written.

---

Built for the Design & Analysis of Algorithms course. Repository:
https://github.com/ka0s01/DAA_project
