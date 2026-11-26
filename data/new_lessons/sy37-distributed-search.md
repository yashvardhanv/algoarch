# Lesson 37 — Case Study: Distributed Search Engine (Elasticsearch at Scale)

> **Priority:** ★★★★★ — "design product search" or "design log search" is a standard prompt, and every follow-up is about shards, relevance and freshness.
>
> **Study time:** 60 minutes. **Do this after:** the Latency Numbers & Capacity Estimation lesson and Replication & Sharding. You should know what an inverted index is in one sentence.

A search engine answers "which documents match these words, best first" over more data than one
machine holds, while new documents keep arriving. The interview is rarely about the index itself; it
is about the three things the index forces on you: **every query fans out to every shard**, **relevance
scores depend on statistics that each shard only knows locally**, and **"indexed" is not the same as
"searchable" or "durable"**. This lesson builds a small BM25 search engine, shards it, and works through
those three with numbers.

---

## 1. Mental Model

> **A search cluster is many small search engines (shards) behind a coordinator. Every query is
> scatter-gather: ask each shard for its best few, merge them. Everything else (sizing, ranking
> accuracy, pagination, freshness) follows from that one shape.**

What follows from it:

- **Cost per query is proportional to the number of shards it touches.** More shards make each one
  smaller, but every query pays for all of them, unless routing sends it to one.
- **A shard ranks with what it knows.** BM25 uses document frequencies; if each shard uses its own, the
  same document can score differently depending on where it lives.
- **The coordinator only needs `k` hits from each shard for the top `k`.** That is why the first page is
  cheap and page 1,000 is not.
- **A write becomes searchable at refresh and durable at fsync of the translog.** They are separate
  clocks, and you should be able to name both.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "full-text search, ranked by relevance" | an inverted index with BM25 scoring per shard, scatter-gather |
| "queries are always within one tenant / one user" | custom routing by tenant so a query touches one shard |
| "scores look wrong on small indices" or "the same doc ranks differently" | local vs global statistics; `dfs_query_then_fetch` or fewer shards |
| "let users page deep" or "export all matches" | `search_after` with a point in time, never large `from` |
| "new items must be searchable within a second" | the refresh interval (default 1s on active indices) |
| "no acknowledged write may be lost" | translog durability `request` (the default) and replicas |
| "index grows forever (logs)" | time-based indices and deleting whole indices, not documents |

---

## 3. Requirements and Capacity

**Functional.** Index product documents (title, description, attributes); full-text query with filters;
results ranked by relevance, 10 per page; new or updated products searchable quickly.

**Non-functional.** p99 query latency within a few hundred milliseconds; writes durable once
acknowledged; survive the loss of one node.

**Capacity estimate.** Every input below is an **assumption** for this exercise, not a measured figure;
every result is reproduced by `test/lesson_code/capacity_check.py`.

| Input (assumed) | Value |
|---|---|
| documents | 200 million |
| average source size | 2 KB |
| on-disk index size relative to source | 1.5x (measure this on your own data) |
| target shard size | 40 GB |
| replicas per primary | 1 |
| peak search rate | 20,000 queries/s |
| peak write rate | 2,000 documents/s |
| CPU time per shard-level search | 2 ms of one thread |

| Result | Arithmetic | Value |
|---|---|---|
| raw source | 200M x 2 KB | 400 GB |
| primary index on disk | 400 GB x 1.5 | 600 GB |
| primary shards | ceil(600 / 40) | 15 |
| documents per shard | 200M / 15 | about 13.3 million |
| shard copies and total disk | 15 x 2; 600 GB x 2 | 30 copies, 1.2 TB |
| shard-level searches | 20,000 x 15 | 300,000 per second |
| search CPU | 300,000 x 2 ms | 600 cores busy; 1,000 cores at 60% target utilisation |
| same, with routing to one shard | 20,000 x 1 x 2 ms | 40 cores busy |
| indexing work | 2,000 x 2 copies | 4,000 document writes/s |

The shard size sits inside Elastic's guidance (aim for 10 GB to 50 GB per shard and keep each shard
below 200 million documents). The CPU line is the one to say aloud: **fan-out multiplies the cost of
every query by the number of shards**, which is why a per-tenant product should route by tenant.

Visual (planned): a coordinator node fanning a query out to 15 shard copies and merging 15 small top-10 lists into one.

---

## 4. API and Data Model

```
PUT  /products/_doc/{id}          body: {title, description, brand, price, updated_at}
GET  /products/_search            body: {query, filters, size, search_after?, pit?}
POST /products/_pit?keep_alive=1m returns a point-in-time id for stable deep paging
```

A document is routed to a shard by `shard_num = hash(_routing) % num_primary_shards`, where `_routing`
defaults to the document id. Because the shard count is in the formula, **the number of primaries is
effectively fixed for an index**; changing it means copying into a new index (the split and shrink APIs do this for you). Choose it from the
capacity estimate, not by habit.

