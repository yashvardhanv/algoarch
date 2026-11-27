"""Runs the python blocks of the sy60 online-judge lesson: the output checker against an independent formulation, the
verdict precedence against a ranking reference, a real subprocess runner (wall time, output cap, exit codes, grandchild
holding stdout), the re-measure rule against its closed form, and the judge queue (FIFO and per-user fair) against a
time-stepped reference plus invariants. Figures the lesson prints from the simulations are asserted here."""
import re, sys, random, math, time, os

src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
assert len(blocks) >= 4, 'expected the lesson code blocks'
ns = {}
for b in blocks:
    exec(b, ns)
compare, Limits, Run, verdict = ns['compare'], ns['Limits'], ns['Run'], ns['verdict']
run_case, judged_time, simulate = ns['run_case'], ns['judged_time'], ns['simulate']


def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the checked figure: %r' % p


# ---- 1. output checker -----------------------------------------------------------------------------------------------
assert compare('1 2 3\n', '1 2 3', 'exact') is False and compare('1 2 3\n', '1 2 3\n', 'exact')
assert compare('a b\n\n', 'a b  \r\n', 'lines') and compare('a\nb', 'a\nb\n\n\n', 'lines')
assert not compare('a b', 'a  c', 'lines') and not compare('a\n\nb', 'a\nb', 'lines')      # an inner blank line matters
assert compare('1  2\n3', '1 2 3', 'tokens') and not compare('1 2 3', '1 2', 'tokens') and not compare('1 2', '1 2 3', 'tokens')
assert not compare('1 2 3', '1 2 4', 'tokens') and not compare('', '0', 'tokens') and compare('', '  \n', 'tokens')


def ref_float(e, a, eps):
    """independent formulation: absolute OR relative error, relative to the expected value"""
    es, as_ = e.split(), a.split()
    if len(es) != len(as_):
        return False
    num = re.compile(r'^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$')
    for x, y in zip(es, as_):
        if x == y:
            continue
        if not (num.match(x) and num.match(y)):
            return False
        d = abs(float(x) - float(y))
        if not (d <= eps or d <= eps * abs(float(x))):
            return False
    return True


assert compare('1000000', '1000000.5', 'float') and not compare('1000000', '1000001.5', 'float')     # relative for big values
assert compare('0', '0.0000009', 'float') and not compare('0', '0.000002', 'float')                  # absolute near zero
assert compare('1', '1.000001', 'float', 1e-6) and not compare('1', '1.0000011', 'float', 1e-6)       # boundary on both sides
assert compare('1', '1.5', 'float', 0.5) and not compare('1', '1.5000001', 'float', 0.5)       # exactly on the tolerance is accepted
assert not compare('10', '1_0', 'float') and not compare('1', 'nan', 'float') and not compare('1', 'inf', 'float')
assert compare('nan', 'nan', 'float') and not compare('1', '1 2', 'float') and not compare('abc', 'abd', 'float')
assert not compare('1e0', '1e', 'float') and compare('1e0', '1.0', 'float') and compare('-.5', '-0.5', 'float')
rnd = random.Random(60)
toks = ['0', '1', '-1', '2.5', '1e3', '1000', '1000.0004', '1000.002', '0.0000005', 'x', 'nan', '1_0', '.5', '1e', '+3']
for _ in range(4000):
    n = rnd.choice([0, 1, 2, 3])
    e = ' '.join(rnd.choice(toks) for _ in range(n))
    a = ' '.join(rnd.choice(toks) for _ in range(rnd.choice([n, n, n, 1, 4])))
    assert compare(e, a, 'float', 1e-6) == ref_float(e, a, 1e-6), (e, a)
    assert compare(e, a, 'tokens') == (e.split() == a.split()), (e, a)

