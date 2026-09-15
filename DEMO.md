# Delivery Command Center — demo script for your review

**Total time: about 8 minutes.** Everything below is verified against the current
code on `main` — the numbers are the real ones the program prints.

Read §1 the night before. Run through §2 and §4 once, in full, an hour before.
Then just follow §4 during the review.

---

## 1. The 30-second pitch (memorise this, say it first)

> "It's a delivery-route optimiser for a manager with one van. Two classic
> problems sit inside it: **what fits in the van** is a 0/1 knapsack, and
> **in what order do I visit the stops** is a Travelling Salesman problem.
>
> The part that makes it a project rather than a textbook exercise is that the
> two aren't independent — **priority couples them**. And the road network
> changes *while the van is already driving*, so the route gets recomputed live.
>
> Everything is exact where it can be: knapsack is DP, travel times are
> Dijkstra, and the routing is Held–Karp — with priority folded into the DP so
> it's still solved exactly, not approximated."

Then: **"Let me show you."** Don't explain more. Open the app.

---

## 2. Before she walks in (the 3-minute setup)

```
cd "C:\Users\Aaron Varghese\Projects\DAA_project"
python app.py
```

You should see `Delivery Command Center → http://localhost:8000`.
Open **http://localhost:8000** in Chrome/Edge. **Full-screen it** (F11) — the
three panels get cramped otherwise.

Have a second PowerShell tab ready and already `cd`'d into the project, because
you'll run two commands in it later (§4, Act 6). Pre-run them once so the
commands are in your history — just press ↑ instead of typing.

**Pre-flight, 30 seconds, do it while the room settles:**

| check | where |
| --- | --- |
| Page loads, map draws, no console errors | browser |
| Phase pill reads `idle` | top bar |
| Click **▶ Run auto-demo**, watch it finish, then **↺ Reset** | top bar → right panel |

That one click-through means you've already proven the demo works *before*
you're being watched. Reset afterwards so you start from a clean `idle` state.

**If `python app.py` tracebacks instead of printing the URL** (only happens when
output is redirected, not in a normal PowerShell window): run
`$env:PYTHONIOENCODING='utf-8'; python app.py` instead. Same for
`python experiments.py` in Act 7.

---

## 3. What you're looking at (so you're never lost)

```
1 · Plan the load      2 · Route map              3 · Dispatch & watch
(left)                 (centre)                   (right)

0/1 KNAPSACK           DIJKSTRA + TSP             LIVE RE-ROUTING
capacity               click road = roadblock     Dispatch / Pause / Reset
premium                alt-click  = traffic       route sequence
punctuality λ          van + route + ghosts       event log
scope
catalogue of 48 items
```

The city: **42 intersections, 67 roads, 12 stops, 48 items, van 430 kg.** A
river runs down the middle and **only 2 bridges cross it** — that's deliberate.
Close one bridge and the route *must* go the long way round the river, and you
can watch it happen. That's your money shot.

---

## 4. The demo, act by act

These map 1:1 onto what the project is actually claiming. If you only get three
minutes, do **Act 2, Act 3, Act 5**.

### Act 1 — The city and the plan (45 sec)

**Do:** point at the map filled with the idle preview.

**Say:**
> "The dashed blue line is the planned route. The red, amber and green circles
> are the 12 delivery stops — red is P1 critical, amber is P2, green is P3.
> The black square top-left is the depot.
>
> Every travel time in this whole program is a **Dijkstra shortest path on the
> actual road graph** — not straight-line distance. So when I change the roads,
> every number downstream changes with it."

### Act 2 — The live re-route (2 min) ← *the centrepiece*

**Do:** click **▶ Run auto-demo** in the top bar. Then **say nothing for about
20 seconds** and just let them watch the van.

What happens, in order:
1. Route is planned and the van departs.
2. At about **00:01–00:02** (a few seconds of real time) a ⛔ appears on
   **Main St Bridge** — you're watching a disruption get injected mid-run.
3. The route **re-draws**, the old path stays on screen as a **faded ghost**,
   and the van turns around and takes the far bridge.
