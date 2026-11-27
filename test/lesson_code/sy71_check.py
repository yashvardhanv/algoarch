"""Runs the python blocks of the sy71 fitness-tracking lesson: haversine distance, elevation gain with and without a
noise threshold, moving time, the encoded-polyline format (against Google's published example), Douglas-Peucker
simplification against a recursive reference and its error bound, the grid-indexed segment matcher against a
brute-force matcher, and the idempotent ingest/process pipeline under crashes."""
import re, sys, random, math

src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
assert len(blocks) >= 3, 'expected the lesson code blocks'
ns = {}
for b in blocks:
    exec(b, ns)
haversine, elevation_gain, moving_time = ns['haversine'], ns['elevation_gain'], ns['moving_time']
encode_polyline, decode_polyline = ns['encode_polyline'], ns['decode_polyline']
rdp, seg_dist = ns['rdp'], ns['seg_dist']
SegmentIndex, match_efforts, pdist = ns['SegmentIndex'], ns['match_efforts'], ns['pdist']
ActivityStore = ns['ActivityStore']


def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the checked figure: %r' % p


def forbid(*phrases):
    for p in phrases:
        assert p not in src, 'lesson text still contains stale wording: %r' % p


# ---- 1. distance, elevation, moving time ---------------------------------------------------------------------------
deg = haversine(0, 0, 1, 0)
assert abs(deg - 111194.93) < 0.01, deg                                   # 2 pi R / 360 with R = 6,371,000 m
assert abs(haversine(0, 10, 0, 11) - deg) < 0.01                           # a degree of longitude on the equator is the same
assert haversine(40, -75, 40, -75) == 0
assert abs(haversine(10, 20, -5, 33) - haversine(-5, 33, 10, 20)) < 1e-6
assert abs(haversine(60, 0, 60, 1) - deg * 0.5) < 100                      # a degree of longitude at 60 degrees is half as long (about)
assert abs(haversine(0, 179.5, 0, -179.5) - deg) < 0.01                    # across the antimeridian

assert elevation_gain([100, 100, 100], 3) == 0
assert elevation_gain([0, 5, 10, 15, 20], 3) == 20                          # a clean climb counts in full
assert elevation_gain([20, 15, 10, 5, 0], 3) == 0                           # a clean descent counts nothing
assert elevation_gain([0, 10, 0, 10], 3) == 20                              # two real ups
assert elevation_gain([0, 2, 0, 2, 0, 2], 3) == 0                           # wobble below the threshold counts nothing
assert elevation_gain([0, 3], 3) == 3 and elevation_gain([0, 2.99], 3) == 0   # the threshold itself counts
assert elevation_gain([5, 0, 5], 3) == 5                                    # drop first, then climb: the reference follows the drop
rng = random.Random(71)
noisy_flat = [100 + rng.uniform(-2, 2) for _ in range(3600)]
naive = sum(max(0, b - a) for a, b in zip(noisy_flat, noisy_flat[1:]))
assert naive > 1000 and elevation_gain(noisy_flat, 5) == 0, naive          # 1 Hz noise of +-2 m: thousands of metres of fake climb
NAIVE_FIG = round(naive)
for trial in range(50):                                                     # a true 300 m ramp under noise of +-2 m, threshold 5
    ramp = [i * 300 / 3599 + rng.uniform(-2, 2) for i in range(3600)]
    g = elevation_gain(ramp, 5)
    assert 300 - 12 <= g <= 300 + 12, g
assert moving_time([0, 1, 2, 3, 4], [0, 3, 6, 6, 6], 1.0) == 2              # two seconds moving, two standing
assert moving_time([0, 1, 2], [0, 1, 2], 1.0) == 2                          # speed exactly at the limit counts as moving
assert moving_time([0, 10, 20], [0, 5, 10], 1.0) == 0                       # 0.5 m/s with a 1 m/s limit
assert moving_time([0, 2, 7], [0, 4, 4], 1.0) == 2                          # the long standing gap is not moving time

