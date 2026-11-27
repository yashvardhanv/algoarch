"""Runs the python blocks of the sy68 distributed-lock-service lesson against an independent reference and a simulated
pause-then-resume client: session expiry boundaries, FIFO grants, the recipe's client under every kind of interleaving
(lost wakeups, a dead middle waiter, lost create replies), herd cost against closed forms, fencing tokens, lock-delay,
the conservative local lease, and the detection window. Figures the lesson prints from the simulation are asserted here."""
import re, sys, random, math, collections

src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
assert len(blocks) >= 4, 'expected the lesson code blocks'
ns = {}
for b in blocks:
    exec(b, ns)
LockService, LockClient, Store = ns['LockService'], ns['LockClient'], ns['Store']
pause_trace, counter_trace = ns['pause_trace'], ns['counter_trace']
delayed_packet_trace, local_deadline = ns['delayed_packet_trace'], ns['local_deadline']


def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the checked figure: %r' % p


# ---- 1. sessions, expiry boundary, FIFO grants -------------------------------------------------------------------------
svc = LockService(10)
a, b = svc.open_session(0), svc.open_session(0)
assert svc.heartbeat(a, 10) is True                    # exactly one timeout of silence is still alive ("more than" expires)
assert svc.heartbeat(b, 10.001) is False               # a hair over is not
assert svc.heartbeat(b, 10.002) is False and svc.enqueue(b, 10.002, 'x') is None      # and it stays dead
assert svc.heartbeat(a, 20) is True and svc.heartbeat(a, 30.5) is False

svc = LockService(10)
s1, s2, s3 = (svc.open_session(0) for _ in range(3))
n1, n2, n3 = svc.enqueue(s1, 0, 'g1'), svc.enqueue(s2, 1, 'g2'), svc.enqueue(s3, 2, 'g3')
assert (n1, n2, n3) == (1, 2, 3) and svc.holder(3) == 1
assert svc.release(s2, n1, 3) is False and svc.holder(3) == 1          # only the owner can release
assert svc.release(s1, n1, 4) is True and svc.holder(4) == 2           # next in line
assert svc.release(s1, n1, 4) is False                                  # twice is a no-op
assert svc.enqueue(s1, 5, 'g1b') == 4                                   # sequence numbers are never reused
assert svc.enqueue(s2, 5, 'g2') == n2 and len(svc.nodes) == 3           # same guid: the retry finds its own node
assert svc.enqueue(s2, 5, 'g2') == n2 and len(svc.nodes) == 3
assert svc.enqueue(s2, 5, 'g2-other') == 5 and len(svc.nodes) == 4      # a different guid is a different request
svc.heartbeat(s1, 12); svc.heartbeat(s3, 12)
assert svc.holder(12) == 2                                              # s2 was last heard at 5, alive until 15
svc.heartbeat(s1, 15.5); svc.heartbeat(s3, 15.5)
assert svc.holder(15.5) == 3                                            # s2 silent for more than 10: its nodes (2 and 5) are gone
assert 2 not in svc.nodes and 5 not in svc.nodes
assert ('expired', 15, s2) in svc.events

# lock-delay applies when the HOLDER is lost, not when a waiter is, and not on a clean release
svc = LockService(10, lock_delay=5)
h, w = svc.open_session(0), svc.open_session(0)
nh, nw = svc.enqueue(h, 0, 'h'), svc.enqueue(w, 0, 'w')
svc.heartbeat(w, 9)
assert svc.holder(10.5) is None and svc.holder(14.0) is None                  # held back until deadline + delay
svc.heartbeat(w, 14.9)
assert svc.holder(14.9) is None
svc.heartbeat(w, 15.2)
assert svc.holder(15.2) == nw
svc = LockService(10, lock_delay=5)
h, w = svc.open_session(0), svc.open_session(0)
nh, nw = svc.enqueue(h, 0, 'h'), svc.enqueue(w, 0, 'w')
svc.heartbeat(h, 9)
assert svc.holder(10.5) == nh and svc.free_after == 0.0                 # the waiter timing out costs nothing
assert svc.release(h, nh, 11) is True and svc.holder(11) is None and svc.free_after == 0.0   # the dead waiter's node is gone, no delay was started
svc = LockService(10, lock_delay=5)
h, w = svc.open_session(0), svc.open_session(0)
nh, nw = svc.enqueue(h, 0, 'h'), svc.enqueue(w, 0, 'w')
svc.release(h, nh, 1)
assert svc.holder(1) == nw                                              # clean release: immediately available

