# Lesson 72 — Case Study: Multiplayer Game Backend and Matchmaking (online chess)

> **Priority:** ★★☆☆☆ (proposed; the curriculum data holds the final rating) — a recurring prompt in a gaming-flavoured loop, and a clean test of whether you can separate rating maths, queue design and a real-time server that must survive retries, lag and crashes.
>
> **Study time:** 70 minutes. **Do this after:** Real-Time Gaming Leaderboard; Scaling Patterns II: Large Blobs, Long-Running Tasks and Real-Time Updates; Caching Patterns and Consistent Hashing; Time, Clocks and Ordering; Distributed Lock Service (Chubby / ZooKeeper).
>
> **Level:** extended.

Two strangers click "play". The system must pick opponents of similar strength without making anyone wait forever, run the game with a clock neither can cheat, tolerate a dropped connection or a retried move without corrupting the game, and update ratings afterwards. The code is checked in `test/lesson_code/sy72_check.py`: the rating update reproduces the worked examples in Glickman's paper, the queue is compared with a brute-force matcher, and the game server is tested with duplicated, late and early moves. Capacity figures come from `capacity_check_i.py`. Leaderboards are not re-taught (see Real-Time Gaming Leaderboard), nor is routing by hash (see Caching Patterns and Consistent Hashing).

---

## 1. Mental Model

> **Three components with three different clocks: ratings change once per game and may be slow, matchmaking runs once per second over a small queue, and the game itself must answer in tens of milliseconds and must be the only authority on whose turn it is and how much time is left.**

- **A rating is an estimate with an error bar.** A system that stores only a number cannot tell a new player from a veteran; one that stores a number and its uncertainty can (section 5).
- **Matchmaking trades quality for wait.** A tight rating window gives fair games and long waits; a window that widens with waiting time gives a bound on both (section 6).
- **The server owns the game.** Clients propose moves; the server validates, orders, times and records them. Nothing the client says about time is trusted beyond a capped allowance for lag (section 7).
- **A move has a position in the game.** Numbering moves (the "ply") makes a retried move harmless and a skipped move detectable.
- **Persist the log, not the process.** A game server holds state in memory for speed, so recovery means replaying the move log; that is only correct if replay is tested (section 7).

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "match players of similar skill" | rating with uncertainty (Glicko-style) plus a queue whose window widens with wait (sections 5, 6) |
| "players should not wait too long" | window growth with a cap; measure median and tail wait (section 6) |
| "what if a client sends the move twice" | number the moves; a retry of an accepted move is acknowledged, nothing is applied again (section 7) |
| "a client has lag" | server-side clock; credit a capped amount of measured lag (section 7) |
| "flag a player who disappears" | a server timer, not a client message (section 7) |
| "server crashes mid-game" | append-only move log; rebuild by replay |
| "many spectators" | fan out from the game owner through a separate gateway tier; see Scaling Patterns II |
| "leaderboard" | see Real-Time Gaming Leaderboard |

---

## 3. Requirements and Capacity

**Functional.** Seek a game by time control; get paired; play moves under a clock; handle resignation, draw offers and disconnects; rate finished games; let others watch live; keep a history of games.

**Non-functional.** A move is acknowledged in tens of milliseconds; no move is applied twice or lost; time is decided by the server; a game survives the loss of its server; matchmaking makes quality-bounded pairs with bounded wait.

**Capacity.** All inputs are assumptions chosen to size the design, not statistics about any service; outputs are computed in `capacity_check_i.py`.

| Quantity | Assumption or derivation | Result |
|---|---|---|
| Concurrent games at peak | assumed | 100,000 (so at least 200,000 connected players: a game has two) |
| Connections | 200,000 players plus an assumed 100,000 spectators | about 300,000 |
| Game length | assumed 10 minutes, 40 moves per side | 600 seconds, 80 moves |
| Moves per second | 100,000 games x 80 moves / 600 s | about 13,333 |
| Messages per move | assumed: ack to the mover, push to the opponent, one spectator on average | 3, so about 40,000 messages per second |
| Games started per second | 100,000 games / 600 s | about 167 (about 14.4 million per day if the peak load lasted all day, so an upper bound) |
| Seeks per second | two players per game | about 333 |
| Players waiting | Little's law with an assumed 10 s mean wait | about 3,333 |
| Live state per game | assumed 1.5 KB | 150 MB for all games, small enough to keep in memory |
| Move log per game | 80 moves x 32 bytes (assumed) | 2,560 bytes, so about 36.9 GB per day at the constant-load upper bound |

