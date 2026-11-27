"""Runs the python blocks of the sy57 maps routing and ETA lesson against independent references: Floyd-Warshall on
thousands of random directed graphs (zero weights, parallel arcs, disconnected pairs, ties), a plain O(n^2) Dijkstra on
larger graphs, brute-force path enumeration for time-dependent travel, and a from-the-definition decayed-sample estimator.
Search-space figures the lesson prints are measured here and asserted against the text."""
import re, sys, random, itertools, heapq

src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
assert len(blocks) >= 3, 'expected the lesson code blocks'
ns = {}
for b in blocks:
    exec(b, ns)
dijkstra, bidirectional, astar, reverse = ns['dijkstra'], ns['bidirectional'], ns['astar'], ns['reverse']
CH = ns['CH']
arrival_fn, profile_is_fifo, td_dijkstra = ns['arrival_fn'], ns['profile_is_fifo'], ns['td_dijkstra']
blended_speed, traverse, estimate_speed = ns['blended_speed'], ns['traverse'], ns['estimate_speed']
INF = float('inf')


def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the checked figure: %r' % p


def forbid(*phrases):
    for p in phrases:
        assert p not in src, 'lesson text still contains stale wording: %r' % p


# ---- references --------------------------------------------------------------------------------------------------------
def floyd(n, edges):
    d = [[INF] * n for _ in range(n)]
    for i in range(n):
        d[i][i] = 0
    for u, v, w in edges:
        d[u][v] = min(d[u][v], w)
    for k in range(n):
        for i in range(n):
            dik = d[i][k]
            if dik == INF:
                continue
            for j in range(n):
                if dik + d[k][j] < d[i][j]:
                    d[i][j] = dik + d[k][j]
    return d


def plain_dijkstra(n, edges, s):
    """O(n^2) array version: independent of the heap version in the lesson."""
    out = [dict() for _ in range(n)]
    for u, v, c in edges:
        out[u][v] = min(out[u].get(v, INF), c)
    dist, done = [INF] * n, [False] * n
    dist[s] = 0
    for _ in range(n):
        u = min((i for i in range(n) if not done[i]), key=lambda i: dist[i], default=None)
        if u is None or dist[u] == INF:
            break
        done[u] = True
        for b, c in out[u].items():
            if dist[u] + c < dist[b]:
                dist[b] = dist[u] + c
    return dist


def to_adj(n, edges):
    adj = [[] for _ in range(n)]
    for u, v, w in edges:
        adj[u].append((v, w))
    return adj


def path_ok(edges, path, s, t, dist):
    """the returned path must exist arc by arc and add up to the reported distance"""
    assert path[0] == s and path[-1] == t
    best = {}
    for u, v, w in edges:
        best[(u, v)] = min(best.get((u, v), INF), w)
    total = 0
    for a, b in zip(path, path[1:]):
        assert (a, b) in best, 'path uses an arc that does not exist: %s->%s' % (a, b)
        total += best[(a, b)]
    assert total == dist, 'path length %s differs from reported distance %s' % (total, dist)


def rand_graph(rng, n, m, wmax):
    return [(rng.randrange(n), rng.randrange(n), rng.randint(0, wmax)) for _ in range(m)]


# ---- 1. every algorithm against Floyd-Warshall, all pairs, thousands of graphs -----------------------------------------------
rng = random.Random(57)
pairs = 0
for trial in range(600):
    n = rng.randint(1, 13)
    m = rng.randint(0, 4 * n)
    wmax = rng.choice([1, 3, 9, 100])                       # tiny ranges force ties and zero weights
    edges = rand_graph(rng, n, m, wmax)
    adj, radj = to_adj(n, edges), reverse(to_adj(n, edges))
    d = floyd(n, edges)
    order = list(range(n)); rng.shuffle(order)               # CH is correct for ANY contraction order
    chs = [CH(adj, order), CH(adj)]
    for s in range(n):
        for t in range(n):
            exp = d[s][t]
            for fn in (lambda: dijkstra(adj, s, t), lambda: bidirectional(adj, radj, s, t),
                       lambda: chs[0].query(s, t), lambda: chs[1].query(s, t)):
                got, path = fn()
                assert got == exp, (trial, s, t, got, exp)
                if exp < INF:
                    path_ok(edges, path, s, t, exp)
                else:
                    assert path is None
            pairs += 1
assert pairs > 5000

