# Lesson 66 — Case Study: Log Aggregation and Search (ELK / Splunk)

> **Priority:** ★★★☆☆ (proposed; the curriculum data holds the final rating) — "collect logs from thousands of machines and search them" tests whether you separate a write path that must never lose lines from a read path that can be slow and cheap.
>
> **Study time:** 75 minutes. **Do this after:** Distributed Search Engine (Elasticsearch at Scale); Overload, Load Shedding and Cascading Failures; Replication & Sharding.
>
> **Level:** extended.

A log system takes a firehose of small, append-only lines, keeps them for weeks or months, and answers "what did service X say between 14:00 and 14:05?" fast enough for an on-call engineer. Searching is the part everyone draws; the parts that decide the design are the volume, the shape of the index, and what happens to a line when something between the machine and the disk fails. The Distributed Search Engine lesson already covers BM25, scatter-gather and shard sizing for search at large; this lesson links to it and covers what is specific to logs. The code is a small model checked in `test/lesson_code/sy66_check.py` against brute-force references; capacity numbers come from `capacity_check_h.py`.

---

## 1. Mental Model

> **Logs are write-heavy, time-ordered and rarely read, so the design question is how little you have to do per line at write time, while still being able to find it. Everything you index at write time you pay for on every line; everything you do not, you pay for on the few queries that need it.**

- **Time is the primary key.** Almost every query has a time range, so partition by time, keep min and max timestamps per segment, and skip what cannot match. Retention then drops whole units instead of deleting lines.
- **Two designs sit on one axis.** Index every term (the Elasticsearch/Lucene approach): fast arbitrary search, large index. Index only labels and store compressed chunks (the approach Loki documents): small and cheap, queries scan the chunks you select.
- **Delivery is at-least-once, so the store must dedupe.** Retries are how you avoid loss; duplicates are what they cost.
- **Buffer before you index.** A durable queue between agents and indexers absorbs an indexer outage and a traffic spike so the agents never have to drop lines.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "search logs by any word, across services" | inverted index per segment, partitioned by time (section 5) |
| "cheap long retention, mostly search by service and time" | label index plus compressed chunks in object storage (section 3 and 5) |
| "a deploy writes ten times the logs and the indexers fall behind" | a durable buffer between agents and indexers; backpressure and shedding (Overload, Load Shedding and Cascading Failures) |
| "delete logs older than 30 days" | drop whole time partitions, never delete by query (section 6) |
| "no log line may be lost or counted twice" | sequence numbers, cumulative acks, dedupe at the receiver (section 7) |
| "one index per host per day" | no: tiny shards and a huge index count (section 3, with arithmetic) |
| "how fresh is a search" | near-real-time: a refresh interval, not instant (section 5) |

---

## 3. Requirements and Capacity

**Functional.** Agents tail files and ship lines with labels (service, environment, level, host); search by time range, labels and words; tail a stream live; retention by age; per-team isolation. **Non-functional.** No silent loss during a spike or an indexer outage; search over the last hours in seconds; cheap long retention; a bounded delay from log to searchable. **Out of scope:** alerting rules, traces, access control detail.

**Capacity estimate.** Inputs marked *assumed* are this lesson's, not any company's. Inputs marked *docs* are guidance printed in the Elasticsearch documentation read for this lesson. Every result is reproduced by `capacity_check_h.py`. The compression and expansion factors are assumptions: measure your own logs before trusting any of them.

| Input | Value |
|---|---|
| average and peak ingest | 100,000 lines per second average, three times that at peak *(assumed)*; 300 bytes per line *(assumed)* |
| buffer retention | 6 hours of peak *(assumed)* |
| full-text store | stored size 1.2 times raw including the index, one replica *(assumed)* |
| label-and-chunk store | chunks compress 8 to 1 *(assumed)*, one copy in object storage |
| shard size target | 30 GB *(docs: aim for 10 GB to 50 GB per shard, fewer than 200 million documents)* |
| master heap rule | fewer than 3,000 indices per GB of heap *(docs, a rule of thumb for master nodes)* |
| services, pods | 200 services, 5,000 pods *(assumed)* |
| scan speed | 500 MB per second per query worker *(assumed)* |

