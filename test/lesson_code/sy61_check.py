"""Runs the python blocks of the sy61 video-conferencing lesson: ICE candidate and pair priorities against the RFC formulas
(including the 64-bit trap), pair selection against a brute-force maximum, the SFU forwarder (sequence rewriting across
wrap, source switches on keyframes, pauses) against the spec the receiver sees, NACK packing against a decoder and a
brute-force minimum, and per-receiver layer allocation against an exact brute force. Figures the lesson prints from the
simulations are asserted here."""
import re, sys, random, itertools

src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
assert len(blocks) >= 4, 'expected the lesson code blocks'
ns = {}
for b in blocks:
    exec(b, ns)
cand_priority, pair_priority, pick_pair = ns['cand_priority'], ns['pair_priority'], ns['pick_pair']
Forwarder, nack_fcis, nack_decode = ns['Forwarder'], ns['nack_fcis'], ns['nack_decode']
allocate, greedy = ns['allocate'], ns['greedy']
M16 = 1 << 16


def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the checked figure: %r' % p


# ---- 1. ICE priorities: the RFC 8445 formulas --------------------------------------------------------------------------
assert cand_priority('host') == 126 * 2**24 + 65535 * 256 + 255 == 2130706431
assert cand_priority('prflx') == 110 * 2**24 + 65535 * 256 + 255
assert cand_priority('srflx') == 100 * 2**24 + 65535 * 256 + 255 and cand_priority('relay') == 65535 * 256 + 255
assert cand_priority('host', local_pref=1, component=2) == 126 * 2**24 + 256 + 254
assert cand_priority('host') > cand_priority('prflx') > cand_priority('srflx') > cand_priority('relay')
g, d = 5_000_000_000, 4_000_000_000
assert pair_priority(g, d) == 2**32 * d + 2 * g + 1 and pair_priority(d, g) == 2**32 * d + 2 * g      # the controlling side is G
assert pair_priority(7, 7) == 2**32 * 7 + 14 and pair_priority(7, 7) != pair_priority(7, 8)
rnd = random.Random(61)
for _ in range(2000):                         # a pair with a relayed candidate always ranks below any pair of non-relayed candidates
    a1, a2 = (cand_priority(rnd.choice(['host', 'srflx', 'prflx']), rnd.randint(0, 65535), rnd.randint(1, 256)) for _ in range(2))
    r1 = cand_priority('relay', rnd.randint(0, 65535), rnd.randint(1, 256))
    o = cand_priority(rnd.choice(['host', 'srflx', 'prflx', 'relay']), rnd.randint(0, 65535), 1)
    assert pair_priority(a1, a2) > pair_priority(r1, o) and pair_priority(a1, a2) > pair_priority(o, r1)
top = cand_priority('host', 65535, 1)
assert pair_priority(top, top) < 2**63                                    # fits a signed 64-bit integer
# the trap: two different pairs that a double-precision float cannot tell apart
d_low = cand_priority('host', 60000, 1)
gs = [cand_priority('host', lp, comp) for lp in range(65530, 65536) for comp in (1, 2)]
pairs = {pair_priority(x, d_low) for x in gs}
collide = [(x, y) for x, y in itertools.combinations(sorted(pairs), 2) if float(x) == float(y)]
assert collide, 'expected two distinct pair priorities that collide as floats'
assert all(x != y for x, y in collide) and all(pair_priority(top, top) > 2**53 for _ in [0])


# ---- 2. choosing a pair: the best working pair, by brute force ------------------------------------------------------------
def brute_pick(local, remote, works, controlling=True):
    best, arg = -1, None
    for i, l in enumerate(local):
        for j, r in enumerate(remote):
            if works(i, j):
                p = pair_priority(l[1], r[1]) if controlling else pair_priority(r[1], l[1])
                if p > best or (p == best and arg is None):
                    best, arg = p, (i, j)
    return arg, best


