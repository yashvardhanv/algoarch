"""Runs the python blocks of the sy73 price-tracker lesson: the polling-interval allocation against random feasible
alternatives and a perturbation test, the observation filter (confirmation and validity) against a direct definition,
the alert state machine with re-arming against an independent definition, the sorted threshold index against a scan,
and the change-only price history against a full per-tick series."""
import re, sys, random, math

src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
assert len(blocks) >= 3, 'expected the lesson code blocks'
ns = {}
for b in blocks:
    exec(b, ns)
intervals, stale_cost = ns['intervals'], ns['stale_cost']
Tracker, Alert, ThresholdIndex, History, PriceBook = ns['Tracker'], ns['Alert'], ns['ThresholdIndex'], ns['History'], ns['PriceBook']


def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the checked figure: %r' % p


def forbid(*phrases):
    for p in phrases:
        assert p not in src, 'lesson text still contains stale wording: %r' % p


rng = random.Random(73)

# ---- 1. polling intervals ---------------------------------------------------------------------------------------------
w = [1, 4, 16, 100]
iv = intervals(w, 1.0, 0.25, 24)
assert [round(x, 4) for x in iv] == [17.0, 8.5, 4.25, 1.7], iv                     # I = K / sqrt(w), K = sum(sqrt w) / budget
assert abs(sum(1 / x for x in iv) - 1.0) < 1e-9
assert round(stale_cost(w, iv), 6) == 144.5 and stale_cost(w, [4, 4, 4, 4]) == 242.0
MORE = round(100 * (242.0 / 144.5 - 1))                                             # equal polling costs 67 percent MORE ...
LESS = round(100 * (1 - 144.5 / 242.0))                                             # ... the optimum is 40 percent LESS
assert (MORE, LESS) == (67, 40)
try:
    intervals(w, 100.0, 0.25, 24)                                                    # 4 / 0.25 = 16 polls per hour is the most you can spend
    raise SystemExit('an unspendable budget must be refused')
except AssertionError:
    pass
try:
    intervals(w, 0.1, 0.25, 24)                                                      # 4 / 24 per hour is the least you can spend
    raise SystemExit('a budget that cannot be met must be refused')
except AssertionError:
    pass
for trial in range(120):
    n = rng.randint(2, 6)
    ws = [10 ** rng.uniform(-1, 3) for _ in range(n)]
    lo, hi = 0.25, 48.0
    budget = rng.uniform(n / hi * 1.05, n / lo * 0.95)
    opt = intervals(ws, budget, lo, hi)
    assert all(lo - 1e-9 <= x <= hi + 1e-9 for x in opt)
    assert abs(sum(1 / x for x in opt) - budget) < 1e-7 * budget, (sum(1 / x for x in opt), budget)
    best = stale_cost(ws, opt)
    # random feasible alternatives (same total poll rate, within the bounds) never do better
    tried = 0
    for _ in range(400):
        r = [rng.expovariate(1) for _ in range(n)]
        scale = budget / sum(r)
        rates = [x * scale for x in r]
        if all(1 / hi <= x <= 1 / lo for x in rates):
            tried += 1
            assert stale_cost(ws, [1 / x for x in rates]) >= best - 1e-9 * best, (ws, budget)
    # moving a little poll rate from one product to another never helps (local optimality)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            rates = [1 / x for x in opt]
            d = 1e-4 * budget
            if rates[i] - d >= 1 / hi and rates[j] + d <= 1 / lo:
                rates[i] -= d
                rates[j] += d
                assert stale_cost(ws, [1 / x for x in rates]) >= best - 1e-12 * best
# the alternatives the lesson warns about cost more: equal intervals, intervals proportional to 1/w
ws = [1, 4, 16, 100, 400]
budget = 2.0
opt = intervals(ws, budget, 0.01, 1000)
equal = [len(ws) / budget] * len(ws)
k = sum(1 / x for x in [1 / x for x in ws])
prop = [k / budget / x for x in ws]                                                  # interval proportional to 1 / weight
assert abs(sum(1 / x for x in prop) - budget) < 1e-9
assert stale_cost(ws, opt) < stale_cost(ws, equal)
assert stale_cost(ws, opt) < stale_cost(ws, prop)
# bounds bind: the hottest product is held at lo and the quietest at hi
iv = intervals([1, 1000, 1000000], 3.0, 0.5, 24)
assert iv[0] == 24 and iv[2] == 0.5 and 0.5 < iv[1] < 24, iv
assert abs(sum(1 / x for x in iv) - 3.0) < 1e-9
assert round(iv[1], 3) == 1.043, iv

