# Lesson 19 — Advanced Graphs: Shortest Paths, Spanning Trees and Connectivity

> **Priority:** ★★★★★ — the graph questions that separate a strong round from an average one.
>
> **Study time:** 60 minutes. **Do this after:** Lesson 11 (BFS, DFS and graph modelling) and Lesson 12 (Union-Find).
> **Level:** advanced. Optional for a crash plan; worth doing if your target loops include hard graph rounds.

BFS and DFS answer "can I get there" and "how many steps". This lesson answers the questions real
systems ask: **what is the cheapest route, what is the cheapest way to connect everything, and
which single failure splits the network.** Each has one standard algorithm, one trap, and a
two-sentence tell in the prompt that tells you which to reach for.

---

## 1. Mental Model

> **Every algorithm in this lesson is one idea: keep an estimate for each node, and improve it
> whenever you find something better. The algorithms differ only in the order they look.**

- **Dijkstra** looks at the cheapest unfinished node first. That is only safe when no edge can
  *reduce* a total, so it needs non-negative weights.
- **Bellman-Ford** does not trust any order. It improves every edge, over and over, and stops
  when nothing improves. Slower, but it survives negative weights and *notices* negative cycles.
- **Floyd-Warshall** improves all pairs at once by asking, for each node `k`, "is it cheaper to go
  via `k`?"
- **Kruskal** builds a spanning tree by taking the cheapest edge that doesn't close a cycle.
- **Tarjan** uses DFS discovery times to spot edges and groups whose removal disconnects things.

---

## 2. The Recognition Reflex

| If the prompt says... | Reach for | Time |
|---|---|---|
| "cheapest/fastest route", all weights ≥ 0 | **Dijkstra** with a heap | `O((V + E) log V)` |
| "negative costs", "arbitrage", "detect a cycle that keeps reducing" | **Bellman-Ford** | `O(V · E)` |
| "at most K stops/edges" | **Bellman-Ford limited to K+1 rounds** | `O(K · E)` |
| "between every pair", `V` up to a few hundred | **Floyd-Warshall** | `O(V³)` |
| "connect everything at minimum total cost" | **Kruskal + Union-Find** (or Prim) | `O(E log E)` |
| "which link/server, if removed, disconnects the network" | **Tarjan bridges** | `O(V + E)` |
| "groups where everyone reaches everyone" (directed) | **Tarjan or Kosaraju SCC** | `O(V + E)` |

> **If all weights are equal (or 0/1), use BFS (or 0-1 BFS).** Reaching for Dijkstra there is
> correct but slower, and interviewers notice.

---

## 3. Dijkstra, the One You Must Write From Memory

```python
import heapq

def dijkstra(n, edges, src):
    """Shortest distance from src to every node. edges: (u, v, w) with w >= 0, directed.
    Unreachable nodes get float('inf')."""
    adj = [[] for _ in range(n)]
    for u, v, w in edges:
        adj[u].append((v, w))
    dist = [float('inf')] * n
    dist[src] = 0
    heap = [(0, src)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u]:          # a stale entry: u was already finalised with a smaller distance
            continue
        for v, w in adj[u]:
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                heapq.heappush(heap, (nd, v))
    return dist
```

**Why the stale-entry check matters.** A node can be pushed several times with different
distances. The first time it is popped is its best; later pops are stale and must be skipped, or
you do wasted work and, on dense graphs, blow the time limit.

**Why it fails on negative edges.** Dijkstra finalises a node the moment it pops. A later negative
edge could still have made it cheaper, but it will never be looked at again.

> **The trap: "add a constant to every edge to make them positive."** This changes the answer. A
> path with more edges gets penalised more, so the cheapest path can switch. It is wrong, not
> merely slow.

---

## 4. Bellman-Ford, and the K-Stops Variant

