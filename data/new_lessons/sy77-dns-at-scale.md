# Lesson 77 — Case Study: DNS at Scale

> **Priority:** ★★★☆☆ (proposed; the curriculum data holds the final rating) — every request starts with a lookup, and the TTL is the one dial that trades how fast you can move traffic against how much load your name servers carry.
>
> **Study time:** 55 minutes. **Do this after:** Caching Patterns and Consistent Hashing; Content Delivery Network; Overload, Load Shedding and Cascading Failures.
>
> **Level:** extended.

DNS is the largest cache hierarchy most engineers use without designing, and "how would you fail traffic over to another region" quietly assumes it. This lesson builds a caching resolver as a small model: positive and negative caching, a TTL clamp, serving stale answers during an outage, and merging of simultaneous misses. The model is checked in `test/lesson_code/sy77_check.py` against a byte-level packet parser, hand-computed boundary cases and a Poisson simulation; capacity numbers come from `capacity_check_j.py`. It is not a tour of record types or of any provider's product (no operator's engineering material was read; see Sources).

---

## 1. Mental Model

> **DNS scales because answers are cached with a lifetime chosen by the owner of the data, not by the reader. Load on the authoritative servers is set by how many caches there are and how long they hold an answer; the time to move traffic is set by the same number.**

- **A resolver asks upstream once per cycle:** a cache hit lasts the TTL; the next miss comes whenever the next client happens to ask. For one name at one resolver that gives `rate = q / (1 + q·TTL)` upstream queries per second for a client rate of `q` (section 5).
- **The same TTL is your failover time.** Anyone who cached the old answer keeps using it until it expires. Lowering the TTL is not free, because it multiplies authoritative load (section 3).
- **Caching helps the head of the distribution most; the tail still mostly misses.** A name asked for less than once per TTL on average usually expires before it is asked again; a longer TTL helps such names most in relative terms and still leaves most of their queries as misses (section 3).
- **Negative answers are cached too,** with a lifetime taken from the zone's SOA record, so a typo storm or a missing record is also a cache question.
- **Resolvers can answer from expired data when upstream is down.** That turns an authoritative outage into a degradation (section 7), at the price of serving old addresses.

*Visual (planned): a row of resolvers each holding one name with a countdown bar, a record change at a chosen instant, and a histogram of how long each one keeps handing out the old address. Not built yet.*

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "fail over to another region", "move traffic in seconds" | the TTL on the record, and the arithmetic in section 3; DNS alone gives a bound, not a guarantee |
| "our authoritative servers are overloaded" | too many caches missing: raise TTLs on the heads, check negative caching, look for zero-TTL records |
| "a popular name expires and everything stampedes" | merge simultaneous misses into one upstream query (section 6) |
| "what if the DNS provider is down" | serve-stale at the resolver; for your own clients, a second provider and sensible TTLs |
| "why is a lookup slow or failing for big answers" | the 512-byte UDP limit, the truncation bit and the TCP retry (section 8) |
| "do we cache NXDOMAIN?" | yes, for `min(SOA minimum, SOA TTL)` of the zone (section 5) |

---

## 3. Requirements and Capacity

**Functional.** Resolve names to addresses through a hierarchy of caches; let the owner of a record choose how long it may be cached; answer negatively and cheaply for names that do not exist. **Out of scope:** DNSSEC, record types beyond addresses, anycast and routing, zone transfer.

**Non-functional.** The authoritative side must stay up when the caches in front of it misbehave; a lookup should rarely leave the resolver; a change should reach clients in a bounded, known time.

**Capacity estimate.** Every input is an assumption of this lesson (marked *assumed*) and every result is reproduced by `capacity_check_j.py`.

| Input | Value |
|---|---|
| names one recursive resolver serves | 1,000,000 *(assumed)* |
| query rate at that resolver | 20,000 per second in total, Zipf with exponent 1 across the names *(assumed)* |
| TTL | 60 seconds *(assumed)* |
| bytes per cache entry | 100 *(assumed)* |
| resolvers that ask one authoritative zone | 100,000 *(assumed)* |
| rate one such resolver sees for a popular name | 2 per second *(assumed)* |