# ---- 2. larger graphs: random sparse and grid-like, 120 random pairs each, against the O(n^2) reference -----------------------
for trial in range(8):
    n = rng.choice([100, 150, 220])
    edges = rand_graph(rng, n, 2 * n, 1000) + [(i, i + 1, rng.randint(1, 1000)) for i in range(n - 1)]
    adj, radj = to_adj(n, edges), reverse(to_adj(n, edges))
    ch = CH(adj)
    for s in rng.sample(range(n), 6):
        ref = plain_dijkstra(n, edges, s)
        for t in rng.sample(range(n), 20):
            assert dijkstra(adj, s, t)[0] == ref[t]
            assert bidirectional(adj, radj, s, t)[0] == ref[t]
            got, path = ch.query(s, t)
            assert got == ref[t]
            if ref[t] < INF:
                path_ok(edges, path, s, t, ref[t])

# a graph where the first meeting of the two searches is NOT the shortest path (the stopping-rule trap)
trap = [(0, 1, 10), (1, 3, 10), (0, 2, 1), (2, 4, 1), (4, 5, 1), (5, 3, 1)]
a = to_adj(6, trap)
assert bidirectional(a, reverse(a), 0, 3)[0] == 4 and CH(a, [1, 0, 2, 3, 4, 5]).query(0, 3)[0] == 4

# ---- 3. A*: exact with a consistent potential on a grid; an over-estimate breaks it --------------------------------------------
W = H = 14
def grid(rng):
    edges, c = [], 3
    pos = {}
    for y in range(H):
        for x in range(W):
            pos[y * W + x] = (x, y)
    for y in range(H):
        for x in range(W):
            for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < W and 0 <= ny < H:
                    edges.append((y * W + x, ny * W + nx, c + rng.randint(0, 4)))   # weight >= c per unit step
    return edges, pos, c
gedges, gpos, cmin = grid(rng)
gadj = to_adj(W * H, gedges)
wrong_overestimate = 0
for _ in range(150):
    s, t = rng.randrange(W * H), rng.randrange(W * H)
    tx, ty = gpos[t]
    h = lambda u: cmin * (abs(gpos[u][0] - tx) + abs(gpos[u][1] - ty))       # Manhattan * cheapest step: consistent
    h_bad = lambda u: 3 * h(u)                                              # inadmissible
    exp = dijkstra(gadj, s, t)[0]
    got, path = astar(gadj, s, t, h)
    assert got == exp
    path_ok(gedges, path, s, t, exp)
    wrong_overestimate += astar(gadj, s, t, h_bad)[0] != exp
assert wrong_overestimate > 10, 'an inadmissible potential should visibly break A*'

# search spaces on a road-like grid: local streets cost 8 to 12, every fifth row and column is a fast road costing 2 or 3
# (illustrative figures printed in the lesson)
def road_grid(w, rng, every=5):
    edges = []
    for y in range(w):
        for x in range(w):
            for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < w:
                    fast = (dy == 0 and y % every == 0) or (dx == 0 and x % every == 0)
                    edges.append((y * w + x, ny * w + nx, rng.randint(2, 3) if fast else rng.randint(8, 12)))
    return edges
