# Lesson 39 — Real-Time Gaming Leaderboard at 10M QPS

> **Priority:** ★★★★☆ (Riot, Dream11, Supercell, Ride-Hailing, FinTech)  
> **Estimated Study Time:** 50 minutes  
> **Key Skills:** Redis Sorted Sets (Skiplist + Hash), Memory Sharding by Score Bands, Timestamp Tie-Breaking, Write-Behind Caching, WebSocket Push.

---

## 1. Scale & Requirements

- **Users:** 50 Million registered players; 2 Million concurrent active players.
- **Traffic:** 200,000 score updates / sec; 1,000,000 rank query requests / sec.
- **Latency:** Query user rank + Top 100 within < 10ms.

---

## 2. Core Storage Engine: Redis Sorted Set (ZSET) Internals

Redis ZSET uses two simultaneous data structures:
1. **Hash Table:** Maps `member -> score` in `O(1)` for score lookups and updates.
2. **Skip List (Probabilistic Balanced Tree):** Stores members sorted by score. Each node has random forward pointers with `p = 0.25`, achieving `O(log N)` search, insertion, deletion, and rank calculation (`ZRANK`, `ZREVRANGE`).

### Tie-Breaking with Timestamp Packing
When two users have identical scores (e.g. 1500 points), who ranks higher? The player who achieved it earlier!
Since Redis ZSET accepts a 64-bit IEEE double float:
`Combined_Score = Score + (1.0 - (Timestamp / 10^12))`
Users with equal score will have higher floating fraction if their timestamp is lower, guaranteeing strict deterministic ordering without extra database lookups.

---

## 3. Sharding for Millions of QPS

A single Redis instance maxes out around 80,000-100,000 QPS. To serve 1M+ QPS:
- **Read Replicas:** 10 Read Replicas fronted by HAProxy/Envoy easily absorb 1M rank read queries.
- **Score-Range Sharding:** Partition players by tier:
  - Shard 1: Scores 0 - 999 (Bronze)
  - Shard 2: Scores 1000 - 2499 (Silver / Gold)
  - Shard 3: Scores 2500+ (Diamond / Global Elite)
- A global coordinator computes rank by summing the cardinality (`ZCARD`) of all higher tier shards plus the user's offset in their own shard.
