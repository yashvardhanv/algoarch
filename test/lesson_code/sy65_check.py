"""Runs the python blocks of the sy65 live-streaming lesson: a sliding-window live playlist (RFC 8216 window and join rules, the
latency it implies, how long a paused player can resume), request coalescing at a cache tier against brute-force counts, and the
live-comments path (a room with sequence numbers and a resume buffer, hub fan-out counts, a per-room thinning rule) against
reference counts and a random join/leave/lose/resume fuzz. Figures the lesson prints from simulations are asserted here."""
import re, sys, random, math, collections

src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
assert len(blocks) >= 3, 'expected the lesson code blocks'
ns = {}
for b in blocks:
    exec(b, ns)
LiveOrigin, join_seq, join_latency, pause_budget = ns['LiveOrigin'], ns['join_seq'], ns['join_latency'], ns['pause_budget']
CacheNode = ns['CacheNode']
Room, Hub, Client, select = ns['Room'], ns['Hub'], ns['Client'], ns['select']


def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the checked figure: %r' % p


def forbid(*phrases):
    for p in phrases:
        assert p not in src, 'lesson text still contains stale wording: %r' % p


# ---- 1. the sliding window and the join rule ----------------------------------------------------------------------------
try:
    LiveOrigin(2, 2)
    raise SystemExit('a live playlist shorter than three target durations must be refused (RFC 8216 6.2.2)')
except AssertionError:
    pass
o = LiveOrigin(2, 6)
assert o.playlist() == [] and o.media_sequence() == 0
for _ in range(4):
    o.publish()
assert o.playlist() == [0, 1, 2, 3] and o.media_sequence() == 0
for _ in range(6):
    o.publish()
assert o.newest == 9 and o.playlist() == [4, 5, 6, 7, 8, 9] and o.media_sequence() == 4
assert len(o.playlist()) * o.target >= 3 * o.target                  # never shorter than three target durations
assert join_seq(o) == 7 and o.playlist()[-3] == 7                    # the third segment from the end
# the media sequence number never decreases and increases by one per removed segment (RFC 8216 6.2.2)
o = LiveOrigin(2, 5)
prev = 0
for n in range(40):
    o.publish()
    ms = o.media_sequence()
    assert ms >= prev and ms - prev <= 1 and (n < 5 or ms == n - 4)
    prev = ms
# RFC 8216 6.2.2: a removed segment stays for its own duration plus the playlist's duration: W + 1 segments after removal.
# Segment s leaves the playlist when s + W is published; the period ends when s + 2W + 1 is published (not guaranteed from then on).
o = LiveOrigin(2, 4)
for _ in range(30):
    o.publish()
assert o.newest == 29 and o.fetchable(29) and o.fetchable(22) and o.fetchable(21) and not o.fetchable(20) and not o.fetchable(30) and not o.fetchable(-1)
assert 29 - 21 == 2 * 4 and (4 + 1) * o.target == 10        # 21 left the playlist when 25 appeared: 10 s (5 segments) later it is still owed until 29
assert 29 - 4 + 1 == 26 == o.media_sequence()                        # 22..25 are out of the playlist but still served

# latency behind live at join: segment n is available at (n + 1) * T + d (encode and package delay d); the player starts at the
# third segment from the end, so the first frame it shows is 3T + d (joined just after a publish) to just under 4T + d old
for T, d in [(2, 1.5), (6, 1.5), (4, 0), (1, 2.0)]:
    lat = [join_latency(T, d, t0 / 100.0) for t0 in range(int(20 * T * 100), int(30 * T * 100), 7)]
    assert min(lat) == 3 * T + d or abs(min(lat) - (3 * T + d)) < 0.07, (T, d, min(lat))
    assert max(lat) < 4 * T + d + 1e-9 and max(lat) > 4 * T + d - 0.07, (T, d, max(lat))
assert abs(join_latency(2, 1.5, 10 + 1.5) - 7.5) < 1e-9          # joined the instant segment 4 (the fifth) became available
assert (3 * 2 + 1.5, 4 * 2 + 1.5) == (7.5, 9.5) and (3 * 6 + 1.5, 4 * 6 + 1.5) == (19.5, 25.5)
need('7.5 to 9.5 seconds', '19.5 to 25.5 seconds')

# how long can a player pause and still resume without re-joining?  brute force against the closed form
for W in range(3, 12):
    for retained in (False, True):
        best = -1
        for k in range(0, 4 * W):
            org = LiveOrigin(2, W)
            for _ in range(20):
                org.publish()
            nxt = join_seq(org)                                      # the segment the player needs next
            for _ in range(k):
                org.publish()
            ok = (org.fetchable(nxt) if retained else nxt in org.playlist())
            if ok:
                best = k
        assert best == pause_budget(W, retained), (W, retained, best, pause_budget(W, retained))
