# Lesson 67 — Case Study: Content Delivery Network

> **Priority:** ★★★★☆ (proposed; the curriculum data holds the final rating) — a CDN appears in every "serve images, video or a global site" design, and the weak answers stop at "put a cache near the user" without saying how a request finds a cache, what is allowed into it, or what protects the origin.
>
> **Study time:** 85 minutes. **Do this after:** Caching Patterns and Consistent Hashing; Networking, TLS & Load Balancing; Distributed Cache (Memcached/Redis); Overload, Load Shedding and Cascading Failures.
>
> **Level:** extended.

A CDN is thousands of caches placed close to users, plus the machinery that sends each user to a good one, decides what each cache may keep, and stops the herd of misses from reaching your servers. The ring and rendezvous hashing belong to Caching Patterns and Consistent Hashing; the cache-stampede basics to Distributed Cache (Memcached/Redis). This lesson links to them and builds the CDN-specific parts as a small model checked in `test/lesson_code/sy67_check.py` against independent references: the HTTP freshness rules, a cache that refuses one-hit wonders, per-object server selection, stable assignment of users to clusters, and the origin load of a two-tier cache. Capacity numbers come from `capacity_check_h.py`. The one engineering source read in depth is Akamai's own paper (section 10); every other CDN's internals are outside this lesson.

---

## 1. Mental Model

> **A CDN turns "the origin answers every request" into "the origin answers each object about once per cache lifetime". Three decisions make that true: route the user to a cache that probably has the object, admit into the cache only what will be asked for again, and let exactly one request per object travel upstream when many miss at once.**

- **Hit ratio is leverage on the origin.** Origin traffic is the miss fraction; going from 95% to 90% hits doubles it (section 3).
- **Routing is a matching problem, not a nearest-server lookup.** Proximity, cluster capacity and cost all matter, and the answer changes every few seconds.
- **A cache is also a write-heavy disk.** Most objects are requested once; storing them wastes space and wears disks (section 6).
- **Freshness is a contract written by the origin,** in headers, and a shared cache must obey it; purging is a separate, weaker mechanism.
- **Tiers and coalescing give origin load that does not grow with the number of edges** (section 7).

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "serve static assets or video globally" | edge caches, DNS-based steering to a cluster, consistent placement inside the cluster |
| "a flash crowd on one object" | serve it from more than one server in the cluster; coalesce misses (sections 5 and 7) |
| "how does the user reach the nearest server" | DNS answers chosen per resolver or client subnet, balanced against cluster capacity (section 5) |
| "what do we cache" | what the origin's headers allow, and only objects likely to be requested again (section 6) |
| "the origin is overloaded by cache misses" | a parent tier plus request coalescing; stale-while-revalidate (sections 6 and 7) |
| "we published a wrong file, remove it everywhere" | purge fan-out, with a versioned URL as the reliable fix (section 7) |
| "dynamic or personalised pages" | the CDN as a front end over optimised paths to the origin, not caching (section 8) |

---

## 3. Requirements and Capacity

**Functional.** Serve HTTP objects from the edge; honour the origin's cache headers; revalidate and refill from upstream; steer users by DNS; purge on request. **Non-functional.** Low latency and high availability from many networks; origin protected from bursts; cost per delivered byte low. **Out of scope:** TLS termination detail, video packaging, billing.

**Capacity estimate.** Inputs marked *assumed* are this lesson's. Inputs marked *paper* are figures printed in the Akamai paper (section 10), used as inputs. Every result is reproduced by `capacity_check_h.py`.

