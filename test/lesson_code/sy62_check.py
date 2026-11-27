"""Runs the python blocks of the sy62 music-streaming lesson: the prefetch and source rules against a table, the chunk
scheduler against an independent per-step argmin and invariants, the tracker and LRU cache against naive references,
the seek index against a linear scan (and the constant-bitrate error it replaces), and fractional playlist keys against
exact fractions (order, bounds, growth). Figures the lesson prints from the simulations are asserted here."""
import re, sys, random
from fractions import Fraction
from collections import OrderedDict

src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
assert len(blocks) >= 4, 'expected the lesson code blocks'
ns = {}
for b in blocks:
    exec(b, ns)
prefetch_stage, choose_source, server_may_fetch = ns['prefetch_stage'], ns['choose_source'], ns['server_may_fetch']
assign_chunks, Tracker, LruCache = ns['assign_chunks'], ns['Tracker'], ns['LruCache']
SeekIndex, between, DIGITS, CHUNK = ns['SeekIndex'], ns['between'], ns['DIGITS'], ns['CHUNK']


def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the checked figure: %r' % p


# ---- 1. prefetch and source rules (the 2010 paper's numbers; thresholds marked assumed in the lesson are tested as stated) ------------
assert prefetch_stage(31, 0) == 'none' and prefetch_stage(30.0001, 0) == 'none'
assert prefetch_stage(30, 0) == 'peers' and prefetch_stage(11, 0) == 'peers' and prefetch_stage(10.5, 20) == 'peers'
assert prefetch_stage(10, 0) == 'server' and prefetch_stage(3, 14.9) == 'server'
assert prefetch_stage(10, 15) == 'peers' and prefetch_stage(0, 60) == 'peers'                  # enough of the next track in hand
assert choose_source(2.9, True) == ('server', True) and choose_source(3, True) == ('server', False)      # emergency below 3 s: stop uploading
assert choose_source(2.9, False) == ('server', True) and choose_source(7.9, True) == ('server', False)
assert choose_source(8, True) == ('peers', False) and choose_source(60, True) == ('peers', False)
assert choose_source(60, False) == ('server', False)                                                  # nobody to stream from
assert server_may_fetch(14.9, True) and not server_may_fetch(15, True) and server_may_fetch(100, False)

# ---- 2. the chunk scheduler ----------------------------------------------------------------------------------------------------
KB = 1024
assert CHUNK == 16 * KB
peers = {'p': {'speed': 10 * KB, 'out': 0}}
plan = assign_chunks([(0, 5.0), (1, 5.0), (2, 5.0)], peers)
assert plan == [(0, 'p'), (1, 'p'), (2, 'server')], plan          # 32 kB is always allowed; a third chunk is over the cap (2 s x 10 kB/s = 20 kB)
assert peers['p']['out'] == 0                                       # the caller's state is not mutated
fast = {'p': {'speed': 100 * KB, 'out': 0}, 'q': {'speed': 50 * KB, 'out': 0}}
plan = assign_chunks([(i, 10.0) for i in range(8)], fast)
assert [c for c, _ in plan] == list(range(8)) and plan[0] == (0, 'p')                              # chunks go out in order
assert plan.count((1, 'q')) + plan.count((2, 'q')) + plan.count((3, 'q')) >= 1                      # the busy fast peer eventually yields to the idle slower one
assert assign_chunks([(0, 0.05)], {'p': {'speed': 100 * KB, 'out': 0}}) == [(0, 'server')]          # would arrive in 0.16 s > 0.05 s: not requested
assert assign_chunks([(0, 0.16)], {'p': {'speed': 100 * KB, 'out': 0}}) == [(0, 'p')]            # exactly on time is accepted
assert assign_chunks([(0, 9)], {}) == [(0, 'server')] and assign_chunks([(0, 9)], {'p': {'speed': 0, 'out': 0}}) == [(0, 'server')]


def ref_assign(needed, peers):
    out = {k: v['out'] for k, v in peers.items()}
    plan = []
    for cid, dl in needed:
        ok = []
        for k, v in sorted(peers.items()):
            if v['speed'] > 0 and out[k] + CHUNK <= max(32 * KB, 2 * v['speed']) and (out[k] + CHUNK) / v['speed'] <= dl:
                ok.append(((out[k] + CHUNK) / v['speed'], k))
        if ok:
            k = min(ok)[1]
            out[k] += CHUNK
            plan.append((cid, k))
        else:
            plan.append((cid, 'server'))
    return plan