assert [pause_budget(6, False), pause_budget(6, True)] == [3, 10]
need('3 segments', '10 segments')

# ---- 2. coalescing at a cache tier -------------------------------------------------------------------------------------
def run_single(arrivals, lat, coalesce):
    n = CacheNode(lat, None, coalesce)
    answers = [n.get('s', t) for t in sorted(arrivals)]
    return n.fetches, answers


rng = random.Random(61)
for _ in range(300):
    N, lat = rng.randint(1, 60), rng.choice([0.01, 0.05, 0.2])
    arr = sorted(rng.uniform(0, 1.0) for _ in range(N))
    f, ans = run_single(arr, lat, True)
    assert f == 1 and all(a >= arr[0] + 2 * lat - 1e-12 for a in ans)
    assert all(abs(a - max(t, arr[0] + 2 * lat)) < 1e-12 for a, t in zip(ans, arr)), 'everyone is answered at the first reply or at once'
    f2, ans2 = run_single(arr, lat, False)
    expect = sum(1 for t in arr if t < arr[0] + 2 * lat)             # every request that arrives before the first reply goes upstream itself
    assert f2 == expect, (f2, expect)
# a hit after the reply does not go upstream again, and a second segment is a separate object
n = CacheNode(0.05, None, True)
close = lambda a, b: abs(a - b) < 1e-9
assert close(n.get('a', 0.0), 0.1) and close(n.get('a', 0.04), 0.1) and close(n.get('a', 0.1), 0.1) and n.get('a', 5.0) == 5.0 and n.fetches == 1
assert close(n.get('b', 5.0), 5.1) and n.fetches == 2
nn = CacheNode(0.05, None, False)                                 # no coalescing, a request exactly at the reply time is a hit
nn.get('a', 0.0)
assert close(nn.get('a', 0.1), 0.1) and nn.fetches == 1 and nn.get('a', 0.09) is not None and nn.fetches == 2
# two tiers: E edges, a shield, the origin. Without a shield every edge asks the origin; with one the origin is asked once.
def tiers(E, per_edge, shield, coalesce, seed):
    rng = random.Random(seed)
    top = CacheNode(0.04, None, coalesce) if shield else None
    edges = [CacheNode(0.02, top, coalesce) for _ in range(E)]
    events = sorted((rng.uniform(0, 0.5), e) for e in range(E) for _ in range(per_edge))
    for t, e in events:
        edges[e].get('s', t)
    return edges, top
edges, top = tiers(50, 200, True, True, 1)
assert top.fetches == 1 and sum(e.fetches for e in edges) == 50
edges, top = tiers(50, 200, False, True, 1)
assert sum(e.fetches for e in edges) == 50 and top is None           # no shield: the origin sees one request per edge
edges, top = tiers(50, 200, True, False, 1)
assert top.fetches > 1 and sum(e.fetches for e in edges) > 50        # nobody coalescing: a herd reaches the origin
HERD = (top.fetches, sum(e.fetches for e in edges))
assert HERD == (1624, 2488), HERD
need("1,624 requests leave the shield and 2,488 leave the edges")
for E_, per in [(1, 1), (5, 30), (50, 200), (200, 5)]:
    for seed in range(3):
        edges, top = tiers(E_, per, True, True, seed)
        assert top.fetches == 1 and sum(e.fetches for e in edges) == E_
        edges, _ = tiers(E_, per, False, True, seed)
        assert sum(e.fetches for e in edges) == E_

# ---- 3. live comments: a room of frames, a resume ring -----------------------------------------------------------------
def pub(rm, rng, k=1, prio=0):
    for _ in range(k):
        rm.post('u', 'x', prio)
    return rm.tick(rng)


rng0 = random.Random(1)
r = Room(ring=5, cap=1000)
assert r.since(0) == ('ok', []) and r.tick(rng0) is None and r.seq == 0
for i in range(1, 4):
    assert pub(r, rng0)['seq'] == i
assert [f['seq'] for f in r.since(0)[1]] == [1, 2, 3] and [f['seq'] for f in r.since(2)[1]] == [3] and r.since(3) == ('ok', [])
assert r.tick(rng0) is None and r.seq == 3                           # an empty tick uses no frame number
for i in range(4, 9):
    pub(r, rng0)
