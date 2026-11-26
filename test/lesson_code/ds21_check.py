"""Runs the python code blocks from data/new_lessons/ds21-bitmask-dp.md against brute-force checks."""
import re, sys, random, itertools
src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
ns = {}
for b in blocks:
    exec(b, ns)
held_karp, assign_min, shortest_all, can_partition_k, submasks, min_partition_cost = (
    ns['held_karp'], ns['min_cost_assignment'], ns['shortest_path_visiting_all'],
    ns['can_partition_k_subsets'], ns['submasks'], ns['min_partition_cost'])
INF = float('inf')
random.seed(21)

# Held-Karp vs all permutations (complete graph, asymmetric costs)
for _ in range(150):
    n = random.randint(1, 7)
    d = [[random.randint(1, 20) for _ in range(n)] for _ in range(n)]
    if n == 1:
        exp = 0
    else:
        exp = min(d[0][p[0]] + sum(d[p[i]][p[i + 1]] for i in range(len(p) - 1)) + d[p[-1]][0]
                  for p in itertools.permutations(range(1, n)))
    assert held_karp(d) == exp, (d, held_karp(d), exp)

# Assignment vs all permutations (rectangular not needed: n people, n tasks)
for _ in range(200):
    n = random.randint(1, 7)
    c = [[random.randint(0, 30) for _ in range(n)] for _ in range(n)]
    exp = min(sum(c[i][p[i]] for i in range(n)) for p in itertools.permutations(range(n)))
    assert assign_min(c) == exp, (c,)

# Shortest path visiting all nodes (connected unweighted graph) vs Floyd + permutations
for _ in range(200):
    n = random.randint(1, 6)
    adj = [set() for _ in range(n)]
    for v in range(1, n):                    # random spanning tree keeps it connected
        u = random.randrange(v); adj[u].add(v); adj[v].add(u)
    for _e in range(random.randint(0, 4)):
        u, v = random.randrange(n), random.randrange(n)
        if u != v: adj[u].add(v); adj[v].add(u)
    graph = [sorted(s) for s in adj]
    dist = [[0 if i == j else (1 if j in adj[i] else INF) for j in range(n)] for i in range(n)]
    for k in range(n):
        for i in range(n):
            for j in range(n):
                dist[i][j] = min(dist[i][j], dist[i][k] + dist[k][j])
    exp = min(sum(dist[p[i]][p[i + 1]] for i in range(n - 1)) for p in itertools.permutations(range(n)))
    assert shortest_all(graph) == exp, (graph, shortest_all(graph), exp)
assert shortest_all([[1, 2, 3], [0], [0], [0]]) == 4

# k equal-sum subsets vs recursive bucket assignment
def brute_k(nums, k):
    total = sum(nums)
    if total % k: return False
    t = total // k
    buckets = [0] * k
    def go(i):
        if i == len(nums): return all(b == t for b in buckets)
        for j in range(k):
            if buckets[j] + nums[i] <= t:
                buckets[j] += nums[i]
                if go(i + 1): return True
                buckets[j] -= nums[i]
        return False
    return go(0)
for _ in range(400):
    n = random.randint(1, 8); k = random.randint(1, 4)
    nums = [random.randint(1, 6) for _ in range(n)]
    assert can_partition_k(list(nums), k) == brute_k(nums, k), (nums, k)
assert can_partition_k([4, 3, 2, 3, 5, 2, 1], 4) is True
assert can_partition_k([1, 2, 3, 4], 3) is False
assert can_partition_k([5], 1) is True and can_partition_k([5], 2) is False

# submasks: exactly the non-empty submasks, each once, descending; total over all masks is 3^n - 2^n
for mask in range(0, 64):
    got = list(submasks(mask))
    exp = [s for s in range(mask, 0, -1) if s & mask == s]
    assert got == exp, (mask, got, exp)
n = 8
assert sum(len(list(submasks(m))) for m in range(1 << n)) == 3 ** n - 2 ** n

# min_partition_cost vs enumeration of all set partitions
def partitions(items):
    if not items:
        yield []; return
    first, rest = items[0], items[1:]
    for p in partitions(rest):
        yield [[first]] + p
        for i in range(len(p)):
            yield p[:i] + [[first] + p[i]] + p[i + 1:]
for _ in range(100):
    n = random.randint(1, 6)
    cost = [0] + [random.randint(1, 20) for _ in range((1 << n) - 1)]
    exp = min(sum(cost[sum(1 << x for x in g)] for g in part) for part in partitions(list(range(n))))
    assert min_partition_cost(n, cost) == exp, (n, cost)
print("ds21 code checks passed")
