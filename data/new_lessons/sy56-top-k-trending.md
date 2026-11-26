# Lesson 56 — Case Study: Top-K and Trending (YouTube top videos, hashtags)

> **Priority:** ★★★★☆ — a very common prompt, and one where a precise statement of what you give up (exactness) and what you keep (a guarantee) separates strong answers from "use Redis".
>
> **Study time:** 70 minutes. **Do this after:** Real-Time Gaming Leaderboard (sy39), Ad-Click Aggregator & Stream Processing (sy27), and Scaling Patterns I (sy51).
>
> **Level:** core.

"Show the ten most viewed videos of the last hour" and "show the hashtags that are trending right now" are the same
problem: count events per key in a stream, keep the largest, and answer for a sliding window. With a million keys a hash
map and a heap solve it. With a billion keys and a million events a second, memory and hot keys decide the design. This
lesson builds exact counting, a count-min sketch, the Space-Saving algorithm, sliding windows with provable bounds,
the shard-merge trap and a trend score; all are checked against exact counting in
`test/lesson_code/sy56_check.py`, and all capacity numbers in `test/lesson_code/capacity_check_c.py`. Where exact
ranking over a modest key set is enough, sy39's sorted sets are the answer; this lesson starts where they stop fitting.

---

## 1. Mental Model

> **Top-K is a counting problem under a memory budget. Exact counting needs one counter per distinct key. A sketch uses
> far less memory by giving you counts that can only be too high, by a bound you can compute. Everything else (windows,
> shards, trending) is how you cut the stream, not how you count.**

What follows from it:

- **Ask for the error you can tolerate before choosing the structure.** Top-10 on a home page tolerates a swap between
  ranks 9 and 10; a billing counter tolerates nothing.
- **One-sided errors are useful.** A count-min sketch never undercounts; Space-Saving's count minus its recorded error
  never overcounts. Either gives you a bound, not just a hope.
- **The skew of the data is the reason this works.** If counts were uniform, no summary smaller than the key set could
  find the top ten. Real view counts are heavy-tailed, so the top is far above the noise.
- **Windows are a separate decision.** Cut time into buckets, summarise each bucket, and combine summaries.
- **"Trending" is not "most".** Most is a count; trending is a count relative to what was normal for that key.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "top K videos / products / queries" | exact if the key set fits in memory; else Space-Saving or count-min plus a heap of candidates |
| "in the last hour / day" | per-minute buckets, drop the oldest, combine; not a fresh count on every query |
| "trending" | compare the recent window with the key's own history, with smoothing, plus a minimum volume |
| "billions of keys, memory is the limit" | sketch with a known error, sized from epsilon and delta |
| "many ingest servers" | partition by key so each key has one owner; or merge sketches by adding them |
| "one key gets a huge share" | pre-aggregate at the edge for a second before the shared counter; sy51 hot-key splitting |
| "must be exact" | a log plus a batch job for the truth; the sketch is the fast, approximate view |
| "ranks must be right" | say how big a count gap you can resolve, and report error bars |

---

## 3. Requirements and Capacity

**Functional.** Ingest view events; answer `top(k, window, filter)` for windows such as 1 hour and 24 hours, by
category and region; show trending items; refresh within about a minute. **Out of scope:** bot and fraud filtering,
personalisation, the exact all-time view count shown on a video page (a different, exact counter).

**Non-functional.** Query latency in milliseconds (answers are precomputed). Bounded memory. A stated, tested error.
Survives a node restart by rebuilding from the event log.

