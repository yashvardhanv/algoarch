"""Runs the python blocks of the sy69 Dynamo-style key-value store lesson against independent references: quorum overlap
enumerated over every acknowledged set and every responder set, the sloppy-quorum hole, hinted handoff and read repair under
random failures (convergence to the reference merge of everything ever written), Merkle diffs against a bucket-by-bucket
brute force, the observed-remove cart against the paper's union merge, the order-statistic tail formula against a
simulation, and gossip spread. Figures the lesson prints from simulation are asserted here."""
import re, sys, random, itertools, math

src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
assert len(blocks) >= 4, 'expected the lesson code blocks'
ns = {}
for b in blocks:
    exec(b, ns)
descends, merge_clock, reconcile = ns['descends'], ns['merge_clock'], ns['reconcile']
Dynamo, build_tree, diff_buckets, bucket = ns['Dynamo'], ns['build_tree'], ns['diff_buckets'], ns['bucket']
Cart, union_merge, p_slow, gossip_rounds, h = ns['Cart'], ns['union_merge'], ns['p_slow'], ns['gossip_rounds'], ns['h']


def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the checked figure: %r' % p


# ---- 1. version vectors: the helpers (clocks themselves are Time, Clocks and Ordering's subject) -----------------------
assert descends({'a': 2, 'b': 1}, {'a': 1}) and descends({'a': 1}, {}) and descends({}, {})
assert not descends({'a': 1}, {'a': 1, 'b': 1}) and not descends({'a': 2}, {'b': 1})
assert merge_clock([{'x': 2, 'y': 1}, {'x': 1, 'z': 1}]) == {'x': 2, 'y': 1, 'z': 1}
# the paper's figure 3: D2 overwrites D1, D3 and D4 are concurrent, D5 (written after reading both) supersedes them
D1, D2 = ({'Sx': 1}, 'D1'), ({'Sx': 2}, 'D2')
D3, D4 = ({'Sx': 2, 'Sy': 1}, 'D3'), ({'Sx': 2, 'Sz': 1}, 'D4')
D5 = ({'Sx': 3, 'Sy': 1, 'Sz': 1}, 'D5')
assert [v for _, v in reconcile([D1, D2])] == ['D2']
assert sorted(v for _, v in reconcile([D1, D2, D3, D4])) == ['D3', 'D4']
assert [v for _, v in reconcile([D1, D2, D3, D4, D5])] == ['D5']
assert [v for _, v in reconcile([D2, D2])] == ['D2']                       # the same version twice collapses to one
assert reconcile([]) == []


# ---- 2. strict quorums: R + W > N always overlap; R + W <= N need not ---------------------------------------------------
def acked_then_read(n, r, w, sloppy=False, down=(), heal_before_read=True, deliver=False, read_hints=False):
    """Every set of (w - 1) non-coordinator acks x every set of r responders. Returns (reads that missed the write, reads)."""
    nodes = ['n%d' % i for i in range(n + 2)]
    probe = Dynamo(nodes, n, r, w, sloppy, read_hints=read_hints)
    for x in down:
        probe.fail(probe.preference_list('k')[x])
    rest = [hd for hd, _ in probe.contacts('k')[1:]]
    missed = total = 0
    for acks in itertools.combinations(rest, w - 1):
        d = Dynamo(nodes, n, r, w, sloppy, read_hints=read_hints)
        for x in down:
            d.fail(d.preference_list('k')[x])
        assert d.put('k', 'new', others=set(acks)) is not None
        if heal_before_read:
            for x in down:
                d.heal(d.preference_list('k')[x])
        if deliver:
            d.deliver_hints()
        reading = [hd for hd, _ in d.contacts('k')]
        for resp in itertools.combinations(reading, r):
            got, _ = d.get('k', responders=set(resp), repair=False)
            total += 1
            missed += not any(v == 'new' for _, v in got)
    return missed, total


for n in range(1, 6):
    for r in range(1, n + 1):
        for w in range(1, n + 1):
            missed, total = acked_then_read(n, r, w)
            assert total > 0
            if r + w > n:
                assert missed == 0, (n, r, w)            # every read set meets every acknowledged set
            else:
                assert missed > 0, (n, r, w)             # and when they need not meet, some pair does not
assert acked_then_read(3, 2, 2) == (0, 6)                # the common (3,2,2): acked on 2 of 3, any 2 of 3 read it
assert acked_then_read(3, 1, 3) == (0, 3) and acked_then_read(3, 1, 1) == (2, 3)

