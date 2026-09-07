# Delivery Command Center — a plain-English guide to the whole project

This file explains **everything**: what the project is, what every file does,
what every button on the website does, how the algorithms connect, and — most
importantly — which behaviours you saw are *intended* vs *a bug* (you hit a few
confusing ones). It's written for you, the author, so you understand it well
enough to explain it and to make the "right" choices yourself.

Companion documents: `README.md` (short pitch + how to run) and `REPORT.md`
(the formal DAA write-up with the experiment numbers). This guide is the
"how do I actually use and understand it" layer.

---

## 1. The one-sentence idea

A delivery manager has one van, a catalogue of items, and a list of delivery
stops in a city. Two questions, in order:

1. **What fits in the van?** — a *0/1 knapsack* problem.
2. **In what order do I visit the stops?** — a *Travelling Salesman* problem.

The twist that makes this a course project and not a textbook demo:
**priority** (is the cargo critical?) shapes **both** decisions, and the road
network can change **while the van is already driving** (roadblock / traffic),
so the route is recomputed live.

---

## 2. The city (everything is fake but deterministic)

Open the browser map and you're looking at a hand-drawn city that the program
generates every time, identically (no randomness → reproducible demos and
numbers):

| thing | value |
| --- | --- |
| Road grid | 7 avenues × 6 streets = **42 intersections (nodes)** |
| Roads | **67** named road segments |
| River | runs north–south down the middle |
| Bridges | only **2** cross the river (Main St Bridge, Grand St Bridge) |
| Depot | top-left corner (black square) |
| Delivery stops | **12** commercial stops, each on its own node |
| Catalogue | **48** items, 4 offered per stop |
| Van | capacity **430 kg** by default (slider: 80–900) |

Why only two bridges? So that **closing a bridge is dramatic** — if the only
nearby river crossing is blocked, the route *must* detour around the river, and
you can *see* the van take the long way. That's the demo money-shot.

**Priority tiers.** Every stop (and every item at it) has a tier:

| tier | meaning | stops | color on map |
| --- | --- | --- | --- |
| **P1** | critical | City Fire Station, Central Hospital | red |
| **P2** | high | Clinic, Pharmacy, School, Electronics, Mall | amber |
| **P3** | normal | Grocery, Market, Diner, Bookstore, Cafe | green |

Some P1/P2 stops also have a **deadline** (latest arrival after departure) — miss
it and the run counts a "late stop".

---

## 3. The files, explained

```
DAA_project/
├─ core/                    ← the brains. Pure Python, no web stuff.
│  ├─ city.py                 builds the city above: nodes, roads, stops, items, van
│  ├─ algorithms.py           the four algorithms (see §5) with complexity + correctness notes
│  ├─ routing.py              ties them together: plan_load() = knapsack;
│  │                          solve_route() = TSP over the loaded stops
│  └─ engine.py               the "living" sim: a van, a clock, disruptions, live re-route
├─ app.py                   thin web layer — turns browser clicks into calls into core/
├─ templates/index.html     one page, the whole dashboard
├─ static/style.css         looks
├─ static/app.js            all the browser logic (drawing, polling, buttons)
├─ algo_tests.py            sanity tests, run in the terminal, prints ALL TESTS PASSED
├─ demo_cli.py              same story as the website but printed as text (no browser)
├─ experiments.py           prints the tables that REPORT.md quotes
├─ requirements.txt         the only dependency: Flask
├─ README.md                short pitch + quick start
└─ REPORT.md                the formal write-up you hand in
```

---

## 4. The website, room by room

The dashboard has three panels. Workflows flow **left → centre → right**.

### 4.1 Header (top bar)
| control | what it does |
| --- | --- |
| clock `⏱` | simulated time of the current run (mm:ss) |
| phase pill | `idle` (no run yet — preview only) · `‖ paused` · `● running` · `■ done` |
| **▶ Run auto-demo** | one-click canned demo (§6.4). **WARNING:** it *ignores your sliders/checkboxes* and resets to the default scenario. |

### 4.2 LEFT panel — "1 · Plan the load"
This is the **knapsack** side. Four inputs, then a catalogue.