4. Event log prints `Re-routing: Main St Bridge closed` then
   `New route: … detour adds ~8 min`.
5. All 9 stops get delivered, van returns to depot.

**Say while it runs:**
> "The van was already driving on a plan that went over that bridge. The engine
> notices the closure is on a road *still ahead of it*, throws that road out of
> the graph, and **re-runs Dijkstra and the TSP from the van's current position**
> over the stops it hasn't delivered yet — still ending back at the depot.
>
> This is the open-path version of the TSP: the start is the van's current node,
> not the depot. The old route stays on screen as a ghost so you can see what it
> gave up."

**Then point at the log:** "`detour adds ~8 min` — that's measured, not a
message I wrote in. It's `old remaining travel − new plan travel`."

> **Careful:** auto-demo **resets your sliders and ignores your checkboxes**. It's
> a canned scenario. Say so if you've been playing with settings — otherwise the
> jump will look like a bug.

### Act 3 — Priority coupling, first half: λ (1.5 min) ← *the professor's ask #1*

**Do:** in the left panel, drag **Punctuality λ** to **0**, pause, then drag it to
**8**. Watch the **Route sequence** list on the right reorder live.

**Say:**
> "The route cost is travel time **plus** λ times the priority weight times the
> stop's position in the run. So the route literally pays a penalty for serving
> a critical stop late.
>
> At **λ = 0** it's the pure shortest tour — **13.7 minutes** — but look where
> the two P1 stops land: **positions 6 and 9**. The Hospital is served sixth and
> the Fire Station is served *last*. That's the shortest route, and it's
> operationally terrible.
>
> At **λ = 8** it accepts **18.3 minutes** — almost 5 minutes more driving — to
> put the same two stops at **positions 1 and 2**.
>
> Same stops, same roads, same city. The only thing that changed is what I told
> the algorithm to care about."

> **If she says "so it's not the shortest route?"** — that's the point, and say
> so: *"It's exactly optimal for the objective I defined. The objective includes
> priority. The shortest-distance route is the optimum of a* different
> *objective — λ = 0. That's what the slider is: which objective do you want."*

### Act 4 — Priority coupling, second half: premium (1 min)

**Do:** drag **Priority premium** from **220** to **500**, keeping capacity at
430. Watch the catalogue on the left — items flip between **✓ loaded** and
**✕ not loaded**.

**Say:**
> "This is the other half of the coupling. Each item's score is its value plus
> the premium times `(3 − priority)` — so a P1 item gets `+2×premium`, P2 gets
> `+premium`, P3 gets nothing.
>
> At premium 220 the van leaves **2 critical items** behind — the hydrant
> fittings and the oxygen cylinders, they're the heaviest things in the
> catalogue and there isn't room. At premium 500 it drops ordinary stock
> instead and gets down to **1 critical item left behind**.
>
> It's still an exact knapsack either way — the premium only changes each
> item's value *before* the DP runs, so the optimality argument is untouched."

**And the coupling, said out loud:**
> "Loaded items decide which stops the route visits. So the loading decision
> feeds the routing decision — they're one pipeline, not two separate demos."

### Act 5 — Do it yourself, live (1 min)

This is the one that proves it's real and not a video.

**Do:**
1. Click **↺ Reset** (clears the auto-demo).
2. Set **λ** back to about **2**.
3. Click **🚚 Dispatch van** — the van starts driving *your* plan.
4. **Click a road ahead of the van** on the map → ⛔ appears.
5. Watch it re-route.

**Say:**
> "This is the same mechanism, but I chose the disruption. Clicking a road
> toggles a roadblock; alt-click makes it traffic — traffic only re-routes if a
> genuinely faster route exists, so the log doesn't churn."

Clicking **one** bridge is the most dramatic version — close the bridge the van
is heading for and it has to go the long way round the river. That's safe
*because you pressed Reset first*, so no bridge is currently blocked.

> 💡 Roadblock **one** bridge for the drama. If you roadblock **both**, you get
> the "both bridges are blocked" popup and the far-bank stops drop off the route
> — handled, not a crash (§6/§7), but it cuts the act short. One at a time here;
> save the both-bridges case for the §6 question.
>
> **Traffic is always safe** — alt-clicking just slows roads, it never severs
> the city.

