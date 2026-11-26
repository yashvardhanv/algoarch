# Lesson 39 — Real-Time Gaming Leaderboard at 10M QPS

> **Priority:** ★★★★☆ — a compact prompt that tests data-structure choice, tie-breaking and sharding trade-offs in one go.
>
> **Study time:** 50 minutes. **Do this after:** Redis Internals & Eviction and Replication & Sharding.
>
> **Level:** extended. Worth doing if your loops include gaming, social or ranking products.

"Show the top 100, and show me my rank" sounds like a sort. At tens of millions of players with scores
changing every second it is a data-structure question (what answers rank in `O(log N)`), a precision question
(how do you break ties inside a 64-bit float), and a sharding question with a twist: **the usual way to shard
makes top-K easy and rank expensive**. This lesson builds each piece, checks it against sorting, and sizes it.
The "10M QPS" in the title is the kind of number an interviewer throws out; the method below is how you test
whether a design meets any given number.

---

## 1. Mental Model

> **A leaderboard is an ordered index on (score, tiebreak). Top-K reads the front of it; rank counts the
> entries in front of you. Every design choice is about keeping that count cheap as the index is split.**

What follows from it:

- **Rank needs order statistics,** not just ordering. A plain heap gives the top but not "how many are above me".
  Redis sorted sets give both: they are a skip list plus a hash table, with `O(log N)` rank.
- **Ties must be decided by the key, not by luck.** Encode the tiebreak (earlier achievement wins) into the sort key.
- **Splitting by player (hash sharding) keeps writes local but makes rank ask every shard;** splitting by score
  range keeps rank cheap but creates hot shards. Pick from the read/write mix.
- **Exact rank is for the top; approximate rank is fine for everyone else.** "Top 3%" can come from a histogram.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "top 100 and my rank, live" | a sorted set per leaderboard (Redis `ZADD`, `ZREVRANGE`, `ZREVRANK`) |
| "keep each player's best score" | `ZADD ... GT` (update only if greater) |
| "equal scores: earlier wins" | pack points and time into one integer score below 2^53 |
| "players near me" | rank, then a range around it (`ZRANGE key max(0, rank-r) rank+r REV`) |
| "global board, hundreds of millions of players" | exact top tier plus histogram percentiles for everyone else |
| "daily / weekly / per-region boards" | one sorted set per board key; expire or archive old ones |
| "scores must never be lost" | the sorted set is a cache; the durable score log lives in a database |

---

## 3. Requirements and Capacity

**Functional.** Submit a match result; show the top 100; show a player's rank and the players around them;
one board per season.

**Non-functional.** A new score is reflected within about a second; rank reads in single-digit milliseconds
on the server; no score lost (the durable record is not the leaderboard).

**Capacity estimate.** Inputs are **assumptions** for the exercise; every result is reproduced by
`test/lesson_code/capacity_check.py`. The per-shard throughput figure in particular is a placeholder to replace
with your own benchmark: Redis's benchmark page shows that results depend heavily on hardware, pipelining and
the command mix.

| Input (assumed) | Value |
|---|---|
| players on the season board | 50 million |
| memory per sorted-set entry | 100 bytes (measure it on your data) |
| peak score submissions | 5,000 per second |
| peak rank reads | 50,000 per second |
| top-100 reads | served from a cache refreshed once per second |
| sorted-set operations one shard can serve | 50,000 per second |

| Result | Arithmetic | Value |
|---|---|---|
| memory for one board | 50M x 100 B | 5 GB |
| operations on one primary | 5,000 + 50,000 | 55,000 per second: above the assumed 50,000 |
| hash-shard into 4: memory and writes per shard | 5 GB / 4; 5,000 / 4 | 1.25 GB and 1,250 writes/s per shard |
| hash-shard into 4: rank reads | each rank asks all 4 shards | 200,000 shard operations/s, 50,000 on every shard |
| instead, 1 primary + 2 read replicas | 50,000 / 3 + 5,000 replicated writes | about 21,667 operations/s per node (16,667 rank reads + 5,000 writes) |
| ten times the writes (50,000/s), 4 hash shards | 50,000 / 4 + 50,000 | 62,500 per shard: above the assumed 50,000 |
| ten times the writes, 1 primary + 2 replicas | 50,000 / 3 + 50,000 | about 66,667 per node: above the assumed 50,000 |
| ten times the writes, 4 hash shards each with 2 replicas | 50,000 / 3 + 12,500 | about 29,167 per node |