for seed in range(500):
    r = random.Random(seed)
    pr = {n: {'speed': r.choice([0, 5 * KB, 20 * KB, 100 * KB, 400 * KB]), 'out': r.choice([0, 0, 16 * KB, 64 * KB])} for n in r.sample('abcde', r.randint(0, 4))}
    needed = [(i, r.choice([0.05, 0.3, 1.0, 3.0, 10.0])) for i in range(r.randint(0, 12))]
    assert assign_chunks(needed, pr) == ref_assign(needed, pr), (seed, pr, needed)
    sent = {n: v['out'] for n, v in pr.items()}
    for (cid, dl), (c2, who) in zip(needed, assign_chunks(needed, pr)):
        if who != 'server':
            sent[who] += CHUNK
            assert sent[who] <= max(32 * KB, 2 * pr[who]['speed']) and sent[who] / pr[who]['speed'] <= dl + 1e-12    # the cap and the deadline hold

# ---- 3. the tracker: the 20 most recent peers per track, up to 10 online in a reply ------------------------------------------------------
t = Tracker()
for i in range(25):
    t.play('x', 'p%d' % i)
assert t.peers('x') == ['p%d' % i for i in range(24, 4, -1)] and len(t.peers('x')) == 20          # newest first, 5 oldest dropped
assert t.lookup('x', set('p%d' % i for i in range(25))) == ['p%d' % i for i in range(24, 14, -1)]   # at most 10
assert t.lookup('x', {'p3', 'p24', 'p20'}) == ['p24', 'p20'] and t.lookup('nope', {'p1'}) == []    # offline peers are not returned
t.play('x', 'p5')
assert t.peers('x')[0] == 'p5' and t.peers('x').count('p5') == 1 and len(t.peers('x')) == 20         # a replay moves the peer to the front
for seed in range(200):
    r = random.Random(seed)
    tr, ref = Tracker(), {}
    for _ in range(80):
        k, p = r.choice('ab'), 'p%d' % r.randint(0, 30)
        tr.play(k, p)
        ref[k] = [p] + [q for q in ref.get(k, []) if q != p]
        ref[k] = ref[k][:20]
        on = {'p%d' % r.randint(0, 30) for _ in range(r.randint(0, 20))}
        assert tr.lookup(k, on) == [q for q in ref[k] if q in on][:10]

# ---- 4. the client's LRU cache --------------------------------------------------------------------------------------------------------------
c = LruCache(100)
assert c.put('a', 40) and c.put('b', 40) and c.get('a') is True and c.put('c', 40)          # touching a makes b the oldest
assert not c.has('b') and c.has('a') and c.has('c') and c.used == 80
assert not c.put('huge', 101) and c.used == 80                                              # bigger than the cache: not stored, nothing evicted
assert c.put('a', 10) and c.used == 50                                                      # a re-put replaces, it does not add
assert c.get('zzz') is False
for seed in range(300):
    r = random.Random(seed)
    cap = r.randint(5, 60)
    lc, order = LruCache(cap), OrderedDict()
    for _ in range(120):
        k = r.choice('abcdefgh')
        if r.random() < 0.4:
            hit = lc.get(k)
            assert hit == (k in order)
            if hit:
                order.move_to_end(k)
        else:
            sz = r.randint(1, 25)
            stored = lc.put(k, sz)
            assert stored == (sz <= cap)
            if sz <= cap:
                order.pop(k, None)
                order[k] = sz
                while sum(order.values()) > cap:
                    order.popitem(last=False)
        assert lc.used == sum(order.values()) <= cap and set(lc.keys()) == set(order), seed

# ---- 5. seeking in a variable-bitrate file -------------------------------------------------------------------------------------------------------
# a quiet intro: 60 s at 100 kbps (12,500 B/s), then 180 s at 200 kbps (25,000 B/s)
pts, off = [], 0
for sec in range(240):
    pts.append((sec * 1000, off))
    off += 12_500 if sec < 60 else 25_000