### Act 6 — The proof (1 min)

Switch to the PowerShell tab. Run:

```
python algo_tests.py
```

**Say:** *"13 checks. The important ones are the brute-force oracles: the
knapsack agrees with exhaustive brute force, and **Held–Karp agrees with
permutation brute force** — including the position-cost and open-path variants
I need for re-routing. It also checks that closing the north bridge forces a
strictly longer detour."*

Then:

```
python experiments.py
```

**Say:** *"Every number in my report comes from this script running the real
code on the real city. Nothing is hand-written."*

Point at the §6 block — **exact 322.26 vs heuristic 373.73, a 16% gap** — and
say: *"That's why I use the exact DP and only fall back to nearest-neighbour
+2-opt past 12 stops."*

### Act 7 — The code (1 min)

Open these in your editor **in this order**, and let her read the docstrings —
they're where the complexity and correctness arguments live:

| file | what to point at |
| --- | --- |
| `core/algorithms.py` | every function has **complexity + a correctness argument** in its docstring. Point at `tsp_held_karp`'s `node_cost` hook — that's the trick that keeps priority *exact*. |
| `core/routing.py` | the two objectives in one file: `plan_load()` and `solve_route()`. This is where the coupling lives. |
| `core/engine.py` | `_maybe_reroute()` — the roadblock-mandatory vs traffic-optional policy. |

---

## 5. Numbers to have in your head

If she asks for a figure, these are all real and reproducible.

| thing | number |
| --- | --- |
| City | 42 nodes, 67 roads, 2 bridges, 12 stops, 48 items |
| Van capacity | 430 kg default (slider 80–900) |
| Default load | **26 items, 428 kg, 99.5% full**, score 12920 |
| Default route | 9 stops, Held–Karp, **travel 18.3 min** |
| λ = 0 | travel **13.7 min**, P1 stops at positions **{6, 9}** |
| λ = 8 | travel **18.3 min**, P1 stops at positions **{1, 2}** |
| Close Main St Bridge | **+7.7 min, +42%** |
| Close Grand St Bridge | +2.9 min, +16% |
| Exact vs NN+2-opt (real 9-stop) | 322.26 vs 373.73 — **16% gap** |
| Held–Karp | `O(k²·2^k)`, capped at k ≤ 12 |
| Knapsack | `O(n·W)`, exact |
| Dijkstra | `O((V+E) log V)` per source |
| Tests | 13, all pass |

Complexities — **memorise the table in REPORT.md §3**, it's the most likely
question:

| problem | algorithm | complexity | exact? |
| --- | --- | --- | --- |
| Load the van | 0/1 knapsack DP | `O(n·W)` | exact |
| All travel times | Dijkstra (binary heap) | `O((V+E) log V)` | exact |
| Route, small k | Held–Karp over subsets | `O(k²·2^k)` | exact |
| Route, large k | Nearest-neighbour + 2-opt | `O(k²)` | approx. |
| Re-route | Dijkstra + Held–Karp re-run | as above | exact |

---

## 6. Questions she'll probably ask

**"Why is the route zig-zagging? That's not the shortest path."**
> "Correct — it's not, and that's intended. At λ = 4 it's optimal for the
> *priority-aware* objective. Drag λ to 0 and it becomes the shortest tour.
> The trade-off is measurable: 13.7 min shortest vs 18.3 min critical-first."

**"Isn't TSP NP-hard? How is this exact?"**
> "It is — `O(k²·2^k)` is still exponential, I'm not claiming polynomial. But a
> delivery run has single-digit stops. It's exact to k = 12, which measures at
> about 86 ms, and past that it falls back to nearest-neighbour + 2-opt."

**"Why does λ in the DP not break exactness?"**
> This is the best question she can ask — it's the core idea. *"Because the
> priority charge depends only on the position, and the position is exactly the
> popcount of the subset mask. So it's a constant for each DP state. The
> recurrence still holds, so the DP is still exact for the full objective."*

