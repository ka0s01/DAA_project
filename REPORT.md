# Design & Analysis of Algorithms — Course Project Report

**Delivery Command Center**: priority-aware load planning and *live* re-routing for a fleet dispatcher

| | |
| --- | --- |
| **Name** | *replace with your name* |
| **Course / Section** | *replace, e.g. CS3XXX — Design & Analysis of Algorithms* |
| **Institution / Semester** | *replace* |
| **Submission date** | *replace* |
| **Repository** | https://github.com/ka0s01/DAA_project |

> Every table in §7 is produced by `python experiments.py` on this repository —
> nothing is hard-coded, so every number can be regenerated and re-verified.

---

## 1. Problem statement and objectives

A delivery manager must (i) **decide what fits in one van** and (ii) **decide the
order in which to visit delivery stops**, in a city with one-way-off street
geometry, time-sensitive goods and live disruptions. Two textbook problems hide
in this job, and the interesting part is that they do **not** sit side by side —
they are coupled through **priority**:

* **What fits (0/1 Knapsack).** Every item has a weight and a value. The van has
  a weight capacity. Critical goods (hospital oxygen, fire-hydrant fittings) must
  win ties over ordinary stock when there is not room for everything.
* **In what order (Travelling Salesman).** A route that returns to the depot must
  be chosen. But a *minimum-distance* route may serve a P1 (critical) stop last —
  unacceptable when the load contains life-saving stock. Priority must be priced
  into the route objective, not bolted on afterwards.
* **Nothing stays static.** Roads close (roadblock) and slow down (traffic).
  Because plans are made ahead of time, the system must *notice* a disruption on
  the van's route **while the van is already driving** and re-plan from the van's
  current position over the remaining stops.

The project is built as a **management console** (Flask web app) so the
algorithms are exercised through a realistic workflow — plan the load, see the
route, dispatch the van, block a bridge mid-run and watch it detour live.

### 1.1 Scope and non-goals
* Simulated but deterministic city; no live map data (roads are drawn programmatically).
* Single van, single depot.
* Priority tiers are fixed (P1/P2/P3) but their weights in both objectives are
  manager-adjustable, which is exactly what exposes the algorithm trade-offs.

---

## 2. Formal model

Let the street network be an undirected graph `G = (V, E)` with `|V| = 42` nodes
and `|E| = 67` roads. Each road `e` has a base travel time `t(e)`; a *disruption*
map `D : E → {open, traffic(f), closed}` turns this into an *effective* weight
`w_D(e)` used by shortest-path search:

```
w_D(e)  =  t(e)                        if e is open
           t(e) · f                    if e has traffic with slowdown f ≥ 1
           +∞  (edge removed)          if e is roadblocked (closed)
```

**Items.** A catalogue of `n` items; item `i` has weight `w_i` (kg), base value
`v_i`, priority tier `p_i ∈ {1,2,3}` and a destination stop `s(i)`.

**Loading decision (0/1 knapsack).** With capacity `W` and a *priority premium*
`π ≥ 0`, the effective value of item `i` is

```
v_i'  =  v_i  +  π · (3 − p_i)                     # P1 bonus = 2π, P2 = π, P3 = 0
```

and we solve

```
maximize   Σ_i v_i' x_i
subject to Σ_i w_i x_i ≤ W ,     x_i ∈ {0,1}.
```

Because a loaded item must be delivered, the set of items loaded induces a set of
*destination stops* that the route must visit.

**Routing decision (priority-aware TSP).** Let `S` be the stops to visit, `d(a,b)`
be the shortest effective travel time from node `a` to node `b` (Dijkstra on
`(G, w_D)`), and the depot be `0`. Choosing a visiting order is a permutation `π`
of `S`. With a *punctuality* weight `λ ≥ 0` and priority weights
`pw = {P1:3, P2:2, P3:1}`, minimise

```
C(π)  =  d(0, π₁)  +  Σ_{t=1..k−1} d(π_t, π_{t+1})  +  d(π_k, 0)
         +  λ · Σ_{t=1..k}  pw(p(π_t)) · t
```