**Capacity estimate.** Inputs are **assumptions** (they are not any company's figures); every result is reproduced by
`test/lesson_code/capacity_check_c.py`.

| Input (assumed) | Value |
|---|---|
| view events | 5 billion per day |
| peak to average | 3 |
| distinct videos | 1 billion |
| window | 1 hour, as 60 one-minute buckets |
| exact counter | 8-byte id + 8-byte count |
| sketch cell | 4 bytes |
| target error epsilon, failure probability delta | 0.0001, 0.01 |
| Space-Saving counters per bucket | 10,000 (1/epsilon), 24 bytes each |
| popularity shape | Zipf with exponent 1 (illustrative) |

| Result | Arithmetic | Value |
|---|---|---|
| average rate | 5 billion / 86,400 | 57,870 views per second |
| peak rate | x 3 | 173,611 views per second |
| views in the window | 5 billion / 24 | 208,333,333 views |
| exact counters, one hour (ceiling) | min(1 billion keys, 208,333,333 views) x 16 B | 3.3 GB |
| exact counters, one minute bucket (ceiling) | min(1 billion keys, 3,472,222 views) x 16 B | 55.6 MB |
| exact, 60 minute buckets (ceiling) | x 60 | 3.3 GB |
| sketch width, depth | ceil(e / 0.0001), ceil(ln 100) | 27,183 by 5 = 135,915 cells |
| one sketch | 135,915 x 4 B | 544 KB |
| 60 sketches | x 60 | 32.6 MB |
| absolute error bound | 0.0001 x 208,333,333 | 20,833 views |
| Space-Saving, one bucket | 10,000 counters x 24 B | 240 KB |
| Space-Saving, 60 buckets | x 60 | 14.4 MB |
| harmonic number, 1 billion keys | ln(10⁹) + 0.5772 | H = 21.3 |
| views of rank 10 | 208,333,333 / (10 x 21.3) | about 978,000 views |
| views of rank 100 | 208,333,333 / (100 x 21.3) | about 97,800 views |
| views of rank 1,000 | 208,333,333 / (1,000 x 21.3) | about 9,780 views |
| last rank whose count is above the error bound | 1 / (0.0001 x 21.3) | rank 469 |
| gap between ranks 100 and 101 | 208,333,333 / (21.3 x 100 x 101) | about 968 views |
| last rank that can be ordered from its neighbour | largest r with r(r+1) below 469.5 | rank 21 |
| share of the top key | 1 / 21.3 | 4.7%, which is 8,150 views per second at the peak rate |
| candidates to rank in a query | 60 buckets x 10,000 | 600,000 candidates |

Four conclusions. **Exact counting is cheaper than it first looks, and the sketch still wins on bounds.** A window cannot
hold more distinct keys than events: at most 3.3 GB for the hour and 55.6 MB for a minute bucket, never the 16 GB a
billion-key table would suggest (real Zipf traffic has far fewer distinct keys than events, so these are ceilings). The
summaries (14.4 MB to 32.6 MB) are about 100 to 230 times smaller than that ceiling, not thousands of times. The honest
argument for a sketch is that its size is fixed in advance whatever the key cardinality, that it merges across servers,
and that the saving multiplies once you keep one per region, category and window. **The error is absolute, not relative:**
20,833 views either way. A key is *detectable* (its count is above the bound) up to about rank 469, but two *adjacent*
ranks can be put in the right order only while their gap exceeds the error, which here ends at rank 21: ranks 100 and
101 differ by about 968 views, so positions 22 and below can come out in any order. Promise "the top 20, ordered, and
the next few hundred as a set". The shape assumption matters: a flatter distribution shrinks both numbers. **The hot
key is the first bottleneck:** the top key alone draws 8,150 views per second, so pre-aggregate before touching a
shared counter. **Answering a query is cheap:** 600,000 candidates is a sort, and the top-K list can be materialised
every minute anyway.

Visual (planned): events into a partitioned log; per-partition aggregators filling one-minute buckets; a merger combining the last 60 buckets into the top-K list that the API serves from a cache.

---

## 4. API and Data Model

```
POST /view            {video_id, ts, region}               (batched; goes to a log, not a database)
GET  /top?k=10&window=1h&region=IN                          -> [{video_id, estimate, lower_bound}]
GET  /trending?k=10&window=15m
bucket summary: {partition, minute, sketch cells or counters, total events}      (small, written once per minute)
top-K list:     {window, region, computed_at, items[]}                            (cached, refreshed each minute)
```

The write path never updates a global counter per view. Events go to a partitioned log (sy36); each aggregator owns a
set of partitions, folds events into the current minute's summary in memory, and flushes it when the minute closes.
A merger reads the last 60 summaries and publishes the top-K list. Recovery is replay: a restarted aggregator re-reads
its partitions from the last flushed minute, as in sy44's journal-and-replay.

---

## 5. Deep Dive 1: Counting Under a Memory Budget

**Exact** is a hash map and a sort. It is the reference every other structure here is tested against.

**Count-min sketch** (Cormode and Muthukrishnan). A table of `depth` rows by `width` columns of counters and one hash
function per row. To add an item, increment one cell in every row; to estimate, take the minimum over the item's cells.
Collisions only add, so the estimate is never below the true count. With `width = ceil(e / epsilon)` and
`depth = ceil(ln(1 / delta))`, the paper proves that with probability at least `1 - delta` the estimate is at most the
true count plus `epsilon` times the total count `N` (the sum of all updates). Space and update time do not depend on the
number of distinct keys. To find heavy items you add a small candidate set: after each update, estimate the item and keep
it if it beats the current smallest candidate. The paper's heavy-hitter result for streams of insertions uses the same
idea with a threshold, and every item above the threshold is reported.

```python
import heapq, math, random, hashlib, collections

def exact_topk(items, k):
    c = collections.Counter(items)
    return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:k]       # ties broken by key, so results are comparable

P = (1 << 61) - 1

def _fp(item):
    return int.from_bytes(hashlib.sha256(str(item).encode()).digest()[:8], 'big')

class CountMin:
    def __init__(self, eps, delta, seed=0):
        self.eps, self.delta, self.seed = eps, delta, seed
        self.width, self.depth = math.ceil(math.e / eps), math.ceil(math.log(1 / delta))
        r = random.Random(seed)
        self.ab = [(r.randrange(1, P), r.randrange(P)) for _ in range(self.depth)]   # one (a, b) per row: ((a x + b) mod P) mod width
        self.table = [[0] * self.width for _ in range(self.depth)]

    def _cells(self, item):
        x = _fp(item)
        return [(row, ((a * x + b) % P) % self.width) for row, (a, b) in enumerate(self.ab)]

    def add(self, item, c=1):
        for row, col in self._cells(item):
            self.table[row][col] += c

    def estimate(self, item):
        return min(self.table[row][col] for row, col in self._cells(item))

    def merge(self, other):                      # same shape and same hash functions: the sketch of the union is the sum
        if (self.width, self.depth, self.seed) != (other.width, other.depth, other.seed):
            raise ValueError('sketches must share shape and seed')
        out = CountMin(self.eps, self.delta, self.seed)
        out.table = [[x + y for x, y in zip(r1, r2)] for r1, r2 in zip(self.table, other.table)]
        return out

class CMSTopK:
    def __init__(self, k, eps, delta, seed=0):
        self.k, self.cm, self.cand = k, CountMin(eps, delta, seed), {}

    def add(self, item):
        self.cm.add(item)
        est = self.cm.estimate(item)
        if item in self.cand or len(self.cand) < self.k:
            self.cand[item] = est
        else:
            low = min(self.cand, key=lambda e: (self.cand[e], e))      # O(k); a heap in production
            if est > self.cand[low]:
                del self.cand[low]
                self.cand[item] = est

    def top(self):
        return sorted(self.cand.items(), key=lambda kv: (-kv[1], kv[0]))
```

The check asserts the formulas for width and depth, that **no estimate is ever below the truth** (12 seeded Zipf streams,
every key plus 50 never-seen keys), that the fraction of estimates exceeding the true count plus `epsilon * N` is at most
`delta`, and that a deliberately narrow sketch visibly overestimates. It also asserts **merge linearity**: adding two
sketches' tables cell by cell equals the sketch of the combined stream, which is why sketches combine across servers;
and that sketches built with different hash seeds refuse to merge, because their cells mean different things. For
`CMSTopK` on 10 Zipf streams, estimates are never below the truth and at least 90% of the true top 10 are recovered.
That is a measured recall on this data, not a guarantee: items near the cut line can swap.

**Space-Saving** (Metwally, Agrawal and El Abbadi). Keep `m` counters. If the item has a counter, increment it. Otherwise
evict the item with the **smallest** counter, give the new item that counter's value plus one, and record the evicted
value as the new item's possible overestimate. The paper proves the facts the check tests: the smallest counter is at
most `floor(N / m)`; any item whose true count exceeds the smallest counter is certainly being monitored; a monitored
item's counter is never below its true count; and the counters always add up to `N`. Because every counter records its own
possible error, **the algorithm can tell you when its top-k is certain**: the top `i` items are guaranteed to be the top
`i` if the smallest `count - error` among them is at least the next count. Their experiments favour it over other
counter-based algorithms on skewed data and report that for Zipfian data far fewer counters suffice; this lesson does
not reproduce those experiments.

```python
class SpaceSaving:
    def __init__(self, m):
        self.m, self.n, self.count, self.err, self.heap = m, 0, {}, {}, []   # heap holds (count, item) pairs, some stale

    def add(self, item):
        self.n += 1
        if item in self.count:
            self.count[item] += 1
        elif len(self.count) < self.m:
            self.count[item], self.err[item] = 1, 0
        else:
            low, c = self._pop_min()
            del self.count[low], self.err[low]
            self.count[item], self.err[item] = c + 1, c          # inherits the evicted count; that is its possible overestimate
        heapq.heappush(self.heap, (self.count[item], item))
        if len(self.heap) > 4 * self.m + 16:                      # drop stale pairs so memory stays O(m)
            self.heap = [(c, e) for e, c in self.count.items()]
            heapq.heapify(self.heap)

    def _pop_min(self):
        while True:
            c, e = heapq.heappop(self.heap)
            if self.count.get(e) == c:
                return e, c

    def min_count(self):
        while self.heap and self.count.get(self.heap[0][1]) != self.heap[0][0]:
            heapq.heappop(self.heap)
        return self.heap[0][0] if self.heap else 0

    def top(self, k):
        return sorted(self.count.items(), key=lambda kv: (-kv[1], kv[0]))[:k]

    def guaranteed(self, k):
        """Largest i <= k such that the i best items are certainly the i most frequent."""
        rows = self.top(len(self.count))
        slack = self.min_count() if len(self.count) == self.m else 0    # an unmonitored item has at most this many
        best, lowest = 0, float('inf')
        for i, (item, c) in enumerate(rows[:k], 1):
            lowest = min(lowest, c - self.err[item])
            outside = rows[i][1] if i < len(rows) else slack
            if lowest >= outside:
                best = i
        return best
```

The check runs the paper's own two-counter example (stream X, Z, Y, Y leaves a smallest counter of 1; X, Y, Y, Z leaves
2, so the smallest counter depends on order, which is why the analysis bounds it instead). Then 500 random streams with
random `m` assert: counters sum to the stream length; for every monitored item `count - error <= true <= count`; when
full, the smallest counter is at most `N // m` and every item above it is monitored; when not full, all counts are exact;
and every claim `guaranteed(k)` makes is checked against the true counts by brute force. On a skewed 30,000-event stream
50 counters recover the true top five in order.