for seed in range(300):
    r = random.Random(seed)
    mk = lambda: [(k, cand_priority(k, r.randint(0, 65535), r.randint(1, 3))) for k in r.sample(['host', 'srflx', 'relay', 'prflx'], r.randint(1, 4))]
    L, R = mk(), mk()
    ok = {(i, j) for i in range(len(L)) for j in range(len(R)) if r.random() < 0.4}
    for ctl in (True, False):
        got = pick_pair(L, R, lambda i, j: (i, j) in ok, ctl)
        want, bestp = brute_pick(L, R, lambda i, j: (i, j) in ok, ctl)
        if want is None:
            assert got is None
        else:
            gi, gj = got
            assert (gi, gj) in ok
            pp = pair_priority(L[gi][1], R[gj][1]) if ctl else pair_priority(R[gj][1], L[gi][1])
            assert pp == bestp, (seed, got, want)
# both behind address-dependent NATs: only relay-relay-style pairs work, and ICE falls through to them
L = [('host', cand_priority('host')), ('srflx', cand_priority('srflx')), ('relay', cand_priority('relay'))]
R = [('host', cand_priority('host')), ('srflx', cand_priority('srflx')), ('relay', cand_priority('relay'))]
# the two roles must disagree only through the tie-break bit, and pick_pair must honour the role it is given
sym_l, sym_r = [('host', 5), ('host', 7)], [('host', 7), ('host', 5)]
assert pick_pair(sym_l, sym_r, lambda i, j: i == j, True) == (1, 1) and pick_pair(sym_l, sym_r, lambda i, j: i == j, False) == (0, 0)
assert pick_pair(L, R, lambda i, j: i == 2 and j == 2) == (2, 2) and pick_pair(L, R, lambda i, j: False) is None
assert pick_pair(L, R, lambda i, j: True) == (0, 0)


# ---- 3. the forwarder: one receiver's gap-free sequence numbers ------------------------------------------------------------------
def run_scenario(seed, first_out, n_events=400, wrap_start=True):
    r = random.Random(seed)
    f = Forwarder(first_out)
    nxt = {s: (r.choice([65500, 65530, 0, 1234]) if wrap_start else 100) for s in 'ABC'}     # per-source seq (16 bit), ext counters below
    ext = {s: nxt[s] for s in 'ABC'}
    sent = []                      # (out, src, ext_seq, ts, epoch)
    epoch, cur_ref, want = 0, None, None
    for _ in range(n_events):
        x = r.random()
        if x < 0.08:
            want = r.choice(['A', 'B', 'C', None])
            f.select(want)
            if want is None:
                cur_ref = None
                epoch += 1
        else:
            s = r.choice('ABC')
            ext[s] += 1 + (r.randint(1, 3) if r.random() < 0.1 else 0)        # an upstream loss leaves a gap
            key = r.random() < 0.15
            ts = ext[s] * 90
            res = f.forward(s, ext[s] % M16, ts, key)
            will = (s == want and s != cur_ref and key) or (s == cur_ref)
            if s == want and s != cur_ref and key:
                cur_ref = s
                epoch += 1
            assert (res is not None) == will, (seed, s, want, cur_ref)
            if res is not None:
                assert res[1] == ts                                            # the timestamp is not rewritten
                sent.append((res[0], s, ext[s], ts, epoch))
    return f, sent


for seed in range(400):
    first = random.Random(seed).choice([0, 5, 65530, 65535])
    f, sent = run_scenario(seed, first, wrap_start=seed % 2 == 0)
    if sent:
        assert sent[0][0] == first % M16                                           # the first forwarded packet takes the receiver's next number
    for p, q in zip(sent, sent[1:]):
        if p[4] == q[4]:                                                       # same source and epoch: the receiver sees the same gap upstream saw
            assert (q[0] - p[0]) % M16 == q[2] - p[2], (seed, p, q)
        else:                                                                  # a new epoch continues straight on: no phantom loss
            assert (q[0] - p[0]) % M16 == 1, (seed, p, q)
    for out, s, e, ts, ep in sent[-50:]:
        assert f.lookup(out) == (s, e % M16)                                   # a NACK for a recent packet maps back to the source packet
    assert len(f.sent) <= f.WINDOW