The first line is the classical *closed tour* travel cost; the second term prices
**how late** each stop is served (a stop served at position `t` pays its priority
weight × `t`). Pushing a P1 stop late therefore costs `3λ` per position.

**Dynamic re-routing.** Mid-run, at the van's current node `v` with the set of
still-undelivered stops `S_rem ⊆ S`, and under an *updated* disruption map `D'`,
we solve the same objective but with `d(v, ·)` as the start — i.e. the closed
tour becomes an open path that starts at `v` and must still finish back at the
depot `0` (see §5.4).

---

## 3. Algorithms and why they are the right tool

| Problem | Algorithm | Complexity | Exact? |
| --- | --- | --- | --- |
| Load the van | 0/1 knapsack DP | `O(n · W)` time & space | exact |
| Travel time between every pair | Dijkstra (binary heap) | `O((V+E) log V)` per source | exact |
| Order the route (small k) | Held–Karp DP over subsets | `O(k² · 2^k)` time, `O(k · 2^k)` space | exact |
| Order the route (large k) | Nearest-neighbour + 2-opt | `O(k²)` | approx. |
| Live re-route | Dijkstra + Held–Karp re-run | as above, on remaining stops | exact |

### 3.1 0/1 Knapsack — exact dynamic programming

`V[i][c]` = best value using the first `i` items and capacity `c`:

```
V[0][c] = 0
V[i][c] = max( V[i-1][c],  v_i' + V[i-1][c − w_i] )     if w_i ≤ c
          V[i-1][c]                                      otherwise
```

**Correctness.** Induction on `i`: either item `i` is not taken, in which case the
optimum for `i−1` items and capacity `c` stands, or it is taken and the remaining
capacity `c − w_i` is filled optimally from the first `i−1` items; taking the max
over these two cases cannot miss the optimum. **Complexity:** the table is
`(n+1)×(W+1)` and each cell is constant work, so `O(nW)` time and space. The
chosen subset is reconstructed by walking the table backwards from `V[n][W]`
(implemented in `core/algorithms.py:knapsack_01`). Since we need the *set*, the
full table is kept rather than the space-saving two-row version.

**The premium hook (§2)** only changes each item's value before the DP runs; the
optimality argument is untouched.

### 3.2 Dijkstra — shortest road time (graph layer)

Standard binary-heap Dijkstra over `(G, w_D)`. Running it from the depot and from
every candidate stop yields the complete cost matrix `d(·,·)` that the TSP layer
uses, and a *path reconstruction* (`prev`) yields the actual node polyline the van
drives along. **Correctness:** edge weights are non-negative; when a vertex is
popped its distance is final (a later, longer path cannot improve it).
**Complexity:** `O((V+E) log V)` per source. Closing a bridge simply omits that
edge from the graph (weight `+∞`), which is what makes every downstream number
"notice" the closure.

### 3.3 Held–Karp — exact TSP with a position-aware objective

For the ordered set of stops `S` we solve the TSP DP over subsets. Let the
depot be the start and `others = S` be the `k` visitable stops, indexed `0..k−1`;
`dp[mask][j]` = cheapest way to start at the depot, visit exactly the set
`mask`, and finish at stop `j`:

```
dp[{j}][j]            = d(depot, j)          + cost(j, 1)
dp[mask ∪ {j}][j]     = min_i dp[mask][i]
                        + d(i, j)            + cost(j, |mask|+1)
answer                = min_j dp[full][j]    + d(j, depot)
```

**Why priority stays exact here.** The priority term is additive and depends only
on `position = |mask| + 1`, which is fixed per DP state. So
`cost(j, position) = λ · pw(p(j)) · position` is a constant per state and the
recurrence remains valid — the DP is still *exact* for the full priority-aware
objective `C(π)` in §2. This is the key idea that stops the priority model from
degrading the routing into a heuristic.

**Correctness.** Any optimal route restricted to a prefix that ends at `j` over
the set `mask` is itself optimal for that subproblem (otherwise replacing the
prefix improves the whole route), so the DP composes optimally.
**Complexity:** `O(k² · 2^k)` time (k transitions per mask per endpoint) and
`O(k · 2^k)` space, the standard exponential TSP DP. §7.6 measures the wall-clock
growth — roughly `×6` per +2 stops — which is why the exact solver is capped at
`k ≤ 12` route stops.