| Result | Arithmetic | Value |
|---|---|---|
| raw volume | 100,000 x 300 B x 86,400 | 2.592 TB per day (30 MB per second average, 90 MB per second at peak) |
| buffer for a 6 hour indexer outage | 90 MB/s x 21,600 s | 1.94 TB (5.83 TB with three copies) |
| full-text store, one day | 2.592 TB x 1.2 x 2 | 6.22 TB; 18.7 TB for 3 hot days |
| primary shards per day | 3.11 TB / 30 GB | 104 |
| label-and-chunk store, one day | 2.592 TB / 8 | 324 GB; 118 TB for a year |
| one index per pod per day, a year | 5,000 x 365 | 1,825,000 indices, 608 GB of master heap by the rule; each shard about 518 MB, 19 times under the 10 GB floor |
| daily rollover at 30 GB, 30 days | 104 x 30 | 3,120 shards, about 1 GB of heap by the same rule |
| streams if the label set adds pod and level | 5,000 pods x 5 levels | 25,000 streams |
| streams if a request id becomes a label | up to one per line | up to 8.64 billion a day: more entries than the data is worth |
| one service for one hour | 2.592 TB / 200 / 24 | 540 MB, about 1.1 s on one worker |
| scanning one whole day | 2.592 TB / 500 MB/s | 5,184 worker-seconds, 52 s on 100 workers |

Five conclusions. **Volume, not search, sizes the cluster:** 2.6 TB a day raw. **The buffer is cheap insurance:** under two terabytes for six hours of peak. **The cost gap between the designs is the index:** 6.2 versus 0.32 terabytes a day with these assumed factors (about 19 times); it is an illustration of the shape and not a measured ratio. **Shard count is a design variable:** per pod per day gives 1.8 million indices and 19 times undersized shards; rollover by size gives about 3,000 shards a month. **Cardinality is the label design's failure mode:** labels turn into streams, and a label with a value per request makes the index as large as the data. The Loki documentation says plainly that a good set of labels is key to efficient queries; the arithmetic is this lesson's.

---

## 4. API and Data Model

```
agent:    log(line) -> seq per source                 outbox() -> unacked (source, seq, line)     on_ack(upto)
ingest:   accept(source, seq, line) -> cumulative ack   (idempotent)
search:   search(terms, t0, t1, stream?) -> lines in [t0, t1) containing every term, newest last
store:    segment {docs, postings: term -> doc ids, min_ts, max_ts, streams}   (immutable once written)
```