# hand cases: the first packet takes first_out; a switch waits for a keyframe; the old source keeps flowing until then
f = Forwarder(65534)
f.select('A')
assert f.forward('A', 10, 900, False) is None                                  # nothing before a keyframe
assert f.forward('A', 11, 990, True) == (65534, 990)
assert f.forward('A', 12, 1080, False) == (65535, 1080) and f.forward('A', 13, 1170, False) == (0, 1170)
f.select('B')
assert f.forward('B', 500, 5, False) is None and f.forward('A', 14, 1260, False) == (1, 1260)    # B not yet: A continues
assert f.forward('B', 501, 6, True) == (2, 6)                                  # the keyframe switches; out continues from 1
assert f.forward('A', 15, 1350, True) is None and f.forward('B', 502, 7, False) == (3, 7)
assert f.forward('B', 504, 9, False) == (5, 9)                                  # upstream lost 503: the gap is kept so the receiver can ask
assert f.lookup(5) == ('B', 504) and f.lookup(4) is None and f.lookup(2) == ('B', 501)
assert f.forward('B', 503, 8, False) == (4, 8)                                  # the late packet fills the hole at its own number
assert f.forward('B', 505, 10, False) == (6, 10)                                # and does not move the counter backwards
f.select(None)
assert f.forward('B', 506, 11, True) is None                                    # paused: nothing flows
f.select('B')
assert f.forward('B', 507, 12, False) is None and f.forward('B', 508, 13, True) == (7, 13)     # resume re-anchors with no gap
# a late packet fills its own hole and must not pull the counter back: the next switch continues after the highest number sent
f = Forwarder(0)
f.select('A')
assert [f.forward('A', q, q, True) for q in (100, 101, 103, 102)] == [(0, 100), (1, 101), (3, 103), (2, 102)]
f.select('B')
assert f.forward('B', 7, 1, True) == (4, 1)
# the lookup table is bounded and keeps the newest entries, also across many wraps of the 16-bit counter
f = Forwarder(0)
f.WINDOW = 8
f.select('A')
for q in range(50):
    f.forward('A', q, q, True)
assert len(f.sent) == 8 and f.lookup(49) == ('A', 49) and f.lookup(42) == ('A', 42) and f.lookup(41) is None
f = Forwarder(0)
f.select('A')
for q in range(70000):
    f.forward('A', q % M16, q, q == 0)
assert len(f.sent) <= f.WINDOW and f.lookup(69999 % M16) == ('A', 69999 % M16) and f.lookup((69999 - 2000) % M16) is None
# a switch between sources whose numbers are unrelated does not disturb the receiver
f = Forwarder(0)
f.select('A')
assert f.forward('A', 60000, 0, True) == (0, 0) and f.forward('A', 60001, 1, False) == (1, 1)
f.select('B')
assert f.forward('B', 3, 5, True) == (2, 5) and f.forward('B', 4, 6, False) == (3, 6)
# a real restart inside one source: numbers jump, with a keyframe it starts a new run straight after the last number
f = Forwarder(0)
f.select('A')
assert [f.forward('A', q, q, q == 100) for q in (100, 101, 102)] == [(0, 100), (1, 101), (2, 102)]
assert f.forward('A', 40000, 7, True) == (3, 7) and f.forward('A', 40001, 8, False) == (4, 8)
assert f.lookup(3) == ('A', 40000)
g = Forwarder(0)
g.select('A')
assert g.forward('A', 100, 0, True) == (0, 0) and g.forward('A', 102, 0, False) == (2, 0)
assert g.forward('A', 10000, 0, False) is None                                          # a jump of 9,898 without a keyframe waits
assert g.forward('A', 3101, 0, False) == (3001, 0)                                      # a gap of 2,999 is still just loss
assert g.forward('A', 6101, 0, False) is None                                           # 3,000 is the first jump
assert f.forward('A', 5000, 1, False) is None and f.forward('A', 5001, 2, True) == (5, 2)
assert f.forward('A', 5001 - 50, 3, False) is None      # a restart to a number just below the keyframe is indistinguishable from a straggler: dropped      # a jump without a keyframe waits for one
# restart across the 16-bit wrap is just an ordinary gap-free run
f = Forwarder(65530)
f.select('A')
assert f.forward('A', 65530, 0, True) == (65530, 0) and f.forward('A', 3, 1, False) == (65539 % M16, 1)
# a reordered packet of the new source that arrives after the switch keyframe, from before it, must not reuse an output number
f = Forwarder(0)
f.select('A')
for q in range(1, 11):
    assert f.forward('A', q, q, q == 1) == (q - 1, q)
