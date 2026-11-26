"""Runs the python code blocks from data/new_lessons/ds25.md against brute-force checks."""
import re, sys, random, itertools
src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
ns = {}
for b in blocks:
    exec(b, ns)
find_order, topo_dfs, smallest_order, min_semesters, unique_order, alien_order = (
    ns['find_order'], ns['topo_dfs'], ns['smallest_order'], ns['minimum_semesters'],
    ns['has_unique_order'], ns['alien_order'])
random.seed(25)

def valid(order, n, edges):
    pos = {v: i for i, v in enumerate(order)}
    return sorted(order) == list(range(n)) and all(pos[u] < pos[v] for u, v in edges)

def all_valid(n, edges):
    return [p for p in itertools.permutations(range(n)) if valid(p, n, edges)]

def longest_chain(n, edges):
    adj = [[] for _ in range(n)]
    for u, v in edges: adj[u].append(v)
    memo = {}
    def go(u):
        if u not in memo: memo[u] = 1 + max((go(v) for v in adj[u]), default=0)
        return memo[u]
    return max(go(u) for u in range(n))

for _ in range(1500):
    n = random.randint(1, 6)
    edges = [(random.randrange(n), random.randrange(n)) for _ in range(random.randint(0, 9))]   # includes self loops, repeats
    if random.random() < 0.7:                      # bias towards acyclic inputs by keeping only forward edges
        edges = [(u, v) for u, v in edges if u < v]
    orders = all_valid(n, edges)
    got = find_order(n, [[v, u] for u, v in edges])          # LeetCode form: [course, prerequisite]
    got2 = topo_dfs(n, edges)
    if not orders:
        assert got == [] and got2 == [], (n, edges, got, got2)
        assert smallest_order(n, edges) == [] and min_semesters(n, edges) == -1 and unique_order(n, edges) is False
    else:
        assert valid(got, n, edges), (n, edges, got)
        assert valid(got2, n, edges), (n, edges, got2)
        assert smallest_order(n, edges) == list(min(orders)), (n, edges)
        assert min_semesters(n, edges) == longest_chain(n, edges), (n, edges)
        assert unique_order(n, edges) is (len(orders) == 1), (n, edges)
assert find_order(4, [[1, 0], [2, 0], [3, 1], [3, 2]]) in ([0, 1, 2, 3], [0, 2, 1, 3])
assert find_order(2, [[1, 0], [0, 1]]) == []

# Long chain: iterative code must not hit the recursion limit
n = 30000
chain = [(i, i + 1) for i in range(n - 1)]
assert find_order(n, [[v, u] for u, v in chain]) == list(range(n))
assert topo_dfs(n, chain) == list(range(n))
assert min_semesters(n, chain) == n
assert topo_dfs(n, chain + [(n - 1, 0)]) == []

# Alien dictionary vs trying every alphabet order
def sorted_under(words, order):
    key = {c: i for i, c in enumerate(order)}
    ks = [[key[c] for c in w] for w in words]
    return all(ks[i] <= ks[i + 1] for i in range(len(ks) - 1))
def brute_alien(words):
    letters = sorted({c for w in words for c in w})
    for p in itertools.permutations(letters):
        if sorted_under(words, p): return True
    return False
for _ in range(1500):
    alpha = 'abcd'[:random.randint(1, 4)]
    if random.random() < 0.5:                       # a dictionary that is sorted under a random alphabet
        order = random.sample(alpha, len(alpha))
        key = {c: i for i, c in enumerate(order)}
        words = sorted((''.join(random.choice(alpha) for _ in range(random.randint(1, 3))) for _ in range(random.randint(1, 5))),
                       key=lambda w: [key[c] for c in w])
    else:
        words = [''.join(random.choice(alpha) for _ in range(random.randint(1, 3))) for _ in range(random.randint(1, 5))]
    got = alien_order(words)
    if brute_alien(words):
        letters = {c for w in words for c in w}
        assert got != "" and sorted(got) == sorted(letters) and sorted_under(words, got), (words, got)
    else:
        assert got == "", (words, got)
assert alien_order(["wrt", "wrf", "er", "ett", "rftt"]) != "" and alien_order(["abc", "ab"]) == "" and alien_order(["z", "x", "z"]) == ""
print("ds25 code checks passed")
