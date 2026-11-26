"""Runs the python blocks of the sy56 top-k lesson against exact counting: count-min error bounds, merge linearity,
the Space-Saving invariants from the paper, deterministic window bounds, shard-merge counterexamples and trend ordering."""
import re, sys, random, math, collections, itertools

src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
assert len(blocks) >= 4, 'expected the lesson code blocks'
ns = {}
for b in blocks:
    exec(b, ns)
exact_topk, CountMin, CMSTopK, SpaceSaving = ns['exact_topk'], ns['CountMin'], ns['CMSTopK'], ns['SpaceSaving']
WindowTopK, shard_of, merge_local_topk, trend_score = ns['WindowTopK'], ns['shard_of'], ns['merge_local_topk'], ns['trend_score']

def zipf_stream(n, universe, s, seed):
    r = random.Random(seed)
    weights = [1 / (i + 1) ** s for i in range(universe)]
    return ['v%d' % i for i in r.choices(range(universe), weights=weights, k=n)]

def brute_topk(stream, k):
    c = collections.Counter(stream)
    return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:k]

# ---- 1. exact reference -------------------------------------------------------------------------------------------
rr = random.Random(56)
for _ in range(300):
    st = [rr.choice([0, 1, 2, 3, 4, 10, 11, 100]) for _ in range(rr.randint(0, 60))]    # keys of different lengths
    k = rr.randint(1, 6)
    assert exact_topk(st, k) == brute_topk(st, k), (st, k)
assert exact_topk([], 3) == []
wide = CountMin(0.001, 0.001, seed=2)
wide.add('x', 7); wide.add('y', 3); wide.add('x', 2)
assert wide.estimate('x') == 9 and wide.estimate('y') == 3 and wide.estimate('z') == 0      # weights count

# ---- 2. count-min -------------------------------------------------------------------------------------------------
cm = CountMin(0.01, 0.01)
assert cm.width == math.ceil(math.e / 0.01) == 272 and cm.depth == math.ceil(math.log(100)) == 5
assert CountMin(1e-4, 0.01).width == 27183
over_eps, tested = 0, 0
for seed in range(12):
    st = zipf_stream(6000, 800, 1.1, seed)
    cm = CountMin(0.01, 0.01, seed=seed)
    for x in st: cm.add(x)
    true = collections.Counter(st)
    n = len(st)
    for item in list(true) + ['never-seen-%d' % i for i in range(50)]:
        est = cm.estimate(item)
        assert est >= true.get(item, 0), (seed, item)               # never underestimates
        tested += 1
        if est > true.get(item, 0) + 0.01 * n: over_eps += 1
assert over_eps / tested <= 0.01, (over_eps, tested)                 # the delta bound, observed
# a narrow sketch really does overestimate: the error is real, not a rounding detail
narrow = CountMin(0.2, 0.2, seed=1)
for i in range(500): narrow.add('i%d' % i)
assert max(narrow.estimate('i%d' % i) for i in range(500)) > 1
# weighted updates and merge: adding the cell arrays equals sketching the union
a, b, both = CountMin(0.05, 0.05, seed=3), CountMin(0.05, 0.05, seed=3), CountMin(0.05, 0.05, seed=3)
for i in range(300):
    x, c = 'k%d' % rr.randint(0, 40), rr.randint(1, 5)
    (a if i % 2 else b).add(x, c); both.add(x, c)
m = a.merge(b)
assert m.table == both.table and all(m.estimate('k%d' % i) == both.estimate('k%d' % i) for i in range(41))
assert a.table != both.table
try:
    a.merge(CountMin(0.05, 0.05, seed=4)); assert False, 'different hash seeds must not merge'
except ValueError:
    pass