f.select('B')
assert f.forward('B', 1000, 1, True) == (10, 1)
assert f.forward('B', 999, 0, False) is None and f.lookup(9) == ('A', 10)                       # A's packet 9 is still A's
assert f.forward('B', 1001, 2, False) == (11, 2) and f.forward('B', 65535, 3, False) is None   # across the wrap: also older
f = Forwarder(0)
f.select('B')
assert f.forward('B', 2, 0, True) == (0, 0) and f.forward('B', 65535, 0, False) is None and f.forward('B', 3, 0, False) == (1, 0)

# ---- 4. NACK packing (RFC 4585 section 6.2.1): PID + 16-bit mask ---------------------------------------------------------------
assert nack_fcis([]) == [] and nack_fcis([100]) == [(100, 0)]
assert nack_fcis([65534, 65535, 65536, 65537]) == [(65534, 0b111)]                  # wrap: 65535, 0 and 1 are PID+1..3
assert nack_fcis(list(range(100, 117))) == [(100, 0xFFFF)]                          # 17 packets in one entry
assert nack_fcis(list(range(100, 118))) == [(100, 0xFFFF), (117, 0)]                # the 18th needs another
assert nack_fcis([5, 3, 3, 4]) == [(3, 0b11)]                                       # unordered, duplicated input
assert nack_fcis([1000, 1017]) == [(1000, 0), (1017, 0)] and nack_fcis([1000, 1016]) == [(1000, 0x8000)]
for seed in range(500):
    r = random.Random(seed)
    base = r.choice([0, 100, 65500, 131000])
    lost = sorted(set(base + r.randint(0, 60) for _ in range(r.randint(0, 25))))
    fcis = nack_fcis(lost)
    assert all(0 <= pid < M16 and 0 <= blp < M16 for pid, blp in fcis)
    assert nack_decode(fcis) == {x % M16 for x in lost}, (seed, lost, fcis)         # no phantom losses, none missing
    if len(lost) <= 9:                                                              # brute-force minimum number of entries
        best = len(lost)
        for k in range(len(lost) + 1):
            done = False
            for starts in itertools.combinations(lost, k):
                if all(any(0 <= x - s <= 16 for s in starts) for x in lost):
                    best, done = k, True
                    break
            if done:
                break
        assert len(fcis) == best, (seed, lost, fcis, best)

# ---- 5. layer allocation: exact, against brute force --------------------------------------------------------------------------
LAYERS = [(0, 0), (150, 1), (500, 2), (1500, 3)]
for seed in range(300):
    r = random.Random(seed)
    n = r.randint(1, 5)
    tiles = []
    for _ in range(n):
        k = r.randint(1, 4)
        tiles.append((r.randint(1, 4), LAYERS[:k]))
    budget = r.choice([0, 100, 149, 150, 650, 1000, 2000, 2650])
    best = max(sum(w * L[c][1] for (w, L), c in zip(tiles, ch)) for ch in itertools.product(*[range(len(L)) for _, L in tiles])
               if sum(L[c][0] for (_, L), c in zip(tiles, ch)) <= budget)
    val, pick = allocate(budget, tiles)
    assert val == best, (seed, val, best)
    assert sum(L[c][0] for (_, L), c in zip(tiles, pick)) <= budget
    assert sum(w * L[c][1] for (w, L), c in zip(tiles, pick)) == val
    gval, gpick = greedy(budget, tiles)
    assert gval <= val and sum(L[c][0] for (_, L), c in zip(tiles, gpick)) <= budget
