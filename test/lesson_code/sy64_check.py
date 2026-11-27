"""Runs the python blocks of the sy64 food-delivery-dispatch lesson: the delivery-time and courier-wait cost, the optimal
assignment (Hungarian) against a brute-force over every partial matching, greedy against it (the gap is measured), candidate
pruning, batching (route cost, exact route search against an independent enumerator, cheapest insertion measured against it)
and the offer/accept protocol under random interleavings. Figures the lesson prints from simulations are asserted here."""
import re, sys, random, itertools

src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
assert len(blocks) >= 4, 'expected the lesson code blocks'
ns = {}
for b in blocks:
    exec(b, ns)
dist, eta, hungarian, match = ns['dist'], ns['eta'], ns['hungarian'], ns['match']
greedy, prune, cost_matrix = ns['greedy'], ns['prune'], ns['cost_matrix']
run_route, route_cost, best_route = ns['run_route'], ns['route_cost'], ns['best_route']
insert_best, batch_ok, Dispatch = ns['insert_best'], ns['batch_ok'], ns['Dispatch']
BIG = ns['BIG']


def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the checked figure: %r' % p


def forbid(*phrases):
    for p in phrases:
        assert p not in src, 'lesson text still contains stale wording: %r' % p


# ---- 1. cost of giving an order to a courier ---------------------------------------------------------------------------
o = {'rest': (0, 0), 'cust': (4, 0), 'ready': 10, 'created': 0}
assert dist((0, 0), (3, 4)) == 7 and dist((3, 4), (0, 0)) == 7
# courier 2 away at speed 1, now 0: arrives at 2, food ready at 10 -> waits 8, picks up at 10, drops at 14
drop, wait, c = eta((2, 0), o, 0, speed=1.0, wait_weight=0.5)
assert (drop, wait, c) == (14, 8, 14 + 4.0)
# courier far away: arrives after the food is ready, no wait
drop, wait, c = eta((20, 0), o, 0, speed=1.0, wait_weight=0.5)
assert (drop, wait, c) == (24, 0, 24)
assert eta((10, 0), o, 0, speed=1.0)[1] == 0                      # food ready exactly when the courier arrives: no wait
assert eta((20, 0), o, 0, speed=0.5)[0] == 40 + 8                  # half speed doubles travel
assert eta((2, 0), o, 0, speed=1.0, wait_weight=0)[2] == eta((9, 0), o, 0, speed=1.0, wait_weight=0)[2] == 14   # without the term they tie
assert eta((2, 0), o, 0, speed=1.0)[2] > eta((9, 0), o, 0, speed=1.0)[2]      # with it the early courier costs more
of = {'rest': (0, 0), 'cust': (2, 0), 'ready': 3, 'created': 0}            # fractional times: arrives at 2.5, food ready at 3
df, wf, cf = eta((1, 0), of, 0, speed=0.4, wait_weight=0.5)
assert abs(df - 8) < 1e-9 and abs(wf - 0.5) < 1e-9 and abs(cf - 8.25) < 1e-9
assert abs(run_route((1, 0), 0, [of], [('p', 0), ('d', 0)], speed=0.4)[1] - 0.5) < 1e-9
o3 = {'rest': (0, 0), 'cust': (4, 0), 'ready': 0, 'created': -3}                # an order that has already waited 3 minutes
assert eta((2, 0), o3, 0, speed=1.0, wait_weight=0.5) == (6, 0, 6 + 3)
assert eta((2, 0), o, 7, speed=1.0)[0] == 14 and eta((2, 0), o, 7, speed=1.0)[1] == 1    # a later "now" shortens the wait


# ---- 2. assignment: Hungarian against brute force ----------------------------------------------------------------------
def brute(cost, penalty):
    n, m = len(cost), len(cost[0])
    best = [float('inf')]

    def rec(i, used, total):
        if total >= best[0]:
            return
        if i == n:
            best[0] = total
            return
        rec(i + 1, used, total + penalty)                       # leave order i unassigned
        for j in range(m):
            if j not in used and cost[i][j] < penalty:
                rec(i + 1, used | {j}, total + cost[i][j])
    rec(0, frozenset(), 0)
    return best[0]


def total_of(cost, assign, penalty):
    return sum(penalty if j is None else cost[i][j] for i, j in enumerate(assign))


