"""Runs the python blocks of the sy72 online-game lesson: the Glicko rating update against the worked examples in
Glickman's paper, the matchmaking tick against a brute-force reference, a queue simulation, the move-submission
protocol (duplicates, stale and future moves, clocks, lag credit) against a plain reference, an exhaustive count of
tic-tac-toe games, and recovery by replaying the move log."""
import re, sys, random, math

src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
assert len(blocks) >= 3, 'expected the lesson code blocks'
ns = {}
for b in blocks:
    exec(b, ns)
g, expected, update, age, win_prob, rate_game, c_for = (ns[k] for k in ('g', 'expected', 'update', 'age', 'win_prob', 'rate_game', 'c_for'))
window, compatible, match_tick, simulate_queue = ns['window'], ns['compatible'], ns['match_tick'], ns['simulate_queue']
winner, Game = ns['winner'], ns['Game']


def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the checked figure: %r' % p


def forbid(*phrases):
    for p in phrases:
        assert p not in src, 'lesson text still contains stale wording: %r' % p


# ---- 1. Glicko (Glickman, "The Glicko system") --------------------------------------------------------------------
assert [round(g(x), 4) for x in (30, 100, 300)] == [0.9955, 0.9531, 0.7242]        # the paper's table
games = [(1400, 30, 1), (1550, 100, 0), (1700, 300, 0)]
assert [round(expected(1500, rj, rdj), 3) for rj, rdj, _ in games] == [0.639, 0.432, 0.303]
r, rd = update(1500, 200, games)
assert round(r) == 1464 and round(rd, 1) == 151.4, (r, rd)                          # the paper's worked example
assert round(win_prob(1400, 80, 1500, 150), 3) == 0.376                             # the paper's expected-outcome example
assert abs(win_prob(1700, 50, 1500, 80) + win_prob(1500, 80, 1700, 50) - 1) < 1e-12
assert win_prob(1500, 30, 1500, 30) == 0.5
assert 0.5 < win_prob(1700, 350, 1500, 350) < win_prob(1700, 30, 1500, 30)          # uncertainty pulls the estimate towards even
assert update(1500, 200, []) == (1500, 200)
assert round(c_for(50, 30), 1) == 63.2                                              # the paper's choice of c (2-month periods, 5 years)
assert age(50, 63.2, 30) == 350 or abs(age(50, 63.2, 30) - 350) < 0.5
assert age(50, 63.2, 1) > 50 and age(340, 63.2, 5) == 350 and age(120, 0, 9) == 120
# a win raises the rating, a loss lowers it, a game always shrinks RD, in a spread of random cases
rng = random.Random(72)
for _ in range(500):
    r0, d0 = rng.uniform(800, 2400), rng.uniform(30, 350)
    r1, d1 = rng.uniform(800, 2400), rng.uniform(30, 350)
    win, lose = update(r0, d0, [(r1, d1, 1)]), update(r0, d0, [(r1, d1, 0)])
    assert win[0] > r0 > lose[0] and win[1] < d0 and lose[1] < d0 and win[1] == lose[1]
    draw = update(r0, d0, [(r1, d1, 0.5)])
    assert lose[0] < draw[0] < win[0]
# paper: rating changes are not balanced, an unrated winner moves much more than the established loser
a, b = rate_game((1700, 350), (1700, 50), 1)
assert a[0] - 1700 > 3 * (1700 - b[0]) > 0, (a, b)
# a game is rated from BOTH pre-game values: rating A first and then using its new value for B changes B's result
for _ in range(200):
    pa, pb = (rng.uniform(1000, 2200), rng.uniform(40, 350)), (rng.uniform(1000, 2200), rng.uniform(40, 350))
    s = rng.choice([0, 0.5, 1])
    na, nb = rate_game(pa, pb, s)
    mb, ma = rate_game(pb, pa, 1 - s)
    assert (na, nb) == (ma, mb), (pa, pb, s)
    stale = update(pb[0], pb[1], [(na[0], na[1], 1 - s)])                            # the sequential bug
    assert abs(stale[0] - nb[0]) > 1e-9
# RD floor of 30
assert rate_game((1500, 30), (1500, 30), 1)[0][1] == 30 and rate_game((1500, 30), (1500, 30), 1)[1][1] == 30
for _ in range(200):
    ra, rb = rate_game((1500, 31), (1500, rng.uniform(30, 40)), 1)
    assert ra[1] >= 30 and rb[1] >= 30

