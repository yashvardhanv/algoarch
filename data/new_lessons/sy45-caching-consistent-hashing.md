# Lesson 45 — Caching Patterns and Consistent Hashing

> **Priority:** ★★★★★ (proposed; the curriculum data holds the final rating) — a cache appears in almost every design, and the standard follow-ups are "how does a write reach it?" and "what happens to it when you add or lose a node?".
>
> **Study time:** 60 minutes. **Do this after:** Redis Internals & Eviction, and Latency Numbers & Capacity Estimation.
>
> **Level:** core.

Two questions sit under every cache. **Who is allowed to put a value in it, and in what order relative to the database write?** Get that wrong and a cache serves a stale value until it expires, with no error anywhere. **Which node holds a given key, and what moves when the set of nodes changes?** Get that wrong and adding one node empties your cache. Replication & Sharding introduced the ring and virtual nodes in a paragraph, and the Distributed Cache case study covers stampedes and hot keys. This lesson does the part they skip: it enumerates every interleaving of a cache-aside read and write to show exactly which one goes stale, and it measures five placement schemes so that "consistent hashing moves about one in N keys" is a number you produced.

---

## 1. Mental Model

> **A cache is a copy with no authority. Correctness comes from the order of two operations (commit to the source of truth, then invalidate), and capacity planning comes from the miss rate, which is the only part of the hit rate that reaches your database.**

What follows from it:

- **The database load is `reads x miss rate`.** Going from a 99% to a 95% hit rate does not cost 4% more work; it multiplies database reads by five.
- **Stale entries come from reordering, not from bugs in any one step.** Every step of cache-aside is correct alone; one specific interleaving of two correct sequences is not.
- **Delete is safer than update.** A delete says "I do not know the value now"; an update says "I know it", and two updaters can disagree about the order.
- **Placement has two jobs that pull apart:** spread keys evenly, and move few of them when nodes change. `hash(key) mod N` is excellent at the first and terrible at the second.
- **A cache you can lose is only safe if the database can survive the miss storm.** Size the database for the cold-cache case, or protect it (see the Distributed Cache lesson).

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "read-heavy, tolerate seconds of staleness" | cache-aside with a TTL, delete on write |
| "the cache must never be behind the database" | you do not want a cache; or write-through plus accepting the latency, and say what "never" means |
| "writes are bursty, the database cannot keep up" | write-behind (a queue), and name the loss window |
| "add cache nodes without a cold cache" | consistent hashing (ring with virtual nodes) |
| "numbered shards that only ever grow" | jump hash: no memory, but buckets must be numbered `0..N-1` |
| "nodes of different sizes" | virtual nodes in proportion to capacity, or weighted rendezvous |
| "one node must never exceed X% of average load" | consistent hashing with bounded loads |
| "a key is stale for a long time after an update" | check the order: commit, then invalidate; look for a reader filling after your delete |

---

## 3. What a Hit Rate Buys

Inputs below are **assumptions**; every figure is reproduced by `test/lesson_code/sy45_check.py`.

```python
def db_reads_per_second(qps, hit_rate):
    return round(qps * (1 - hit_rate))

def mean_read_ms(hit_rate, cache_ms, db_ms):
    """Look-aside: every read asks the cache; a miss also reads the database and fills the cache."""
    return cache_ms + (1 - hit_rate) * (db_ms + cache_ms)
```

With 100,000 reads per second, an assumed 0.5 ms cache round trip and an assumed 10 ms database read:

| Hit rate | Database load | Mean read latency |
|---|---|---|
| 99% | 1,000 reads/s | 0.605 ms |
| 95% | 5,000 reads/s | 1.025 ms |
| 90% | 10,000 reads/s | 1.550 ms |
| 0% (cold cache) | 100,000 reads/s | 11.000 ms |

Read the cold row as the capacity question: if the database is sized for the 99% row, a cold cache sends it 100 times its load. That is why the Distributed Cache lesson treats cold start as the dangerous failure.