# lock-delay must not be extended by a waiter that never held the lock (review M2): H holds and expires (delay until 15),
# W dies at 11.01 while the lock is still withheld, X keeps heartbeating and must get the lock at 15, not 16
svc = LockService(10, lock_delay=5)
h, w, x = svc.open_session(0), svc.open_session(1), svc.open_session(0)
nh, nw, nx = svc.enqueue(h, 0, 'h'), svc.enqueue(w, 1, 'w'), svc.enqueue(x, 0, 'x')
svc.heartbeat(x, 5); svc.heartbeat(x, 10)
svc.holder(10.5)
assert svc.free_after == 15
svc.heartbeat(x, 11.5)
svc.holder(11.5)
assert nw not in svc.nodes and svc.free_after == 15, svc.free_after
svc.heartbeat(x, 14)
assert svc.holder(14.9) is None and svc.holder(15) == nx

# ---- 2. against an independent naive reference ---------------------------------------------------------------------
class Ref:
    """Naive reference: a FIFO list and a table of last-touch times; aliveness recomputed from scratch on every question."""
    def __init__(self, ttl):
        self.ttl, self.touched, self.q, self.seq, self.sid = ttl, {}, [], 0, 0
    def alive(self, sid, now):
        return sid in self.touched and now - self.touched[sid] <= self.ttl
    def open(self, now):
        self.sid += 1; self.touched[self.sid] = now; return self.sid
    def hb(self, sid, now):
        if not self.alive(sid, now): return False
        self.touched[sid] = now; return True
    def enq(self, sid, now, guid):
        if not self.alive(sid, now): return None
        self.touched[sid] = now
        for s, o, g in self.q:
            if o == sid and g == guid: return s
        self.seq += 1; self.q.append((self.seq, sid, guid)); return self.seq
    def rel(self, sid, seq, now):
        if not self.alive(sid, now): return False
        self.touched[sid] = now
        for e in self.q:
            if e[0] == seq and e[1] == sid:
                self.q.remove(e); return True
        return False
    def holder(self, now):
        for s, o, g in self.q:
            if self.alive(o, now): return s
        return None
    def kids(self, now):
        return [s for s, o, g in self.q if self.alive(o, now)]

for seed in range(300):
    r = random.Random(seed)
    ttl = r.choice([3, 5, 8])
    svc, ref, now, sids = LockService(ttl), Ref(ttl), 0.0, []
    for _ in range(80):
        now += r.choice([0, 0.5, 1, 2, 4, 9])
        op = r.choice(['open', 'enq', 'enq', 'rel', 'hb', 'hb', 'kids'])
        if op == 'open' or not sids:
            x, y = svc.open_session(now), ref.open(now); assert x == y; sids.append(x); continue
        sid = r.choice(sids)
        if op == 'enq':
            g = 'g%d' % r.randint(0, 3)
            assert svc.enqueue(sid, now, g) == ref.enq(sid, now, g), (seed, op)
        elif op == 'rel':
            seq = r.randint(1, max(1, ref.seq))
            assert svc.release(sid, seq, now) == ref.rel(sid, seq, now), (seed, op)
        elif op == 'hb':
            assert svc.heartbeat(sid, now) == ref.hb(sid, now), (seed, op)
        else:
            got = svc.children(sid, now)
            if ref.alive(sid, now):
                ref.touched[sid] = now
                assert got == ref.kids(now), (seed, got, ref.kids(now))
            else:
                assert got is None
        assert svc.holder(now) == ref.holder(now), (seed, now)

