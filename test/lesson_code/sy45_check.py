"""Runs the python blocks from data/new_lessons/sy45-caching-consistent-hashing.md against reference checks,
and checks that every figure the lesson prints was produced by that code."""
import re, sys, random, bisect, math, itertools
from collections import OrderedDict

src = open(sys.argv[1], encoding='utf-8').read()
ns = {}
for b in re.findall(r"```python\n(.*?)```", src, re.S):
    exec(b, ns)

def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the computed figure: %r' % p

# ---------------------------------------------------------------- cache-aside interleavings
interleavings, stale_runs = ns['interleavings'], ns['stale_runs']
a, b = list('abc'), list('xy')
seqs = [tuple(s) for s in interleavings(a, b)]
assert len(seqs) == math.comb(5, 2) == len(set(seqs)) == 10
for s in seqs:                                           # each merge keeps both orders and uses every step once
    assert [t for t in s if t in a] == a and [t for t in s if t in b] == b
assert [list(s) for s in interleavings([], b)] == [b] and [list(s) for s in interleavings(a, [])] == [a]

start = {'db': 'old', 'cache': None, 'lease': None, 'n': 0}
warm = dict(start, cache='old')
reader, leased = ns['READER'], ns['LEASED_READER']
w_then_d = [('write db', ns['write_db']), ('delete', ns['drop'])]
d_then_w = [('delete', ns['drop']), ('write db', ns['write_db'])]
lw_then_d = [('write db', ns['write_db']), ('delete', ns['drop_lease'])]
ld_then_w = [('delete', ns['drop_lease']), ('write db', ns['write_db'])]
counts = {}
counts['plain write-delete cold'] = len(stale_runs(reader, w_then_d, start))
counts['plain write-delete warm'] = len(stale_runs(reader, w_then_d, warm))
counts['plain delete-write cold'] = len(stale_runs(reader, d_then_w, start))
counts['plain delete-write warm'] = len(stale_runs(reader, d_then_w, warm))
counts['lease write-delete cold'] = len(stale_runs(leased, lw_then_d, start))
counts['lease write-delete warm'] = len(stale_runs(leased, lw_then_d, warm))
counts['lease delete-write cold'] = len(stale_runs(leased, ld_then_w, start))
counts['lease delete-write warm'] = len(stale_runs(leased, ld_then_w, warm))
assert counts == {'plain write-delete cold': 1, 'plain write-delete warm': 0,
                  'plain delete-write cold': 6, 'plain delete-write warm': 2,
                  'lease write-delete cold': 0, 'lease write-delete warm': 0,
                  'lease delete-write cold': 2, 'lease delete-write warm': 2}, counts
assert stale_runs(reader, w_then_d, start) == [['get', 'read db', 'write db', 'delete', 'fill']]
# two writers, update-on-write: the database order and the cache order can disagree
A = [('A db', lambda s: s.__setitem__('db', 'A')), ('A cache', lambda s: s.__setitem__('cache', 'A'))]
B = [('B db', lambda s: s.__setitem__('db', 'B')), ('B cache', lambda s: s.__setitem__('cache', 'B'))]
two = stale_runs(A, B, start)
assert two == [['A db', 'B db', 'B cache', 'A cache'], ['B db', 'A db', 'A cache', 'B cache']], two
assert len(list(interleavings(A, B))) == 6
# the same two writers with delete-on-write never leave a stale value behind
Ad = [('A db', A[0][1]), ('A del', ns['drop'])]
Bd = [('B db', B[0][1]), ('B del', ns['drop'])]
assert stale_runs(Ad, Bd, start) == []

# ---------------------------------------------------------------- hit-rate arithmetic
db_reads = ns['db_reads_per_second']
assert db_reads(100000, 0.99) == 1000 and db_reads(100000, 0.95) == 5000 and db_reads(100000, 0.90) == 10000
assert db_reads(100000, 0.0) == 100000
mean_ms = ns['mean_read_ms']
assert round(mean_ms(0.99, 0.5, 10), 3) == 0.605 and round(mean_ms(0.95, 0.5, 10), 3) == 1.025
assert round(mean_ms(0.90, 0.5, 10), 3) == 1.55 and round(mean_ms(0.0, 0.5, 10), 3) == 11.0