assert [f['seq'] for f in r.since(3)[1]] == [4, 5, 6, 7, 8] and r.since(3)[0] == 'ok'     # ring of 5 holds 4..8
assert r.since(2) == ('gap', 4) and r.since(0) == ('gap', 4) and r.since(8) == ('ok', []) and r.since(99) == ('ok', [])
rng = random.Random(71)
for _ in range(500):
    ring = rng.randint(1, 12)
    rm, allf = Room(ring=ring, cap=1000), []
    for _ in range(rng.randint(0, 40)):
        f = pub(rm, rng0, rng.randint(0, 2))
        if f is not None:
            allf.append(f['seq'])
    assert allf == list(range(1, len(allf) + 1))
    for last in range(0, len(allf) + 3):
        kind, got = rm.since(last)
        want = [s_ for s_ in allf if s_ > last]
        held = allf[-ring:] if allf else []
        if not want:
            assert (kind, got) == ('ok', [])
        elif want[0] in held:
            assert kind == 'ok' and [f['seq'] for f in got] == want
        else:
            assert kind == 'gap' and got == held[0]

# hub: hops follow edges, deliveries follow connections, and neither depends on how many messages were posted
hub = Hub(ring=100, cap=1000)
for e, c in [('e1', 'a'), ('e1', 'b'), ('e2', 'c'), ('e3', 'd')]:
    hub.join('room', e, c)
assert hub.tick('room', rng0) is None                                 # nothing posted: no frame
hub.post('room', 'u', 'hi')
assert hub.tick('room', rng0) == {'seq': 1, 'hops': 3, 'deliveries': 4}
hub.leave('room', 'e3', 'd')
hub.post('room', 'u', 'x')
assert hub.tick('room', rng0)['hops'] == 2                            # an edge with no viewers is no longer a hop
hub.leave('room', 'e1', 'a')
hub.post('room', 'u', 'x')
assert hub.tick('room', rng0) == {'seq': 3, 'hops': 2, 'deliveries': 2}
hub.post('empty', 'u', 'x')
assert hub.tick('empty', rng0) == {'seq': 1, 'hops': 0, 'deliveries': 0}
hub = Hub(ring=10, cap=20)
V, E = 1000, 10
for i in range(V):
    hub.join('big', 'e%d' % (i % E), 'c%d' % i)
tot = []
for _ in range(7):
    for _ in range(500):
        hub.post('big', 'u', 'm')
    tot.append(hub.tick('big', rng0))
assert sum(t['hops'] for t in tot) == 7 * E and sum(t['deliveries'] for t in tot) == 7 * V
assert hub.rooms['big'].n == 3500 and all(len(f['msgs']) == 20 for f in hub.rooms['big'].buf)

# THE COMBINATION: thinning together with the real client.  Numbering messages and thinning them makes holes by design.
def naive_numbered_messages(ticks=10, per_tick=500, cap=20, seed=3):
    rng = random.Random(seed)
    n, last, resyncs, received = 0, 0, 0, 0
    for _ in range(ticks):
        batch = [{'n': n + i + 1, 'prio': 0} for i in range(per_tick)]
        n += per_tick
        for m in select(batch, cap, rng):
            if m['n'] <= last:
                continue
            if m['n'] == last + 1:
                received += 1
                last = m['n']
            else:                                                       # a hole: resume pulls everything after `last`
                resyncs += 1
                received += n - last
                last = n
    return resyncs, received
assert naive_numbered_messages() == (10, 5000)
need('10 resyncs and 5,000 messages received instead of 200')
rm = Room(ring=120, cap=20)
cl = Client('v')
cl.connect(rm)
for t in range(10):
    for _ in range(499):
        rm.post('u', 'x')
    pn = rm.post('mod', 'x', 1)
    fr = rm.tick(rng0)
    assert len(fr['msgs']) == 20 and pn in [m['n'] for m in fr['msgs']]
    cl.on_live(rm, fr)
assert (cl.syncs, len(cl.received), cl.shown, cl.gaps) == (0, 10, 200, [])
rm = Room(ring=120, cap=20)
cl = Client('v')
cl.connect(rm)
for t in range(10):
    for _ in range(500):
        rm.post('u', 'x')
    fr = rm.tick(rng0)
    if t != 4:                                                          # frame 5 is lost on the wire
        cl.on_live(rm, fr)
assert (cl.syncs, cl.received, cl.shown, cl.gaps) == (1, list(range(1, 11)), 200, [])     # one resume, thinned frames, 200 not 5,000