| Result | Arithmetic | Value |
|---|---|---|
| busiest name's rate at the resolver | 20,000 / (1 · H), H the harmonic sum of 1 to 1,000,000 (14.39) | 1,390 per second |
| rarest name's rate | 20,000 / (1,000,000 · H) | 0.0014 per second, one every 12 minutes |
| upstream queries from that resolver | sum over names of q / (1 + q·60) | 3,564 per second out of 20,000 |
| hit ratio | 1 − 3,564 / 20,000 | 82.2% |
| entries alive at any moment | sum over names of q·60 / (1 + q·60) | 213,814 entries, 21 MB at 100 bytes each |
| names asked less than once per TTL on average | names with q·60 < 1 | 916,625 of 1,000,000, carrying 17.3% of the queries |
| one very hot name, q = 1,000 per second | 1,000 / (1 + 1,000·60) | one upstream query per 60 seconds, hit ratio 99.998% |
| one tail name, q = 0.001 per second | 0.001·60 / (1 + 0.001·60) | hit ratio 5.7% |
| the same tail name at TTL 600 | 0.001·600 / (1 + 0.001·600) | hit ratio 37.5%, 6.6 times the TTL-60 figure |
| the whole resolver at TTL 600 | the sums above with 600 in place of 60 | 1,095 upstream queries per second, hit ratio 94.5%, 657,150 entries alive (66 MB) |
| authoritative load for one popular name, TTL 5 / 60 / 300 s | 100,000 · 2 / (1 + 2·TTL) | 18,182 / 1,653 / 333 per second |
| the ceiling for that load | resolvers / TTL | 20,000 / 1,667 / 333 per second |
| mean time resolvers keep serving the old address after a change | (TTL / 2) · q·TTL / (1 + q·TTL) | 2.3 / 29.8 / 149.8 seconds |

Four conclusions. **The tail sets your miss rate.** 916,625 names are cheap to hold and almost never hit, and they carry 17.3% of the traffic: the overall hit ratio of 82.2% is the head's near-perfect hits diluted by those misses. A longer TTL changes the head little (it is already above 99%) and helps the tail most in relative terms, because a tail name's hit ratio is about `q·TTL`, linear in the TTL: the tail name above goes from 5.7% to 37.5% at TTL 600, and the whole resolver from 82.2% to 94.5%. But a tail name still misses most of its queries at either TTL, and the price is a ten times longer bound on how fast a change is seen, so the TTL is a trade with failover time, not a way to rescue the tail. **A 12x TTL cut is an 11x authoritative bill.** At 5 seconds against 60 the popular name costs 18,182 queries per second instead of 1,653, and it approaches the `resolvers / TTL` ceiling from below. **A change takes up to one TTL to be seen everywhere, and about half of it on average,** in this model (resolvers that do not hold the name at the moment of the change contribute zero). **The memory is not the problem:** 21 MB for a million names. The cost is the miss traffic, which is why this lesson counts queries, not bytes.

---

## 4. API and Data Model

This is the lesson's own design, not any product's, and it matches the model below.

```
resolve(name, now) -> (rcode, address, ttl, source)     source: cache | upstream | stale | failure   Resolver.resolve
Zone.query(name, now) -> (rcode, address, ttl)           rcode: OK | NXDOMAIN | FAIL                  the authoritative side
wire (UDP)  header 12 B | question: name, type, class | answers: pointer to the name, type, class, TTL, length, address
            a response over 512 bytes is truncated with the TC bit set and the client retries over TCP (section 8)

zone record   {name -> (address, ttl)}   plus the SOA numbers: minimum and ttl
cache entry   {name -> (rcode, address, expires_at)}
failure memo  {name -> time of the last failed upstream attempt}     per name, the lesson's choice
```

A negative answer is a cache entry with rcode `NXDOMAIN` and an expiry from the SOA. Sizes are the 100-byte entry assumed in section 3; no other size is claimed.

---

## 5. The Model: A Caching Resolver

