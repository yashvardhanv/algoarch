"""Runs the python blocks from data/new_lessons/sy46-time-clocks-ordering.md against reference checks:
timestamps against an independently computed happened-before relation, the vector-clock and HLC rules against
their published examples, and the linearizability checker against brute force over every ordering."""
import re, sys, random, math
from itertools import permutations

src = open(sys.argv[1], encoding='utf-8').read()
ns = {}
for b in re.findall(r"```python\n(.*?)```", src, re.S):
    exec(b, ns)

def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the computed figure: %r' % p

# ---------------------------------------------------------------- unit rules
assert ns['lamport_tick'](4) == 5 and ns['lamport_recv'](4, 9) == 10 and ns['lamport_recv'](9, 4) == 10
assert ns['vc_tick']((1, 2, 3), 1) == (1, 3, 3)
assert ns['vc_recv']((1, 4, 0), (3, 2, 5), 1) == (3, 5, 5)
rel = ns['vc_relation']
assert rel((1, 2), (1, 2)) == 'equal' and rel((1, 2), (2, 2)) == 'before' and rel((2, 2), (1, 2)) == 'after'
assert rel((2, 0), (0, 2)) == 'concurrent' and rel((0, 0), (0, 0)) == 'equal'
send, recv = ns['hlc_send'], ns['hlc_recv']
assert send((0, 0), 100) == (100, 0)                     # physical time ahead: counter resets
assert send((100, 0), 100) == (100, 1)                   # same millisecond: counter breaks the tie
assert send((100, 7), 90) == (100, 8)                    # physical clock behind: l stays, c grows
assert recv((50, 3), (100, 4), 80) == (100, 5)           # message from the future: adopt its l, c+1
assert recv((100, 3), (100, 9), 80) == (100, 10)         # both equal: max of counters + 1
assert recv((100, 3), (60, 9), 80) == (100, 4)           # own l wins
assert recv((10, 3), (20, 9), 100) == (100, 0)           # physical clock wins: counter resets

# ---------------------------------------------------------------- simulation against an independent happened-before
simulate, happened_before = ns['simulate'], ns['happened_before']

def reachable(events, a, b):
    """Is there a path a -> b along process order and send->receive edges? (plain DFS, no bitmasks)"""
    stack, seen = [b], set()
    last_on_node = {}
    prev = {}
    for e in events:
        prev[e['id']] = last_on_node.get(e['node'])
        last_on_node[e['node']] = e['id']
    while stack:
        x = stack.pop()
        for p in (prev[x], events[x]['src']):
            if p is None or p in seen:
                continue
            if p == a:
                return True
            seen.add(p)
            stack.append(p)
    return False

for seed in range(25):
    ev = simulate(seed, steps=40)
    assert [e['id'] for e in ev] == list(range(len(ev)))
    for b in range(len(ev)):
        for a in range(b):
            assert happened_before(ev, a, b) == reachable(ev, a, b), (seed, a, b)
        assert not happened_before(ev, b, b)
    assert any(e['kind'] == 'receive' for e in ev) and any(e['kind'] == 'send' for e in ev)

# the clock condition, vector exactness, HLC order and the bound l - pt <= skew spread
offsets = (0, 40, -35, 10)
spread = max(offsets) - min(offsets)
total_order = ns['total_order']
for seed in range(30):
    ev = simulate(seed, offsets=offsets)
    order = [e['id'] for e in total_order(ev)]
    pos = {i: k for k, i in enumerate(order)}
    keys = [(e['lamport'], e['node']) for e in ev]
    assert len(set(keys)) == len(keys)                                  # the tie-break makes it a total order
    for b in range(len(ev)):
        assert ev[b]['hlc'][0] >= ev[b]['wall'] and ev[b]['hlc'][0] - ev[b]['wall'] <= spread
        for a in range(b):
            hb = happened_before(ev, a, b)
            if hb:
                assert ev[a]['lamport'] < ev[b]['lamport']              # Clock Condition
                assert ev[a]['hlc'] < ev[b]['hlc']                      # HLC keeps it, lexicographically
                assert pos[a] < pos[b]                                  # total order extends happened-before
                assert rel(ev[a]['vector'], ev[b]['vector']) == 'before'
            else:
                assert rel(ev[a]['vector'], ev[b]['vector']) == 'concurrent'

survey = ns['survey']
s = survey(100)
assert s['lamport_wrong'] == s['hlc_wrong'] == s['vector_wrong'] == 0
assert s['wall_wrong'] > 0 and s['ordered'] > 0 and s['concurrent'] > 0
assert s['lamport_orders_concurrent'] > 0.5 * s['concurrent']
sweep = ns['skew_sweep'](100)
assert [r[0] for r in sweep] == [0, 5, 75, 350] and sweep[0][2] == 0
assert sweep[0][2] < sweep[1][2] < sweep[2][2] < sweep[3][2]
pct = lambda a, b: '%.1f%%' % (100 * a / b)
need('%s of %s (%s)' % (format(s['wall_wrong'], ','), format(s['ordered'], ','), pct(s['wall_wrong'], s['ordered'])),
     '%s of %s' % (format(s['lamport_orders_concurrent'], ','), format(s['concurrent'], ',')),
     '| Lamport | 0 of %s' % format(s['ordered'], ','), '| vector | 0 of %s' % format(s['ordered'], ','),
     '| HLC | 0 of %s' % format(s['ordered'], ','))
for spread_ms, ordered, wrong in sweep:
    need('| %d ms | %s | %s | %s |' % (spread_ms, format(ordered, ','), format(wrong, ','), pct(wrong, ordered)))