# more than ten live nodes: grants and listings follow the numeric sequence, never the string order (review I6)
svc = LockService(1000)
ids = [svc.open_session(0) for _ in range(14)]
seqs = [svc.enqueue(i, 0, 'g') for i in ids]
for k in range(8):
    assert svc.release(ids[k], seqs[k], 1)
assert svc.holder(1) == 9
assert svc.release(ids[8], seqs[8], 1) and svc.holder(1) == 10
assert svc.children(ids[13], 1) == [10, 11, 12, 13, 14]
for seed in range(100):                                  # reference runs that keep dozens of nodes alive at once
    r = random.Random(1000 + seed)
    svc, ref, now, sids = LockService(1000), Ref(1000), 0.0, []
    for _ in range(70):
        now += r.choice([0, 0.5, 1])
        if not sids or r.random() < 0.15:
            a, b = svc.open_session(now), ref.open(now); assert a == b; sids.append(a); continue
        sid = r.choice(sids)
        if r.random() < 0.7:
            g = 'g%d' % r.randint(0, 40)
            assert svc.enqueue(sid, now, g) == ref.enq(sid, now, g)
        else:
            seq = r.randint(1, max(1, ref.seq))
            assert svc.release(sid, seq, now) == ref.rel(sid, seq, now)
        assert svc.holder(now) == ref.holder(now), (seed, now)
        assert svc.children(sid, now) == (ref.kids(now) if ref.alive(sid, now) else None) or not ref.alive(sid, now)

# ---- 3. the recipe's client: interleavings, lost wakeups, a dead middle waiter ----------------------------------------
svc = LockService(1000)
ids = [svc.open_session(0) for _ in range(3)]
cl = [LockClient(svc, ids[i], 'g%d' % i) for i in range(3)]
for c in cl:
    while c.state not in ('held', 'wait'):
        c.step(0)
assert [c.state for c in cl] == ['held', 'wait', 'wait']
assert [c.pred for c in cl] == [None, 1, 2]                              # each waiter watches the node just below it
assert cl[0].release(0) is True and [c.state for c in cl] == ['done', 'list', 'wait']       # exactly one wake-up
cl[1].step(0)
assert cl[1].state == 'held' and cl[2].state == 'wait'

# lost wakeup: the holder releases between the waiter's listing and its watch call
svc = LockService(1000)
p, q = svc.open_session(0), svc.open_session(0)
hc, wc = LockClient(svc, p, 'p'), LockClient(svc, q, 'q')
while hc.state != 'held': hc.step(0)
for _ in range(2): wc.step(0)                                            # new -> list -> watch (pred = holder)
assert wc.state == 'watch' and wc.pred == hc.seq
hc.release(0)                                                            # the watched node is gone before the watch is set
wc.step(0)
assert wc.state == 'list', 'a watch on a node that is already gone must send the client back to look again'
wc.step(0)
assert wc.state == 'held'

# a waiter in the middle dies: only its successor wakes, and it does not become the holder
svc = LockService(10)
ids = [svc.open_session(0) for _ in range(3)]
cl = [LockClient(svc, ids[i], 'g%d' % i) for i in range(3)]
for c in cl:
    while c.state not in ('held', 'wait'):
        c.step(0)
for t in (3, 6, 9):                                                      # A and C keep heartbeating, B goes silent after t=0
    cl[0].heartbeat(t); cl[2].heartbeat(t)
svc.holder(11)                                                           # the service notices B is gone
assert ('delete', 2, 1) in svc.events and cl[2].state == 'list'
cl[2].heartbeat(11); cl[0].heartbeat(11)
cl[2].step(11)
assert cl[2].state == 'watch' and cl[2].pred == 1                        # it now watches the holder, and is NOT held
cl[2].step(11)
assert cl[2].state == 'wait'
assert cl[0].release(11) and cl[2].state == 'list'
cl[2].step(11)
assert cl[2].state == 'held'