def fuzz_chat(seed, ring):
    rng = random.Random(seed)
    room = Room(ring=ring, cap=rng.choice([1, 3, 20]))
    clients = [Client('c%d' % i) for i in range(4)]
    online = set()
    for _ in range(150):
        op = rng.random()
        c = rng.choice(clients)
        if op < 0.45:
            for _ in range(rng.randint(0, 40)):
                room.post('u', 'm', 1 if rng.random() < 0.05 else 0)
            frame = room.tick(rng)
            if frame is not None:
                assert len(frame['msgs']) <= room.cap
                for x in clients:
                    if x.name in online and rng.random() > 0.2:             # a live frame that may be lost on the wire
                        x.on_live(room, frame)
        elif op < 0.65:
            c.connect(room); online.add(c.name)
        elif op < 0.8:
            online.discard(c.name)
        elif op < 0.9 and c.name in online:
            c.sync(room)
    for c in clients:
        if c.name in online:
            c.sync(room)
            assert c.last == room.seq, (seed, c.name, c.last, room.seq)
        seqs = c.received
        assert seqs == sorted(set(seqs)), 'out of order or duplicated'
        assert c.shown <= room.cap * len(seqs)
        if c.start is not None:
            lost = sum(b - a + 1 for a, b in c.gaps)
            assert len(seqs) + lost == c.last - c.start, (seed, c.name, len(seqs), lost, c.start, c.last)
            for a, b in c.gaps:
                assert not any(a <= s_ <= b for s_ in seqs)
    return sum(len(c.gaps) for c in clients)


gaps_small = sum(fuzz_chat(s, 3) for s in range(300))
gaps_big = sum(fuzz_chat(s, 10_000) for s in range(300))
assert gaps_big == 0 and gaps_small > 0
# a first-time viewer starts from now, not from the beginning of the ring; duplicates and stale frames change nothing
rm = Room(ring=50, cap=20)
for _ in range(5):
    pub(rm, rng0)
cl = Client('new')
cl.connect(rm)
assert (cl.last, cl.start, cl.received) == (5, 5, [])
cl.sync(rm)
assert cl.received == [] and cl.last == 5
f6, f7, f8 = pub(rm, rng0), pub(rm, rng0), pub(rm, rng0)                # live copies of 6 and 7 are lost
cl.on_live(rm, f8)
assert cl.received == [6, 7, 8] and cl.last == 8
before = cl.syncs
cl.on_live(rm, f8); cl.on_live(rm, f6)
assert cl.received == [6, 7, 8] and cl.syncs == before          # a duplicate is dropped, it does not trigger a resume
nn = Client('n')                                                       # a client that never connected ignores live frames
nn.on_live(rm, f8)
assert nn.received == [] and nn.syncs == 0

# ---- 4. thinning a hot room ---------------------------------------------------------------------------------------------
batch = [{'n': i, 'prio': 1 if i in (3, 7) else 0} for i in range(1, 11)]
rng = random.Random(81)
for _ in range(500):
    cap = rng.randint(1, 12)
    pick = select(batch, cap, rng)
    assert len(pick) == min(cap, len(batch)) and [m['n'] for m in pick] == sorted(m['n'] for m in pick)
    assert all(m in batch for m in pick) and len({m['n'] for m in pick}) == len(pick)
    if cap >= 2:
        assert 3 in [m['n'] for m in pick] and 7 in [m['n'] for m in pick]        # priority always survives
pb = [{'n': i, 'prio': 1} for i in range(1, 8)]
assert [m['n'] for m in select(pb, 3, random.Random(1))] == [5, 6, 7]            # priority alone over the cap: the newest win
assert select([], 5, random.Random(1)) == [] and select(batch, 0, random.Random(1)) == []
assert [m['n'] for m in select(batch, 99, random.Random(1))] == list(range(1, 11))
cnt, T = collections.Counter(), 40_000
rng = random.Random(91)
for _ in range(T):
    for m in select(batch, 5, rng):
        cnt[m['n']] += 1
for i in range(1, 11):
    if i in (3, 7):
        assert cnt[i] == T
    else:
        assert abs(cnt[i] / T - 3 / 8) < 0.01, (i, cnt[i] / T)
assert abs(cnt[1] - cnt[10]) / T < 0.015

# ---- 5. text locks ------------------------------------------------------------------------------------------------------
need('Do this after', 'Last reviewed: 27 November 2026', 'RFC 8216', 'three target durations', 'Edge', 'Pubsub', 'Clue', 'Room',
     '3-second HLS segments', '98 percent', 'nearly a hundred PoPs')
assert len(re.findall(r'^\d+\. ', src.split('## Drills')[1].split('## Homework')[0], re.M)) == 8, 'eight drills'
need('plus the duration of the longest playlist', 'Caching Patterns and Consistent Hashing', '`2W - 2`', 'a cold herd can be far worse')
forbid("at least the playlist's duration", '2W - 3', '9 segments', '3 or 9', 'Hub.publish', 'ring buffer of the last N messages')
for bad in ('lakh', 'crore', 'LPA'):
    forbid(bad)
print('sy65 code checks passed')