| control | default | what it changes |
| --- | --- | --- |
| **Van capacity** | 430 kg | how much total weight the knapsack may load |
| **Priority premium** | 220 | how much *value* a critical item gains in the knapsack, so it wins ties (§5.1) |
| **Punctuality λ** | 4.0 | how much the route "pays" for serving a stop late (§5.3) |
| **Deliver to** scope | Loaded stops | which stops the route is allowed to visit (§4.2a) |
| **Catalogue** | all 48 checked | uncheck an item to **exclude** it from the knapsack |

Under the sliders: a load summary (fill %, weight/capacity, and the total
"score value" — note that's the **algorithm's score**, which includes the
premium, not real money), and a warning if critical items couldn't fit.

The catalogue groups items by destination stop. After a plan each row shows its
fate:
- **✓** (blue) → loaded by the knapsack
- **✕** (dimmed, struck through) → not loaded — no room at this capacity/premium
- **⊘** (very faint) → you excluded it

**Every change auto-re-plans** ~150 ms later (the dashed route on the map, the
route list, and the item states all update). The big **"Re-plan load & route"**
button just forces that same refresh. It appears to "do nothing" when:
- you're mid-run (it's **disabled by design** while the van is driving — see §6), or
- you just moved a slider (the auto-plan already ran, so nothing is left to change).

**(a) The "Deliver to" scope — read this, it's a trap.**

| scope | the route may visit |
| --- | --- |
| **Loaded stops** | only stops that received ≥ 1 item from the knapsack (the sensible default) |
| **Every stop** | all 12 candidate stops, even ones with no cargo (a full-city tour demo) |
| **Critical only** | stops receiving a loaded P1/P2 item **plus every P1 stop, even if it has no cargo** |

That last line is the reason Fire Station didn't disappear when you unchecked
its items (see §6.2). "Critical only" means *"I always want the critical places
covered"* — so it forces the P1 *stops* regardless of whether you loaded their
items.

### 4.3 CENTRE panel — "2 · Route map"
An SVG of the city. Symbols:
- roads = grey lines; **bridges** = dark teal, slightly thicker
- river = pale band; stops = coloured circles (red/amber/green = P1/P2/P3) with short labels
- **DEPOT** = black square (top-left)
- ⛔ badge on a road = **closed**; 🐢 badge = **traffic**

Route lines:
- **dashed blue** = the current *preview* (the plan that exists before you dispatch)
- **solid blue** = the remaining road still ahead, once a run is live
- **faded dashed** = a "ghost" of an old route after the van re-routed

The van is the little black dot; the stop it's heading to **pulses**; delivered
stops turn **grey**.

**Clicking roads is the disruption system:**
- **click** a road → toggles a **roadblock** (⛔)
- **alt-click** (or shift-click) → toggles **traffic** (🐢)
- hover a road for its name / minutes / current status

If you do this *before* dispatch, the next plan simply routes around it. If you
do it *while the van is driving*, it triggers a live re-route (§5.4).

### 4.4 RIGHT panel — "3 · Dispatch & watch"
| control | what it does |
| --- | --- |
| **🚚 Dispatch van** | starts a live run using the *current* sliders/scope/exclusions (§4.5). Disabled while a run is live. |
| Pause/Resume | freezes / unfreezes the simulated clock |
| **Simulation speed** (1–6×) | how many sim-minutes per real second (§5.5) |
| KPI cards | delivered count · number of re-routes · late stops · run minutes |
| disruption dropdown + ⛔/🐢/Clear | same as clicking roads, but by picking from a list |
| **Route sequence** | the stops in visit order. Delivered rows show their arrival time + ✓ (and "⚠ X late" if late); remaining rows show projected ETA. Reorder on a re-route. |
| **Event log** (bottom, newest on top) | a timestamped narration of everything: plan → disruption → re-route → each delivery → done. Colour-coded by type. **Read this to understand what the algorithms are doing.** |

### 4.5 Dispatch = commit, not preview
This is the key mental model:
- Sliders + Re-plan = **preview only** ("here's the best plan for these settings") — nothing moves.
- **Dispatch** sends those same settings to the server, which re-runs the knapsack
  and TSP, and starts the van driving the result.

So a dispatch and its preview always agree *if the settings are identical*.

---

## 5. What the algorithms are actually doing (plain version)