# ---------------------------------------------------------------- last-writer-wins on skewed clocks, with and without HLC
wall_winner, hlc_winner = ns['lww_scenario']()
assert (wall_winner, hlc_winner) == ('cart=[book]', 'cart=[book,pen]')
need('cart=[book]', 'cart=[book,pen]')

# ---------------------------------------------------------------- Dynamo's published example, and truncation
rel_d, truncate = ns['dict_relation'], ns['truncate']
D1, D2 = {'Sx': 1}, {'Sx': 2}
D3, D4 = {'Sx': 2, 'Sy': 1}, {'Sx': 2, 'Sz': 1}
D5 = {'Sx': 3, 'Sy': 1, 'Sz': 1}
assert rel_d(D1, D2) == 'before' and rel_d(D2, D3) == 'before' and rel_d(D2, D4) == 'before'
assert rel_d(D3, D4) == 'concurrent' and rel_d(D4, D3) == 'concurrent'
assert rel_d(D3, D5) == 'before' and rel_d(D4, D5) == 'before' and rel_d(D5, D1) == 'after' and rel_d(D5, D5) == 'equal'
assert rel_d({}, D1) == 'before'
stamps = {'x': 5, 'y': 1, 'z': 9}
assert truncate({'x': 3, 'y': 1}, stamps, 1) == {'x': 3}                  # drops the oldest-updated node
assert truncate({'x': 3, 'y': 1, 'z': 2}, stamps, 2) == {'x': 3, 'z': 2}
assert truncate({'x': 3, 'y': 1}, stamps, 5) == {'x': 3, 'y': 1}
older, newer = {'x': 2, 'y': 1}, {'x': 3, 'y': 1}
assert rel_d(older, newer) == 'before' and rel_d(older, truncate(newer, stamps, 1)) == 'concurrent'    # false conflict
c, other = {'x': 1, 'y': 1}, {'x': 2}
assert rel_d(c, other) == 'concurrent' and rel_d(truncate(c, stamps, 1), other) == 'before'            # silent loss
need('false conflict', 'silently')

# ---------------------------------------------------------------- linearizability checker against brute force
Op, check = ns['Op'], ns['check']

def brute(ops, init=0, real_time=True):
    n = len(ops)
    for perm in permutations(range(n)):
        ok = True
        for p in range(n):
            for q in range(p + 1, n):
                a, b = ops[perm[p]], ops[perm[q]]
                if (real_time and b.ret < a.call) or (b.client == a.client and b.call < a.call):
                    ok = False
                    break
            if not ok:
                break
        if not ok:
            continue
        state = init
        for i in perm:
            if ops[i].kind == 'w':
                state = ops[i].value
            elif ops[i].value != state:
                ok = False
                break
        if ok:
            return True
    return False

def gen(rng):
    """Run a real atomic register: every operation takes effect at a point inside its interval; maybe corrupt a read."""
    ops, nxt = [], 1
    for client in range(rng.randint(2, 3)):
        t = rng.uniform(0, 4)
        for _ in range(rng.randint(1, 3)):
            call, ret = t, t + rng.uniform(0.5, 5)
            point = rng.uniform(call, ret)
            kind = rng.choice('wr')
            ops.append([client, kind, None, call, ret, point])
            t = ret + rng.uniform(0.1, 3)
    state = 0
    for op in sorted(ops, key=lambda o: o[5]):
        if op[1] == 'w':
            op[2] = nxt
            nxt += 1
            state = op[2]
        else:
            op[2] = state
    reads = [o for o in ops if o[1] == 'r']
    if reads and rng.random() < 0.6:
        rng.choice(reads)[2] = rng.randrange(0, nxt + 1)
    return [Op('c%d' % c, k, v, call, ret) for c, k, v, call, ret, _ in ops]

rng = random.Random(21)
tally = {(rt, ans): 0 for rt in (True, False) for ans in (True, False)}
for _ in range(220):
    ops = gen(rng)
    if len(ops) > 7:
        continue
    for rt in (True, False):
        got, explored = check(ops, real_time=rt)
        want = brute(ops, real_time=rt)
        assert got == want, (ops, rt, got, want)
        assert explored >= 1
        tally[(rt, want)] += 1
assert all(v >= 8 for v in tally.values()), tally                          # both answers occurred in both modes
# a history that is sequentially consistent but not linearizable shows up often enough to matter
assert check([], real_time=True) == (True, 0)

stale = [Op('A', 'w', 1, 0, 1), Op('B', 'r', 0, 2, 3)]
backwards = [Op('W', 'w', 1, 0, 10), Op('A', 'r', 1, 1, 2), Op('B', 'r', 0, 3, 4)]
overlap_ok = [Op('W', 'w', 1, 0, 10), Op('A', 'r', 0, 1, 2), Op('B', 'r', 1, 3, 4)]
assert check(stale)[0] is False and check(stale, real_time=False)[0] is True
assert check(backwards)[0] is False and check(backwards, real_time=False)[0] is True
assert check(overlap_ok)[0] is True
assert brute(stale) is False and brute(backwards) is False and brute(overlap_ok) is True
need('A stale read', 'Reads going backwards')

# the state count: n overlapping writes and an impossible read explore n * 2**(n-1) + 1 states
explored = {}
for n in (4, 6, 8, 10, 12):
    ops = [Op('c%d' % i, 'w', i + 1, 0, 100) for i in range(n)] + [Op('r', 'r', 99, 101, 102)]
    ans, states = check(ops)
    assert ans is False and states == n * 2 ** (n - 1) + 1, (n, states)
    explored[n] = states
    need('| %d | %s |' % (n, format(states, ',')))
need('n x 2^(n-1) + 1')
assert explored[12] == 24577
print('sy46 code checks passed')
