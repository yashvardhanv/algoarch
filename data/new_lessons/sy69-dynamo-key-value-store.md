# Lesson 69 — Case Study: Dynamo-style Key-Value Store

> **Priority:** ★★★★☆ (proposed; the curriculum data holds the final rating) — "design a key-value store that stays up" is a standard prompt, and the follow-ups (what does R + W > N buy, what is a sloppy quorum, how do replicas heal) are where answers go vague.
>
> **Study time:** 85 minutes. **Do this after:** Caching Patterns and Consistent Hashing; Time, Clocks and Ordering; Replication & Sharding; CAP Theorem to PACELC.
>
> **Level:** extended.

A Dynamo-style store chooses to accept every write and sort out conflicts later. The ring, the virtual nodes and the preference list belong to Caching Patterns and Consistent Hashing, and version vectors and their truncation to Time, Clocks and Ordering; this lesson links to them and does not repeat them. It builds what is left, as a small model checked in `test/lesson_code/sy69_check.py` against independent references: quorum overlap enumerated exhaustively, the hole a sloppy quorum opens, hinted handoff and read repair under random failures, Merkle-tree anti-entropy, and a shopping cart that does not resurrect deleted items. Capacity numbers come from `capacity_check_h.py`.

---

## 1. Mental Model

> **Dynamo trades a single truth for an always-open write path. Writes are never refused for want of a quorum; the price is that reads may return several versions, and "latest" is something the application, not the store, decides. The knobs N, R and W do not buy consistency; they buy a probability that replicas overlap.**

- **R + W > N is a statement about two sets of nodes meeting.** It holds only while both sets come from the same N nodes. A sloppy quorum breaks that (section 5, measured).
- **Three repair mechanisms cover three failure lengths:** read repair for what a read happens to see, hinted handoff for a node that is briefly away, Merkle-tree anti-entropy for everything else.
- **Conflict handling moves to the reader.** The store keeps sibling versions; the application merges. A merge that is only a union brings deleted items back (the paper says so).
- **Latency is an order statistic.** An operation waits for the W-th (or R-th) fastest replica, so smaller W and R cut the tail sharply (section 3).

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "always writable, even during a partition", "shopping cart" | Dynamo-style: sloppy quorum, hinted handoff, siblings merged by the application |
| "which replicas does a key live on" | the preference list from Caching Patterns and Consistent Hashing |
| "how many replicas must answer" | N, R, W; (3,2,2) is the common setting the paper reports; R + W > N for overlap |
| "a node is down for an hour, then returns" | hinted handoff first; Merkle anti-entropy for whatever the hints miss (section 6) |
| "replicas have drifted, how do you find out cheaply" | Merkle trees: compare roots, descend only where hashes differ |
| "two clients write the same key at once" | version vectors detect it; the client merges (Time, Clocks and Ordering) |
| "need strictly one winner, or a transaction across keys" | not this design: it offers no isolation and single-key updates only (paper) |

---

## 3. Requirements and Capacity