The punchline is in rows three to five: **hash sharding divides memory and writes but not rank reads**, because a
rank needs a count from every shard, so every shard still sees all 50,000 rank reads. Replicas divide reads, but every
replica applies every write, and ranks are slightly stale (Redis replication is asynchronous). For this mix, one
primary with read replicas fits. With ten times the writes, **neither option fits alone** (rows six and seven):
combine them, hash shards to divide the writes and replicas on each shard to divide the fan-out rank reads (row
eight), or shard by score range, which makes a rank read touch one shard plus cached counts of the shards above it
(cutting the fan-out) but concentrates writes on the busiest score ranges.

Visual (planned): a game server writing to a durable score log and to the sorted set, with read replicas serving rank and a cache serving the top 100.

---

## 4. API and Data Model

```
POST /boards/{season}/scores          {player, points, achieved_at}
GET  /boards/{season}/top?k=100
GET  /boards/{season}/players/{id}    -> {rank, points, neighbours: [...]}
```

- **Durable record:** `scores(player, season, points, achieved_at)` in a database; the source of truth.
- **Sorted set** `board:{season}`: member = player id, score = packed points and time. Rebuildable from the durable record.
- **Top-100 cache:** refreshed once per second, so 100,000 viewers cost one sorted-set read per second per cache node.

---

## 5. Deep Dive 1: Ties Inside a Double

Redis scores are double-precision floats. Its docs say a double represents integers exactly between
`-(2^53)` and `2^53`, and that equal scores are ordered by member, byte-wise. A common answer packs the tiebreak
into the fraction, `score + (1 - timestamp / 10^12)`. It fails twice, and the check proves both:

- With millisecond timestamps (about `1.7 x 10^12` today) the fraction is negative: 1,500 points becomes 1499.3.
- With second timestamps, at 1,000,000 points the gap between adjacent doubles is about `1.16 x 10^-10`, far larger
  than the `10^-12` a one-second difference contributes, so two players one second apart get **the same double**.

Pack integers instead, with the bit budget written down:

```python
POINT_BITS, TIME_BITS = 20, 23        # points < 1,048,576; a season shorter than 2**23 s (about 97 days)

def pack(points, achieved_at, season_end):
    """One integer score: more points first, then earlier achievement. Exact in a double: < 2**43 <= 2**53."""
    remaining = season_end - achieved_at          # earlier achievement leaves more time remaining
    if not (0 <= points < 2**POINT_BITS and 0 <= remaining < 2**TIME_BITS):
        raise ValueError('out of the packed range')
    return points * 2**TIME_BITS + remaining

def unpack(packed, season_end):
    return packed // 2**TIME_BITS, season_end - packed % 2**TIME_BITS
```

A 90-day season is 7,776,000 seconds, below `2^23 = 8,388,608`; with 20 bits of points the largest packed value is
below `2^43`, ten bits inside the exact range. The check confirms that `pack` orders random pairs exactly as
"more points, then earlier time" and that `unpack` inverts it.

---

## 6. Deep Dive 2: The Sorted Set, Rank and Top-K

Redis implements a sorted set as a skip list plus a hash table: the hash table answers "what is this player's
score", the skip list keeps order. `ZADD`, `ZRANK` and `ZREVRANK` are `O(log N)`; `ZRANGE` is `O(log N + M)` for
`M` results. This model keeps the same two halves, with a sorted Python list standing in for the skip list (its
inserts are `O(N)`, which is fine for checking behaviour, not for production):