# an operator breaks the lock by deleting the holder's node (the recipes page says locks can be broken): a client that LISTS again
# finds its node gone and never treats itself as the holder. (A client already in 'held' has no watch on its own node and does
# not learn; the model does not give it one.)
svc = LockService(1000)
sid = svc.open_session(0)
c = LockClient(svc, sid, 'g')
while c.state != 'held':
    c.step(0)
assert svc.release(sid, c.seq, 1)                                        # the node disappears under a live session
c.state = 'list'
c.step(2)
assert c.state == 'lost' and svc.holder(2) is None

# a lost create reply: the retry reuses the node (guid); without it the client waits behind itself forever
svc = LockService(1000)
s = svc.open_session(0)
first = svc.enqueue(s, 0, 'same')                                        # the reply is lost; the client retries
again = svc.enqueue(s, 1, 'same')
assert first == again and len(svc.nodes) == 1
svc2 = LockService(1000)
s = svc2.open_session(0)
n_a = svc2.enqueue(s, 0, 'first-try'); n_b = svc2.enqueue(s, 1, 'retry-with-a-new-name')     # what a missing guid does
assert svc2.holder(1) == n_a                                             # the lock is held by a node its owner does not know about
c_dup = LockClient(svc2, s, 'retry-with-a-new-name')
c_dup.seq = n_b; c_dup.state = 'list'; c_dup.step(1)
assert c_dup.state == 'watch' and c_dup.pred == n_a                      # it watches its own first node: stuck while the session lives


class Actor:
    def __init__(self, name, rng):
        self.name, self.start = name, rng.uniform(0, 8)
        self.crash = rng.uniform(5, 60) if rng.random() < 0.2 else None
        self.frozen_until, self.c, self.last_hb = 0.0, None, 0.0
        self.phase, self.read, self.write_at = 'acq', None, 0.0


def fuzz(seed, mode, n=5, T=150.0, ttl=6.0, dt=0.5, client_cls=LockClient):
    """n clients each take the lock once and do read-modify-write on a counter; clients freeze at random (a GC pause,
    a stalled VM) or die. mode: naive store / fenced with a claim before the read / fenced with a claim just before the write."""
    rng = random.Random(seed)
    svc, store = LockService(ttl), Store(fenced=(mode != 'naive'))
    acts = [Actor(i, rng) for i in range(n)]
    acked, overlap, last_holder, t = 0, False, 0, 0.0
    while t <= T:
        rng.shuffle(acts)
        for a in acts:
            if t < a.start or (a.crash is not None and t >= a.crash) or t < a.frozen_until:
                continue
            if a.c is None:
                a.c = client_cls(svc, svc.open_session(t), 'g%d' % a.name); a.last_hb = t
            c = a.c
            if a.phase == 'write' and t >= a.write_at:                   # the paused client resumes and writes at once
                if mode == 'late':
                    store.claim(c.seq)
                acked += 1 if store.write(c.seq, a.read + 1) else 0
                a.phase = 'finish'
            if c.state != 'done' and t - a.last_hb >= ttl / 3:
                c.heartbeat(t); a.last_hb = t
            if a.phase == 'finish':
                c.release(t); a.phase = 'done'
            elif c.state in ('new', 'list', 'watch'):
                c.step(t)
            if c.state == 'held' and a.phase == 'acq':
                if mode == 'first':
                    store.claim(c.seq)
                a.read = store.read()
                gap = rng.choice([0.0, 0.0, 0.5, rng.uniform(0, 3 * ttl)])  # the pause between checking the lease and using it
                a.write_at, a.phase = t + gap, 'write'
                if gap > 0:
                    a.frozen_until = t + gap
            if rng.random() < 0.02 and a.phase != 'done':
                a.frozen_until = max(a.frozen_until, t + rng.uniform(0, 2 * ttl))
        h = svc.holder(t)
        believers = [a for a in acts if a.c is not None and a.c.state == 'held' and a.phase != 'done'
                     and not (a.crash is not None and t >= a.crash)]        # a crashed client believes nothing
        live = [a for a in believers if a.c.sid in svc.last_heard]
        assert len(live) <= 1 and (not live or live[0].c.seq == h), (seed, t)      # a live session believing it holds IS the holder
        overlap = overlap or len(believers) >= 2
        if h is not None:
            assert h >= last_holder, (seed, t, h, last_holder)         # tokens of successive holders never go backwards
            last_holder = h
        t += dt
    for a in acts:
        if a.crash is None or a.crash > T:
            assert a.c.state in ('done', 'lost'), (seed, a.name, a.c.state, 'a live client is stuck')
    if client_cls is LockClient:
        assert all(e[2] <= 1 for e in svc.events if e[0] == 'delete'), (seed, 'a release woke more than one client')
    return store.value, acked, overlap