total_bytes, total_ms = off, 240_000
assert total_bytes == 5_250_000
idx = SeekIndex(pts)
assert idx.offset_for(0) == 0 and idx.offset_for(999) == 0 and idx.offset_for(1000) == 12_500
assert idx.offset_for(60_000) == 750_000 and idx.offset_for(61_500) == 775_000 and idx.offset_for(10**9) == pts[-1][1]
assert idx.offset_for(-5) == 0
cbr = lambda t_ms: t_ms * total_bytes // total_ms
assert cbr(60_000) == 1_312_500 and cbr(60_000) - idx.offset_for(60_000) == 562_500
landing_ms = 60_000 + (cbr(60_000) - 750_000) * 1000 // 25_000                  # where the CBR guess actually lands
assert landing_ms == 82_500
for seed in range(300):
    r = random.Random(seed)
    n = r.randint(1, 40)
    p, tt, bb = [(0, 0)], 0, 0
    for _ in range(n):
        tt += r.randint(1, 3000)
        bb += r.randint(0, 9000)
        p.append((tt, bb))
    ix = SeekIndex(p)
    for _ in range(30):
        q = r.randint(-10, tt + 500)
        ref = 0
        for ms, by in p:
            if ms <= q:
                ref = by
        assert ix.offset_for(q) == ref, (seed, q)

# ---- 6. fractional keys for playlist order -----------------------------------------------------------------------------------------------------------
assert DIGITS == ''.join(sorted(DIGITS)) and len(DIGITS) == 62                       # string order must equal numeric order
val = lambda k: sum(Fraction(DIGITS.index(ch), 62 ** (i + 1)) for i, ch in enumerate(k))
valid = lambda k: bool(k) and not k.endswith('0')
first = between(None, None)
assert first == 'V' and valid(first)
for seed in range(300):
    r = random.Random(seed)
    keys = []
    for _ in range(150):
        pos = r.randint(0, len(keys))
        a = keys[pos - 1] if pos > 0 else None
        b = keys[pos] if pos < len(keys) else None
        k = between(a, b)
        assert valid(k) and (a is None or a < k) and (b is None or k < b), (seed, a, k, b)
        assert (a is None or val(a) < val(k)) and (b is None or val(k) < val(b))
        keys.insert(pos, k)
    assert keys == sorted(keys) and len(set(keys)) == len(keys)
for a, b in [('1', '2'), ('1V', '2'), ('z', None), ('1z', '2'), ('0V', 'V'), ('V', 'V1'), ('Vz', 'W'), ('', 'V'), ('1', '2V'), ('1V', '2V'), ('Uz', 'V1')]:
    k = between(a, b)
    assert valid(k) and (a or '') < k and (b is None or k < b), (a, b, k)
try:
    between('b', 'a')
    raise SystemExit('between must refuse a >= b')
except ValueError:
    pass
try:
    between('a', 'a')
    raise SystemExit('between must refuse a == b')
except ValueError:
    pass
# the hole: repeated insertion at the same spot grows the key about one character per six inserts
front, k = [], None
fk = 'V'
for _ in range(1000):
    fk = between(None, fk)
    assert valid(fk)
front_len = len(fk)
ek = 'V'
for _ in range(1000):
    ek = between(ek, None)
    assert valid(ek)
end_len = len(ek)
mk_a, mk_b = 'V', 'W'
for _ in range(1000):
    mk_b = between(mk_a, mk_b)                                       # always insert just after V
mid_len = len(mk_b)
FIG = (front_len, end_len, mid_len)

# ---- 7. wording the lesson must keep, and stale wordings it must not --------------------------------------------------------------------------------------
for stale in ('Spotify uses peer-to-peer today', 'Spotify today', 'Spotify still uses', 'Spotify serves', 'Spotify stores', 'the paper says Spotify uses a CDN'):
    assert stale not in src, stale
need('Sources', 'Last reviewed: 27 November 2026', 'Level:** extended', '(proposed; the curriculum data holds the final rating)')
need('not consulted', '2010', '265 ms', '8.8%', '35.8%', '55.4%', '39%', '88%', 'Ogg Vorbis', '16 kB', 'RFC 8216')
need('%d characters after 1,000 inserts at the front' % FIG[0], '%d at the end' % FIG[1], '%d just after one fixed key' % FIG[2])
assert 4.5 < 1000 / front_len < 6.5 and 4.5 < 1000 / end_len < 6.5          # the prose says one character per five or six inserts
need('five or six inserts')
need('82.5 seconds', '562,500')
for t in ('YouTube / Netflix Video Streaming', 'Caching Patterns and Consistent Hashing', 'Real-Time Collaborative Docs & Whiteboard'):
    assert t in src, t
print('sy62 code checks passed')