**Functional.** `get(key)` returns one object or several conflicting versions plus an opaque context; `put(key, context, object)`. Keys and values are opaque bytes; values are small (the paper says usually under 1 MB). No multi-key operations, no isolation. **Non-functional.** Writes are accepted through node and data-centre failures; latency is stated at the 99.9th percentile (the paper's example SLA: 300 ms for 99.9% of requests at a given load); incremental scaling; no central coordinator.

**Capacity.** Inputs marked *assumed* are this lesson's. Inputs marked *paper* are figures the Dynamo paper prints, used as inputs. Every result is reproduced by `capacity_check_h.py`.

| Input | Value |
|---|---|
| nodes | 200 *(paper: its measurements ran on "a couple hundred nodes")* |
| N, R, W | 3, 2, 2 *(paper: the common configuration)* |
| keys and value size | 1 billion keys, 1 KB each *(assumed)* |
| peak load | 300,000 puts per second, 1,000,000 gets per second *(assumed)* |
| read path | the coordinator asks all N nodes and waits for R *(paper, section 4.5)* |

| Result | Arithmetic | Value |
|---|---|---|
| data per node | 1 billion x 1 KB x 3 / 200 | 15 GB: storage is not the constraint |
| replica writes per node | 300,000 x 3 / 200 | 4,500 per second |
| replica reads per node | 1,000,000 x 3 / 200 | 15,000 per second (3, not 2, because all N are asked) |
| tail, W = N = 3, each replica slow with probability 1% | 1 - 0.99^3 | 2.97% of writes slow |
| tail, W = 2 | 3 x 0.01^2 x 0.99 + 0.01^3 | 0.0298% |
| tail, W = 1 | 0.01^3 | 0.0001% |
| slow-replica rate that still meets a 99.9% target | solve for q | 1.84% at W = 2, 0.033% at W = 3 |
| hint writes for a node down one hour | 4,500 x 3,600 | 16.2 million (16.2 GB if every write kept its own hint) |
| distinct keys among them, writes spread evenly over the node's 15 million keys *(assumed)* | 15M x (1 - e^(-16.2/15)) | 9.9 million keys, 9.9 GB |
| the same when the writes equal the key count, at 3,333 s | 15M x (1 - 1/e) | 9.5 million keys, 9.5 GB |
| Merkle diff, 1 million keys, 100 differing leaves | 1 + 2 x 100 x 20 hashes of 20 bytes | at most 4,001 hashes, about 80 KB, against 20 MB for all key hashes |

```python
from math import comb

def p_slow(n, k, q):
    """An operation returns when the k-th fastest of n replicas answers, so it is slow iff more than n-k replicas are slow.
    Assumes replicas are slow independently with probability q."""
    return sum(comb(n, j) * q**j * (1 - q)**(n - j) for j in range(n - k + 1, n + 1))
```

The check compares this with a simulation on four (n, k, q) settings, and with the hand-written cases (W = 3 gives 1 - 0.99^3).

Five conclusions. **The cluster is request-bound, not disk-bound:** 15 GB per node is small; fan-out is the cost (3 writes per put, 3 reads per get). **Replicas fail independently only if you place them so;** the tail figures assume independence, which a shared rack or data centre breaks (the paper spreads each preference list over several data centres). **Why R and W below N:** the paper says latency is "dictated by the slowest of the R (or W)" replicas, and the table shows how much waiting for one fewer replica removes. **Hints are bounded by the node's key count, not by the outage length:** a hint store that keeps the newest version of each key cannot grow past the 15 GB the node holds, and after an hour it holds about 9.9 GB of distinct keys (9.5 GB at 3,333 s, when the writes equal the key count). Anti-entropy afterwards moves only the keys that changed, the same set, so volume does not decide between them. What does: hints sit on stand-ins that can fail, which the paper gives as the reason for anti-entropy; they take space on the stand-ins; and a hint log that appends one entry per write grows without bound (16.2 GB in the hour). **The Merkle cost scales with differences, not data.**

---

## 4. API and Data Model

```
get(key)                    -> [(value, clock)], context      (one value, or siblings)
put(key, context, value)    -> ok | failed                    (context = merged clock from a prior get)
node store:  key -> [(clock, value)]  siblings that no other version supersedes
hint store:  stand-in node -> [(intended node, key, clock, value)]   (kept apart from the store)
```

Placement and clocks are not repeated here. The paper hashes keys with MD5, replicates each key at the N clockwise successors and builds the preference list over distinct physical nodes (Caching Patterns and Consistent Hashing). Each version carries a vector clock; if one clock descends from another the older version is dropped, otherwise both are kept (Time, Clocks and Ordering). The code uses one position per node in place of virtual nodes: the model is about replication, not placement.

---

## 5. Deep Dive 1: Quorums, and the Hole a Sloppy Quorum Opens

The paper: a put goes to the first N healthy nodes of the preference list and succeeds when W-1 others answer (the coordinator wrote locally); a get asks the same set and returns after R replies, with all versions that no other supersedes. First the helpers, then the model.

```python
import hashlib

def h(s): return int(hashlib.md5(s.encode()).hexdigest(), 16)

def descends(a, b):                      # a has seen everything b has
    return all(a.get(n, 0) >= c for n, c in b.items())

def merge_clock(clocks):
    out = {}
    for c in clocks:
        for n, v in c.items(): out[n] = max(out.get(n, 0), v)
    return out

def reconcile(versions):
    """(clock, value) pairs. Keep one copy of every version that no other version supersedes."""
    out = []
    for i, (c, v) in enumerate(versions):
        if any(descends(c2, c) and (c2 != c or j < i) for j, (c2, _) in enumerate(versions) if j != i):
            continue
        out.append((c, v))
    return out
```

```python
LEAVES = 8

class Dynamo:
    """One key space over a ring of nodes. Hinted replicas sit in a separate store (paper, 4.6); whether a read served by the stand-in returns them is the
    `read_hints` switch, because the paper does not say. The default is that it does not."""
    def __init__(self, nodes, n=3, r=2, w=2, sloppy=True, read_hints=False):
        self.nodes, self.n, self.r, self.w, self.sloppy, self.read_hints = list(nodes), n, r, w, sloppy, read_hints
        self.up = set(nodes)
        self.data = {x: {} for x in nodes}      # node -> key -> [(clock, value)]
        self.hints = {x: [] for x in nodes}     # stand-in -> [(intended, key, clock, value)]
        self.issued = {}                        # (node, key) -> last counter that node issued
        self.log = []                           # every (key, clock, value) any put created: the audit trail for the checks

    def preference_list(self, key):
        s = h(key) % len(self.nodes)
        return [self.nodes[(s + i) % len(self.nodes)] for i in range(len(self.nodes))]

    def contacts(self, key):
        """[(holder, intended)]: the first N healthy nodes if sloppy, else the live members of the home N."""
        pl = self.preference_list(key); home = pl[:self.n]
        if not self.sloppy:
            return [(x, x) for x in home if x in self.up]
        healthy = [x for x in pl if x in self.up][:self.n]
        missing = [x for x in home if x not in self.up]
        return [(x, x) if x in home else (x, missing.pop(0)) for x in healthy]

    def _store(self, holder, intended, key, clock, value):
        if holder == intended:
            self.data[holder][key] = reconcile(self.data[holder].get(key, []) + [(dict(clock), value)])
        else:
            self.hints[holder].append((intended, key, dict(clock), value))

    def put(self, key, value, ctx=None, others=None):
        """The coordinator (first contact) bumps its own counter past the context and past every counter it has issued for the key. `others`: which other contacts answered."""
        c = self.contacts(key)
        if not c: return None
        (coord, ci), rest = c[0], c[1:]
        if others is not None: rest = [t for t in rest if t[0] in others]
        clock = dict(ctx or {})
        clock[coord] = max(clock.get(coord, 0), self.issued.get((coord, key), 0)) + 1
        self.issued[(coord, key)] = clock[coord]     # a coordinator never reissues a counter, even after it handed its hints back
        self.log.append((key, dict(clock), value))
        self._store(coord, ci, key, clock, value)
        for hd, it in rest: self._store(hd, it, key, clock, value)
        return clock if 1 + len(rest) >= self.w else None     # a failed put is NOT rolled back: copies already written stay

    def get(self, key, responders=None, repair=True):
        c = self.contacts(key)
        got = c[:self.r] if responders is None else [t for t in c if t[0] in responders]
        if len(got) < self.r: return None
        seen = [v for hd, _ in got for v in self.data[hd].get(key, [])]
        if self.read_hints: seen += [(cl, val) for hd, _ in got for it, k, cl, val in self.hints[hd] if k == key]
        versions = reconcile(seen)
        if repair:                                            # read repair: outstanding replies bring stale home nodes up to date
            for hd, it in c:
                if hd == it: self.data[hd][key] = reconcile(self.data[hd].get(key, []) + versions)
        return versions, merge_clock([cl for cl, _ in versions])

    def fail(self, x): self.up.discard(x)
    def heal(self, x): self.up.add(x)

    def deliver_hints(self):
        for s in self.nodes:
            if s not in self.up: continue
            keep = []
            for it, key, clock, value in self.hints[s]:
                if it in self.up: self.data[it][key] = reconcile(self.data[it].get(key, []) + [(clock, value)])
                else: keep.append((it, key, clock, value))
            self.hints[s] = keep
```

**Strict quorum.** The check enumerates, for N from 1 to 5 and every R and W, every set of acknowledging nodes (the coordinator plus W-1 others) against every set of R responders. When R + W > N, no read set misses the write, in all of them; when R + W is at most N, some pair does. For (3, 2, 2) the three read pairs all meet the acknowledged pair; for (3, 1, 1) two of the three single-node reads miss. This is the overlap argument and it is exact, but it needs both sets drawn from the same N nodes.

**Sloppy quorum.** Take N = 3, R = W = 2, the first home node A down, and a write that stands in a fourth node D for it. The write is acknowledged by the coordinator B and one more node: C or the stand-in D. If it was C, B and C both hold a real copy and every read pair meets them. If it was D, only B holds a real copy and D holds a hint. Two reads then miss it, depending on when they happen.

- **A has come back, hints not yet delivered.** The read set is the first three healthy nodes, {A, B, C}. D is no longer asked, and the pair {A, C} sees nothing: C never took the write. Reading hints would change nothing.
- **A is still down.** The read set is {B, C, D}, the same three nodes the write used, which is the case the overlap rule is supposed to cover. The pair {C, D} misses the write if D does not serve its hint. The paper says reads and writes use the first N healthy nodes, which includes D, but not whether D answers from its hint store; the model's default is that it does not, and with `read_hints=True` this miss disappears.

The check enumerates all 6 combinations of acknowledger and responder pair in each case: **1 of 6 acknowledged writes is missed, with R + W > N**, both after A returns and (in the model's default) while it is down. With hints served, the while-down case misses 0 of 6 and the after-return case still 1 of 6. After `deliver_hints` the enumeration misses none. With a strict quorum and the same failure the write needs both live home nodes, and no read misses it.

So the honest statement is: **a sloppy quorum guarantees durability on W nodes somewhere, not an overlap with later reads.** The paper says as much in its own terms: it uses the sloppy quorum to keep reads and writes from failing during temporary failures. Cassandra's documentation, read for this lesson, lists a consistency level ANY where the coordinator may store a hint instead of a replica write, the same trade in another product. Two consequences the model also pins: **a put that reaches fewer than W nodes returns failure yet the copies it wrote are not rolled back** (the model's choice; the paper does not say), so a "failed" write can appear later; and **W = 1 accepts a write while a single node is up**, the paper's always-writable end, with a durability window it names itself.

---

## 6. Deep Dive 2: Three Repairs for Three Failure Lengths

**Read repair** (paper, section 5): after a read returns, the coordinator waits briefly for outstanding replies and, if any replica returned a stale version, writes the newest to it. The check makes a home node miss a write, shows a read without repair leaves it stale, and a read with repair brings it up to date.

**Hinted handoff**: the stand-in keeps the replica with the intended node's name, scans periodically and hands it back when the node returns; then it may delete its copy (paper, section 4.6). Its limits: hints live on a stand-in that can fail first, they take space there, and delivery needs a scan; this lesson's section 3 shows the store is bounded by the node's key count. The paper itself says hinted handoff works best when churn is low and failures are transient.

**Anti-entropy with Merkle trees** covers permanent loss and anything hints missed. A Merkle tree is a hash tree whose parents hash their children and whose leaves are hashes of the values of individual keys (paper; the code below lets each leaf cover a hash bucket of keys, this lesson's simplification); two replicas compare roots, equal roots mean nothing to do, and otherwise they descend only into children whose hashes differ (paper, section 4.7). The paper keeps one tree per key range a node hosts and notes the drawback: when membership changes, many ranges change and their trees must be recomputed, which its later fixed-partition scheme addresses. Here:

```python
def bucket(key, leaves=LEAVES): return h(key) % leaves

def _sha(s): return hashlib.sha1(s.encode()).hexdigest()

def _vh(versions): return _sha(repr(sorted((sorted(c.items()), v) for c, v in versions)))

def build_tree(store, leaves=LEAVES):
    """tree[0] is the root level; tree[-1] holds one hash per bucket. leaves must be a power of two."""
    assert leaves > 0 and leaves & (leaves - 1) == 0
    groups = [[] for _ in range(leaves)]
    for k, v in store.items(): groups[bucket(k, leaves)].append((k, _vh(v)))
    level = [_sha(repr(sorted(g))) for g in groups]
    tree = [level]
    while len(tree[0]) > 1:
        t = tree[0]
        tree.insert(0, [_sha(t[i] + t[i + 1]) for i in range(0, len(t), 2)])
    return tree

def diff_buckets(ta, tb):
    """Descend from the roots, comparing children only under differing parents. Returns (buckets, hashes compared)."""
    compared, frontier = 1, ([0] if ta[0][0] != tb[0][0] else [])
    for lvl in range(1, len(ta)):
        nxt = []
        for i in frontier:
            for c in (2 * i, 2 * i + 1):
                compared += 1
                if ta[lvl][c] != tb[lvl][c]: nxt.append(c)
        frontier = nxt
    return frontier, compared

def _sync(self, a, b):
    shared = lambda x, y: {k: v for k, v in self.data[x].items() if {x, y} <= set(self.preference_list(k)[:self.n])}
    va, vb = shared(a, b), shared(b, a)
    buckets, _ = diff_buckets(build_tree(va), build_tree(vb))
    for k in set(va) | set(vb):
        if bucket(k) in buckets:
            merged = reconcile(va.get(k, []) + vb.get(k, []))
            self.data[a][k] = self.data[b][k] = merged
Dynamo.sync = _sync
```

The check compares `diff_buckets` against a bucket-by-bucket brute force on 400 random store pairs (1 to 64 leaves, a missing key on either side, a changed value, an extra sibling), including bucket numbers above 9 so a bug that orders them as strings cannot hide. It asserts the cost bound: with d differing buckets and L leaves, at most `1 + 2 d log2(L)` hashes are compared, and equal stores cost exactly one. It also asserts that `sync` restores a lost replica for every key and never gives a key to a node that is not one of its replicas.

**The whole system under failure.** The fuzz runs 120 seeds of 80 random steps on 7 nodes (puts with stale or fresh contexts and partial acknowledgements, reads with and without repair, nodes failing and healing, hint delivery), half of them sloppy. At the end every node heals, hints are delivered and anti-entropy runs. It asserts, for every key: every home replica holds exactly the reference merge of every version ever written; no two writes got the same clock (the coordinator must remember the counters it has issued, because a stand-in that handed its hints back no longer holds its own earlier write; the fuzz found two collisions of this kind in the first drafts of the model); every acknowledged write is still descended from by a surviving version; and no hint is left. It found no case where an acknowledged write is lost once repairs have run.

---

## 7. Deep Dive 3: Siblings and the Shopping Cart

The paper's cart is its example of business-logic reconciliation: both "add to cart" and "delete" are puts; when versions diverge, the client merges them, and with that merge an add is never lost, **but deleted items can resurface**. Concurrent clients make this concrete: both read version v1 = {book, pen}; one removes the book, the other adds a lamp. The versions are concurrent, so the store returns both. A union merge gives {book, pen, lamp}: the removal is undone.

A fix is an observed-remove set: each add carries a unique tag, and a remove tombstones the tags it has seen. Merge is the union of adds and the union of tombstones.

```python
class Cart:
    """Observed-remove set: a remove kills the adds it has seen; an add it has not seen survives."""
    def __init__(self, adds=(), removed=()): self.adds, self.removed = frozenset(adds), frozenset(removed)
    def add(self, item, tag): return Cart(self.adds | {(item, tag)}, self.removed)
    def remove(self, item): return Cart(self.adds, self.removed | {t for i, t in self.adds if i == item})
    def merge(self, o): return Cart(self.adds | o.adds, self.removed | o.removed)
    def items(self): return {i for i, t in self.adds if t not in self.removed}

def union_merge(item_sets): return set().union(*item_sets)      # the paper's cart merge
```

The check runs the scenario (union: book, pen, lamp; observed-remove: pen, lamp), a concurrent add of the same item with a new tag surviving a remove it did not see (an add wins over an unobserved remove), and 400 random triples for commutative, associative and idempotent merge, with the visible items compared against a separate statement of the rule. The cost, which the code makes visible: tombstones only grow, so a real system must expire them, and it must pick the tag uniquely (a client id and a counter). The convergence argument for such types is in Real-Time Collaborative Whiteboard & Docs. This is this lesson's design; the paper describes union merging only.

---

## 8. Membership, Coordination and Gossip

**Membership** is explicit: an administrator issues a join or leave; the node that served it records the change with its time, and a gossip protocol, each node contacting a random peer every second, reconciles the histories (paper, section 4.8.1). Seeds, nodes known to every node, stop two rings from forming (4.8.2). **Failure detection is local:** a node treats a peer as failed when it does not answer, and retries it later; the paper says an early global detector was dropped because explicit joins and leaves made it unnecessary (4.8.3). The paper also admits a limit: the full-membership model works for a couple of hundred nodes and not easily for tens of thousands.

How fast is "every second, a random peer"?

```python
import random

def gossip_rounds(n, rng):
    """Synchronous push-pull: each round every node picks a random other node; if either knows the news, both do."""
    know, rounds = {0}, 0
    while len(know) < n:
        rounds += 1
        new = set(know)
        for i in range(n):
            j = rng.randrange(n - 1); j += j >= i
            if i in know or j in know: new |= {i, j}
        know = new
    return rounds
```

The check simulates synchronous push-pull rounds: with 16 nodes the news reaches everyone in 4.1 rounds on average over 200 runs, with 200 nodes in 7.4 rounds (200 runs), with 2,000 nodes in 10.0 rounds (30 runs) (simulation, illustrative; one round stands for one second only if rounds are synchronous, which real gossip is not). It asserts the mean is at least 0.8 log2(n) rounds and no run exceeds 4 log2(n): spread takes logarithmically many rounds, not one.

**Who coordinates.** Requests go through a load balancer to any node: any node can coordinate a read, and a write is forwarded to a node in the key's preference list (which creates the new version stamp); or a partition-aware client library sends them directly (paper, 4.5, 6.4). Table 2 of the paper, a 24-hour comparison, reports 99.9th-percentile read latency of 68.9 ms server-driven against 30.4 ms client-driven, and averages of 3.9 and 1.55 ms; the client polls a random node for membership every 10 seconds, so it can hold a stale view for that long. The paper also lets any of the top N nodes coordinate writes, choosing the node that answered the previous read fastest, to cut tail latency and improve the chance of read-your-writes.

---

## 9. Failure Modes

| What breaks | What you see | Defence |
|---|---|---|
| a home node down | sloppy write lands on a stand-in; a read before handoff can miss it (1 of 6 above) | hinted handoff; reads that need the latest must wait out repair, or use R = N |
| stand-in space | hints pile up on the stand-ins, one per write if not deduplicated | keep the newest version per key; bound the hint store; fall back to anti-entropy |
| stand-in dies before handing back | the replica is lost | anti-entropy (paper: hints can become unavailable) |
| concurrent writers | siblings | client merge; busy automated clients drove most divergence in the paper |
| union merge of a cart | deleted items return | observed-remove merge, with tombstone expiry |
| a failed put | the copies it wrote remain | idempotent clients; treat "failed" as "unknown" |
| background repair load | foreground latency rises | the paper throttles background work with an admission controller driven by foreground latency |
| whole data centre lost | a preference list in one site loses its replicas | preference lists spread over data centres (paper) |

---

## 10. What Real Systems Did

- **Dynamo** (DeCandia et al., SOSP 2007, read 2026-11-27): N = 3 typical; (3, 2, 2) common; 99.9th percentile around 200 ms in the production graph, an order of magnitude above the mean; a 24-hour sample of the cart service (Time, Clocks and Ordering already uses this measurement) saw exactly one version in 99.94% of requests, two in 0.00057%, three in 0.00047%, four in 0.00009% (these printed figures sum to 99.9411%, not 100%; the paper does not explain the gap, so treat them as the paper's approximate figures). It reports 99.9995% of requests answered successfully with no data loss in its first two years of use, and a write buffer in memory cut the 99.9th percentile by a factor of 5 at the price of durability, mitigated by having one replica write durably. Its storage engines included Berkeley DB Transactional Data Store, used by most production instances.
- **Cassandra** (documentation, read 2026-11-27, architecture page only): describes its architecture alongside the Dynamo paper, lists read repair, hinted handoff and Merkle-tree repair as its convergence mechanisms, and adds sub-range and incremental repair that the paper does not have. Its consistency levels include QUORUM (n/2 + 1) and ANY. Nothing else about its current behaviour is claimed.

---

## 11. Pitfalls Checklist

1. **"R + W > N means strongly consistent."** Only for strict quorums over the same N nodes, with no concurrent writes; the check shows a miss with R + W > N under a sloppy quorum.
2. **Assuming a stand-in's hinted replica answers reads.** The paper does not say; decide, and test both ways (the check does).
3. **Treating a failed put as not written.** Copies remain.
4. **Merging siblings by union.** Deleted items return.
5. **Two writes with the same clock.** The coordinator must go past what it holds.
6. **Comparing Merkle buckets as strings** ("10" before "2") or hashing only the root.
7. **Assuming independent replica failures** when replicas share a rack.
8. **A hint log with one entry per write.** It grows without bound; keep the newest version per key.
9. **Quoting the paper's percentages as a distribution.** They do not sum to 100%.

---

## Drills

1. With N = 3, why does (R, W) = (2, 2) always read an acknowledged write when nothing has failed, and (1, 1) not? Give the count from the enumeration.
2. Explain the 1-in-6 miss with R + W > N: who acknowledged, who answered, and what changes after hint delivery.
3. Why does the coordinator wait for W-1 other acknowledgements, and what happens to the copies of a put that got fewer?
4. Compute the chance a (3, 2, 2) write is slow when each replica is slow 1% of the time, and compare with W = 3.
5. A node is down for 90 minutes in the example cluster. How large is the hint store with and without deduplication by key, and why does anti-entropy afterwards move about the same keys? State the assumption on how writes spread.
6. Two replicas of a million keys differ in 100 keys. How many hashes does the Merkle comparison exchange at most, and what drives that number?
7. Why does a union merge of two cart versions resurrect a deleted item, and what does the observed-remove cart store to prevent it?
8. Why does the paper's gossip survive a couple of hundred nodes and not tens of thousands, and what does the simulation say about rounds as nodes grow?

---

## Homework

1. Run `sy69_check.py` on this file. Make `put` use the ctx counter only (not what the coordinator holds) and find the failing assertion.
2. Run `acked_then_read(3, 2, 2, sloppy=True, down=(0,), heal_before_read=False)` with and without `read_hints=True` and explain the change from 1 of 6 to 0 of 6. Then run it with A healed first and explain why nothing changes.
3. Add tombstone expiry to `Cart` and write a check that finds the case it gets wrong (an old replica returning).
4. Implement fixed partitions (as in Caching Patterns and Consistent Hashing) with one Merkle tree per partition and measure how many trees change when a node joins.

---

## Sources

All read 2026-11-27. The model, the figures marked *assumed*, the cart and the simulations are this lesson's own.

- DeCandia et al., *Dynamo: Amazon's Highly Available Key-value Store*, SOSP 2007, allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf. Read sections 1 to 7 including Tables 1 and 2 from text extraction; figures (graphs) not examined.
- Apache Cassandra documentation, Dynamo architecture page (cassandra.apache.org/doc/latest/cassandra/architecture/dynamo.html): read the passages on convergence mechanisms and consistency levels only.

## Further reading (not consulted)

Cassandra's hints and repair pages, Riak's documentation, the DynamoDB paper and documentation (a different system from the paper's), the Merkle-tree original, the gossip failure-detector paper the Dynamo paper cites. None were read, so no claim is made about them.

*Last reviewed: 27 November 2026.*