Inside a shard the index is an **inverted index**: for each term, the documents that contain it and how
often. Lucene stores it as **segments**: immutable mini-indices. New documents go into a buffer, a
**refresh** writes the buffer out as a new segment and opens it for search, and **merges** combine small
segments into larger ones in the background.

---

## 5. Deep Dive 1: BM25, Built and Checked

BM25 scores document `D` for query terms `q` as the sum over terms of
`IDF(q) * f(q, D) * (k1 + 1) / (f(q, D) + k1 * (1 - b + b * |D| / avgdl))`,
with `IDF(q) = ln(1 + (N - n(q) + 0.5) / (n(q) + 0.5))`. `f` is the term's count in the document, `|D|` the
document's length, `avgdl` the average length, `N` the number of documents and `n(q)` how many contain
the term. Lucene's defaults are `k1 = 1.2` and `b = 0.75`. This is the textbook form of BM25; Lucene's
scorer does not use exactly this expression, so absolute scores in Elasticsearch's `_explain` output differ
from it by constant factors, but the ranking is the same.

Read the formula as two ideas: **rare terms count more** (IDF), and **repeating a term helps less and
less, more so in long documents** (the saturating fraction, normalised by length).

```python
import math, heapq
from collections import Counter, defaultdict

def tokenize(text):
    return text.lower().split()

class Index:
    """One shard: an inverted index of term -> {doc_id: term frequency}, plus document lengths."""
    def __init__(self):
        self.postings = defaultdict(dict)
        self.doc_len = {}

    def add(self, doc_id, text):
        toks = tokenize(text)
        self.doc_len[doc_id] = len(toks)
        for term, tf in Counter(toks).items():
            self.postings[term][doc_id] = tf

    def stats(self):
        """(document count, total length, {term: document frequency}): what this shard knows."""
        return len(self.doc_len), sum(self.doc_len.values()), {t: len(p) for t, p in self.postings.items()}

def idf(N, df):
    return math.log(1 + (N - df + 0.5) / (df + 0.5))

def bm25_top_k(index, query, k, stats=None, k1=1.2, b=0.75):
    """Top k hits as (-score, doc_id), best first; ties go to the smaller doc_id.
    stats: collection statistics to score with; None means this shard's own (local) statistics.
    Each distinct query term counts once."""
    N, total_len, df = stats or index.stats()
    if N == 0:
        return []
    avgdl = total_len / N
    scores = defaultdict(float)
    for term in set(tokenize(query)):
        w = idf(N, df.get(term, 0))
        for doc, tf in index.postings.get(term, {}).items():   # only documents that contain the term
            norm = k1 * (1 - b + b * index.doc_len[doc] / avgdl)
            scores[doc] += w * tf * (k1 + 1) / (tf + norm)
    return heapq.nsmallest(k, ((-s, d) for d, s in scores.items()))
```

The loop touches only the postings of the query's terms, never the whole collection: that is the point
of an inverted index. The check builds random collections and compares `bm25_top_k` with a brute-force
scorer that re-reads every document's text and applies the formula directly.

---

## 6. Deep Dive 2: Scatter-Gather and the Local-Statistics Trap

```python
def merge_stats(all_stats):
    df = Counter()
    for _, _, d in all_stats:
        df.update(d)
    return sum(s[0] for s in all_stats), sum(s[1] for s in all_stats), dict(df)

def distributed_top_k(shards, query, k, dfs=True):
    """Scatter-gather. dfs=True first collects statistics from every shard (a DFS round),
    so each shard scores with global statistics; dfs=False scores with each shard's own."""
    stats = merge_stats([s.stats() for s in shards]) if dfs else None
    partial = [bm25_top_k(s, query, k, stats) for s in shards]
    return heapq.nsmallest(k, [hit for part in partial for hit in part])
```

**Why `k` per shard is enough.** With global statistics a document's score does not depend on which
shard holds it. Any document in the global top `k` beats every document outside it, so it is also in
its own shard's top `k`. The check confirms `distributed_top_k(..., dfs=True)` equals the single-index
result on random collections and random shard counts.

**Worked example: local statistics change the winner.** Query `redis`, two shards:

| Shard | Documents |
|---|---|
| A | 1: `redis sorted sets`, 2: `redis persistence modes`, 3: `redis eviction policies` |
| B | 4: `tuning redis for a large kafka deployment`, 5: `kafka consumer groups`, 6: `kafka log compaction` |

With global statistics, `redis` appears in 4 of 6 documents; documents 1, 2 and 3 tie at 0.477 (short
documents) and document 4 scores less, because it is long. With local statistics, `redis` is in every
document of shard A (low IDF there) but only one of shard B (high IDF there), so document 4 scores 0.784
and wins, while document 1 scores 0.134. Same documents, same query, different winner, only because of
where the documents live. (The check recomputes these four numbers.)