### 5.1 Load = 0/1 Knapsack (`plan_load`, `core/algorithms.py:knapsack_01`)
Each item has a weight (kg) and a *score*. The score is:
```
score(item) = base value + premium × (3 − priority)
             P1 gets +2×premium, P2 gets +1×premium, P3 gets +0
```
The algorithm finds the subset with the **highest total score that still fits**
in the van. It's a dynamic program — **exact**, not a greedy guess — that tries
every item in/out and remembers the best. This is why raising the *premium*
trades ordinary stock for critical stock: the critical items now "score" enough
to justify their weight.

The load's destination stops **become the route's stops** (a loaded item must be
delivered). That's the first priority-coupling.

### 5.2 Travel time = Dijkstra (`core/algorithms.py:dijkstra`)
Between any two stops the program needs "how many minutes by road". Dijkstra
finds the shortest path on the actual road network. **It is re-run on the graph
with the disruptions applied**, so a closed bridge or traffic jam genuinely
changes the travel times — a roadblock just deletes the road, traffic multiplies
its time by a factor.

### 5.3 Order = priority-aware TSP (`solve_route`)
The route is a loop: depot → stops in some order → depot. A pure "shortest loop"
would be a normal TSP. Here the cost of a loop is:

```
route cost = total travel minutes
           + λ × (sum over stops of  priority_weight × its position in the loop)
```
with priority weights P1=3, P2=2, P3=1. **The second term charges the route for
serving a high-priority stop late.** At λ=0 the route is the pure shortest loop;
at higher λ the solver accepts extra driving to get P1 stops early.

Two solvers:
- **Held–Karp** — exact, exponential `O(k²·2^k)`. Used when there are ≤ 12 route
  stops. Because the priority charge depends only on *which* stops are visited so
  far (= position), it slots into the DP exactly — priority is optimised, not
  approximated.
- **Nearest-neighbour + 2-opt** — fast approximation for (rare) bigger instances.

That's the second priority-coupling, and §6.3 explains the consequence you saw
on the map.

### 5.4 Live re-routing (`core/engine.py`)
While a run is live the engine keeps checking whether any active disruption lies
on a road the van hasn't reached yet. If it finds one:
- **roadblock ahead** → re-route is *mandatory* (that road is gone)
- **traffic ahead** → re-route only if a genuinely faster route exists

It then **re-runs Dijkstra + the TSP from the van's current position** over the
stops still undelivered (still ending back at the depot), swaps in the new route,
and logs the reason and the detour cost. The old path stays on screen as a ghost.

