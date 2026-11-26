"""Runs the python code blocks from data/new_lessons/sy42.md (real SQL in SQLite, and the GA counter) against
reference models that keep every hold in a list and decide availability by scanning them, under random
interleavings; then a 16-thread test against one database file."""
import re, sys, random, sqlite3, threading, tempfile, os, time
src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
ns = {}
for b in blocks:
    exec(b, ns)
SCHEMA, hold, confirm, release, available, GaCounter = (
    ns['SCHEMA'], ns['hold'], ns['confirm'], ns['release'], ns['available'], ns['GaCounter'])
random.seed(42)

def new_db(path, n_seats):
    conn = sqlite3.connect(path, timeout=60, isolation_level=None, check_same_thread=False)
    conn.executescript(SCHEMA)
    conn.executemany('INSERT INTO seats (seat_id) VALUES (?)', [('s%02d' % i,) for i in range(n_seats)])
    return conn

class Ref:
    """Every hold ever made, in a list. A seat is taken at time t if a confirmed hold covers it, or an active
    hold covers it and has not expired."""
    def __init__(self, seats):
        self.seats, self.holds, self.by_key = seats, {}, {}
    def taken(self, seat, t):
        return any(seat in h['seats'] and (h['state'] == 'CONFIRMED' or (h['state'] == 'ACTIVE' and h['exp'] > t))
                   for h in self.holds.values())
    def can_hold(self, seats, t):
        return not any(self.taken(s, t) for s in seats)
    def add(self, hid, key, seats, t, ttl):
        self.holds[hid] = {'seats': set(seats), 'exp': t + ttl, 'state': 'ACTIVE'}
        self.by_key[key] = hid
    def confirm(self, hid, t):
        h = self.holds.get(hid)
        if h is None or h['state'] == 'RELEASED':
            return False
        if h['state'] == 'CONFIRMED':
            return True
        if h['exp'] > t:
            h['state'] = 'CONFIRMED'
            return True
        return False
    def release(self, hid):
        h = self.holds.get(hid)
        if h and h['state'] == 'ACTIVE':
            h['state'] = 'RELEASED'
    def available(self, t):
        return sum(1 for s in self.seats if not self.taken(s, t))

ops = 0
for trial in range(60):
    n = random.randint(3, 12)
    conn = new_db(':memory:', n)
    seats = ['s%02d' % i for i in range(n)]
    ref = Ref(seats)
    t, ids, key_no = 0, [], 0
    for _ in range(150):
        r = random.random()
        if r < 0.45:
            want = random.sample(seats, random.randint(1, min(4, n)))
            ttl = random.randint(1, 8)
            if ref.by_key and random.random() < 0.15:            # a client retry with an old key
                key = random.choice(list(ref.by_key))
                assert hold(conn, 'u', want, t, ttl, key) == ref.by_key[key]
            else:
                key_no += 1
                key = 'k%d' % key_no
                expect = ref.can_hold(want, t)
                got = hold(conn, 'u%d' % random.randint(1, 5), want, t, ttl, key)
                assert (got is not None) == expect, (want, t, got, expect)
                if got:
                    ref.add(got, key, want, t, ttl)
                    ids.append(got)
        elif r < 0.65 and ids:
            hid = random.choice(ids)
            assert confirm(conn, hid, t) == ref.confirm(hid, t), (hid, t)
        elif r < 0.75 and ids:
            hid = random.choice(ids)
            release(conn, hid)
            ref.release(hid)
        elif r < 0.78:
            assert confirm(conn, 'no-such-hold', t) is False
        else:
            t += random.randint(0, 3)
        ops += 1
        assert available(conn, t) == ref.available(t), (t, available(conn, t), ref.available(t))
        sold = {row[0] for row in conn.execute("SELECT seat_id FROM seats WHERE status = 'SOLD'")}
        ref_sold = set().union(*[h['seats'] for h in ref.holds.values() if h['state'] == 'CONFIRMED'])
        assert sold == ref_sold
        confirmed = [h['seats'] for h in ref.holds.values() if h['state'] == 'CONFIRMED']
        assert sum(map(len, confirmed)) == len(ref_sold), 'a seat sold twice'
    try:
        hold(conn, 'u', [], t, 5, 'empty')
        raise AssertionError('empty hold accepted')
    except ValueError:
        pass