# ---------------------------------------------------------------- placement: ring, rendezvous, jump, bounded loads
Ring, h64, rendezvous, jump_hash = ns['Ring'], ns['h64'], ns['rendezvous'], ns['jump_hash']
nodes = ['node-%d' % i for i in range(10)]
keys = ['key-%d' % i for i in range(3000)]
for v in (1, 7, 50):
    r = Ring(nodes, v)
    assert len(r.points) == len(set(r.points)) == 10 * v and r.points == sorted(r.points)
    for k in keys[:600]:                                  # naive scan: the owner is the smallest point above the hash
        hk = h64(k)
        above = [p for p in r.points if p > hk]
        expect = r.owner[min(above)] if above else r.owner[min(r.points)]
        assert r.lookup(k) == expect, (v, k)
    # adding a node only moves keys TO the new node; removing it moves them back (monotonicity)
    before = {k: r.lookup(k) for k in keys}
    r.add('node-new')
    after = {k: r.lookup(k) for k in keys}
    assert all(after[k] == 'node-new' for k in keys if after[k] != before[k])
    assert any(after[k] == 'node-new' for k in keys)
    r.remove('node-new')
    assert {k: r.lookup(k) for k in keys} == before and len(r.points) == 10 * v
    # removing a node only moves the keys that node owned
    r.remove('node-3')
    gone = {k: r.lookup(k) for k in keys}
    assert all(gone[k] != 'node-3' for k in keys)
    assert len(r.owner) == len(r.points) == 9 * v and set(r.owner.values()) == set(nodes) - {'node-3'}
    assert all(gone[k] == before[k] for k in keys if before[k] != 'node-3')
    # preference lists: distinct physical nodes, first is the owner, equals a brute-force walk
r = Ring(nodes, 5)
for k in keys[:400]:
    pl = r.preference_list(k, 3)
    assert len(pl) == len(set(pl)) == 3 and pl[0] == r.lookup(k)
    hk = h64(k)
    order = sorted(r.points, key=lambda p: (p - hk) % 2**64 if p != hk else 2**64)  # clockwise, strictly above hk first
    walk = []
    for p in order:
        if r.owner[p] not in walk:
            walk.append(r.owner[p])
    assert pl == walk[:3], (k, pl, walk[:3])
assert len(Ring(['a'], 3).preference_list('k', 3)) == 1          # fewer nodes than asked: returns what exists

# rendezvous: the winner among n+1 nodes is either the old winner or the new node
for k in keys[:800]:
    w10, w11 = rendezvous(k, nodes), rendezvous(k, nodes + ['node-10'])
    assert w11 in (w10, 'node-10')
    assert rendezvous(k, list(reversed(nodes))) == w10                 # does not depend on list order

# jump hash: range, determinism, monotonicity, 1/(n+1) movement, and the slow definition's closed form
for k in range(2000):
    prev = jump_hash(k, 1)
    assert prev == 0
    for n in range(2, 40):
        cur = jump_hash(k, n)
        assert 0 <= cur < n
        assert cur == prev or cur == n - 1, (k, n, prev, cur)          # either stays, or jumps to the new bucket
        prev = cur
moves = sum(jump_hash(h64(str(k)), 20) != jump_hash(h64(str(k)), 21) for k in range(40000))
assert abs(moves / 40000 - 1 / 21) < 0.006, moves / 40000
cnt = [0] * 12
for k in range(60000):
    cnt[jump_hash(h64('j%d' % k), 12)] += 1
assert max(cnt) / (60000 / 12) < 1.06 and min(cnt) / (60000 / 12) > 0.94

# bounded loads: capacity respected, every key placed, huge c equals the plain ring
bounded_assign = ns['bounded_assign']
big = ['key-%d' % i for i in range(5000)]
for v in (1, 10):
    ring = Ring(nodes, v)
    for c in (1.0, 1.25, 2.0):
        placed = bounded_assign(ring, big, c)
        cap = math.ceil(c * len(big) / 10)
        loads = [sum(1 for n in placed.values() if n == x) for x in nodes]
        assert len(placed) == len(big) and sum(loads) == len(big) and max(loads) <= cap, (v, c, max(loads), cap)
    plain = {k: ring.lookup(k) for k in big}
    assert bounded_assign(ring, big, 1000.0) == plain
    placed = bounded_assign(ring, big, 1.25)
    assert placed != plain                                           # with v=1 or 10 the plain ring overloads someone
    assert all(placed[k] in nodes for k in big)

# the report harness
compare, failure_spread, balance, moved_share = ns['compare'], ns['failure_spread'], ns['balance'], ns['moved_share']
assert balance([10, 10, 10, 10]) == (1.0, 0.0) and moved_share(['a', 'b', 'c'], ['a', 'x', 'y']) == 2 / 3
rows = compare(['key-%d' % i for i in range(50000)])
by = {name: (mx, sd, mv) for name, mx, sd, mv in rows}
assert abs(by['mod N'][2] - 0.911) < 0.002 and by['mod N'][0] < 1.06      # mod N balances well and moves ~91%
for name, (mx, sd, mv) in by.items():
    if name != 'mod N':
        assert 0.07 < mv < 0.125, (name, mv)                             # everything else moves about 1/11
assert by['ring, 1 vnode'][0] > 2.5 and by['ring, 1000 vnodes'][0] < 1.05
assert by['ring, 1 vnode'][0] > by['ring, 10 vnodes'][0] > by['ring, 100 vnodes'][0] > by['ring, 1000 vnodes'][0]
fs = {v: failure_spread(['key-%d' % i for i in range(50000)], v) for v in (1, 10, 100, 1000)}
assert fs[1] == (1.0, 1) and fs[1000][1] == 9 and fs[1000][0] < fs[100][0] < 0.25
for name, (mx, sd, mv) in by.items():
    need('| %s | %.3f | %.3f | %.1f%% |' % (name, mx, sd, mv * 100))