```python
class Zone:
    """The authoritative side of one zone: a table of names, SOA numbers for negative answers, outage windows."""
    def __init__(self, records, soa_minimum=300, soa_ttl=3600, outages=()):
        self.records = dict(records)           # name -> (address, ttl)
        self.soa_minimum, self.soa_ttl = soa_minimum, soa_ttl
        self.outages = list(outages)           # (start, end), start inclusive, end exclusive
        self.queries = 0

    def down(self, now):
        return any(s <= now < e for s, e in self.outages)

    def query(self, name, now):
        self.queries += 1
        if self.down(now):
            return ('FAIL', None, 0)
        if name in self.records:
            address, ttl = self.records[name]
            return ('OK', address, ttl)
        return ('NXDOMAIN', None, min(self.soa_minimum, self.soa_ttl))   # RFC 2308, section 5


class Resolver:
    def __init__(self, zone, max_ttl=7 * 86400, serve_stale=False, stale_ttl=30, max_stale=86400, recheck=30):
        self.zone, self.max_ttl = zone, max_ttl
        self.serve_stale, self.stale_ttl, self.max_stale, self.recheck = serve_stale, stale_ttl, max_stale, recheck
        self.cache = {}                        # name -> (rcode, address, expires_at)
        self.failed_at = {}                    # name -> time of the last failed attempt

    def resolve(self, name, now):
        """Returns (rcode, address, ttl handed to the client, where the answer came from)."""
        entry = self.cache.get(name)
        if entry and now < entry[2]:           # at exactly the expiry instant the entry is already stale
            return (entry[0], entry[1], entry[2] - now, 'cache')
        if name in self.failed_at and now - self.failed_at[name] < self.recheck:
            return self._failure(entry, now)   # do not hammer a server that just failed
        rcode, address, ttl = self.zone.query(name, now)
        if rcode == 'FAIL':
            self.failed_at[name] = now
            return self._failure(entry, now)
        ttl = min(ttl, self.max_ttl)
        self.cache[name] = (rcode, address, now + ttl)   # a TTL of 0 expires immediately: never cached
        return (rcode, address, ttl, 'upstream')

    def _failure(self, entry, now):
        if self.serve_stale and entry and entry[0] == 'OK' and now < entry[2] + self.max_stale:
            return ('OK', entry[1], self.stale_ttl, 'stale')
        return ('SERVFAIL', None, 0, 'failure')
```

What each piece comes from, and what is the lesson's own choice:

- **A positive answer is cached for its TTL.** RFC 2181 defines the TTL as an unsigned number between 0 and 2,147,483,647 (2^31 - 1), and RFC 8767 updates it: a value with the high-order bit set is treated as positive and then clamped, not as 0, with a suggested cap of 7 days (next bullet). RFC 2181 also requires the TTLs of all records in a set of records of one name and type to be the same, deprecating differing TTLs because they can cause partial replies from a cache. A TTL of 0 is therefore a record nobody may reuse: every client query becomes an upstream query. That is a classic accident on the authoritative side (a zero TTL left on a busy name).
- **`max_ttl` is a clamp.** RFC 8767 describes a maximum cache TTL in many resolvers as a clamp on the TTL values received and notes that its own definition recommends 7 days, "rather than the 68 years allowed" by the full 31 bits. The default here follows that.
- **A negative answer is cached for `min(SOA minimum, SOA TTL)`.** RFC 2308, section 5 says the authoritative server puts the zone's SOA record in the authority section, taking its TTL from the lesser of the SOA minimum field and the SOA record's own TTL, and caches count that down like any other answer.
- **Serve-stale follows RFC 8767 in shape:** answers served from expired data carry a TTL greater than 0 (the RFC recommends 30 seconds, and explains that 0 has been problematic and very short TTLs invite a refresh storm); refresh attempts against a failing server are recommended no more often than every 30 seconds (the failure recheck timer); and a maximum stale timer caps how long data is kept past expiry, with a suggested value between 1 and 3 days. The default `max_stale` here is one day.
- **Lesson's own choices, not RFC text:** serving stale only for positive answers (negative answers fall through to a failure); the exact boundary convention at the TTL instant; the model's failure recheck being keyed per name; and all the times above being exact values. The RFC's client response timer and query resolution timer are not modelled.