tiles = [(3, LAYERS)] + [(1, LAYERS)] * 8
vals = [allocate(b, tiles)[0] for b in range(0, 3001, 250)]
assert vals == sorted(vals)                                                        # more bandwidth never lowers the value
assert allocate(0, tiles) == (0, [0] * 9)
# the lesson's example: a 1 speaker + 8 thumbnails call
val, pick = allocate(1800, tiles)
assert pick == [2, 1, 1, 1, 1, 1, 1, 1, 1] and val == 14, (val, pick)               # unique optimum: 500 + 8 x 150 = 1,700 kbps used
assert sum(LAYERS[c][0] for c in pick) == 1700
val, pick = allocate(1500, tiles)
assert val == 12 and pick[0] == 2 and pick.count(0) == 2 and sum(LAYERS[c][0] for c in pick) == 1400    # two thumbnails switched off
assert allocate(2000, tiles)[0] == 14 and allocate(2500, tiles)[0] == 16
best_val, plans = -1, set()                                                            # exactly two plans tie at 2,000 kbps
for ch in itertools.product(range(4), repeat=9):
    cost = sum(LAYERS[c][0] for c in ch)
    if cost <= 2000:
        v = 3 * LAYERS[ch[0]][1] + sum(LAYERS[c][1] for c in ch[1:])
        if v > best_val:
            best_val, plans = v, set()
        if v == best_val:
            plans.add((ch[0], tuple(sorted(ch[1:])), cost))
assert best_val == 14 and plans == {(2, (1,) * 8, 1700), (2, (0, 1, 1, 1, 1, 1, 1, 2), 1900)}, plans
             # at 2,000 two different plans tie at 14
# greedy by marginal value per kbps against the exact answer, over random calls (illustrative)
worse, worst = 0, 0.0
rr = random.Random(7)
T = 300
for _ in range(T):
    n = rr.randint(3, 8)
    tl = [(rr.choice([1, 1, 2, 3, 5]), LAYERS[:rr.choice([2, 3, 4])]) for _ in range(n)]
    b = rr.choice([300, 600, 1000, 1600, 2000])
    ev, _p = allocate(b, tl)
    gv, _q = greedy(b, tl)
    assert gv <= ev
    if gv < ev:
        worse += 1
        worst = max(worst, (ev - gv) / ev)
assert 0 < worse < T and worst < 0.5
GREEDY_STATS = (worse, round(100 * worst))

# ---- 6. wording the lesson must keep, and stale wordings it must not ------------------------------------------------------------
for stale in ('Zoom uses', 'Google Meet uses', 'Zoom runs', 'Meet runs', 'mesh scales', 'the SFU decodes', 'sequence numbers are copied unchanged'):
    assert stale not in src, stale
need('Sources', 'Last reviewed: 27 November 2026', 'Level:** extended', '(proposed; the curriculum data holds the final rating)')
need('not consulted', 'RFC 7667', 'RFC 8445', 'RFC 8656', 'RFC 4585', 'RFC 3550', 'Discord', '2130706431', '2^63', '17 packets')
need('%d of %d random calls' % (GREEDY_STATS[0], T), 'worst %d%%' % GREEDY_STATS[1])
after = [l for l in src.splitlines() if l.startswith('> **Study time')][0]
for t in ('Scaling Patterns II: Large Blobs, Long-Running Tasks and Real-Time Updates', 'WhatsApp / Real-Time Chat'):
    assert t in src, t
print('sy61 code checks passed')
