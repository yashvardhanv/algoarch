# Lesson 51 — Scaling Patterns I: Reads, Writes and Contention

> **Priority:** ★★★★★ — "it works for 1,000 users; what breaks at 100 million?" is answered by saying which of three different things is saturated, and each has a different cure.
>
> **Study time:** 70 minutes. **Do this after:** Replication & Sharding, and Caching Patterns and Consistent Hashing.
>
> **Level:** core.

Most scaling answers fail the same way: "add a cache", "shard it", "put a queue in front", offered before anyone has said what is overloaded. Reads, writes and contention are different problems. Reads scale by making copies, and the copies are stale. Writes scale by splitting and batching, and splitting makes reads harder. Contention is the odd one: the hardware is idle, but everyone wants the same row. This lesson builds one worked model for each, runs it, and ends with a table for choosing. The case studies later in the course (newsfeed, leaderboard, ticketing, counters in ad aggregation) are these patterns in costume. Every number below is produced by the code in this file.

---

## 1. Mental Model

> **Scaling is moving a bottleneck, so first name the saturated resource and whether the load is spread or concentrated. Reads are cured by copying (and the price is staleness). Writes are cured by splitting, batching or queueing (and the price is read fan-out, latency or delay). Contention is cured by changing what has to be serialised, because adding machines does not help a single hot item.**

What follows from it:

- **Spread versus concentrated is the first question.** A fleet at 30% average utilisation can still be down if one partition is at 400%. Averages hide the failing resource; per-partition and per-key numbers show it.
- **Every cure for one problem creates a cost in another.** Replicas make reads cheap and give stale reads. Sharding makes writes parallel and turns a range query into a scatter-gather. Batching makes writes cheap and adds delay. Counting the cost is the design.
- **Contention is not capacity.** If 5,000 clients increment one counter, a second machine does not help. The fixes are to shrink the critical section, split the item, combine updates before they reach it, or give the item a single owner.
- **Name the staleness you can tolerate per read type.** A balance, a like count and a profile photo are different answers, and the answer chooses the pattern.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "10 to 100 times more reads than writes" | copies: cache, then replicas; decide the staleness per read |
| "users must see their own post immediately" | read-your-writes: route by what the replica has applied, not by a guess at the lag |
| "write rate exceeds what one primary does" | shard by a key with many distinct values; batch; queue if bursty |
| "one celebrity / viral item / one tenant is slow" | hot key: split it into sub-keys; reads of that key now fan out |
| "everyone increments the same counter" | atomic increment, then sharded counters, then coalesce before writing |
| "two users buy the last item" | a conditional update or a single owner; see the flash-sale lesson for the full case |
| "retries make the database slower" | optimistic concurrency cost grows with the number of contenders; add backoff, split, or serialise |
| "traffic spikes for a minute, then returns to normal" | a queue, sized so that capacity is above the base load, or it never drains |

---

## 3. Reads: Copies and the Staleness They Carry

The ladder for a read-heavy system, cheapest change first:

| Step | What it multiplies | What it costs |
|---|---|---|
| make each read cheaper (index, query shape) | what one database does | nothing semantic; see the Postgres lessons |
| cache in front of the database | reads that never reach it | staleness and invalidation, see Caching Patterns |
| read replicas | the number of machines that can answer | replication lag |
| precomputed read models (a materialised feed, a summary row) | reads become key lookups | write amplification and lag; see the Newsfeed case study |
| a CDN or edge cache for content that is the same for everyone | reads at the edge | staleness until expiry or purge |

The step people get wrong is the third: replicas. A replica applies the primary's writes in order but some time later. For most reads that delay is invisible. For one read it is a bug: **the user who just wrote something and does not see it**. That is a read-your-writes violation, and fixing it is the routing problem below.

### Deep dive 1: routing reads so a session sees its own writes

The model: the primary commits each write at a time and gives it the next version number. A replica with a lag of `L` milliseconds has applied exactly the writes committed at least `L` ms ago, in order. A session remembers the version of its last write. Four policies decide where a read goes:

- **primary only**: always correct, no scaling.
- **any replica**: round robin; cheap, and sometimes stale for your own writes.
- **pin**: send the session's reads to the primary for a fixed window after its write; otherwise any replica.
- **token**: send the read to a replica that has applied at least the session's last write version; use the primary only if none has.

```python
import random
from bisect import bisect_right

def applied_version(commit_times, lag_ms, t):
    """Writes the replica has applied by time t: those whose commit time plus the replica's lag is <= t.
    commit_times is the sorted list of primary commit times; the write's version is its 1-based position."""
    return bisect_right(commit_times, t - lag_ms)

def make_workload(sessions=20, ops=40, write_share=0.25, span_ms=10_000, seed=7):
    """Each session does `ops` operations at random times; each is a write with probability `write_share`.
    Returns the sorted list of (time, session, kind) events."""
    rng = random.Random(seed)
    ev = []
    for s in range(sessions):
        for _ in range(ops):
            ev.append((rng.randrange(span_ms), s, 'w' if rng.random() < write_share else 'r'))
    ev.sort()
    return ev

def run_policy(events, lags, policy, window_ms=0):
    """Replay the events. policy: 'primary', 'any' (round robin over replicas), 'pin' (primary for `window_ms` after
    the session's own write, else round robin), 'token' (first replica that has applied the session's last write,
    else the primary). Returns (reads, read-your-writes violations, reads served by the primary)."""
    commits = [t for t, _, k in events if k == 'w']          # the primary commits a write when it arrives
    token, last_w = {}, {}
    version, rr = 0, 0
    reads = viol = on_primary = 0
    for t, s, k in events:
        if k == 'w':
            version += 1
            token[s], last_w[s] = version, t
            continue
        reads += 1
        want = token.get(s, 0)
        if policy == 'primary':
            got, via_primary = version, True
        else:
            r = rr % len(lags); rr += 1
            if policy == 'pin' and s in last_w and t - last_w[s] < window_ms:
                got, via_primary = version, True
            elif policy == 'token':
                got, via_primary = None, False
                for j in range(len(lags)):
                    c = (r + j) % len(lags)
                    if applied_version(commits, lags[c], t) >= want:
                        got = applied_version(commits, lags[c], t)
                        break
                if got is None:
                    got, via_primary = version, True
            else:
                got, via_primary = applied_version(commits, lags[r], t), False
        viol += got < want
        on_primary += via_primary
    return reads, viol, on_primary
```

Three replicas with lags of 10, 50 and 200 ms; 20 sessions making 800 operations in ten seconds, a quarter of them writes. 587 reads result, and this is what each policy does with them (a model with made-up lags, not a measurement of any database):

| Policy | Reads that missed the session's own write | Reads served by the primary |
|---|---|---|
| primary only | 0.00% | 100.00% |
| any replica | 7.84% | 0.00% |
| primary for 50 ms after a write | 4.60% | 4.77% |
| primary for 200 ms after a write | 0.00% | 19.42% |
| replica that has the write | 0.00% | 1.19% |

Reading the table is the lesson:

- **Any replica misses 46 of the 587 reads.** The slow replicas are the ones that miss, and a round robin sends two thirds of all reads to the replicas with lags of 50 and 200 ms.
- **A pin window is a guess about the worst lag.** At 50 ms it still leaks 4.60%, because the 200 ms replica is slower than the window. At 200 ms it is correct, and it costs 19.42% of reads going to the primary. The check confirms the window never adds violations as it widens, and that a zero window is plain round robin.
- **The token is the exact version of the same idea.** It asks the replica what it has applied instead of assuming a lag, so it is right when lag spikes, and it sends only 1.19% of reads to the primary here. The price is that the router must know each replica's applied position. How a given database exposes that position differs by product and was not consulted for this lesson.
- **A session stuck to one replica gets monotonic reads** (a later read is never older than an earlier one) because a replica applies writes in order. That follows from the model; it says nothing about a different session seeing your write.

