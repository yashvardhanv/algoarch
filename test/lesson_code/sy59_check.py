"""Runs the python blocks of the sy59 online auction lesson against independent references: eBay's increment table written
out separately and compared at every cent up to $6,000; a ledger-based model of proxy bidding that finds the price by
searching for the lowest amount one increment above the runner-up; the bid ledger replayed against the stored state after
twelve threads race on one item; soft-close and hard-close boundaries; and a simulation of late bids under both rules
whose figures the lesson prints. Figures printed from these runs are asserted against the text."""
import re, sys, random, sqlite3, threading, tempfile, os, shutil

src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
assert len(blocks) >= 2, 'expected the lesson code blocks'
ns = {}
for b in blocks:
    exec(b, ns)
increment, new_auction, resolve, extended_end = ns['increment'], ns['new_auction'], ns['resolve'], ns['extended_end']
SCHEMA, open_auction, place_bid, close, runner_up = ns['SCHEMA'], ns['open_auction'], ns['place_bid'], ns['close'], ns['runner_up']
ACCEPTED = ('LEADING', 'RAISED', 'OUTBID')


def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the checked figure: %r' % p


def forbid(*phrases):
    for p in phrases:
        assert p not in src, 'lesson text still contains stale wording: %r' % p


# ---- 1. the increment table against a separately written copy of eBay's table, at every cent -----------------------------------
EBAY = [(1, 99, 5), (100, 499, 25), (500, 2499, 50), (2500, 9999, 100), (10000, 24999, 250), (25000, 49999, 500),
        (50000, 99999, 1000), (100000, 249999, 2500), (250000, 499999, 5000), (500000, 10 ** 12, 10000)]   # dollars 0.01-0.99 is 5c ... $5,000 and up is $100


def ref_inc(c):
    for lo, hi, inc in EBAY:
        if lo <= c <= hi:
            return inc
    raise ValueError(c)


for c in range(1, 600_001):
    assert increment(c) == ref_inc(c), c
for edge in (100, 500, 2500, 10000, 25000, 50000, 100000, 250000, 500000):          # every bracket starts exactly here
    assert increment(edge) > increment(edge - 1)
assert increment(99) == 5 and increment(100) == 25 and increment(2499) == 50 and increment(2500) == 100 and increment(500000) == 10000
assert increment(10 ** 9) == 10000
try:
    increment(0)
    raise AssertionError('price below one cent must be refused')
except ValueError:
    pass


# ---- 2. proxy bidding against a ledger model ---------------------------------------------------------------------------------------
def lowest_unbeatable(start, m1, m2):
    """lowest amount a in [start, m1] that is at least one increment above the runner-up's maximum, else m1;
    linear scan for small values, binary search for large ones (both are used, the scan checks the search)"""
    need_ = m2 + ref_inc(m2)
    lo, hi = start, m1
    if hi - lo < 4000:
        for a in range(lo, hi + 1):
            if a >= need_:
                return a
        return m1
    if need_ > m1:
        return m1
    while lo < hi:                                           # predicate "a >= need_" is monotone in a
        mid = (lo + hi) // 2
        if mid >= need_:
            hi = mid
        else:
            lo = mid + 1
    return lo


for _ in range(300):                                          # the search agrees with the scan where both apply
    s = random.Random(_).randint(1, 3000); a1 = s + random.Random(_ + 1).randint(0, 3500); a2 = random.Random(_ + 2).randint(1, a1)
    need_ = a2 + ref_inc(a2)
    lin = next((a for a in range(s, a1 + 1) if a >= need_), a1)
    lo, hi = s, a1
    if need_ > a1:
        bs = a1
    else:
        while lo < hi:
            mid = (lo + hi) // 2
            if mid >= need_:
                hi = mid
            else:
                lo = mid + 1
        bs = lo
    assert lin == bs


