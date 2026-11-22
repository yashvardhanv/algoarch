# Lesson 40 — Distributed Transactions, Spanner TrueTime & Multi-Region DR

> **Priority:** ★★★★★ (The definitive Staff Engineer / L5-L6 Distributed Systems Bar)  
> **Estimated Study Time:** 60 minutes  
> **Key Skills:** Two-Phase Commit (2PC) blocking failure analysis, Three-Phase Commit (3PC), Google Spanner TrueTime API & GPS/Atomic clock hardware, Paxos replication, Multi-region Active-Active failover.

---

## 1. Why Traditional 2PC Blocks (The Fatal Coordinator Flaw)

In standard Two-Phase Commit (2PC):
1. **Prepare Phase:** Coordinator asks all participants: "Can you commit?" All say "YES" and write locks to disk.
2. **Commit Phase:** Coordinator broadcasts "COMMIT".
- **The Crash Failure Mode:** If the coordinator crashes *after* participants reply "YES" but *before* broadcasting "COMMIT", **all participants are blocked indefinitely with row locks held**. They cannot abort (the coordinator might have sent COMMIT to someone else) and cannot commit (the coordinator might have decided ABORT).

---

## 2. Google Spanner's Breakthrough: TrueTime + Paxos

Spanner combines two layers:
1. **Paxos Groups:** Every shard is replicated across datacenters via Paxos. A participant or coordinator is never a single server; it is a fault-tolerant Paxos group! If the leader crashes, another Paxos replica takes over instantly.
2. **TrueTime API:** Returns `[earliest, latest]` timestamp interval with guaranteed bounded uncertainty `epsilon` (typically <= 7ms).
   - Driven by GPS receivers and atomic clocks across Google data centers.
   - **Commit Wait Rule:** When a transaction commits at time `s`, the coordinator waits until `TrueTime.now().earliest > s` before releasing locks and making data visible.
   - **Result:** Strict serializability and external consistency across globally distributed continents without central timestamp coordination bottlenecks!

---

## 3. Active-Active Multi-Region Disaster Recovery Matrix

| Strategy | RPO (Recovery Point Objective - Data Loss) | RTO (Recovery Time Objective - Downtime) | Trade-Off |
|---|---|---|---|
| **Active-Passive (Async DB Replication)** | Seconds to Minutes of recent transactions lost | 5 to 15 Minutes (DNS switch + DB promote) | Cheap, but replication lag loses data |
| **Active-Passive (Sync Replication)** | 0 (Zero data loss) | 1 to 3 Minutes (Automated failover) | High write latency (limited by cross-region RTT) |
| **Active-Active (Spanner / CockroachDB / Multi-Leader)** | 0 (Zero data loss) | Sub-second (Traffic routed via Anycast DNS / BGP) | Requires multi-region consensus and strict conflict resolution |