Elasticsearch exposes exactly this choice as the `search_type` parameter: `query_then_fetch` scores with
each shard's local frequencies ("usually faster but less accurate"), and `dfs_query_then_fetch` first
gathers global frequencies ("usually slower but more accurate"). In an interview: say the default is local,
say when it hurts (few documents per shard, skewed routing), and say the fixes (more documents per shard,
fewer shards, or the DFS round). The model's DFS phase here sums counts, lengths and frequencies; it shows
the idea, not Elasticsearch's exact message format.

---

## 7. Deep Dive 3: Pagination Without Melting the Cluster

With `from` and `size`, each shard must produce its top `from + size` and the coordinator merges all of
them, then throws away `from`. Elastic's docs say each shard loads the requested hits and the hits for
every previous page into memory, and that `from + size` cannot exceed `index.max_result_window`, 10,000
by default.

| Request on 15 shards | Hits each shard returns | Hits the coordinator merges |
|---|---|---|
| page 1 (`from=0, size=10`) | 10 | 150 |
| page 1,000 (`from=9990, size=10`, the deepest the default window allows) | 10,000 | 150,000 |

The fix is a cursor. `search_after` passes the sort values of the last hit; each shard returns only the
next `size` hits after it, so every page costs the same. A unique tiebreaker in the sort keeps pages from
skipping or repeating hits, and a **point in time** keeps the view stable across refreshes.

```python
def page_after(shards, query, size, after=None, stats=None):
    """One page: the next `size` hits strictly after the cursor `after` (a (-score, doc_id) pair).
    Each shard sends at most `size` hits, whatever the page number."""
    hits = []
    for s in shards:
        ranked = bm25_top_k(s, query, len(s.doc_len), stats)    # a real shard seeks to the cursor
        hits.extend([h for h in ranked if after is None or h > after][:size])
    return heapq.nsmallest(size, hits)

def paginate(shards, query, size, stats=None):
    """All hits, page by page, using the last hit of each page as the next cursor."""
    pages, after = [], None
    while True:
        page = page_after(shards, query, size, after, stats)
        if not page:
            return pages
        pages.append(page)
        after = page[-1]
```

The `(-score, doc_id)` pair is the sort key and the tiebreaker at once. The check pages through random
collections and confirms the concatenated pages equal the full ranking, with no hit missing or repeated.

---

## 8. Freshness and Durability: Two Clocks

| Event | What happens | Default from Elastic's docs |
|---|---|---|
| index request | operation applied to the in-memory buffer and written to the **translog** | translog fsynced before the request is acknowledged (`index.translog.durability: request`), on the primary and every allocated replica |
| **refresh** | buffer written as a new segment and opened: now **searchable** | every 1 second, but only for indices that received a search in the last 30 seconds |
| **flush** | Lucene commit, new translog generation | automatic; also when unflushed operations reach 10 GB (`index.translog.flush_threshold_size`) |
| crash | acknowledged operations not in the last commit are replayed from the translog | |

So a write is **durable** when acknowledged (with the default) and **searchable** after the next refresh.
Switching durability to `async` fsyncs every `sync_interval` (5 seconds by default) and can lose the
operations since the last sync. At the assumed 2,000 writes/s, a 5-second window is up to 10,000 lost
acknowledged writes on a crash: a number worth saying when someone proposes `async` for speed.

Refreshing every second creates a new small segment each time on every shard that received writes; merging
those back into larger segments is constant background work. Deletes only mark documents, which keep
using resources until a merge removes them; for time-based data, Elastic recommends deleting whole indices.

---

## 9. Failure Modes

| Failure | Effect | Mitigation |
|---|---|---|
| node holding a primary dies | that shard's writes pause until a replica is promoted | at least one replica per primary, spread across nodes |
| hot shard from skewed routing (one huge tenant) | one shard slow, every query on it slow | route large tenants to their own index, or partition their routing |
| too many small shards (oversharding) | per-shard overhead, search thread pool exhausted by fan-out | size shards 10 GB to 50 GB; fewer, larger shards |
| deep `from` paging | memory and CPU spikes on every shard | cap at `max_result_window`; `search_after` with a point in time |
| mapping explosion (every field auto-mapped) | heap use per field and per segment grows | explicit mappings |
| slow query in a scatter-gather | the slowest shard sets the latency of every query | timeouts, fewer shards per query, replicas to spread load |

---

## 10. What Real Systems Document

From Elastic's own documentation (read 2026-11-26), which records the vendor's operating experience:

- **Shard sizing:** shards between 10 GB and 50 GB "typically work well", with under 200 million documents
  per shard; a shard can in theory hold just over two billion documents. Searching a thousand 50 MB shards is
  described as substantially more expensive than one 50 GB shard holding the same data.