```python
def bellman_ford(n, edges, src):
    """Returns (dist, has_negative_cycle). dist[v] is inf if unreachable."""
    dist = [float('inf')] * n
    dist[src] = 0
    for _ in range(n - 1):
        changed = False
        for u, v, w in edges:
            if dist[u] != float('inf') and dist[u] + w < dist[v]:
                dist[v] = dist[u] + w
                changed = True
        if not changed:
            break
    # One more pass: any improvement means a negative cycle reachable from src.
    has_cycle = any(dist[u] != float('inf') and dist[u] + w < dist[v] for u, v, w in edges)
    return dist, has_cycle


def cheapest_within_k_edges(n, edges, src, dst, k):
    """Cheapest cost from src to dst using at most k edges, or -1. (Cheapest Flights Within K Stops
    is this with k = stops + 1.)"""
    dist = [float('inf')] * n
    dist[src] = 0
    for _ in range(k):
        nxt = dist[:]                      # relax from the previous round only
        for u, v, w in edges:
            if dist[u] != float('inf') and dist[u] + w < nxt[v]:
                nxt[v] = dist[u] + w
        dist = nxt
    return -1 if dist[dst] == float('inf') else dist[dst]
```

**Why `V - 1` rounds.** A shortest path never repeats a node, so it has at most `V - 1` edges.
After round `i`, every shortest path of at most `i` edges is correct. After `V - 1` rounds, all
are. If round `V` still improves something, a negative cycle exists.

**Why the K-stops version copies the array.** If you relax in place, a node improved in this round
can feed another edge in the *same* round, so you silently use more than `k` edges. Relaxing from
a copy of the previous round is the whole trick.

---

## 5. Floyd-Warshall and the Loop-Order Trap

```python
def floyd_warshall(n, edges):
    """All-pairs shortest distances. Returns an n x n matrix; inf where no path."""
    INF = float('inf')
    dist = [[0 if i == j else INF for j in range(n)] for i in range(n)]
    for u, v, w in edges:
        dist[u][v] = min(dist[u][v], w)
    for k in range(n):                      # k MUST be the outermost loop
        for i in range(n):
            for j in range(n):
                if dist[i][k] + dist[k][j] < dist[i][j]:
                    dist[i][j] = dist[i][k] + dist[k][j]
    return dist
```

> **The trap:** `k` must be the outer loop. After iteration `k`, `dist[i][j]` is the best path using
> only nodes `0..k` as stops. Put `k` inside and you are using stops you have not finished
> computing. Use this only when `V` is a few hundred at most; it is `O(V³)`.

---

## 6. Kruskal: Cheapest Way to Connect Everything

```python
def kruskal(n, edges):
    """Minimum spanning tree weight and edges for an undirected graph, or (None, []) if disconnected."""
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]   # path halving
            x = parent[x]
        return x

    total, used = 0, []
    for u, v, w in sorted(edges, key=lambda e: e[2]):
        ru, rv = find(u), find(v)
        if ru != rv:                         # this edge does not close a cycle
            parent[ru] = rv
            total += w
            used.append((u, v, w))
    return (total, used) if len(used) == n - 1 else (None, [])
```

**The invariant:** the cheapest edge that does not form a cycle is always safe to take. Sort
once, check with Union-Find, stop at `n - 1` edges. Dense graph with a vertex-count limit?
Prim with a heap is the usual alternative; the answers are equal.

---

## 7. Tarjan: Bridges and Strongly Connected Components

**Bridges** (an edge whose removal disconnects an undirected graph):

```python
def critical_connections(n, connections):
    """Bridges of an undirected graph. Handles repeated edges between the same pair."""
    adj = [[] for _ in range(n)]
    for i, (u, v) in enumerate(connections):
        adj[u].append((v, i))
        adj[v].append((u, i))
    tin = [-1] * n
    low = [0] * n
    out, timer = [], 0

    def dfs(u, parent_edge):
        nonlocal timer
        tin[u] = low[u] = timer
        timer += 1
        for v, eid in adj[u]:
            if eid == parent_edge:           # skip only the edge we came by, not every edge to the parent
                continue
            if tin[v] != -1:
                low[u] = min(low[u], tin[v])          # back edge
            else:
                dfs(v, eid)
                low[u] = min(low[u], low[v])
                if low[v] > tin[u]:                   # nothing below v reaches u or above
                    out.append([u, v])

    for s in range(n):
        if tin[s] == -1:
            dfs(s, -1)
    return out
```