# ---- 2. verdict precedence ---------------------------------------------------------------------------------------------
lim = Limits(cpu_s=1.0, mem_kb=65536, out_bytes=1000)
ok = Run(exit_code=0, cpu_s=0.2, peak_kb=1000, out_bytes=10)
assert verdict(ok, '5', '5', lim) == 'AC' and verdict(ok, '5', '6', lim) == 'WA'
assert verdict(Run(cpu_s=1.0001, out_bytes=1), '5', '5', lim) == 'TLE'          # finished, right answer, over the limit
assert verdict(Run(cpu_s=1.0), '5', '5', lim) == 'AC'                           # exactly the limit is allowed
assert verdict(Run(killed='cpu', cpu_s=1.0), '5', '5', lim) == 'TLE' and verdict(Run(killed='wall'), '5', '5', lim) == 'TLE'
assert verdict(Run(killed='oom'), '', '', lim) == 'MLE' and verdict(Run(peak_kb=65537), '5', '5', lim) == 'MLE'
assert verdict(Run(peak_kb=65536), '5', '5', lim) == 'AC'
assert verdict(Run(killed='output'), '', '', lim) == 'OLE' and verdict(Run(out_bytes=1001), 'x', 'x', lim) == 'OLE'
assert verdict(Run(exit_code=1), '5', '5', lim) == 'RE' and verdict(Run(signal=11), '5', '5', lim) == 'RE'   # a crash with the right prefix is still RE
assert verdict(Run(signal=11, peak_kb=65536), '', '', lim) == 'MLE'              # a failed allocation surfaces as a crash at the limit
assert verdict(Run(exit_code=134, peak_kb=math.ceil(65536 * 0.98)), '', '', lim) == 'MLE'
assert verdict(Run(exit_code=134, peak_kb=int(65536 * 0.97)), '', '', lim) == 'RE'
assert verdict(Run(peak_kb=70000, cpu_s=5), '5', '5', lim) == 'MLE'              # both over: memory first (documented policy)
assert verdict(Run(cpu_s=5, out_bytes=5000), '5', '5', lim) == 'TLE'


def ref_verdict(r, e, a, l, mode='tokens'):
    reasons = set()
    if r.killed == 'oom' or r.peak_kb > l.mem_kb or (r.peak_kb >= l.mem_kb * 0.98 and (r.signal or r.exit_code)):
        reasons.add('MLE')
    if r.killed in ('cpu', 'wall') or r.cpu_s > l.cpu_s:
        reasons.add('TLE')
    if r.killed == 'output' or r.out_bytes > l.out_bytes:
        reasons.add('OLE')
    if r.signal or r.exit_code:
        reasons.add('RE')
    reasons.add('AC' if compare(e, a, mode) else 'WA')
    for v in ('MLE', 'TLE', 'OLE', 'RE', 'WA', 'AC'):
        if v in reasons:
            return v


for _ in range(3000):
    r = Run(exit_code=rnd.choice([0, 0, 1, 134]), signal=rnd.choice([0, 0, 0, 9, 11]), cpu_s=rnd.choice([0.5, 1.0, 1.1, 9]),
            peak_kb=rnd.choice([100, 64000, 64200, 65536, 70000]), out_bytes=rnd.choice([5, 1000, 1001]),
            killed=rnd.choice(['', '', '', 'cpu', 'wall', 'oom', 'output']))
    e, a = rnd.choice([('1', '1'), ('1', '2')])
    assert verdict(r, e, a, lim) == ref_verdict(r, e, a, lim), (r, e, a)

