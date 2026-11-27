"""Runs the python blocks of the sy70 dating-app lesson: the swipe/match write path under every interleaving of two
clients (and random schedules of many), the Bloom filter and its rotating variant for the seen set, and the exposure
feedback loop with and without a cap. Figures the lesson prints from the simulation are asserted here."""
import re, sys, random, itertools, math

src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
assert len(blocks) >= 3, 'expected the lesson code blocks'
ns = {}
for b in blocks:
    exec(b, ns)
SwipeStore, swipe_steps = ns['SwipeStore'], ns['swipe_steps']
Bloom, bloom_size, bloom_fp, RotatingSeen = ns['Bloom'], ns['bloom_size'], ns['bloom_fp'], ns['RotatingSeen']
simulate_exposure = ns['simulate_exposure']


def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the checked figure: %r' % p


def forbid(*phrases):
    for p in phrases:
        assert p not in src, 'lesson text still contains stale wording: %r' % p


def run_schedule(gens, schedule):
    """Advance generator number s for each s in schedule; each generator has 2 segments (one yield)."""
    live = list(gens)
    for s in schedule:
        try:
            next(live[s])
        except StopIteration:
            pass


# ---- 1. two swipes, every interleaving ---------------------------------------------------------------------------
scheds = sorted(set(itertools.permutations([0, 0, 1, 1])))
assert len(scheds) == 6
for sch in scheds:
    st = SwipeStore()
    run_schedule([swipe_steps(st, 'A', 'B'), swipe_steps(st, 'B', 'A')], sch)
    assert list(st.matches) == [('A', 'B')], ('safe order must always produce exactly one match', sch)
lost = []
for sch in scheds:
    st = SwipeStore()
    run_schedule([swipe_steps(st, 'A', 'B', safe=False), swipe_steps(st, 'B', 'A', safe=False)], sch)
    if not st.matches:
        lost.append(sch)
assert len(lost) == 4, lost                                      # read-then-write loses 4 of 6 orders: both read before either writes
assert all(sch[:2] in ((0, 1), (1, 0)) for sch in lost)
assert (0, 0, 1, 1) not in lost and (1, 1, 0, 0) not in lost
# a one-sided swipe never matches; a retried swipe (double tap) never makes a second match
for safe in (True, False):
    st = SwipeStore()
    run_schedule([swipe_steps(st, 'A', 'B', safe)], [0, 0])
    assert not st.matches
st = SwipeStore()
for _ in range(3):
    run_schedule([swipe_steps(st, 'A', 'B')], [0, 0])
run_schedule([swipe_steps(st, 'B', 'A')], [0, 0])
run_schedule([swipe_steps(st, 'B', 'A')], [0, 0])
run_schedule([swipe_steps(st, 'A', 'B')], [0, 0])
assert list(st.matches) == [('A', 'B')]
assert st.create_match('A', 'B') is False and st.create_match('B', 'A') is False and st.matches[('A', 'B')] == 1   # a second creator is told it was already done (no second notification)
st = SwipeStore()                                              # pair key is unordered, ids compare numerically
for pair in ((9, 10), (10, 9)):
    run_schedule([swipe_steps(st, *pair)], [0, 0])
assert list(st.matches) == [(9, 10)]

# many users, random schedules, against the definition: a match is a pair that swiped right on each other
rng = random.Random(70)
for trial in range(300):
    n = rng.randint(3, 12)
    swipes = [(rng.randrange(n), rng.randrange(n)) for _ in range(rng.randint(1, 40))]
    swipes = [(a, b) for a, b in swipes if a != b]
    expected = {(min(a, b), max(a, b)) for (a, b) in swipes if (b, a) in set(swipes)}
    st = SwipeStore()
    gens = [swipe_steps(st, a, b) for a, b in swipes]
    order = [i for i in range(len(gens)) for _ in range(2)]
    rng.shuffle(order)
    run_schedule(gens, order)
    assert set(st.matches) == expected and len(st.matches) == len(expected), (trial, swipes)
    # with the unsafe order some trial must lose a match (the model is not vacuous)
lost_any = 0
for trial in range(300):
    n = rng.randint(2, 4)
    swipes = [(0, 1), (1, 0)] + [(rng.randrange(n), rng.randrange(n)) for _ in range(3)]
    swipes = [(a, b) for a, b in swipes if a != b]
    expected = {(min(a, b), max(a, b)) for (a, b) in swipes if (b, a) in set(swipes)}
    st = SwipeStore()
    gens = [swipe_steps(st, a, b, safe=False) for a, b in swipes]
    order = [i for i in range(len(gens)) for _ in range(2)]
    rng.shuffle(order)
    run_schedule(gens, order)
    lost_any += set(st.matches) != expected