# ---- 3. count-min plus a small candidate set ---------------------------------------------------------------------
hits = total = 0
for seed in range(10):
    st = zipf_stream(20000, 3000, 1.2, seed)
    t = CMSTopK(10, 0.002, 0.01, seed=seed)
    for x in st: t.add(x)
    true = collections.Counter(st)
    got = t.top()
    assert len(got) <= 10 and got == sorted(got, key=lambda kv: (-kv[1], kv[0]))
    assert all(est >= true[item] for item, est in got)                # estimates never below the truth
    want = {item for item, _ in brute_topk(st, 10)}
    hits += len(want & {item for item, _ in got}); total += 10
assert hits / total >= 0.9, hits / total

# ---- 4. Space-Saving: the paper's invariants ----------------------------------------------------------------------
def run_ss(stream, m):
    ss = SpaceSaving(m)
    for x in stream: ss.add(x)
    return ss
assert run_ss('XZYY', 2).min_count() == 1 and run_ss('XYYZ', 2).min_count() == 2     # the paper's own m=2 example
for seed in range(500):
    r = random.Random(seed)
    universe, m = r.randint(2, 14), r.randint(1, 8)
    st = [r.choice(range(universe)) if r.random() < 0.5 else r.randint(0, 2) for _ in range(r.randint(0, 120))]
    ss = run_ss(st, m)
    true, n = collections.Counter(st), len(st)
    assert ss.n == n and len(ss.count) <= m
    assert sum(ss.count.values()) == n, seed                       # counters always add up to the stream length
    for e in ss.count:
        assert ss.count[e] - ss.err[e] <= true[e] <= ss.count[e], (seed, e)
    if len(ss.count) == m and n:
        assert ss.min_count() <= n // m, seed                       # Lemma 1: min <= floor(N/m)
        assert all(e in ss.count for e, f in true.items() if f > ss.min_count()), seed    # Theorem 1
    elif n:
        assert all(ss.count[e] == true[e] and ss.err[e] == 0 for e in ss.count)           # not full: exact
    top = ss.top(m)
    assert [c for _, c in top] == sorted((c for _, c in top), reverse=True)
    for k in range(1, m + 1):
        g = ss.guaranteed(k)
        if g:                                                       # reported items are genuinely the top
            chosen = {e for e, _ in ss.top(g)}
            worst_in = min(true[e] for e in chosen)
            best_out = max((f for e, f in true.items() if e not in chosen), default=0)
            assert worst_in >= best_out, (seed, k, g, ss.top(m), dict(true))
# on a skewed stream a small counter set recovers the true top 5 in order
st = zipf_stream(30000, 5000, 1.3, 7)
ss = run_ss(st, 50)
assert [e for e, _ in ss.top(5)] == [e for e, _ in brute_topk(st, 5)]

# ---- 5. windows ---------------------------------------------------------------------------------------------------
for seed in range(300):
    r = random.Random(seed)
    nb, m = r.randint(1, 5), r.randint(1, 6)
    w = WindowTopK(nb, m)
    history = [[]]
    for _ in range(r.randint(1, 80)):
        if r.random() < 0.15:
            w.tick(); history.append([])
        else:
            x = r.choice(['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j'][: r.randint(2, 10)])
            w.add(x); history[-1].append(x)
    window = [x for b in history[-nb:] for x in b]
    true, n = collections.Counter(window), len(window)
    for item in 'abcdefghijz':
        lo, hi = w.bounds(item)
        assert lo <= true.get(item, 0) <= hi, (seed, item, lo, true.get(item, 0), hi)       # deterministic bounds
    cands = w.candidates()
    assert all(item in cands for item, f in true.items() if f > n / m), seed               # heavy in the window => candidate
    top = w.top(3)
    assert all(lo <= true.get(item, 0) <= hi for item, lo, hi in top)
    assert top == sorted(((e, *w.bounds(e)) for e in cands), key=lambda r: (-r[2], r[0]))[:3], seed     # rank by upper bound
