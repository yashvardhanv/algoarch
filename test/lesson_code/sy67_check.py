"""Runs the python blocks of the sy67 content delivery network lesson against independent references: the RFC 9111 freshness
arithmetic (hand-computed values, the RFC 5861 examples, every boundary), the cache-on-second-hit filter against an exact
two-generation reference and against the Bloom false-positive formula, per-object server selection (only the removed
server's objects move; overlap of two popular objects against exact closed forms), stable assignment of clients to clusters
against brute-force enumeration of every assignment, and the origin load of an edge and parent tier with and without
request coalescing. Figures the lesson prints from simulation are asserted here."""
import re, sys, random, itertools, math
from math import comb

src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
assert len(blocks) >= 5, 'expected the lesson code blocks'
ns = {}
for b in blocks:
    exec(b, ns)
freshness_lifetime, current_age, serve_decision = ns['freshness_lifetime'], ns['current_age'], ns['serve_decision']
Bloom, bloom_size, EdgeCache = ns['Bloom'], ns['bloom_size'], ns['EdgeCache']
SecondHit, admit_all = ns['SecondHit'], ns['admit_all']
servers_for, ring_servers, stable_assign = ns['servers_for'], ns['ring_servers'], ns['stable_assign']
Origin, TierNode = ns['Origin'], ns['TierNode']


def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the checked figure: %r' % p


# ---- 1. RFC 9111 freshness ------------------------------------------------------------------------------------------------
assert freshness_lifetime({'max-age': '600'}, date=1000) == 600
assert freshness_lifetime({'max-age': '600', 's-maxage': '60'}, date=1000, shared=True) == 60       # s-maxage wins in a shared cache
assert freshness_lifetime({'max-age': '600', 's-maxage': '60'}, date=1000, shared=False) == 600     # and is ignored in a private one
assert freshness_lifetime({'max-age': '600'}, date=1000, expires=9999) == 600                       # max-age beats Expires
assert freshness_lifetime({}, date=1000, expires=1300) == 300                                       # Expires minus Date, not minus now
assert freshness_lifetime({}, date=1000, expires=900) == 0                                          # already expired
assert freshness_lifetime({'max-age': 'abc'}, date=1000, expires=9999) == 0                         # invalid freshness information: stale
assert freshness_lifetime({'max-age': '-5'}, date=1000) == 0 and freshness_lifetime({'max-age': '1.5'}, date=1000) == 0
assert freshness_lifetime({'max-age': '0'}, date=1000) == 0
assert freshness_lifetime({}, date=1000) == 0                                                       # nothing explicit, no heuristic: stale
assert freshness_lifetime({}, date=10000, last_modified=0, heuristic=True) == 1000                 # 10% of the time since modification
assert freshness_lifetime({}, date=10000, last_modified=0, heuristic=False) == 0
assert freshness_lifetime({'max-age': '5'}, date=10000, last_modified=0, heuristic=True) == 5        # never heuristic when explicit
assert freshness_lifetime({}, date=1000, last_modified=None, heuristic=True) == 0

# age: the RFC's own formulas, hand-computed
assert current_age(age_value=10, date_value=95, request_time=100, response_time=102, now=110) == 20   # corrected 12, plus 8 resident
assert current_age(age_value=0, date_value=90, request_time=100, response_time=101, now=101) == 11     # apparent age 11 beats corrected 1
assert current_age(age_value=0, date_value=200, request_time=100, response_time=101, now=105) == 5      # a Date in the future: apparent age 0
assert current_age(age_value=50, date_value=0, request_time=0, response_time=0, now=0) == 50

# freshness is strict: a response whose age equals its lifetime is stale
assert serve_decision(600, 599) == 'fresh' and serve_decision(600, 600) == 'revalidate' and serve_decision(0, 0) == 'revalidate'
# RFC 5861 examples: max-age=600, stale-while-revalidate=30
assert serve_decision(600, 610, swr=30) == 'stale-while-revalidate' and serve_decision(600, 629, swr=30) == 'stale-while-revalidate'
assert serve_decision(600, 630, swr=30) == 'revalidate'                                            # "after 30 seconds" the window has closed
# RFC 5861 example: max-age=600, stale-if-error=1200; validating at age 900 gets a 500 and the cache answers from its copy
assert serve_decision(600, 900, sie=1200, origin_error=True) == 'stale-if-error'
assert serve_decision(600, 1800, sie=1200, origin_error=True) == 'stale-if-error'                  # not "greater than 1800" yet
assert serve_decision(600, 1801, sie=1200, origin_error=True) == 'error'                           # now the error is written through
assert serve_decision(600, 900, sie=0, origin_error=True) == 'error'
assert serve_decision(600, 900, sie=1200, origin_error=True, must_revalidate=True) == 'error'       # a directive can forbid serving stale
assert serve_decision(600, 100, sie=1200, origin_error=True) == 'fresh'
assert serve_decision(600, 900, swr=300, must_revalidate=True) == 'revalidate'

