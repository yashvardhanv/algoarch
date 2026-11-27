# Lesson 57 — Case Study: Maps Routing and ETA (Google Maps)

> **Priority:** ★★★★☆ (proposed; the curriculum data holds the final rating) — "design Google Maps" is a standard prompt, and most answers say "Dijkstra" and stop at the first question about a continent, or about traffic.
>
> **Study time:** 80 minutes. **Do this after:** Proximity Service & Location-Based Systems; Scaling Patterns I: Reads, Writes and Contention.
>
> **Level:** extended.

A route is a shortest path on a road graph, and an ETA is the same path priced at the speeds the roads will have when you reach them. The first part is a solved algorithm problem with a sharp trade-off (preprocess for fast queries, then live traffic undoes the preprocessing); the second is a data problem (most roads have no fresh measurement) with a modelling trap (a forecast can make "leave later" arrive sooner). This lesson builds the search methods, a contraction hierarchy and a time-dependent ETA model as small code checked in `test/lesson_code/sy57_check.py` against Floyd-Warshall and brute-force enumeration; capacity numbers come from `capacity_check_e.py`. Finding places near a point is not repeated (see Proximity Service & Location-Based Systems).

---

## 1. Mental Model

> **Routing is a shortest-path query on a graph that was prepared for the question. Preprocessing buys query speed by freezing edge weights; live traffic changes the weights; so every design is a choice about how much of the preparation survives a change.**

- **Plain Dijkstra is exact and too slow at continental scale:** the survey this lesson reads reports 9,326,696 vertices scanned and about 2.2 seconds per random query on a 18.0-million-vertex road network.
- **A geographic guess barely helps.** A* with "straight-line distance over top speed" is correct but the bound is poor, because one fast road makes everything look close.
- **A hierarchy helps a lot** because long trips all funnel onto a few important roads: contract the unimportant vertices, keep shortcuts, search only upward.
- **The hierarchy assumes the weights.** Change a weight and the shortcuts built from it are wrong. Customization, repair or a different time model is the price.
- **An ETA is not a distance.** It is a sum of traversal times that depend on when you arrive, so the model has to respect first-in, first-out (leaving later must not arrive earlier) or the search quietly returns wrong answers.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "shortest route between two points" | Dijkstra on a directed graph, bidirectional to halve the work; say the weights are travel seconds, not metres |
| "continental scale, millisecond answers" | preprocessing: a contraction hierarchy (or a partition-based overlay) and upward-only search |
| "A* with straight-line distance" | correct, but weak on road networks; say why (section 5) |
| "include live traffic" | weights change: customization or a separate speed overlay, and a fallback to history where there are no probes |
| "ETA 30 minutes from now", "leave at 8am" | time-dependent edge costs that obey FIFO; blend live into history with a horizon |
| "snap my GPS dot to a road" | nearest-edge lookup (spatial index, see Proximity Service & Location-Based Systems), then use the edge in the graph |
| "avoid tolls", "bike or car" | a different cost function: a different customization, or a different graph |

---

## 3. Requirements and Capacity

**Functional.** Route between two points for a mode; turn-by-turn steps; an ETA that reflects traffic; alternatives; re-routing as conditions change. **Out of scope:** public transit timetables, map rendering and tiles, place search, the machine-learning model itself.

**Non-functional.** Exact shortest paths for the chosen cost function (the survey: current state-of-the-art algorithms are provably exact); interactive latency; traffic fresh within minutes; degrade to history, never to nothing.

**Capacity estimate.** Inputs marked *survey* are figures printed in Bast et al., *Route Planning in Transportation Networks* (2015): a road network of Western Europe, one core of an Intel X5680 server of that time, random source and target pairs. They are **old hardware and random long-range queries**, so use them for ratios, not for a hardware budget; real queries are mostly local and faster. Inputs marked *assumed* are this lesson's. Every result is reproduced by `capacity_check_e.py`.

