"""Runs the python blocks of data/new_lessons/sy76-social-graph-pymk.md against brute-force references:
two-hop candidate generation (counts and Adamic/Adar scores), exclusion rules, the hub guard, the work counter,
and the shards-touched formula against a simulation."""
import re, sys, math, random
src = open(sys.argv[1], encoding='utf-8').read()
ns = {}
for b in re.findall(r"```python\n(.*?)```", src, re.S):
    exec(b, ns)
build_graph, candidates, top_k = ns['build_graph'], ns['candidates'], ns['top_k']
expected_shards_touched = ns['expected_shards_touched']

def rand_graph(rnd, n, m):
    return build_graph([(rnd.randrange(n), rnd.randrange(n)) for _ in range(m)])

def brute(g, u, cap=None, blocked=()):
    """Every non-neighbour v: common neighbours counted straight from the definition."""
    counts, aa = {}, {}
    for v in g:
        if v == u or v in g.get(u, set()) or v in blocked:
            continue
        common = [z for z in g[u] & g[v] if cap is None or len(g[z]) <= cap]
        if common:
            counts[v] = len(common)
            aa[v] = sum(1 / math.log(len(g[z])) for z in common)
    return counts, aa

# ---- graph building -----------------------------------------------------------------------------------------------
g = build_graph([(1, 2), (2, 1), (2, 3), (3, 3), (4, 3)])
assert g == {1: {2}, 2: {1, 3}, 3: {2, 4}, 4: {3}}                         # symmetric, no self loops, duplicates merged

# ---- candidates against the definition ---------------------------------------------------------------------------
rnd = random.Random(11)
for trial in range(300):
    n = rnd.randint(3, 40)
    g = rand_graph(rnd, n, rnd.randint(2, 120))
    for u in rnd.sample(sorted(g), min(5, len(g))):
        blocked = set(rnd.sample(sorted(g), min(2, len(g)))) - {u}
        counts, aa, work = candidates(g, u, blocked=blocked)
        rc, raa = brute(g, u, blocked=blocked)
        assert dict(counts) == rc, (u, dict(counts), rc)
        assert set(aa) == set(raa) and all(abs(aa[v] - raa[v]) < 1e-9 for v in aa), (u,)
        assert work == sum(len(g[z]) for z in g[u])                          # the work counter is the sum of friends' degrees
        assert u not in counts and not (set(counts) & g[u]) and not (set(counts) & blocked)

# ---- the hub guard equals the definition restricted to non-hub intermediates -------------------------------------------
for trial in range(200):
    g = rand_graph(rnd, rnd.randint(5, 40), rnd.randint(10, 150))
    cap = rnd.choice((2, 3, 5, 8))
    u = rnd.choice(sorted(g))
    counts, aa, work = candidates(g, u, max_fanout=cap)
    rc, raa = brute(g, u, cap=cap)
    assert dict(counts) == rc and all(abs(aa[v] - raa[v]) < 1e-9 for v in aa), (u, cap)
    assert work == sum(len(g[z]) for z in g[u] if len(g[z]) <= cap)

# ---- ranking: the score, then the id, so ties are deterministic ---------------------------------------------------
g = build_graph([(0, 1), (0, 2), (1, 5), (2, 5), (1, 6), (2, 6), (1, 7), (3, 7), (3, 1)])
assert top_k(g, 0, 3, 'common') == [(5, 2), (6, 2), (3, 1)]                 # two ties, broken by id, then the 3 before the 7
for trial in range(100):
    g = rand_graph(rnd, rnd.randint(5, 30), rnd.randint(5, 80))
    u = rnd.choice(sorted(g))
    for metric in ('common', 'adamic_adar'):
        got = top_k(g, u, 50, metric)
        assert got == sorted(got, key=lambda p: (-p[1], p[0]))
# Adamic/Adar prefers a rare shared friend over a popular one, where plain counting ties
g2 = build_graph([(0, 'rare'), (0, 'pop'), ('rare', 'x'), ('pop', 'y')] + [('pop', f'p{i}') for i in range(20)])
aa2 = dict(top_k(g2, 0, 30, 'adamic_adar'))
assert aa2['x'] > aa2['y']                                                  # a rare friend is stronger evidence than a popular one
assert dict(top_k(g2, 0, 30, 'common'))['x'] == dict(top_k(g2, 0, 30, 'common'))['y'] == 1
assert abs(aa2['x'] - 1 / math.log(2)) < 1e-12 and abs(aa2['y'] - 1 / math.log(22)) < 1e-12
assert top_k(build_graph([(1, 2)]), 99, 5, 'common') == []                  # unknown user: nothing, no crash
assert top_k(build_graph([(0, 1), (1, 2)]), 0, 0, 'common') == []

# ---- how many shards a two-hop query must visit --------------------------------------------------------------------
for shards, friends in ((100, 200), (100, 1000), (16, 50), (1000, 300)):
    r2 = random.Random(shards * 7 + friends)
    trials = 3000
    mean = sum(len({r2.randrange(shards) for _ in range(friends)}) for _ in range(trials)) / trials
    want = expected_shards_touched(shards, friends)
    assert abs(mean - want) / want < 0.01, (shards, friends, mean, want)
assert round(expected_shards_touched(100, 200), 1) == 86.6
assert abs(expected_shards_touched(100, 1) - 1.0) < 1e-9 and abs(expected_shards_touched(1, 50) - 1.0) < 1e-9

# ---- hub guard on a graph with one very large account: work, and what it costs in recommendations ----------------------
rnd = random.Random(5)
N, M = 4000, 24000
edges = [(rnd.randrange(N), rnd.randrange(N)) for _ in range(M)] + [(0, v) for v in range(1, N)]     # account 0 follows everyone
g = build_graph(edges)
users = [u for u in rnd.sample(range(1, N), 400)]
plain = guarded = 0
overlaps = []
for u in users:
    _, _, w1 = candidates(g, u)
    c2, a2, w2 = candidates(g, u, max_fanout=100)
    plain += w1; guarded += w2
    t1 = [v for v, _ in top_k(g, u, 10, 'common')]
    t2 = [v for v, _ in sorted(((v, s) for v, s in c2.items()), key=lambda p: (-p[1], p[0]))[:10]]
    overlaps.append(len(set(t1) & set(t2)) / max(1, len(t1)))
assert plain > 20 * guarded, (plain, guarded)                                # the hub dominated the work: about 25 times fewer visits
assert sum(overlaps) / len(overlaps) > 0.98                                  # and, by construction, no ranking changed: a friend of everyone adds the same +1 to every candidate
print("hub work", plain, "->", guarded, "top-10 overlap", round(sum(overlaps) / len(overlaps), 3))
# the side effect of a friend-of-everyone account: for a sparse user the plain top 10 is padded with arbitrary non-friends
gs = build_graph([(0, v) for v in range(1, 60)] + [(1, 2), (2, 3), (1, 3), (4, 5)])
c_full, _, _ = candidates(gs, 1)
c_guard, _, _ = candidates(gs, 1, max_fanout=10)
t_full = [v for v, _ in top_k(gs, 1, 10, 'common')]
t_guard = [v for v, _ in sorted(c_guard.items(), key=lambda p: (-p[1], p[0]))[:10]]
assert len(t_full) == 10 and len(t_guard) < 10 and t_full != t_guard          # padded by the hub, not by real evidence
assert all(c_full[v] == 1 for v in t_full[len(t_guard):])                     # the padding has count 1, from the hub alone
print("sy76 code checks passed")