assert lost_any > 20, lost_any

# ---- 2. Bloom filter ---------------------------------------------------------------------------------------------
assert bloom_size(1000, 0.01) == (9586, 7)
assert bloom_size(100_000, 0.01) == (958_506, 7)
m, k = bloom_size(2000, 0.01)
assert abs(bloom_fp(m, k, 2000) - 0.01) < 0.0015
assert abs(bloom_fp(1000, 1, 1000) - (1 - math.exp(-1))) < 1e-12           # one hash, load 1: 1 - e^-1
bf = Bloom(m, k)
members = list(range(0, 4000, 2))                                           # 2000 even ids
for x in members:
    bf.add(x)
assert all(x in bf for x in members), 'a Bloom filter has no false negatives'
others = [x for x in range(1, 40001, 2)]                                    # 20000 odd ids, never added
fp = sum(1 for x in others if x in bf) / len(others)
assert 0.005 < fp < 0.016, fp                                               # target 1 percent
fp_small = Bloom(m, 1)                                                      # one hash is much worse
for x in members:
    fp_small.add(x)
fp1 = sum(1 for x in others if x in fp_small) / len(others)
assert fp1 > 3 * fp, (fp1, fp)
assert len(bf.bits) == (m + 7) // 8
assert bf.k == 7
idx = bf._idx(123)
assert len(idx) == 7 and all(0 <= i < m for i in idx) and len(set(idx)) >= 5
# every hash position is set after add (catches a filter that sets only the first)
bf2 = Bloom(1024, 5)
bf2.add('x')
assert all(bf2.bits[i >> 3] >> (i & 7) & 1 for i in bf2._idx('x'))
assert sum(bin(b).count('1') for b in bf2.bits) == len(set(bf2._idx('x')))

# rotating generations: recent keys always present, old ones eventually forgotten
rs = RotatingSeen(gens=3, n=500, p=0.001)
for g in range(5):
    for x in range(g * 1000, g * 1000 + 100):
        rs.add(x)
    if g < 4:
        rs.rotate()
assert all(x in rs for x in range(4000, 4100)), 'current generation'
assert all(x in rs for x in range(3000, 3100)) and all(x in rs for x in range(2000, 2100))   # within 3 generations
gone = sum(1 for x in range(0, 100) if x in rs) + sum(1 for x in range(1000, 1100) if x in rs)
assert gone <= 4, gone                                                      # forgotten, apart from rare false positives

# the pool a user can never see again: hidden unseen profiles ~ fp rate
pool = list(range(1, 40001, 2))
hidden = sum(1 for x in pool if x in bf)
assert hidden == round(fp * len(pool))
HIDDEN_FIG = round(100 * fp, 1)
print('bloom measured fp %.2f percent, one-hash %.1f percent' % (100 * fp, 100 * fp1))

# ---- 3. exposure feedback loop -----------------------------------------------------------------------------------
res_u = simulate_exposure(cap=None, seed=7)
res_c = simulate_exposure(cap=30, seed=7)
assert res_u['max_per_round'] > 30, res_u
assert res_c['max_per_round'] <= 30, res_c                                  # the cap is a hard invariant
assert res_u['top10_share'] > res_c['top10_share'] + 0.15, (res_u, res_c)
assert 0.0 < res_c['top10_share'] < res_u['top10_share'] <= 1.0
assert res_c['impressions'] == res_u['impressions'] == 60000                     # the cap does not starve the feed
assert simulate_exposure(cap=None, seed=7) == res_u                          # deterministic
print('exposure top-10-percent share: uncapped %.0f percent, capped %.0f percent' % (100 * res_u['top10_share'], 100 * res_c['top10_share']))
EXPO = (round(100 * res_u['top10_share']), round(100 * res_c['top10_share']))
assert round(100 * fp, 2) == 1.16 and round(100 * fp1, 1) == 9.7 and EXPO == (60, 29) and res_u['max_per_round'] == 599
need('60 percent of impressions', '29 percent and the maximum is 30', '599 viewers', '1.16 percent', '9.7 percent', '60,000 impressions', '855 KiB', '128 KiB', 'Visual (planned)', 'Two clients', '4 of 6', '6 of 6')
forbid('Tinder uses', 'Tinder stores', 'Tinder runs')
print('sy70 code checks passed')