class Model:
    """Ledger of accepted bids. The leader is the highest maximum (earlier wins a tie). The price is the highest value
    reached so far, where a value is only produced when a CHALLENGER's bid is accepted: it is the lowest amount one
    increment above the runner-up's maximum, capped at the leader's. Raising your own limit produces no new value."""
    def __init__(self, start):
        self.start, self.ledger, self.n, self.price = start, [], 0, start
    def best(self, ledger=None):
        per = {}
        for b, m, t in (self.ledger if ledger is None else ledger):
            if b not in per or m > per[b][0]:
                per[b] = (m, t)
        return per
    def leader_of(self, per):
        if not per:
            return None
        return max(per, key=lambda b: (per[b][0], -per[b][1]))
    def state(self):
        per = self.best()
        leader = self.leader_of(per)
        return leader, (per[leader][0] if leader else 0), self.price
    def bid(self, bidder, m):
        leader, m1, price = self.state()
        if leader is None:
            ok = m >= self.start
        elif bidder == leader:
            ok = m > m1
        else:
            ok = m >= price + ref_inc(price)
        self.n += 1
        if ok:
            self.ledger.append((bidder, m, self.n))
            if leader is not None and bidder != leader:                 # a challenger: the price may move
                per = self.best()
                new_leader = self.leader_of(per)
                top = per[new_leader][0]
                second = max(v[0] for b, v in per.items() if b != new_leader)
                self.price = max(self.price, lowest_unbeatable(self.start, top, second))
        return ok


rng = random.Random(59)
STARTS = [1, 5, 99, 100, 2500, 7000]
BRACKETS = [(1, 99), (100, 499), (500, 2499), (2500, 9999), (10000, 24999), (25000, 99999), (100000, 499999), (500000, 700000)]
seqs = 0
for seq in range(2500):
    start = rng.choice(STARTS)
    a, model = new_auction(start, 1000), Model(start)
    seen, bidders = [], ['A', 'B', 'C', 'D', 'E']
    last_price = start
    for step in range(rng.randint(2, 14)):
        who = rng.choice(bidders)
        if seen and rng.random() < 0.3:
            m = rng.choice(seen) + rng.choice([-1, 0, 0, 1])          # ties and off-by-one around earlier maxima
        else:
            lo, hi = rng.choice(BRACKETS)
            m = rng.randint(lo, hi)
        m = max(m, 1)
        seen.append(m)
        before = a
        a, outcome = resolve(a, who, m)
        ok = model.bid(who, m)
        assert (outcome in ACCEPTED) == ok, (seq, step, who, m, outcome, before)
        leader, m1, price = model.state()
        assert (a['leader'], a['leader_max'], a['price']) == (leader, m1, price) if leader else a['leader'] is None, (seq, step, a, leader, m1, price)
        if ok:
            assert outcome == ('LEADING' if a['leader'] == who and before['leader'] != who else 'RAISED' if before['leader'] == who else 'OUTBID')
        assert a['price'] >= last_price and a['price'] <= max(a['leader_max'], a['price'])
        if a['leader'] is not None:
            assert a['price'] <= a['leader_max']
        last_price = a['price']
        seqs += 1
assert seqs > 15000