The point of the table is what is small. The whole live state fits in the memory of one machine and the whole queue is a few thousand rows. The state is small; the load is the 300,000 connections and about 40,000 messages per second. Whether one machine could carry that depends on the machine and is not measured here, so treat splitting connections from games as a design choice for independent scaling and failure (section 8), not as a limit the table proves. Work is routed by game id.

---

## 4. API and Data Model

```
WS  /play        {type: seek, time_control} -> {type: matched, game_id, color}
WS  /game/{id}   {type: move, ply, cell, client_ts}   -> {type: ack|dup|stale|future|illegal|...}
                 server pushes: opponent_move, clock, result
POST /games/{id}/resign | draw_offer | draw_accept
GET  /games/{id}                                       -> moves, result, clocks (for spectators and reconnection)
```

| Store | Key | Notes |
|---|---|---|
| ratings | (player, time control) | rating, deviation, last-played time; one row per rating pool |
| queue | in memory per time control | rebuilt from reconnecting clients; losing it costs a few seconds, not data |
| live game | game id | in the owner process; board, clocks, move list |
| move log | (game id, ply) | durable, append-only; the source of truth for recovery and history |
| finished games | game id | moves, result, rating before and after, for audit and for recomputation |

---

## 5. Deep Dive 1: Ratings With an Error Bar

Elo's system gives each player a number; the expected score against an opponent is a logistic function of the rating difference, and the number moves by a fixed multiple of (score minus expected). Glickman's paper *The Glicko system* (he says he created the system in 1995), which this section implements, starts from one weakness: two players both rated 1700 are treated alike even if one has not played for years. He adds a **ratings deviation** (RD), a standard deviation that measures how uncertain the rating is. Time away raises it; each game lowers it; a new player starts at rating 1500 with RD 350. He notes that Elo is a special case of his system and that, in his, rating changes are not balanced between the two players: an uncertain player moves a lot, a well-known one barely.

```python
import math

Q = math.log(10) / 400


def g(rd):
    """Discount for the opponent's uncertainty: a shaky rating counts for less."""
    return 1 / math.sqrt(1 + 3 * Q * Q * rd * rd / math.pi ** 2)


def expected(r, rj, rdj):
    return 1 / (1 + 10 ** (-g(rdj) * (r - rj) / 400))


def update(r, rd, games):
    """One Glicko rating period. games: [(opponent rating, opponent rd, score 1 / 0.5 / 0)]."""
    if not games:
        return r, rd
    es = [expected(r, rj, rdj) for rj, rdj, _ in games]
    d2inv = Q * Q * sum(g(rdj) ** 2 * e * (1 - e) for (_, rdj, _), e in zip(games, es))
    denom = 1 / rd ** 2 + d2inv
    new_r = r + Q / denom * sum(g(rdj) * (s - e) for (_, rdj, s), e in zip(games, es))
    return new_r, math.sqrt(1 / denom)


def age(rd, c, periods=1):
    """Uncertainty grows while a player is away, up to the unrated value 350."""
    return min(math.sqrt(rd * rd + c * c * periods), 350.0)


def c_for(rd_typical, periods, rd_max=350.0):
    """The c for which a typical player reaches an unrated player's RD after `periods` rating periods."""
    return math.sqrt((rd_max ** 2 - rd_typical ** 2) / periods)


def win_prob(r1, rd1, r2, rd2):
    return 1 / (1 + 10 ** (-g(math.sqrt(rd1 ** 2 + rd2 ** 2)) * (r1 - r2) / 400))


def rate_game(a, b, score_a, floor=30.0):
    """Rate one finished game. a and b are (rating, rd) from BEFORE the game; both updates use the pre-game values."""
    na = update(a[0], a[1], [(b[0], b[1], score_a)])
    nb = update(b[0], b[1], [(a[0], a[1], 1 - score_a)])
    return (na[0], max(floor, na[1])), (nb[0], max(floor, nb[1]))
```