| Input | Value |
|---|---|
| road graph | 18.0 million vertices, 42.5 million directed arcs *(survey)* |
| Dijkstra query | 9,326,696 vertices scanned, 2,195,080 microseconds *(survey, Table 1)* |
| bidirectional Dijkstra | 1,205,660 microseconds *(survey)* |
| contraction hierarchy query | 280 vertices scanned, 110 microseconds, distance only *(survey, Table 1; the Table 2 variant with paths is 0.21 ms)* |
| partition overlay (CRP) | 1.81 ms for a path; a new cost function applied in about 370 ms on a 12-core server *(survey, Table 2 and text)* |
| peak request rate, one region | 50,000 route requests per second *(assumed)* |
| navigating drivers in the region | 1,000,000, one GPS ping per 5 seconds, 100 bytes each *(assumed)* |
| history | a week in 15-minute buckets, one byte of quantised speed per bucket *(assumed)* |

| Result | Arithmetic | Value |
|---|---|---|
| graph in memory | 42.5M arcs x 8 bytes + 18.0M vertices x 4 bytes *(assumed layout)* | 0.38 GiB (the survey's Dijkstra row reports 0.4 GiB) |
| speed-up of the hierarchy | 2,195,080 / 110 | 19,955 times fewer microseconds per query |
| cores at 50,000 route requests per second, plain Dijkstra | 50,000 x 2.195 s | 109,754 cores (bidirectional: 60,283) |
| the same, contraction hierarchy with paths | 50,000 x 0.21 ms | 10.5 cores |
| the same, partition overlay with paths | 50,000 x 1.81 ms | 90.5 cores |
| probe traffic | 1,000,000 / 5 s | 200,000 pings per second; 12,000,000 per minute; 20 MB per second |
| share of arcs that could have one sample in a minute | 12,000,000 / 42.5M, if every ping hit a different arc | at most 28.2% (in reality far less: pings pile onto busy roads) |
| history per arc as a series | 42.5M x 672 buckets x 1 byte | 28.6 GB |
| history as a shared profile id per arc | 42.5M x 2 bytes + 1,000 profiles x 672 | 86 MB, 333 times smaller (a design choice; the number of profiles is assumed) |
| refreshing the overlay once a minute | 370 ms / 60 s | 0.62% of one 12-core server |

Read the table in this order. The hierarchy is the difference between an impossible 109,754 cores and ten, and the overlay costs about nine times the hierarchy's cores to keep traffic fresh. Then notice the probe row: 200,000 pings per second sounds like a lot of data and is still too little to measure most of the graph in a minute. **The ETA model must work on roads it has not seen a car on recently.** That is a data-sparsity problem, and section 7 handles it.

---

## 4. API and Data Model

```
POST /v1/route   { origin: {lat, lon}, destination: {lat, lon}, mode: "car", depart_at?: ts, avoid?: ["tolls"] }
  -> { routes: [ { polyline, steps: [...], distance_m, eta_s, traffic_version } ], snapped: { origin_edge, destination_edge } }
```

| Store | Contents | Notes |
|---|---|---|
| graph tiles | vertices, edges (length, class, one-way flag), turn restrictions and penalties, coordinates for snapping | static between map releases; tile by area so a regional extract fits in memory |
| preprocessing | contraction order and shortcuts, or overlay cells, per cost function | rebuilt on a map release; the metric part re-run on traffic |
| history | a profile id per edge, a table of profiles by time of week | section 3: shared profiles, not a series per edge |
| live speeds | edge id -> (estimated speed, sample count, timestamp) | written by the probe pipeline, read by customization and by ETA |
| ETA correction | the learned residual model (section 7) | a separate service in front of or after the router |

`traffic_version` lets a bug report name the speeds that produced an ETA.

---

## 5. Deep Dive 1: Searching a Graph, and Why the Easy Speed-Ups Disappoint

Three searches, one block. `dijkstra` is the baseline. `astar` adds a potential `h(u)`: a lower bound on the distance from `u` to the target that is also *consistent* (`h(u) <= w(u,v) + h(v)`); then the first time the target is taken from the queue it is exact. `bidirectional` runs a forward search and a backward search on the reversed graph. Its stopping rule is the part people get wrong: the two searches meeting at a vertex does not mean they have found the shortest path. Stop only when the two queue tops added together reach the best meeting seen.

```python
import heapq
INF = float('inf')

def reverse(adj):
    radj = [[] for _ in adj]
    for u, arcs in enumerate(adj):
        for v, w in arcs:
            radj[v].append((u, w))
    return radj

def _chain(prev, s, t):
    path = [t]
    while path[-1] != s:
        path.append(prev[path[-1]])
    return path[::-1]

def dijkstra(adj, s, t, stats=None):
    """adj[u] = [(v, w)], w >= 0. Returns (distance, path); (INF, None) if t is unreachable."""
    dist, prev, done = {s: 0}, {}, set()
    pq = [(0, s)]
    while pq:
        d, u = heapq.heappop(pq)
        if u in done:
            continue
        done.add(u)
        if stats is not None:
            stats['settled'] += 1
        if u == t:
            return d, _chain(prev, s, t)
        for v, w in adj[u]:
            if d + w < dist.get(v, INF):
                dist[v], prev[v] = d + w, u
                heapq.heappush(pq, (d + w, v))
    return INF, None

def astar(adj, s, t, h, stats=None):
    """h(u) must never exceed the true distance u->t and must satisfy h(u) <= w(u,v) + h(v) (consistent)."""
    g, prev, done = {s: 0}, {}, set()
    pq = [(h(s), 0, s)]
    while pq:
        _, d, u = heapq.heappop(pq)
        if u in done:
            continue
        done.add(u)
        if stats is not None:
            stats['settled'] += 1
        if u == t:
            return d, _chain(prev, s, t)
        for v, w in adj[u]:
            if v not in done and d + w < g.get(v, INF):
                g[v], prev[v] = d + w, u
                heapq.heappush(pq, (d + w + h(v), d + w, v))
    return INF, None

def bidirectional(adj, radj, s, t):
    """Forward search on adj, backward search on radj. Stop only when the two queue tops together reach the best
    meeting found; the first vertex both searches touch is not necessarily on the shortest path."""
    if s == t:
        return 0, [s]
    dist, prev, pq = [{s: 0}, {t: 0}], [{}, {}], [[(0, s)], [(0, t)]]
    g = (adj, radj)
    best, via = INF, None                       # via = (side, u, v): the arc u->v on this side closed the best meeting
    while pq[0] and pq[1]:
        if pq[0][0][0] + pq[1][0][0] >= best:
            break
        side = 0 if pq[0][0][0] <= pq[1][0][0] else 1
        d, u = heapq.heappop(pq[side])
        if d > dist[side][u]:
            continue
        for v, w in g[side][u]:
            if d + w < dist[side].get(v, INF):
                dist[side][v], prev[side][v] = d + w, u
                heapq.heappush(pq[side], (d + w, v))
            if v in dist[1 - side] and d + w + dist[1 - side][v] < best:
                best, via = d + w + dist[1 - side][v], (side, u, v)
    if via is None:
        return INF, None
    side, u, v = via                            # side 0: s..u, arc u->v, v..t.  side 1: s..v, arc v->u, u..t
    a, b = (u, v) if side == 0 else (v, u)
    left = _chain(prev[0], s, a)
    right = [b]
    while right[-1] != t:
        right.append(prev[1][right[-1]])
    return best, left + right
```

**What the survey says about each.** Bidirectional search visits roughly half as many vertices as the one-directional search on road networks. A* with geographic distance divided by the maximum speed in the network gives a poor bound and little or no gain, and the survey says it performs poorly against other modern methods even for distance. The lesson's explanation: the fastest road, which most trips barely use, sets the scale for every step.

**What the checks do.** Every algorithm is compared with Floyd-Warshall on 600 random directed graphs of up to 13 vertices, **all** pairs, with tiny weight ranges so zero-weight arcs, parallel arcs, ties and unreachable pairs are common; each returned path must exist arc by arc and add up to the reported distance. Then they are compared with a separate O(n²) array Dijkstra on graphs of 100 to 220 vertices, because a bug can hide in a 13-vertex graph. A fixed graph (`trap`) has a first meeting that is not shortest: stopping there returns 20 instead of 4.

**A* needs a feasible bound.** On a 14 by 14 grid the Manhattan distance times the cheapest step is exact; the same bound multiplied by 3 is wrong on more than ten of 150 random queries, with no warning.

**Measured here (illustrative; a toy graph, not a road network).** On a 40 by 40 road-like grid (1,600 vertices, 6,240 arcs; local streets cost 8 to 12, every fifth row and column is a fast road costing 2 or 3), averaged over 100 random pairs, the searches settle:

| Method | Vertices settled per query |
|---|---|
| Dijkstra | 888.3 |
| A*, potential = 2 x Manhattan distance | 280.3 |
| contraction hierarchy | 71.8 |

The A* potential has to use the fast roads' cost (2) to stay a lower bound, so on streets costing about 10 it guides weakly. That is the survey's point in miniature.

---

## 6. Deep Dive 2: Contraction Hierarchies, and What Traffic Does to Them

**Idea.** Order the vertices by "importance". Contract them from least to most important. To contract `v`, remove it, and for every pair of neighbours `u -> v -> w` add a shortcut `u -> w` of weight `w(u,v) + w(v,w)` **unless a path that avoids `v` and is at least as short already exists** (a *witness*). A query runs two searches that only follow arcs to higher-ranked vertices. The survey states the guarantee: the highest-ranked vertex on the true shortest path is reached by both searches with exact distances, so the best meeting is exact; and the searches cannot stop at the first meeting. A path is unpacked by replacing each shortcut with the two arcs through its middle vertex.

```python
class CH:
    """Contraction hierarchy. Contract vertices one at a time; when v goes, add a shortcut u->w only if the path
    u->v->w is the shortest u->w path that avoids v (a 'witness' search looks for a path at least as short)."""
    def __init__(self, adj, order=None, settle_limit=60):
        n = len(adj)
        out, inn = [dict() for _ in range(n)], [dict() for _ in range(n)]
        for u in range(n):
            for v, w in adj[u]:
                if u != v and w < out[u].get(v, INF):
                    out[u][v] = inn[v][u] = w
        self.out, self.inn, self.limit = out, inn, settle_limit
        self.mid, self.fwd, self.bwd, self.n_shortcuts = {}, [None] * n, [None] * n, 0
        if order is not None:
            for v in order:
                self._contract(v)
        else:
            heap = [(self._priority(v), v) for v in range(n)]
            heapq.heapify(heap)
            while heap:
                p, v = heapq.heappop(heap)
                q = self._priority(v)                    # lazy update: the cost may have changed since it was queued
                if heap and q > heap[0][0]:
                    heapq.heappush(heap, (q, v))
                else:
                    self._contract(v)

    def _needed(self, v):
        """shortcuts u->w that contracting v would force"""
        out, inn = self.out, self.inn
        found = []
        for u, wu in inn[v].items():
            targets = {w: wu + ww for w, ww in out[v].items() if w != u}
            if not targets:
                continue
            seen, pq, settled = {u: 0}, [(0, u)], 0       # witness search: bounded, avoids v
            limit = max(targets.values())
            while pq and settled < self.limit:
                d, x = heapq.heappop(pq)
                if d > seen[x]:
                    continue
                settled += 1
                if d > limit:
                    break
                for y, w in out[x].items():
                    if y != v and d + w < seen.get(y, INF):
                        seen[y] = d + w
                        heapq.heappush(pq, (d + w, y))
            for w, cand in targets.items():
                if seen.get(w, INF) > cand:                # no path as short as u->v->w: the shortcut is needed
                    found.append((u, w, cand))
        return found

    def _priority(self, v):
        return len(self._needed(v)) - len(self.inn[v]) - len(self.out[v])   # edge difference

    def _contract(self, v):
        for u, w, cand in self._needed(v):
            if cand < self.out[u].get(w, INF):
                self.out[u][w] = self.inn[w][u] = cand
                self.mid[(u, w)] = v
                self.n_shortcuts += 1
        self.fwd[v], self.bwd[v] = list(self.out[v].items()), list(self.inn[v].items())   # the arcs that remain go upward
        for u in self.inn[v]:
            del self.out[u][v]
        for w in self.out[v]:
            del self.inn[w][v]
        self.out[v], self.inn[v] = {}, {}

    def query(self, s, t, stats=None):
        """Two upward searches; stop a side when its smallest key cannot beat the best meeting."""
        if s == t:
            return 0, [s]
        dist, prev, pq = [{s: 0}, {t: 0}], [{}, {}], [[(0, s)], [(0, t)]]
        g = (self.fwd, self.bwd)
        best, meet = INF, None
        while pq[0] or pq[1]:
            for side in (0, 1):
                if not pq[side]:
                    continue
                d, u = pq[side][0]
                if d >= best:
                    pq[side] = []
                    continue
                heapq.heappop(pq[side])
                if d > dist[side][u]:
                    continue
                if stats is not None:
                    stats['settled'] += 1
                if u in dist[1 - side] and d + dist[1 - side][u] < best:
                    best, meet = d + dist[1 - side][u], u
                for v, w in g[side][u]:
                    if d + w < dist[side].get(v, INF):
                        dist[side][v], prev[side][v] = d + w, u
                        heapq.heappush(pq[side], (d + w, v))
        if meet is None:
            return INF, None
        hops = _chain(prev[0], s, meet)
        while hops[-1] != t:
            hops.append(prev[1][hops[-1]])
        path = [s]
        for a, b in zip(hops, hops[1:]):
            todo = [(a, b)]
            while todo:                                       # unpack shortcuts through their middle vertex
                x, y = todo.pop()
                m = self.mid.get((x, y))
                if m is None:
                    path.append(y)
                else:
                    todo.extend([(m, y), (x, m)])
        return best, path
```

**Two properties the code relies on, and the checks for them.**

- **Correct for any order.** The order changes the number of shortcuts and the query speed, never the answer. The checks build the hierarchy with a *random* order as well as the edge-difference order (shortcuts added minus arcs removed), and then run two broken copies (a witness search allowed to pass through `v`, and a query that stops at the first meeting) to prove the comparison with Floyd-Warshall catches them; both are caught within the first five random graphs.
- **A bounded witness search is safe.** It settles at most 60 vertices; giving up finds no witness, so a possibly unnecessary shortcut is added. Missing a witness costs space; wrongly finding one loses a shortcut and breaks answers.

**Where it works and where it does not (measured).** On the 40 by 40 road-like grid above, contraction adds 3,852 shortcuts over the 6,240 original arcs and the query settles 71.8 vertices against 888.3 for Dijkstra. On a 14 by 14 grid of nearly uniform streets (weights 3 to 7, no fast roads) there is no hierarchy to exploit: 830 shortcuts over 728 arcs and 39.5 vertices settled per query against 39.8 for A* and 104.1 for Dijkstra. The idea pays only where long trips funnel onto few roads, which real road networks do. The survey adds that finding the best contraction order is NP-hard, so orders are heuristic, and it notes the common belief that turn penalties cost little turned out to be wrong for CH (its Table 2 row with the compact turn representation scans 1,998 vertices in 2.27 ms against 280 vertices and 0.11 ms without turns).

**Traffic changes the weights; the survey lists four responses.**

| Response | What it does | Cost |
|---|---|---|
| rebuild | rerun the preprocessing | exact, but minutes: too slow to follow traffic |
| repair | track which shortcuts depended on the changed arcs and redo only those | works best when the changed arcs are unimportant ones; the survey reports mixed success |
| adapt the query | keep the old preprocessing and let the search route around shortcuts that are now wrong | fine when queries are rare relative to updates; ALT-style bounds stay valid when weights only increase |
| split preprocessing | topology-only work once, a cheap metric-dependent step per update | for a partition overlay, about 370 ms to apply a new cost function; 36 ms with GPUs |

That last row is why a design can honestly say: "contraction hierarchy for static or slowly changing weights, a metric-independent overlay or customizable hierarchy when weights change often". In section 3 the overlay costs 90.5 cores against 10.5 for the hierarchy at the same request rate, and buys fresh traffic. **Do not say which of these a given company runs unless a source says so**: the survey states that companies tend to be secretive and names only a few (OSRM uses a hierarchy for its queries; Bing Maps uses the overlay method), and this lesson read nothing from Google about its routing algorithm.

---

## 7. Deep Dive 3: ETA, Time-Dependence and Sparse Data

An ETA is not distance over speed. Three layers, from the lesson's reading of the sources:

1. **A time-dependent path cost.** Each edge's travel time depends on the clock time at which you enter it. Dijkstra still works on such a graph if every edge function obeys **FIFO**: leaving later never arrives earlier (the survey's non-overtaking property). Then settling a vertex at its earliest arrival is safe.
2. **A speed per edge that is a blend of what is happening and what usually happens.** Google's own descriptions (its 3 September 2020 post and DeepMind's of the same date) say live traffic is combined with historical patterns by machine learning, because live data does not say what traffic will be 10, 20 or 50 minutes into a drive. The blend below is **this lesson's simple stand-in**, not what Google runs.
3. **A learned correction.** Uber's engineering post (10 February 2022) describes a routing engine that sums segment traversal times along the best path, followed by a model that predicts the residual between that ETA and observed outcomes; the post calls this the highest-QPS model at Uber and gives a budget of a few milliseconds.