N_SEEDS = 200
viol = {'naive': 0, 'late': 0, 'first': 0}
overlap_runs, stale_accepted = 0, 0
for seed in range(N_SEEDS):
    for mode in ('naive', 'late', 'first'):
        value, acked, overlap = fuzz(seed, mode)
        viol[mode] += value != acked
        if mode == 'naive':
            overlap_runs += overlap
assert viol['first'] == 0, 'fenced store with a claim before the read must never lose an acknowledged update'
assert viol['naive'] > 0 and viol['late'] > 0 and overlap_runs > 0, (viol, overlap_runs)
big = {'naive': 0, 'late': 0, 'first': 0}
for seed in range(60):
    for mode in ('naive', 'late', 'first'):
        value, acked, _ = fuzz(5000 + seed, mode, n=14, T=260.0)
        big[mode] += value != acked
assert big['first'] == 0 and big['naive'] > 0, big       # fourteen clients: tokens above 9 take part
print('fuzz', N_SEEDS, 'seeds:', viol, 'runs with two clients believing they hold the lock:', overlap_runs)
need(*['%d of %d runs' % (x, N_SEEDS) for x in (viol['naive'], viol['late'], viol['first'], overlap_runs)])
assert src.count('%d of %d runs' % (overlap_runs, N_SEEDS)) >= 2, 'the belief-overlap figure appears in the text and in the failure table'
need('claim before you read')

# ---- 4. herd cost against closed forms -----------------------------------------------------------------------------------
class HerdClient(LockClient):
    def _target(self, kids):
        return kids[0]                                                   # the simple recipe: everyone watches the holder


def drain(cls, n):
    svc = LockService(1e9)
    cl = []
    for i in range(n):
        c = cls(svc, svc.open_session(0.0), 'g%d' % i)
        while c.state not in ('held', 'wait'):
            c.step(0.0)
        cl.append(c)
    arrival = svc.names_listed
    svc.events.clear()
    for k in range(n):
        assert cl[k].state == 'held', (cls, k)
        cl[k].release(0.0)
        moved = True
        while moved:
            moved = False
            for c in cl:
                if c.state in ('list', 'watch'):
                    c.step(0.0); moved = True
    return arrival, svc.names_listed - arrival, [e[2] for e in svc.events if e[0] == 'delete']

for n in (2, 5, 50):
    arr_c, cost_c, wakes_c = drain(LockClient, n)
    arr_h, cost_h, wakes_h = drain(HerdClient, n)
    assert arr_c == arr_h == n * (n + 1) // 2
    assert cost_c == n * (n - 1) // 2 and cost_h == (n - 1) * n * (2 * n - 1) // 6, (n, cost_c, cost_h)
    assert wakes_c == [1] * (n - 1) + [0] and wakes_h == list(range(n - 1, -1, -1)), (wakes_c, wakes_h)
assert drain(LockClient, 50)[1] == 1225 and drain(HerdClient, 50)[1] == 40425
need('1,225 names', '40,425 names')

