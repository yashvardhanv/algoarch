# Lesson 19 — Advanced Graphs: Shortest Paths, MST & Tarjan's SCC

> **Priority:** ★★★★★ (Critical for Google L5, Meta E5, Uber algorithmic bar)  
> **Estimated Study Time:** 60 minutes  
> **Key Skills:** Bellman-Ford, Floyd-Warshall, Kruskal's & Prim's MST, Tarjan's Strongly Connected Components, Bridges & Articulation Points.

---

## 1. Mental Model & Constraint Recognition

Standard BFS finds shortest paths on **unweighted** graphs in `O(V + E)`. Dijkstra solves shortest paths on **non-negative weighted** graphs in `O((V + E) log V)`. But FAANG senior interviewers test edge-cases:

1. **Negative Edge Weights:** Dijkstra will produce wrong answers or enter infinite loops. You must recognize **Bellman-Ford** (`O(V * E)`).
2. **Detecting Negative Weight Cycles (Currency Arbitrage):** If the `V`-th relaxation pass still decreases distance, a negative cycle exists.
3. **All-Pairs Shortest Path (APSP):** When `V <= 400`, triple-nested loop **Floyd-Warshall** (`O(V^3)`) takes 5 lines of code and eliminates complex priority queue overhead.
4. **Network Cable / Minimum Spanning Tree:** Kruskal's algorithm (Sort edges by weight + Union-Find) in `O(E log E)`.
5. **Critical Connections / Single Points of Failure:** Tarjan's Bridge finding algorithm using DFS discovery times `tin[u]` and lowest reachable ancestor `low[u]`.

---

## 2. The 45-Second Recognition Reflex

| If you hear this phrase in the prompt... | Reach for this immediately | Complexity |
|---|---|---|
| "Negative edge weights or detecting infinite deduction/arbitrage" | **Bellman-Ford** (relax all edges `V-1` times) | `O(V * E)` |
| "Shortest path between every pair of nodes, V <= 300" | **Floyd-Warshall** (intermediate node `k` outer loop) | `O(V^3)` space `O(V^2)` |
| "Connect all computers/cities with minimum total wire/cost" | **Kruskal's Algorithm** with DSU | `O(E log E)` |
| "Removing which server or cable disconnects the cluster?" | **Tarjan's Bridge Detection** (`low[v] > tin[u]`) | `O(V + E)` |
| "Strongly connected groups in directed graph" | **Tarjan's SCC** or **Kosaraju's 2-Pass DFS** | `O(V + E)` |

---

## 3. Production Python Implementation: Tarjan's Critical Bridges

```python
def criticalConnections(n: int, connections: list[list[int]]) -> list[list[int]]:
    """
    Finds all critical edges (bridges) in an undirected graph in O(V + E).
    An edge (u, v) is a bridge if low[v] > tin[u], meaning subtree at v has
    no back-edge to u or any ancestor of u.
    """
    adj = [[] for _ in range(n)]
    for u, v in connections:
        adj[u].append(v)
        adj[v].append(u)

    tin = [-1] * n
    low = [-1] * n
    bridges = []
    timer = 0

    def dfs(u: int, parent: int = -1):
        nonlocal timer
        tin[u] = low[u] = timer
        timer += 1

        for v in adj[u]:
            if v == parent:
                continue
            if tin[v] != -1:
                # Back-edge to an already visited ancestor
                low[u] = min(low[u], tin[v])
            else:
                # Forward tree-edge
                dfs(v, u)
                low[u] = min(low[u], low[v])
                # Bridge condition: no back-edge from v to u or higher
                if low[v] > tin[u]:
                    bridges.append([u, v])

    for i in range(n):
        if tin[i] == -1:
            dfs(i)

    return bridges
```

---

## 4. The #1 FAANG Interview Trap

> ⚠️ **The Floyd-Warshall Loop Order Trap:**  
> The intermediate node `k` **MUST be the outermost loop**. If you put `k` inside, you are calculating paths through intermediate nodes before all subpaths using `k` have been computed.  
> Correct order:
> ```python
> for k in range(n):
>     for i in range(n):
>         for j in range(n):
>             dist[i][j] = min(dist[i][j], dist[i][k] + dist[k][j])
> ```

---

## 5. Staff L5 Interview Rubric

- **Rejected (L3/L4 Weak):** Tries to run Dijkstra on negative weights by "adding a constant to all edges" (a fatal mathematical flaw, because paths with more edges get penalized more).
- **Hire (L4/L5):** Immediately identifies that adding a constant breaks shortest paths, reaches for Bellman-Ford, correctly derives why `V - 1` passes suffice (simple shortest path has at most `V - 1` edges).
- **Strong Hire (L5+):** Proactively writes Tarjan's low-link algorithm in clean recursion, defines the difference between a tree edge and back edge, explains why cross edges don't exist in undirected graphs, and proves `O(V + E)` time.