# ---- 2. Bloom filter and cache-on-second-hit ---------------------------------------------------------------------------------
m, k = bloom_size(40_000_000, 0.001)                                   # the Akamai paper's worked example
assert abs(m - 575.1e6) < 0.1e6, m
assert k == 10 and round(m / 8 / 2 ** 20, 1) == 68.6
fpr = (1 - math.exp(-k * 40_000_000 / m)) ** k
assert 0.0009 < fpr < 0.0011
bf = Bloom(1 << 12, 4)
keys = ['u%d' % i for i in range(300)]
for key in keys:
    bf.add(key)
assert all(key in bf for key in keys)                                  # no false negatives, ever
assert 'u300' not in Bloom(1 << 12, 4)
rng = random.Random(1)
for n_, p_ in [(2000, 0.01), (5000, 0.05), (3000, 0.001)]:
    m_, k_ = bloom_size(n_, p_)
    bf = Bloom(m_, k_)
    for i in range(n_):
        bf.add('in%d' % i)
    fp = sum(('out%d' % i) in bf for i in range(20000)) / 20000
    assert all(('in%d' % i) in bf for i in range(0, n_, 7))
    fp_expect = (1 - math.exp(-k_ * n_ / m_)) ** k_
    assert abs(fp - fp_expect) < max(0.004, fp_expect * 0.6), (fp, fp_expect)


class ExactSecondHit:
    """Reference: two generations of exact sets, rotated after `limit` new objects (the same discipline as SecondHit)."""
    def __init__(self, limit): self.limit, self.a, self.b = limit, set(), set()
    def __call__(self, key):
        seen = key in self.a or key in self.b
        if not seen:
            self.a.add(key)
            if len(self.a) >= self.limit:
                self.b, self.a = self.a, set()
        return seen


def stream(rng, n, popular, onehit_share):
    out, uniq = [], 0
    for _ in range(n):
        if rng.random() < onehit_share:
            uniq += 1; out.append('once%d' % uniq)
        else:
            out.append('hot%d' % min(popular - 1, int(rng.paretovariate(1.0)) - 1))
    return out


for trial in range(40):
    rng = random.Random(trial)
    reqs = stream(rng, 1500, rng.choice([5, 30, 200]), rng.choice([0, .3, .7]))
    limit = rng.choice([3, 10, 40])
    a, b = SecondHit(1 << 22, 4, limit), ExactSecondHit(limit)           # a filter so large it never collides must equal the exact sets
    assert [a(x) for x in reqs] == [b(x) for x in reqs], trial
sh = SecondHit(1 << 22, 4, 100)
assert sh('x') is False and sh('x') is True and sh('y') is False
# rotation forgets: after `limit` further new objects the old generation is discarded entirely (two generations are remembered)
sh = SecondHit(1 << 22, 4, 2)
assert sh('a') is False and sh('b') is False        # primary fills (2 new) -> rotates: a, b now in the secondary
assert sh('a') is True                              # still remembered by the secondary
assert sh('c') is False and sh('d') is False        # primary fills again -> secondary (a, b) discarded, (c, d) kept
assert sh('a') is False and sh('c') is True


def run_cache(reqs, cap, admit):
    c = EdgeCache(cap, admit)
    hits = sum(c.request(x, 1) for x in reqs)
    return hits / len(reqs), c.writes


rng = random.Random(42)
mixed = stream(rng, 60000, 800, 0.5)                      # half of all requests are for objects asked for once
h_all, w_all = run_cache(mixed, 400, admit_all)
h_sh, w_sh = run_cache(mixed, 400, SecondHit(1 << 20, 4, 2000))
assert h_sh > h_all and w_sh < w_all * 0.6
rng = random.Random(43)
pure = stream(rng, 60000, 800, 0.0)                       # no one-hit wonders: the filter only delays admission
p_all, pw_all = run_cache(pure, 400, admit_all)
p_sh, pw_sh = run_cache(pure, 400, SecondHit(1 << 20, 4, 2000))
assert p_sh <= p_all and pw_sh < pw_all
need('%.1f%%' % (h_all * 100), '%.1f%%' % (h_sh * 100), '{:,}'.format(w_all), '{:,}'.format(w_sh), '%.1f%%' % (p_all * 100), '%.1f%%' % (p_sh * 100))
# the paper's disk-write figure
assert round((1 - 5738 / 10209) * 100) == 44

c = EdgeCache(3, admit_all)
for x in ['a', 'b', 'c', 'a', 'd']:
    c.request(x, 1)