# strict quorum with a home node down for the write: the write still needs both live home nodes, reads still overlap
assert acked_then_read(3, 2, 2, sloppy=False, down=(0,)) == (0, 3)
# sloppy quorum, same failure, hints not yet delivered: the stand-in's copy is a hint and is not read
assert acked_then_read(3, 2, 2, sloppy=True, down=(0,)) == (1, 6)
# the miss when A is back is C's: C did not take the write and the stand-in is outside the read set, so reading hints changes nothing
assert acked_then_read(3, 2, 2, sloppy=True, down=(0,), read_hints=True) == (1, 6)
# read while A is STILL down: the read set {B, C, D} is drawn from the same three healthy nodes as the write set, and the
# model's choice not to serve a hint from D is what produces the miss; serving hints removes it
assert acked_then_read(3, 2, 2, sloppy=True, down=(0,), heal_before_read=False) == (1, 6)
assert acked_then_read(3, 2, 2, sloppy=True, down=(0,), heal_before_read=False, read_hints=True) == (0, 6)
# with a strict quorum nothing is parked anywhere, so reading while down is safe
assert acked_then_read(3, 2, 2, sloppy=False, down=(0,), heal_before_read=False) == (0, 1)
# once the stand-in hands the hint back, the same read sets all see the write
assert acked_then_read(3, 2, 2, sloppy=True, down=(0,), deliver=True)[0] == 0
# with W = N the stand-in counts toward W but is never a read replica: still stale
assert acked_then_read(3, 1, 3, sloppy=True, down=(0,))[0] > 0
# reading from the same stand-in set would hide it: a read while the node is STILL down sees the first healthy N
d = Dynamo(['n%d' % i for i in range(5)], 3, 2, 2, True)
home0 = d.preference_list('k')[0]
d.fail(home0)
assert d.put('k', 'x') is not None
assert [v for _, v in d.get('k')[0]] == ['x']                              # the two live home nodes answer first
assert d.hints[d.contacts('k')[-1][0]] and d.data[home0] == {}              # the hint is parked, the home node has nothing yet
standin = d.contacts('k')[-1][0]
d.fail(standin)                                                              # a crashed stand-in cannot hand anything back
d.heal(home0)
d.deliver_hints()
assert d.data[home0] == {} and d.hints[standin]
d.heal(standin)
d.deliver_hints()
assert [v for _, v in d.data[home0]['k']] == ['x'] and all(not x for x in d.hints.values())

# a put that reaches fewer than W nodes returns failure but is NOT rolled back (the model; the paper does not say)
d = Dynamo(['a', 'b', 'c'], 3, 2, 3, False)
d.fail(d.preference_list('k')[1])
assert d.put('k', 'x') is None
assert any(d.data[x].get('k') for x in 'abc')
# W = 1 accepts a write while only the coordinator is up (the paper: rejected only if every node is down)
d = Dynamo(['a', 'b', 'c'], 3, 1, 1, True)
for x in 'abc':
    d.fail(x)
assert d.put('k', 'x') is None                                             # nobody is up at all
d.heal('b')
assert d.put('k', 'x') is not None

# ---- 3. fuzz: failures, hints, read repair, concurrent writers; everything converges to the reference merge ----------------
def fuzz(seed, sloppy):
    rng = random.Random(seed)
    nodes = ['n%d' % i for i in range(7)]
    d = Dynamo(nodes, 3, rng.choice([1, 2]), rng.choice([1, 2, 3]), sloppy)
    keys = ['key%d' % i for i in range(5)]
    ctxs, acked = {k: [{}] for k in keys}, {k: [] for k in keys}
    for step in range(80):
        op = rng.random()
        k = rng.choice(keys)
        if op < 0.45:
            clock = d.put(k, 'v%d' % step, ctx=rng.choice(ctxs[k]), others=None if rng.random() < .6 else set(rng.sample(nodes, rng.randint(0, 3))))
            if clock is not None:
                acked[k].append(clock)
        elif op < 0.65:
            got = d.get(k, repair=rng.random() < .7)
            if got:
                ctxs[k].append(got[1])
        elif op < 0.80:
            d.fail(rng.choice(nodes))
        elif op < 0.92:
            d.heal(rng.choice(nodes))
        else:
            d.deliver_hints()
    for x in nodes:
        d.heal(x)
    d.deliver_hints()
    for _ in range(2):
        for a, b in itertools.combinations(nodes, 2):
            d.sync(a, b)
    for k in keys:
        home = d.preference_list(k)[:3]
        want = sorted(repr((sorted(c.items()), v)) for c, v in reconcile([(c, v) for kk, c, v in d.log if kk == k]))
        for x in home:
            have = sorted(repr((sorted(c.items()), v)) for c, v in d.data[x].get(k, []))
            assert have == want, (seed, sloppy, k, x)
        clocks = [repr(sorted(c.items())) for kk, c, v in d.log if kk == k]
        assert len(clocks) == len(set(clocks)), 'two different writes got the same clock'
        for c in acked[k]:                                                     # an acknowledged write is never lost
            assert any(descends(cc, c) for cc, _ in d.data[home[0]].get(k, [])), (seed, k)
    assert all(not hh for hh in d.hints.values())