**Choosing.** Count-min needs a candidate set and its error is relative to the whole stream; Space-Saving's error is
per item and visible, and its counters are the candidates. Sketches shine for *point queries and merging* (count-min); a
counter-based summary shines for *top-k with certificates* (Space-Saving). Redis ships a Top-K type built on
HeavyKeeper (a different counting scheme: count with exponential decay, biased against small flows), a hash table of
counts and a min-heap of the K best; its documentation says width and depth default to 7 and 8, the decay constant to
0.9, and suggests sizing the width as `k log k` and the depth as `log k` with a minimum of 5. That page was read, not the
HeavyKeeper paper, so no claim is made beyond what the page states.

---

## 6. Deep Dive 2: Windows and Trending

"Last hour" cannot be a fresh count per query. Cut time into one-minute buckets, keep a summary per bucket, drop the
bucket that slides out, and combine the rest. With Space-Saving per bucket the combination has **deterministic bounds**:
for a key monitored in a bucket, its contribution lies between `count - error` and `count`; for an unmonitored key in a
full bucket it lies between 0 and that bucket's smallest counter (the paper's guarantee), and in a bucket that is not
full it is exactly 0. Add those up to get `[lower, upper]` for the window. And any key with window count above
`N_window / m` must be a candidate in some bucket, because otherwise each bucket would hold at most `N_b / m` of it and
the total could not exceed `N_window / m`.