# when every bucket has room, the window answer is exact
w = WindowTopK(3, 10)
for x in 'aabbbc': w.add(x)
w.tick()
for x in 'bcc': w.add(x)
assert w.top(3) == [('b', 4, 4), ('c', 3, 3), ('a', 2, 2)]
w.tick(); w.tick(); w.tick()
assert w.top(3) == []                                              # everything slid out of a 3-bucket window

# ---- 6. shards ----------------------------------------------------------------------------------------------------
# splitting by arrival loses a global winner: 'a' is second everywhere and first overall
shards = [collections.Counter({'x': 4, 'a': 3}), collections.Counter({'y': 4, 'a': 3}), collections.Counter({'z': 4, 'a': 3})]
total = sum(shards, collections.Counter())
assert total.most_common(1) == [('a', 9)]
assert [i for i, _ in merge_local_topk(shards, 1)] != ['a']
assert [i for i, _ in merge_local_topk(shards, 2)][0] == 'a'      # asking each shard for more (k') recovers it here
# splitting by item hash: every item lives on one shard, so merging local top-k lists is exact
for seed in range(150):
    r = random.Random(seed)
    st = [r.randint(0, 25) for _ in range(r.randint(1, 200))]
    n_shards, k = r.randint(1, 5), r.randint(1, 6)
    parts = [collections.Counter() for _ in range(n_shards)]
    for x in st: parts[shard_of(x, n_shards)][x] += 1
    got = merge_local_topk(parts, k)
    assert got == brute_topk(st, k), (seed, got, brute_topk(st, k))
assert all(0 <= shard_of(x, 7) < 7 and shard_of(x, 7) == shard_of(x, 7) for x in ['a', 'b', 'video:42'])

# ---- 7. trend score -----------------------------------------------------------------------------------------------
near = lambda x, y: abs(x - y) < 1e-3
steady = trend_score(1000, [1000, 1000, 1000])
spike = trend_score(200, [10, 12, 8])
growth = trend_score(1500, [1000, 1000, 1000])
assert steady == 1.0 and near(spike, 205 / 15) and near(growth, 1505 / 1005)        # the values the lesson prints
assert near(trend_score(3, [0, 0, 0], min_volume=0), 8 / 5)                         # smoothing alone: 0 -> 3 scores 1.6
assert trend_score(3, [0, 0, 0], min_volume=0) > growth                             # ... above 1,000 -> 1,500 (the lesson says so)
assert trend_score(3, [0, 0, 0]) == 0.0 < growth                                    # the minimum-volume rule removes it
assert trend_score(19, [0]) == 0.0 and near(trend_score(20, [0]), 25 / 5)           # exactly at the threshold counts
assert spike > growth > steady
assert trend_score(50, [1000, 1000]) < 1                                           # falling
assert trend_score(0, []) == 0.0 and near(trend_score(30, []), 7.0)                # new key with real volume
assert trend_score(100, [10], smoothing=0.0) == 10.0 and near(trend_score(100, [10], smoothing=10.0), 110 / 20)   # smoothing is a parameter

# window ranking rule: by upper bound, key as tiebreak (a key whose lower bound is high but upper low cannot outrank)
w = WindowTopK(1, 2)
for x in 'aaaabbbbbcd': w.add(x)         # a:4 b:5 then c and d evict: bounds differ from counts
rows = w.top(2)
assert rows == sorted(((e, *w.bounds(e)) for e in w.candidates()), key=lambda r: (-r[2], r[0]))[:2], rows
assert [r[2] for r in rows] == sorted((r[2] for r in rows), reverse=True)
w = WindowTopK(1, 2)
for x in ['p'] * 3 + ['q'] * 3 + ['r']: w.add(x)     # r evicts the smaller of p/q and inherits its count
lo_hi = {e: (lo, hi) for e, lo, hi in w.top(2)}
best_by_hi = max(lo_hi, key=lambda e: (lo_hi[e][1], e))
assert w.top(2)[0][0] == best_by_hi and any(lo < hi for lo, hi in lo_hi.values())
print('sy56 code checks passed')