# ---- 5. fencing: the pause trace, the hole, the counter -------------------------------------------------------------------
assert pause_trace(False) == ('a2', True, True)        # naive store: the stale write wins, and A's own lease check had passed
assert pause_trace(True) == ('b1', False, True)        # fenced store: the same stale write is refused
st = Store(True)
assert st.claim(3) and st.write(3, 'x') and st.write(3, 'y') and st.value == 'y'       # the holder may write many times
assert not st.write(2, 'z') and st.value == 'y' and not st.claim(1) and st.claim(4) and not st.write(3, 'w')
assert st.write(5, 'v') and st.accepted == [(3, 'x'), (3, 'y'), (5, 'v')]
nv = Store(False)
assert nv.write(5, 'a') and nv.write(1, 'b') and nv.value == 'b'                         # the naive store believes anyone
assert counter_trace('read_then_claim') == (6, True)   # two acknowledged increments, one visible: a lost update
assert counter_trace('slip_then_claim') == (7, True)   # A's write slipped in before B claimed, but B read after claiming: nothing lost
assert counter_trace('claim_then_read') == (6, False)  # A was refused, B's increment stands: nothing lost, nothing falsely acknowledged
for order in ('read_then_claim', 'slip_then_claim', 'claim_then_read'):
    value, a_ok = counter_trace(order)
    acknowledged = 1 + (1 if a_ok else 0)              # B's increment always succeeds; A's only if its write was accepted
    consistent = value == 5 + acknowledged
    assert consistent == (order != 'read_then_claim'), order        # only the read-before-claim order loses an acknowledged update

st = Store(True)
assert st.claim(9) and st.claim(10) and not st.write(9, 'stale') and st.write(10, 'ok') and st.value == 'ok'   # numeric, not string, order
assert st.claim(100) and not st.claim(99) and not st.write(20, 'x')
st = Store(True)                                       # a rotated lock directory restarts the sequence: pair it with an epoch
assert st.claim((1, 2_000_000_000)) and st.claim((2, 1)) and not st.write((1, 5), 'stale') and st.write((2, 1), 'new')
assert st.value == 'new' and not st.claim((1, 2_000_000_000))
bare = Store(True)
assert bare.claim(2_000_000_000) and not bare.claim(1)  # a bare restart at 1 is refused for ever: why rotation needs an epoch

# ---- 6. lock-delay: it narrows the window for a delayed packet, it cannot close it ----------------------------------------
# A pings at 3 and 6, sends its last write at 9 and dies: expiry at 16 (7 s after death, inside the 6.67 to 10 window)
assert delayed_packet_trace(0, 7.0) == (16.5, True)      # B starts at 16.5; the packet landed at 16
assert delayed_packet_trace(0, 8.0) == (16.5, False)     # a packet that lands at 17 arrives after B has read: stale write wins
assert delayed_packet_trace(60, 30.0) == (76.0, True)    # lock-delay 60: B waits until 76, the packet landed at 39
assert delayed_packet_trace(60, 100.0) == (76.0, False)  # a packet delayed longer than the delay still gets through
assert delayed_packet_trace(5, 11.0) == (21.0, True) and delayed_packet_trace(5, 13.0)[1] is False

# ---- 7. the client's local lease: safe, and also usable under a parked KeepAlive -----------------------------------------
for seed in range(3000):
    r = random.Random(seed)
    drift = r.choice([0.0, 0.001, 0.01, 0.1])
    lease, flight_bound = r.uniform(1, 20), r.choice([0.0, 0.2, 1.0, 3.0])
    reply_sent = r.uniform(0, 100)                       # when the master sends the reply that grants `lease` (client time)
    flight = r.uniform(0, flight_bound)                  # how long the reply was in flight
    k = r.uniform(1 / (1 + drift), 1 + drift)            # server seconds per client second
    expiry = reply_sent + lease / k
    assert local_deadline(reply_sent + flight, lease, drift, flight_bound) <= expiry + 1e-9, seed