```python
class WindowTopK:
    def __init__(self, nbuckets, m):
        self.m = m
        self.buckets = collections.deque([SpaceSaving(m)], maxlen=nbuckets)    # the deque drops the oldest bucket

    def add(self, item):
        self.buckets[-1].add(item)

    def tick(self):                                  # a minute has passed
        self.buckets.append(SpaceSaving(self.m))

    def candidates(self):
        return {e for b in self.buckets for e in b.count}

    def bounds(self, item):
        lo = hi = 0
        for b in self.buckets:
            if item in b.count:
                lo += b.count[item] - b.err[item]
                hi += b.count[item]
            elif len(b.count) == self.m:
                hi += b.min_count()                  # unmonitored in a full bucket: at most the smallest counter
        return lo, hi

    def top(self, k):
        rows = [(e, *self.bounds(e)) for e in self.candidates()]
        return sorted(rows, key=lambda r: (-r[2], r[0]))[:k]
```

The check drives 300 random streams with random bucket counts, `m` and ticks, and for 11 keys (one never seen) asserts
`lower <= true <= upper` against an exact count of the same window, and that every key above `N / m` is a candidate.
When every bucket has room the answer is exact, and after enough ticks the window is empty. The result is a list of
`(key, lower, upper)`, ranked by upper bound (so no key that might be heavy is ranked below one that is not), with ties by
key; the check asserts that rule against a recomputation. Serve the lower bound as "at least" and the upper bound as "at
most", and do not claim a rank order the intervals do not support.