# ---- 2. matchmaking ---------------------------------------------------------------------------------------------------
assert window(0) == 50 and window(10) == 100 and window(70) == 400 and window(1000) == 400
P = lambda i, r, j, tc='blitz': (i, r, j, tc)
assert compatible(P(1, 1500, 0), P(2, 1540, 0), 0) and not compatible(P(1, 1500, 0), P(2, 1551, 0), 0)
assert compatible(P(1, 1500, 0), P(2, 1550, 0), 0)                                  # exactly at the window
assert not compatible(P(1, 1500, 0), P(2, 1500, 0, 'rapid'), 0)                     # different time control
assert not compatible(P(1, 1500, 0), P(2, 1600, -100), 0)                           # q waited long, p just arrived: p's window decides


def tick_ref(queue, now):
    order = sorted(queue, key=lambda p: (p[2], p[0]))
    used, pairs = set(), []
    for p in order:
        if p[0] in used:
            continue
        best = None
        for q in queue:
            if q[0] == p[0] or q[0] in used or not compatible(p, q, now):
                continue
            key = (abs(p[1] - q[1]), q[0])
            if best is None or key < best[0]:
                best = (key, q)
        if best:
            used.update((p[0], best[1][0]))
            pairs.append((p[0], best[1][0]))
    return pairs


for trial in range(400):
    n = rng.randint(0, 25)
    now = rng.randint(0, 120)
    queue = [P(i, rng.choice([1400, 1450, 1500, 1500, 1510, 1700]) + rng.randint(-60, 60), now - rng.randint(0, 100),
               rng.choice(['blitz', 'blitz', 'rapid'])) for i in range(n)]
    pairs, left = match_tick(queue, now)
    assert pairs == tick_ref(queue, now), (queue, now)
    ids = [x for pr in pairs for x in pr]
    assert len(ids) == len(set(ids)) and set(ids) | {p[0] for p in left} == {p[0] for p in queue}
    by = {p[0]: p for p in queue}
    assert all(compatible(by[a], by[b], now) for a, b in pairs)
    # maximality: no two players left in the queue could have been paired
    lp = [by[i] for i in sorted(by) if i not in set(ids)]
    assert not any(compatible(x, y, now) for i, x in enumerate(lp) for y in lp[i + 1:]), 'a compatible pair was left waiting'
# a nearest neighbour whose own window is too narrow must not hide a farther player whose window is wide enough
# windows at now=100: player 1 waited 100 s (400), 2 just arrived (50), 3 waited 100 s (400)
pairs, _ = match_tick([P(1, 1500, 0), P(2, 1520, 100), P(3, 1580, 0)], 100)
assert pairs == [(1, 2)], pairs                                                    # gap 20 <= min(400, 50): the nearest compatible player wins
# a nearer player whose own window is too narrow must not hide a farther player whose window is wide enough
pairs, _ = match_tick([P(1, 1500, 0), P(2, 1560, 100), P(3, 1580, 0)], 100)       # 1-2 gap 60 > 50 (2's window); 1-3 gap 80 <= 400
assert pairs == [(1, 3)], pairs
assert match_tick([], 5) == ([], [])

m1 = simulate_queue(seed=3)
m2 = simulate_queue(seed=3)
assert m1 == m2, 'deterministic'
assert m1['pairs'] > 500 and m1['max_gap'] <= 400
assert m1['median_wait_typical'] < m1['median_wait_outlier'], m1
assert m1['unmatched_outliers'] >= 1 or m1['p95_wait_outlier'] > m1['p95_wait_typical'], m1
print('queue sim:', m1)
assert (m1['pairs'], m1['max_gap'], m1['median_wait_typical'], m1['p95_wait_typical'], m1['median_wait_outlier'], m1['p95_wait_outlier'], m1['unmatched_outliers'], m1['outliers']) == (1385, 187, 0, 5, 6, 43, 0, 129)

# ---- 3. the game server -----------------------------------------------------------------------------------------------
memo = {}


def count(board, turn):
    """Number of complete games from this position as (X wins, O wins, draws); memoised on (board, turn)."""
    key = (tuple(board), turn)
    if key in memo:
        return memo[key]
    w = winner(board)
    if w:
        out = (1, 0, 0) if w == 'X' else (0, 1, 0)
    elif all(c is not None for c in board):
        out = (0, 0, 1)
    else:
        out = (0, 0, 0)
        for i in range(9):
            if board[i] is None:
                board[i] = turn
                sub = count(board, 'O' if turn == 'X' else 'X')
                board[i] = None
                out = tuple(x + y for x, y in zip(out, sub))
    memo[key] = out
    return out


tally = dict(zip('XOD', count([None] * 9, 'X')))
assert tally == {'X': 131_184, 'O': 77_904, 'D': 46_080} and sum(tally.values()) == 255_168, tally
assert len(memo) == 5478, len(memo)                                                  # the known number of reachable positions
assert winner([None] * 9) is None and winner(['X', 'X', 'X'] + [None] * 6) == 'X' and winner([None] * 6 + ['O', 'O', 'O']) == 'O'
assert winner(['X', None, None, 'O', 'X', None, None, None, 'X']) == 'X' and winner([None, None, 'O', None, 'O', None, 'O', None, None]) == 'O'

