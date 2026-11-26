"""Runs the python blocks from data/new_lessons/sy51-scaling-patterns-reads-writes.md against independent references:
the replica-routing replay against a per-read brute force, the batching model against an event simulation, the
hot-key placement against a second implementation plus conservation checks, the contention models against full
enumeration, and every number the lesson prints."""
import re, sys, math, random, hashlib, itertools

src = open(sys.argv[1], encoding='utf-8').read()
ns = {}
for b in re.findall(r"```python\n(.*?)```", src, re.S):
    exec(b, ns)

def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the computed figure: %r' % p

# ---------------------------------------------------------------- reads: replicas and read-your-writes
applied_version, make_workload, run_policy = ns['applied_version'], ns['make_workload'], ns['run_policy']

# applied_version against a plain count
for commits in ([], [5], [5, 5, 9], [1, 2, 3, 40, 41, 100]):
    for lag in (0, 10, 50):
        for t in range(-5, 130):
            assert applied_version(commits, lag, t) == sum(1 for c in commits if c + lag <= t), (commits, lag, t)

def ref_run(events, lags, policy, window_ms=0):
    """Independent replay: no bisect, no shared helpers; the write list is scanned per read."""
    writes = []                                 # (commit time, version)
    mine = {}                                   # session -> (version, time) of its last write
    n = len(lags)
    counter = 0
    reads = bad = prim = 0
    for t, s, k in events:
        if k == 'w':
            counter += 1
            writes.append((t, counter))
            mine[s] = (counter, t)
            continue
        def seen_by(replica):
            return max([v for (ct, v) in writes if ct + lags[replica] <= t] or [0])
        need_v = mine[s][0] if s in mine else 0
        idx = reads % n                          # the round robin position is the read counter
        reads += 1
        if policy == 'primary':
            got, p = counter, 1
        elif policy == 'any':
            got, p = seen_by(idx), 0
        elif policy == 'pin':
            if s in mine and t - mine[s][1] < window_ms:
                got, p = counter, 1
            else:
                got, p = seen_by(idx), 0
        else:
            got, p = None, 0
            for j in range(n):
                cand = (idx + j) % n
                if seen_by(cand) >= need_v:
                    got = seen_by(cand)
                    break
            if got is None:
                got, p = counter, 1
        bad += 1 if got < need_v else 0
        prim += p
    return reads, bad, prim

checked = 0
for seed in (1, 7, 42):
    for lags in ([10, 50, 200], [0, 30], [100], [5, 5, 5, 400]):
        ev = make_workload(sessions=8, ops=25, write_share=0.3, span_ms=3000, seed=seed)
        for pol, kw in (('primary', {}), ('any', {}), ('pin', {'window_ms': 0}), ('pin', {'window_ms': 60}),
                        ('pin', {'window_ms': 500}), ('token', {})):
            assert run_policy(ev, lags, pol, **kw) == ref_run(ev, lags, pol, **kw), (seed, lags, pol, kw)
            checked += 1
assert checked == 72

ev = make_workload()
lags = [10, 50, 200]
tab = {}
for name, kw in (('primary', {}), ('any', {}), ('pin50', {'window_ms': 50}), ('pin200', {'window_ms': 200}), ('token', {})):
    pol = 'pin' if name.startswith('pin') else name
    tab[name] = run_policy(ev, lags, pol, **kw)
reads = tab['primary'][0]
assert reads == 587 and all(v[0] == reads for v in tab.values())
assert tab['primary'][1] == 0 and tab['token'][1] == 0 and tab['pin200'][1] == 0       # no stale own-writes
assert tab['any'][1] > tab['pin50'][1] > 0                                              # a window below the worst lag still leaks
assert tab['primary'][2] == reads and tab['any'][2] == 0
assert tab['token'][2] < tab['pin200'][2] < reads                                       # the token pins far fewer reads
# widening the window never adds violations, and a zero window is plain round robin
prev = None
for w in range(0, 301, 25):
    v = run_policy(ev, lags, 'pin', window_ms=w)[1]
    assert prev is None or v <= prev
    prev = v
assert run_policy(ev, lags, 'pin', window_ms=0) == run_policy(ev, lags, 'any')
# a replica with no lag is never stale
assert run_policy(ev, [0], 'any')[1] == 0
def pct(x):
    return '%.2f%%' % (100.0 * x / reads)
for name, label in (('primary', 'primary only'), ('any', 'any replica'), ('pin50', 'primary for 50 ms after a write'),
                    ('pin200', 'primary for 200 ms after a write'), ('token', 'replica that has the write')):
    need('| %s | %s | %s |' % (label, pct(tab[name][1]), pct(tab[name][2])))
need('587 reads', '46 of the 587')

# ---------------------------------------------------------------- writes: batching
batch_shape, cost_per_second = ns['batch_shape'], ns['cost_per_second']