### 5.5 The simulated clock
The server keeps a *simulated* clock in minutes. It only ticks while a run is
`running`, advancing by real elapsed time × the speed setting. At **1×**, one sim minute
passes per real second, so a run that spans tens of sim-minutes of driving plus
stop service time plays out in tens of real seconds; at **6×** it is ~6× quicker. (The engine is also stepable headlessly —
that's how `demo_cli.py` and the tests verify behaviour deterministically.)

---

## 6. "Is that a bug?" — the behaviours you actually asked about

### 6.1 "The route isn't the shortest — it skips a nearby stop and goes to the far end. Because of priority. Intended?"
**Yes — intended, and it's the whole point of the λ slider.** There are two
legitimate answers to "most efficient":
- **Shortest travel**: set **λ = 0** (pure shortest path, ~13.7 min for the stock
  load) — but then the critical Hospital and Fire Station get served *almost
  last*.
- **Critical first**: at the default **λ = 4** the solver is willing to drive
  **~+34% longer** (18.3 min of driving vs the 13.7-min shortest loop) to put
  P1/P2 stops early, and the result is roughly a "P1 → P2 → P3" sweep. That zig-zag is the *mathematically
  optimal* answer for the stated objective (travel + λ × lateness), solved
  exactly — it is **not** a routing bug.

So: **drag λ down to ~1** for a natural-looking route that still nudges P1
earlier, or **crank λ up** when you want to *show* the priority trade-off on
purpose. The event log and REPORT.md §7.4 spell out the cost.

### 6.2 "I unchecked all of Fire Station's items and the van still went there."
Three possible reasons — two are intended, one is a visual illusion:
1. **You were on "Critical only" scope.** That scope *forces* every P1 stop even
   if it carries nothing. Switching to **Loaded stops** fixes it (verified: the
   route drops Fire Station, 8 stops).
2. **You pressed ▶ Run auto-demo.** Auto-demo deliberately resets to the default
   load and ignores your checkboxes. Use **🚚 Dispatch** if you want your load.
3. **The van drove *through* the intersection without stopping.** Fire Station
   sits on the road between other stops, so the truck rolls past its node. On the
   map that *looks* like a visit, but the event log never says "Delivered City
   Fire Station". Look at the **✓ / delivered markers** and the log, not the
   van's path, to tell "visited" from "drove past".

If you *loaded* no items to a stop and are on **Loaded stops**, that stop is not
in the run — excluding its items does remove it (verified).

### 6.3 "The Re-plan button doesn't seem to do anything."
It works; it's just *redundant* most of the time:
- moving a slider or checking/unchecking an item **already auto-plans** ~150 ms
  later, so by the time you click, nothing is left to change;
- during a live run it's **disabled by design** (you shouldn't re-plan a van
  that's already driving). Finish the run (phase → `■ done`) and it re-enables.

### 6.4 "Why did auto-demo do its own thing?"
**Run auto-demo** = a scripted demonstration, not "use my current plan". It
resets to defaults, plans the stock load, dispatches, and schedules the first
bridge on the route to close just before the van reaches it — so you are
*guaranteed* to see a live re-route every single time. Use it to show the
"dynamic re-routing" story; use **Dispatch** to run *your* plan.

### 6.5 Anything actually wrong / inconsistent right now?
A few cosmetic / clarity gaps (no crashes, verified tests all green):
- "Critical only" forcing empty P1 stops is easy to misread (see §6.2). We can
  change it to only cover stops that have critical cargo, if you prefer.
- λ = 4 as the default makes routes look needlessly zig-zaggy to a first-time
  viewer. We can lower the default to ~1.5 so it still prioritises but looks sane.
- The map doesn't visually distinguish "van drove past a stop's intersection"
  from "van delivered here". We could make delivered stops pop more.
- None of these are *bugs* in the algorithms — `algo_tests.py` checks knapsack
  and Held–Karp against brute-force oracles and everything passes.

---

## 7. The recommended "correct" mental defaults

If you're unsure what's "right", here's a sensible way to think about it:
- **Capacity & premium** are a *business* choice: "how much room, and how much do
  I value critical goods over ordinary stock?" Higher premium = fewer critical
  items left behind (see the premium table in REPORT.md §7.3).
- **λ is a dial between two valid goals**, not right/wrong:
  - λ = 0 → shortest distance.
  - λ ≈ 1–2 → mostly natural route, slight priority nudge (**good default for a
    demo that should "look smart"**).
  - λ ≥ 4 → visibly critical-first, shows the trade-off on purpose.
- **Loaded stops** scope is the intuitive default. "Critical only" is a
  "must-cover the critical places" mode. "Every stop" is a showcase of the full
  city circuit.
- **Watch the event log** — it narrates *why* the van does what it does
  ("traffic on X — current route still best", "Re-routing… detour adds ~7.7 min").

---

## 8. How to run everything

From the project folder in PowerShell:

```
python app.py            # → open http://localhost:8000  (the dashboard)
python demo_cli.py       # headless text version of the same story
python algo_tests.py     # sanity tests → prints ALL TESTS PASSED
python experiments.py    # prints every number REPORT.md quotes
```

Suggested first browser session (≈1 minute, no explaining needed):
1. Open the app. Click **▶ Run auto-demo** and watch the ⛔ close + live detour.
2. Drag **λ** down to 0 and back up to 8 — watch the route list reorder and the
   map change. That single motion demonstrates the priority model.
3. Drag **premium** 0 → 500 — watch ✓/✕ change on the catalogue (critical items
   come in, ordinary stock goes out).
4. Start a fresh dispatch (**Loaded stops**), pause it, then **click a road ahead**
   of the van → resume and watch it detour on *your* route.

---

## 9. Where the "proof" lives
- `algo_tests.py` — 13 checks: knapsack vs brute-force, Held–Karp vs permutation
  brute-force, NN+2-opt never beats exact, roadblock makes the detour strictly
  longer, etc.
- `experiments.py` → the numbers in REPORT.md §7 (capacity sweep, premium
  trade-offs, λ reorder, bridge-closure +42%, exact-vs-heuristic gap, DP growth).
  Re-run it any time to re-verify.
- REPORT.md is the submission document — **fill in your name / course / dates** at
  the top before handing it in.

If after reading this you'd like any of the three changes in §6.5 (softer default
λ, "Critical only" that follows exclusions, or clearer delivered-vs-passed
visuals), just say which and I'll make them.