# hand-worked cases (dollars written as cents)
a = new_auction(100, 1000)
a, o = resolve(a, 'A', 1000); assert (o, a['leader'], a['price']) == ('LEADING', 'A', 100)
a, o = resolve(a, 'B', 500); assert (o, a['leader'], a['price']) == ('OUTBID', 'A', 550)                 # 5.00 + 0.50
a, o = resolve(a, 'C', 599); assert o == 'TOO_LOW' and a['price'] == 550                                  # 5.50 + 0.50 = 6.00 is the minimum
a, o = resolve(a, 'C', 600); assert (o, a['leader'], a['price']) == ('OUTBID', 'A', 650)
a, o = resolve(a, 'B', 1200); assert (o, a['leader'], a['price']) == ('LEADING', 'B', 1050)              # one increment over A's 10.00
a, o = resolve(a, 'B', 1100); assert o == 'NO_CHANGE'                                                     # you cannot lower your limit
a, o = resolve(a, 'B', 2000); assert (o, a['leader_max'], a['price']) == ('RAISED', 2000, 1050)         # raising your limit does not move the price
a, o = resolve(a, 'A', 1050); assert o == 'TOO_LOW'                                                       # 10.50 + 0.50 = 11.00 is the minimum now
a = new_auction(100, 1000)
a, _ = resolve(a, 'A', 1000); a, o = resolve(a, 'B', 1000)
assert (o, a['leader'], a['price']) == ('OUTBID', 'A', 1000)                                              # an equal limit loses: it arrived later
a = new_auction(100, 1000)
a, _ = resolve(a, 'A', 10000); a, o = resolve(a, 'B', 2499)
assert (o, a['leader'], a['price']) == ('OUTBID', 'A', 2549)                                              # 24.99 + 0.50: the price crosses into the next bracket
a, o = resolve(a, 'C', 2548); assert o == 'TOO_LOW'                                                       # next minimum 25.49 + 1.00 = 26.49
a, o = resolve(a, 'C', 2649); assert (o, a['price']) == ('OUTBID', 2749)                                  # 26.49 + 1.00
a = new_auction(100, 1000)
a, o = resolve(a, 'A', 99); assert o == 'TOO_LOW' and a['leader'] is None
a, o = resolve(a, 'A', 100); assert (o, a['price']) == ('LEADING', 100)
a = new_auction(100, 1000)
a, _ = resolve(a, 'A', 5000); a, o = resolve(a, 'B', 5020)
assert (o, a['leader'], a['price']) == ('LEADING', 'B', 5020)                                             # a new leader just above: one increment would be 51.00, capped at their limit

# the finding: a price recomputed from the two maximums would jump when the leader raises their limit; the real one does not
a = new_auction(5, 1000)
a, _ = resolve(a, 'E', 48120); a, o = resolve(a, 'A', 48119)
assert (o, a['leader'], a['price']) == ('OUTBID', 'E', 48120)                      # the runner-up pushes the price up to the leader's limit
a, o = resolve(a, 'E', 490860)
assert (o, a['price']) == ('RAISED', 48120) and 48119 + increment(48119) == 48619   # not 48,619

# ---- 3. the store: the ledger replays to the stored state; closing rules -----------------------------------------------------------
def replay(rows, start, end_at, hard_end, window, extend):
    """feed the ledger back through the pure functions in sequence order"""
    a, state, outs = new_auction(start, end_at, hard_end), 'OPEN', []
    for seq, bidder, m, at, outcome in rows:
        if at >= a['end_at']:
            out = 'CLOSED'
        else:
            new, out = resolve(a, bidder, m)
            if out in ACCEPTED:
                new['end_at'] = extended_end(a, at, window, extend)
                a = new
        outs.append(out)
    return a, outs


def new_db(path=':memory:'):
    conn = sqlite3.connect(path, timeout=60, isolation_level=None, check_same_thread=False)
    conn.executescript(SCHEMA)
    return conn


tmp = tempfile.mkdtemp()
path = os.path.join(tmp, 'auction.db')
conn = new_db(path)
open_auction(conn, 'item', 100, 1000.0, hard_end=1060.0)
errors = []


def bidder_thread(w):
    r = random.Random(w)
    c = sqlite3.connect(path, timeout=60, isolation_level=None, check_same_thread=False)
    try:
        for i in range(30):
            lo, hi = r.choice(BRACKETS)
            place_bid(c, 'item', 'u%d' % (w % 5), r.randint(lo, hi), r.uniform(0, 1055), window=10, extend=10)
    except BaseException as e:
        errors.append(e)
    finally:
        c.close()