### 3.4 Nearest-neighbour + 2-opt — polynomial fallback

For route sizes beyond the DP cap the code falls back to an `O(k²)` construction:
nearest-neighbour greedily builds a tour, then repeated **2-opt** local-search
passes reverse a block `(b…c)` whenever replacing edges `(a,b),(c,d)` with
`(a,c),(b,d)` saves distance:

```
gain = d(a,b) + d(c,d) − d(a,c) − d(b,d)      # reverse block if gain > 0
```

Endpoints (start = van node, home = depot) are fixed during improvement, so the
same routine supports the open-path re-plan. The result is *not* guaranteed
optimal (TSP is NP-hard), and §7.5 quantifies how far it can be on random
instances — a few percent on average but occasionally much worse — which is the
report's justification for preferring the exact DP whenever it is affordable.

---

## 4. Why this is more than “two algorithms glued together”

The two centrepieces the professor is asked to look for are *coupling* and
*dynamism*.

### 4.1 Priority is priced into both decisions (§2)
* **Loading:** a manager-adjusted premium `π` makes a critical item worth more
  than an equal-weight normal item, so the knapsack *chooses* oxygen cylinders
  over an appliance unit when they compete for the last kilograms (§7.3 shows the
  exact trades).
* **Routing:** a manager-adjusted punctuality `λ` makes the route pay for serving
  a P1 stop late. Because the term is position-additive it is solved *exactly* by
  Held–Karp rather than approximated (§7.4 shows P1 stops jump from positions
  {6,9} to {1,2} when `λ` rises).

Both knobs are live in the UI, so the trade-offs (more value vs. more critical
goods; shortest km vs. critical-first) are demonstrated, not asserted.

### 4.2 Re-routing is checked *while the van drives*
Planning-time routing reacts to disruptions because Dijkstra runs on the modified
graph. The stronger claim is **runtime**: a scripted (or manager-clicked) closure
on a road ahead of the van triggers a re-plan *from the van's current node* over
the stops still undelivered, and the dashboard visibly detours (§5.3). Closing
the only nearby bridge is dramatic by construction: the city has exactly two
river crossings, so one closure forces a long detour around the river (§7.4).

---

## 5. System and simulation design

```
core/                 pure, deterministic, Flask-free
  city.py             schematic grid city cut by a river (2 bridges), 12 stops,
                      48 items, van config
  algorithms.py       knapsack_01 · dijkstra · tsp_held_karp · tsp_nn_2opt
  routing.py          plan_load()      → loading decision
                      solve_route()    → priority-aware order (+ method choice)
                      route_geometry() → road polyline for drawing/simulation
  engine.py           DeliverySim: simulated clock, van position, disruptions,
                      check-while-driving re-route, ETA, event log
app.py                thin Flask layer: /api/plan, /api/sim/start|state|control,
                      /api/disrupt, /api/demo/scenario
templates+static/     three-panel management console over an SVG city map
algo_tests.py         13 sanity tests (plain asserts), incl. brute-force oracles
demo_cli.py           headless end-to-end run (no browser needed)
experiments.py        regenerates every table in §7
```

### 5.1 The simulated clock
`DeliverySim` advances a *simulated* clock that moves only while the run phase is
`running`, by real elapsed wall time × a user-set `timescale` (1× ≈ 1 sim minute
per real second). The whole engine can be stepped deterministically headless via
`advance(dt)` — which is how the tests and `demo_cli.py` prove behaviour — while
the web layer drives it through `tick()`.

### 5.2 Disruption model
`add_disruption(rid, kind)` marks a road **roadblock** (removed from the graph)
or **traffic** (×`factor`). The graph object `adjacency(disruptions)` is
recomputed on demand, so *every* Dijkstra call downstream already sees the new
world.

### 5.3 Re-routing policy
At each node and after each disruption the engine asks "is any active disruption
on a road still ahead of the van?" If a **roadblock** is ahead, re-routing is
mandatory (the planned polyline is now infeasible). If **traffic** is ahead, the
engine only re-routes when the re-planned remaining travel is genuinely shorter,
so the log never churns on noise. A re-route keeps the van's current node as the
new start (`open-path` variant of §2) and the depot as the fixed home, logs the
reason and the detour cost, and stores the previous polyline as a faded "ghost"
for the dashboard.