assert 'b' not in c.lru and set(c.lru) == {'c', 'a', 'd'} and c.writes == 4
c = EdgeCache(10, admit_all)
c.request('big', 11)                             # an object larger than the whole cache is never stored
assert 'big' not in c.lru and c.used == 0

# ---- 3. which servers hold an object -------------------------------------------------------------------------------------------
servers = ['s%d' % i for i in range(12)]
objs = ['obj%d' % i for i in range(400)]
for gone in servers[:4]:
    rest = [s for s in servers if s != gone]
    for o in objs:
        old, new = servers_for(o, servers, 3), servers_for(o, rest, 3)
        if gone in old:
            assert new == [s for s in old if s != gone] + [x for x in new if x not in old], (o, gone)     # only the lost slot is refilled
            assert len(new) == 3 and set(old) - {gone} <= set(new)
        else:
            assert new == old                                                                             # everything else stays put
    for o in objs:
        old, new = servers_for(o, rest, 3), servers_for(o, servers, 3)
        assert set(new) - set(old) <= {gone}                                                              # adding a server only adds that server
assert len(servers_for('x', servers, 20)) == 12 and servers_for('x', [], 3) == []
assert servers_for('x', servers, 3) == servers_for('x', list(reversed(servers)), 3)                       # independent of list order
ring_pos = lambda s: ns['h'](s)
assert ring_servers('x', servers, 3) == ring_servers('x', list(reversed(servers)), 3)
ring_order = sorted(servers, key=ring_pos)
r_ = ring_servers('x', servers, 5)
i0 = ring_order.index(r_[0])
assert r_ == [ring_order[(i0 + j) % 12] for j in range(5)]                                                 # k clockwise neighbours