Hit rate is also not a free function of cache size. Real key popularity is heavy-tailed; the code models it as Zipf with exponent 1 (key `i` is requested with probability proportional to `1/i`), which is an **assumption, not a measurement of any product**. It compares an ideal cache that permanently holds the most popular keys with an LRU cache, over 100,000 keys and 300,000 requests, starting cold:

```python
import bisect, itertools, random
from collections import OrderedDict

def zipf_stream(n_keys, n_requests, s, seed):
    """Key i (0-based) is requested with probability proportional to 1/(i+1)**s."""
    cdf = list(itertools.accumulate(1.0 / i ** s for i in range(1, n_keys + 1)))
    rng = random.Random(seed)
    return [bisect.bisect_left(cdf, rng.random() * cdf[-1]) for _ in range(n_requests)]

def ideal_hit_rate(n_keys, cache_size, s):
    w = [1.0 / i ** s for i in range(1, n_keys + 1)]
    return sum(w[:cache_size]) / sum(w)

def lru_hit_rate(stream, cache_size, skip=0):
    """Hit rate over stream[skip:]; the first `skip` requests only warm the cache."""
    cache, hits = OrderedDict(), 0
    for i, k in enumerate(stream):
        if k in cache:
            hits += i >= skip
            cache.move_to_end(k)
        else:
            cache[k] = True
            if len(cache) > cache_size:
                cache.popitem(last=False)
    return hits / (len(stream) - skip)
```

| Cache size (keys) | Ideal | LRU, cold start (300,000 requests) | LRU, warm (second half of 600,000) |
|---|---|---|---|
| 100 | 42.9% | 29.1% | 28.9% |
| 1,000 | 61.9% | 50.6% | 50.7% |
| 10,000 | 81.0% | 73.1% | 73.8% |
| 50,000 | 94.3% | 84.0% | 91.8% |

Three readings. Holding 1% of the keys already gives about 62% hits in the ideal case, and each tenfold increase in memory buys a roughly constant gain (about 19 points per decade here, because the ideal hit rate under this skew grows with the logarithm of the cache size); what grows is the memory each extra point costs. The cold-start LRU column is not a measure of LRU's policy at the large end: the 300,000-request trace touches only 48,056 distinct keys, so a 50,000-entry cache never evicts anything and the 84.0% is exactly 1 minus 48,056/300,000, the compulsory first-touch misses. The warm column (hits counted only in the second half of a 600,000-request trace) separates the two effects: at 50,000 keys LRU is 2.5 points below ideal (91.8% against 94.3%), and about eight of the ten points in the cold column were cold start. The policy gap is real but shrinks with size (14, 11, 7 and 2.5 points at the four sizes), because LRU spends space on recently seen keys that will not return. The check confirms the same code gives a hit rate of cache size divided by key count on uniform keys, which is why skew is what makes caching work at all.

---

## 4. The Write Patterns

| Pattern | A read | A write | You get | You pay |
|---|---|---|---|---|
| **Cache-aside** (look-aside) | app asks cache; on a miss the app reads the database and fills the cache | app writes the database, then deletes the key | the cache holds only what was read; a cache outage degrades to the database | the stale-fill race in section 5; the first read after a write is a miss |
| **Read-through** | the cache itself loads from the database on a miss | as above | one place implements loading, and it can coalesce concurrent misses | the cache must know how to talk to the database |
| **Write-through** | as above | the cache writes the database synchronously, then updates itself | reads right after writes hit | write latency of both; two updaters can still race (section 5) |
| **Write-behind** | as above | the cache acknowledges, then writes the database later in batches | the database sees fewer, larger writes | the cache is now the only copy for a while: crash and you lose acknowledged writes |
| **Refresh-ahead** | the cache reloads hot keys before they expire | as above | no expiry miss on hot keys | wasted loads for keys nobody reads again |