G = lambda **kw: Game(clock_ms=1000, inc_ms=100, lag_cap_ms=50, **kw)
gm = G()
assert gm.submit('X', 0, 4, 200) == 'ok'
assert gm.left['X'] == 1000 - 200 + 100 and gm.t0 == 200 and gm.turn == 'O'
before = (list(gm.board), dict(gm.left), gm.t0, gm.turn, list(gm.moves))
assert gm.submit('X', 0, 4, 5000) == 'dup'                                          # a retry of an accepted move: acknowledged, nothing changes
assert (gm.board, gm.left, gm.t0, gm.turn, gm.moves) == before
assert gm.submit('X', 0, 5, 300) == 'stale' and gm.submit('O', 0, 4, 300) == 'stale'
assert gm.submit('O', 2, 0, 300) == 'future'
assert gm.submit('X', 1, 0, 300) == 'not_your_turn'
assert gm.submit('O', 1, 4, 300) == 'illegal' and gm.t0 == 200 and gm.left['O'] == 1000   # an illegal move costs nothing and the clock runs on
assert gm.submit('O', 1, 9, 300) == 'illegal' and gm.submit('O', 1, -1, 300) == 'illegal'
assert gm.submit('O', 1, 0, 700) == 'ok' and gm.left['O'] == 1000 - 500 + 100
# lag credit is capped: a 40 ms lag is credited fully, a 5,000 ms claimed lag only 50 ms
a, b = G(), G()
assert a.submit('X', 0, 0, 300, lag=40) == 'ok' and a.left['X'] == 1000 - 260 + 100
assert b.submit('X', 0, 0, 300, lag=5000) == 'ok' and b.left['X'] == 1000 - 250 + 100
c = G()
assert c.submit('X', 0, 0, 0) == 'ok' and c.left['X'] == 1100                         # no time spent: the increment is a pure gain
# flag boundary: using exactly all the time is fine, one more millisecond is a loss
f1, f2 = G(), G()
assert f1.submit('X', 0, 0, 1000) == 'ok' and f1.left['X'] == 100
assert f2.submit('X', 0, 0, 1001) == 'flagged' and f2.result == ('O', 'timeout') and f2.submit('O', 0, 1, 1002) == 'over'
f3 = G()
assert f3.submit('X', 0, 0, 1050, lag=50) == 'ok'                                     # 1050 ms elapsed, 50 credited: exactly the clock
assert G().submit('X', 0, 0, 1051, lag=50) == 'flagged'
# the server's own timer: no message needed, with the lag allowance as grace
t = G()
assert t.flag_deadline() == 1000 + 50 and t.flag_check(1050) is False and t.result is None
assert t.flag_check(1051) is True and t.result == ('O', 'timeout') and t.flag_check(2000) is False
t = G()
t.submit('X', 0, 0, 200)
assert t.flag_deadline() == 200 + t.left['O'] + 50
# wins and draws
w = G()
for ply, (side, cell) in enumerate([('X', 0), ('O', 3), ('X', 1), ('O', 4), ('X', 2)]):
    assert w.submit(side, ply, cell, 10 * (ply + 1)) == 'ok'
assert w.result == ('X', 'win') and w.submit('O', 5, 5, 100) == 'over'
d = G()
seq = [0, 1, 2, 4, 3, 5, 7, 6, 8]
for ply, cell in enumerate(seq):
    assert d.submit('XO'[ply % 2], ply, cell, 10 * (ply + 1)) == 'ok'
assert d.result == ('-', 'draw')


def random_game(rng):
    """A random legal game as a list of (side, cell)."""
    gm, out = G(), []
    board, turn = [None] * 9, 'X'
    while True:
        free = [i for i in range(9) if board[i] is None]
        cell = rng.choice(free)
        board[cell] = turn
        out.append((turn, cell))
        if winner(board) or len(out) == 9:
            return out
        turn = 'O' if turn == 'X' else 'X'


def state(gm):
    return (gm.board, gm.moves, gm.left, gm.turn, gm.result, gm.t0)


