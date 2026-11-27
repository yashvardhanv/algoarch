"""Runs the python blocks of the sy58 hotel and flight booking lesson (real SQL in SQLite, an overbooking rule, availability
bitmaps and a reserve-charge-confirm flow with crash injection) against independent references: a list-based booking model
under random operation sequences, a night-by-night loop, an exact binomial built by convolution and a Monte Carlo run,
a 12-thread test on one database file, and every crash point with and without retries. Figures the lesson prints from
these runs are asserted against the text."""
import re, sys, random, sqlite3, threading, tempfile, os, shutil, math

src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
assert len(blocks) >= 4, 'expected the lesson code blocks'
ns = {}
for b in blocks:
    exec(b, ns)
SCHEMA, reserve, confirm, cancel, rooms_left = ns['SCHEMA'], ns['reserve'], ns['confirm'], ns['cancel'], ns['rooms_left']
IdempotencyMismatch = ns['IdempotencyMismatch']
overflow_prob, best_limit, expected_profit = ns['overflow_prob'], ns['best_limit'], ns['expected_profit']
night_mask, is_free, take = ns['night_mask'], ns['is_free'], ns['take']
Psp, Crash, book, reconcile, expire = ns['Psp'], ns['Crash'], ns['book'], ns['reconcile'], ns['expire']


def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the checked figure: %r' % p


def forbid_claims(subject, verbs):
    """no un-negated sentence may have the company as subject with one of the claim verbs"""
    for sentence in re.split(r"(?<=[.!?])\s+|\n", src.split('## Further reading')[0]):
        if re.search(subject, sentence) and re.search(verbs, sentence) and not re.search(r"\b(not|no|nor|never|without|neither|none)\b|n't", sentence, re.I):
            raise AssertionError('unsourced claim about a company: %r' % sentence[:160])


def forbid(*phrases):
    for p in phrases:
        assert p not in src, 'lesson text still contains stale wording: %r' % p


def new_db(path=':memory:', inventory=None):
    conn = sqlite3.connect(path, timeout=60, isolation_level=None, check_same_thread=False)
    conn.executescript(SCHEMA)
    for rtype, nights, total in (inventory or []):
        conn.executemany('INSERT INTO inv (rtype, night, total) VALUES (?, ?, ?)', [(rtype, n, total) for n in range(nights)])
    return conn


# ---- 1. the booking table against a list-based model, random operation sequences ------------------------------------------------
class Ref:
    """Every booking in a list; occupancy per night is recomputed by scanning. Spec: reserve first expires pending
    reservations whose time has run out, then admits the stay only if every night has room."""
    def __init__(self, totals):
        self.totals, self.b = totals, []                      # totals[(rtype, night)] = rooms
    def occupied(self, rtype, night):
        return sum(x['rooms'] for x in self.b if x['rtype'] == rtype and x['in'] <= night < x['out'] and x['state'] in ('PENDING', 'CONFIRMED'))
    def reserve(self, idem, guest, rtype, d_in, d_out, rooms, now, ttl):
        for x in self.b:
            if x['idem'] == idem:
                if (x['guest'], x['rtype'], x['in'], x['out'], x['rooms']) != (guest, rtype, d_in, d_out, rooms):
                    return 'MISMATCH'
                return x['id']
        for x in self.b:
            if x['state'] == 'PENDING' and x['exp'] <= now:
                x['state'] = 'EXPIRED'
        for n in range(d_in, d_out):
            if (rtype, n) not in self.totals or self.occupied(rtype, n) + rooms > self.totals[(rtype, n)]:
                return None
        bid = len(self.b) + 1
        self.b.append(dict(id=bid, idem=idem, guest=guest, rtype=rtype, out=d_out, rooms=rooms, state='PENDING', exp=now + ttl, **{'in': d_in}))
        return bid
    def confirm(self, bid, now):
        x = next((y for y in self.b if y['id'] == bid), None)
        if x is None:
            return False
        if x['state'] == 'PENDING' and x['exp'] > now:
            x['state'] = 'CONFIRMED'
        return x['state'] == 'CONFIRMED'
    def cancel(self, bid):
        x = next((y for y in self.b if y['id'] == bid), None)
        if x is None or x['state'] not in ('PENDING', 'CONFIRMED'):
            return False
        x['state'] = 'CANCELLED'
        return True