for v, (worst, receivers) in fs.items():
    need('| %d | %d | %.1f%% |' % (v, receivers, worst * 100))

# bounded-load table
rows_b = ns['bounded_report']()
assert [r[0] for r in rows_b] == [1, 10, 100]
for v, plain_max, bounded_max in rows_b:
    assert bounded_max <= 1.25 + 1e-9                       # the cap: ceil(1.25 * 2000) / 2000
    if plain_max > 1.25:
        assert abs(bounded_max - 1.25) < 1e-9               # an over-full ring is brought exactly to the cap
    else:
        assert bounded_max == plain_max                      # an already-within-cap ring is left alone
    need('| %d | %.3f | %.3f |' % (v, plain_max, bounded_max))

# ---------------------------------------------------------------- Zipf and LRU
zipf_stream, ideal_hit_rate, lru_hit_rate = ns['zipf_stream'], ns['ideal_hit_rate'], ns['lru_hit_rate']
def naive_lru(stream, size):
    order, hits = [], 0
    for k in stream:
        if k in order:
            hits += 1
            order.remove(k)
        order.append(k)
        if len(order) > size:
            order.pop(0)
    return hits / len(stream)
rng = random.Random(3)
for _ in range(60):
    st = [rng.randrange(12) for _ in range(rng.randrange(0, 80))]
    size = rng.randrange(1, 8)
    if st:
        assert lru_hit_rate(st, size) == naive_lru(st, size), (st, size)
w = sorted((1 / i ** 1.0 for i in range(1, 101)), reverse=True)
assert abs(ideal_hit_rate(100, 10, 1.0) - sum(w[:10]) / sum(w)) < 1e-12
assert ideal_hit_rate(100, 100, 1.0) == 1.0 and ideal_hit_rate(100, 10, 0.0) == 0.1
st = zipf_stream(1000, 20000, 1.0, 5)
assert len(st) == 20000 and min(st) >= 0 and max(st) < 1000 and st == zipf_stream(1000, 20000, 1.0, 5)
freq = [0] * 1000
for k in st:
    freq[k] += 1
assert freq[0] > freq[9] > freq[99] and abs(freq[0] / 20000 - 1 / sum(1 / i for i in range(1, 1001))) < 0.012
u = zipf_stream(1000, 40000, 0.0, 5)
assert abs(lru_hit_rate(u, 100) - 0.1) < 0.01                          # uniform keys: hit rate is cache size / keys
big_stream = zipf_stream(100000, 300000, 1.0, 7)
warm_stream = zipf_stream(100000, 600000, 1.0, 7)
distinct = len(set(big_stream))
assert distinct == 48056 < 50000
assert lru_hit_rate(big_stream, 50000) == 1 - distinct / len(big_stream)      # a cache that never evicts: only first touches miss
gaps = []
prev_gain = None
for size in (100, 1000, 10000, 50000):
    ideal, lru = ideal_hit_rate(100000, size, 1.0), lru_hit_rate(big_stream, size)
    warm = lru_hit_rate(warm_stream, size, skip=300000)
    assert lru < ideal and warm < ideal + 1e-9
    gaps.append(ideal - warm)
    need('| %s | %.1f%% | %.1f%% | %.1f%% |' % (format(size, ','), ideal * 100, lru * 100, warm * 100))
assert gaps[0] > gaps[1] > gaps[2] > gaps[3] and round(gaps[3] * 100, 1) == 2.5            # policy gap shrinks with size
assert [round(g * 100, 1) for g in gaps] == [14.0, 11.2, 7.2, 2.5]
ideals = [ideal_hit_rate(100000, c, 1.0) for c in (100, 1000, 10000)]
assert abs((ideals[1] - ideals[0]) - (ideals[2] - ideals[1])) < 0.01           # roughly constant gain per decade
need('48,056', '2.5 points below ideal', '91.8% against 94.3%')

# ---------------------------------------------------------------- capacity figures in the prose
m_mod, m_ring = by['mod N'][2], by['ring, 1000 vnodes'][2]
miss_mod, miss_ring = 1 - 0.95 * (1 - m_mod), 1 - 0.95 * (1 - m_ring)
assert round(miss_mod * 100, 1) == 91.5 and round(miss_ring * 100) == 14 and 2.5 < 100000 * miss_ring / 5000 < 3
assert round(1 / 9 * 100, 1) == 11.1
need('about 91.5%', 'about 14%', 'almost three times', '1/9 = 11.1%')
need('1,000 reads/s', '5,000 reads/s', '10,000 reads/s', '100,000 reads/s',
     '0.605 ms', '1.025 ms', '1.550 ms', '11.000 ms',
     '%s reads/s' % format(round(100000 * miss_mod, -2), ',.0f'), '%s reads/s' % format(round(100000 * miss_ring, -2), ',.0f'))
print('sy45 code checks passed')