**"What if two roads are closed?"**
> "Same mechanism, it just re-runs — the graph rebuild is on-demand, so every
> Dijkstra call already sees the current world. Closing a bridge *and* a street
> is fine, and so is slowing both bridges with traffic."

**"What if both bridges close?"** ← *worth showing her, it's a good answer*
> **Click it.** Block Main St Bridge, then Grand St Bridge. A popup appears:
> *"Both bridges are blocked — the river cuts the city in two, so stops on the
> far bank can't be reached."* The route list drops to the 3 stops still on the
> van's side, and the ones it can't reach are named in the warning under the
> load summary.
>
> Then say: *"Those are the only two river crossings, so the graph is genuinely
> severed — there's no valid tour. Rather than crash or silently return a wrong
> answer, it detects the unreachable stops, drops them, and tells the manager
> why. That's the reachability guard in `solve_route`."*
>
> Reopen one bridge and the popup clears and the full 9-stop route comes back.
> This is a nice one to end on — it shows you thought about failure, not just
> the happy path.

**"Is the data real?"**
> "No — and deliberately so. It's a deterministic schematic city, no randomness,
> so the demo and every number in the report reproduce exactly. There's no map
> library, no network calls — Flask is the only dependency."

**"What would you do next?"**
> Straight from REPORT.md §8: *"Multiple vans — that's vehicle routing, where the
> exact DP stops scaling and 2-opt becomes the workhorse. And comparing the
> fallback against Christofides, which has a 1.5 approximation guarantee — right
> now I only measure the gap empirically."*

---

## 7. Things to fix before the review

> ### ✅ Closing both bridges is handled
>
> Block Main St Bridge **and** Grand St Bridge and you get a **popup**:
> *"Both bridges are blocked — the river cuts the city in two, so stops on
> the far bank can't be reached."* The unreachable stops are dropped from the
> route and named in the warning under the load summary.
>
> It's worth **deliberately demoing** (see §6) — it shows the failure case is
> handled rather than crashing. **↺ Reset** or reopening a bridge clears it.

- [ ] **REPORT.md still says `*replace with your name*`** at the top (lines 7–10,
      name / course / institution / date). Fill those in — it's the submission
      document.
- [ ] Push to GitHub before you present, so the repo she opens matches what you
      demoed. `git push` — check `git status` is clean first.
- [ ] Decide your λ default. **λ = 4** is the shipped default and shows the
      priority effect strongly, but the route looks deliberately zig-zaggy. If
      you want it to look "smarter" at first glance, use **λ = 2** for Act 1 and
      only crank it to 8 when you're making the point in Act 3.
- [ ] Have `python experiments.py` output open in a tab already, as a fallback
      if the terminal misbehaves.

---

## 8. If something goes wrong

| symptom | fix |
| --- | --- |
| Route looks crazy / van goes somewhere you didn't ask | You're probably mid-run and pressed something. **↺ Reset** and re-dispatch. |
| "The van went to a stop with no cargo" | The van **drove through** that junction without stopping. Stops not on the route are dimmed on the map, and the **event log is the truth** — it only says "Delivered" for real deliveries. |
| Reprocessing button seems to do nothing | It's redundant by design — sliders auto-re-plan ~150 ms after you move them. And it's **disabled while the van is driving**. |
| Auto-demo did its own thing | It's meant to — it ignores your sliders and resets to defaults. Use **🚚 Dispatch** to run *your* plan. |
| Server won't start / traceback on the URL line | `$env:PYTHONIOENCODING='utf-8'; python app.py` |
| Popup: "Both bridges are blocked …" | Expected — you closed both river crossings. **↺ Reset** or reopen one bridge and it clears. See §7. |
| Port 8000 already in use | `$env:PORT='8001'; python app.py` |

---

## 9. The one thing not to forget

Your two centrepieces are **Act 3/4 (priority coupling)** and **Act 2 (live
re-routing)**. Everything else is supporting evidence. If you're running short
on time, cut Act 1 and Act 7 — never cut those two.

And say the words **"exact, not approximated"** at least once about the routing.
That's the sentence that separates this from a demo that just calls a solver.