def sold_table(conn):
    return {(r, n): s for r, n, s in conn.execute('SELECT rtype, night, sold FROM inv')}


rng = random.Random(58)
ops = 0
for seq in range(400):
    types = ['A', 'B']
    nights = rng.randint(3, 20)
    totals = {(t, n): rng.randint(1, 4) for t in types for n in range(nights)}
    conn = new_db()
    for (t, n), tot in totals.items():
        conn.execute('INSERT INTO inv (rtype, night, total) VALUES (?, ?, ?)', (t, n, tot))
    ref, now, used = Ref(totals), 0, []
    for step in range(rng.randint(10, 45)):
        k = rng.random()
        if k < 0.55:
            if used and rng.random() < 0.15:                            # a retry: same key, same or changed request
                idem, args = rng.choice(used)
                if rng.random() < 0.5:
                    args = (args[0], args[1], args[2], args[3] + 1, args[4])
            else:
                idem = 'k%d' % len(used)
                d_in = rng.randint(0, nights + 2)
                args = ('g%d' % rng.randint(0, 3), rng.choice(types), d_in, d_in + rng.randint(1, 6), rng.randint(1, 3))
                used.append((idem, args))
            ttl = rng.choice([3, 10, 50])
            exp = ref.reserve(idem, *args, now, ttl)
            if exp == 'MISMATCH':
                try:
                    reserve(conn, idem, *args, now, ttl)
                    raise AssertionError('same idempotency key with a different request must be refused')
                except IdempotencyMismatch:
                    pass
            else:
                assert reserve(conn, idem, *args, now, ttl) == exp, (seq, step)
        elif k < 0.75:
            bid = rng.randint(1, len(ref.b) + 1)
            assert confirm(conn, bid, now) == ref.confirm(bid, now), (seq, step)
        elif k < 0.88:
            bid = rng.randint(1, len(ref.b) + 1)
            assert cancel(conn, bid) == ref.cancel(bid), (seq, step)
        else:
            now += rng.choice([1, 4, 12])
        ops += 1
        # after EVERY operation: the counters equal what a scan of the bookings gives, nothing is oversold, states agree
        got = sold_table(conn)
        for (t, n), tot in totals.items():
            occ = sum(x['rooms'] for x in ref.b if x['rtype'] == t and x['in'] <= n < x['out'] and x['state'] in ('PENDING', 'CONFIRMED'))
            assert got[(t, n)] == occ <= tot, (seq, step, t, n, got[(t, n)], occ, tot)
        st = {i: s for i, s in conn.execute('SELECT id, state FROM bookings')}
        assert st == {x['id']: x['state'] for x in ref.b}, (seq, step)
    conn.close()
assert ops > 8000

# boundaries: back-to-back stays fit, overlapping ones do not, zero nights is refused, a night with no inventory is full
conn = new_db(inventory=[('U', 10, 1)])
assert reserve(conn, 'a', 'g', 'U', 1, 3, 1, 0, 100) is not None                  # nights 1 and 2
assert reserve(conn, 'b', 'g', 'U', 3, 5, 1, 0, 100) is not None                  # check-in on the day the last guest leaves
assert reserve(conn, 'c', 'g', 'U', 2, 4, 1, 0, 100) is None                      # overlaps night 2 and night 3
assert reserve(conn, 'd', 'g', 'U', 0, 1, 1, 0, 100) is not None                  # a one-night stay before: fits
assert reserve(conn, 'e', 'g', 'U', 8, 12, 1, 0, 100) is None                     # runs past the inventory window
assert sold_table(conn)[('U', 8)] == 0 and sold_table(conn)[('U', 9)] == 0        # ... and left nothing half-booked
for bad in ((3, 3, 1), (4, 3, 1), (1, 2, 0)):
    try:
        reserve(conn, 'z', 'g', 'U', bad[0], bad[1], bad[2], 0, 100)
        raise AssertionError('invalid stay accepted')
    except ValueError:
        pass