Facebook's memcache paper (NSDI 2013, read in part) solves the same problem for a cache fed from replicated databases. A web server that writes first sets a *remote marker* for the key in its own region, writes to the master region's database, and deletes the key locally. A later read finds no cached value, sees the marker, and goes to the master region instead of the possibly lagging local replica. The paper says directly that this trades extra latency on that miss for a smaller chance of reading stale data, and that a concurrent modification of the same key can delete a marker another operation still needs. It is the pin policy applied per key, with the marker's presence as the window.

Visual (planned): a timeline with three replicas applying a write at different times, and a read for each policy landing on a replica that has or has not applied it.

---

## 4. Writes: Batching, Queues and Splitting

### Batching: pay the fixed cost once

Every write request has a fixed part (a network round trip, a log append, a commit) and a per-record part. When the fixed part dominates, sending records together divides it. Kafka's producer is the standard example. Its 4.1 documentation (read 2026-11-26) describes `batch.size` (default 16,384 bytes, an upper bound per partition) and `linger.ms`, the time to wait for more records before sending a partly full batch. The default of `linger.ms` is 5, changed from 0 in Kafka 4.0 on the stated reasoning that larger batches typically give similar or lower latency despite the wait; the page compares it to Nagle's algorithm. The design page calls batching one of the big drivers of Kafka's efficiency.

A model of that trade. Records arrive evenly spaced; a batch opens at its first record and is sent when it is full or when it has waited `linger_ms`.

```python
from math import ceil

def batch_shape(gap_ms, batch_records, linger_ms):
    """Evenly spaced arrivals every `gap_ms`. A batch opens at its first record and is sent when it holds
    `batch_records` records or when `linger_ms` has passed since it opened, whichever comes first (a record arriving
    exactly at the deadline opens the next batch). Returns (records per batch, mean added delay in ms)."""
    if linger_ms <= 0:
        return 1, 0.0
    n = min(batch_records, ceil(linger_ms / gap_ms))
    send_at = (n - 1) * gap_ms if n == batch_records else linger_ms
    return n, send_at - (n - 1) * gap_ms / 2           # records arrive at 0, gap, ..., (n-1)*gap

def cost_per_second(rate, n, fixed_us, per_record_us):
    """Broker-side microseconds spent per second: one `fixed_us` per request plus `per_record_us` per record."""
    return rate / n * fixed_us + rate * per_record_us
```

Take 1,000 records per second of 1 KiB each (so a full batch is 16 records) and an **illustrative** cost of 200 microseconds per request plus 5 per record; these costs are made up to show the shape, not a measurement of Kafka or anything else:

| Linger (ms) | Records per request | Requests per second | Mean added delay (ms) | Broker CPU (ms per second) |
|---|---|---|---|---|
| 0 | 1 | 1000 | 0 | 205 |
| 2 | 2 | 500 | 1.5 | 105 |
| 5 | 5 | 200 | 3 | 45 |
| 10 | 10 | 100 | 5.5 | 25 |
| 50 | 16 | 62 | 7.5 | 17.5 |

- **The first few milliseconds buy almost all of it.** A 5 ms linger cuts the modelled CPU from 205 to 45 ms per second for a mean added delay of 3 ms. Going from 5 to 50 ms adds delay and saves little more, because the batch fills at 16 records.
- **The delay is paid by every record, but not equally.** The first record in a batch waits the whole linger; the last waits none. A latency-sensitive path that cannot afford the wait sets linger to zero and accepts the cost.
- **A buffered record is not durable.** Records sitting in a batch are lost if the process dies before the send. Whether that is acceptable is a requirement for the use case, not a tuning detail.
- **Real producers also batch under load without waiting.** The Kafka page says batching normally happens when records arrive faster than requests can be sent; linger adds artificial delay to batch at lower load. The model shows only the waiting part.

### A queue absorbs a burst only if capacity exceeds the base load

A queue between producers and a consumer trades delay for smoothness. The arithmetic is short and decides whether the queue helps or merely delays a collapse:

```python
def burst_backlog(base, burst, burst_s, capacity):
    """A queue in front of a consumer that serves `capacity` per second. Load is `base` per second, except for
    `burst_s` seconds at `burst`. Returns (peak backlog, seconds after the burst until the queue is empty,
    wait in seconds of the last item queued at the peak); None for the last two if the queue never drains."""
    peak = max(0, (burst - capacity) * burst_s)
    if capacity <= base:
        return peak, None, None
    return peak, peak / (capacity - base), peak / capacity

def coalesced_write_rate(servers, flush_interval_s):
    """Writes per second reaching a hot row when each server adds up its increments and flushes once per interval."""
    return servers / flush_interval_s
```

Base load 2,000 per second, a burst of 10,000 per second for 30 seconds, a consumer that serves 4,000: the backlog peaks at 180,000 items, drains in 90 s after the burst, and the last item queued at the peak waits 45 s. The consumer's spare capacity (4,000 minus 2,000) is the only thing that drains it, which is why it takes three times as long as the burst. If the consumer serves only 2,000, the backlog is 240,000 and never drains. The check compares the formula with a second-by-second simulation. A queue that does not drain is the overload loop of the next-door lesson on load shedding, so a queue needs a bound and a drop or shed rule as well.

### Splitting writes across partitions, and the hot key that defeats it

Hash-sharding by key spreads load only if the load is spread across keys. Real key popularity is skewed. This experiment uses a Zipf law (key `i` has weight `1/i`, a common model of skew, chosen here for illustration) over 100,000 keys and 50,000 writes per second, placed on 128 partitions by a stable hash. The hottest key alone is 4,136 writes per second.

```python
import hashlib
from math import ceil

def zipf_rates(keys, total_rate, s=1.0):
    """Expected writes/s for each key when popularity follows a Zipf law: key i (1-based) gets weight 1 / i**s."""
    w = [1.0 / (i ** s) for i in range(1, keys + 1)]
    z = sum(w)
    return [total_rate * x / z for x in w]

def place(name, partitions):
    """A stable hash placement (md5, so the result does not change between runs)."""
    return int.from_bytes(hashlib.md5(name.encode()).digest()[:8], 'big') % partitions

def partition_loads(rates, partitions, split=None):
    """Writes/s landing on each partition. `split` maps a key index to the number of sub-keys it is split into
    (writes go to key#0 .. key#n-1 with equal probability); unsplit keys are placed by their own name."""
    load = [0.0] * partitions
    for i, r in enumerate(rates):
        n = (split or {}).get(i, 1)
        for j in range(n):
            name = 'key%d' % i if n == 1 else 'key%d#%d' % (i, j)
            load[place(name, partitions)] += r / n
    return load

def splits_needed(key_rate, limit):
    """Sub-keys needed so that no sub-key is above `limit` writes/s."""
    return max(1, ceil(key_rate / limit))

def split_plan(rates, limit):
    """Split every key that alone exceeds `limit` writes/s into the number of sub-keys that brings it under."""
    return {i: splits_needed(r, limit) for i, r in enumerate(rates) if r > limit}

def hottest_over_mean(load):
    return max(load) / (sum(load) / len(load))
```

The mean is 391 writes per second per partition. Suppose a partition tops out at 1,000. Each row splits the keys above a threshold into sub-keys that bring each piece under it, then reports the busiest partition:

| Split keys | Keys split | Sub-keys created | Busiest partition (writes/s) | Busiest over mean | Partitions over 1,000 |
|---|---|---|---|---|---|
| no split | 0 | 0 | 4349 | 11.13 | 6 |
| above 1000/s | 4 | 12 | 1206 | 3.09 | 8 |
| above 500/s | 8 | 28 | 1257 | 3.22 | 1 |
| above 250/s | 16 | 66 | 962 | 2.46 | 0 |
| above 125/s | 33 | 156 | 814 | 2.08 | 0 |

