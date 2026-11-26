"""Runs the python code blocks from data/new_lessons/ds19-advanced-graphs.md against brute-force checks."""
import re, sys, random, itertools, heapq
src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
ns = {}
for b in blocks:
    exec(b, ns)
dijkstra, bellman_ford, cheapest = ns['dijkstra'], ns['bellman_ford'], ns['cheapest_within_k_edges']
floyd, kruskal, bridges, scc = ns['floyd_warshall'], ns['kruskal'], ns['critical_connections'], ns['strongly_connected_components']
INF = float('inf')
random.seed(7)

def rand_edges(n, m, lo, hi):
    return [(random.randrange(n), random.randrange(n), random.randint(lo, hi)) for _ in range(m)]

# Dijkstra == Bellman-Ford == Floyd on non-negative graphs; Bellman-Ford reports no cycle
for _ in range(300):
    n = random.randint(1, 8); e = rand_edges(n, random.randint(0, 20), 0, 9)
    d = dijkstra(n, e, 0); bf, cyc = bellman_ford(n, e, 0); fw = floyd(n, e)
    assert d == bf and not cyc and d == fw[0], (n, e)

# Negative cycle detection vs brute force (reachable negative cycle via Floyd diagonal)
for _ in range(300):
    n = random.randint(1, 6); e = rand_edges(n, random.randint(0, 12), -4, 6)
    _, cyc = bellman_ford(n, e, 0)
    fw = floyd(n, [(u, v, w) for u, v, w in e])
    reach0 = {0} | {j for j in range(n) if fw[0][j] < INF}
    expect = any(fw[i][i] < 0 for i in reach0)
    assert cyc == expect, (n, e)

# K-edges variant vs brute force DP over walks of at most k edges
for _ in range(300):
    n = random.randint(2, 6); e = rand_edges(n, random.randint(0, 14), 1, 9); k = random.randint(1, 4)
    best = [INF] * n; best[0] = 0
    cur = best[:]
    for _r in range(k):
        nxt = cur[:]
        for u, v, w in e:
            if cur[u] + w < nxt[v]: nxt[v] = cur[u] + w
        cur = nxt
    dst = n - 1
    assert cheapest(n, e, 0, dst, k) == (-1 if cur[dst] == INF else cur[dst]), (n, e, k)
# The classic: 0->1 cost 100, 0->2 cost 500 is wrong with 1 stop limit
assert cheapest(3, [(0, 1, 100), (1, 2, 100), (0, 2, 500)], 0, 2, 1) == 500
assert cheapest(3, [(0, 1, 100), (1, 2, 100), (0, 2, 500)], 0, 2, 2) == 200

# Kruskal vs brute-force minimum spanning tree (try all (n-1)-subsets)
for _ in range(200):
    n = random.randint(1, 5); e = [(u, v, w) for u, v, w in rand_edges(n, random.randint(0, 9), 1, 9) if u != v]
    def connected_tree(sub):
        p = list(range(n))
        def f(x):
            while p[x] != x: x = p[x]
            return x
        for u, v, w in sub:
            a, b = f(u), f(v)
            if a == b: return False
            p[a] = b
        return True
    best = None
    for sub in itertools.combinations(e, n - 1):
        if connected_tree(sub):
            t = sum(w for _, _, w in sub)
            best = t if best is None else min(best, t)
    got, used = kruskal(n, e)
    assert got == best, (n, e, got, best)
assert kruskal(4, [(0, 1, 4), (1, 2, 2), (0, 2, 5), (2, 3, 1)])[0] == 7

# Bridges vs brute force edge removal (multigraph, no self loops)
def components(n, edges):
    p = list(range(n))
    def f(x):
        while p[x] != x: x = p[x]
        return x
    for u, v in edges: p[f(u)] = f(v)
    return len({f(i) for i in range(n)})
for _ in range(300):
    n = random.randint(2, 7)
    e = [(u, v) for u, v, _w in rand_edges(n, random.randint(0, 10), 0, 0) if u != v]
    expect = sorted(sorted(x) for i, x in enumerate(e) if components(n, e[:i] + e[i + 1:]) > components(n, e))
    got = sorted(sorted(x) for x in bridges(n, [list(x) for x in e]))
    assert got == expect, (n, e, got, expect)

# SCC vs reachability closure
for _ in range(300):
    n = random.randint(1, 7); e = [(u, v) for u, v, _w in rand_edges(n, random.randint(0, 14), 0, 0)]
    fw = floyd(n, [(u, v, 1) for u, v in e])
    reach = lambda a, b: a == b or fw[a][b] < INF
    expect = sorted(sorted(c) for c in {frozenset(j for j in range(n) if reach(i, j) and reach(j, i)) for i in range(n)})
    got = sorted(sorted(c) for c in scc(n, e))
    assert got == expect, (n, e, got, expect)
print("ds19 code checks passed")