ts = [threading.Thread(target=bidder_thread, args=(w,)) for w in range(12)]
[t.start() for t in ts]; [t.join() for t in ts]
assert not errors, errors
rows = conn.execute('SELECT seq, bidder, max_bid, at, outcome FROM bids WHERE item = ? ORDER BY seq', ('item',)).fetchall()
assert len(rows) == 360 and [r[0] for r in rows] == list(range(1, 361))                       # every attempt is in the ledger, in one order
# the ledger's `at` is not monotone (threads picked random times), so replay uses the stored order: that IS the serial order
final, outs = replay(rows, 100, 1000.0, 1060.0, 10, 10)
assert outs == [r[4] for r in rows], 'a recorded outcome differs from replaying the ledger: a lost update or a race'
st = conn.execute('SELECT leader, leader_max, price, end_at FROM auctions WHERE item = ?', ('item',)).fetchone()
assert st == (final['leader'], final['leader_max'], final['price'], final['end_at'])
accepted = sum(r[4] in ACCEPTED for r in rows)
assert accepted > 5
conn.close(); shutil.rmtree(tmp, ignore_errors=True)

# a single-threaded run with many items: replay equals state, and the runner-up is the best other maximum
for seq in range(200):
    conn = new_db()
    start = rng.choice(STARTS)
    open_auction(conn, 'x', start, 500.0)
    t = 0.0
    for _ in range(rng.randint(1, 15)):
        t += rng.uniform(0, 30)
        lo, hi = rng.choice(BRACKETS)
        place_bid(conn, 'x', rng.choice('ABCD'), rng.randint(lo, hi), t)
    rows = conn.execute('SELECT seq, bidder, max_bid, at, outcome FROM bids ORDER BY seq').fetchall()
    final, outs = replay(rows, start, 500.0, 500.0, 0, 0)
    assert outs == [r[4] for r in rows]
    got = conn.execute('SELECT leader, leader_max, price FROM auctions').fetchone()
    assert got == (final['leader'], final['leader_max'], final['price'])
    acc = [r for r in rows if r[4] in ACCEPTED]
    per = {}
    for _, b, m, _, _ in acc:
        per[b] = max(per.get(b, 0), m)
    others = {b: m for b, m in per.items() if b != final['leader']}
    ru = runner_up(conn, 'x')
    if final['leader'] is None or not others:
        assert ru is None
    else:
        assert ru[1] == max(others.values()) and others[ru[0]] == ru[1]
    # a bid at or after the end is refused, and so is anything once the item is closed
    assert place_bid(conn, 'x', 'Z', 700000, 500.0) == 'CLOSED'
    res = close(conn, 'x', 500.0)
    assert res == ((final['leader'], final['price']) if final['leader'] else None)
    assert close(conn, 'x', 900.0) == res                                       # idempotent
    assert place_bid(conn, 'x', 'Z', 700000, 501.0) == 'CLOSED'
    conn.close()

# closing boundaries
conn = new_db(); open_auction(conn, 'i', 100, 100.0)
assert place_bid(conn, 'i', 'A', 500, 99.999) == 'LEADING' and place_bid(conn, 'i', 'B', 600, 100.0) == 'CLOSED'
assert close(conn, 'i', 99.9) is None and conn.execute('SELECT state FROM auctions').fetchone()[0] == 'OPEN'        # not yet
assert close(conn, 'i', 100.0) == ('A', 100)
conn = new_db(); open_auction(conn, 'i', 100, 100.0)
assert close(conn, 'i', 200.0) is None and conn.execute('SELECT state FROM auctions').fetchone()[0] == 'NO_SALE'