# ---- 2. observation filter ----------------------------------------------------------------------------------------------
def confirmed_ref(obs, confirm):
    """Direct definition: after a first valid price, a new price is confirmed once the last `confirm` valid observations all agree on it."""
    valid, current, out = [], None, []
    for i, p in enumerate(obs):
        if p is None or p <= 0:
            continue
        valid.append(p)
        if current is None:
            current = p
            out.append((i, p))
        elif len(valid) >= confirm and len(set(valid[-confirm:])) == 1 and valid[-1] != current:
            current = valid[-1]
            out.append((i, current))
    return out


def run_tracker(obs, confirm):
    t, out = Tracker(confirm), []
    for i, p in enumerate(obs):
        c = t.observe(p)
        if c is not None:
            out.append((i, c))
    return out


assert run_tracker([100, 100, 90, 90, 90], 2) == [(0, 100), (3, 90)]
assert run_tracker([100, 100, 1, 100, 100], 2) == [(0, 100)]                         # a one-sample glitch is ignored
assert run_tracker([100, 1, 100, 1, 100], 2) == [(0, 100)]                           # and so is a flapping one
assert run_tracker([100, 0, 0, None, 100], 2) == [(0, 100)]                          # parse failures (0, None) are not prices
assert run_tracker([100, 90, 0, 90], 2) == [(0, 100), (3, 90)]                       # a failed parse neither confirms nor resets
assert run_tracker([100, 90, 95, 95], 2) == [(0, 100), (3, 95)]
assert run_tracker([100, 90, 100, 90, 90], 2) == [(0, 100), (4, 90)]                 # going back to the current price clears the pending change
assert run_tracker([None, 100], 2) == [(1, 100)] and run_tracker([], 2) == []
assert run_tracker([100, 90], 1) == [(0, 100), (1, 90)]
assert run_tracker([100, 90, 90, 90, 80, 80, 80], 3) == [(0, 100), (3, 90), (6, 80)]
assert run_tracker([100, 90, 90, 80, 80], 3) == [(0, 100)]
for trial in range(1500):
    n = rng.randint(0, 25)
    obs = [rng.choice([None, 0, 90, 90, 100, 100, 100, 110, 95]) for _ in range(n)]
    c = rng.choice([1, 2, 3])
    assert run_tracker(obs, c) == confirmed_ref(obs, c), (obs, c)

# ---- 3. alerts with re-arming -----------------------------------------------------------------------------------------
def alert_ref(prices, thr, pct):
    """Fire when price <= thr and, since the last fire, the price has been back at or above the re-arm level (or never fired)."""
    rearm = thr + (thr * pct + 99) // 100
    fired = []
    for i, p in enumerate(prices):
        if p > thr:
            continue
        if not fired or any(q >= rearm for q in prices[fired[-1] + 1:i]):
            fired.append(i)
    return fired


def run_alert(prices, thr, pct):
    a, out = Alert(thr, pct), []
    for i, p in enumerate(prices):
        if a.on_price(p):
            out.append(i)
    return out


assert run_alert([12000, 9900, 9800, 10100, 9900], 10000, 5) == [1]                  # 101.00 does not re-arm: needs 105.00
assert run_alert([12000, 9900, 10600, 9900], 10000, 5) == [1, 3]
assert run_alert([10000], 10000, 5) == [0] and run_alert([10001], 10000, 5) == []    # the threshold itself fires
assert run_alert([9000, 10500, 9000], 10000, 5) == [0, 2]                            # exactly the re-arm level re-arms
assert run_alert([9000, 10499, 9000], 10000, 5) == [0]
assert Alert(10000, 5).rearm_at == 10500 and Alert(999, 5).rearm_at == 999 + 50       # ceil(49.95)
for trial in range(2000):
    n = rng.randint(0, 30)
    prices = [rng.choice([9000, 9500, 9900, 10000, 10100, 10400, 10500, 10600, 12000]) for _ in range(n)]
    pct = rng.choice([1, 3, 5, 10])
    assert run_alert(prices, 10000, pct) == alert_ref(prices, 10000, pct), (prices, pct)

# glitches through the whole pipeline: one bad sample fires a naive alert but not the confirmed one
series = [10200, 10200, 1, 10200, 10200, 9500, 9500, 9500]
naive = run_alert(series, 10000, 5)
trk = Tracker(2)
cond = []
al = Alert(10000, 5)
for p in series:
    c = trk.observe(p)
    if c is not None and al.on_price(c):
        cond.append(p)
