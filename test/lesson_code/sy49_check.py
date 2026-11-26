"""Runs the python blocks from data/new_lessons/sy49-overload-load-shedding.md against reference checks: the retry-loop
simulator against an independent implementation and against the arithmetic published in the metastable-failure
paper, the SRE book's overload figures, and every number the lesson prints."""
import re, sys, math, itertools

src = open(sys.argv[1], encoding='utf-8').read()
ns = {}
for b in re.findall(r"```python\n(.*?)```", src, re.S):
    exec(b, ns)

def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the computed figure: %r' % p

# ---------------------------------------------------------------- arithmetic from the papers and the SRE book
assert ns['stable_load_limit'](300) == 150 and ns['stable_load_limit'](300, 3) == 100
assert ns['extra_retry_room'](300, 280) == 20
assert round(ns['cache_loss_amplification'](0.9), 6) == 10 and round(ns['cache_loss_amplification'](0.99), 6) == 100
share = ns['bimodal_goodput_share']
assert round(share(1000, 1000, 0.1, 0.05, 100), 4) == 0.1963 and round(1 - share(1000, 1000, 0.1, 0.05, 100), 3) == 0.804
assert share(1000, 1000, 0.1, 0.05, 10) == 1.0 and share(1000, 1000, 0.1, 0.05, 1) == 1.0
assert share(1000, 1000, 0.1, 0.0, 100) == 1.0 and 0 < share(1000, 1000, 0.1, 0.5, 100) < 0.02
assert abs(ns['queue_wait'](100, 10, 0.1) - 1.1) < 1e-12 and abs(ns['queue_wait'](0, 10, 0.1) - 0.1) < 1e-12
assert ns['max_load_for_recovery'](10000, 0.1) == 1000 and ns['max_load_for_recovery'](10000, 1.0) == 10000
need('19.6%', '80.4%', '1.1 seconds', '1,000 QPS')

# rejecting is not free
g = ns['goodput_with_rejection_cost']
assert g(500, 1000, 0.5) == 500 and g(1000, 1000, 0.5) == 1000
assert g(1500, 1000, 0.5) == 500 and g(2000, 1000, 0.5) == 0 and g(3000, 1000, 0.5) == 0
assert [round(g(o * 1000, 1000, 0.1)) for o in (1, 1.5, 2, 3)] == [1000, 944, 889, 778]
assert g(2000, 1000, 0.0) == 1000                                          # free rejection: goodput holds at capacity
for r in (0.05, 0.3, 0.7):
    a = g(2500, 1000, r)
    assert a <= 1000 + 1e-9 and a + r * (2500 - a) <= 1000 + 1e-9 or a == 0   # the work it does fits in the capacity
need('| 1,000 | 944 | 889 | 778 |', '| 1,000 | 500 | 0 | 0 |')

# adaptive throttling reproduces the two statements in the SRE book
s2, a2 = ns['throttle_equilibrium'](3000, 1000, k=2.0)
s11, a11 = ns['throttle_equilibrium'](3000, 1000, k=1.1)
assert round(s2) == 2000 and round(a2) == 1000 and round(s2 - a2) == 1000          # one rejection per accepted request
assert round(s11) == 1100 and round(a11) == 1000 and round(s11 - a11) == 100       # one rejection per ten accepted
s_ok, a_ok = ns['throttle_equilibrium'](800, 1000, k=2.0)
assert (round(s_ok), round(a_ok)) == (800, 800)                                    # below capacity it does nothing
need('2,000', '1,100')

# criticality shedding
plan = ns['shed_plan']
off = {'CRITICAL_PLUS': 13, 'CRITICAL': 52, 'SHEDDABLE_PLUS': 39, 'SHEDDABLE': 26}
p = plan(off, 100)
assert p == {'CRITICAL_PLUS': 13, 'CRITICAL': 52, 'SHEDDABLE_PLUS': 20, 'SHEDDABLE': 0}, p
assert plan({k: v * 0.2 for k, v in off.items()}, 100) == {k: v * 0.2 for k, v in off.items()}
order = list(ns['THRESHOLDS'])
for _ in range(200):
    import random
    rr = random.Random(_)
    o = {c: rr.uniform(0, 80) for c in order}
    cap = rr.uniform(20, 200)
    q = plan(o, cap)
    assert sum(q.values()) <= cap + 1e-9 and all(0 <= q[c] <= o[c] + 1e-9 for c in order)
    for hi, lo in itertools.combinations(order, 2):                     # a lower class is never admitted past a rejected higher one
        if q[hi] < o[hi] - 1e-9:
            assert q[lo] == 0, (o, cap, q)
need('| CRITICAL_PLUS | 13 | 13 |', '| SHEDDABLE | 26 | 0 |')

# ---------------------------------------------------------------- the retry-loop simulator against an independent one
simulate, recovery_seconds = ns['simulate'], ns['recovery_seconds']

