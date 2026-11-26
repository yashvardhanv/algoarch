"""Runs the python code blocks from data/new_lessons/sy40-spanner-truetime-dr.md: the 2PC termination rule against a
brute-force enumeration of consistent worlds, and the TrueTime commit simulation against the external-consistency
invariant stated in the Spanner paper."""
import re, sys, random, itertools
src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
ns = {}
for b in blocks:
    exec(b, ns)
termination, tt_now, tt_after, commit = ns['termination'], ns['tt_now'], ns['tt_after'], ns['commit']
random.seed(40)
STATES = ('working', 'prepared', 'aborted', 'committed')

# ---------------- 2PC termination vs brute force ----------------
def consistent(decision, states):
    """decision: the coordinator's hidden decision (None, 'commit', 'abort'); states: every participant's state."""
    if decision == 'commit' and any(s not in ('prepared', 'committed') for s in states):
        return False                      # commit needs every vote yes
    if any(s == 'committed' for s in states) and decision != 'commit':
        return False                      # a participant commits only after the commit decision
    if decision == 'abort' and any(s == 'committed' for s in states):
        return False
    return True

def brute(reachable, n_unreachable):
    worlds = []
    for hidden in itertools.product(STATES, repeat=n_unreachable):
        for d in (None, 'commit', 'abort'):
            if consistent(d, list(reachable) + list(hidden)):
                worlds.append(d)
    assert worlds, 'the observed states are impossible'
    if all(d == 'commit' for d in worlds):
        return 'commit'
    if not any(d == 'commit' for d in worlds):
        return 'abort'                    # reachable 'working' participants refuse, so commit stays impossible
    return 'blocked'

cases = 0
for r in range(1, 5):
    for reach in itertools.product(STATES, repeat=r):
        for u in range(0, 3):
            # skip observations no execution can produce
            if not any(consistent(d, list(reach)) for d in (None, 'commit', 'abort')):
                continue
            assert termination(list(reach), u) == brute(reach, u), (reach, u, termination(list(reach), u), brute(reach, u))
            cases += 1
assert termination(['prepared', 'prepared', 'prepared'], 0) == 'blocked'

# ---------------- TrueTime commit simulation ----------------
txns_total, pairs = 0, 0
for trial in range(120):
    eps = random.randint(1, 40)
    servers = [random.randint(-eps, eps) for _ in range(random.randint(1, 4))]
    if trial % 3 == 0:
        servers = [-eps, eps]                         # extreme skew between two leaders
    last_ts = [0] * len(servers)
    txns, last_arrival = [], 0
    for i in range(150):
        if txns and random.random() < 0.7:
            base = random.choice(txns)['visible'] + random.randint(0, 2)   # starts just after another commits
        else:
            base = last_arrival + random.randint(0, 5)
        start = max(base, last_arrival)
        arrival = start + random.randint(0, 2)
        last_arrival = arrival
        k = random.randrange(len(servers))
        off = servers[k]
        lo, hi = tt_now(arrival, off, eps)
        assert lo <= arrival <= hi
        paxos_done = arrival + random.randint(0, 3 * eps)
        prev = last_ts[k]
        s, visible = commit(arrival, off, eps, prev, paxos_done)
        assert s > prev
        last_ts[k] = s
        assert s < visible and tt_after(s, visible, off, eps), 'commit visible before TT.after(s)'
        if s == hi:                                    # timestamp came from TT.now().latest
            wait_end = s - off + eps + 1
            assert wait_end - arrival == 2 * eps + 1
            assert tt_after(s, wait_end, off, eps) and not tt_after(s, wait_end - 1, off, eps)
        txns.append({'start': start, 'arrival': arrival, 's': s, 'visible': visible})
    for t1 in txns:
        for t2 in txns:
            if t1 is not t2 and t1['visible'] < t2['start']:
                assert t1['s'] < t2['s'], ('external consistency violated', eps, t1, t2)
                pairs += 1
    txns_total += len(txns)

# ---------------- numbers quoted from the paper and derived ----------------
assert round(30 * 200e-6 * 1000, 6) == 6.0 and 6 + 1 == 7          # drift part of epsilon plus communication
assert 2 * 4 == 8 and round(14.4 - 9.4, 1) == 5.0
print('sy40 code checks passed (%d termination cases, %d transactions, %d ordered pairs)' % (cases, txns_total, pairs))