for seed in range(120):
    fuzz(seed, sloppy=seed % 2 == 0)

# ---- 4. read repair: a stale replica is brought up to date by a read and not before ---------------------------------------
d = Dynamo(['a', 'b', 'c', 'd'], 3, 2, 2, False)
home = d.preference_list('k')[:3]
d.put('k', 'one')
d.put('k', 'two', ctx=d.get('k')[1], others={home[1]})                         # home[2] never saw 'two'
assert d.data[home[2]]['k'][0][1] == 'one' and d.data[home[0]]['k'][0][1] == 'two'
got, _ = d.get('k', responders={home[0], home[1]}, repair=False)
assert d.data[home[2]]['k'][0][1] == 'one'                                      # no repair, still stale
d.get('k', responders={home[0], home[1]}, repair=True)
assert d.data[home[2]]['k'][0][1] == 'two'

# ---- 5. Merkle trees: the diff finds exactly the differing buckets, and the cost bound ---------------------------------------
def brute_diff(a, b, leaves):
    def per_bucket(st):
        out = [dict() for _ in range(leaves)]
        for k, vs in st.items():
            out[bucket(k, leaves)][k] = repr(sorted((sorted(c.items()), v) for c, v in vs))
        return out
    pa, pb = per_bucket(a), per_bucket(b)
    return [i for i in range(leaves) if pa[i] != pb[i]]


rng = random.Random(7)
for trial in range(400):
    leaves = rng.choice([1, 2, 4, 8, 16, 32, 64])
    keys = ['k%d' % i for i in range(rng.randint(0, 120))]
    a = {k: [({'x': rng.randint(1, 3)}, 'v%d' % rng.randint(0, 2))] for k in keys}
    b = {k: list(v) for k, v in a.items()}
    for _ in range(rng.randint(0, 6)):
        if not keys:
            break
        k = rng.choice(keys)
        kind = rng.random()
        if kind < .3:
            b.pop(k, None)
        elif kind < .6:
            b[k] = [({'x': 9}, 'changed')]
        elif kind < .8:
            a.pop(k, None)
        else:
            b[k] = b.get(k, []) + [({'y': 1}, 'sibling')]
    found, compared = diff_buckets(build_tree(a, leaves), build_tree(b, leaves))
    assert sorted(found) == brute_diff(a, b, leaves), (trial, leaves)
    d_ = len(found)
    assert compared <= 1 + 2 * d_ * int(math.log2(leaves)), (trial, compared, d_, leaves)
    if d_ == 0:
        assert compared == 1                                                   # equal roots: one hash exchanged, nothing else
assert diff_buckets(build_tree({}, 1), build_tree({}, 1)) == ([], 1)
try:
    build_tree({}, 6)
    raise SystemExit('a tree with 6 leaves must be refused')
except AssertionError:
    pass
# buckets above 9 are found as numbers, not as strings
big_a = {'k%d' % i: [({'x': 1}, 'v')] for i in range(300)}
big_b = {k: list(v) for k, v in big_a.items()}
victim = next(k for k in big_a if bucket(k, 16) == 11)
big_b[victim] = [({'x': 2}, 'v')]
assert diff_buckets(build_tree(big_a, 16), build_tree(big_b, 16))[0] == [11]
# the lesson's cost figure: 1 million keys, one key per leaf (2**20 leaves), 100 differing leaves
assert 1 + 2 * 100 * 20 == 4001

# sync merges both sides, only for keys both nodes should hold
d = Dynamo(['a', 'b', 'c', 'd', 'e'], 3, 2, 2, False)
for i in range(60):
    d.put('k%d' % i, 'v')
pairs = 0
for k in ['k%d' % i for i in range(60)]:
    hm = d.preference_list(k)[:3]
    d.data[hm[1]].pop(k, None)                                                  # lose one replica of every key
before = {x: dict(d.data[x]) for x in d.nodes}
for a_, b_ in itertools.combinations(d.nodes, 2):
    d.sync(a_, b_)
for k in ['k%d' % i for i in range(60)]:
    hm = d.preference_list(k)[:3]
    assert all(d.data[x].get(k) for x in hm), k
    for x in d.nodes:
        if x not in hm:
            assert k not in d.data[x]                                           # a non-replica is never given the key