assert conn.execute('SELECT COUNT(*) FROM bookings').fetchone()[0] == 3
# a retry after expiry returns the dead booking: the caller must use a new key
conn = new_db(inventory=[('U', 5, 1)])
b1 = reserve(conn, 'k', 'g', 'U', 0, 2, 1, 0, 5)
assert reserve(conn, 'other', 'h', 'U', 0, 2, 1, 6, 5) is not None and reserve(conn, 'k', 'g', 'U', 0, 2, 1, 7, 5) == b1
assert conn.execute('SELECT state FROM bookings WHERE id = ?', (b1,)).fetchone()[0] == 'EXPIRED' and confirm(conn, b1, 7) is False
# confirm re-checks the clock at write time even if nobody has reclaimed yet
conn = new_db(inventory=[('U', 5, 1)])
b = reserve(conn, 'k', 'g', 'U', 0, 2, 1, 0, 5)
assert confirm(conn, b, 5) is False and confirm(conn, b, 4) is True and confirm(conn, b, 400) is True     # boundary: expires at 5; confirmed stays confirmed
# the check constraint is the seat belt: a bad update cannot oversell
try:
    conn.execute('UPDATE inv SET sold = total + 1 WHERE night = 0')
    raise AssertionError('constraint missing')
except sqlite3.IntegrityError:
    pass
assert rooms_left(new_db(inventory=[('U', 5, 3)]), 'U', 0, 5) == 3
c2 = new_db(inventory=[('U', 5, 3)]); reserve(c2, 'k', 'g', 'U', 2, 3, 2, 0, 9)
assert rooms_left(c2, 'U', 0, 5) == 1 and rooms_left(c2, 'U', 3, 5) == 3 and rooms_left(c2, 'U', 3, 7) == 0

# ---- 2. twelve threads, one database file: no night ever oversold -----------------------------------------------------------------
tmp = tempfile.mkdtemp()
path = os.path.join(tmp, 'hotel.db')
conn = new_db(path, [('R', 30, 3), ('S', 30, 1)])
results, glock, errors = [], threading.Lock(), []


def guest(w):
    r = random.Random(w)
    c = sqlite3.connect(path, timeout=60, isolation_level=None, check_same_thread=False)
    try:
        for i in range(40):
            rt = r.choice(['R', 'S'])
            d_in = r.randint(0, 27)
            args = (rt, d_in, d_in + r.randint(1, 3), 1)
            bid = reserve(c, 'w%d-%d' % (w, i), 'g%d' % w, *args, 0, 10 ** 6)
            if bid is not None:
                if r.random() < 0.7:
                    assert confirm(c, bid, 1)
                elif r.random() < 0.5:
                    assert cancel(c, bid)
                with glock:
                    results.append((bid, args))
    except BaseException as e:           # surface the failure in the main thread
        errors.append(e)
    finally:
        c.close()


ts = [threading.Thread(target=guest, args=(w,)) for w in range(12)]
[t.start() for t in ts]; [t.join() for t in ts]
assert not errors, errors
occ = {}
for rt, a, b, n, st in conn.execute('SELECT rtype, d_in, d_out, rooms, state FROM bookings'):
    if st in ('PENDING', 'CONFIRMED'):
        for night in range(a, b):
            occ[(rt, night)] = occ.get((rt, night), 0) + n
tot = {('R', n): 3 for n in range(30)} | {('S', n): 1 for n in range(30)}
got = sold_table(conn)
assert all(got[k] == occ.get(k, 0) <= tot[k] for k in tot)
print("threads: %d successful reservations of %d attempts" % (len(results), 12 * 40)); assert len(results) > 40
conn.close(); shutil.rmtree(tmp, ignore_errors=True)

# ---- 3. overbooking: against an exact binomial built by convolution, brute force over the limit, and Monte Carlo ----------------------
def binom_dp(n, p):
    """distribution of the number of shows, built one guest at a time (independent of math.comb)"""
    d = [1.0]
    for _ in range(n):
        nd = [0.0] * (len(d) + 1)
        for k, v in enumerate(d):
            nd[k] += v * (1 - p)
            nd[k + 1] += v * p
        d = nd
    return d


def profits(C, p, r, c, Lmax):
    """expected profit for every L from 0 to Lmax, adding one guest to the distribution at a time"""
    d, out = [1.0], []
    for L in range(Lmax + 1):
        out.append(sum(v * (r * min(k, C) - c * max(k - C, 0)) for k, v in enumerate(d)))
        nd = [0.0] * (len(d) + 1)
        for k, v in enumerate(d):
            nd[k] += v * (1 - p)
            nd[k + 1] += v * p
        d = nd
    return out


def profit_ref(L, C, p, r, c):
    return profits(C, p, r, c, L)[L]