**Trending is a ratio, not a count.** A giant video with a steady million views an hour is popular, not trending. A
simple score divides the recent window's count by the key's own recent average. Smoothing stops a zero baseline from
giving an infinite score, but it does not stop a tiny key outranking a big one, so there is also a minimum volume below
which a key is not trending at all. This one is **illustrative; no platform's real formula was read**, and a production
version also handles seasonality (a Monday has a different baseline from a Sunday) and demotes content that trended before.

```python
def trend_score(recent, history, smoothing=5.0, min_volume=20):
    if recent < min_volume:
        return 0.0                                   # too small to call a trend, whatever the ratio
    baseline = sum(history) / len(history) if history else 0.0
    return (recent + smoothing) / (baseline + smoothing)
```

The check asserts the printed values: a steady key scores exactly 1.0, a key rising from about 10 to 200 per window
scores 205/15, about 13.7, a key growing from 1,000 to 1,500 scores about 1.5, and a key falling scores below 1. A key
going from 0 to 3 scores 1.6 with `min_volume=0`, above the 1,000 to 1,500 key, which is exactly what the volume rule
removes (it scores 0.0 by default). New keys with real volume score high: 30 views against no history is 7.0. To get *candidates* for trending, you still need per-key
counts; run this score over the candidates of the recent window, which is why the window summaries above come first.

---

## 7. Deep Dive 3: Many Servers, Hot Keys and the Shard-Merge Trap