for trial in range(300):
    plan = random_game(rng)
    gm = G()
    now, ply = 0, 0
    history = []
    # deliver each move once or several times, sometimes early (future) and sometimes late (stale / dup)
    while ply < len(plan):
        side, cell = plan[ply]
        now += rng.randint(1, 30)
        if rng.random() < 0.3 and ply + 1 < len(plan):
            s2, c2 = plan[ply + 1]
            assert gm.submit(s2, ply + 1, c2, now) == 'future'                      # next move arrives first: refused, nothing changes
        assert gm.submit(side, ply, cell, now, lag=rng.randint(0, 80)) == 'ok'
        history.append((side, cell))
        for _ in range(rng.randint(0, 2)):                                       # duplicates, delivered after
            st = state(gm)
            now += rng.randint(0, 3)
            assert gm.submit(side, ply, cell, now) == 'dup'                         # even after the game ended: the retry is acknowledged
            assert state(gm) == st
        ply += 1
    assert [(m[0], m[1]) for m in gm.moves] == plan and gm.result is not None
    ref = [None] * 9
    for side, cell in plan:
        ref[cell] = side
    assert gm.board == ref
    assert all(m[3] <= 50 for m in gm.moves)                                   # the log holds the lag actually credited (capped)
    # recovery from the log alone reproduces the whole state, clocks included, even under a different cap in the config
    rg = Game.replay(gm.log, clock_ms=1000, inc_ms=100, lag_cap_ms=50)
    assert state(rg) == state(gm)
    assert state(Game.replay(gm.log, clock_ms=1000, inc_ms=100, lag_cap_ms=500)) == state(gm)


# failover: a new owner takes over a game 30 s after the last move; the outage is charged to nobody
def crashed_game():
    gm = Game(clock_ms=10_000, inc_ms=0, lag_cap_ms=50)
    assert gm.submit('X', 0, 4, 1000) == 'ok'
    return gm


old = crashed_game()
bad = Game.replay(old.log, clock_ms=10_000, inc_ms=0, lag_cap_ms=50)              # replayed without a resume: the old turn clock
assert bad.flag_check(31_500) is True and bad.result == ('X', 'timeout')          # the outage is charged to the player on move (O loses on time)
new = Game.replay(old.log, clock_ms=10_000, inc_ms=0, lag_cap_ms=50)
new.resume(31_500)                                                                 # the new owner's own clock
assert new.flag_check(31_500) is False and new.result is None and new.t0 == 31_500
assert new.left == old.left                                                        # nobody lost or gained time
assert new.flag_deadline() == 31_500 + 10_000 + 50 and new.flag_check(41_550) is False and new.flag_check(41_551) is True
new = Game.replay(old.log, clock_ms=10_000, inc_ms=0, lag_cap_ms=50)
new.resume(31_500)
again = Game.replay(new.log, clock_ms=10_000, inc_ms=0, lag_cap_ms=50)             # a second failover replays the resume marker too
assert state(again) == state(new) and again.log == new.log
assert again.submit('O', 1, 0, 31_900) == 'ok' and again.left['O'] == 10_000 - 400    # 400 ms after the resume, on the new owner's clock
done = Game(clock_ms=1000, inc_ms=0, lag_cap_ms=50)
for ply, (sd, c) in enumerate([('X', 0), ('O', 3), ('X', 1), ('O', 4), ('X', 2)]):
    done.submit(sd, ply, c, 10 * (ply + 1))
done.resume(99_999)
assert done.result == ('X', 'win') and done.t0 == 50                                # resuming a finished game changes nothing
# fuzz with owner changes: after each resume the clock jumps to another machine's time base
for trial in range(200):
    plan = random_game(rng)
    gm = G()
    now, ply = 0, 0
    while ply < len(plan):
        if rng.random() < 0.3:
            now = rng.randint(-5000, 5000)                                          # another machine's clock, any offset
            gm.resume(now)
        now += rng.randint(1, 30)
        assert gm.submit(plan[ply][0], ply, plan[ply][1], now) == 'ok'
        ply += 1
    assert state(Game.replay(gm.log, clock_ms=1000, inc_ms=100, lag_cap_ms=50)) == state(gm)
    assert gm.left['X'] > 0 and gm.left['O'] > 0

# replay refuses a log that would not have been accepted
try:
    Game.replay([('X', 0, 10, 0), ('X', 1, 20, 0)], clock_ms=1000, inc_ms=100, lag_cap_ms=50)
    raise SystemExit('replay must refuse a log whose moves are not all accepted')
except AssertionError:
    pass

need('Failover must not cost anyone time', 'flags O', 'caps of 50 and 500', 'Caching Patterns and Consistent Hashing', 'Distributed Lock Service (Chubby / ZooKeeper)', '1,385 couples with a largest rating gap of 187', 'median wait of 0 seconds and a 95th-percentile wait of 5', '129 of them', 'median wait of 6 seconds and a 95th percentile of 43', 'none was still waiting', '5,478 distinct positions', 'Visual (planned)', '255,168', '131,184', '77,904', '46,080', '1464', '151.4', '0.376', '63.2')
forbid('Lichess uses Glicko-2 for', 'chess.com uses', "Glickman's 1995 paper", 'Caching and Consistent Hashing', 'millions of WebSocket', 'millions of spectators')
print('sy72 code checks passed')
