"""Runs the python code blocks from data/new_lessons/sy41-machine-coding-lld.md against independent reference
models (scan-based spot choice, minute-by-minute fees, partition enumeration for debts, a copy-on-begin store)
and threaded tests of the stated concurrency rules."""
import re, sys, random, threading, itertools, copy
src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
ns = {}
for b in blocks:
    exec(b, ns)
Size, ParkingLot, LotFull, HourlyFee = ns['Size'], ns['ParkingLot'], ns['LotFull'], ns['HourlyFee']
split_equal, split_exact, split_percent = ns['split_equal'], ns['split_exact'], ns['split_percent']
Ledger, simplify, min_payments, KVStore = ns['Ledger'], ns['simplify'], ns['min_payments'], ns['KVStore']
random.seed(41)
sys.setswitchinterval(1e-6)          # switch threads often so races would show up

# ---------------- parking lot: assignment vs a full scan
FITS = {'motorcycle': {1, 2, 3}, 'car': {2, 3}, 'truck': {3}}
def ref_fee(rate, cap, grace, minutes):
    if minutes <= grace:
        return 0
    per_day = {}
    for m in range(minutes):                       # every started hour of every 24 h block, walked minute by minute
        per_day.setdefault(m // 1440, set()).add((m % 1440) // 60)
    total = 0
    for hours in per_day.values():
        c = len(hours) * rate
        total += c if cap is None else min(c, cap)
    return total

for trial in range(150):
    layout = {}
    for level in range(random.randint(1, 3)):
        for num in range(random.randint(1, 8)):
            layout[(level, num)] = random.choice(list(Size))
    rates = {'motorcycle': 50, 'car': 200, 'truck': 500}
    cap = random.choice([None, 1500, 6000])
    fee = HourlyFee(rates, grace=15, daily_cap=cap)
    lot = ParkingLot(layout, fee)
    free = set(layout)
    active = {}                                     # tid -> (spot, type, t0, plate)
    now, plate_no = 0, 0
    for _ in range(80):
        now += random.randint(0, 200)
        if active and random.random() < 0.4:
            tid = random.choice(list(active))
            spot, vt, t0, plate = active.pop(tid)
            minutes = now - t0
            got = lot.leave(tid, now)
            assert got == ref_fee(rates[vt], cap, 15, minutes), (vt, cap, minutes, got)
            free.add(spot)
            try:
                lot.leave(tid, now)
                raise AssertionError('reused ticket accepted')
            except KeyError:
                pass
        else:
            vt = random.choice(list(FITS))
            plate_no += 1
            plate = 'P%d' % plate_no
            cands = [s for s in free if layout[s].value in FITS[vt]]
            if not cands:
                try:
                    lot.park(plate, vt, now)
                    raise AssertionError('parked with no fitting spot')
                except LotFull:
                    continue
            want = min(cands, key=lambda s: (layout[s].value, s))
            tid, spot = lot.park(plate, vt, now)
            assert spot == want, (vt, spot, want)
            free.discard(spot)
            active[tid] = (spot, vt, now, plate)
            try:
                lot.park(plate, vt, now)
                raise AssertionError('same plate parked twice')
            except ValueError:
                pass

# fee corner cases and the worked example
f = HourlyFee({'car': 200}, grace=15, daily_cap=1500)
assert f.fee('car', 0, 15) == 0 and f.fee('car', 0, 16) == 200 and f.fee('car', 0, 60) == 200 and f.fee('car', 0, 61) == 400
assert f.fee('car', 0, 26 * 60 + 10) == 2100 == 1500 + 3 * 200
assert f.fee('car', 0, 49 * 60 + 1) == 3400 == 2 * 1500 + 2 * 200
assert HourlyFee({'car': 200}, daily_cap=6000).fee('car', 0, 24 * 60) == 4800      # cap above a day of rate
try:
    f.fee('car', 10, 5)
    raise AssertionError('negative stay accepted')
except ValueError:
    pass

# concurrency: 50 threads, 20 spots, exactly 20 tickets and no spot twice
for _ in range(5):
    layout = {(0, i): Size.COMPACT for i in range(20)}
    lot = ParkingLot(layout, f)
    barrier = threading.Barrier(50)
    got, full, glock = [], [0], threading.Lock()
    def worker(i):
        barrier.wait()
        try:
            r = lot.park('T%d' % i, 'car', 0)
            with glock:
                got.append(r)
        except LotFull:
            with glock:
                full[0] += 1
    ts = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(got) == 20 and full[0] == 30, (len(got), full[0])
    assert len({s for _, s in got}) == 20 and len({t for t, _ in got}) == 20

# concurrency under churn: 8 threads park and leave repeatedly; every ticket and spot must stay unique
for _ in range(3):
    layout = {(lv, i): random.choice(list(Size)) for lv in range(4) for i in range(100)}
    lot = ParkingLot(layout, HourlyFee({'motorcycle': 50, 'car': 200, 'truck': 500}))
    barrier = threading.Barrier(8)
    issued, errors, glock = [], [], threading.Lock()
    def churn(w):
        barrier.wait()
        mine = []
        try:
            for j in range(600):
                if mine and j % 3 == 2:
                    lot.leave(mine.pop(0), 100)
                else:
                    try:
                        tid, spot = lot.park('W%d-%d' % (w, j), random.choice(list(FITS)), 0)
                        mine.append(tid)
                        with glock:
                            issued.append(tid)
                    except LotFull:
                        pass
        except Exception as e:                    # a race shows up as a lost ticket or a corrupted heap
            with glock:
                errors.append(repr(e))
    ts = [threading.Thread(target=churn, args=(w,)) for w in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors, errors[:3]
    assert len(issued) == len(set(issued)), 'duplicate ticket ids'
    held = [v[0] for v in lot.tickets.values()]
    free_now = [s for h in lot.free.values() for s in h]
    assert len(held) == len(set(held)) and not set(held) & set(free_now)
    assert sorted(held + free_now) == sorted(layout), 'a spot was lost or duplicated'

# ---------------- splits
assert split_equal(1000, ['a', 'b', 'c']) == {'a': 334, 'b': 333, 'c': 333}
assert split_percent(1001, {'a': 33, 'b': 33, 'c': 34}) == {'a': 330, 'b': 330, 'c': 341}
for _ in range(3000):
    users = ['u%d' % i for i in range(random.randint(1, 7))]
    total = random.randint(0, 100000)
    eq = split_equal(total, users)
    assert sum(eq.values()) == total and max(eq.values()) - min(eq.values()) <= 1
    cuts = sorted(random.randint(0, 100) for _ in range(len(users) - 1))
    pct = dict(zip(users, [b - a for a, b in zip([0] + cuts, cuts + [100])]))
    sp = split_percent(total, pct)
    assert sum(sp.values()) == total
    for u in users:                                   # each share is the exact share rounded down or up
        exact = total * pct[u] / 100
        assert sp[u] - 1 < exact < sp[u] + 1 or sp[u] == exact, (u, sp[u], exact)
    # largest remainder: nobody who got the extra cent has a smaller fraction than someone who did not
    bumped = [u for u in users if sp[u] * 100 > total * pct[u]]
    others = [u for u in users if u not in bumped]
    if bumped and others:
        assert min((total * pct[u]) % 100 for u in bumped) >= max((total * pct[u]) % 100 for u in others)
for bad in (lambda: split_exact(10, {'a': 4, 'b': 5}), lambda: split_percent(10, {'a': 50, 'b': 49})):
    try:
        bad()
        raise AssertionError('bad split accepted')
    except ValueError:
        pass

# ---------------- debts: greedy validity and bound; DP vs partition enumeration
def partitions(items):
    if not items:
        yield []
        return
    first, rest = items[0], items[1:]
    for p in partitions(rest):
        for i in range(len(p)):
            yield p[:i] + [[first] + p[i]] + p[i + 1:]
        yield [[first]] + p

def brute_min(vals):
    vals = [v for v in vals if v]
    best = 0
    for p in partitions(list(range(len(vals)))):
        if all(sum(vals[i] for i in blk) == 0 for blk in p):
            best = max(best, len(p))
    return len(vals) - best

def apply(net, payments):
    out = dict(net)
    for frm, to, amt in payments:
        assert amt > 0
        out[frm] += amt
        out[to] -= amt
    return out

for _ in range(1500):
    n = random.randint(1, 7)
    ledger = Ledger()
    people = ['p%d' % i for i in range(n)]
    for _ in range(random.randint(0, 6)):
        payer = random.choice(people)
        group = random.sample(people, random.randint(1, n))
        total = random.randint(1, 60)
        ledger.add_expense(payer, total, split_equal(total, group))
    net = {p: ledger.net.get(p, 0) for p in people}
    assert sum(net.values()) == 0
    pays = simplify(net)
    assert all(v == 0 for v in apply(net, pays).values())
    nz = sum(1 for v in net.values() if v)
    assert len(pays) <= max(0, nz - 1)
    opt = min_payments(net)
    assert opt == brute_min(list(net.values())), (net, opt)
    assert opt <= len(pays)

example = {'Asha': -40, 'Ben': -30, 'Chen': 20, 'Dev': 20, 'Esha': 30}
assert len(simplify(example)) == 4 and min_payments(example) == 3 == brute_min(list(example.values()))
assert simplify(example)[0] == ('Asha', 'Esha', 30)
try:
    Ledger().add_expense('a', 10, {'a': 3, 'b': 3})
    raise AssertionError('bad expense accepted')
except ValueError:
    pass
lg = Ledger()
lg.add_expense('a', 90, split_equal(90, ['a', 'b', 'c']))
lg.record_payment('b', 'a', 30)
assert lg.net == {'a': 30, 'b': 0, 'c': -30}

# ---------------- key-value store vs a copy-on-begin reference
class Clock:
    def __init__(self):
        self.t = 0
    def __call__(self):
        return self.t

class RefStore:
    def __init__(self, clock):
        self.clock, self.d, self.snaps = clock, {}, []
    def live(self, k):
        e = self.d.get(k)
        return None if e is None or (e[1] is not None and e[1] <= self.clock()) else e
    def set(self, k, v, ttl=None):
        self.d[k] = (v, None if ttl is None else self.clock() + ttl)
    def get(self, k):
        e = self.live(k)
        return None if e is None else e[0]
    def delete(self, k):
        ex = self.live(k) is not None
        self.d.pop(k, None)
        return ex
    def incr(self, k, by=1):
        e = self.live(k)
        v = (0 if e is None else e[0]) + by
        self.d[k] = (v, None if e is None else e[1])
        return v
    def ttl(self, k):
        e = self.live(k)
        return None if e is None else (-1 if e[1] is None else e[1] - self.clock())
    def begin(self):
        self.snaps.append(copy.deepcopy(self.d))
    def rollback(self):
        self.d = self.snaps.pop()
    def commit(self):
        self.snaps.pop()

ops_run = 0
for trial in range(300):
    clk = Clock()
    db, ref = KVStore(clk), RefStore(clk)
    keys = ['k%d' % i for i in range(4)]
    for _ in range(120):
        r = random.random()
        k = random.choice(keys)
        if r < 0.2:
            ttl = random.choice([None, None, 1, 3, 7])
            v = random.randint(0, 9)
            db.set(k, v, ttl)
            ref.set(k, v, ttl)
        elif r < 0.35:
            assert db.get(k) == ref.get(k), (k, db.get(k), ref.get(k))
        elif r < 0.45:
            assert db.delete(k) == ref.delete(k)
        elif r < 0.55:
            assert db.incr(k) == ref.incr(k)
        elif r < 0.62:
            assert db.ttl(k) == ref.ttl(k)
        elif r < 0.72:
            db.begin()
            ref.begin()
        elif r < 0.80:
            if ref.snaps:
                db.rollback()
                ref.rollback()
            else:
                try:
                    db.rollback()
                    raise AssertionError('rollback without begin')
                except RuntimeError:
                    pass
        elif r < 0.87:
            if ref.snaps:
                db.commit()
                ref.commit()
        elif r < 0.93:
            clk.t += random.randint(0, 4)
        else:
            db.sweep(limit=random.choice([None, 1]))
        ops_run += 1
        for kk in keys:
            assert db.get(kk) == ref.get(kk), (kk, db.get(kk), ref.get(kk))
    clk.t += 100
    db.sweep()
    assert not db.data or all(e[1] is None for e in db.data.values()), 'sweep left expired keys'

# Redis-like TTL rules stated in the lesson
clk = Clock()
db = KVStore(clk)
db.set('a', 1, ttl=10)
db.incr('a')
assert db.ttl('a') == 10                       # incr keeps the TTL
db.set('a', 5)
assert db.ttl('a') == -1                       # plain set clears it
db.set('b', 1, ttl=5)
clk.t = 5
assert db.get('b') is None and db.ttl('b') is None
# nested commit then outer rollback restores the original
db = KVStore(clk)
db.set('x', 'orig')
db.begin(); db.set('x', 'outer'); db.begin(); db.set('x', 'inner'); db.commit()
assert db.get('x') == 'inner'
db.rollback()
assert db.get('x') == 'orig'

# concurrency: 8 threads x 2000 incr must sum exactly
for _ in range(3):
    db = KVStore(Clock())
    barrier = threading.Barrier(8)
    def inc():
        barrier.wait()
        for _ in range(2000):
            db.incr('n')
    ts = [threading.Thread(target=inc) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert db.get('n') == 16000, db.get('n')

print('sy41 code checks passed (%d store operations)' % ops_run)