def sim_batches(gap, batch_records, linger, horizon=100_000):
    """Event simulation of the same producer: returns (records per batch, mean added delay) from real batches."""
    batches, cur = [], []                      # each batch is the list of its records' arrival times
    deadline = None
    for t in range(0, horizon, gap):
        if cur and linger > 0 and t >= deadline:
            batches.append((deadline, cur)); cur = []
        cur.append(t)
        if len(cur) == 1:
            deadline = t + linger
        if len(cur) == batch_records or linger <= 0:
            batches.append((t, cur)); cur = []
    sizes = {len(b) for _, b in batches[:-1]}
    delays = [sum(sent - a for a in b) / len(b) for sent, b in batches[:-1]]
    return sizes, delays

for gap in (1, 2, 3, 5):
    for B in (1, 4, 16):
        for L in (0, 1, 2, 5, 7, 10, 50):
            n, d = batch_shape(gap, B, L)
            sizes, delays = sim_batches(gap, B, L)
            assert sizes == {n}, (gap, B, L, sizes, n)
            assert all(abs(x - d) < 1e-9 for x in delays), (gap, B, L, d, set(delays))
assert batch_shape(1, 16, 5) == (5, 3.0) and batch_shape(1, 16, 50) == (16, 7.5) and batch_shape(1, 16, 0) == (1, 0.0)
assert cost_per_second(1000, 1, 200, 5) == 205000 and cost_per_second(1000, 5, 200, 5) == 45000
rows = [(L,) + batch_shape(1, 16, L) for L in (0, 2, 5, 10, 50)]
for L, n, d in rows:
    need('| %d | %d | %d | %s | %s |' % (L, n, 1000 // n, ('%.1f' % d).rstrip('0').rstrip('.') if d % 1 else '%d' % d,
                                       '%g' % (cost_per_second(1000, n, 200, 5) / 1000)))
# more linger never raises the request rate or lowers the delay (until the batch is full)
last = None
for L in range(0, 60):
    n, d = batch_shape(1, 16, L)
    if last:
        assert n >= last[0]
    last = (n, d)

burst_backlog, coalesced_write_rate = ns['burst_backlog'], ns['coalesced_write_rate']
def tick_backlog(base, burst, burst_s, capacity):
    q = peak = 0.0
    t = 0
    for _ in range(100_000):
        rate = burst if t < burst_s else base
        q = max(0.0, q + rate - capacity)
        peak = max(peak, q)
        t += 1
        if t > burst_s and q == 0:
            return peak, t - burst_s
    return peak, None
assert burst_backlog(2000, 10000, 30, 4000) == (180000, 90.0, 45.0)
pk, drain = tick_backlog(2000, 10000, 30, 4000)
assert pk == 180000 and drain == 90                                   # the tick simulation agrees with the formula
assert burst_backlog(2000, 10000, 30, 2000)[1:] == (None, None) and burst_backlog(2000, 1000, 30, 4000) == (0, 0.0, 0.0)
assert coalesced_write_rate(50, 1) == 50 and coalesced_write_rate(50, 5) == 10
need('180,000', '90 s', '45 s')

# ---------------------------------------------------------------- writes: skewed keys
zipf_rates, place, partition_loads = ns['zipf_rates'], ns['place'], ns['partition_loads']
splits_needed, split_plan, hottest_over_mean = ns['splits_needed'], ns['split_plan'], ns['hottest_over_mean']
write_units, read_units, max_item_rate = ns['write_units'], ns['read_units'], ns['max_item_rate']

rates = zipf_rates(100_000, 50_000, 1.0)
assert len(rates) == 100_000 and abs(sum(rates) - 50_000) < 1e-6
assert all(rates[i] >= rates[i + 1] for i in range(len(rates) - 1))
assert abs(rates[0] - 50_000 / sum(1 / i for i in range(1, 100_001))) < 1e-9
for i in range(0, 30):                                                     # placement is stable and in range
    assert place('key%d' % i, 128) == int.from_bytes(hashlib.md5(('key%d' % i).encode()).digest()[:8], 'big') % 128

def ref_loads(rates, P, plan):
    out = {}
    for i, r in enumerate(rates):
        n = plan.get(i, 1)
        names = ['key%d' % i] if n == 1 else ['key%d#%d' % (i, j) for j in range(n)]
        for nm in names:
            p = int.from_bytes(hashlib.md5(nm.encode()).digest()[:8], 'big') % P
            out[p] = out.get(p, 0.0) + r / len(names)
    return [out.get(p, 0.0) for p in range(P)]

small = zipf_rates(500, 1000, 1.2)
for P in (4, 16, 64):
    for thr in (400, 100, 25):
        plan = split_plan(small, thr)
        got, want = partition_loads(small, P, plan), ref_loads(small, P, plan)
        assert all(abs(a - b) < 1e-9 for a, b in zip(got, want))
        assert abs(sum(got) - 1000) < 1e-6                                 # splitting moves load, it never creates or loses it
        assert all(small[i] / n <= thr + 1e-9 for i, n in plan.items())    # every sub-key is under the threshold
        assert all(small[i] <= thr for i in range(len(small)) if i not in plan)