# the race walk-throughs, deterministically
conn = new_db(':memory:', 4)
a = hold(conn, 'A', ['s01', 's02'], 0, 10, 'a')
assert a and hold(conn, 'B', ['s02', 's03'], 0, 10, 'b') is None
assert available(conn, 0) == 2                                      # B's partial update on s03 was rolled back
b = hold(conn, 'B', ['s01'], 10, 10, 'b2')                          # A expired at 10, B takes s01
assert b and confirm(conn, a, 11) is False and confirm(conn, b, 11) is True and confirm(conn, b, 99) is True
assert hold(conn, 'A', ['s01', 's02'], 0, 10, 'a') == a             # same key: same answer

# 16 threads, one database file: no seat ever confirmed to two holds
tmp = tempfile.mkdtemp()
path = os.path.join(tmp, 'inv.db')
new_db(path, 30).close()
t0 = time.monotonic()
clock = lambda: int((time.monotonic() - t0) * 1000)                  # one shared clock, in ms
wins, errs, glock = [], [], threading.Lock()
def buyer(w):
    rnd = random.Random(w)
    conn = sqlite3.connect(path, timeout=60, isolation_level=None, check_same_thread=False)
    try:
        for j in range(40):
            want = rnd.sample(['s%02d' % i for i in range(30)], rnd.randint(1, 3))
            hid = hold(conn, 'w%d' % w, want, clock(), rnd.randint(1, 15), 'w%d-%d' % (w, j))
            if hid and rnd.random() < 0.7:
                if rnd.random() < 0.3:
                    time.sleep(0.01)                                   # a slow payment: the hold may expire
                if confirm(conn, hid, clock()):
                    with glock:
                        wins.append((hid, set(want)))
            elif hid:
                release(conn, hid)
    except Exception as e:
        with glock:
            errs.append(repr(e))
    finally:
        conn.close()
ts = [threading.Thread(target=buyer, args=(w,)) for w in range(16)]
[x.start() for x in ts]
[x.join() for x in ts]
assert not errs, errs[:3]
allseats = [s for _, ss in wins for s in ss]
assert len(allseats) == len(set(allseats)), 'a seat was confirmed to two holds'
conn = sqlite3.connect(path, isolation_level=None)
sold = {r[0] for r in conn.execute("SELECT seat_id FROM seats WHERE status = 'SOLD'")}
assert sold == set(allseats)
for hid, ss in wins:
    assert {r[0] for r in conn.execute('SELECT seat_id FROM seats WHERE hold_id = ?', (hid,))} == ss
conn.close()

# ---------------- general admission counter vs a scan of all holds
ga_ops = 0
for trial in range(400):
    initial = random.randint(0, 20)
    limit = random.choice([None, None, 1, 2])
    ga = GaCounter(initial, reclaim_limit=limit)
    holds, sold, t, hid = {}, 0, 0, 0
    for _ in range(80):
        r = random.random()
        if r < 0.5:
            hid += 1
            q, ttl = random.randint(1, 5), random.randint(1, 6)
            room = initial - sold - sum(h[0] for h in holds.values() if h[2] == 'ACTIVE' and h[1] > t)
            got = ga.hold(hid, q, t, ttl)
            if limit is None:
                assert got == (room >= q), (room, q, got)
            elif got:
                assert room >= q, 'oversold'
            if got:
                holds[hid] = [q, t + ttl, 'ACTIVE']
        elif r < 0.75 and holds:
            h = random.choice(list(holds))
            expect = holds[h][2] == 'ACTIVE' and holds[h][1] > t
            assert ga.confirm(h, t) == expect
            if expect:
                holds[h][2] = 'SOLD'
                sold += holds[h][0]
        else:
            t += random.randint(0, 3)
        ga_ops += 1
        assert ga.stock >= 0 and ga.sold == sold
        assert ga.stock + sum(ga.qty.values()) + ga.sold == initial, 'units created or lost'

print('sy42 code checks passed (%d SQL operations, %d threaded confirms, %d GA operations)' % (ops, len(wins), ga_ops))