The check pins the implementation to the paper (Glickman, *The Glicko system*), not to a second implementation of the same formulas:

- The discount table for RD 30, 100, 300 is 0.9955, 0.9531, 0.7242; the expected scores in the paper's example are 0.639, 0.432, 0.303.
- The worked example (a 1500 player with RD 200 beats a 1400 and loses to 1550 and 1700 players of RD 30, 100 and 300) gives rating 1464 and RD 151.4.
- The expected-outcome example (1400 with RD 80 against 1500 with RD 150) gives 0.376; the two directions always sum to 1; more uncertainty pulls the probability towards one half.
- The paper's choice of `c` (typical RD 50, thirty 2-month periods to reach 350) gives 63.2, and `age` caps at the unrated value 350.
- In 500 random cases a win raises the rating, a loss lowers it, a draw lands between them, and any game shrinks RD.
- The balance claim: a new player (1700, RD 350) who beats an established one (1700, RD 50) gains more than three times what the loser loses.

Two practical rules the paper gives are in the code and tested. First, an RD floor: the paper warns that very frequent players' ratings stop moving and recommends a floor such as 30; `rate_game` applies 30. Second, the paper's "rating period" can be as short as a minute, with ratings updated game by game; `rate_game` does that, and it must use **both players' pre-game values**. The check rates 200 random games from both sides and requires the same result, and shows that updating A first and then feeding A's new values into B's update gives a different (wrong) answer for B.

**What Lichess's open-source code shows.** The file `modules/rating/src/main/Glicko.scala` in the Lichess repository (read on 27 November 2026) defines a default rating of 1500, a maximum deviation of 500, a minimum deviation of 45, and the thresholds 75 (standard chess) and 65 (variants) under which a deviation is "rankable". It carries a third value, volatility (default 0.09), which is the extra parameter of Glickman's later Glicko-2 paper. It caps a single game's rating change at 700 points and sets the rate at which deviation grows with time "so a typical player's RD goes from 60 -> 110 in 1 year" (a code comment). The lesson reads that file as a set of tuned constants for one service, not as a recommendation, and it does not implement Glicko-2.

**What the formulas leave open.** Separate pools per time control, whether a provisional player (high RD) may appear on a leaderboard, and abuse such as losing on purpose are policy questions, not maths.

---

## 6. Deep Dive 2: The Matchmaking Queue

The queue holds players who clicked "play". Each second, a tick pairs players. Two requirements pull against each other: close ratings (fair games) and a short wait. The standard resolution is a rating window that widens with waiting time. The code below uses a base of 50 points growing by 5 per second to a cap of 400 (illustrative constants, so a player waiting 70 seconds accepts anyone within 400).