- **Without splitting, the hottest partition carries 11 times the mean.** Adding partitions would not help the hottest key: it hashes to one of them, and `4,136 / 1,000` shows it needs five pieces just to fit.
- **Splitting only to the limit is not enough.** Row two splits to pieces under 1,000, the busiest partition drops from 4,349 to 1,206, and the number of partitions over the limit goes from 6 up to 8. A piece of 827 writes per second landing next to the ordinary load of 391 exceeds 1,000. The limit applies to a partition, not to a key, so the threshold has to leave room for the keys that share it. Here a quarter of the limit works.
- **The cost moved to reads.** A key split 34 ways (key 0 at the 125 threshold) is 34 lookups to read it back, and the sub-keys must be merged. Only split the keys that need it, and keep the list of split keys small enough to look up on every request.
- **Load is conserved.** Splitting moves writes around; the check asserts the total never changes and that every piece is under its threshold.

The DynamoDB documentation (read 2026-11-26) gives the same technique and its cost. A partition is designed for at most 1,000 write units and 3,000 read units per second; a write unit is one write of up to 1 KB, a read unit one strongly consistent read of up to 4 KB (or two eventually consistent ones). Its "write sharding" page adds a random suffix (its example is 1 to 200 on a date key) to spread writes, and says reading everything for the date means one query per suffix and merging the results. It also describes a *calculated* suffix (a hash of an order id) that spreads writes and still lets you find a single item. The item size matters: a 3 KB item costs 3 write units, so one partition takes at most 333 such writes per second, and a 20 KB item costs 5 read units, so 600 strongly consistent reads per second on one item. The helpers below reproduce those figures:

```python
def write_units(item_kb):
    """DynamoDB write units one write of an item consumes: one per KB, rounded up."""
    return ceil(item_kb)

def read_units(item_kb, consistent=True):
    """DynamoDB read units one read consumes: one per 4 KB, rounded up, for a strongly consistent read;
    half that for an eventually consistent one."""
    units = ceil(item_kb / 4)
    return units if consistent else units / 2

def max_item_rate(unit_limit, units_per_op):
    """Operations per second a single partition sustains at `unit_limit` units per second."""
    return unit_limit // units_per_op
```

This models the arithmetic of a store where you place keys yourself. DynamoDB places and splits partitions itself, so do not read the table above as a prediction of its behaviour.

Visual (planned): a bar chart of load per partition for the five rows, with the 1,000 line, and the hot key's pieces coloured.

---

## 5. Contention: When the Hardware Is Idle and Everyone Waits

### Why read-modify-write loses updates

Two clients each read a counter, add one and write it back. If their steps interleave, an update vanishes. The code below enumerates every interleaving of `n` clients that each do `read` then `write`:

```python
from collections import Counter
from itertools import permutations

def rmw_outcomes(clients):
    """Every interleaving of `clients` clients that each do: read the counter, then write (value read + 1).
    Returns a Counter {final counter value: number of interleavings}."""
    steps = [(c, op) for c in range(clients) for op in ('read', 'write')]
    seen, out = set(), Counter()
    for order in permutations(steps):
        if order in seen:
            continue
        seen.add(order)
        if any(order.index((c, 'read')) > order.index((c, 'write')) for c in range(clients)):
            continue                                     # a client must read before it writes
        value, held = 0, {}
        for c, op in order:
            if op == 'read':
                held[c] = value
            else:
                value = held[c] + 1
        out[value] += 1
    return out
```

For two clients there are six valid interleavings, and **4 of the 6 end with the counter at 1 instead of 2**. For three clients there are 90: 6 end at 3, 36 at 2 and 48 at 1. Only the orders that behave like running the clients one after another reach the right answer (the check confirms the count of right answers is `n!` for up to four clients). The fix is never "hope the interleaving is lucky". It is to make the read and the write one step, or to detect the conflict.

### The ladder of cures