# ---- 3. a real subprocess runner ---------------------------------------------------------------------------------------------
py = sys.executable
killed, code, out, wall = run_case([py, '-c', 'import sys;print(sum(map(int,sys.stdin.read().split())))'], b'1 2 3\n', 10, 1000)
assert (killed, code, out.strip()) == ('', 0, b'6'), (killed, code, out)
killed, code, out, wall = run_case([py, '-c', 'import sys;sys.exit(3)'], b'', 10, 1000)
assert (killed, code) == ('', 3)
t0 = time.monotonic()
killed, code, out, wall = run_case([py, '-c', 'while True: pass'], b'', 0.4, 1000)
assert killed == 'wall' and 0.4 <= wall < 3.0 and time.monotonic() - t0 < 4, (killed, wall)
killed, code, out, wall = run_case([py, '-c', 'import time;time.sleep(30)'], b'', 0.4, 1000)    # asleep: only the wall clock catches it
assert killed == 'wall' and wall < 3.0
flood = 'import sys\nwhile True: sys.stdout.buffer.write(b"x" * 65536); sys.stdout.buffer.flush()'
killed, code, out, wall = run_case([py, '-c', flood], b'', 10, 100_000)
assert killed == 'output' and out == b'x' * 100_000 and wall < 8, (killed, len(out), wall)           # truncated to exactly the limit
exactly = 'import sys;sys.stdout.write("y"*1000)'
killed, code, out, wall = run_case([py, '-c', exactly], b'', 10, 1000)
assert killed == '' and len(out) == 1000                                                          # exactly the limit is not an overflow
killed, code, out, wall = run_case([py, '-c', 'import sys;sys.stdout.write("y"*1001)'], b'', 10, 1000)
assert killed == 'output' and len(out) == 1000
# a grandchild that keeps our stdout open must not hold the judge: the runner waits for its child, not for end-of-file
gc = 'import subprocess,sys;subprocess.Popen([sys.executable,"-c","import time;time.sleep(3)"]);print("hi")'
t0 = time.monotonic()
killed, code, out, wall = run_case([py, '-c', gc], b'', 10, 1000)
assert killed == '' and out.strip() == b'hi' and time.monotonic() - t0 < 2.5, (killed, out, time.monotonic() - t0)

# ---- 4. re-measuring a reading that is over the limit ------------------------------------------------------------------------
def trial(true_t, n, k, seed, mean=0.1):
    r = random.Random(seed)
    over = 0
    for _ in range(n):
        reads = []
        m = lambda: (reads.append(1), true_t * (1 + r.expovariate(1 / mean)))[1]
        if judged_time(m, 1.0, reruns=k) > 1.0:
            over += 1
    return over / n, 0
N = 200_000
p1 = trial(0.8, N, 0, 1)[0]
p3 = trial(0.8, N, 2, 2)[0]
exact1, exact3 = math.exp(-2.5), math.exp(-2.5) ** 3
assert abs(p1 - exact1) < 4 * math.sqrt(exact1 * (1 - exact1) / N), (p1, exact1)
assert abs(p3 - exact3) < 5 * math.sqrt(exact3 / N) + 1e-4, (p3, exact3)
assert round(exact1, 3) == 0.082 and round(exact3, 5) == 0.00055
assert trial(1.05, 20_000, 2, 3)[0] == 1.0 and trial(1.05, 20_000, 9, 4)[0] == 1.0     # a truly slow solution never gets through
calls = []
assert judged_time(lambda: (calls.append(1), 0.9)[1], 1.0) == 0.9 and len(calls) == 1      # within the limit: one reading
calls.clear()
assert judged_time(lambda: (calls.append(1), 5.0)[1], 1.0, hopeless=2.0) == 5.0 and len(calls) == 1   # hopeless: not re-measured
calls.clear()
seq = iter([1.2, 1.4, 0.95, 0.5])
assert judged_time(lambda: (calls.append(1), next(seq))[1], 1.0, reruns=3) == 0.95 and len(calls) == 3   # stops at the first reading under
seq = iter([1.2, 1.4, 1.3, 0.5])
assert judged_time(lambda: next(seq), 1.0, reruns=2) == 1.2                                   # the fastest of three readings, not the last
# extra work: the share of submissions near the limit that cost extra readings, for the lesson's example
extra = exact1 + exact1 ** 2
assert round(extra, 3) == 0.089