```python
import bisect, random


def window(wait, base=50, grow=5, cap=400):
    """Acceptable rating gap after `wait` seconds in the queue."""
    return min(base + grow * wait, cap)


def compatible(p, q, now):
    """p, q = (id, rating, joined_at, time_control). Both players must accept the gap."""
    return (p[3] == q[3]
            and abs(p[1] - q[1]) <= min(window(now - p[2]), window(now - q[2])))


def match_tick(queue, now):
    """Pair the longest-waiting player first with the closest compatible rating. Returns (pairs, left over)."""
    by_tc = {}
    for p in queue:
        by_tc.setdefault(p[3], []).append((p[1], p[0]))
    for lst in by_tc.values():
        lst.sort()
    byid = {p[0]: p for p in queue}
    used, pairs = set(), []
    for p in sorted(queue, key=lambda x: (x[2], x[0])):
        if p[0] in used:
            continue
        lst, w = by_tc[p[3]], window(now - p[2])
        lo = bisect.bisect_left(lst, (p[1] - w, -1))
        hi = bisect.bisect_right(lst, (p[1] + w, float('inf')))
        best = None
        for r, qid in lst[lo:hi]:
            if qid == p[0] or qid in used or not compatible(p, byid[qid], now):
                continue
            key = (abs(r - p[1]), qid)
            if best is None or key < best:
                best = key
        if best:
            used.update((p[0], best[1]))
            pairs.append((p[0], best[1]))
    return pairs, [p for p in queue if p[0] not in used]


def simulate_queue(seed=1, seconds=900, per_second=3):
    """Players arrive each second with ratings from a normal(1500, 250); the queue is ticked once a second."""
    rng = random.Random(seed)
    queue, waits, gaps, nid = [], {}, [], 0
    arrivals = {}
    for now in range(seconds):
        for _ in range(per_second * 2):
            if rng.random() < 0.5:
                nid += 1
                r = min(3000, max(400, rng.gauss(1500, 250)))
                queue.append((nid, r, now, 'blitz'))
                arrivals[nid] = (r, now)
        pairs, queue = match_tick(queue, now)
        for a, b in pairs:
            waits[a], waits[b] = now - arrivals[a][1], now - arrivals[b][1]
            gaps.append(abs(arrivals[a][0] - arrivals[b][0]))
    settled = [i for i, (r, t) in arrivals.items() if t < seconds - 120]     # ignore the tail still queueing at the end
    typical = [i for i in settled if abs(arrivals[i][0] - 1500) <= 250]
    outlier = [i for i in settled if abs(arrivals[i][0] - 1500) > 500]
    med = lambda xs: sorted(xs)[len(xs) // 2]
    p95 = lambda xs: sorted(xs)[int(0.95 * (len(xs) - 1))]
    tw = [waits[i] for i in typical if i in waits]
    ow = [waits[i] for i in outlier if i in waits]
    return {'pairs': len(gaps), 'max_gap': round(max(gaps)),
            'median_wait_typical': med(tw), 'p95_wait_typical': p95(tw),
            'median_wait_outlier': med(ow), 'p95_wait_outlier': p95(ow),
            'unmatched_outliers': sum(1 for i in outlier if i not in waits), 'outliers': len(outlier)}
```

Design choices the check pins:

- **Both players must accept.** The gap must fit inside the *smaller* of the two windows. If only the searcher's window counted, a veteran of the queue could be paired with someone who has waited a second and would refuse a gap that wide.
- **Oldest first, nearest rating.** The longest-waiting player picks first and takes the closest compatible partner (ties by id). The code scans only the sorted ratings inside the searcher's window, using binary search, but it must not stop at the nearest rating, because the nearest player's own window may be too narrow while a farther player's is wide enough. The check has that exact case: with windows of 400, 50 and 400, player 1 is paired with the farther player 3 when the nearer player 2 is 60 away (more than 2's window of 50).
- **No missed pair.** After a tick, no two left-over players of one time control could have been paired. The check asserts this over 400 random queues, and also that the output equals a double loop written independently, that every pair is compatible, and that nobody is paired twice or lost.

**Does it stay live?** A simulation (seed 3, illustrative: three arrivals per second on average for 900 seconds, ratings from a normal distribution with mean 1500 and standard deviation 250, one tick per second) paired 1,385 couples with a largest rating gap of 187. Players within one standard deviation of the mean had a median wait of 0 seconds and a 95th-percentile wait of 5; players more than two standard deviations out (129 of them) had a median wait of 6 seconds and a 95th percentile of 43, and none was still waiting at the end. That is one invented load with a dense pool; a sparse pool (a rare time control, an odd hour) behaves differently. A player at 2,900 may wait the full 70 seconds for the window to reach 400 and then be paired with nobody, which is why products add a bot, a wider cap or a "no opponent found" outcome. Measure the tail wait, not the average.

**Scaling the queue.** One tick over a few thousand players is cheap; shard by time control (and rating band with overlapping bands if needed).

---

## 7. Deep Dive 3: The Game Server

The game server is authoritative: it decides which moves are legal, whose turn it is and how much time each side has. The class below uses tic-tac-toe in place of chess so that every rule can be checked exhaustively; the protocol around the rules is what carries over.