| Input | Value |
|---|---|
| peak delivered traffic | 20 Tbps *(assumed)* |
| edge byte hit ratio | 95% *(assumed)*; a parent tier answers 80% of edge misses *(assumed)* |
| server | 40 Gbps network port, run at 50% *(assumed)*; average object 500 KB *(assumed)* |
| Bloom filter sizing | 40 million objects per server, 0.1% false positives *(paper's worked example)* |
| steering | DNS answers cached for 20 s *(assumed)*; assignments recomputed every 10 to 30 s *(paper)* |

| Result | Arithmetic | Value |
|---|---|---|
| origin traffic with edge hits only | 20 Tbps x (1 - 0.95) | 1 Tbps |
| with a parent tier | 1 Tbps x (1 - 0.8) | 0.2 Tbps |
| origin traffic if hits fall to 90% | 20 x 0.10 | 2 Tbps: twice as much |
| servers for the peak | 20 Tbps / (40 Gbps x 50%) | 1,000 |
| requests per second | 20 Tbps / (500 KB x 8) | 5 million, 5,000 per server |
| Bloom filter for 40 million objects | m = -n ln p / (ln 2)^2 | 575.1 million bits, 68.6 MB, 10 hash functions |
| time to move load off a cluster, worst case | recompute interval + DNS time-to-live | up to 30 s + 20 s = 50 s before new lookups stop arriving |

Five conclusions. **The origin sees the miss rate:** 1 Tbps at 95% hits, so one point of hit ratio at this scale is 0.2 Tbps. **A tier above the edge is the cheapest cut:** 0.2 Tbps. **The filter is tiny:** 68.6 MB against the disk it protects. **Steering is slow by design:** 50 seconds is the worst case for DNS-based traffic shifting under these assumptions, for resolvers that honour the lifetime; some hold answers longer (unmeasured here). **Per-server request rate is modest;** the constraint is bandwidth and disk writes, not requests.

---

## 4. Request Flow and Data Model

```
client -> resolver -> CDN authoritative DNS: pick a cluster for this client group    (section 5)
       -> cluster DNS / hashing: pick the servers for this object                    (section 5)
       -> edge server: fresh copy? serve.  stale? revalidate or serve stale (rules)   (section 6)
          miss -> peers in the cluster, then a parent cluster, then the origin        (section 7)
```

The paper describes this order: the edge asks the other servers in its cluster first, then a parent cluster, then the origin. Cache entry: `key, headers (Cache-Control, Date, Expires, Last-Modified), body, stored_at, fetch_request_time`.

---

## 5. Deep Dive 1: How a Request Finds a Cache

**Picking a cluster.** The paper describes global load balancing: the CDN's authoritative name server answers based on the resolver's address (or the client subnet the resolver passes), choosing a cluster using a variant of the stable marriage algorithm. Groups of clients ("map units", a set of nearby addresses plus a traffic class such as video or web) rank clusters by predicted performance; clusters rank the groups they prefer to serve (contract terms, cost) and have a capacity. The paper reports tens of millions of map units against thousands of clusters, and that assignments are recomputed every 10 to 30 seconds because congestion and flash crowds change faster than that. Its real version has integer demands and trees of resource constraints; the model below is the simplest honest core, the unit-proposing Gale-Shapley algorithm with cluster capacity in slots and partial preference lists.

```python
import hashlib, math
from collections import OrderedDict

def h(s): return int(hashlib.md5(s.encode()).hexdigest(), 16)

def stable_assign(unit_prefs, cluster_prefs, cap):
    """Unit-proposing deferred acceptance. A cluster only accepts units on its list; each unit has demand 1 (a simplification)."""
    rank = {c: {u: i for i, u in enumerate(p)} for c, p in cluster_prefs.items()}
    nxt, held, free = {u: 0 for u in unit_prefs}, {c: [] for c in cluster_prefs}, list(unit_prefs)
    while free:
        u = free.pop()
        while nxt[u] < len(unit_prefs[u]):
            c = unit_prefs[u][nxt[u]]; nxt[u] += 1
            if u not in rank[c]: continue                      # not acceptable to the cluster
            held[c].append(u)
            if len(held[c]) <= cap[c]: break
            worst = max(held[c], key=lambda x: rank[c][x]); held[c].remove(worst)
            if worst != u: free.append(worst); break           # someone is bumped; if it was u, u tries its next choice
    out = {u: None for u in unit_prefs}
    for c, us in held.items():
        for u in us: out[u] = c
    return out
```

The check runs the paper's figure 2 example (M1 to C2, M2 to C1, M3 to C3), and 300 random instances with partial lists and capacities of 1 to 3 against **brute-force enumeration of every assignment**: the output is always stable (no unit and cluster both prefer each other to what they have), within capacity, and every unit gets the best cluster it can have in any stable assignment, which the paper calls map-unit-optimal and links to its aim of maximising client performance. What stability buys: nobody can defect to a pair that would both be happier; what it does not give: minimum total latency.

**Picking servers inside a cluster.** Placement by consistent hashing is the subject of Caching Patterns and Consistent Hashing. What is new here, from the paper: a single very popular object (a flash crowd) cannot be served by one server, so it is mapped to k servers, where k grows with popularity. The naive way is the k clockwise neighbours on one ring; the weakness is that two popular objects hashing near each other share servers. The paper's way is a separate random ordering of the servers for each object, and it keeps the consistent-hashing property: removing a server moves only the objects that were on it. The code below gets the same effect by ranking servers by a hash of the pair (this is the idea of rendezvous hashing from the earlier lesson; the paper describes its own per-object mapping, so the equivalence is this lesson's reading).