# ---- 5. the queue: against a time-stepped reference, then invariants ---------------------------------------------------------
def ref_sim(jobs, workers, policy):
    """integer times, one tick at a time: at each tick, free workers start jobs chosen by the policy"""
    started, finish, waiting, free_at, count = {}, {}, [], [0] * workers, {}
    t = 0
    while len(started) < len(jobs):
        for i, j in enumerate(jobs):
            if j[0] == t:
                waiting.append(i)
        for w in range(workers):
            if free_at[w] <= t and waiting:
                key = (lambda i: (jobs[i][0], i)) if policy == 'fifo' else (lambda i: (count.get(jobs[i][1], 0), jobs[i][0], i))
                i = min(waiting, key=key)
                waiting.remove(i)
                started[i] = t
                free_at[w] = t + jobs[i][2]
                count[jobs[i][1]] = count.get(jobs[i][1], 0) + 1
        t += 1
    return started


for seed in range(300):
    r = random.Random(seed)
    W = r.randint(1, 4)
    jobs = [(r.randint(0, 12), r.randint(0, 3), r.randint(1, 6)) for _ in range(r.randint(1, 25))]
    for pol in ('fifo', 'fair'):
        got = simulate(jobs, W, pol)
        ref = ref_sim(jobs, W, pol)
        assert {i: got[i][0] for i in got} == ref, (seed, pol, jobs, W)
        assert all(got[i][1] - got[i][0] == jobs[i][2] and got[i][0] >= jobs[i][0] for i in got)
        events = sorted({s for s, f in got.values()} | {f for s, f in got.values()} | {j[0] for j in jobs})
        for t in events:                                                    # never more than W running; never idle with work waiting
            running = sum(1 for s, f in got.values() if s <= t < f)
            waiting_now = sum(1 for i, (s, f) in got.items() if jobs[i][0] <= t < s)
            assert running <= W and not (waiting_now and running < W), (seed, pol, t)
assert simulate([], 2, 'fifo') == {}

# the burst in the lesson: one user submits 40 jobs at t=0, eight others one job each at t=1; 4 workers, 5 s each
burst = [(0, 0, 5)] * 40 + [(1, u, 5) for u in range(1, 9)]
stats = {}
for pol in ('fifo', 'fair'):
    res = simulate(burst, 4, pol)
    waits = sorted(res[i][0] - burst[i][0] for i in range(40, 48))
    stats[pol] = (waits[0], waits[-1], max(f for s, f in res.values()))
assert stats['fifo'] == (49, 54, 60) and stats['fair'] == (4, 9, 60), stats      # same makespan: fair sharing reorders, it creates no capacity
# the same burst under fair share: the heavy user's own last job finishes when?
res = simulate(burst, 4, 'fair')
assert max(res[i][1] for i in range(40)) == 60 and max(simulate(burst, 4, 'fifo')[i][1] for i in range(40)) == 50

# ---- 6. wording the lesson must keep, and stale wordings it must not ------------------------------------------------------------
for stale in ('LeetCode runs', 'LeetCode uses', 'Codeforces uses', 'gVisor is a seccomp', 'a sandbox makes untrusted code safe',
              'CPU time and wall time are the same', 'seccomp alone'):
    assert stale not in src, stale
need('Sources', 'Last reviewed: 27 November 2026', 'Level:** extended', '(proposed; the curriculum data holds the final rating)')
need('not consulted', 'isolate', 'gVisor', 'Firecracker', 'cgroup', 'seccomp', 'extra-time', 'wall-time')
need('49 seconds', '54 seconds', '4 seconds', '9 seconds', '**8.2%**', '**0.055%**', '**8.9%**')
after = [l for l in src.splitlines() if l.startswith('> **Study time')][0]
for t in ('Distributed Message Queue (SQS / RabbitMQ)', 'Docker & Container Internals', 'Real-Time Gaming Leaderboard at 10M QPS'):
    assert t in after or t in src, t
print('sy60 code checks passed')