```python
LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


def winner(board):
    for a, b, c in LINES:
        if board[a] is not None and board[a] == board[b] == board[c]:
            return board[a]
    return None


class Game:
    """Server-authoritative tic-tac-toe standing in for chess. Times are integer milliseconds on the SERVER's clock."""
    def __init__(self, clock_ms=60_000, inc_ms=0, lag_cap_ms=100, start_ms=0):
        self.board, self.moves, self.log, self.turn, self.result = [None] * 9, [], [], 'X', None
        self.left = {'X': clock_ms, 'O': clock_ms}
        self.inc, self.cap, self.t0 = inc_ms, lag_cap_ms, start_ms

    def submit(self, side, ply, cell, now, lag=0):
        """ply = number of moves the sender believes are already on the board. Returns a status string."""
        if ply < len(self.moves):                                   # already decided: acknowledge a retry, refuse a rival
            return 'dup' if self.moves[ply][:2] == (side, cell) else 'stale'
        if self.result:
            return 'over'
        if ply > len(self.moves):
            return 'future'                                         # a gap: the earlier move has not arrived yet
        if side != self.turn:
            return 'not_your_turn'
        credit = min(lag, self.cap)                                 # credit at most `cap` ms of network delay
        charge = max(0, now - self.t0 - credit)
        if charge > self.left[side]:
            self.result = ('O' if side == 'X' else 'X', 'timeout')
            return 'flagged'
        if not 0 <= cell < 9 or self.board[cell] is not None:
            return 'illegal'                                        # costs nothing; the clock keeps running
        self.left[side] += self.inc - charge
        self.t0 = now
        self.board[cell] = side
        self.moves.append((side, cell, now, credit))                # the log records the credit actually used
        self.log.append(self.moves[-1])
        w = winner(self.board)
        if w:
            self.result = (w, 'win')
        elif len(self.moves) == 9:
            self.result = ('-', 'draw')
        else:
            self.turn = 'O' if side == 'X' else 'X'
        return 'ok'

    def flag_deadline(self):
        return self.t0 + self.left[self.turn] + self.cap            # the allowance for lag is the grace period

    def flag_check(self, now):
        """The server's own timer: ends the game even if the player's message never arrives."""
        if self.result is None and now > self.flag_deadline():
            self.result = ('O' if self.turn == 'X' else 'X', 'timeout')
            return True
        return False

    def resume(self, now):
        """A new owner takes over. The outage is charged to nobody: the turn clock restarts at the new owner's time."""
        if self.result is None:
            self.t0 = now
        self.log.append(('resume', now))

    @classmethod
    def replay(cls, log, **config):
        """Rebuild a game from its log: accepted moves (side, cell, now, credit) and ('resume', now) markers, in order."""
        game = cls(**config)
        for entry in log:
            if entry[0] == 'resume':
                game.resume(entry[1])
                continue
            side, cell, now, credit = entry
            assert game.submit(side, len(game.moves), cell, now, credit) == 'ok', 'the log holds a move that is not valid'
        return game
```

**Rules and an exhaustive check.** Counting every complete game with `winner` gives 255,168, of which 131,184 are won by X, 77,904 by O and 46,080 drawn, over 5,478 distinct positions. Those are the known counts for the game; the check recomputes them, which validates both the win detection and the legality rule.

**Retries, stale and early moves.** Each move carries `ply`, the number of moves the client believes have been played. The server answers:

| Situation | Answer | Effect |
|---|---|---|
| `ply` equals the move count, right player, legal | `ok` | applied, clock charged |
| `ply` is already decided and the same move | `dup` | acknowledged, nothing changes (checked: board, clocks, turn and log identical before and after) |
| `ply` is already decided and a different move | `stale` | refused |
| `ply` is ahead of the log | `future` | refused: an earlier move has not arrived |
| wrong player | `not_your_turn` | refused |
| occupied or off-board cell | `illegal` | refused, and the clock is not touched |
| game finished | `over` | refused |

The check plays 300 random games in which each move is sometimes preceded by the next move arriving early (it must be refused as `future`) and followed by up to two duplicates; the final move list always equals the intended one. Without the `ply`, a retry of a move on a square that happens to be free again, or a late duplicate after the opponent moved, could be applied as a new move.