assert naive == [2] and cond == [9500]
# the confirmed alert is one poll later than the naive one for a real drop
assert [i for i, _ in run_tracker([10200, 9500, 9500], 2)] == [0, 2]

# ---- 4. threshold index -------------------------------------------------------------------------------------------------
idx = ThresholdIndex()
for thr, uid in [(100, 1), (90, 2), (100, 3), (95, 4), (80, 5)]:
    idx.add(thr, uid)
assert idx.crossed(110, 95) == [4, 1, 3] and idx.crossed(100, 90) == [2, 4]          # [new, old): 100 was already met at old=100
assert idx.crossed(100, 100) == [] and idx.crossed(90, 100) == []                    # no drop, no crossing
assert idx.crossed(81, 80) == [5] and idx.crossed(80, 79) == [] and idx.crossed(1000, 0) == [5, 2, 4, 1, 3]
idx.remove(95, 4)
assert idx.crossed(110, 95) == [1, 3]
idx.remove(95, 4)                                                                    # removing twice is harmless
for trial in range(300):
    ix, rows = ThresholdIndex(), []
    for u in range(rng.randint(0, 40)):
        thr = rng.randint(80, 120)
        ix.add(thr, u)
        rows.append((thr, u))
    for r in rng.sample(rows, k=min(len(rows), rng.randint(0, 5))):
        ix.remove(*r)
        rows.remove(r)
    for _ in range(30):
        old, new = rng.randint(70, 130), rng.randint(70, 130)
        want = [u for thr, u in sorted(rows) if new <= thr < old]
        assert ix.crossed(old, new) == want, (old, new)
ids = ThresholdIndex()
for u in (10, 9):
    ids.add(100, u)
assert ids.crossed(101, 100) == [9, 10]                                              # numeric order within a threshold

# ---- 5. change-only price history ------------------------------------------------------------------------------------------
h = History()
assert h.record(0, 100) and not h.record(5, 100) and h.record(10, 90) and h.record(20, 95)
assert h.ts == [0, 10, 20] and h.ps == [100, 90, 95]
assert h.at(-1) is None and h.at(0) == 100 and h.at(9) == 100 and h.at(10) == 90 and h.at(500) == 95
assert h.lowest(12, 15) == 90 and h.lowest(0, 9) == 100 and h.lowest(0, 10) == 90 and h.lowest(21, 30) == 95
assert h.lowest(-9, -1) is None
try:
    h.record(15, 50)
    raise SystemExit('an observation older than the last change must be refused')
except ValueError:
    pass
assert h.record(20, 96) and h.at(20) == 96 and h.ts == [0, 10, 20, 20]               # equal timestamps are accepted (not out of order)
assert h.lowest(20, 20) == 96
for trial in range(400):
    hist, full, price = History(), {}, None
    for t in range(60):
        if rng.random() < 0.15 or price is None:
            price = rng.choice([80, 85, 90, 95, 100, 105, 110])
        hist.record(t, price)
        full[t] = price
    assert len(hist.ts) <= 60
    for _ in range(40):
        a = rng.randint(0, 59)
        b = rng.randint(a, 59)
        assert hist.at(a) == full[a]
        assert hist.lowest(a, b) == min(full[t] for t in range(a, b + 1)), (a, b)
CHANGES = len(hist.ts)

# ---- 6. the whole pipeline: raw observations -> Tracker -> PriceBook (two sorted indexes), against one Alert machine per user ----
def book_run(events, pct):
    """events: ('obs', raw price) or ('add', uid, thr) or ('del', uid). Returns [(event index, uid)] in firing order."""
    trk, book, out = Tracker(2), PriceBook(pct), []
    for k, ev in enumerate(events):
        if ev[0] == 'obs':
            c = trk.observe(ev[1])
            if c is not None:
                out += [(k, u) for u in sorted(book.on_change(c))]
        elif ev[0] == 'add':
            if book.add(ev[1], ev[2]):
                out.append((k, ev[1]))
        else:
            book.remove(ev[1])
    return out