**Partition by key.** If events are routed so that every event for a key goes to one aggregator, the key's whole count
lives in one place, and the global top-K is exactly the top-K of the union of the shards' local top-K lists (sy39 shows
this for leaderboards; here it is repeated only to contrast it with the case that breaks). **Partition by
arrival** (round robin, or whichever server received the event) does not have that property. Three shards where item `a`
has 3 views on each and shards' own leaders have 4 each: every local top-1 is a different item with 4 views, the merged
top-1 is one of them, and `a`, with 9 views in total, is lost. Asking each shard for more than K helps here, but no fixed
extra works in general. The check builds exactly that case, asserts the failure, and also verifies on 150 random streams
that key-partitioned merging equals the exact top-K.

```python
def shard_of(item, n_shards):
    return _fp(item) % n_shards

def merge_local_topk(shard_counts, k):
    total = collections.Counter()
    for sc in shard_counts:
        for e, c in sorted(sc.items(), key=lambda kv: (-kv[1], kv[0]))[:k]:
            total[e] += c
    return sorted(total.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
```

If you cannot partition by key (an edge tier sees arbitrary events), count-min's linearity is the escape: each edge server
builds a sketch with the same shape and seed, a merger adds the tables, and the sum is the sketch of everything. That works
for point estimates and for ranking a candidate list, so the edge servers must also forward candidates. No source on merging
Space-Saving summaries was read, so nothing is claimed about how it is done.

**The hot key.** With the assumed Zipf shape the top key receives 4.7% of all traffic: 8,150 increments per second at the
peak rate. Pre-aggregate in each ingest server for a second or a minute and send `(key, delta)` pairs: the shared state
sees one update per key per server per interval instead of one per view. For one very hot key you can also split its
counter across `r` shards and sum on read (sy51).

**Late and duplicate events.** Count by event time into the right bucket and close a bucket only after a lateness
allowance; a bucket's summary is written once, so late events beyond the allowance are dropped or sent to a correction
path. Deduplicate by event id where the same view can arrive twice, since both sketches count what they are given.

---

## 8. Failure Modes

| What breaks | What you see | Defence |
|---|---|---|
| hot key | one aggregator or counter saturated | pre-aggregate at the edge, split the key |
| arrival-sharded top-K | a globally heavy item missing | partition by key, or merge counts not lists |
| window grows | sketch error grows with `N` (it is `epsilon * N`) | bucket per minute so each sketch sees a small `N`; reset per bucket |
| skew assumption false | counts of ranks 1 to 100 nearly equal, ranks unresolvable | report intervals; size by the gap you must resolve, not by memory |
| aggregator restart | lost current minute | replay the log from the last flushed bucket |
| replayed or duplicate events | inflated counts | event ids, idempotent flush of each bucket |
| clock skew, late data | counts in the wrong bucket | event time plus a lateness allowance |
| trending dominated by noise | tiny keys at the top | smoothing, minimum volume |
| bot traffic | manipulated ranks | filter before counting; out of scope here |

---

## 9. What Real Companies Did

- **Redis Open Source, Top-K** (documentation page, read 2026-11-26; page undated): a Top-K type based on the HeavyKeeper
  algorithm (Gong et al.), count-with-exponential-decay, using a hash table of counts and a min-heap of the K best; its
  use-case text names trending hashtags and most-read news. A product description, not a production case study.
- **Count-min sketch** (Cormode and Muthukrishnan; the journal version, preprint dated 16 December 2003, read in parts,
  see Sources): the bounds above, and their heavy-hitters procedure.
- **Space-Saving** (Metwally, Agrawal and El Abbadi, ICDT 2005, read in parts): the algorithm and guarantees above; their
  motivation was Internet advertising commissioners monitoring ad, click, sale and lead streams, which is the sy27 setting.
- No engineering write-up from YouTube, X (Twitter), Instagram, Reddit or any other platform on how they compute top or
  trending lists was read for this revision, so no claim is made about how they do it. "YouTube top videos" and
  "hashtags" here are the interview prompt, not a statement about those systems.

---

## 10. Pitfalls Checklist