```python
def arrival_fn(points):
    """points = [(t, travel_time)] sorted by t, linear between, flat outside. Returns f(depart) -> arrival."""
    def f(t):
        if t <= points[0][0]:
            return t + points[0][1]
        for (a, x), (b, y) in zip(points, points[1:]):
            if t <= b:
                return t + x + (y - x) * (t - a) / (b - a)
        return t + points[-1][1]
    return f

def profile_is_fifo(points):
    """FIFO: leaving later never arrives earlier, i.e. travel time falls by at most 1 second per second."""
    return all(y - x >= -(b - a) for (a, x), (b, y) in zip(points, points[1:]))

def td_dijkstra(adj, s, t, t0):
    """adj[u] = [(v, f)], f(depart) -> arrival. Correct only if every f is FIFO."""
    best, pq = {s: t0}, [(t0, s)]
    while pq:
        now, u = heapq.heappop(pq)
        if now > best[u]:
            continue
        if u == t:
            return now
        for v, f in adj[u]:
            a = f(now)
            if a < best.get(v, INF):
                best[v] = a
                heapq.heappush(pq, (a, v))
    return INF

def blended_speed(hist, live, tau, horizon):
    """Seconds ahead of now -> speed in m/s: the live reading fades linearly into the historical profile."""
    w = max(0.0, 1 - tau / horizon)
    return hist + (live - hist) * w

def traverse(pieces, tau0, hist, live, horizon):
    """Drive the pieces (lengths in metres) in order; each uses the speed in force when it is entered."""
    tau = tau0
    for length in pieces:
        tau += length / blended_speed(hist, live, tau, horizon)
    return tau

def estimate_speed(samples, now, hist, half_life, prior):
    """Weighted mean of recent probe speeds, shrunk toward history: `prior` counts as that many fresh samples."""
    num, den = prior * hist, prior
    for ts, speed in samples:
        w = 0.5 ** ((now - ts) / half_life)
        num, den = num + w * speed, den + w
    return num / den
```