A line is `(timestamp, stream, text)`. A **stream** is the set of lines that share a label set, as the Loki documentation defines it. A **segment** is an immutable batch written at each refresh (Lucene's per-segment search, as the Elasticsearch near-real-time page describes). Segments carry their time range and their streams so a query can skip them.

---

## 5. Pipeline and Deep Dive 1: Segments, Refresh and Merging

**The pipeline.** Agents on each host tail files, batch lines, label them and ship them. A buffer decouples them from the indexers: the Kafka paper (LinkedIn's log-processing system) stores each partition as a log of segment files of about 1 GB, addresses messages by offset instead of an id, has consumers pull and keep their own offset so they can rewind, and guarantees at-least-once delivery, which is what log shipping needs. Indexers consume from the buffer and write the store. Queries go to a coordinator that fans out to shards and merges, as in the Distributed Search Engine lesson. Facebook's Scribe and Cloudera's Flume are named in the Kafka paper as earlier aggregators that dump to HDFS or similar; nothing else about them was read.

**Two store designs.** Elasticsearch documents that a document is searchable in near real time, within one second, because Lucene writes a new segment cheaply into the filesystem cache and opens it without a full commit. By default it refreshes every second, only on indices that received a search in the last 30 seconds. So "how fresh is a search" has an answer in seconds, set by the refresh interval and the queue ahead of the indexer. Loki's documentation describes the other design: it does not index log contents, only a set of labels per stream; lines are compressed into chunks in object storage; writes are hashed per stream onto a consistent hash ring (see Caching Patterns and Consistent Hashing) to ingesters with a replication factor, acknowledged when a quorum answers; reads split a query into sub-queries and read in-memory data from ingesters plus chunks from the store.

**The model.** An append buffer; `refresh` turns it into an immutable segment with an inverted index and its time and stream summary; search reads segments only.

```python
class Segment:
    def __init__(self, docs):
        self.docs = list(docs)                                   # (ts, stream, text)
        self.post = {}                                           # term -> doc positions
        for i, (ts, st, text) in enumerate(self.docs):
            for t in set(text.lower().split()): self.post.setdefault(t, []).append(i)
        self.min_ts = min(d[0] for d in self.docs); self.max_ts = max(d[0] for d in self.docs)
        self.streams = {d[1] for d in self.docs}

class LogStore:
    def __init__(self): self.buffer, self.segments = [], []
    def append(self, ts, stream, text): self.buffer.append((ts, stream, text))
    def refresh(self):                                            # near-real-time: lines become searchable only now
        if self.buffer: self.segments.append(Segment(self.buffer)); self.buffer = []
    def search(self, terms, t0, t1, stream=None):
        """Lines with ts in [t0, t1) containing every term (lower-case). Returns (sorted lines, segments opened)."""
        out, opened = [], 0
        for seg in self.segments:
            if seg.max_ts < t0 or seg.min_ts >= t1 or (stream is not None and stream not in seg.streams): continue
            opened += 1
            ids = set(seg.post.get(terms[0], []))
            for t in terms[1:]: ids &= set(seg.post.get(t, []))
            out += [seg.docs[i] for i in ids if t0 <= seg.docs[i][0] < t1 and (stream is None or seg.docs[i][1] == stream)]
        return sorted(out), opened
    def expire(self, cutoff):
        """Retention: drop whole segments that end before the cutoff. Returns how many were dropped."""
        keep = [s for s in self.segments if s.max_ts >= cutoff]
        dropped, self.segments = len(self.segments) - len(keep), keep
        return dropped
```

The check compares `search` with a plain scan over every flushed line on 300 random stores (late arrivals, 13 terms, one and two-term queries, with and without a stream), asserts the half-open window at both boundaries, and asserts that lines in the buffer are invisible until `refresh`.

**Merging.** Many small segments make every query open many files, so a background merge combines them. The Lucene documentation read for this lesson describes `TieredMergePolicy`: it merges segments of roughly equal size, allows a configured number per tier, can merge non-adjacent segments, avoids over-merging, and favours merges that reclaim deleted documents. The model below is a simpler stand-in, not Lucene's policy: merge `m` equal segments into one. Its cost has exact closed forms.

```python
def merge_sim(n_flushes, m):
    """Flush n unit segments; whenever m segments have the same size, merge them. Returns (live segments, total units written)."""
    sizes, written = [], 0
    for _ in range(n_flushes):
        sizes.append(1); written += 1
        while True:
            full = [s for s in set(sizes) if sizes.count(s) == m]
            if not full: break
            s = full[0]
            for _ in range(m): sizes.remove(s)
            sizes.append(s * m); written += s * m
    return len(sizes), written

def digit_sum(n, m):                       # live segments after n flushes: the base-m digit sum
    total = 0
    while n: total += n % m; n //= m
    return total

def written_formula(n, m):                 # every size-m^t segment is written once: sum of floor(n / m^t) * m^t
    return sum((n // m ** t) * m ** t for t in range(0, 64) if m ** t <= n)
```

The check asserts `merge_sim` equals both forms for every n below 700 and m in 2, 3, 4, 10. The consequences you can quote: after 1,000 flushes with m = 10 there is one segment and each flushed unit has been written 4 times in total (once at the flush, three times by merges); after 999 flushes there are 27 segments (the digit sum 9 + 9 + 9). **Write amplification is about log base m of the number of flushes**, and a larger `m` means fewer rewrites and more segments per query. This is why a log system wants large, infrequent refreshes on cold data and cheap ones on hot data. Reality adds deletes and size caps (the documentation notes a maximum merged segment size), which the model ignores.

---

## 6. Deep Dive 2: Time Partitioning and Retention

Queries carry a time range, so every segment keeps its `min_ts` and `max_ts` and a query skips segments outside the range. The check shows the effect: ten disjoint one-hour segments, a one-hour query opens 1 of 10, a ten-hour query opens all 10. **Late lines widen a segment's range:** a line arriving with an old timestamp makes its segment cover both times, so a query for the old time must open it. The check pins this: a segment holding timestamps 100 and 5000 is opened by a query for 90 to 110. Lines that arrive far out of order therefore cost pruning, which is one reason to bound lateness (reject or route very late lines to a separate "late" index).

**Retention drops whole segments, not lines.** `expire(cutoff)` removes segments whose newest line is older than the cutoff. The check, on 200 random stores, asserts three things: no line inside the retention window is ever lost; every surviving segment reaches into the window; and every line that disappears is older than the cutoff. The price is granularity: a segment that straddles the cutoff survives with some expired lines. For Elasticsearch the same idea is a data stream, whose backing indices are created over time and whose old ones a lifecycle policy moves to cheaper hardware and then deletes; the documentation lists hot, warm, cold and frozen tiers, with the hot tier on fast storage and the cold tier optimised for storage cost. Deleting lines inside a live segment means rewriting it; dropping a unit is a metadata change. That is the whole argument for time partitioning, and it needs no number.

**Where the shard count comes from.** Section 3's table: partition by size at about 30 GB, not by host or pod. Both too many small shards and too few huge ones hurt (the documentation says very large shards slow searches and recovery; oversharding wastes heap).

---

## 7. Deep Dive 3: Not Losing or Duplicating a Line

An agent crashes after sending a batch and before it hears an acknowledgement. If it does not resend, lines are lost; if it resends, the receiver may store them twice. The standard answer is to resend until acknowledged and make the receiver idempotent. Each agent numbers its lines per source. The receiver keeps, per source, the next expected number and the set of numbers received early, ignores anything it already has, and returns a **cumulative** acknowledgement: "I have everything below this".

```python
class Agent:
    def __init__(self, source): self.source, self.seq, self.unacked = source, 0, {}
    def log(self, line): self.unacked[self.seq] = line; self.seq += 1
    def outbox(self): return [(self.source, s, l) for s, l in sorted(self.unacked.items())]
    def on_ack(self, upto):                         # everything below `upto` is safe; a late, smaller ack changes nothing
        for s in [s for s in self.unacked if s < upto]: del self.unacked[s]

class Receiver:
    def __init__(self): self.expect, self.early, self.stored = {}, {}, []
    def accept(self, source, seq, line):
        nxt, early = self.expect.get(source, 0), self.early.setdefault(source, set())
        if seq >= nxt and seq not in early:
            self.stored.append((source, seq, line)); early.add(seq)
        while nxt in early: early.discard(nxt); nxt += 1
        self.expect[source] = nxt
        return nxt
```

The check drives three sources of 5 to 45 lines each through a channel that loses half the messages, delivers a quarter of them twice, reorders them, and loses half the acknowledgements, for 300 seeds. It asserts that every line is stored **exactly once**, that every agent ends with nothing unacknowledged, and that each source's stored numbers are exactly `0..n-1` with an empty early set. A copy of the receiver without the dedupe stores duplicates on the same channel, so the test is not vacuous. Numbers beyond 9 and 99 are handled as numbers: 120 lines delivered newest-first end at an acknowledgement of 120.

What this guarantees is delivery from the agent's memory to the receiver. If the agent's host dies with unacknowledged lines only in memory, they are gone; a durable on-disk position (what a log shipper keeps for the file it tails) closes that, and the model does not include it. The same idempotence is what makes it safe to replay a buffer after an indexer restart: the Kafka paper's consumer-side offsets give at-least-once, and this section is the dedupe that turns it into once.

**The read path, and live tail.** Searching is a fan-out with a time budget. Loki's documentation describes the shape: a query front end splits the query into sub-queries, queriers pull them from a scheduler, ask the ingesters for lines not yet flushed, read the rest from the store, deduplicate (the replicas hold the same lines, which is the same at-least-once cost as above) and the front end merges the results. Two consequences you can reuse for any log design. First, **a query must always carry a time range and a limit**, because time is what lets you skip data; a query with neither is a full scan of the retention period (5,184 worker-seconds a day at the assumed scan speed, section 3). Second, **live tail is a different path**: it reads the newest lines from the ingesters or the buffer and never touches the store, so it works even when indexing is minutes behind. In the model that is `LogStore.buffer` read directly, the very thing `search` refuses to see.

**Overload.** When ingest exceeds what indexers can write, the buffer fills. Decide in advance which lines to shed (debug before error, one noisy tenant before the others), at the edge, with a per-tenant quota. That policy and its failure modes are the subject of Overload, Load Shedding and Cascading Failures.

---

## 8. Failure Modes

| What breaks | What you see | Defence |
|---|---|---|
| indexers fall behind | buffer grows, search lags | a buffer sized in hours (1.94 TB for 6 hours here), backpressure, shedding by priority |
| agent retry after a lost ack | duplicate lines | per-source sequence numbers and a cumulative ack |
| a label with unbounded values | stream count and index explode | cap label cardinality; keep request ids in the line, not in a label |
| one index per host per day | millions of tiny shards, master heap pressure | size-based rollover (section 3) |
| very late lines | segments span huge ranges, pruning stops working | bound lateness, route stragglers to a separate index |
| a spike in one tenant | other tenants' lines dropped or delayed | per-tenant quotas at the edge |
| a hot node in the ring | ingesters overloaded | replication factor and rebalancing; this is Caching Patterns and Consistent Hashing's subject |
| a long query scans everything | the cluster stalls | split into sub-queries with limits (Loki's query frontend does this), time-range caps |

---

## 9. What Real Systems Did

- **Elasticsearch / Lucene** (documentation read 2026-11-27: near-real-time search, data streams, data tiers, shard sizing guidance, and the Lucene 9.9 `TieredMergePolicy` API page): the near-real-time refresh, the 10 GB to 50 GB shard guidance, the heap rule, data streams with hot, warm, cold and frozen tiers. Only the documented behaviour above is claimed.
- **Loki** (Grafana documentation read 2026-11-27: overview and architecture pages): labels-only index, compressed chunks in object storage, the distributor-to-ingester write path with a replication factor and quorum, and the query-frontend read path. The marketing statements on the overview page (cost, scale claims) are not used.
- **Kafka** (Kreps, Narkhede and Rao, NetDB 2011, read 2026-11-27): the buffer layer for log processing at LinkedIn, which the paper says accumulated hundreds of gigabytes and close to a billion messages a day at the time.
- **Splunk:** its documentation page returned only a stub when fetched, so no Splunk behaviour is described. The design above is the general approach, not Splunk's.

---

## 10. Pitfalls Checklist

1. **Indexing everything by default.** The index is most of the cost; decide what search must be fast.
2. **Labels with unbounded values.** Cardinality is the index size.
3. **One index per host or pod.** Tiny shards, a master that runs out of heap.
4. **Deleting by query for retention.** Drop whole partitions.
5. **At-most-once shipping.** A crash loses the lines you most needed.
6. **Resending without dedupe.** Duplicates in every count and alert.
7. **Comparing sequence numbers as strings** ("10" sorts before "9"), or acknowledging a gap.
8. **Treating "searchable" as instant.** It is a refresh interval plus a queue.
9. **No bound on lateness.** One old timestamp widens a segment and defeats pruning.

---

## Drills

1. A query for 10:00 to 11:00 opens 1 of 10 hourly segments, but a late-arriving line widens one of them. Walk through why pruning gets worse and what you would do.
2. The merge model gives 27 live segments after 999 flushes with m = 10. Where does 27 come from, and what is the write cost of the 1,000th flush?
3. Compute the daily raw volume for 100,000 lines per second at 300 bytes, and the buffer needed to ride out a 6 hour indexer outage at triple that rate.
4. Why is "one index per pod per day" wrong at 5,000 pods, and what does the master-heap rule say about it?
5. An agent sends lines 0 to 4, the receiver gets 0, 1, 3 and acknowledges. What does it acknowledge, and what does the agent resend?
6. Why does a cumulative acknowledgement survive a lost or reordered ack, and what would a per-line ack cost you?
7. Contrast a full-text index with a label index on cost, on the query "find this request id" and on the query "all errors from service X yesterday".
8. A team asks to add `request_id` as a label "so we can search it". What do you say, with numbers?

---

## Homework

1. Run `sy66_check.py` on this file. Change the window to `t0 <= ts <= t1` and find the failing assertion; then drop `min_ts` from the prune test and find which fails.
2. Add a "late" side index for lines more than an hour old and measure segments opened on the check's workload.
3. Extend `expire` to rewrite straddling segments and compare the write cost with dropping.
4. Give the agent a durable position file and extend the channel check with a crash that loses the agent's memory.

---

## Sources

All read 2026-11-27. The model, the figures marked *assumed* and the arithmetic are this lesson's own.

- Elasticsearch reference documentation (elastic.co/guide/en/elasticsearch/reference/current): near real-time search, data streams, data tiers, size your shards. Read the text of each page extracted from HTML; the index lifecycle and translog pages were fetched but not read closely and no claim is made from them.
- Apache Lucene 9.9.0 API documentation for `TieredMergePolicy`: read the class summary and the method summaries.
- Grafana Loki documentation (overview and architecture pages, latest version at the access date): read in full for the passages used.
- Kreps, Narkhede, Rao, *Kafka: a Distributed Messaging System for Log Processing*, NetDB 2011 (a copy at notes.stephenholiday.com/Kafka.pdf): read the introduction, related work, architecture and deployment sections; the experiments were skimmed.

## Further reading (not consulted)

Splunk documentation (not retrievable), the Elasticsearch translog and index lifecycle pages in detail, the Lucene index-format documentation, ClickHouse or Parquet-based log stores, OpenTelemetry's log data model, and engineering posts from companies that run these at scale. None were read, so no claim is made about them.

*Last reviewed: 27 November 2026.*