**The rate formula, derived.** After a miss the answer is held for `TTL`; the next query then arrives on average `1 / q` later (Poisson arrivals, rate `q`). One cycle is `TTL + 1/q` long and contains one upstream query, so the upstream rate is `1 / (TTL + 1/q) = q / (1 + q·TTL)`, and the share of time the name is held is `q·TTL / (1 + q·TTL)`.

```python
def upstream_rate(qps, ttl):
    """Expected upstream queries per second for one name at one cache: one per cycle of ttl + 1/qps."""
    return qps / (1 + qps * ttl)

def authoritative_qps(resolvers, qps_each, ttl):
    """Load on the zone for one name when `resolvers` independent caches each see qps_each."""
    return resolvers * upstream_rate(qps_each, ttl)

def live_entries(rates, ttl):
    """Expected number of cache entries alive at one instant, given each name's rate."""
    return sum(q * ttl / (1 + q * ttl) for q in rates)
```

The check simulates Poisson arrivals through the real `Resolver` for five (rate, TTL) pairs and holds the formula to within 3%. It also measures the mean staleness after a change across 2,000 simulated resolvers and holds it to the closed form in the table (staleness is a property of when each cache last refreshed). The model assumes independent Poisson arrivals and equal TTLs; real traffic is bursty and clients and intermediate caches add their own caching, none of which is modelled or measured here.

---

## 6. Deep Dive 1: The Stampede on Expiry

A popular name expires. In the next round trip every client that asks finds the cache empty, and a resolver that sends one upstream query per client sends a burst proportional to the traffic. The remedy is to merge identical in-flight queries.

```python
def burst(arrival_times, rtt, coalesce):
    """Upstream queries a resolver with an empty cache sends for one name when clients ask at these times."""
    sent, cached_at = 0, None
    for t in sorted(arrival_times):
        if cached_at is not None and t >= cached_at:
            continue                            # the first answer has arrived: this is a cache hit
        if coalesce and sent > 0:
            continue                            # join the query already on its way
        sent += 1
        if cached_at is None:
            cached_at = t + rtt
    return sent
```

With 500 clients asking at the same instant and a 200 ms round trip, the unmerged resolver sends 500 queries and the merging one sends 1; a client arriving exactly when the answer lands is a cache hit, not a new query. The check pins each case against an independent count. In the Zipf model of section 3, the head names are where this matters: the busiest name sees 1,390 queries per second, so at a 200 ms upstream round trip, about 278 further clients ask during the 200 ms after the first miss. The first miss sends one query; unmerged, the others add about 278 more (279 in all, the expected number of Poisson arrivals in 200 ms), and the merge removes those 278. **What the model leaves out:** the time a merged client waits is the upstream round trip, and if that query fails or times out all merged clients fail together (a thundering herd of retries on the client side is real; its size is not modelled).

---

## 7. Deep Dive 2: When the Authoritative Side Is Down

Three behaviours, all checked by exact scenarios:

| Behaviour | What happens in the model |
|---|---|
| no serve-stale | the moment the cached entry expires, the name fails (`SERVFAIL`); with a 60 s TTL, everything on that zone fails inside a minute of the outage starting |
| serve-stale on | the expired answer keeps being served, with a 30 s TTL, until `max_stale` after expiry (here, boundary tested at 60 + 200 = 260 s) |
| failure recheck | one name queried every second during a 600 s outage costs **20** upstream attempts, not 600; with a 10 s recheck it costs 60 |

The failure recheck is what stops a resolver's own retries from becoming the load that keeps the zone down: it is the same lesson as in Overload, Load Shedding and Cascading Failures, applied to a cache. Serving a 30-second TTL on stale answers also rate-limits clients that respect TTLs, which is the stated reason in RFC 8767. The cost is real: while serving stale, clients are handed addresses the owner may have already moved away from. A DNS-based failover that depends on resolvers re-asking is exactly the thing an outage plus serve-stale defeats. State that in an interview: failover through DNS has a lower bound set by the TTL and, with serve-stale, by the outage itself.

---