```python
import bisect, heapq, zlib

class Leaderboard:
    """One sorted set. order holds (-packed, player): index 0 is the best; equal packed scores go to the
    smaller player id. (In Redis, reverse order also reverses ties; either rule is fine if it is fixed.)"""
    def __init__(self):
        self.score = {}               # player -> packed score (the hash-table half)
        self.order = []               # sorted (-packed, player) (stands in for the skip list)

    def submit(self, player, packed):
        """Keep each player's best score, like ZADD GT. Returns True if the stored score changed."""
        old = self.score.get(player)
        if old is not None and packed <= old:
            return False
        if old is not None:
            self.order.pop(bisect.bisect_left(self.order, (-old, player)))
        self.score[player] = packed
        bisect.insort(self.order, (-packed, player))
        return True

    def better_than(self, packed, player):
        """How many entries rank strictly above (packed, player)."""
        return bisect.bisect_left(self.order, (-packed, player))

    def rank(self, player):
        """0-based rank from the top, like ZREVRANK."""
        return self.better_than(self.score[player], player)

    def top(self, k):
        return self.order[:k]

    def around(self, player, r):
        i = self.rank(player)
        return self.order[max(0, i - r): i + r + 1]
```

Now shard it by player. Top-K and rank behave very differently:

```python
class ShardedLeaderboard:
    """Players hash-partitioned across shards (like a key-hashed cluster)."""
    def __init__(self, n):
        self.shards = [Leaderboard() for _ in range(n)]

    def _shard(self, player):
        return self.shards[zlib.crc32(player.encode()) % len(self.shards)]

    def submit(self, player, packed):
        return self._shard(player).submit(player, packed)

    def top(self, k):
        """Exact: the global top k is inside the union of every shard's top k."""
        return heapq.nsmallest(k, (e for s in self.shards for e in s.top(k)))

    def rank(self, player):
        """Exact, but asks every shard how many entries beat this one."""
        packed = self._shard(player).score[player]
        return sum(s.better_than(packed, player) for s in self.shards)
```

`top(k)` needs `k` from each shard and a merge: cheap, and the result can be cached. `rank` needs a count from
**every** shard, which is the fan-out in the capacity table. In Redis terms each shard answers with `ZCOUNT` over
the scores above yours (plus ties ahead of you), so a rank costs one `O(log N)` call per shard.

A Redis Cluster note: keys map to one of 16,384 hash slots by `CRC16(key) mod 16384`, so a single sorted set lives
on one node; hash sharding a board means splitting it into several keys yourself. The cluster replicates
asynchronously, and its spec says there are windows in which acknowledged writes can be lost on failover. That is
why the durable score record lives elsewhere and the board can be rebuilt.

---

## 7. Deep Dive 3: Approximate Rank for Everyone Else

Players at rank 3,000,000 do not need an exact number; "top 6%" is the product. Keep a count of players per points
bucket in a Fenwick tree; the count of players in higher buckets is a lower bound on rank, and adding the player's
own bucket gives an upper bound.

```python
class PointsHistogram:
    """Players counted per points bucket; prefix sums with a Fenwick tree, O(log B) per update and query."""
    def __init__(self, max_points, bucket):
        self.bucket, self.n = bucket, max_points // bucket + 1
        self.tree = [0] * (self.n + 1)

    def _add(self, b, delta):
        b += 1
        while b <= self.n:
            self.tree[b] += delta
            b += b & -b

    def _prefix(self, b):
        """Players in buckets [0, b)."""
        s = 0
        while b > 0:
            s += self.tree[b]
            b -= b & -b
        return s

    def move(self, old_points, new_points):
        """A player's best moved (old_points None for a new player)."""
        if old_points is not None:
            self._add(old_points // self.bucket, -1)
        self._add(new_points // self.bucket, 1)

    def rank_bounds(self, points):
        """(lo, hi): the 0-based exact rank of a player with these points lies in [lo, hi]."""
        b = points // self.bucket
        total, upto = self._prefix(self.n), self._prefix(b + 1)
        lo = total - upto
        return lo, lo + (upto - self._prefix(b)) - 1
```

The histogram needs only one counter per bucket, so it can be sharded or replicated freely and even rebuilt from a
sample. The check confirms the exact rank always lies inside the bounds.

---

## 8. Failure Modes