rr = random.Random(7)
checked = 0
big = 0
for _ in range(120):
    C = rr.choice([1, 2, 5, 10, 30, 80, 120])
    p = rr.uniform(0.3, 0.99)
    r, c = 1.0, rr.uniform(0.2, 10)
    L = best_limit(C, p, r, c)
    best = max(profits(C, p, r, c, int(C / p * 1.4) + 30)[C:])
    assert profit_ref(L, C, p, r, c) >= best - 1e-9, (C, p, c, L)
    assert abs(expected_profit(L, C, p, r, c) - profit_ref(L, C, p, r, c)) < 1e-9
    assert L >= C
    big += C >= 80
    checked += 1
assert big > 10
# rule boundaries: certain guests are never overbooked; free walking (tiny c) overbooks a lot; ruinous c (huge) does not
assert best_limit(50, 1.0, 1, 3) == 50
assert best_limit(50, 0.9, 1, 1e6) <= 51
assert best_limit(50, 0.9, 1, 0.01) > best_limit(50, 0.9, 1, 3) > best_limit(50, 0.9, 1, 1000)
# Monte Carlo: simulate guests directly
mc = random.Random(11)
def simulate(L, C, p, r, c, runs):
    tot_ = 0.0
    for _ in range(runs):
        s = sum(mc.random() < p for _ in range(L))
        tot_ += r * min(s, C) - c * max(s - C, 0)
    return tot_ / runs
for (C, p, r, c) in [(20, 0.85, 1.0, 3.0), (100, 0.9, 1.0, 3.0)]:
    L = best_limit(C, p, r, c)
    assert abs(simulate(L, C, p, r, c, 20000) - expected_profit(L, C, p, r, c)) < 0.01 * C
# the headline example (illustrative): 100 rooms, 90% show up, a bumped guest costs three times a room night
C, p, r, c = 100, 0.9, 1.0, 3.0
L = best_limit(C, p, r, c)
no_over = expected_profit(C, C, p, r, c)
with_over = expected_profit(L, C, p, r, c)
d = binom_dp(L, p)
bumped = sum(v * max(k - C, 0) for k, v in enumerate(d))
p_over = sum(v for k, v in enumerate(d) if k > C)
empty = sum(v * max(C - k, 0) for k, v in enumerate(binom_dp(C, p)))
empty_over = sum(v * max(C - k, 0) for k, v in enumerate(d))
print('overbooking: limit %d for %d rooms; expected profit %.2f vs %.2f; bumped %.2f, P(someone bumped) %.3f; empty rooms %.2f -> %.2f'
      % (L, C, with_over, no_over, bumped, p_over, empty, empty_over))
# the independence assumption: a shared shock (weather, an event) moves everyone's show rate together
def mixture_bumped(L, C, ps):
    return sum(sum(v * max(k - C, 0) for k, v in enumerate(binom_dp(L, q))) for q in ps) / len(ps)
def mixture_pover(L, C, ps):
    return sum(sum(v for k, v in enumerate(binom_dp(L, q)) if k > C) for q in ps) / len(ps)
shock_bumped = mixture_bumped(L, C, [0.85, 0.95])
shock_pover = mixture_pover(L, C, [0.85, 0.95])
print('shared shock: bumped %.2f vs %.2f, P(someone bumped) %.3f vs %.3f' % (shock_bumped, bumped, shock_pover, p_over))
assert shock_bumped > bumped and shock_pover > p_over

# ---- 4. availability bitmaps against a night-by-night loop; wider than a machine word -------------------------------------------------
rb = random.Random(3)
for _ in range(3000):
    width = rb.choice([8, 31, 64, 65, 120, 365, 400])
    free = [rb.random() < rb.choice([0.5, 0.9, 0.99]) for _ in range(width)]
    bits = sum(1 << i for i, f in enumerate(free) if f)
    d_in = rb.randrange(width)
    d_out = rb.randint(d_in + 1, min(width, d_in + rb.choice([1, 2, 7, 30, 400])))
    assert is_free(bits, d_in, d_out) == all(free[d_in:d_out])
    after = take(bits, d_in, d_out)
    assert not any(is_free(after, n, n + 1) for n in range(d_in, d_out))
    assert all(is_free(after, n, n + 1) == free[n] for n in range(width) if not d_in <= n < d_out)