Skipping the parent by **edge id**, not by node, is what makes parallel edges work: two edges
between the same pair are never a bridge, because either one is a back route for the other.

**Strongly connected components** (directed graph, Tarjan):

```python
def strongly_connected_components(n, edges):
    """Return a list of components (each a list of nodes) of a directed graph."""
    adj = [[] for _ in range(n)]
    for u, v in edges:
        adj[u].append(v)
    index = [-1] * n
    low = [0] * n
    on_stack = [False] * n
    stack, comps, counter = [], [], 0

    def dfs(u):
        nonlocal counter
        index[u] = low[u] = counter
        counter += 1
        stack.append(u)
        on_stack[u] = True
        for v in adj[u]:
            if index[v] == -1:
                dfs(v)
                low[u] = min(low[u], low[v])
            elif on_stack[v]:                         # only edges into the current stack matter
                low[u] = min(low[u], index[v])
        if low[u] == index[u]:                        # u is the root of a component
            comp = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                comp.append(w)
                if w == u:
                    break
            comps.append(comp)

    for s in range(n):
        if index[s] == -1:
            dfs(s)
    return comps
```

> **Python recursion limit.** These recursive versions fail on graphs of around a thousand or more
> nodes in a chain. In an interview, say so and either raise the limit
> (`sys.setrecursionlimit`) or convert to an explicit stack. Saying it unprompted is a
> strong signal.

---

## 8. Pitfalls Checklist

1. **Dijkstra on negative weights**, or "shift all weights up". Both are wrong.
2. **No stale-entry check** in Dijkstra's heap loop.
3. **In-place relaxation** in the K-edges variant of Bellman-Ford.
4. **Floyd-Warshall with `k` not outermost.**
5. **Adding `inf + negative`** in Bellman-Ford without the "reachable" guard, which can produce a
   falsely finite distance.
6. **Kruskal on a disconnected graph** returning a forest as if it were a tree. Check for `n - 1`
   edges.
7. **Bridges skipping the parent by node** instead of by edge id when the graph has parallel edges.
8. **Mixing the SCC rule with the bridge rule.** In SCC, only update `low` from a neighbour that is
   still on the stack; in bridges, update from any visited neighbour except the incoming edge.

---

## 9. Drills

1. State the one change that makes Bellman-Ford detect a negative cycle.
2. Why does adding a constant to every edge weight not fix Dijkstra for negative edges?
3. Why must the K-edges Bellman-Ford relax from a copy of the previous round?
4. In Floyd-Warshall, what does `dist[i][j]` mean after iteration `k`?
5. Run Kruskal by hand on edges `(0,1,4) (1,2,2) (0,2,5) (2,3,1)`. What is the tree weight?
6. Why must bridge detection skip the parent by edge id?
7. When is Prim preferable to Kruskal, and when is BFS preferable to either shortest-path algorithm?
8. What does `low[u] == index[u]` mean in Tarjan's SCC?

---

## 10. Homework

Solve these, in this order, without looking at your notes first. Names are the common problem titles;
the numbers are LeetCode's.

1. **Network Delay Time** (743) — Dijkstra.
2. **Path With Minimum Effort** (1631) — Dijkstra with a different cost function.
3. **Cheapest Flights Within K Stops** (787) — the K-edges Bellman-Ford above.
4. **Find the City With the Smallest Number of Neighbors at a Threshold Distance** (1334) — Floyd-Warshall.
5. **Min Cost to Connect All Points** (1584) — Kruskal or Prim.
6. **Critical Connections in a Network** (1192) — bridges.

Then explain to a friend, aloud, in under a minute: *why* Dijkstra is correct on non-negative
weights and wrong on negative ones. If you cannot, reread §3.

---

## Further reading

Standard references for every algorithm above are CLRS (the shortest-paths, minimum-spanning-tree
and strongly-connected-components chapters) and the CP-Algorithms graph pages. They were not
consulted while writing this revision: the code here was written from the algorithms themselves and
checked against brute-force versions on random small graphs before publishing.

*Last reviewed: 2026-11-26.*