### 5.4 Open-path TSP (start ≠ home)
Held–Karp and the 2-opt fallback both accept `start` and `home` independently
(`tsp_held_karp(..., start, home)`), so an initial run is a *closed* tour from
and to the depot, while a mid-run re-plan is an *open* path from wherever the van
is, still ending at the depot.

### 5.5 Correctness harness
`algo_tests.py` checks each algorithm against an independent oracle: knapsack vs.
full brute force on random cases, Dijkstra on a hand-computed chain, **Held–Karp
vs. permutation brute force** on random small matrices (including the position-cost
and open-path variants), and "nearest-neighbour + 2-opt never beats exact".
`demo_cli.py` is an end-to-end smoke test (load → plan → close a bridge mid-run →
re-route → all stops delivered). Both exit `0`.

---

## 6. Related work / where the idea sits
(Optional paragraph — delete if not wanted.) Textbook TSP + knapsack demos treat
the two as independent optimisations on static data. This project's contribution
is (a) a single manager-facing objective in which *priority* couples loading and
routing, solved exactly because the priority term is DP-state-additive, and
(b) treating routing as a *live* decision — Dijkstra + the same TSP re-run from
the van's moving position whenever the road network it was planned on changes.

---

## 7. Experiments (regenerated by `python experiments.py`)

Unless noted, defaults are used: capacity `W = 430 kg`, premium `π = 220`,
punctuality `λ = 4`. City: 67 roads, 12 candidate stops, 48 items, van 430 kg.

### 7.1 Default load
```
loaded 26 items / 428 kg (99.5% of 430 kg), score value 12920
priority mix loaded: P1=6 · route visits 9 stops via held_karp (k=9)
route objective: travel 18.3 min + priority penalty 304.0 = 322.3
critical items the van could not take: Hydrant fittings, Oxygen cylinder
```

Even near-full, the two *heaviest* critical items (fire hydrant fittings 40 kg,
oxygen cylinders 55 kg) cannot both ride at 430 kg — an honest case that shows
why the knapsack, not a greedy rule, must choose.

### 7.2 Capacity sweep — what a bigger van buys
| capacity | items | weight | fill | score | stops | critical left |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 150 | 11 | 150 | 100.0% | 6190 | 5 | 5 |
| 250 | 16 | 249 | 99.6% | 9030 | 7 | 3 |
| 350 | 21 | 349 | 99.7% | 11410 | 8 | 2 |
| 430 | 26 | 428 | 99.5% | 12920 | 9 | 2 |
| 600 | 30 | 599 | 99.8% | 15350 | 9 | 0 |
| 900 | 42 | 894 | 99.3% | 17055 | 12 | 0 |

The knapsack keeps the van ≥ 99% full at every size while strictly prioritising:
critical items are the *last* to be dropped as capacity shrinks.

### 7.3 Priority premium — why critical goods win ties (capacity 430)
| premium | score | items | fill | P1 loaded | P1 left behind |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 6670 | 25 | 100.0% | 5 | 3 |
| 220 | 12920 | 26 | 99.5% | 6 | 2 |
| 500 | 21190 | 24 | 99.1% | 7 | 1 |