1. **One atomic step.** `UPDATE t SET n = n + 1 WHERE id = 7` instead of read then write. In PostgreSQL's default Read Committed level, an UPDATE that finds its row already updated by an in-progress transaction waits for it, then re-evaluates its `WHERE` clause against the updated row version and proceeds (read 2026-11-26). So concurrent increments and conditional decrements such as `WHERE stock >= 1` are safe without an explicit lock. Redis's counter pattern is the same idea: `INCR` is an atomic increment. The same Redis page shows how a two-command rate limiter races between `INCR` and `EXPIRE`, and fixes it with `MULTI`/`EXEC` or a Lua script: put the steps that must not interleave into one atomic unit.
2. **Detect and retry.** Add a version column; write only if the version still matches; on a mismatch, re-read and retry. PostgreSQL's higher isolation levels do the same thing at transaction scale, and say applications must be ready to retry the whole transaction on a serialization failure. The cost is the next table.
3. **Split the item.** Keep `S` counters and add up their values on read.
4. **Combine before writing.** Each application server adds up its increments in memory and writes the total once per interval.
5. **A single owner per key.** Route every write for a key to one worker (a queue partitioned by the key), so the serialisation happens in one place, with a queue in front instead of a lock.
6. **Change the model.** Insert an event row per action (inserts to different rows do not contend) and aggregate later, instead of updating one shared row.

### What retrying costs

Optimistic concurrency has no waiting, but it has waste. Suppose `n` clients all want to apply an update to the same row, and each round every one of them reads the current version and tries to write. Exactly one write per row succeeds; the rest see a mismatch and retry:

```python
def optimistic_attempts(clients, shards=1):
    """Clients hold a version-checked read-modify-write on a counter. Each round every client with work left reads
    the current version of its shard and tries to write; per shard exactly one write in a round succeeds, the others
    see a version mismatch and retry next round. Clients are dealt to shards round-robin.
    Returns (rounds until all are done, total write attempts)."""
    left = [[c for c in range(clients) if c % shards == s] for s in range(shards)]
    rounds = attempts = 0
    while any(left):
        rounds += 1
        for q in left:
            if q:
                attempts += len(q)
                q.pop(0)                                 # one attempt wins, the rest retry
    return rounds, attempts

def shards_needed(write_rate, per_shard_rate):
    """Shards that keep every shard at or under `per_shard_rate` writes per second."""
    return -(-write_rate // per_shard_rate)
```

| Contenders | Shards | Rounds | Write attempts |
|---|---|---|---|
| 10 | 1 | 10 | 55 |
| 10 | 2 | 5 | 30 |
| 10 | 5 | 2 | 15 |
| 100 | 1 | 100 | 5050 |
| 100 | 10 | 10 | 550 |

- **One row costs `n(n+1)/2` attempts for `n` updates.** 100 contenders make 5,050 write attempts to apply 100 updates, and it takes 100 rounds because one wins per round. The check compares the simulation with that closed form for every case up to 39 clients.
- **Splitting divides the waste by roughly the number of shards.** Ten shards for 100 clients: 550 attempts, 10 rounds. The waste is a sum of squares, so it falls faster than the throughput rises.
- **Backoff with jitter thins the herd** (see the Resilience lesson) but does not change the shape: one row still commits one write at a time.
- **Pessimistic locking is the same ceiling with waiting instead of waste.** A row lock serialises the holders; throughput is one over the hold time. That is why the cure on the hot row is to hold it for less time, as in step 1.

### A worked fix: counting likes

A post gets 5,000 likes per second, and the count lives in a document database where one document is designed to take about one write per second. The Firestore "distributed counters" page (read 2026-11-26) says a single document cannot be updated at an unlimited rate and shows the fix: a counter document with a subcollection of shards, the counter's value being the sum of the shards, throughput rising with the number of shards. Its sample code's comment says each shard can support being incremented once per second, so 5,000 shards are needed for 5,000 increments per second: `shards_needed(5000, 1)`. The same page lists the costs: too few shards means retries, too many means reads load every shard (cost linear in the shard count), and it suggests a separate roll-up document updated at a slower cadence for reads.

Coalescing attacks the number the shard count comes from. If 50 application servers each add up their likes and flush once a second, the hot row sees `coalesced_write_rate(50, 1)` = 50 writes per second, so 50 shards are enough, and reads of the count load 50 documents instead of 5,000. The price is the one in section 4: up to a second of increments is lost if a server dies, and the displayed count lags by up to the flush interval. For a like count that is the right trade; for a balance it is not, and a balance takes the single-owner or conditional-update route instead (see the flash-sale lesson).

---

## 6. Choosing and Measuring