## 8. Deep Dive 3: The 512-Byte Limit and the TCP Fallback

RFC 1035 restricts DNS messages over UDP to 512 bytes (not counting IP or UDP headers); a longer message is truncated and the TC bit is set so the client retries over TCP. RFC 9210 (2022) says all resolvers and servers must support and service both UDP and TCP, and that servers must support TCP so clients can reliably receive responses too large for UDP; the older text making TCP optional is replaced.

```python
import struct

def encode_name(name):
    out = b''
    for label in name.rstrip('.').split('.'):
        raw = label.encode('ascii')
        assert 0 < len(raw) <= 63
        out += bytes([len(raw)]) + raw
    return out + b'\x00'

def build_a_response(qname, n_answers, ttl=60):
    """A response with one question and n_answers A records; each answer's name is a pointer to the question."""
    header = struct.pack('!HHHHHH', 0x1234, 0x8180, 1, n_answers, 0, 0)
    question = encode_name(qname) + struct.pack('!HH', 1, 1)
    answer = b'\xc0\x0c' + struct.pack('!HHIH', 1, 1, ttl, 4) + bytes([192, 0, 2, 1])
    return header + question + answer * n_answers

def max_a_records(qname, limit=512):
    n = 0
    while len(build_a_response(qname, n + 1)) <= limit:
        n += 1
    return n
```

For `www.example.com` the header is 12 bytes, the question 17 + 4 = 21, and each answer 16 bytes (a 2-byte pointer, type, class, a 4-byte TTL, a 2-byte length and 4 bytes of address): `(512 − 33) / 16 = 29.9`, so **29** address records fit and a 30th triggers truncation. The check builds the packets, parses them back with an independent byte walker (confirming the pointers, counts and lengths) and compares the maximum with that closed form for 300 random names and four limits. The 1,232-byte and 4,096-byte limits in that test are arbitrary what-if sizes, not claims about EDNS, which was not read.