rng = random.Random(11)
for trial in range(1500):
    n, m = rng.randint(1, 6), rng.randint(1, 7)
    hi = rng.choice([10, 100, 10 ** 6])
    pen = rng.choice([hi // 2 + 1, hi, 2 * hi])
    cost = [[rng.randint(0, hi) for _ in range(m)] for _ in range(n)]
    assign = match(cost, pen)
    assert len(assign) == n
    cols = [j for j in assign if j is not None]
    assert len(cols) == len(set(cols)), 'a courier got two orders'
    assert all(cost[i][j] < pen for i, j in enumerate(assign) if j is not None), 'assigned at or above the penalty'
    assert total_of(cost, assign, pen) == brute(cost, pen), (trial, cost, pen)
assert match([[5], [3], [4]], 100) == [None, 0, None]              # more orders than couriers: the cheapest gets it
assert match([[1, 1], [1, 1]], 100) in ([0, 1], [1, 0])
assert match([[200, 300]], 100) == [None]                          # too expensive: leave it for the next cycle
tot, col = hungarian([[4, 1, 3], [2, 0, 5], [3, 2, 2]])
assert tot == 5 and sorted(col) == [0, 1, 2]
big = [[rng.randint(0, 10 ** 12) for _ in range(8)] for _ in range(7)]
t, col = hungarian(big)
assert t == sum(big[i][col[i]] for i in range(7))
assert t == min(sum(big[i][p[i]] for i in range(7)) for p in itertools.permutations(range(8), 7))

# ---- 3. greedy against optimal: the classic trap and the measured gap -------------------------------------------------
trap = [[1, 2], [2, 100]]                                           # order 0 is seen first and takes the courier order 1 needed
assert greedy(trap, 1000) == [0, 1] and total_of(trap, greedy(trap, 1000), 1000) == 101
assert match(trap, 1000) == [1, 0] and total_of(trap, match(trap, 1000), 1000) == 4
rng = random.Random(21)
worse, trials = 0, 2000
for _ in range(trials):
    n, m = rng.randint(2, 6), rng.randint(2, 8)
    cost = [[rng.randint(1, 100) for _ in range(m)] for _ in range(n)]
    g, o_ = total_of(cost, greedy(cost, 10 ** 6), 10 ** 6), total_of(cost, match(cost, 10 ** 6), 10 ** 6)
    assert g >= o_
    worse += g > o_
assert (worse, trials) == (1079, 2000), (worse, trials)
need('1,079 of 2,000')


# ---- 4. the cost matrix and candidate pruning --------------------------------------------------------------------------
def make_instance(rng, n, m, g=20):
    orders = [{'rest': (rng.randint(0, g), rng.randint(0, g)), 'cust': (rng.randint(0, g), rng.randint(0, g)),
               'ready': rng.randint(0, 15), 'created': rng.randint(-5, 0)} for _ in range(n)]
    couriers = [(rng.randint(0, g), rng.randint(0, g)) for _ in range(m)]
    return orders, couriers


rng = random.Random(31)
orders, couriers = make_instance(rng, 4, 6)
M = cost_matrix(orders, couriers, 0, speed=1.0, wait_weight=0.5)
assert len(M) == 4 and len(M[0]) == 6
assert all(M[i][j] == eta(couriers[j], orders[i], 0, speed=1.0, wait_weight=0.5)[2] for i in range(4) for j in range(6))
assert prune(M, 99) == M and prune(M, 6) == M
P = prune(M, 2)
for i in range(4):
    assert sorted(x for x in P[i] if x < BIG) == sorted(M[i])[:2] and sum(1 for x in P[i] if x >= BIG) == 4
rng = random.Random(41)
lost, trials = 0, 1000
for _ in range(trials):
    n, m = rng.randint(3, 8), rng.randint(8, 14)
    orders, couriers = make_instance(rng, n, m)
    M = cost_matrix(orders, couriers, 0, speed=1.0, wait_weight=0.5)
    pen = 10 ** 6
    full = total_of(M, match(M, pen), pen)
    pr = total_of(M, match(prune(M, 3), pen), pen)
    assert pr >= full
    assert total_of(M, match(prune(M, m), pen), pen) == full
    lost += pr > full
assert (lost, trials) == (81, 1000), (lost, trials)
need('81 of 1,000')

# ---- 5. batching: route cost, exact search, cheapest insertion ---------------------------------------------------------
A = {'rest': (0, 0), 'cust': (3, 0), 'ready': 0, 'created': 0}
B = {'rest': (1, 0), 'cust': (5, 0), 'ready': 6, 'created': 0}
seq = [('p', 0), ('p', 1), ('d', 0), ('d', 1)]
# start (0,0): p0 at 0; p1 reached at 1, food ready 6 so wait 5; d0 at 8; d1 at 10 -> delays 8 + 10 and a wait of 5
assert run_route((0, 0), 0, [A, B], seq, speed=1.0) == ({0: 8, 1: 10}, 5)
assert route_cost((0, 0), 0, [A, B], seq, speed=1.0, wait_weight=0.5) == 8 + 10 + 0.5 * 5
seq2 = [('p', 0), ('d', 0), ('p', 1), ('d', 1)]                    # d0 at 3, p1 reached at 5 (wait 1), d1 at 10
assert run_route((0, 0), 0, [A, B], seq2, speed=1.0) == ({0: 3, 1: 10}, 1)
assert route_cost((0, 0), 0, [A, B], seq2, speed=1.0, wait_weight=0.5) == 3 + 10 + 0.5
assert route_cost((0, 0), 0, [A, B], [('d', 0), ('p', 0), ('p', 1), ('d', 1)], speed=1.0) is None      # drop before pickup
assert route_cost((0, 0), 0, [A, B], [('p', 0), ('d', 0)], speed=1.0) is None                           # an order left out
assert route_cost((0, 0), 0, [A], [('p', 0), ('d', 0), ('d', 0)], speed=1.0) is None                    # dropped twice
assert route_cost((0, 0), 0, [A], [('p', 0), ('p', 0), ('d', 0)], speed=1.0) is None                    # picked twice
assert route_cost((0, 0), 0, [A], [('p', 0), ('d', 0)], speed=1.0) == 3
assert route_cost((5, 0), 0, [A], [('p', 0), ('d', 0)], speed=1.0) == 5 + 3                              # courier starts elsewhere
# the order of delivery matters: B first is better here for the customers
assert best_route((0, 0), 0, [A, B], speed=1.0, wait_weight=0.5)[0] == min(
    route_cost((0, 0), 0, [A, B], list(p), speed=1.0, wait_weight=0.5) or 1e18
    for p in itertools.permutations([('p', 0), ('p', 1), ('d', 0), ('d', 1)]))


def all_sequences(k):
    """Independent enumerator: build sequences left to right, a drop only after its pickup."""
    out = []

    def rec(seq, picked, dropped):
        if len(dropped) == k:
            out.append(list(seq))
            return
        for i in range(k):
            if i not in picked:
                rec(seq + [('p', i)], picked | {i}, dropped)
            elif i not in dropped:
                rec(seq + [('d', i)], picked, dropped | {i})
    rec([], frozenset(), frozenset())
    return out


assert [len(all_sequences(k)) for k in (1, 2, 3)] == [1, 6, 90]
rng = random.Random(51)
opt_count, trials, worst, shortfalls = 0, 1500, 0.0, 0
for _ in range(trials):
    k = rng.randint(1, 3)
    orders, (start,) = make_instance(rng, k, 1)
    t0 = 0
    exact_cost, exact_seq = best_route(start, t0, orders, speed=1.0, wait_weight=0.5)
    ref = min(route_cost(start, t0, orders, s, speed=1.0, wait_weight=0.5) for s in all_sequences(k))
    assert abs(exact_cost - ref) < 1e-9 and route_cost(start, t0, orders, exact_seq, speed=1.0, wait_weight=0.5) == exact_cost
    # cheapest insertion, orders added one at a time in index order
    seq, cost_ins = [], None
    for i in range(k):
        cost_ins, seq = insert_best(start, t0, orders[:i + 1], seq, i, speed=1.0, wait_weight=0.5)
    assert abs(route_cost(start, t0, orders, seq, speed=1.0, wait_weight=0.5) - cost_ins) < 1e-9
    assert cost_ins >= exact_cost - 1e-9
    if k == 1:
        assert abs(cost_ins - exact_cost) < 1e-9
    if cost_ins - exact_cost < 1e-9:
        opt_count += 1
    else:
        shortfalls += 1
        worst = max(worst, cost_ins - exact_cost)
assert (opt_count, trials) == (1377, 1500), (opt_count, trials)
need('1,377 of 1,500')
# with one order insertion is exact; with two the insertion of the second can still miss the best route
for _ in range(300):
    orders, (start,) = make_instance(rng, 1, 1)
    c1, s1 = insert_best(start, 0, orders, [], 0, speed=1.0, wait_weight=0.5)
    assert s1 == [('p', 0), ('d', 0)] and c1 == best_route(start, 0, orders, speed=1.0, wait_weight=0.5)[0]
# insertion must consider positions in the middle, not only the end: this case needs the new pickup before an old drop
C = {'rest': (0, 1), 'cust': (0, 5), 'ready': 0, 'created': 0}
D = {'rest': (0, 2), 'cust': (0, 4), 'ready': 0, 'created': 0}
cst, sq = insert_best((0, 0), 0, [C, D], [('p', 0), ('d', 0)], 1, speed=1.0, wait_weight=0.5)
assert cst == route_cost((0, 0), 0, [C, D], sq, speed=1.0, wait_weight=0.5)
assert sq == [('p', 0), ('p', 1), ('d', 1), ('d', 0)], sq

seq_b = [('p', 0), ('p', 1), ('d', 0), ('d', 1)]
# batch_ok: nobody is made more than max_extra later than they would be alone
assert run_route((0, 0), 0, [A], [('p', 0), ('d', 0)], speed=1.0)[0] == {0: 3}
assert batch_ok((0, 0), 0, [A, B], seq_b, 5, speed=1.0) is True        # A is 5 later than alone (8 against 3), B is 0 later
assert batch_ok((0, 0), 0, [A, B], seq_b, 4.99, speed=1.0) is False
assert batch_ok((0, 0), 0, [A, B], seq2, 0, speed=1.0) is True      # serving A first delays nobody beyond their solo time
assert batch_ok((0, 0), 0, [A, B], [('d', 0), ('p', 0)], 99, speed=1.0) is False   # an infeasible route is never ok

# ---- 6. the offer / accept protocol ------------------------------------------------------------------------------------
d = Dispatch(ttl=15, max_load=2)
d.add_order('o1')
oid1 = d.offer('o1', 'A', 0)
assert oid1 is not None and d.offer('o1', 'B', 1) is None            # an order already offered cannot be offered again
assert d.accept('o1', 'B', oid1, 2) is False                        # wrong courier
assert d.accept('o1', 'A', oid1 + 1, 2) is False                    # wrong offer id
assert d.accept('o1', 'A', oid1, 15) is True and d.orders['o1']['state'] == 'assigned'      # exactly at the expiry still counts
assert d.accept('o1', 'A', oid1, 16) is False and d.load['A'] == 1  # a second accept does nothing
d = Dispatch(ttl=15)                                                  # an accept after the deadline fails even if expire() has not run yet
d.add_order('o')
f0 = d.offer('o', 'A', 0)
assert d.accept('o', 'A', f0, 15.5) is False and d.orders['o']['state'] == 'offered' and d.load.get('A', 0) == 0
# the late accept: A's offer lapsed, B got the order, A's accept arrives afterwards (same order, old offer id)
d = Dispatch(ttl=15)
d.add_order('o')
first = d.offer('o', 'A', 0)
d.expire(15)
assert d.orders['o']['state'] == 'offered'                           # expiry is strictly after the deadline
d.expire(15.5)
assert d.orders['o']['state'] == 'open' and 'A' not in d.offered_to
second = d.offer('o', 'B', 16)
assert second != first
assert d.accept('o', 'A', first, 16.5) is False                      # stale accept refused
assert d.accept('o', 'B', second, 17) is True and d.orders['o']['courier'] == 'B' and d.load.get('A', 0) == 0
# the same courier re-offered the same order gets a new offer id; the old one stays dead
d = Dispatch(ttl=5)
d.add_order('o')
f1 = d.offer('o', 'A', 0); d.expire(6)
f2 = d.offer('o', 'A', 7)
assert f2 != f1 and d.accept('o', 'A', f1, 8) is False and d.accept('o', 'A', f2, 8) is True
# a delayed decline of an OLD offer must not cancel the new offer to the same courier
d = Dispatch(ttl=5)
d.add_order('o')
g1 = d.offer('o', 'A', 0); d.expire(6)
g2 = d.offer('o', 'A', 7)
assert d.decline('o', 'A', g1, 8) is False and d.orders['o']['state'] == 'offered' and d.orders['o']['offer'] == g2
assert d.accept('o', 'A', g2, 8) is True
# the cap holds at the commit point: a courier pushed to the cap behind the offer's back cannot accept
d = Dispatch(ttl=50, max_load=2)
d.add_order('o')
h = d.offer('o', 'A', 0)
d.load['A'] = 2
assert d.accept('o', 'A', h, 1) is False and d.orders['o']['state'] == 'open' and 'A' not in d.offered_to and d.load['A'] == 2
# declines free the order and the courier
d = Dispatch(ttl=5)
d.add_order('o'); d.add_order('p')
f = d.offer('o', 'A', 0)
assert d.offer('p', 'A', 1) is None                                  # one open offer per courier
assert d.decline('o', 'B', f, 1) is False and d.decline('o', 'A', f, 1) is True
assert d.offer('p', 'A', 2) is not None
# capacity: a courier carrying max_load orders is not offered another
d = Dispatch(ttl=50, max_load=2)
for k in 'abc':
    d.add_order(k)
for k in 'ab':
    assert d.accept(k, 'A', d.offer(k, 'A', 0), 1) is True
assert d.offer('c', 'A', 2) is None
d.complete('a')
assert d.load['A'] == 1 and d.offer('c', 'A', 3) is not None
assert d.complete('a') is False and d.load['A'] == 1                 # completing twice frees nothing more


def fuzz_dispatch(seed, steps=300):
    rng = random.Random(seed)
    d = Dispatch(ttl=10, max_load=2)
    oids, couriers, now = ['o%d' % i for i in range(8)], ['c%d' % i for i in range(4)], 0.0
    for oid in oids:
        d.add_order(oid)
    accepted, issued, n_acc = {}, [], 0
    for _ in range(steps):
        now += rng.choice([0, 1, 3, 11])
        op = rng.random()
        oid, c = rng.choice(oids), rng.choice(couriers)
        if op < 0.35:
            f = d.offer(oid, c, now)
            if f is not None:
                issued.append((oid, c, f))
        elif op < 0.6 and issued:
            o2, c2, f2 = rng.choice(issued)                          # accept with any offer ever issued, fresh or stale
            if d.accept(o2, c2, f2, now):
                assert o2 not in accepted, 'an order was accepted twice'
                accepted[o2] = c2
                n_acc += 1
        elif op < 0.7 and issued:
            o2, c2, f2 = rng.choice(issued)
            d.decline(o2, c2, f2, now)
        elif op < 0.85:
            d.expire(now)
        else:
            if d.complete(oid):
                accepted.pop(oid, None)
        # invariants
        assigned = {k: v['courier'] for k, v in d.orders.items() if v['state'] == 'assigned'}
        assert assigned == accepted, (seed, assigned, accepted)
        for cc in couriers:
            assert d.load.get(cc, 0) == sum(1 for v in assigned.values() if v == cc) <= 2
            assert sum(1 for v in d.orders.values() if v['state'] == 'offered' and v['courier'] == cc) <= 1
        for k, v in d.orders.items():
            if v['state'] == 'offered':
                assert d.offered_to.get(v['courier']) == k
        assert all(d.orders[k]['state'] == 'offered' for k in d.offered_to.values())
    return n_acc


total_acc = sum(fuzz_dispatch(s) for s in range(150))
assert total_acc > 300, 'the fuzz must actually assign orders'

# ---- 7. cited and computed figures -------------------------------------------------------------------------------------
need('2.7% of orders need four or more offers', 'a third of a 20-second window', 'Do this after', 'Last reviewed: 27 November 2026', 'arXiv', '20-second', 'ASAP', 'XCAT', 'mixed-integer', '1,079 of 2,000', '81 of 1,000', '1,377 of 1,500', '150 seeded random interleavings')
assert len(re.findall(r'^\d+\. ', src.split('## Drills')[1].split('## Homework')[0], re.M)) == 8, 'eight drills'
forbid('NP-hard', 'more than a window', 'fencing token in Flash Sale')
for bad in ('lakh', 'crore', 'LPA'):
    forbid(bad)
print('sy64 code checks passed')
