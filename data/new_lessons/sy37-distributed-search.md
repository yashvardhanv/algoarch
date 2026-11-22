# Lesson 37 — Case Study: Distributed Search Engine (Elasticsearch at Scale)

> **Priority:** ★★★★★ (Meta, Uber, Amazon, Databricks Infrastructure Bar)  
> **Estimated Study Time:** 60 minutes  
> **Key Skills:** Inverted index internals, Term dictionary & Postings list with Roaring Bitmaps, BM25 ranking algorithm, Sharding & segment merging (LSM-style), Distributed Query Coordinator.

---

## 1. System Requirements & Napkin Math

- **Scale:** 500 Million documents; 1 KB average text content.
- **Traffic:** 25,000 search queries / sec (QPS); 5,000 document writes/updates / sec.
- **SLA:** p99 query latency < 100ms; near-real-time indexation (visible within 1 second).
- **Storage:** 500M * 1KB = 500 GB raw text. With inverted index, term vectors, and doc values (2.5x overhead) = ~1.25 TB per replica. With 3x replication = 3.75 TB total SSD storage.

---

## 2. Inverted Index Data Structures

```
Document 1: "distributed systems fault tolerance"
Document 2: "high throughput distributed caching"

Term Dictionary (B-Tree or FST in RAM)
├── "caching"     ──> Postings List: [Doc 2 (pos: 4)]
├── "distributed" ──> Postings List: [Doc 1 (pos: 1), Doc 2 (pos: 3)]
├── "fault"       ──> Postings List: [Doc 1 (pos: 3)]
├── "high"        ──> Postings List: [Doc 2 (pos: 1)]
├── "systems"     ──> Postings List: [Doc 1 (pos: 2)]
└── "throughput"  ──> Postings List: [Doc 2 (pos: 2)]
```

### Postings List Compression: Roaring Bitmaps & Frame of Reference (FOR)
Raw list of integer Document IDs `[104, 108, 115, 240]` is stored as **delta values** `[+104, +4, +7, +125]`. Deltas are bit-packed using Roaring Bitmaps, allowing billion-doc boolean intersections (`AND` / `OR`) using hardware SIMD bitwise operations at microsecond speeds.

---

## 3. Distributed Architecture & Query Lifecycle

```
Client
  │
  ▼
API Gateway / Load Balancer
  │
  ▼
[Query Coordinating Node]
  │  (Scatter Phase)
  ├───► Shard 0 Replica (Executes BM25 match, returns top 10 Doc IDs + Scores)
  ├───► Shard 1 Replica (Executes BM25 match, returns top 10 Doc IDs + Scores)
  └───► Shard 2 Replica (Executes BM25 match, returns top 10 Doc IDs + Scores)
  │
  ▼
[Query Coordinating Node] (Merge & Rank top 10 globally)
  │  (Gather Phase: Fetch Source Documents by ID)
  ├───► Fetch Document 42 from Shard 0
  └───► Fetch Document 89 from Shard 2
  │
  ▼
Return enriched search results to Client (total latency < 45ms)
```

---

## 4. Staff L5 Interview Traps

> ⚠️ **The Deep Pagination Trap:**  
> Asking for page 1,000 with page size 10 (`from=10000, size=10`): Every shard must score and sort **10,010 documents**, transmit them across the network to the coordinator, and the coordinator sorts `Num_Shards * 10,010` documents before throwing away 10,000!  
> **L5 Solution:** Enforce `search_after` (cursor-based pagination using the last seen document's sort value and doc ID), eliminating the `O(N * K)` heap memory blowup.