**FIFO is checkable per edge.** For a piecewise-linear travel-time profile, leaving later arrives no earlier exactly when the travel time falls by at most one second per second, which `profile_is_fifo` tests breakpoint by breakpoint (slope exactly -1 is allowed: arrival is flat). The checks compare `td_dijkstra` with brute-force enumeration of every simple path on 400 random small graphs with random FIFO profiles, then show the failure: an edge that takes 100 s when leaving at 0 and 0 s when leaving at 10 makes the search report arrival at 100, while waiting 10 seconds arrives at 10. The search never tries waiting, so it silently returns a worse answer.

**A forecast can create that failure by itself.** Give a segment a historical speed of 20 m/s, a live speed of 2 m/s (a jam right now), and let the live reading fade to history over 3,600 s. Treat a 10 km road as one segment priced at its entry speed: leaving now arrives at 5,000 s; leaving 100 s later arrives at 4,100 s. The model says wait, so Dijkstra's answer is no longer optimal. Cut the same road into 100 pieces of 100 m, each priced at the speed in force when it is entered, and the arrival for leaving now is 1,648 s and the arrival function is nondecreasing across 145 departures (checked). Long segments with a forecast that changes quickly break FIFO; short ones, or integrating speed along the segment, do not. Segment granularity is part of the model, not a detail.