# ---- 6. the shopping cart: union resurrects a deleted item, the observed-remove cart does not ---------------------------------
v1 = Cart().add('book', 't1').add('pen', 't2')
mine = v1.remove('book')                                                      # client 1 removes the book from version v1
yours = v1.add('lamp', 't3')                                                  # client 2, from the same v1, adds a lamp
assert mine.items() == {'pen'} and yours.items() == {'book', 'pen', 'lamp'}
assert union_merge([mine.items(), yours.items()]) == {'book', 'pen', 'lamp'}   # the paper's merge: the book is back
assert mine.merge(yours).items() == {'pen', 'lamp'}                            # observed-remove: the removal sticks
# add wins over a concurrent remove it did not observe (a different tag)
assert v1.remove('book').merge(v1.add('book', 't4')).items() == {'book', 'pen'}
assert v1.remove('book').add('book', 't4').items() == {'book', 'pen'}          # re-adding after removing works too
rng = random.Random(11)
def rand_cart():
    c = Cart()
    for _ in range(rng.randint(0, 6)):
        c = c.add(rng.choice('abc'), 't%d' % rng.randint(0, 30)) if rng.random() < .7 else c.remove(rng.choice('abc'))
    return c
for _ in range(400):
    x, y, z = rand_cart(), rand_cart(), rand_cart()
    assert x.merge(y).items() == y.merge(x).items()
    assert x.merge(y).merge(z).adds == x.merge(y.merge(z)).adds and x.merge(y).merge(z).removed == x.merge(y.merge(z)).removed
    assert x.merge(x).adds == x.adds and x.merge(x).removed == x.removed
    ref = {i for i, t in x.adds | y.adds if t not in (x.removed | y.removed)}      # independent statement of the rule
    assert x.merge(y).items() == ref

# ---- 7. latency: waiting for the w-th fastest of n replicas -----------------------------------------------------------------------
def sim_slow(n, k, q, trials, rng):
    return sum(sum(rng.random() < q for _ in range(n)) > n - k for _ in range(trials))    # slow iff more than n-k replicas are slow


assert abs(p_slow(3, 3, .01) - (1 - .99 ** 3)) < 1e-12                          # waiting for all three
assert abs(p_slow(3, 2, .01) - (3 * .01 ** 2 * .99 + .01 ** 3)) < 1e-12
assert abs(p_slow(3, 1, .01) - .01 ** 3) < 1e-15
rng = random.Random(5)
for n_, k_, q_ in [(3, 2, .05), (3, 3, .05), (5, 3, .2), (3, 1, .3)]:
    trials = 60000
    est = sim_slow(n_, k_, q_, trials, rng) / trials
    assert abs(est - p_slow(n_, k_, q_)) < 0.006, (n_, k_, q_, est, p_slow(n_, k_, q_))
assert round(p_slow(3, 3, .01) * 100, 2) == 2.97 and round(p_slow(3, 2, .01) * 100, 4) == 0.0298 and round(p_slow(3, 1, .01) * 100, 6) == 0.0001
lo, hi = 0.0, 0.5
for _ in range(60):
    mid = (lo + hi) / 2
    lo, hi = (mid, hi) if p_slow(3, 2, mid) <= 0.001 else (lo, mid)
assert round(lo * 100, 2) == 1.84                                               # per-replica slow rate that still meets 99.9% at W = 2
lo, hi = 0.0, 0.5
for _ in range(60):
    mid = (lo + hi) / 2
    lo, hi = (mid, hi) if p_slow(3, 3, mid) <= 0.001 else (lo, mid)
assert round(lo * 100, 3) == 0.033                                              # and at W = 3

# ---- 8. gossip: how many one-second rounds until every node has heard ----------------------------------------------------------
rng = random.Random(3)
runs = {n_: [gossip_rounds(n_, rng) for _ in range(reps)] for n_, reps in ((16, 200), (200, 200), (2000, 30))}
means = {n_: sum(v) / len(v) for n_, v in runs.items()}
for n_, v in runs.items():
    assert min(v) >= 2 and sum(v) / len(v) >= math.log2(n_) * 0.8               # not instant: roughly log2(n) rounds
    assert max(v) <= 4 * math.log2(n_)
assert gossip_rounds(2, random.Random(0)) == 1 and gossip_rounds(1, random.Random(0)) == 0
need('%.1f rounds' % means[200], '%.1f rounds' % means[16], '%.1f rounds' % means[2000])

hits = re.findall(r'\d+ of \d+(?= acknowledged| above)', src)
assert len(hits) >= 2 and all(x == '1 of 6' for x in hits), hits          # every statement of the sloppy-quorum miss rate
need('exactly one version in 99.94% of requests', '0.00057%', '99.9411%', '30.4 ms', '68.9 ms',
     'Berkeley', 'not rolled back', 'deleted items can resurface', 'observed-remove')
for stale in ('R + W > N always reads the latest write, sloppy or not', 'hinted replicas are read'):
    assert stale.lower() not in src.lower(), 'stale wording: %r' % stale
print('sy69 code checks passed')