- **One thread per shard per search:** each shard runs a search on a single CPU thread, so searches over many
  shards can deplete a node's search thread pool.
- **Master heap:** fewer than 3,000 indices per GB of heap on master nodes.
- **Scroll is no longer recommended for deep pagination;** use a point in time with `search_after`.

No company-specific architecture write-up was read for this revision, so none is described here.

---

## 11. Pitfalls Checklist

1. **Picking a shard count without a size estimate.** The primary count is baked into routing; derive it from data size.
2. **Forgetting that fan-out multiplies CPU.** Doubling shards doubles shard-level searches per query.
3. **Assuming scores are global.** Under the default, IDF is per shard; small or skewed shards rank inconsistently.
4. **Deep paging with `from`.** It costs `from + size` per shard; use `search_after` with a tiebreaker.
5. **Confusing searchable with durable.** Refresh makes data visible; the translog makes it durable.
6. **Proposing `async` translog durability without the data-loss window** (up to `sync_interval` of writes).
7. **Deleting documents from huge time-series indices** instead of dropping whole indices.
8. **A sort without a unique tiebreaker**, so pages skip or repeat hits.

---

## Drills

1. Write the BM25 term score from memory and say what `k1` and `b` each control.
2. Why does the inverted-index loop in `bm25_top_k` never look at documents that contain none of the query terms?
3. Prove that with global statistics, asking each shard for `k` hits is enough for the global top `k`.
4. In the worked example, why does document 4 win under local statistics, and which `search_type` fixes it?
5. Compute the hits merged by the coordinator for `from=5000, size=20` on 15 shards.
6. A write was acknowledged. When is it searchable, and what makes it survive a crash?
7. Your queries are always for one merchant's catalog. What do you change, and what does it save in the capacity table?
8. Why does `page_after` compare with `h > after` rather than `h >= after`?

---

## Homework

1. Extend `Index` with deletes as tombstones and a `merge()` that drops them; check that scores after merging
   match a fresh index built without the deleted documents.
2. Add a filter (`brand = X`) evaluated before scoring and measure how many postings entries the loop skips.
3. Redo the capacity estimate for log search: 2 TB of new data per day, 30 days retained, daily indices. How many
   shards per day, and how many in total?
4. Implement `dfs=False` paging and find a collection where pages under local statistics differ from pages under
   global statistics.
5. Read Elastic's "Size your shards" page end to end and list three settings you would monitor in production.

---

## Sources

All read 2026-11-26.

- Elastic, *Size your Elasticsearch shards*, elastic.co/docs/deploy-manage/production-guidance/optimize-performance/size-shards.
  Source for the 10 GB to 50 GB and 200 million document guidance, the two-billion theoretical limit, one thread per
  shard per search, per-segment and per-field heap overhead, deleting indices instead of documents, and the master heap rule.
- Elastic, *Near real-time search*, elastic.co/docs/manage-data/data-store/near-real-time-search (and the older
  elastic.co/guide/.../near-real-time.html, read through a summarising fetch). Source for segments, refresh, and the
  1 second and 30 second defaults.
- Elastic, *Translog* index settings, elastic.co/guide/en/elasticsearch/reference/current/index-modules-translog.html
  (read through a summarising fetch). Source for translog durability `request` and `async`, the 5 second sync interval,
  flush, and the 10 GB flush threshold.
- Elastic, *Paginate search results*, elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html
  (read through a summarising fetch). Source for `from`/`size`, the 10,000 `max_result_window`, `search_after`,
  point in time, tiebreakers and the scroll recommendation.
- Elastic, *_routing field*, elastic.co/docs/reference/elasticsearch/mapping-reference/mapping-routing-field. Source
  for the routing formula and the default routing value.
- Elastic, *Search API* reference, elastic.co/docs/api/doc/elasticsearch/operation/operation-search (the
  `search_type` parameter only). Source for `query_then_fetch` and `dfs_query_then_fetch`.
- Apache Lucene 9.9 Javadoc, *BM25Similarity*, lucene.apache.org/core/9_9_0/core/org/apache/lucene/search/similarities/BM25Similarity.html
  (read through a summarising fetch). Source for the defaults `k1 = 1.2`, `b = 0.75` and the IDF form.
- Wikipedia, *Okapi BM25*, en.wikipedia.org/wiki/Okapi_BM25 (read through a summarising fetch).
  Source for the full scoring formula.

## Further reading (not consulted)

Robertson and Zaragoza, *The Probabilistic Relevance Framework: BM25 and Beyond* (2009); the Lucene file-format
documentation for postings compression; Elastic's pages on shard allocation awareness and cross-cluster replication.
None were read for this revision.

*Last reviewed: 2026-11-26.*