# soft close
conn = new_db(); open_auction(conn, 'i', 100, 100.0, hard_end=120.0)
assert place_bid(conn, 'i', 'A', 1000, 10.0, window=10, extend=10) == 'LEADING'
end = lambda: conn.execute('SELECT end_at FROM auctions').fetchone()[0]
assert end() == 100.0
assert place_bid(conn, 'i', 'B', 500, 89.999, window=10, extend=10) == 'OUTBID' and end() == 100.0        # just outside the window
assert place_bid(conn, 'i', 'C', 550, 95.0, window=10, extend=10) == 'TOO_LOW' and end() == 100.0       # a rejected bid never extends
assert place_bid(conn, 'i', 'C', 600, 95.0, window=10, extend=10) == 'OUTBID' and end() == 105.0        # inside the window: now + 10
assert place_bid(conn, 'i', 'B', 700, 104.0, window=10, extend=10) == 'OUTBID' and end() == 114.0
assert place_bid(conn, 'i', 'C', 800, 113.0, window=10, extend=10) == 'OUTBID' and end() == 120.0       # the hard end caps it (113 + 10 = 123)
assert place_bid(conn, 'i', 'B', 900, 120.0, window=10, extend=10) == 'CLOSED'
conn = new_db(); open_auction(conn, 'i', 100, 100.0)
assert place_bid(conn, 'i', 'A', 1000, 99.0, window=0, extend=10) == 'LEADING' and end() == 100.0          # window 0 means hard close
assert extended_end(new_auction(1, 100.0, 200.0), 90.0, 10, 15) == 105.0 and extended_end(new_auction(1, 100.0, 200.0), 89.999, 10, 15) == 100.0     # the window edge is inclusive
assert extended_end(new_auction(1, 100.0, 200.0), 90.0, 10, 10) == 100.0 and extended_end(new_auction(1, 100.0, 200.0), 90.5, 10, 10) == 100.5
assert extended_end(new_auction(1, 100.0, 200.0), 95.0, 10, 3) == 100.0 and extended_end(new_auction(1, 100.0, 200.0), 99.0, 10, 3) == 102.0     # a short extension never shortens the auction
assert extended_end(new_auction(1, 100.0, 200.0), 89.9, 10, 10) == 100.0
assert extended_end(new_auction(1, 100.0, 105.0), 95.0, 10, 10) == 105.0                                   # cap
assert extended_end(new_auction(1, 100.0, 100.0), 99.0, 10, 10) == 100.0                                   # no room: hard_end == end_at

# ---- 4. late bids under a hard close and a soft close (illustrative simulation, figures printed in the lesson) -----------------------
def run(rule, n_auctions, seed):
    r = random.Random(seed)
    top_wins = late_rejects = total_bids = 0
    for _ in range(n_auctions):
        end = 3600.0
        values = {b: r.randint(1000, 10000) for b in range(6)}
        arrivals = []
        for b, v in values.items():
            sniper = r.random() < 0.5
            sent = end - 3 if sniper else r.uniform(0, end - 30)
            arrivals.append((sent + r.uniform(0, 4), b, v))
        arrivals.sort()
        a = new_auction(100, end, end + 300)
        for at, b, v in arrivals:
            total_bids += 1
            if at >= a['end_at']:
                late_rejects += 1
                continue
            new, out = resolve(a, b, v)
            if out in ACCEPTED:
                new['end_at'] = extended_end(a, at, *rule)
                a = new
        top = max(values, key=lambda b: values[b])
        top_wins += a['leader'] == top
    return 100 * top_wins / n_auctions, 100 * late_rejects / total_bids


HARD = run((0, 0), 6000, 1)
SOFT = run((10, 10), 6000, 1)
print('late bids: hard close top-value bidder wins %.1f%%, %.1f%% of bids rejected as late; soft close (10 s window, 10 s extension) %.1f%%, %.1f%%'
      % (HARD[0], HARD[1], SOFT[0], SOFT[1]))
assert abs(HARD[0] - 87.5) < 2.0, 'the hard-close loss should be close to 0.5 x 0.25 = 12.5%'     # half snipe, a quarter of those arrive after the end
assert SOFT[0] > HARD[0] + 1 and SOFT[1] < HARD[1]

need('48,619', '48,119', '12.4%', '%.1f%%' % HARD[0], '%.1f%%' % HARD[1], '%.1f%%' % SOFT[0], '%.1f%%' % SOFT[1], '2,500 random bid sequences', 'every cent up to $6,000',
     'Twelve threads', '360 attempts')
forbid('eBay uses a soft close', 'eBay uses a hard close', 'eBay orders bids')
print('sy59 code checks passed (%d proxy bids checked, %d ledger rows replayed)' % (seqs, 360))