# ---- 2. encoded polyline ---------------------------------------------------------------------------------------
google = [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
assert encode_polyline(google) == '_p~iF~ps|U_ulLnnqC_mqNvxq`@'            # example on Google's format page
assert encode_polyline([(0.0, -179.9832104)]) == '?`~oia@'                 # its worked single-value example
assert decode_polyline('_p~iF~ps|U_ulLnnqC_mqNvxq`@') == google
assert encode_polyline([]) == '' and decode_polyline('') == []
assert decode_polyline(encode_polyline([(0, 0)])) == [(0, 0)]
for trial in range(300):
    pts = [(round(rng.uniform(-90, 90), 5), round(rng.uniform(-180, 180), 5)) for _ in range(rng.randint(1, 30))]
    assert decode_polyline(encode_polyline(pts)) == pts, pts
walk = [(round(40 + rng.random() * 1e-3 * i, 5), round(-75 + rng.random() * 1e-3 * i, 5)) for i in range(50)]
assert decode_polyline(encode_polyline(walk)) == walk
big = [(-89.99999, 179.99999), (89.99999, -179.99999), (0, 0)]               # large deltas need several 5-bit chunks
assert decode_polyline(encode_polyline(big)) == big
assert all(63 <= ord(c) <= 126 for c in encode_polyline(big))
# each chunk except the last has its continuation bit set
enc = encode_polyline([(0, -179.9832104)])
assert [ord(c) - 63 for c in enc] == [0, 33, 63, 48, 42, 34, 1]

# ---- 3. Douglas-Peucker -----------------------------------------------------------------------------------------
def rdp_ref(pts, eps):
    if len(pts) < 3:
        return list(pts)
    dmax, idx = -1.0, 0
    for i in range(1, len(pts) - 1):
        d = seg_dist(pts[i], pts[0], pts[-1])
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        left, right = rdp_ref(pts[: idx + 1], eps), rdp_ref(pts[idx:], eps)
        return left[:-1] + right
    return [pts[0], pts[-1]]


assert seg_dist((0, 1), (0, 0), (2, 0)) == 1 and seg_dist((3, 0), (0, 0), (2, 0)) == 1    # distance to the segment, not the line
assert seg_dist((1, 1), (0, 0), (0, 0)) == math.hypot(1, 1)                  # degenerate segment
assert rdp([(0, 0)], 1) == [(0, 0)] and rdp([(0, 0), (1, 1)], 1) == [(0, 0), (1, 1)]
assert rdp([(0, 0), (1, 1), (2, 0)], 1) == [(0, 0), (2, 0)]                 # exactly eps away: dropped
assert rdp([(0, 0), (1, 1.01), (2, 0)], 1) == [(0, 0), (1, 1.01), (2, 0)]
for trial in range(400):
    n = rng.randint(2, 40)
    pts = [(rng.randint(0, 12), rng.randint(0, 12)) for _ in range(n)]
    eps = rng.choice([0, 1, 2, 3])
    out = rdp(pts, eps)
    assert out == rdp_ref(pts, eps), (pts, eps)
    assert out[0] == pts[0] and out[-1] == pts[-1]
    # every dropped point lies within eps of the simplified path (the error bound), checked independently
    pos = 0
    keep_idx = []
    for o in out:                                                           # find kept indices in order
        while pts[pos] != o:
            pos += 1
        keep_idx.append(pos)
        pos += 1
    for a, b in zip(keep_idx, keep_idx[1:]):
        for i in range(a + 1, b):
            assert seg_dist(pts[i], pts[a], pts[b]) <= eps + 1e-9, (pts, eps, i)
# a long track: iterative, no recursion limit, and it compresses
track = [(i * 3.0, 20 * math.sin(i / 40) + rng.uniform(-1, 1)) for i in range(5000)]
simp = rdp(track, 3.0)
assert len(simp) < 0.25 * len(track), len(simp)
RDP_KEPT = round(100 * len(simp) / len(track), 1)
long_line = [(float(i), 0.0) for i in range(5000)]
assert rdp(long_line, 0.5) == [(0.0, 0.0), (4999.0, 0.0)]
zig = [(float(i), float(i % 2) * 10) for i in range(500)]                   # worst case: nothing can be dropped
assert len(rdp(zig, 1.0)) == 500

# ---- 4. segment matching ----------------------------------------------------------------------------------------
TOL, CELL = 25.0, 100.0


def match_brute(track, segs, tol):
    best = {}
    for sid, poly in segs.items():
        near = [pdist((x, y), poly) <= tol for (_, x, y) in track]
        for i in range(len(track)):
            if math.dist(track[i][1:], poly[0]) > tol:
                continue
            for j in range(i + 1, len(track)):
                if math.dist(track[j][1:], poly[-1]) > tol:
                    continue
                if all(near[i:j + 1]):
                    cand = (track[j][0] - track[i][0], i, j)
                    if sid not in best or cand < best[sid]:
                        best[sid] = cand
    return best


def walk_track(rng, n, step=30):
    x, y, h, t = rng.uniform(0, 600), rng.uniform(0, 600), rng.uniform(0, 6.28), 0
    out = []
    for _ in range(n):
        out.append((t, x, y))
        h += rng.uniform(-0.5, 0.5)
        x, y = x + step * math.cos(h), y + step * math.sin(h)
        t += rng.randint(1, 4)
    return out


assert pdist((5, 5), [(0, 0), (10, 0), (10, 10)]) == 5
assert pdist((5, 0), [(0, 0), (10, 0)]) == 0
total_found = 0
for trial in range(60):
    base = walk_track(rng, 60)
    segs = {}
    for sid in range(8):
        a = rng.randint(0, 40)
        b = a + rng.randint(2, 15)
        poly = [(x + rng.uniform(-8, 8), y + rng.uniform(-8, 8)) for (_, x, y) in base[a:b + 1]]
        if rng.random() < 0.3:
            poly = poly[::-1]                                               # a segment ridden the other way
        segs[sid] = poly
    for sid in range(8, 12):
        segs[sid] = [(rng.uniform(0, 1500), rng.uniform(0, 1500)), (rng.uniform(0, 1500), rng.uniform(0, 1500))]
    index = SegmentIndex(segs, TOL, CELL)
    track = base if trial % 2 == 0 else walk_track(rng, 60)
    got = match_efforts(track, index)
    want = match_brute(track, segs, TOL)
    assert {k: (v[0], v[1], v[2]) for k, v in got.items()} == want, (trial, got, want)
    total_found += len(want)
assert total_found > 50, total_found                                          # the model is not vacuous
# a start point just across a cell border is still found (the grid looks at the 3 x 3 neighbourhood)
segs = {1: [(99.0, 50.0), (400.0, 50.0)]}
track = [(0, 101.0, 50.0), (10, 200.0, 50.0), (20, 399.0, 50.0), (30, 450.0, 50.0)]
assert match_efforts(track, SegmentIndex(segs, TOL, CELL))[1][0] == 20
try:
    SegmentIndex(segs, 50.0, 10.0)
    raise SystemExit('a cell smaller than the tolerance must be refused')
except AssertionError:
    pass
# a shortcut (start and end near, middle far) is not an effort; neither is riding it backwards
poly = [(0.0, 0.0), (300.0, 0.0), (300.0, 300.0)]
index = SegmentIndex({1: poly}, TOL, CELL)
assert match_efforts([(0, 0.0, 0.0), (5, 150.0, 150.0), (10, 300.0, 300.0)], index) == {}
assert match_efforts([(0, 300.0, 300.0), (5, 300.0, 0.0), (10, 0.0, 0.0)], index) == {}
ok = match_efforts([(0, 0.0, 0.0), (5, 300.0, 0.0), (9, 300.0, 300.0)], index)
assert ok[1][0] == 9 and ok[1][1:] == (0, 2)
laps = [(0, 0.0, 0.0), (5, 300.0, 0.0), (9, 300.0, 300.0), (20, 0.0, 0.0), (23, 300.0, 0.0), (26, 300.0, 300.0)]
assert match_efforts(laps, index)[1][0] == 6                                   # two laps: the better one is kept

# ---- 5. idempotent ingest and processing -------------------------------------------------------------------------
trk = [(0, 0.0, 0.0), (5, 300.0, 0.0), (9, 300.0, 300.0)]
store = ActivityStore()
a1 = store.ingest('ann', trk)
assert store.ingest('ann', trk) == a1 and len(store.activities) == 1
assert store.ingest('bob', trk) != a1 and len(store.activities) == 2
idx2 = SegmentIndex({1: poly, 2: [(0.0, 0.0), (300.0, 0.0)], 3: [(300.0, 0.0), (300.0, 300.0)]}, TOL, CELL)
clean = ActivityStore()
ca = clean.ingest('ann', trk)
clean.process(ca, idx2)
assert sorted(clean.efforts) == [(ca, 1), (ca, 2), (ca, 3)] and clean.activities[ca]['state'] == 'done'
for k in (1, 2, 3):
    s = ActivityStore()
    aid = s.ingest('ann', trk)
    try:
        s.process(aid, idx2, crash_after=k)
        crashed = False
    except RuntimeError:
        crashed = True
    assert crashed == (k <= 3)
    assert s.activities[aid]['state'] == ('queued' if k <= 3 else 'done')
    s.process(aid, idx2)
    s.process(aid, idx2)                                                    # a duplicate delivery of the same job
    assert s.efforts == clean.efforts and len(s.efforts) == 3 and s.activities[aid]['state'] == 'done'

print('polyline of a 5000-point sine: kept %s percent' % RDP_KEPT)
need('_p~iF~ps|U_ulLnnqC_mqNvxq`@', '111,194.93', 'Visual (planned)', '2,401 metres', 'within 12 m of 300', '60 random cases', 'more than 50 efforts', 'all 500 points', '7,208 bytes', '64 points and 252 bytes', 'fewer than a quarter')
forbid('Strava uses ', 'Strava stores each', 'Strava runs ', 'Strava matches segments by', 'Strava simplifies')
print('sy71 code checks passed')
