"""Runs the python code blocks from data/new_lessons/sy39-realtime-leaderboard.md against sorting (brute force),
and checks the float tiebreak failure numbers stated in the lesson."""
import re, sys, random, math
src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
ns = {}
for b in blocks:
    exec(b, ns)
pack, unpack, Leaderboard, ShardedLeaderboard, PointsHistogram = (
    ns['pack'], ns['unpack'], ns['Leaderboard'], ns['ShardedLeaderboard'], ns['PointsHistogram'])
TIME_BITS = ns['TIME_BITS']
random.seed(39)

# --- packing: order equals (more points, then earlier), exact, invertible
END = 7_776_000
for _ in range(20000):
    p1, p2 = random.randrange(2**20), random.randrange(2**20)
    if random.random() < 0.5:
        p2 = p1
    t1, t2 = random.randrange(END + 1), random.randrange(END + 1)
    a, b = pack(p1, t1, END), pack(p2, t2, END)
    want = (p1, -t1) > (p2, -t2)
    assert (a > b) == want and (a == b) == ((p1, t1) == (p2, t2)), (p1, t1, p2, t2)
    assert unpack(a, END) == (p1, t1) and float(a) == a and a < 2**53
assert pack(2**20 - 1, 0, END) < 2**43
for bad in [(2**20, 0), (-1, 0)]:
    try:
        pack(bad[0], bad[1], END)
        raise AssertionError('out-of-range points accepted')
    except ValueError:
        pass
assert 90 * 86400 == 7_776_000 < 2**23 == 8_388_608

# --- the fractional tiebreak failures stated in the lesson
frac = lambda s, ts: s + (1.0 - ts / 1e12)
assert frac(1500, 1_700_000_000_000) == 1499.3 or abs(frac(1500, 1_700_000_000_000) - 1499.3) < 1e-9
assert frac(1_000_000, 1_700_000_000) == frac(1_000_000, 1_700_000_001)     # one second apart: same double
assert round(math.ulp(1e6) * 1e10, 2) == 1.16
assert frac(1500, 1_700_000_000) != frac(1500, 1_700_000_001)

# --- leaderboard vs sorting
def brute(best):
    return sorted(((-s, p) for p, s in best.items()))

boards = 0
for trial in range(200):
    n_players = random.randint(1, 60)
    players = ['p%d' % i for i in range(n_players)]
    single, sharded = Leaderboard(), ShardedLeaderboard(random.randint(1, 6))
    hist = PointsHistogram(1000, random.choice([1, 7, 50, 1000]))
    best = {}
    for _ in range(random.randint(1, 200)):
        p = random.choice(players)
        packed = pack(random.randint(0, 1000), random.randint(0, 50), 50)   # many exact ties on purpose
        changed = single.submit(p, packed)
        assert sharded.submit(p, packed) == changed
        assert changed == (p not in best or packed > best[p])
        if changed:
            hist.move(None if p not in best else unpack(best[p], 50)[0], unpack(packed, 50)[0])
            best[p] = packed
    order = brute(best)
    assert single.order == order
    for p, s in list(best.items())[:3]:              # resubmitting the same score is not a change (ZADD GT)
        assert single.submit(p, s) is False and single.order == order
    for k in (1, 3, 10, 100):
        assert single.top(k) == order[:k] == sharded.top(k), k
    for i, (neg, p) in enumerate(order):
        assert single.rank(p) == i == sharded.rank(p), (p, i)
        r = random.randint(0, 3)
        assert single.around(p, r) == order[max(0, i - r): i + r + 1]
        lo, hi = hist.rank_bounds(unpack(-neg, 50)[0])
        assert lo <= i <= hi, (lo, i, hi)
        pts = unpack(-neg, 50)[0]
        b = pts // hist.bucket
        assert lo == sum(1 for q in best.values() if unpack(q, 50)[0] // hist.bucket > b)
    boards += 1

# --- capacity statements that depend on the packing
assert 120 * 86400 == 10_368_000 and 2**23 < 10_368_000 < 2**24
print('sy39 code checks passed (%d random boards)' % boards)