assert night_mask(2, 5) == 0b11100 and is_free(0b11100, 2, 5) and not is_free(0b11100, 2, 6) and not is_free(0b11000, 2, 5)

# ---- 5. reserve -> charge -> confirm with a crash at every point, retries, expiry during payment, reconciliation -------------------------
def invariants(conn, psp, label):
    states = {idem: st for idem, st in conn.execute('SELECT idem, state FROM bookings')}
    for idem in psp.charges:
        paid = idem not in psp.refunded
        assert paid == (states.get(idem) == 'CONFIRMED'), (label, idem, paid, states.get(idem))     # charged and kept <=> confirmed
    for idem, st in states.items():
        if st == 'CONFIRMED':
            assert idem in psp.charges and idem not in psp.refunded, (label, idem)
    occ = {}
    for rt, a, b, n, st in conn.execute('SELECT rtype, d_in, d_out, rooms, state FROM bookings'):
        if st in ('PENDING', 'CONFIRMED'):
            for night in range(a, b):
                occ[(rt, night)] = occ.get((rt, night), 0) + n
    for (rt, night), s in sold_table(conn).items():
        assert s == occ.get((rt, night), 0), (label, rt, night)


flows = 0
for crash_at in (None, 'after_reserve', 'after_charge', 'after_confirm'):
    for retry in (False, True):
        conn, psp = new_db(inventory=[('R', 6, 1)]), Psp()
        try:
            out = book(conn, psp, 'k1', 'g1', 'R', 0, 3, 1, 100, 0, crash_at=crash_at)
        except Crash:
            out = 'CRASHED'
        if retry:
            out = book(conn, psp, 'k1', 'g1', 'R', 0, 3, 1, 100, 10)
            assert out == 'CONFIRMED' and list(psp.charges) == ['k1'] and not psp.refunded, (crash_at, out)
        reconcile(conn, psp, 1000)
        invariants(conn, psp, (crash_at, retry))
        assert (conn.execute("SELECT state FROM bookings").fetchone()[0] == 'CONFIRMED') == (retry or crash_at in (None, 'after_confirm'))
        if not retry and crash_at == 'after_charge':
            assert psp.refunded == {'k1'} and sold_table(conn)[('R', 0)] == 0     # reconciliation gave the money and the rooms back
        if not retry and crash_at == 'after_reserve':                          # never charged; the rooms free up lazily, at the next reserve
            assert not psp.charges and reserve(conn, 'next', 'h', 'R', 0, 3, 1, 1000, 600) is not None
        flows += 1
# review I3: a reconcile that runs while the reservation is still alive must leave a charged pending booking alone, and the retry then confirms
conn, psp = new_db(inventory=[('R', 6, 1)]), Psp()
try:
    book(conn, psp, 'k', 'g', 'R', 0, 2, 1, 100, 0, ttl=600, crash_at='after_charge')
except Crash:
    pass
reconcile(conn, psp, 1)
assert not psp.refunded and conn.execute("SELECT state FROM bookings").fetchone()[0] == 'PENDING'
assert book(conn, psp, 'k', 'g', 'R', 0, 2, 1, 100, 10) == 'CONFIRMED' and not psp.refunded
invariants(conn, psp, 'early reconcile')
# review I2: reconcile reads PENDING, then the guest's retry (a slow worker whose clock reads 599) confirms; reconcile must not
# cancel or refund a booking the guest was told is CONFIRMED
conn, psp = new_db(inventory=[('R', 6, 1)]), Psp()
try:
    book(conn, psp, 'k', 'g', 'R', 0, 2, 1, 100, 0, ttl=600, crash_at='after_charge')
except Crash:
    pass
told = []
reconcile(conn, psp, 601, after_read=lambda idem: told.append(book(conn, psp, idem, 'g', 'R', 0, 2, 1, 100, 599)))
assert told == ['CONFIRMED']
assert conn.execute("SELECT state FROM bookings").fetchone()[0] == 'CONFIRMED' and not psp.refunded and sold_table(conn)[('R', 0)] == 1
invariants(conn, psp, 'stale reconcile')
# the other order: reconcile wins first, then the retry must be told EXPIRED and the charge is refunded
conn, psp = new_db(inventory=[('R', 6, 1)]), Psp()
try:
    book(conn, psp, 'k', 'g', 'R', 0, 2, 1, 100, 0, ttl=600, crash_at='after_charge')
except Crash:
    pass