RW = 40
rng2 = random.Random(5)
re_ = road_grid(RW, rng2)
ra, rr = to_adj(RW * RW, re_), reverse(to_adj(RW * RW, re_))
chg = CH(ra)
sd = sa = sc = 0
Q = 100
for _ in range(Q):
    s, t = rng2.randrange(RW * RW), rng2.randrange(RW * RW)
    tx, ty = t % RW, t // RW
    h2 = lambda u: 2 * (abs(u % RW - tx) + abs(u // RW - ty))               # the fastest road speed bounds every step
    exp = dijkstra(ra, s, t)[0]
    assert astar(ra, s, t, h2)[0] == exp and chg.query(s, t)[0] == exp
    st = {'settled': 0}; dijkstra(ra, s, t, st); sd += st['settled']
    st = {'settled': 0}; astar(ra, s, t, h2, st); sa += st['settled']
    st = {'settled': 0}; chg.query(s, t, st); sc += st['settled']
print('road grid %dx%d (%d vertices, %d arcs): dijkstra %.1f, astar %.1f, ch %.1f settled per query on average; shortcuts %d'
      % (RW, RW, RW * RW, len(re_), sd / Q, sa / Q, sc / Q, chg.n_shortcuts))
SEARCH_FIGS = (sd / Q, sa / Q, sc / Q, chg.n_shortcuts, len(re_))
assert sc < sa < sd and sc * 8 < sd

# ---- 4. time-dependent travel against brute-force path enumeration ---------------------------------------------------------------
def rand_profile(rng):
    ts = sorted(rng.sample(range(0, 200, 5), 4))
    pts, prev_t, prev_tt = [], None, None
    for t in ts:
        tt = rng.randint(1, 40)
        if prev_t is not None:                     # keep it FIFO: tt may fall by at most the elapsed time
            tt = max(tt, prev_tt - (t - prev_t))
        pts.append((t, tt)); prev_t, prev_tt = t, tt
    return pts

def brute(n, tdedges, s, t, t0):
    best = INF
    def dfs(u, now, seen):
        nonlocal best
        if u == t:
            best = min(best, now); return
        for v, f in tdedges.get(u, []):
            if v not in seen:
                dfs(v, f(now), seen | {v})
    dfs(s, t0, {s})
    return best

f_ = arrival_fn([(0, 10), (10, 20)])                    # the interpolation itself, checked against hand values
assert f_(-5) == 5 and f_(0) == 10 and f_(5) == 20 and f_(10) == 30 and f_(15) == 35 and f_(2) == 14
assert profile_is_fifo([(0, 10), (10, 0)])             # arrival flat: leaving later never helps, equality allowed
assert profile_is_fifo([(0, 10), (5, 5)])              # slope exactly -1
assert not profile_is_fifo([(0, 10), (5, 4)])          # slope -1.2: leave 5 later, arrive 1 earlier
assert profile_is_fifo([(0, 3)]) and profile_is_fifo([(0, 3), (9, 30)])
for trial in range(400):
    n = rng.randint(2, 7)
    tdedges, adj = {}, [[] for _ in range(n)]
    for _ in range(rng.randint(1, 3 * n)):
        u, v = rng.randrange(n), rng.randrange(n)
        if u != v:
            pts = rand_profile(rng)
            assert profile_is_fifo(pts)
            f = arrival_fn(pts)
            tdedges.setdefault(u, []).append((v, f)); adj[u].append((v, f))
    s, t = rng.randrange(n), rng.randrange(n)
    t0 = rng.choice([0, 7, 60, 150, 400])
    got = td_dijkstra(adj, s, t, t0)
    exp = brute(n, tdedges, s, t, t0)
    assert (got == exp == INF) or abs(got - exp) < 1e-9, (trial, got, exp)

# without FIFO the same search is wrong: leaving later arrives earlier, and the search never tries it
bad = arrival_fn([(0, 100), (10, 0)])                   # leave at 0: arrive 100; leave at 10: arrive 10
assert not profile_is_fifo([(0, 100), (10, 0)])
adj = [[(1, bad)], []]
assert td_dijkstra(adj, 0, 1, 0) == 100
assert min(bad(t) for t in range(0, 11)) == 10          # waiting 10 would have arrived 90 earlier

# ---- 5. live speed blended into history ------------------------------------------------------------------------------------------
assert blended_speed(20, 2, 0, 3600) == 2 and blended_speed(20, 2, 3600, 3600) == 20 and blended_speed(20, 2, 7200, 3600) == 20
assert abs(blended_speed(20, 2, 1800, 3600) - 11) < 1e-12
single = lambda t0: traverse([10000], t0, 20, 2, 3600)
assert single(0) == 5000 and abs(single(100) - 4100) < 1e-9          # leaving 100 s later arrives 900 s earlier: not FIFO
assert single(100) < single(0)
cut = lambda t0: traverse([100] * 100, t0, 20, 2, 3600)
grid_t = list(range(0, 3601, 25))
vals = [cut(t) for t in grid_t]
assert all(b >= a - 1e-9 for a, b in zip(vals, vals[1:])), 'the same road cut into 100 m pieces should be FIFO here'
bad_pieces = [single(t) for t in grid_t]
assert sum(b < a - 1e-9 for a, b in zip(bad_pieces, bad_pieces[1:])) > 5
print('single 10 km piece: leave 0 arrive %.0f; leave 100 arrive %.0f; 100 m pieces: leave 0 arrive %.0f'
      % (single(0), single(100), cut(0)))
# more pieces never hurt FIFO and the total approaches the integral: always at least the best speed would allow
assert 10000 / 20 <= cut(0) <= 10000 / 2

# decayed-sample estimator against the definition
def est_ref(samples, now, hist, half_life, prior):
    num = prior * hist
    den = prior
    for ts, sp in samples:
        w = 0.5 ** ((now - ts) / half_life)
        num += w * sp; den += w
    return num / den
assert estimate_speed([], 1000, 14.0, 120, 3) == 14.0
for _ in range(500):
    k = rng.randint(0, 30)
    samples = [(rng.uniform(0, 1000), rng.uniform(1, 30)) for _ in range(k)]
    now, hist, hl, prior = 1000, rng.uniform(5, 25), rng.choice([60, 120, 600]), rng.choice([1, 3, 10])
    assert abs(estimate_speed(samples, now, hist, hl, prior) - est_ref(samples, now, hist, hl, prior)) < 1e-9
fresh = [(1000, 3.0)] * 30
assert abs(estimate_speed(fresh, 1000, 20.0, 120, 3) - (30 * 3.0 + 3 * 20.0) / 33) < 1e-9     # many fresh samples: the mean wins
assert abs(estimate_speed([(1000, 3.0)], 1000, 20.0, 120, 3) - (3.0 + 60.0) / 4) < 1e-9       # one sample barely moves it
old = [(0, 3.0)] * 30
assert estimate_speed(old, 100000, 20.0, 120, 3) > 19.99                                        # stale samples fade to history

# ---- 6. the checks must be able to fail: run three broken copies of the lesson code and require them to be caught ----------------
def build(old, new):
    ns2 = {}
    for b in blocks:
        assert b.count(old) <= 1
        exec(b.replace(old, new), ns2)
    assert any(b.count(old) == 1 for b in blocks), 'mutation target not found: %r' % old
    return ns2

m = build("if pq[0][0][0] + pq[1][0][0] >= best:", "if best < INF:")           # stop at the first meeting
a = to_adj(6, trap)
TRAP_FIRST = m['bidirectional'](a, reverse(a), 0, 3)[0]
assert TRAP_FIRST == 20, TRAP_FIRST

def fails_within(mutant_ns, trials):
    r = random.Random(99)
    for k in range(1, trials + 1):
        n = r.randint(3, 9)
        edges = rand_graph(r, n, 3 * n, 9)
        order = list(range(n)); r.shuffle(order)
        ch = mutant_ns['CH'](to_adj(n, edges), order)
        d = floyd(n, edges)
        for s_ in range(n):
            for t_ in range(n):
                if ch.query(s_, t_)[0] != d[s_][t_]:
                    return k
    return None
k_witness = fails_within(build("if y != v and d + w < seen.get(y, INF):", "if d + w < seen.get(y, INF):"), 300)
k_stop = fails_within(build("if d >= best:", "if best < INF:"), 300)
assert k_witness is not None and k_stop is not None and max(k_witness, k_stop) <= 5
print('witness-through-v mutant caught on random graph number %d; first-meeting CH query mutant on number %d' % (k_witness, k_stop))

# a nearly uniform grid has no hierarchy to exploit (figures printed in the lesson)
rng3 = random.Random(2)
ue, up, uc = grid(rng3)
ua, uch = to_adj(W * H, ue), CH(to_adj(W * H, ue))
sd = sa = sc = 0
for _ in range(200):
    s, t = rng3.randrange(W * H), rng3.randrange(W * H)
    tx, ty = up[t]
    st = {'settled': 0}; dijkstra(ua, s, t, st); sd += st['settled']
    st = {'settled': 0}; astar(ua, s, t, lambda u: uc * (abs(up[u][0] - tx) + abs(up[u][1] - ty)), st); sa += st['settled']
    st = {'settled': 0}; uch.query(s, t, st); sc += st['settled']
print('uniform grid: dijkstra %.1f, astar %.1f, ch %.1f; shortcuts %d over %d arcs' % (sd / 200, sa / 200, sc / 200, uch.n_shortcuts, len(ue)))
UNIFORM = ('%.1f' % (sd / 200), '%.1f' % (sa / 200), '%.1f' % (sc / 200), uch.n_shortcuts, len(ue))

need('%.1f' % SEARCH_FIGS[0], '%.1f' % SEARCH_FIGS[1], '%.1f' % SEARCH_FIGS[2], '{:,}'.format(SEARCH_FIGS[3]), '{:,}'.format(SEARCH_FIGS[4]),
     '%d shortcuts over %d arcs' % (UNIFORM[3], UNIFORM[4]), UNIFORM[0], UNIFORM[1], UNIFORM[2],
     'returns %d instead of 4' % TRAP_FIRST, 'within the first five random graphs', 'about 4.5 m/s', 'to 15.75', 'arrives at 4,100', '1,648 s', 'across 145 departures',
     'leaving now arrives at 5,000 s', '600 random directed graphs', '400 random small graphs', '500 random sample sets')
forbid('about 4.9 m/s', 'returns 12', 'Google uses contraction hierarchies')
print('sy57 code checks passed')