**Clocks.** All times are integer milliseconds on the server. A move costs the time since the turn began, minus a lag credit capped at `cap`: a client reporting 5,000 ms of lag is credited only 50 ms in the test configuration. The credit must come from the server's own measurement where possible; a client-reported figure is untrusted and the cap bounds what a lying client can gain per move. The check pins the boundaries: using exactly all remaining time is legal and one millisecond more flags the player; a 1,050 ms move with 50 ms credit is exactly on the limit and 1,051 flags; a move at time 0 gains the increment in full; an illegal move leaves clock and turn untouched.

**Flagging without a message.** A player who has disconnected sends nothing, so the server needs a timer: `flag_deadline` is the turn start plus the remaining time plus the lag allowance, and `flag_check` ends the game after it. The grace period is the same cap, so a player with legitimate lag is never flagged by the timer before a move that would have been accepted. The lesson chose these semantics; they are not a description of any service.

**Recovery by replay.** The log stores `(side, cell, server time, lag credited)` for each accepted move, where the lag is the credit actually used (already capped), so a replay under a different configured cap still reproduces the same clocks (the check replays under caps of 50 and 500). `Game.replay` feeds the log back through `submit`; the check requires the rebuilt game to equal the original in board, moves, clocks, turn, result and turn start for all 300 fuzz games, and refuses a log containing a move that would not have been accepted. That is why the server logs what it accepted, with the time it used, and not what it received.

**Failover must not cost anyone time.** A naive replay restores the turn clock as of the last move, and the new owner then counts the whole outage against the player on move. The check shows it: with 10 seconds on the clock and X's move at 1.0 s, a new owner replaying at 31.5 s flags O, who lost on time because a server died. `resume(now)` restarts the turn clock at the new owner's time, so the thinking time already spent before the crash is given back (generous by a few seconds at most; periodic clock checkpoints in the log would be the stricter alternative) and nobody is charged for the outage. It also keeps the clocks of different machines apart: a move's charge is always a difference of two times from the same owner, because a `('resume', now)` marker in the log re-bases the clock, and a second failover replays that marker too. The check changes the time base after random resumes (offsets of up to 5 seconds either way) and replays to the same state. This is the Time, Clocks and Ordering lesson applied: use durations on one clock, never absolute times across machines.

Visual (planned): a timeline of one move with the client send time, the server receive time, the lag credit and the clock charge.

---

## 8. Scale: Routing, Connections and Spectators