| Symptom | Measure first | Pattern |
|---|---|---|
| database CPU high, mostly reads | read:write ratio, hit rate, query shapes | cheaper queries, then cache, then replicas |
| "I posted and it is gone" | rate of reads that miss the session's own write; replica lag | route by applied version, or pin |
| write latency rises, CPU of one shard saturated | per-partition and per-key write rates | split the hot keys; reshard |
| write latency rises on all shards | requests per second versus records per request | batch |
| periodic spikes, then recovery | queue depth and its drain time | a bounded queue sized above base load |
| lock waits or retries climb with traffic | wait time per hot row; retry rate | atomic step, shorter hold, shard or coalesce the row |
| one row fine alone, collapses in a burst | attempts per success | the `n(n+1)/2` curve: split or serialise |

Two habits make the table usable. Look at the **top-k keys and per-partition numbers**, not the average. And choose the staleness before the mechanism: the question to ask is how old a value may be and for whom, and the answer decides whether a cache, a replica, a token, or the primary is acceptable.

---

## 7. Failure Modes

| Failure | Effect | Mitigation |
|---|---|---|
| replica read after own write | the user's change appears lost | route by applied version, or pin past the worst lag |
| pin window shorter than a lag spike | intermittent lost-write reports | version token instead of a window |
| hot key on a hash shard | one partition throttles while others idle | split the key; cache for read-hot keys |
| splitting only down to the limit | the pieces overload their neighbours | split to a fraction of the limit, then measure |
| split key read without merging sub-keys | missing data in reads | one code path that reads all sub-keys |
| batching without a durability decision | lost records on a crash | decide per record class; flush on shutdown; acknowledge after the batch is stored |
| a queue that does not drain | unbounded delay, then overload | capacity above base load; bounds and shedding |
| optimistic retry storms | wasted writes grow with contenders | backoff with jitter; shard or serialise the hot row |
| read-modify-write across two statements | lost updates | single atomic statement, or a version check |
| too many counter shards | slow, costly reads | coalesce first, keep a roll-up for reads |

---

## 8. What Real Systems Document

All read 2026-11-26. The Kafka 4.1 documentation states the producer's batching defaults and the reasoning for the `linger.ms` change. The DynamoDB developer guide states the per-partition limits, the item-size arithmetic and two write-sharding schemes with their read costs. Firestore's distributed-counters page states the sharded counter and its shard-count and read-cost trade-offs. PostgreSQL's documentation states how Read Committed re-evaluates a concurrent UPDATE and how higher isolation levels expect retries. Redis's INCR page states the atomic counter pattern and the race in the naive rate limiter. Facebook's memcache paper (read in part) states the remote-marker mechanism for read-your-writes across replica regions. None of these gives you an interview number to quote for scale; each gives a mechanism and its stated cost.

---

## 9. Pitfalls Checklist

1. **Answering "add a cache" without saying whether it is read-hot or write-hot.** A cache does nothing for a write bottleneck.
2. **Reading from a replica right after a write with no policy.** Pick pin, token or primary, and say which.
3. **A pin window chosen without knowing the worst lag.** It leaks every time the lag spikes.
4. **Quoting average utilisation.** One partition at 400% is an outage at 30% average.
5. **Splitting a hot key to exactly the partition limit.** The pieces land on busy neighbours; leave headroom.
6. **Splitting without paying for the read.** Every split key becomes a scatter-gather read.
7. **Batching by default with no thought for the delay or the loss window.** Both are part of the requirement.
8. **A queue sized for the burst but not for the drain.** If capacity is not above base load it never empties.
9. **Read-modify-write in application code.** Four of six interleavings of two clients lose an update.
10. **Treating retries as free.** A thousand contenders on one row make half a million attempts for a thousand updates.

---

## Drills