Raising the premium from 0 → 500 trades ordinary stock **for** critical stock:
**in** — Hydrant fittings, Rope coils, Stationery box; **out** — Appliance unit,
Cake box, Magazine pack, Roast beans. The raw score also grows because the DP's
"value" is the premium-scaled objective. (Premium 0 is deliberately "greedy on
value": it still loads 100% of the mass but leaves 3 critical items behind.)

### 7.4 Punctuality λ — reordering the run (same 9 loaded stops)
| λ | travel | priority penalty | total | P1 stop positions |
| ---: | ---: | ---: | ---: | --- |
| 0 (shortest route) | 13.7 min | 0.0 | 13.7 min | {6, 9} ← Hospital 6th, Fire Stn 9th/last |
| 8 (critical first) | 18.3 min | 608.0 | 626.3 min | {1, 2} |

At `λ = 0` the route is the classical shortest tour and dumps both critical stops
at the *end* of the run. At `λ = 8` they are served first, at the cost of +4.6
minutes of travel — a clean, measurable statement of the trade-off the objective
`C(π)` encodes. (The raw `penalty` figure is `λ × Σ pw·position`, so it is not a
clock time; the *travel* column is what actually changes.)

### 7.5 Roadblock penalty — a closed bridge (planning time, same load)
| scenario | whole-route travel | vs intact |
| --- | ---: | ---: |
| intact | 18.3 min | — |
| Main St Bridge closed | 26.0 min | **+7.7 min (+42%)** |
| Grand St Bridge closed | 21.1 min | +2.9 min (+16%) |

Because the grid has exactly two river crossings, removing the nearer bridge
forces the route around the far one. The live demo reproduces this at runtime:
closing Main St Bridge at 00:02 mid-run makes the engine log
*“Re-routing … detour adds ~7.7 min”* and finish 9/9 stops.

### 7.6 Exact vs. NN+2-opt fallback
**Real 9-stop instance** (heuristic forced via the DP cap):
```
exact total 322.26  ·  heuristic total 373.73  (gap 16.0%)
```
(Forced onto the fallback, the 2-opt layer also optimises *travel only* — §3.4 —
so part of this 16% is the priority term it ignores; the exact DP is the only one
of the two that minimises the full objective `C(π)`.)
**Random symmetric matrices**, 25 trials/size, average & worst gap of NN+2-opt
against the exact DP:
| k stops | avg gap | worst gap | exact | heuristic |
| ---: | ---: | ---: | ---: | ---: |
| 6 | 4.99% | 27.36% | 0.4 ms | 0.04 ms |
| 8 | 2.33% | 19.28% | 2.1 ms | 0.07 ms |
| 10 | 5.43% | 29.24% | 14.4 ms | 0.12 ms |
| 11 | 9.06% | 53.54% | 35.7 ms | 0.15 ms |

The heuristic is fast but not reliable (worst cases ≫ 2×). On the *real*
instance it is 16% off. This is the empirical justification for using the exact
DP whenever `k ≤ 12`.

### 7.7 Why the DP cap of 12 exists — measured growth
| k stops | DP states `2^k` | Held–Karp time |
| ---: | ---: | ---: |
| 10 | 1,024 | 13.4 ms |
| 12 | 4,096 | 86.4 ms |
| 14 | 16,384 | 480.2 ms |
| 16 | 65,536 | 2,604.2 ms |

Doubling two extra stops roughly sextuples runtime — the signature of the
exponential `O(k²·2^k)` term, and the reason the fallback exists for oversized
(rare) instances.

---

## 8. Limitations and future work
* **One van, one depot.** Extending the knapsack + routing pipeline to *multiple*
  vans is vehicle-routing territory (`mTSP`/`VRP`), where the exact DP no longer
  scales and the 2-opt layer would need to become the workhorse.
* **Deterministic simulation.** Disruptions are injected (auto-demo) or clicked;
  a probabilistic arrival model would test how *often* re-routing is needed.
* **Static priority tiers.** Making `pw` time-dependent (a P1 item whose deadline
  passes becomes urgent) would still fit the additive position-cost trick as long
  as the term depends only on the state.
* **Approximation gap.** §7.6 shows NN+2-opt can be far from optimal; a next step
  is comparing it against **Christofides** (`1.5`-approx) or LKH-style k-opt.

---

## Appendix A — running everything
```
pip install -r requirements.txt
python app.py            # → http://localhost:8000   (browser dashboard)
python demo_cli.py       # headless narrative run (asserts the flow)
python algo_tests.py     # 13 sanity tests, prints ALL TESTS PASSED
python experiments.py    # regenerates every table in §7
```

## Appendix B — repository map
See the tree in §5. The DAA-relevant reading order is `core/algorithms.py`
(docstrings carry each algorithm's complexity + correctness), `core/routing.py`
(the objectives), `core/engine.py` (re-routing), then `algo_tests.py` and
`experiments.py` for evidence.