def ref_simulate(load, capacity, timeout, retries, lifo, drop_stale, outage, seconds, dt=0.1):
    """Same model, different data structures: lists of dicts, an explicit check pointer, min/max by sequence number."""
    requests, entries, goodput = [], [], [0] * seconds
    seq, checked, carry, tokens = 0, 0, 0.0, 0.0
    for i in range(int(round(seconds / dt))):
        now = i * dt
        qps = load(now) if callable(load) else load
        mode = retries(now) if callable(retries) else retries
        carry += qps * dt
        n = int(carry)
        carry -= n
        for _ in range(n):
            r = {'t0': now, 'done': False}
            requests.append(r)
            entries.append({'seq': seq, 'req': r, 'sent': now})
            seq += 1
            if isinstance(mode, tuple):
                tokens = min(tokens + mode[1], 100.0)
        while checked < len(requests) and now - requests[checked]['t0'] >= timeout - 1e-9:
            r = requests[checked]
            checked += 1
            if r['done'] or mode == 'none':
                continue
            if isinstance(mode, tuple):
                if tokens < 1:
                    continue
                tokens -= 1
            entries.append({'seq': seq, 'req': r, 'sent': now})
            seq += 1
        budget = 0 if outage[0] <= now < outage[1] else int(round(capacity * dt))
        while budget and entries:
            e = max(entries, key=lambda x: x['seq']) if lifo else min(entries, key=lambda x: x['seq'])
            entries.remove(e)
            if drop_stale and (now - e['sent'] >= timeout or e['req']['done']):
                continue
            budget -= 1
            if not e['req']['done'] and now - e['sent'] < timeout:
                e['req']['done'] = True
                goodput[int(now)] += 1
    return goodput

checked_runs = 0
for load, cap, mode, lifo, stale in itertools.product((40, 130, 220), (60, 150), ('none', 'unlimited', ('budget', 0.1)),
                                                      (False, True), (False, True)):
    kw = dict(capacity=cap, timeout=1.0, retries=mode, lifo=lifo, drop_stale=stale, outage=(4, 7), seconds=18)
    got = simulate(load, **kw)
    want = ref_simulate(load, cap, 1.0, mode, lifo, stale, (4, 7), 18)
    assert got == want, (load, cap, mode, lifo, stale)
    checked_runs += 1
assert checked_runs == 72
sw = lambda t: 200 if t < 6 else 60                                     # time-varying load and retry mode
rm = lambda t: 'unlimited' if t < 9 else 'none'
assert simulate(sw, capacity=150, retries=rm, outage=(3, 5), seconds=16) == ref_simulate(sw, 150, 1.0, rm, False, False, (3, 5), 16)

# invariants
steady = simulate(280, outage=(0, 0), seconds=60)
assert steady == [280] * 60
for kw in (dict(), dict(lifo=True), dict(drop_stale=True), dict(retries='none'), dict(retries=('budget', 0.1))):
    gp = simulate(280, outage=(20, 30), seconds=120, **kw)
    assert all(0 <= x <= 300 for x in gp)                               # never more than the capacity per second
    assert sum(gp) <= 280 * 120
assert simulate(280, outage=(20, 30), seconds=40)[21:30] == [0] * 9      # nothing completes while the database is down
assert simulate(50, capacity=100, outage=(0, 0), seconds=10) == [50] * 10 and simulate(0, seconds=5) == [0] * 5

# the model's recovery time for 'no retries' matches the backlog arithmetic: (backlog - one second of work) / spare capacity
backlog = 280 * 10
analytic = (backlog - 300) / (300 - 280)
sim = recovery_seconds(simulate(280, retries='none', outage=(20, 30), seconds=300), 280, 30)
assert abs(sim - analytic) <= 5, (sim, analytic)

# ---------------------------------------------------------------- the paper's thresholds appear in the simulation
tt = ns['trigger_table']()
assert list(tt) == [100, 140, 150, 200, 250, 280] and list(tt[100]) == [1, 2, 5, 10, 30]
for d in (1, 2, 5, 10, 30):
    assert tt[100][d] is not None and tt[140][d] is not None           # at or below capacity / 2 every outage is survived
    if d >= 2:
        assert tt[150][d] is None and tt[200][d] is None               # at 150 = 300 / 2 a 2 s outage already tips it
    assert tt[250][d] is None and tt[280][d] is None
assert tt[150][1] == 0 and tt[200][1] == 0 and tt[250][1] is None      # a 1 s outage tips it only from 250 up
assert tt[100][1] < tt[100][5] < tt[100][30] and tt[140][5] < tt[140][10] < tt[140][30]
assert tt[140][10] > 5 * tt[100][10]                                    # recovery time blows up near the edge
def cell(v):
    return 'never' if v is None else '%d s' % v
for load, row in tt.items():
    need('| %d | %s |' % (load, ' | '.join(cell(row[d]) for d in (1, 2, 5, 10, 30))))

dt_ = ns['defence_table']()
assert dt_['nothing (FIFO, unlimited retries)'] is None and dt_['retry budget, 10% of new requests'] is None
assert abs(dt_['no retries at all'] - 127) <= 5
assert dt_['serve the newest first (LIFO)'] == 0 and dt_['database skips abandoned queries'] == 0
assert dt_['operator stops retries at t = 60 s'] > 600
assert 100 <= dt_['operator cuts load to 100 QPS from t = 60 s to 200 s'] <= 200
assert dt_['operator cuts load to 140 QPS from t = 60 s to 140 s'] is None
for name, v in dt_.items():
    need('| %s | %s |' % (name, cell(v)))

# ---------------------------------------------------------------- figures in the prose
need('300 QPS', '150 QPS', '20 QPS', '560 QPS', '10x', '5,000')
print('sy49 code checks passed')