reconcile(conn, psp, 601)
assert book(conn, psp, 'k', 'g', 'R', 0, 2, 1, 100, 602) == 'EXPIRED' and psp.refunded == {'k'} and sold_table(conn)[('R', 0)] == 0
invariants(conn, psp, 'reconcile first')
# expire() is one conditional transition: only a pending reservation at or past its time, and only once
conn = new_db(inventory=[('R', 6, 1)])
b1 = reserve(conn, 'a', 'g', 'R', 0, 2, 1, 0, 10)
assert expire(conn, b1, 9.9) is False and sold_table(conn)[('R', 0)] == 1
assert expire(conn, b1, 10) is True and sold_table(conn)[('R', 0)] == 0 and expire(conn, b1, 11) is False
b2 = reserve(conn, 'b', 'g', 'R', 0, 2, 1, 20, 10); assert confirm(conn, b2, 21)
assert expire(conn, b2, 1000) is False and sold_table(conn)[('R', 0)] == 1               # a confirmed booking is never expired

# a retry after the reservation died: no new charge, 'EXPIRED', the key is spent
conn, psp = new_db(inventory=[('R', 6, 1)]), Psp()
try:
    book(conn, psp, 'k', 'g', 'R', 0, 2, 1, 100, 0, ttl=5, crash_at='after_reserve')
except Crash:
    pass
assert book(conn, psp, 'k', 'g', 'R', 0, 2, 1, 100, 9, ttl=5) == 'EXPIRED' and not psp.charges
# expiry while the guest is paying: charge, confirm refused, refund
conn, psp = new_db(inventory=[('R', 6, 1)]), Psp()
assert book(conn, psp, 'k', 'g', 'R', 0, 2, 1, 100, 0, ttl=5, paid_at=9) == 'EXPIRED' and psp.refunded == {'k'}
invariants(conn, psp, 'slow payment')
# sold out
assert book(conn, psp, 'k2', 'g', 'R', 0, 2, 1, 100, 20) == 'CONFIRMED' and book(conn, psp, 'k3', 'g', 'R', 1, 3, 1, 100, 20) == 'SOLD_OUT'

fz = random.Random(21)
for seq in range(250):
    conn, psp = new_db(inventory=[('R', 8, 2)]), Psp()
    now, keys = 0, []
    for step in range(fz.randint(5, 25)):
        k = fz.random()
        if k < 0.8:
            if not keys or fz.random() < 0.5:                     # a new request, or a retry of an old key
                d_in = fz.randint(0, 5)
                keys.append(('k%d' % len(keys), ('g', 'R', d_in, d_in + fz.randint(1, 3), 1)))
                idem, args = keys[-1]
            else:
                idem, args = fz.choice(keys)
            delay = fz.choice([0, 0, 10])                          # the guest takes this long to pay; time never runs backwards
            try:
                book(conn, psp, idem, *args, 100, now, ttl=fz.choice([3, 20]), crash_at=fz.choice([None, None, 'after_reserve', 'after_charge', 'after_confirm']),
                     paid_at=now + delay)
            except Crash:
                pass
            now += delay
            flows += 1
        elif k < 0.9:
            reconcile(conn, psp, now)
        else:
            now += fz.choice([1, 5, 30])
        assert all(0 <= s_ <= 2 for (s_,) in conn.execute('SELECT sold FROM inv'))
    reconcile(conn, psp, 10 ** 6)
    invariants(conn, psp, ('fuzz', seq))
assert flows > 300

need('400 random operation sequences', 'Twelve threads', '250 sequences', '120 random parameter sets', '20,000 simulated nights',
     'limit %d' % L, '%.2f to **%.2f**' % (no_over, with_over), '**%.2f**' % bumped, '**%.3f**' % p_over, '%.2f to %.2f' % (empty, empty_over),
     '**%.2f**' % shock_bumped, '**%.3f**' % shock_pover, '85% on half the nights', 'one conditional update that changes nothing unless', 'What is not solved', 'leave a charged pending booking alone')
forbid('limit 108', 'limit 110', 'Redlock', 'one clock decides')
forbid_claims(r'Booking\.com|Expedia|Airbnb stores|Airbnb keeps|Airbnb allocates|Airbnb sets', r'(stores|keeps|uses|allocates|sets|overbooks|runs)')
print('sy58 code checks passed (%d booking operations, %d payment flows)' % (ops, flows))