```python
def servers_for(obj, servers, k):
    """Each object gets its own order of the servers; its k servers are the first k."""
    return sorted(servers, key=lambda s: h(obj + '|' + s))[:k]

def ring_servers(obj, servers, k):
    """One shared ring: the k servers clockwise from the object's position."""
    ring = sorted(servers, key=h)
    start = next((i for i, s in enumerate(ring) if h(s) >= h(obj)), 0)
    return [ring[(start + j) % len(ring)] for j in range(min(k, len(ring)))]
```

The check asserts, over 400 objects and four removed servers, that with a server removed every object's list changes only if it contained that server, and then only by that server being replaced by the next in its order; adding a server only ever adds that server. For overlap it uses 40 evenly spaced servers and two popular objects with k = 8 servers each: on the shared ring, the probability that they share at least half their servers (4 or more) is exactly 9 of 40, **22.5%** (their start positions must be within 4; the paper states this probability only as of order k over n, about 20% here, and its exact value depends on the evenly spaced ring assumed); with independent per-object orders the exact (hypergeometric) probability is **3.65%**, and a simulation of 6,000 object pairs agrees with both within sampling error. Both have the same mean overlap, 1.6 servers (k squared over n), as the paper states: the difference is in the tail, not the average. The ideal evenly spaced ring is an assumption; a real ring with random positions is lumpier.

**Grouping by customer.** The paper groups all of a customer's objects under one serial number and hashes the serial number, not each object, so that one browser connection serves a page's many objects from one server (opening a connection and ramping it up is paid once). The trade is coarser load spreading, which the popular-object mapping then relieves.

---

## 6. Deep Dive 2: What May Be Cached, and What Should Be

### Freshness: the HTTP rules, as code

RFC 9111 defines when a stored response can be reused without contacting the origin. A response is fresh while its age is below its freshness lifetime. The lifetime is the first of: `s-maxage` (shared caches only), `max-age`, `Expires` minus `Date`; with none of these a cache may use a heuristic, and the RFC suggests no more than a fraction of the time since `Last-Modified`, typically 10%. Caches are encouraged to treat invalid freshness information as stale. The age starts from the apparent age (response time minus `Date`, floored at zero) or the corrected age value (the `Age` header plus the response delay); the RFC allows the corrected value alone when every cache on the path is HTTP/1.1 and the larger of the two otherwise, and the code takes the conservative larger one; the time resident since is then added.

```python
def freshness_lifetime(cc, date, expires=None, last_modified=None, shared=True, heuristic=False):
    """RFC 9111 section 4.2.1 and 4.2.2. cc maps directive -> string value; times are seconds."""
    num = lambda v: int(v) if v is not None and v.isdigit() else None       # '-5', '1.5', 'abc' are invalid: stale
    if shared and 's-maxage' in cc: return num(cc['s-maxage']) or 0
    if 'max-age' in cc: return num(cc['max-age']) or 0
    if expires is not None: return max(0, expires - date)
    if heuristic and last_modified is not None: return (date - last_modified) // 10
    return 0

def current_age(age_value, date_value, request_time, response_time, now):
    """RFC 9111 section 4.2.3."""
    apparent = max(0, response_time - date_value)
    corrected = age_value + (response_time - request_time)
    return max(apparent, corrected) + (now - response_time)

def serve_decision(lifetime, age, swr=0, sie=0, origin_error=False, must_revalidate=False):
    """fresh iff lifetime > age (equal is stale). RFC 5861: serve stale while revalidating for swr seconds past expiry,
    or up to sie seconds past expiry when revalidation just failed."""
    if age < lifetime: return 'fresh'
    stale_by = age - lifetime
    if origin_error: return 'stale-if-error' if (not must_revalidate and stale_by <= sie) else 'error'
    return 'stale-while-revalidate' if (not must_revalidate and stale_by < swr) else 'revalidate'
```