- **One owner per game.** All traffic for a game goes to the process that owns it, found by hashing the game id over live servers (see Caching Patterns and Consistent Hashing). Ordering, clocks and the validity of a move need a single writer; with two owners a duplicated move or a double flag becomes possible. Failover does not make that automatic: a partitioned old owner can keep appending moves while the new one runs the game. Make the log append conditional (put-if-absent on `(game id, ply)`) or carry a fencing token from the election, so the stale owner's writes are refused; Distributed Lock Service (Chubby / ZooKeeper) covers the token and is not re-taught here.
- **Separate the connection tier.** Keeping hundreds of thousands of WebSocket connections open (the table's 300,000) is a different resource problem from running games. The Lichess repository's README (read on 27 November 2026) says its WebSocket connections are handled by a separate server that communicates with the main application over Redis; the lesson takes from that only that this split exists in one open-source chess server, and designs its own the same way. Real-time updates and fan-out are covered in Scaling Patterns II.
- **Failover.** When an owner dies, a new owner is chosen, rebuilds each live game by replay, calls `resume` so the outage is not charged, and tells clients, who reconnect and re-send any unacknowledged move with the same `ply`. A retried move is `dup` if it was logged and `ok` if it was not.
- **The log is the bottleneck to watch.** At about 13,333 moves per second the log must be appended before the acknowledgement for the guarantees above to hold; if you acknowledge first and log asynchronously, a crash can lose an acknowledged move.

---

## 9. Failure Modes

| What breaks | What happens | Mitigation |
|---|---|---|
| Client retries a move | double apply | `ply` numbering; `dup` acknowledgement |
| Client lies about lag | free time | server-side measurement; capped credit |
| Player disconnects | clock never ends | server flag timer |
| Owner process crashes | games lost, or the player on move flagged for the outage | log before ack; replay on a new owner, then `resume` (tested) |
| Old owner partitioned, still appending | two writers | conditional append or fencing token (section 8) |
| Sparse rating region | very long waits | cap the window, offer a bot or an explicit outcome |
| Rating update uses post-game values | asymmetric, wrong ratings | both updates from pre-game values (tested) |

---

## 10. What Real Companies Did

- **Glicko.** Glickman's paper (read on 27 November 2026) says the system was implemented on the Free Internet Chess Server with game-by-game updates, and that variations have been adopted by other online game organisations. It is the source of the formulas and worked examples above.
- **Lichess.** Its source repository is public. Read: the README and `Glicko.scala`, as described in sections 5 and 8. Not read: the matchmaking and game-server code, its architecture diagram image or any engineering post, so nothing here describes how Lichess pairs players or runs clocks.
- **Not read:** Chess.com, commercial matchmaking, TrueSkill (the paper was fetched but its text could not be extracted).

---

## 11. Pitfalls Checklist

1. Storing a rating without an uncertainty, then treating a debut like a veteran.
2. Computing the second player's update from the first player's new rating.
3. Requiring only the searcher's window to hold, so someone is paired outside their own tolerance.
4. Stopping the candidate scan at the nearest rating.
5. Measuring matchmaking by the average wait instead of the tail.
6. Moves without a sequence number, so retries or late duplicates can be applied.
7. Trusting a client-reported lag or clock.
8. Charging the clock for an illegal move, or not charging for time before a legal one.
9. Having no server timer, so a disconnected player never flags.
10. Acknowledging a move before it is in the log.
11. Replaying a game after failover without restarting the turn clock: the outage is charged to the player on move.

---

## Drills

1. Why does Glicko keep an RD, and what two things change it?
2. A new player (RD 350) beats a veteran (RD 50), both at 1700. Which rating moves more, and what does the paper say about the sum of the two changes?
3. In `match_tick`, why must the candidate scan not stop at the nearest rating?
4. A player has waited 30 seconds and another 2 seconds, and they are 120 points apart. Using the lesson's constants, will they be paired? (Compute both windows.)
5. A move arrives for `ply` 7 when the log has 7 entries and the game's turn belongs to the other side. What is the answer? And for `ply` 9?
6. A client claims 3,000 ms of lag on every move. How much does the lesson's design credit it, and what would you change to avoid trusting the claim?
7. The owner crashes after logging move 12 but before acknowledging it. What happens when the client retries?
8. Using the sizing table, what grows with the number of games and what does not: connections, queue size, live state, log appends?

---

## Homework

1. Add a rating-period update that takes several games for one player at once and reproduce the paper's three-game example through `rate_game` calls versus one `update` call. Explain any difference.
2. Write a server-side lag estimator (median of the last five ping round trips divided by two) and use it instead of the client-reported `lag`. What happens to the lag-lying test?

---

## Sources

All read on 27 November 2026.

- Mark E. Glickman, *The Glicko system* (glicko.net/glicko/glicko.pdf), read in full. Source for the formulas, the worked examples (1464 and 151.4; 0.376; c = 63.2), the defaults (1500, 350), the RD floor suggestion and the remark that Elo is a special case.
- Mark E. Glickman, *Example of the Glicko-2 system* (glicko.net/glicko/glicko2.pdf), read in part (the introduction and the step list). Source for what volatility is; not implemented.
- Lichess, `lila` repository: `README.md` and `modules/rating/src/main/Glicko.scala` (raw.githubusercontent.com/lichess-org/lila/master/), read in full. Source for the constants and the WebSocket and Redis remarks.
- Wikipedia, *Elo rating system* (en.wikipedia.org/wiki/Elo_rating_system), skimmed; used only to confirm that the expected score is a logistic function of the rating difference with scale 400.
- Not read: Lichess's pairing and game-server code and architecture image; engineering posts by any game company; the TrueSkill paper (fetched, text not extractable); Chess.com material.

## Further reading (not consulted)

- Herbrich, Minka and Graepel, *TrueSkill: a Bayesian skill rating system*.
- Arpad Elo, *The Rating of Chessplayers, Past and Present*.

*Last reviewed: 27 November 2026.*