**Sparse data.** Section 3 showed that at most 28.2% of arcs can receive a sample in a minute even if every ping hit a distinct arc. `estimate_speed` is a shrinkage estimate: probe speeds are weighted by `0.5 ** (age / half_life)`, and the historical speed counts as `prior` extra fresh samples. With no samples it returns history exactly; thirty fresh samples of 3 m/s against a history of 20 m/s with a prior of 3 give about 4.5 m/s; one sample moves it a quarter of the way (to 15.75); samples a day old are ignored. The checks compare it with the definition over 500 random sample sets. The half-life and prior are illustrative knobs, not tuned values.

**Not covered:** turn costs in this lesson's hierarchy code, map matching of probes, the learned corrections, incident ingestion, public transit.

---

## 8. Failure Modes

| What breaks | What you see | Defence |
|---|---|---|
| traffic weights change under a hierarchy | stale shortcuts: a route through a jam, or an ETA that disagrees with the route | customization or an overlay for the live metric; rebuild on map releases |
| a heuristic that is not a lower bound | a path that is not shortest, no error | feasibility check on the potential; compare with Dijkstra in tests |
| first-meeting stop in bidirectional search | slightly long routes on some pairs | stop on the queue-top sum (the `trap` check) |
| forecast breaks FIFO | search returns a route that leaving later would beat | short segments, integrate along the segment, or enforce FIFO by taking the best later arrival |
| roads with no probes | ETA equals a stale guess | shrink toward the history profile and carry the sample count and age |
| GPS snaps to the parallel road | wrong edge's speed, wrong ETA | snap with heading and the previous edge, not nearest only |
| everyone is sent to the same alternative | the alternative becomes the jam (this lesson's reasoning; no source read) | randomise among near-equal alternatives, include predicted load in the cost |

---

## 9. What Real Companies Did

- **The research survey** (Bast et al., arXiv 1504.05140, 20 April 2015, read 2026-11-27 as extracted text): the source for every search figure in this lesson. Its concluding section says companies tend to be secretive about the algorithms they use, then lists a few known ones: TomTom (a variant of arc flags with shortcuts for time-dependent queries), Bing Maps (the partition overlay), OSRM (contraction hierarchies for queries), and Transfer Patterns for public-transit journey planning on Google Maps since 2010.
- **Google Maps, traffic and route choice** (Google blog, 3 September 2020; DeepMind blog, 3 September 2020; both read 2026-11-27): live traffic comes from aggregated location data of people navigating; historical patterns are combined with live conditions by machine learning; DeepMind's work used graph neural networks over "Supersegments" (adjacent road segments sharing significant traffic) and reports ETA accuracy gains of up to 50% in some cities; the blog lists predicted traffic, road quality, directness of the road, authoritative data from local governments and incident reports among the inputs to route choice. During the pandemic the models weighted the last two to four weeks of history more heavily. **Neither post describes the shortest-path algorithm**, so this lesson does not attribute one to Google.
- **Uber** (engineering blog, 10 February 2022, read 2026-11-27): the hybrid of a routing-engine ETA and a learned residual described in section 7; a gateway service (uRoute) calls the routing engine and then the prediction service.

---

## 10. Pitfalls Checklist

1. **Saying "Dijkstra" at continental scale without a number.** The survey's figure is about 2.2 seconds per random query; that is the number to quote and then beat.
2. **Stopping bidirectional search at the first meeting.** Stop on the sum of the queue tops.
3. **Multiplying an A* heuristic to make it faster.** It stops being a lower bound and the answer silently gets worse.
4. **Preprocessing once and adding traffic later.** Weights are baked into shortcuts; say how they are refreshed.
5. **Assuming every edge has a fresh speed.** Size the probes against the edges (section 3); fall back to history.
6. **Pricing a long segment at its entry speed.** With a fast forecast this breaks FIFO.
7. **A time-dependent model without a FIFO check.** The search still answers; the answer is just not the best.
8. **Ranking places by straight-line distance.** The survey notes that ranking by travel time gives better results.
9. **Naming the algorithm a company uses when no source says so.**
10. **Measuring routing on random long pairs only.** Real queries are mostly local.

---

## Drills

1. Why can bidirectional Dijkstra not stop when the two searches first reach a common vertex? Build a four-line counterexample.
2. A* is run with `h(u) = 3 x (Manhattan distance x cheapest step)`. Is the first answer wrong, and why does it give no error?
3. In a contraction hierarchy, you contract `v` with neighbours `u` and `w`, and a path `u -> x -> w` has the same length as `u -> v -> w`. Do you add the shortcut? What breaks if you add it, and what breaks if you skip it when the witness actually passes through `v`?
4. Traffic changes a few thousand edge weights a minute. List the four responses and pick one for a design that has 50,000 requests per second, with the cores from section 3.
5. Show with the section 3 numbers why 200,000 pings per second still leaves most edges with no live sample in a minute.
6. A segment is 10 km, history is 20 m/s, live is 2 m/s and the live reading fades over an hour. Why can leaving 100 seconds later arrive earlier, and what two changes fix it?
7. How does `estimate_speed` behave with no samples, with thirty fresh samples, and with day-old samples?
8. An interviewer asks how Google Maps computes a route. What can you cite, and what must you say you do not know?

---

## Homework

1. Run `sy57_check.py` on this file. Change the bidirectional stop rule to "stop at the first meeting" and find which assertion fails first; then make the A* heuristic 3 times larger and find which fails.
2. Add one-way streets and turn penalties by turning each road into a vertex and each legal turn into an arc, and compare the contraction-hierarchy shortcut count with and without it on the road grid.
3. Replace the linear fade in `blended_speed` with an exponential one and test whether the 10 km, 20 m/s, 2 m/s example is FIFO with one piece and with 100 pieces.

---

## Sources

All read 2026-11-27. The code, the blend, the estimator, the toy graphs and every figure marked *assumed* or *illustrative* are this lesson's own.

- Hannah Bast, Daniel Delling, Andrew Goldberg, Matthias Mueller-Hannemann, Thomas Pajor, Peter Sanders, Dorothea Wagner and Renato Werneck, *Route Planning in Transportation Networks*, arXiv 1504.05140 (20 April 2015), arxiv.org/pdf/1504.05140. Read as extracted text: sections 1 to 3 and the concluding remarks in full; transit and multimodal sections (4 and 5) skimmed. The extraction scrambled the columns of Table 1, so its figures were taken in reading order and checked against Table 2 (CH: 280 vertices scanned, 0.11 ms for a distance, 0.21 ms with the path). The original contraction hierarchies paper (Geisberger et al.) was not read; everything about it comes from the survey.
- Google, *Google Maps 101: How AI helps predict traffic and determine routes*, blog.google (3 September 2020), read in full.
- DeepMind, *Traffic prediction with advanced Graph Neural Networks* (3 September 2020), deepmind.google/discover/blog/traffic-prediction-with-advanced-graph-neural-networks/, read in full.
- Uber Engineering, *DeepETA: How Uber Predicts Arrival Times Using Deep Learning* (10 February 2022), uber.com/en-US/blog/deepeta-how-uber-predicts-arrival-times/, read in full.

## Further reading (not consulted)

The original contraction hierarchies paper and the CRP paper; OSRM's own documentation; Google's published work on Transfer Patterns; map-matching papers; the DeepETA paper itself; any account of how Google Maps stores or serves traffic. None were read, so no claim is made about them.

*Last reviewed: 27 November 2026.*