The check holds these to hand-computed values and the RFCs' own examples: `max-age=600, stale-while-revalidate=30` serves stale at age 610 and 629 and stops at 630; `max-age=600, stale-if-error=1200` serves stale after a failed validation at age 900 and still at 1,800, and writes the error through at 1,801; an age equal to the lifetime is stale; `s-maxage` beats `max-age` in a shared cache and is ignored in a private one; `max-age` beats `Expires`; `Expires` is measured against `Date`, not against now; a `Date` in the future gives apparent age 0. The two boundaries are asymmetric because the RFC text is ("after 30 seconds" against "greater than 1800"); a product's documentation is the authority for its own edge cases. RFC 9111 also says an unsafe request (PUT, POST, DELETE) invalidates only the caches it passes through, which is why a CDN needs its own purge (section 7).

### Admission: do not store what will not come back

The Akamai paper measured one cluster of 45 servers over two days: of more than 400 million distinct objects, about 74% were requested once and 90% fewer than four times. Caching them wastes disk and writes. The paper's rule: cache an object only on its second request within a window, remembered in a Bloom filter (a bit array that never forgets a member but sometimes claims a stranger is one). As a filter fills its false-positive rate rises, so the paper keeps two: new objects go into the primary until it holds a threshold number, then it becomes the secondary and a fresh primary starts, and both are queried. In its production experiment on a cluster of about 47 servers the byte hit rate rose from about 74% to 83% and disk writes fell from an average 10,209 to 5,738 per second, 44% (the paper's figures; this lesson's simulation below is not a reproduction of them). Sizing: with n expected objects and tolerated false-positive probability p, m = -n ln p / (ln 2)^2 bits and k = (m/n) ln 2 hashes; the paper's example of 40 million objects at 0.1% gives 575.1 million bits, 68.6 MB and k = 10.

```python
def bloom_size(n, p):
    m = math.ceil(-n * math.log(p) / math.log(2) ** 2)
    return m, round(m / n * math.log(2))

class Bloom:
    def __init__(self, m, k): self.m, self.k, self.bits = m, k, bytearray((m + 7) // 8)
    def _idx(self, key):                       # double hashing from one MD5 (this lesson's choice; the paper splits one MD5 hash into k parts)
        d = hashlib.md5(key.encode()).digest()
        a, b = int.from_bytes(d[:8], 'big'), int.from_bytes(d[8:], 'big') | 1
        return [(a + i * b) % self.m for i in range(self.k)]
    def add(self, key):
        for i in self._idx(key): self.bits[i >> 3] |= 1 << (i & 7)
    def __contains__(self, key): return all(self.bits[i >> 3] >> (i & 7) & 1 for i in self._idx(key))

class SecondHit:
    """Admit on the second request within the window: two Blooms, rotated after `limit` new objects."""
    def __init__(self, m, k, limit): self.m, self.k, self.limit, self.new, self.old, self.count = m, k, limit, Bloom(m, k), Bloom(m, k), 0
    def __call__(self, key):
        seen = key in self.new or key in self.old
        if not seen:
            self.new.add(key); self.count += 1
            if self.count >= self.limit: self.old, self.new, self.count = self.new, Bloom(self.m, self.k), 0
        return seen

admit_all = lambda key: True

class EdgeCache:
    """LRU by size. `admit(key)` is consulted only on a miss; request returns True on a hit."""
    def __init__(self, capacity, admit): self.cap, self.admit, self.lru, self.used, self.writes = capacity, admit, OrderedDict(), 0, 0
    def request(self, key, size):
        if key in self.lru: self.lru.move_to_end(key); return True
        if size <= self.cap and self.admit(key):
            while self.used + size > self.cap: _, s = self.lru.popitem(last=False); self.used -= s
            self.lru[key] = size; self.used += size; self.writes += 1
        return False
```

The check holds this to an exact two-generation reference: with a filter so large it never collides, `SecondHit` makes the same admit decision as a pair of sets on 40 random streams, and the rotation is pinned (an object seen before the previous rotation is forgotten after the second). The Bloom filter has no false negatives; at the sizes the formula gives, measured false-positive rates match `(1 - e^(-kn/m))^k` and the paper's sizing example reproduces 68.6 MB and k = 10.