assert splits_needed(4135.6, 1000) == 5 and splits_needed(1000, 1000) == 1 and splits_needed(1000.01, 1000) == 2 and splits_needed(3, 1000) == 1
assert hottest_over_mean([5, 5, 5, 5]) == 1.0 and hottest_over_mean([10, 0, 0, 0]) == 4.0

P = 128
plain = partition_loads(rates, P)
assert abs(max(plain) - 4349) < 1 and round(hottest_over_mean(plain), 2) == 11.13
table = []
for thr in (None, 1000, 500, 250, 125):
    plan = split_plan(rates, thr) if thr else {}
    load = partition_loads(rates, P, plan)
    assert abs(sum(load) - 50_000) < 1e-6
    table.append((thr, len(plan), sum(plan.values()), max(load), hottest_over_mean(load), sum(1 for x in load if x > 1000)))
assert table[0][3] > table[-1][3]                                          # splitting does lower the peak
assert table[2][5] >= 1 and table[3][5] == 0 and table[4][5] == 0          # splitting at the limit is not enough; a quarter of it is
assert table[1][3] > 1000 and table[3][3] < 1000
for thr, nkeys, nsub, mx, ratio, over in table:
    need('| %s | %d | %d | %d | %.2f | %d |' % ('no split' if thr is None else 'above %d/s' % thr, nkeys, nsub, round(mx), ratio, over))
# DynamoDB figures from the documentation page: 1,000 write units and 3,000 read units per partition
assert write_units(1) == 1 and write_units(1.0001) == 2 and write_units(3) == 3
assert read_units(4) == 1 and read_units(20) == 5 and read_units(20, consistent=False) == 2.5 and read_units(0.5) == 1
assert max_item_rate(3000, read_units(20)) == 600 and max_item_rate(1000, write_units(3)) == 333
need('600', '333')

# ---------------------------------------------------------------- contention
rmw_outcomes, optimistic_attempts, shards_needed = ns['rmw_outcomes'], ns['optimistic_attempts'], ns['shards_needed']

def ref_outcomes(n):
    """Independent enumeration: recursive over which client moves next, no permutations."""
    out = {}
    def go(state, value, held, count):
        if all(s == 2 for s in state):
            out[value] = out.get(value, 0) + 1
            return
        for c in range(n):
            if state[c] == 0:
                go(state[:c] + (1,) + state[c + 1:], value, held[:c] + (value,) + held[c + 1:], count)
            elif state[c] == 1:
                go(state[:c] + (2,) + state[c + 1:], held[c] + 1, held, count)
    go((0,) * n, 0, (0,) * n, 0)
    return out
for n in (1, 2, 3, 4):
    got = dict(rmw_outcomes(n))
    assert got == ref_outcomes(n), (n, got)
    assert sum(got.values()) == math.factorial(2 * n) // 2 ** n                  # (2n)! / 2^n valid interleavings
    assert got[n] == math.factorial(n)                                          # only the serial-equivalent orders reach n
    assert max(got) == n and min(got) == 1
assert dict(rmw_outcomes(2)) == {1: 4, 2: 2} and dict(rmw_outcomes(3)) == {1: 48, 2: 36, 3: 6}
need('4 of the 6', '48', '36')

for n in range(1, 40):
    for S in (1, 2, 3, 5, 8):
        rounds, attempts = optimistic_attempts(n, S)
        sizes = [len(range(s, n, S)) for s in range(S)]
        assert rounds == max(sizes) == math.ceil(n / S)
        assert attempts == sum(m * (m + 1) // 2 for m in sizes), (n, S)
assert optimistic_attempts(100, 1) == (100, 5050) and optimistic_attempts(100, 10) == (10, 550)
assert optimistic_attempts(10, 1) == (10, 55) and optimistic_attempts(10, 5) == (2, 15)
for n, S, r, a in ((10, 1, 10, 55), (10, 2, 5, 30), (10, 5, 2, 15), (100, 1, 100, 5050), (100, 10, 10, 550)):
    need('| %d | %d | %d | %d |' % (n, S, r, a))
assert shards_needed(ns['coalesced_write_rate'](50, 1), 1) == 50 and shards_needed(5000, 1) == 5000 and shards_needed(5000, 1000) == 5 and shards_needed(5001, 1000) == 6 and shards_needed(1, 1000) == 1
need('5,000 shards')

# figures quoted in the prose and the drills
assert round(rates[0]) == 4136 and round(50_000 / 128) == 391 and round(rates[0] / 5) == 827
assert split_plan(rates, 125)[0] == 34 and splits_needed(rates[0], 1000) == 5
need('4,136', '391', '827', '34 ways', '11 times the mean')
assert burst_backlog(3500, 9000, 20, 4000) == (100000, 200.0, 25.0)
assert optimistic_attempts(1000)[1] == 500500
need('5,050', '500,500' if False else 'half a million')

print('sy51 code checks passed')