Two consequences worth saying aloud. **Hundreds of addresses on one name do not fit one UDP answer,** so return a short, rotated subset (and see the shuffle's effect on caches in Caching Patterns and Consistent Hashing). **TCP is not an edge case:** a resolver or server that does not handle it fails exactly the large answers.

---

## 9. Failure Modes

| Failure | What goes wrong | What the model or RFCs say |
|---|---|---|
| record with TTL 0 | no cache can reuse it; every client query reaches the zone | modelled: six queries, six upstream |
| authoritative outage | caches expire inside one TTL and the name fails | modelled: `SERVFAIL` at the expiry instant without serve-stale |
| outage with serve-stale | stale addresses are served until `max_stale` | modelled; the cost is wrong addresses after a move |
| expiry of a hot name | a burst of identical upstream queries | merge identical in-flight queries (section 6) |
| mistyped or deleted name | every client asks, each answer is a negative one | cached for `min(SOA minimum, SOA TTL)` |
| record changed, old address removed too early | resolvers keep handing out the old address for up to the TTL | modelled: mean about half a TTL, maximum one TTL |
| answer too large for UDP | truncated; clients retry over TCP | RFC 1035 and RFC 9210 |
| differing TTLs inside one set | partial answers from a cache | RFC 2181 deprecates them; all TTLs in a set must match |

---

## 10. What Real Systems Did

No engineering post or paper from any DNS operator or large resolver was read for this lesson. What it relies on is the standards text above (RFC 1035, 2181, 2308, 8767 and 9210), plus the model. Two caveats it states rather than hides: **real clients and intermediate caches do not all follow the TTL** (this lesson reads the standards, not measured behaviour, so it does not claim how often TTLs are ignored or clamped); and **serve-stale as specified is a recommendation to resolver operators,** so what any given public resolver does is not asserted here.

---

## 11. Pitfalls Checklist

1. **Treating DNS failover as instant.** The bound is the TTL; the mean, in the model, is about half of it, and an outage with serve-stale can extend it.
2. **Cutting the TTL without recounting authoritative load.** 5 seconds instead of 60 is about 11x the load, bounded by `resolvers / TTL`.
3. **Leaving a TTL of 0 on a busy name.** It disables caching entirely.
4. **Forgetting negative caching.** A name that does not exist is still a query, cached for the zone's SOA value.
5. **Sending hundreds of addresses in one answer.** About 29 A records fit a 512-byte UDP answer for a short name.
6. **Letting identical misses fan out.** Merge in-flight queries at the resolver.
7. **Counting memory instead of misses.** 21 MB for a million names is nothing; 3,564 queries per second of misses is the bill.
8. **Treating the TTL as a guarantee about clients.** It is an instruction to caches that follow it.

---

## Drills

1. A name is asked for 10 times a second at one resolver with a 30-second TTL. How many upstream queries per second, and what is the hit ratio?
2. Reproduce the 3,564-per-second figure for a resolver with half the names (500,000) and half the traffic (10,000 per second), and say whether the hit ratio goes up or down, with the reason.
3. Authoritative load for one name is 5,000 queries per second at TTL 60 with 50,000 resolvers. Predict the load at TTL 10 and at TTL 600, and say why the answer at TTL 10 cannot exceed `resolvers / 10`.
4. A zone's SOA minimum is 3,600 and the SOA record's own TTL is 60. How long is NXDOMAIN cached, and why?
5. The authoritative servers are down for 10 minutes. With a 60-second TTL, a 1-day maximum stale timer and serve-stale on, what does a client see at minute 1, at minute 5 and at minute 11 (just after recovery)? What if serve-stale is off?
6. Change `<` to `<=` in the cache hit test. Which scenario in the check fails, and what does the failure mean for a record with a TTL of 60 asked at exactly second 60?
7. A name has 40 A records. Does the answer fit in 512 bytes of UDP? What happens to a client that never retries over TCP?
8. Design a failover target of "most users move within 30 seconds". State the TTL you would choose, what it costs the authoritative side for 100,000 resolvers at 2 queries per second each, and two reasons it still might not hold.

---

## Homework

1. Run the model with your own numbers: 5 million names, a Zipf exponent of 0.8, 50,000 queries per second, TTL 120. Report upstream load, hit ratio and live entries, and which part of the name list carries most of the misses.
2. Add the RFC 8767 client response timer to `Resolver`: if upstream has not answered within it, answer from stale data and finish the refresh in the background. Write a check that fails first.
3. Add a second cache layer (a forwarding resolver in front of this one with its own TTL clamp) and measure how the staleness after a change grows. State what you must assume about phase alignment between the two.
4. Read RFC 8767 section 5 on the stale-data timers in full, and list one recommendation this model does not implement.

---

## Sources

All read on 27 November 2026.

- IETF, *RFC 1035, Domain Names — Implementation and Specification*, rfc-editor.org/rfc/rfc1035.txt (read in part: the UDP size restriction and the truncation bit).
- IETF, *RFC 2181, Clarifications to the DNS Specification*, rfc-editor.org/rfc/rfc2181.txt (read in part: the TTL range in section 8 and the requirement that all TTLs in one set of records match, in section 5.2).
- IETF, *RFC 2308, Negative Caching of DNS Queries*, rfc-editor.org/rfc/rfc2308.txt (read in part: section 5, the SOA-based TTL for negative answers).
- IETF, *RFC 8767, Serving Stale Data to Improve DNS Resiliency*, rfc-editor.org/rfc/rfc8767.txt (read in part: the stale TTL, the failure recheck timer, the maximum stale timer and the 7-day clamp remark).
- IETF, *RFC 9210, DNS Transport over TCP — Operational Requirements*, rfc-editor.org/rfc/rfc9210.txt (read in part: the requirement that all resolvers and servers support UDP and TCP).
- Not read: RFC 1034 beyond the download (the resolver and authoritative roles are described here as general background), EDNS(0) and its size negotiation, DNSSEC, any DNS operator's engineering publication, and any measurement study of how clients treat TTLs.

## Further reading (not consulted)

- RFC 1034 and RFC 6891 (EDNS).
- Measurement studies of resolver and client TTL behaviour.
- A DNS provider's own writing on anycast and failover.

*Last reviewed: 27 November 2026.*