| Failure | Effect | Mitigation |
|---|---|---|
| sorted-set primary fails before replicating | recent scores missing from the board | rebuild or replay from the durable score log; idempotent `ZADD GT` makes replays safe |
| score-range shards | the top tier's shard is the hottest at season end | hash shards for writes, or a separate small board for the top tier |
| rank read fan-out across shards | every rank read hits every shard | read replicas, cache ranks for a second, approximate rank below the top tier |
| float tiebreak collisions | equal doubles, unstable order | integer packing below 2^53 |
| cheating or replayed submissions | impossible scores | validate on the game server; never accept scores from clients directly |
| board key never expires | memory grows season after season | archive and delete old season keys |

---

## 9. What Real Systems Document

Redis's own documentation (read 2026-11-26) lists leaderboards for online games as a use case for sorted sets,
documents the skip-list-plus-hash-table implementation and the complexities above, the exact integer range of
scores, the `GT` option of `ZADD`, and the cluster's asynchronous replication. No game company's leaderboard
write-up was read for this revision, so none is described.

---

## 10. Pitfalls Checklist

1. **A heap for "my rank".** Heaps give the top, not order statistics.
2. **Fractional tiebreaks in a double.** Check the magnitude: at large scores the fraction disappears.
3. **Hash sharding and assuming rank got cheaper.** It got more expensive; count the fan-out.
4. **Score-range sharding without a plan for the hot top tier.**
5. **Treating Redis as the system of record** for scores that must not be lost.
6. **Letting clients submit scores.** Scores come from the game server.
7. **Exact rank for everyone** when a percentile would do.
8. **Forgetting `GT` semantics**, so a worse later match overwrites a player's best.

---

## Drills

1. Why does a sorted set answer rank in `O(log N)` but a heap cannot?
2. Show with numbers why `score + (1 - ts / 10^12)` fails at 1,000,000 points.
3. How many bits does a 120-day season need for `remaining`, and does the packed score still fit below `2^53` with 20 point bits?
4. Prove that `ShardedLeaderboard.top(k)` only needs `k` entries per shard.
5. Why does `rank` call `better_than` on every shard, and what does that cost with 8 shards at 50,000 rank reads/s?
6. In the capacity table, why does neither hash sharding nor read replicas alone fit at ten times the writes, and what does each of the two fixes reduce?
7. Given `rank_bounds` returns `(1200, 1450)`, what can you tell the player, and what made the interval wide?
8. The sorted-set primary failed. How do you rebuild the board, and why is that safe to repeat?

---

## Homework

1. Add `around()` to `ShardedLeaderboard` (players just above and below me) and check it against sorting.
2. Add a second board for "today" and design how it is created, expired and archived.
3. Replace the list in `Leaderboard` with a skip list that stores span counts for `O(log N)` rank; check it with the same tests.
4. Redo the capacity table for 500 million players and 100,000 submissions per second.
5. Read the Redis sorted-set page and the `ZADD` page end to end and list every option you would use here.

---

## Sources

All read 2026-11-26.

- Redis, *Redis sorted sets*, redis.io/docs/latest/develop/data-types/sorted-sets/. Source for ordering rules, the
  leaderboard use case, the skip list plus hash table, command complexities and `ZRANGE ... REV`.
- Redis, *ZADD*, redis.io/docs/latest/commands/zadd/. Source for double scores, `GT`/`LT`/`NX`/`XX`/`INCR`, the exact
  integer range up to 2^53, and byte-wise ordering of equal scores.
- Redis, *ZRANK*, redis.io/docs/latest/commands/zrank/. Source for 0-based rank and `ZREVRANK`.
- Redis, *Redis benchmark*, redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/. Source for
  why throughput figures depend on hardware and pipelining, and for Redis being mostly single-threaded in command execution.
- Redis, *Redis Cluster specification*, redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/. Source for
  16,384 hash slots, `CRC16(key) mod 16384`, asynchronous replication and the acknowledged-write loss windows.

## Further reading (not consulted)

Pugh, *Skip Lists: A Probabilistic Alternative to Balanced Trees* (1990); the Redis source (`t_zset.c`); cloud vendors'
leaderboard reference architectures. None were read for this revision.

*Last reviewed: 2026-11-26.*