assert abs(local_deadline(10.0, 12.0, 0.1, 0.5) - (10.0 - 0.5 + 12.0 / 1.1)) < 1e-12
assert abs(local_deadline(10.0, 12.0, 0.1, 0.5) - (10.0 - 0.5 + 12.0 / 1.1)) < 1e-12 and local_deadline(0, 12, 0, 0) == 12
# the extreme case is tight: the longest flight and the fastest allowed server clock land exactly on the bound
assert abs((0.5 + 0.0 - 0.5 + 12 / (1 + 0.1)) - local_deadline(0.5, 12, 0.1, 0.5)) < 1e-12


def jeopardy_share(rule, lease=12.0, cadence=7.0, flight=0.5, drift=0.01, rounds=200):
    """The master parks each KeepAlive and replies every `cadence` seconds (the Chubby paper's 7 s with a 12 s lease); the client
    sends the next request on receiving a reply. Share of time the client's local lease has run out before the next reply."""
    recv = [cadence * i + flight for i in range(rounds + 2)]
    bad = 0.0
    for i in range(1, rounds + 1):
        bad += max(0.0, recv[i + 1] - rule(recv[i], recv[i - 1], lease, drift, flight))
    return bad / (recv[rounds] - recv[1])

new_rule = lambda received, sent, lease, drift, flight: local_deadline(received, lease, drift, flight)
send_time_rule = lambda received, sent, lease, drift, flight: sent + lease / (1 + drift)      # counted from the send time
assert jeopardy_share(new_rule) == 0.0, jeopardy_share(new_rule)
assert jeopardy_share(send_time_rule) > 0.25, jeopardy_share(send_time_rule)         # about 30%: safe but useless with parked calls
assert jeopardy_share(new_rule, flight=6.0) > 0                                      # a flight bound near the cadence also starves it

# ---- 8. how long a dead holder keeps the lock: between 2/3 of the timeout and the whole timeout -----------------------------
ttl = 12.0
lo, hi = float('inf'), 0.0
for step in range(0, 400):
    crash = 20 + step * 0.01                             # crash phases across one heartbeat period (ttl / 3 = 4)
    svc = LockService(ttl)
    h = svc.open_session(0.0); svc.enqueue(h, 0.0, 'h')
    t = 0.0
    while t + ttl / 3 <= crash:                          # the client pings every ttl/3 until it dies
        t += ttl / 3; assert svc.heartbeat(h, t)
    svc.holder(crash + 2 * ttl)
    deadline = [e[1] for e in svc.events if e[0] == 'expired'][0]
    lo, hi = min(lo, deadline - crash), max(hi, deadline - crash)
assert 2 * ttl / 3 < lo < 2 * ttl / 3 + 0.05 and ttl - 0.05 < hi <= ttl, (lo, hi)      # freed between 2s/3 (exclusive) and s after the crash

# ---- 9. wording the lesson must keep, and stale wordings it must not --------------------------------------------------------
for stale in ('safe without a fencing token', 'no two clients can ever', 'Redlock is safe', 'ZooKeeper is a lock service',
              'Chubby-style local lease', '294 years at the coarse-grained 0.23', 'sessions drop above', 'rotate to a new lock directory long before',
              'The herd is quadratic', '294 years for one lock', 'inside the 930 to 1,860 that', 'checks against Chubby or against the most recent one it has seen. The second form is `Store`'):
    assert stale not in src, stale
need('Sources', 'Last reviewed: 27 November 2026', 'Level:** extended', '(proposed; the curriculum data holds the final rating)')
need('not consulted', '45 s against 30 s', 'Flash Sale & Ticket Reservation (Ticketmaster)', 'Scaling Patterns II: Large Blobs, Long-Running Tasks and Real-Time Updates')
need('numeric sequence', 'epoch')
after = [l for l in src.splitlines() if l.startswith('> **Study time')][0]
assert 'Flash Sale & Ticket Reservation (Ticketmaster)' in after and 'Scaling Patterns II' in after, 'link the lessons that teach fencing'
print('sy68 code checks passed')