Facebook's memcache paper (read 2026-11-26) describes its use as a "demand-filled look-aside cache": a web server asks memcache, on a miss reads the database and populates the cache, and on a write sends SQL to the database and then a **delete** to memcache. The paper's stated reason for deleting instead of updating is that deletes are idempotent, and that memcache is not the authoritative source and may evict anything. Section 5 shows what update-on-write would cost.

Two defaults round this out. **Always set a TTL**, even when you invalidate on write: it bounds how long any stale fill can live, whatever bug put it there. **Cache misses too** (a short-lived "not found" entry), or a request for a missing key reaches the database every time.

---

## 5. Deep Dive 1: The Stale Fill, Enumerated

Cache-aside has a reader that does three steps (look in the cache, read the database, fill the cache) and a writer that does two (write the database, delete the key). Each step is atomic on its own. The interesting question is which merges of the two sequences leave a cache entry the database no longer agrees with. There are only `C(5,2) = 10`, so enumerate all of them:

```python
from itertools import combinations

def interleavings(a, b):
    """Every merge of step lists a and b that keeps each list's own order."""
    n = len(a) + len(b)
    for slots in combinations(range(n), len(a)):
        ia, ib = iter(a), iter(b)
        yield [next(ia) if i in slots else next(ib) for i in range(n)]

def stale_runs(first, second, start):
    """Run every interleaving; return the ones that end with the cache holding a value the database does not."""
    bad = []
    for seq in interleavings(first, second):
        s = dict(start)
        for _, step in seq:
            step(s)
        if s['cache'] is not None and s['cache'] != s['db']:
            bad.append([name for name, _ in seq])
    return bad

def get(s):
    if s['cache'] is not None:
        s['seen'], s['hit'] = s['cache'], True

def read_db(s):
    if not s.get('hit'):
        s['seen'] = s['db']

def fill(s):
    if not s.get('hit'):
        s['cache'] = s['seen']

def write_db(s): s['db'] = 'new'
def drop(s): s['cache'] = None

READER = [('get', get), ('read db', read_db), ('fill', fill)]
```

Run the reader against the writer in the right order (commit, then delete) from an empty cache:

```python
start = {'db': 'old', 'cache': None, 'lease': None, 'n': 0}
stale_runs(READER, [('write db', write_db), ('delete', drop)], start)
# [['get', 'read db', 'write db', 'delete', 'fill']]
```

One of ten. The reader reads `old`, the writer commits `new` and deletes, and then the reader fills `old` **after** the delete. The delete found nothing to delete, and the stale value now stays until the TTL. This is the race the Distributed Cache lesson names; here it is a single identified sequence rather than a sentence.

The check varies three things, and the counts below are what it produced (stale interleavings out of ten, or out of six for two writers):

| Scenario | Cold cache | Warm cache |
|---|---|---|
| write database, then delete (the correct order) | 1 of 10 | 0 of 10 |
| delete, then write database (wrong order) | 6 of 10 | 2 of 10 |
| the same two orders, with leases (below) | 0 and 2 of 10 | 0 and 2 of 10 |
| two writers that each write the database then **set** the cache | 2 of 6 | |
| two writers that each write the database then **delete** | 0 of 6 | |

Reading the table:

- **Order matters.** Deleting before the write lets a reader fill the old value between the two steps, six ways out of ten from a cold cache. Commit first, then invalidate.
- **Update-on-write loses to concurrency.** With two writers, the database may end up with `B` while the cache ends with `A` (database order `A, B`, cache order `B, A`, and the reverse). Two deletes cannot disagree, which is the idempotence argument from the paper.
- **A warm cache hides the race, not removes it.** In the warm column the reader mostly hits and never fills; the stale fill needs a miss, and misses are what a cold start, an eviction or a recently deleted hot key produce.

**Leases close the remaining case.** The memcache paper describes a lease: on a miss the cache hands the reader a 64-bit token bound to the key; the reader presents it when filling; a delete invalidates outstanding tokens, so a fill carrying an invalidated token is refused. The paper compares this to load-linked/store-conditional and credits it with preventing stale sets. It also describes rate-limiting tokens, by default one per key per 10 seconds, so that concurrent readers of a missing key wait briefly instead of all reading the database; for a set of keys prone to thundering herds over a week, the paper reports a peak of 17,000 database queries per second without leases and 1,300 with them. Here is the model:

```python
def get_lease(s):
    get(s)
    if not s.get('hit'):
        s['n'] += 1
        s['lease'] = s['tok'] = s['n']

def fill_lease(s):
    if not s.get('hit') and s['lease'] == s['tok']:
        s['cache'], s['lease'] = s['seen'], None

def drop_lease(s):
    s['cache'], s['lease'] = None, None

LEASED_READER = [('get+lease', get_lease), ('read db', read_db), ('fill if lease', fill_lease)]
```

Against write-then-delete the leased reader leaves **zero** stale runs in both start states: the problem sequence ends with a refused fill. The reader still returns `old` to its own caller once, which is acceptable (it read before the commit); what changes is that the cache is not poisoned. Against delete-then-write, leases do **not** help (two stale runs of ten in both columns): the reader gets a fresh token after the delete and reads the database before the write. A lease only protects the commit-then-invalidate order, so the order rule stays.

The honest summary for an interview: cache-aside with delete-after-commit leaves a narrow stale window that needs a miss to coincide with a write; a TTL bounds the damage; leases or versioned writes (or invalidation driven from the database's commit log, which the Facebook paper describes doing with a daemon that reads committed SQL statements) shrink it further. Say which one you would pay for, and why the product tolerates the rest.

---

## 6. Deep Dive 2: Who Owns a Key, and What Moves

The ring: hash nodes and keys onto the same circle; a key belongs to the first node point clockwise. Each node places several points (virtual nodes). Dynamo's paper (read 2026-11-26) uses MD5 to turn a key into a 128-bit position, assigns each node multiple "tokens" on the ring, and builds a key's **preference list** of replicas by walking clockwise and **skipping positions so that the list holds only distinct physical nodes**. The code does the same with a 64-bit slice of MD5:

```python
import bisect, hashlib, math, statistics

def h64(text):
    return int.from_bytes(hashlib.md5(text.encode()).digest()[:8], 'big')

class Ring:
    """Each node owns `vnodes` points; a key belongs to the first point clockwise from its hash."""
    def __init__(self, nodes=(), vnodes=100):
        self.vnodes, self.points, self.owner = vnodes, [], {}
        for n in nodes:
            self.add(n)

    def add(self, node):
        for i in range(self.vnodes):
            p = h64('%s#%d' % (node, i))
            self.owner[p] = node
            bisect.insort(self.points, p)

    def remove(self, node):
        gone = {p for p, n in self.owner.items() if n == node}
        self.points = [p for p in self.points if p not in gone]
        for p in gone:
            del self.owner[p]

    def lookup(self, key):
        i = bisect.bisect_right(self.points, h64(key)) % len(self.points)
        return self.owner[self.points[i]]

    def preference_list(self, key, n):
        """The first n distinct physical nodes clockwise from the key."""
        i = bisect.bisect_right(self.points, h64(key))
        out = []
        for step in range(len(self.points)):
            node = self.owner[self.points[(i + step) % len(self.points)]]
            if node not in out:
                out.append(node)
                if len(out) == n:
                    break
        return out
```

Two schemes need no ring at all. **Rendezvous (highest random weight) hashing** gives each key to the node whose `hash(key, node)` is largest; it costs one hash per node per lookup. **Jump hash**, from Lamping and Veach (read 2026-11-26), maps a key to a bucket number with no stored state in about `ln(n)` loop steps, with one restriction the paper states plainly: buckets must be numbered `0..n-1`, so you can add or drop only at the end. That suits shards of storage (where a shard cannot simply vanish) better than caches whose servers die at random.

```python
def rendezvous(key, nodes):
    return max(nodes, key=lambda n: h64('%s|%s' % (key, n)))

def jump_hash(key, buckets):
    """Lamping and Veach. key is a 64-bit integer; returns a bucket in 0..buckets-1."""
    b, j = -1, 0
    while j < buckets:
        b = j
        key = (key * 2862933555777941757 + 1) & 0xFFFFFFFFFFFFFFFF
        j = int((b + 1) * (float(1 << 31) / float((key >> 33) + 1)))
    return b
```

Now measure. The harness takes 50,000 keys over 10 nodes, adds an eleventh, and reports **balance** (busiest node over the mean, and standard deviation over the mean) and **movement** (share of keys whose owner changed). The ideal movement is the new node's fair share, 1/11 = 9.1%.

```python
def balance(counts):
    mean = sum(counts) / len(counts)
    return max(counts) / mean, statistics.pstdev(counts) / mean

def moved_share(before, after):
    return sum(x != y for x, y in zip(before, after)) / len(before)

def compare(keys, n=10):
    """Rows of (scheme, busiest/mean, std dev/mean, share of keys that move when node n+1 joins)."""
    old = ['node-%d' % i for i in range(n)]
    new = old + ['node-%d' % n]
    def row(name, before, after):
        return (name,) + balance([before.count(x) for x in old]) + (moved_share(before, after),)
    rows = [row('mod N', [old[h64(k) % n] for k in keys], [new[h64(k) % (n + 1)] for k in keys])]
    for v in (1, 10, 100, 1000):
        ring = Ring(old, v)
        before = [ring.lookup(k) for k in keys]
        ring.add(new[-1])
        rows.append(row('ring, %d vnode%s' % (v, '' if v == 1 else 's'), before, [ring.lookup(k) for k in keys]))
    rows.append(row('rendezvous', [rendezvous(k, old) for k in keys], [rendezvous(k, new) for k in keys]))
    rows.append(row('jump hash', [old[jump_hash(h64(k), n)] for k in keys], [new[jump_hash(h64(k), n + 1)] for k in keys]))
    return rows
```

| Scheme | Busiest / mean | Std dev / mean | Keys moved on adding a node |
|---|---|---|---|
| mod N | 1.027 | 0.017 | 91.1% |
| ring, 1 vnode | 2.794 | 0.927 | 11.5% |
| ring, 10 vnodes | 1.604 | 0.264 | 9.3% |
| ring, 100 vnodes | 1.099 | 0.056 | 7.9% |
| ring, 1000 vnodes | 1.026 | 0.020 | 9.4% |
| rendezvous | 1.026 | 0.018 | 9.2% |
| jump hash | 1.019 | 0.012 | 8.9% |

What the table says:

1. **`mod N` is not unbalanced; it is unstable.** Its balance is as good as any, and it moves 91% of keys when `N` goes from 10 to 11 (the fraction that stays is roughly `1/11`). The Jump Hash paper makes the same point with 10 to 12 shards. For a cache, 91% of keys moving is a hit-rate collapse, shown in the next paragraph.
2. **A ring with one point per node is badly lumpy:** the busiest node holds 2.8 times the mean. Virtual nodes fix it, with the cost of more points to store and search. The Jump Hash paper reports that Karger et al.'s experiments needed 1,000 points per bucket to reach a 3.2% standard deviation; the 2.0% here at 1,000 virtual nodes is the same order, on a different setup, so do not read the two numbers as a replication.
3. **Movement is not minimised by balance.** Every consistent scheme moves about the new node's share (the table's spread around 9.1% is sampling noise on a single node's share, and with one vnode it is the luck of one arc). The invariant the check verifies on rings of 1, 7 and 50 virtual nodes is stronger than the average: **keys only ever move to the new node, never between old nodes** (the monotonicity property Karger et al. define). Rendezvous and jump hash satisfy it too.
4. **Rendezvous and jump hash beat a ring on balance without virtual nodes,** at different costs: rendezvous does one hash per node per lookup; jump hash needs the numbered-bucket restriction.

**What the cache feels.** Assume a 95% hit rate and 100,000 reads per second, and a database that comfortably serves 5,000. Adding a node to a `mod N` cache sends 91% of keys to a node that does not hold them, so the miss rate becomes `1 - 0.95 x (1 - 0.911)`, about 91.5%, or **91,500 reads/s** at the database. With a 1,000-vnode ring only 9.4% of keys move, the miss rate becomes about 14%, and the database sees **14,000 reads/s**: still almost three times its comfortable load, which is why you add cache nodes one at a time and watch the miss rate, as the Distributed Cache lesson advises.

**Losing a node.** The same ring answers "where does a dead node's load go?". The harness removes `node-0` and reports the largest share of its keys that any single survivor inherits, and how many survivors inherit anything:

```python
def failure_spread(keys, vnodes, n=10):
    """Kill node-0. Returns (largest share of its keys inherited by one survivor, survivors that inherit any)."""
    ring = Ring(['node-%d' % i for i in range(n)], vnodes)
    before = [ring.lookup(k) for k in keys]
    ring.remove('node-0')
    gained = {}
    for k, b in zip(keys, before):
        if b == 'node-0':
            a = ring.lookup(k)
            gained[a] = gained.get(a, 0) + 1
    return max(gained.values()) / before.count('node-0'), len(gained)
```

| Vnodes per node | Survivors that inherit keys | Largest inherited share |
|---|---|---|
| 1 | 1 | 100.0% |
| 10 | 6 | 22.9% |
| 100 | 9 | 21.1% |
| 1000 | 9 | 14.5% |

With one point per node the dead node's whole arc lands on its single clockwise neighbour, which now carries double load and may fail next: a cascade that starts with one machine. Virtual nodes spread the inheritance across the other nine; the ideal is 1/9 = 11.1%. Dynamo's paper lists exactly this as the benefit of virtual nodes: the load of an unavailable node is dispersed over the remaining ones, and a returning node takes a roughly equal amount from each.

**Choosing among them.** Dynamo's own history is instructive. Its first deployment used `T` random tokens per node with partitions defined by token values (the scheme above); the paper reports that bootstrapping a new node meant low-priority scans of production data, which took almost a day in busy periods, and that the scheme tied partitioning to placement. It moved to fixed, equal-size partitions with `Q/S` tokens per node, which the paper says gave better load balance and cut the membership information by three orders of magnitude, at the price of needing coordination when membership changes. The lesson for an interview is not a winner; it is that **how you cut the key space (fixed partitions) can matter more than how you place nodes on the circle**. Google's Maglev load balancer (read in part, 2026-11-26) takes the opposite priority from classic consistent hashing: it fills a prime-sized lookup table from each backend's pseudorandom preference list, favouring even spread over minimal disruption, because its connection tracking makes a few disruptions tolerable.

---

## 7. Deep Dive 3: Bounding the Load

Balance in the table is about **how many keys** each node holds, and a ring with 100 virtual nodes still has a busiest node 10% above the mean. If the requirement is a hard cap (no server above 125% of average), Mirrokni, Thorup and Zadimoghaddam (read in part, 2026-11-26) give the idea: choose a balancing parameter `c = 1 + e`, give every node capacity `ceil(c x m / n)` for `m` keys on `n` nodes, and when a key's natural node is full, **forward it to the next node clockwise** that is not, as linear probing does. The paper proves bounds on how many keys move on updates; this lesson implements only the simple placement, where keys are inserted in order and a full node forwards:

```python
def bounded_assign(ring, keys, c):
    """Place keys in order; a node at capacity forwards the key to the next point clockwise."""
    nodes = sorted(set(ring.owner.values()))
    cap = math.ceil(c * len(keys) / len(nodes))
    load, placed = dict.fromkeys(nodes, 0), {}
    for k in keys:
        i = bisect.bisect_right(ring.points, h64(k))
        while load[ring.owner[ring.points[i % len(ring.points)]]] >= cap:
            i += 1
        node = ring.owner[ring.points[i % len(ring.points)]]
        load[node] += 1
        placed[k] = node
    return placed

def bounded_report(c=1.25, n=10, m=20000):
    keys = ['key-%d' % i for i in range(m)]
    out = []
    for v in (1, 10, 100):
        ring = Ring(['node-%d' % i for i in range(n)], v)
        plain = [ring.lookup(k) for k in keys]
        placed = list(bounded_assign(ring, keys, c).values())
        out.append((v, balance([plain.count('node-%d' % i) for i in range(n)])[0],
                    balance([placed.count('node-%d' % i) for i in range(n)])[0]))
    return out
```

With `c = 1.25`, 10 nodes and 20,000 keys, the busiest node's load over the mean:

| Vnodes per node | Plain ring | Bounded, c = 1.25 |
|---|---|---|
| 1 | 2.771 | 1.250 |
| 10 | 1.595 | 1.250 |
| 100 | 1.086 | 1.086 |

The cap holds for any ring, and where the ring is already within it (100 vnodes) nothing is forwarded. The check also confirms that with an enormous `c` the assignment equals the plain ring. Two cautions. This placement is **history dependent** (which key forwards depends on arrival order), and the paper's contribution is doing updates without reshuffling; recomputing from scratch when `n` changes would move more keys than a plain ring, so treat the function as a model of the invariant, not as a production algorithm. And it bounds the **count** of keys per node, not request rate: one key at a million requests per second still lands on one node, which is the hot-key problem and needs replication or a local cache, not a better ring. The paper reports that the idea was used in Google Cloud Pub/Sub and, from a Vimeo engineering post it cites (the post itself was not read), by Vimeo with `c = 1.25` for video streaming.

Memcache's Gutter pool (same paper) makes the related point for failures: when a server stops answering, clients do not rehash its keys onto the remaining servers, because a single key can account for a large share of a server's requests and the next owner of a hot key may be overloaded in turn; they send the retry to a small, separate pool of idle servers whose entries expire quickly. The paper reports that Gutter cut client-visible failures by 99% and turned 10% to 25% of failures into hits each day. The trade is the same as everywhere here: slightly stale data for protection of the backing store.

---

## 8. What Real Systems Document

All read 2026-11-26. Dynamo documents MD5 key positions, virtual nodes as tokens, preference lists of distinct physical nodes, and the three partitioning strategies with their measured trade-offs. Karger et al. define consistent hashing by balance, monotonicity, spread and load, and describe giving each bucket about `log C` points on the circle. Lamping and Veach give the jump-hash code and its restriction to numbered buckets. The Facebook memcache paper documents look-aside caching with delete-on-write, leases and Gutter, and says items are distributed across hundreds of memcached servers in a cluster by consistent hashing. No product's current behaviour is asserted from memory, and Redis Cluster's hash slots (the fixed-partition idea in another product) were not read for this lesson, so they are not described.

---

## 9. Pitfalls Checklist

1. **Deleting the cache key before committing the database write.** Six of ten interleavings go stale from a cold cache. Commit, then invalidate.
2. **Updating the cache on write with more than one writer.** The database and the cache can end in different orders; prefer delete.
3. **No TTL "because we invalidate".** The TTL is the backstop for every invalidation you lose or reorder.
4. **`hash(key) mod N` for a cache fleet.** Balanced, and 91% of keys move on a one-node change.
5. **One ring point per node.** The busiest node holds 2.8 times the mean and a failure doubles one neighbour.
6. **Quoting "consistent hashing moves 1/N" without the monotonic property,** or without noting that the hit rate you lose is still the moved share.
7. **Believing a ring fixes a hot key.** It balances keys, not requests; a single hot key needs replication or a local cache.
8. **Treating write-behind as a cache feature.** It makes the cache the only copy; name the loss window and the replay story.
9. **Sizing the database for the 99% row.** Size or protect it for the cold-cache row.
10. **Jump hash for servers that fail at random.** Its buckets must be numbered `0..n-1`; it suits shard counts that only grow.

---

## Drills

1. A database serves 100,000 reads per second at a 98% hit rate. What load does it see at 94%, and how much more is that than at 98%?
2. Enumerate the ten interleavings in your head or on paper: which single one leaves a stale entry under write-then-delete, and what does the delete find?
3. Why does delete-then-write go stale in more interleavings than write-then-delete? Give one sequence.
4. Two writers each update the database and then set the cache. Write the two interleavings that end with different values in each place.
5. What does a lease token prevent, what does it not prevent, and which order of writer steps does it still require?
6. With `mod N`, going from 10 to 11 nodes moves about 91% of keys. Why is it about `1 - 1/11`, and what miss rate does a 95%-hit cache see right after?
7. Why does one ring point per node give a lumpy distribution and a failure that doubles one neighbour, and how many survivors share the dead node's keys at 100 virtual nodes?
8. You need no server above 125% of the average key count. Which scheme, what capacity per node, and what does it not protect against?

---

## Homework

1. Add a third step to the reader (`validate`: re-read the database and refuse to fill if it changed) and run `stale_runs` against both writer orders; compare with leases.
2. Extend `Ring` with weights (a node with twice the capacity places twice the points) and measure whether its share of keys is about twice the others.
3. Run `compare` with 100 nodes instead of 10 and with 100,000 keys; which row changes most and why?
4. Implement Maglev's table population from the paper's pseudocode and measure its balance and the keys that move when one backend is removed, against a 1,000-vnode ring.
5. Read the Dynamo paper sections 4.2 and 6.2 end to end and reproduce the efficiency measure (mean load over maximum load) for the three strategies on a small simulation.
6. Re-do the hit-rate table with Zipf exponent 0.8 and 1.2; write two sentences on how skew changes the memory you need for a 90% hit rate.

---

## Sources

All read 2026-11-26.

- DeCandia et al., *Dynamo: Amazon's Highly Available Key-value Store* (SOSP 2007), allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf. Read sections 4.1 to 4.6 and 6.2 to 6.4 (to the start of the client-driven coordination comparison). Source for MD5 key hashing, virtual nodes (tokens), preference lists of distinct nodes, the three partitioning strategies and their reported trade-offs.
- Karger et al., *Consistent Hashing and Random Trees* (STOC 1997), cs.princeton.edu/courses/archive/fall09/cos518/papers/chash.pdf. Read the abstract, introduction and the consistent-hash definitions and construction in section 4 (balance, monotonicity, spread, load; about `log C` points per bucket); proofs and the random-tree protocols were skimmed or not read.
- Lamping and Veach, *A Fast, Minimal Memory, Consistent Hash Algorithm* (arXiv 1406.2294), arxiv.org/pdf/1406.2294. Read in full. Source for the algorithm, the numbered-bucket restriction and the Karger comparison.
- Mirrokni, Thorup, Zadimoghaddam, *Consistent Hashing with Bounded Loads* (arXiv 1608.01350), arxiv.org/pdf/1608.01350. Read the abstract, introduction and the forwarding description; the proofs were not read. The Vimeo account comes from this paper's text, not from the Vimeo post.
- Nishtala et al., *Scaling Memcache at Facebook* (NSDI 2013), usenix.org/system/files/conference/nsdi13/nsdi13-final170_update.pdf. Read the overview, section 3 through 3.3 (latency, leases, pools, replication within pools, failure handling and Gutter) and the invalidation pipeline in section 4.1; the multi-region sections and the evaluation were not read.
- Eisenbud et al., *Maglev: A Fast and Reliable Software Network Load Balancer* (NSDI 2016), usenix.org/system/files/conference/nsdi16/nsdi16-paper-eisenbud.pdf. Read the abstract and section 3.4 only.

## Further reading (not consulted)

Thaler and Ravishankar, *Using Name-Based Mappings to Increase Hit Rates* (rendezvous hashing, 1998); the Redis Cluster specification; Facebook's later memcache and TAO papers; Vimeo's engineering post on bounded loads. None were read for this revision.

*Last reviewed: 2026-11-26.*