def p_overlap_ring(n, k):          # ideal ring, n evenly spaced servers: overlap of two k-windows is max(0, k - cyclic distance)
    ok = sum(1 for d in range(n) if max(0, k - min(d, n - d)) >= (k + 1) // 2)
    return ok / n


def p_overlap_random(n, k):        # two independent random k-subsets: hypergeometric
    return sum(comb(k, x) * comb(n - k, k - x) for x in range((k + 1) // 2, k + 1)) / comb(n, k)


assert abs(p_overlap_ring(40, 8) - 9 / 40) < 1e-12                                                          # start offsets within 4: 9 of 40
assert round(p_overlap_ring(40, 8) * 100, 1) == 22.5
pr = p_overlap_random(40, 8)
pool = ['s%d' % i for i in range(40)]
rng = random.Random(9)
trials, big_r, big_p, mean_r, mean_p = 6000, 0, 0, 0, 0
order = sorted(pool, key=ring_pos)
for _ in range(trials):
    a, b = 'o%d' % rng.randrange(10 ** 9), 'o%d' % rng.randrange(10 ** 9)
    sa, sb = set(servers_for(a, pool, 8)), set(servers_for(b, pool, 8))
    big_p += len(sa & sb) >= 4; mean_p += len(sa & sb)
    i, j = rng.randrange(40), rng.randrange(40)                           # evenly spaced ideal ring: random starting positions
    ra, rb = {order[(i + t) % 40] for t in range(8)}, {order[(j + t) % 40] for t in range(8)}
    big_r += len(ra & rb) >= 4; mean_r += len(ra & rb)
assert abs(big_p / trials - pr) < 0.008 and abs(big_r / trials - 0.225) < 0.015
assert abs(mean_p / trials - 64 / 40) < 0.06 and abs(mean_r / trials - 64 / 40) < 0.06                   # both average k^2/n = 1.6
need('22.5%', '%.2f%%' % (pr * 100), '1.6 servers')

# ---- 4. stable assignment of client groups to clusters ---------------------------------------------------------------------------
M = {'M1': ['C2', 'C1', 'C3'], 'M2': ['C2', 'C1', 'C3'], 'M3': ['C2', 'C3', 'C1']}
C = {'C1': ['M2', 'M1', 'M3'], 'C2': ['M1', 'M2', 'M3'], 'C3': ['M1', 'M3', 'M2']}
assert stable_assign(M, C, {'C1': 1, 'C2': 1, 'C3': 1}) == {'M1': 'C2', 'M2': 'C1', 'M3': 'C3'}          # the paper's figure 2


def brute_stable(mp, cp, cap):
    units, cls = sorted(mp), sorted(cp)
    rank = {c: {u: i for i, u in enumerate(cp[c])} for c in cls}
    stable = []
    for choice in itertools.product(*[[None] + [c for c in mp[u] if u in rank[c]] for u in units]):
        a = dict(zip(units, choice))
        load = {c: [u for u in units if a[u] == c] for c in cls}
        if any(len(load[c]) > cap[c] for c in cls):
            continue
        blocking = False
        for u in units:
            for c in mp[u]:
                if u not in rank[c]: continue
                better_for_u = a[u] is None or mp[u].index(c) < mp[u].index(a[u])
                if not better_for_u or a[u] == c: continue
                if len(load[c]) < cap[c] or any(rank[c][u] < rank[c][v] for v in load[c]):
                    blocking = True
        if not blocking:
            stable.append(a)
    return stable


rng = random.Random(17)
for trial in range(300):
    nu, nc = rng.randint(1, 6), rng.randint(1, 3)
    units, cls = ['u%d' % i for i in range(nu)], ['c%d' % i for i in range(nc)]
    mp = {u: rng.sample(cls, rng.randint(1, nc)) for u in units}                                       # partial lists
    cp = {c: rng.sample(units, rng.randint(1, nu)) for c in cls}
    cap = {c: rng.randint(1, 3) for c in cls}
    got = stable_assign(mp, cp, cap)
    stable = brute_stable(mp, cp, cap)
    assert got in stable, (trial, got)                                                                 # the output is stable
    for u in units:                                                                                    # and best for every unit among all stable ones
        best = min((mp[u].index(s[u]) if s[u] is not None else 99 for s in stable))
        assert (mp[u].index(got[u]) if got[u] is not None else 99) == best, (trial, u)
    assert all(sum(1 for u in units if got[u] == c) <= cap[c] for c in cls)

# ---- 5. origin load: tiers and request coalescing ---------------------------------------------------------------------------------
def drive(edges, per_edge_period, horizon, ttl, edge_latency, parent, coalesce_edge, coalesce_parent, origin_latency):
    origin = Origin(origin_latency)
    up = TierNode(origin, ttl, coalesce_parent) if parent else origin
    nodes = [TierNode(up, ttl, coalesce_edge, edge_latency) for _ in range(edges)]
    events = sorted((t, i) for i in range(edges) for t in range(0, horizon, per_edge_period))
    for t, i in events:
        nodes[i].get(t)
    return origin.fetches


# waiting times: a coalesced request is answered when the fetch under way completes; without coalescing it starts its own fetch
n_ = TierNode(Origin(2), 10, True)
assert [n_.get(t) for t in (0, 1, 2, 5, 11, 12, 13, 14)] == [2, 2, 2, 5, 11, 14, 14, 14]
n_ = TierNode(Origin(2), 10, False)
assert [n_.get(t) for t in (0, 1)] == [2, 3] and n_.up.fetches == 2
n_ = TierNode(Origin(5), 10, True, hop=1)
assert n_.get(0) == 6 and n_.get(3) == 6 and n_.get(6) == 6 and n_.get(16) == 16 + 6      # freshness runs from completion (6) to 16
one = drive(1, 1, 120, 10, 0, parent=False, coalesce_edge=True, coalesce_parent=True, origin_latency=2)
assert one == 10                                                       # 120 s / (10 s fresh + 2 s fetch): ten cycles, one fetch each
assert drive(5, 1, 120, 10, 0, parent=False, coalesce_edge=False, coalesce_parent=False, origin_latency=2) == 5 * 10 * 2
assert drive(5, 1, 120, 10, 0, parent=False, coalesce_edge=True, coalesce_parent=False, origin_latency=2) == 5 * 10
# with a parent that coalesces, origin load does not grow with the number of edges
for e in (1, 5, 50):
    assert drive(e, 1, 120, 10, 0, parent=True, coalesce_edge=True, coalesce_parent=True, origin_latency=2) == drive(1, 1, 120, 10, 0, parent=True, coalesce_edge=True, coalesce_parent=True, origin_latency=2)
    assert drive(e, 1, 120, 10, 0, parent=True, coalesce_edge=False, coalesce_parent=True, origin_latency=2) == drive(1, 1, 120, 10, 0, parent=True, coalesce_edge=True, coalesce_parent=True, origin_latency=2)
no_parent_50 = drive(50, 1, 120, 10, 0, parent=False, coalesce_edge=True, coalesce_parent=True, origin_latency=2)
assert no_parent_50 == 50 * 10
with_parent_50 = drive(50, 1, 120, 10, 0, parent=True, coalesce_edge=True, coalesce_parent=True, origin_latency=2)
assert with_parent_50 < no_parent_50 / 20
# a parent that does not coalesce gives the herd straight back
assert drive(50, 1, 120, 10, 0, parent=True, coalesce_edge=True, coalesce_parent=False, origin_latency=2) > with_parent_50 * 10
need('%d fetches' % no_parent_50, '%d fetches' % with_parent_50)
for stale in ('a purge reaches every cache automatically', 'the CDN always serves fresh content'):
    assert stale.lower() not in src.lower(), 'stale wording: %r' % stale
print('sy67 code checks passed')