1. A replica lags the primary by 80 ms, and your policy sends a session to the primary for 50 ms after it writes. Describe the failure, and say what changes with a version token.
2. In the routing table, why does "primary for 200 ms after a write" send 19.42% of reads to the primary while the token policy sends 1.19%, and what does the token policy need from the replicas that the pin policy does not?
3. With a 1 KiB record, a 16 KiB batch and 1,000 records per second, what does a 5 ms linger do to requests per second and mean added delay, and what would raise the delay without lowering the request rate?
4. A consumer serves 4,000 per second, base load is 3,500, and a burst of 9,000 per second lasts 20 seconds. How large is the backlog and how long does it take to drain?
5. A key receives 4,136 writes per second and a partition takes 1,000. How many pieces does it need at minimum, why is that not the right number to deploy, and what does the table suggest instead?
6. List the six interleavings of two read-then-write clients on a counter and say which end at 2.
7. 100 clients retry a version-checked update on one row. How many write attempts are made, how many rounds does it take, and how do both change with ten shards?
8. A like counter gets 5,000 increments per second from 50 servers. Compare sharding to 5,000 documents with coalescing before writing: write rate, shards, read cost, and what you give up.

---

## Homework

1. Run `run_policy` with replica lags of 10, 50 and 400 ms. Find the smallest pin window that gives zero violations and compare its primary share with the token policy's.
2. Add a fourth policy to `run_policy`: pin the session to one replica for its lifetime. Measure violations and say whether monotonic reads hold.
3. Extend `batch_shape` to poisson arrivals with a seeded generator and compare the mean batch size with the evenly spaced case at the same average rate.
4. Add a hot-key detector to the Zipf experiment: given only a stream of key names, find the keys above a threshold using a count-min sketch or a space-saving counter, then feed the result to `split_plan`.
5. Add exponential backoff with jitter to `optimistic_attempts` and measure total attempts for 100 contenders on one row.
6. Write the SQL for the conditional decrement `UPDATE stock SET n = n - 1 WHERE id = ? AND n >= 1` and run it from ten concurrent sessions against a local PostgreSQL; count oversells. Then repeat with read-then-write in the application.
7. Read the DynamoDB "write sharding" page end to end and design the key for a table of per-day events with 5,000 writes per second, covering the suffix scheme and the read path.

---

## Sources

All read 2026-11-26.

- Apache Kafka 4.1 documentation, producer configurations, kafka.apache.org/41/generated/producer_config.html. Read the entries for `batch.size`, `linger.ms` and `delivery.timeout.ms`; the other entries were not read. Source for the default values and the stated reason for changing the `linger.ms` default.
- Apache Kafka 4.1 documentation, design, kafka.apache.org/41/design/design/. Read in part (the efficiency section on batching and compression). The rest was not read.
- Amazon DynamoDB Developer Guide, *Best practices for designing and using partition keys effectively*, *Designing partition keys to distribute your workload* and *Using write sharding to distribute workloads evenly*, docs.aws.amazon.com. Read in full. Source for the per-partition limits, the unit definitions, the 20 KB example and both sharding schemes.
- Firebase documentation, *Distributed counters* (Cloud Firestore), firebase.google.com/docs/firestore/solutions/counters. Read the problem statement, the data model, the sample comments and the limitations section; the code samples in other languages were skimmed, not read.
- PostgreSQL documentation, *Transaction Isolation* (the Read Committed, Repeatable Read and Serializable sections), postgresql.org/docs/current/transaction-iso.html. Read the Read Committed section and the retry statements for the two higher levels; the rest of the page was not read. Also *Explicit Locking* (the row-level locks section), read in part.
- Redis documentation, `INCR`, redis.io/docs/latest/commands/incr/. Read the counter and rate-limiter patterns.
- Nishtala et al., *Scaling Memcache at Facebook* (NSDI 2013), usenix.org/system/files/conference/nsdi13/nsdi13-final170_update.pdf. Read in part: section 3.2.1 on leases and the remote-marker passage in the multi-region discussion. The rest of the paper was not read for this lesson.

## Further reading (not consulted)

The Hello Interview scaling-patterns pages (reads, writes, contention) that the course outline cites; only their free introductions were visible and they were not used. Database documentation on replication positions and synchronous replication for each product; the Google Spanner and Aurora papers; Facebook's TAO paper; counting with CRDTs. None of these was read for this lesson, and the models here are this lesson's own.

*Last reviewed: 2026-11-26.*