1. **A global counter updated per event:** the hot key serialises everything.
2. **Sorting all keys on every query** instead of keeping candidates and materialising the list.
3. **Sizing exact counts from the key universe instead of the window:** a window holds at most as many keys as events (3.3 GB for the hour here, not 16 GB).
4. **Using a sketch without stating its error,** or quoting the error as relative when it is absolute (`epsilon * N`).
5. **Merging local top-K lists from arrival-partitioned shards.**
6. **A single long window** instead of buckets, so expiring old counts is impossible.
7. **Calling the most viewed "trending"** and showing a permanent giant.
8. **No minimum volume in the trend score:** even with smoothing, 0 to 3 views scores 1.6, above 1,000 to 1,500 at about 1.5.
9. **Mixing sketches built with different seeds or sizes.**
10. **Ignoring duplicate and late events,** which inflate or misplace counts silently.

---

## Drills

1. State the guarantee a count-min sketch gives for a point query, and what `epsilon` and `delta` control.
2. From the capacity table: why can the sketch detect rank 100 yet not order it against rank 101, and where does ordering
   stop? What changes if the popularity curve is flatter?
3. Why can Space-Saving say "these top 5 are certain" when a count-min sketch cannot, and what does it record to do so?
4. Work the paper's example: with 2 counters, stream X, Z, Y, Y versus X, Y, Y, Z. What is the smallest counter in each,
   and what does that show about bounding it?
5. A count-min sketch at epsilon 0.001 instead of 0.0001: what are the width and the absolute error on 208,333,333 views?
6. Show a three-shard example where merging local top-1 lists returns the wrong global top-1, and give two ways to fix it.
7. Why does a 60-bucket window of Space-Saving summaries guarantee that any key above `N_window / m` is a candidate?
8. A key goes from 0 to 3 views and another from 1,000 to 1,500. Compute `trend_score` for both with `min_volume=0` and
   with the default, and explain what smoothing fixes and what only the minimum volume fixes.

---

## Homework

1. Add per-minute buckets of `CountMin` to `WindowTopK` (same seed) and answer window point queries by summing the
   per-bucket estimates; compare its error with the Space-Saving bounds on a Zipf stream.
2. Add an exact reference run in a batch job over the event log, and compute how often the streaming top 10 differs from
   the exact top 10 over a day of synthetic traffic with exponent 1.0, 0.8 and 1.2.
3. Implement key splitting for the hottest key across `r` counters and measure per-shard load before and after.
4. Implement the decay idea in the Redis documentation's description and compare its top-k recall with `CMSTopK`.
5. Read the Space-Saving paper's section on merging or parallel use, if it has one, and extend `SpaceSaving` with a merge
   plus a check.
6. Write the trending score with seasonality (a baseline for the same hour last week) and show a case where it differs.

---

## Sources

All read 2026-11-26.

- Graham Cormode and S. Muthukrishnan, *An Improved Data Stream Summary: The Count-Min Sketch and Its Applications*,
  preprint submitted 16 December 2003 (PDF). Read: abstract, introduction, section 3 (data structure), section 4.1 (point
  query and Theorem 1) and section 5.2 (heavy hitters, Theorem 6). Range queries, inner products and quantiles were not read.
- Ahmed Metwally, Divyakant Agrawal, Amr El Abbadi, *Efficient Computation of Frequent and Top-k Elements in Data
  Streams*, ICDT 2005 (PDF). Read: abstract, introduction, section 3 (algorithm and properties: Lemma 1, Theorems 1 and
  2), section 4 (frequent and top-k queries). The space analysis for Zipfian data, the proofs (the paper omits them) and
  the experiments were skimmed, not verified.
- Redis, *Top-K*, redis.io/docs/latest/develop/data-types/probabilistic/top-k/ (read; page undated; code samples skipped).

## Further reading (not consulted)

Gong et al., *HeavyKeeper*; Charikar, Chen and Farach-Colton on count-sketch; Misra and Gries on frequent items; the
Space-Saving journal version with proofs; engineering posts on trending systems at large platforms. None were read for
this revision.

*Last reviewed: 26 November 2026.*