def ref_run(events, pct):
    """One independent Alert machine per user, fed the price in force when it was created and every later confirmed change."""
    changes = confirmed_ref([e[1] for e in events if e[0] == 'obs'], 2)
    obs_pos = [k for k, e in enumerate(events) if e[0] == 'obs']
    change_at = {obs_pos[i]: p for i, p in changes}                  # event index -> confirmed price
    cur, alerts, out = None, {}, []
    for k, ev in enumerate(events):
        if ev[0] == 'add':
            alerts[ev[1]] = Alert(ev[2], pct)
            if cur is not None and alerts[ev[1]].on_price(cur):
                out.append((k, ev[1]))
        elif ev[0] == 'del':
            alerts.pop(ev[1], None)
        elif k in change_at:
            cur = change_at[k]
            for u in sorted(alerts):
                if alerts[u].on_price(cur):
                    out.append((k, u))
    return out


# the reviewer's probe: target 100.00, confirmed prices 120.00, 99.00, 110.00, 99.00 -> two alerts, not one
ev = [('add', 1, 10000)] + [('obs', p) for p in (12000, 12000, 9900, 9900, 11000, 11000, 9900, 9900)]
assert book_run(ev, 5) == [(4, 1), (8, 1)] == ref_run(ev, 5), book_run(ev, 5)
# an alert created while the price is already at or below its target fires at once
ev = [('obs', 9000), ('obs', 9000), ('add', 1, 10000)]
assert book_run(ev, 5) == [(2, 1)] == ref_run(ev, 5)
b = PriceBook(5)
assert b.add(1, 10000) is False and b.on_change(9000) == [1] and b.add(2, 9000) is True and b.add(3, 8999) is False
assert b.on_change(10499) == [] and b.on_change(10500) == []                      # re-arming fires nothing by itself
# an alert added before any price is known fires on the first price at or below it
ev = [('add', 1, 10000), ('add', 2, 8000), ('obs', 9500), ('obs', 9500)]
assert book_run(ev, 5) == [(2, 1)] == ref_run(ev, 5)         # the first valid reading is the baseline, so it fires at once
# a deleted alert never fires; a re-armed alert that is deleted while disarmed leaves no index entry behind
ev = [('add', 1, 10000), ('obs', 9000), ('obs', 9000), ('del', 1), ('obs', 11000), ('obs', 11000), ('obs', 9000), ('obs', 9000)]
assert book_run(ev, 5) == [(1, 1)] == ref_run(ev, 5)
b = PriceBook(5)
b.add(1, 10000)
b.on_change(9000)
b.remove(1)
assert b.armed.t == [] and b.disarmed.t == [] and b.alerts == {}
for trial in range(1500):
    pct = rng.choice([1, 3, 5, 10])
    events, live = [], []
    for _ in range(rng.randint(1, 40)):
        r = rng.random()
        if r < 0.22:
            u = rng.randint(0, 7)
            if u not in live:
                live.append(u)
                events.append(('add', u, rng.choice([9000, 9500, 10000, 10000, 10500])))
        elif r < 0.28 and live:
            events.append(('del', live.pop(rng.randrange(len(live)))))
        else:
            p = rng.choice([8900, 9000, 9500, 9900, 10000, 10100, 10500, 10600, 11000, None, 0])
            events += [('obs', p)] * rng.choice([1, 2, 2, 3])
    assert book_run(events, pct) == ref_run(events, pct), (events, pct)
# index entries are consistent: every live alert is in exactly one of the two indexes
b = PriceBook(5)
for u in range(6):
    b.add(u, 9000 + 300 * u)
for p in (9500, 9000, 11000, 8000, 10600, 9800):
    b.on_change(p)
    assert sorted([u for _, u in b.armed.t] + [u for _, u in b.disarmed.t]) == sorted(b.alerts)
    assert len(b.armed.t) + len(b.disarmed.t) == len(b.alerts)
try:
    Alert(10000, 0)
    raise SystemExit('a zero re-arm margin must be refused')
except AssertionError:
    pass

# honest limit: a price that changes at every poll never confirms
assert run_tracker([100, 90, 95, 85, 92, 88], 2) == [(0, 100)]

need('Visual (planned)', '144.5', '242', '67 percent more', 'about 40 percent cheaper', '17, 8.5, 4.25 and 1.7 hours', 'intervals 24, 1.043 and 0.5 hours', 'fire once (at 99.00)', 'fire twice', 'RFC 9309', 'RFC 9110', '120 random instances', '1,500 random observation sequences', '2,000 random sequences', '300 random indexes', '400 random histories')
forbid('CamelCamelCamel uses', 'Keepa uses', 'Amazon blocks', 'Google Shopping uses')
print('sy73 code checks passed')