The simulation (illustrative: unit-size objects, a 400-object cache, 60,000 requests, popularity roughly Pareto over 800 objects) with half of all requests going to objects asked for once: admit-all hit rate **47.7%** with **31,397 writes**; second-hit **49.1%** with **116 writes** (the ceiling is 50%, since half the requests can never hit). With no one-hit wonders at all the filter only delays admission: **99.4%** against **99.1%**. So the filter pays when the stream has many one-hit wonders (a small gain in hits and a very large cut in writes) and costs a little when it has none; it is not free, and the window (the filter's rotation limit) must be long enough for the second request to arrive, or a popular-but-slow object is never cached.

---

## 7. Deep Dive 3: Protecting the Origin

**Coalescing and tiers.** When an object expires, every request that arrives before the refill completes is a miss. Without coalescing each sends its own request upstream; with coalescing one goes and the rest wait for it. With a parent tier, an edge's miss goes to the parent, which itself coalesces. The model is a TTL cache with a fetch delay:

```python
class Origin:
    def __init__(self, latency): self.latency, self.fetches = latency, 0
    def get(self, t): self.fetches += 1; return t + self.latency        # time the response is available

class TierNode:
    """A TTL cache in front of `upstream`. get(t) returns when the response is available here."""
    def __init__(self, upstream, ttl, coalesce, hop=0):
        self.up, self.ttl, self.coalesce, self.hop, self.fresh_until, self.inflight = upstream, ttl, coalesce, hop, -1, []
    def get(self, t):
        for d in [d for d in self.inflight if d <= t]:                  # a finished fetch starts a fresh period
            self.fresh_until = max(self.fresh_until, d + self.ttl); self.inflight.remove(d)
        if t < self.fresh_until: return t                               # hit
        if self.inflight and self.coalesce: return min(self.inflight)   # wait for the fetch already under way
        done = self.up.get(t) + self.hop
        self.inflight.append(done)
        return done
```

The check drives one object with one request per second per edge for 120 seconds, a 10 s lifetime and a 2 s origin fetch. One edge: 10 origin fetches. Five edges without coalescing and no parent: 100 fetches (two per cycle each); with coalescing: 50. With **50 edges** and no parent: 500 fetches; with a coalescing parent: **10 fetches** (**10 fetches** with 1 edge too: the origin load does not depend on how many edges there are), and the parent's own coalescing is what matters: a parent that does not coalesce hands the herd back (over 100 fetches). The edges here are synchronised, the worst case for a thundering herd; real edges drift. RFC 5861's `stale-while-revalidate` adds a second defence: serve the expired copy while one request refreshes it, so no user waits; its window must be long enough that a request actually arrives inside it, the RFC notes.

**Purge.** A cache only invalidates what a request passes through (RFC 9111), so a purge must be sent to every cache that might hold the object, and caches are numerous (the paper counts over 170,000 edge servers in its CDN). No purge latency figure was read, so none is given. Three practical answers: **version the URL** (`/app.3f9c.js`) so nothing needs purging, which also makes long lifetimes safe; **purge by key or tag** through the CDN's API for what cannot be versioned; and give objects a short lifetime plus `stale-if-error` so a stale copy is bounded. A purge is a request that can fail or arrive late: design so that a missed purge is bounded by the lifetime.

---

## 8. Dynamic Content: The Overlay

Not everything is cacheable: personalised pages, applications, live streams. The paper's answer is to use the CDN's servers as relays in an overlay network between the edge and the origin: several candidate paths are measured and the best are chosen, multiple paths give redundancy, and the CDN can use optimised transport between its own nodes. It frames path construction as a multicommodity-flow problem and also describes electing leaders in various contexts, which this lesson does not cover. A learner's version: if the response cannot be cached, the CDN still helps by terminating the connection near the user and keeping a warm, optimised connection to the origin.

---

## 9. Failure Modes

| What breaks | What you see | Defence |
|---|---|---|
| a flash crowd on one object | one server saturated | map the object to k servers by popularity; coalesce |
| a cluster overloaded or lost | clients keep arriving for up to a DNS lifetime | recompute assignments often; short DNS lifetimes; capacity headroom elsewhere |
| origin down | every miss errors | `stale-if-error`, longer lifetimes while healthy |
| expiry herd | origin spike on every TTL | coalescing, a parent tier, stale-while-revalidate |
| one-hit wonders | disk writes high, hit rate low | second-hit admission |
| wrong file published | stale copies worldwide | versioned URLs; purge as a bounded backstop |
| dropped cache headers | everything uncacheable, or heuristically cached | explicit `Cache-Control` on every response |
| popular objects collide on shared servers | hot spots | per-object server order, not a shared ring |

---

## 10. What Real Systems Did

- **Akamai** (Maggs and Sitaraman, *Algorithmic Nuggets in Content Delivery*, an article submitted to ACM SIGCOMM Computer Communication Review, which a search listing dates to 2015; the copy read says in its own header that it is an editorial note and was not peer reviewed; read 2026-11-27): the DNS-then-cluster-then-server request path; stable-marriage global load balancing recomputed every 10 to 30 seconds over tens of millions of map units and thousands of clusters; consistent hashing with per-object mapping for popular objects and customer serial numbers; the Bloom filter admission experiment above; overlay routing for uncacheable content. It states the CDN had over 170,000 edge servers in over 1,300 networks in 102 countries and served 15 to 30% of web traffic, as of the paper.
- **HTTP caching** (RFC 9111, June 2022, and RFC 5861, May 2010, read 2026-11-27): the freshness, age, stale and invalidation rules coded above.
- **Not read:** Cloudflare, Fastly, CloudFront and Netflix Open Connect documentation, Akamai's 2010 platform paper (the copy was blocked), and any purge-latency measurement. The sections on tiers, coalescing and purge describe the general approach, not any named product.

---

## 11. Pitfalls Checklist

1. **Treating the CDN as a single global cache.** It is thousands of independent caches; a purge or an update reaches each separately.
2. **`age >= lifetime` for fresh.** A response whose age equals its lifetime is stale.
3. **Letting a shared cache keep what `private` or `no-store` forbids,** and ignoring `s-maxage` where it applies.
4. **Caching one-hit wonders.** Disk writes and evictions for nothing.
5. **No coalescing at the parent.** The herd just moves up a tier.
6. **Hashing every object independently** and losing one connection per page; or hashing only by customer and losing spread for a hot object.
7. **Trusting a purge.** Bound staleness with lifetime and versioned URLs.
8. **Steering by nearest only,** ignoring cluster capacity.
9. **Quoting the paper's one cluster as a general hit-rate gain.** It is one experiment.

---

## Drills

1. Why does origin traffic double when the edge hit ratio falls from 95% to 90% at 20 Tbps, and how much does a parent tier that answers 80% of misses recover?
2. A response has `max-age=600, stale-while-revalidate=30`. What does a cache do at age 599, 600, 629, 630?
3. A response has `max-age=600, stale-if-error=1200` and the origin returns a 500 when the cache revalidates at age 900. What is served? At age 1801?
4. Two objects each map to 8 of 40 servers. Why is a shared ring more likely than independent per-object orders to give them four or more servers in common, and what are the two probabilities?
5. Explain what makes an assignment of client groups to clusters "stable", and why that is not the same as lowest latency.
6. A cluster holds 400 million distinct objects a day and 74% of them are requested once. What does the second-hit rule change, and what does it cost an object requested twice a day?
7. Fifty edges all refresh an object at once. Compare the origin requests with no parent, a parent that does not coalesce, and one that does.
8. You published a file with the wrong content and it has a one-day `max-age`. Which three things do you do?

---

## Homework

1. Run `sy67_check.py` on this file. Change `age < lifetime` to `age <= lifetime` and find which assertion fails; then make `s-maxage` apply in private caches.
2. Extend `stable_assign` to integer demands and capacities in the simplest way and find a case where the output is no longer stable; read the paper's section 2.2 to see how it handles that.
3. Add a third rule to `SecondHit`: cache immediately if the object is small. Measure the hit rate on the check's workload.
4. Add a purge command to the tier model with a propagation delay and measure how many requests are served stale.

---

## Sources

All read 2026-11-27. The model, the figures marked *assumed* and the simulations are this lesson's own.

- Bruce M. Maggs and Ramesh K. Sitaraman, *Algorithmic Nuggets in Content Delivery* (a copy hosted at courses.cs.duke.edu/spring16/compsci590.6/CCRpaper.pdf, an editorial note submitted to ACM SIGCOMM Computer Communication Review and marked not peer reviewed). Read sections 1 to 5 (introduction, stable allocations, consistent hashing, Bloom filters, overlay routing) in text extraction; the leader-election section and figures were not read closely.
- R. Fielding, M. Nottingham, J. Reschke, *HTTP Caching*, RFC 9111 (June 2022): read sections 4.2 to 4.4 and the `s-maxage` definition. M. Nottingham, *HTTP Cache-Control Extensions for Stale Content*, RFC 5861 (May 2010): read in full.

## Further reading (not consulted)

Akamai's 2010 platform paper (the copy fetched was an access-denied page), Cloudflare, Fastly and CloudFront documentation, Netflix Open Connect, the Maglev paper beyond what Caching Patterns and Consistent Hashing cites, any measured purge latency. No claim is made about them.

*Last reviewed: 27 November 2026.*
