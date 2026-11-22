# Lesson 38 — Real-Time Collaborative Whiteboard & Docs (Google Docs / Figma)

> **Priority:** ★★★★★ (Google, Figma, Canva, Atlassian, Microsoft standard loop)  
> **Estimated Study Time:** 60 minutes  
> **Key Skills:** Operational Transformation (OT) vs Conflict-Free Replicated Data Types (CRDTs - Yjs/Automerge), WebSocket state syncing, Presence broadcasting, Undo/Redo stacks.

---

## 1. The Core Problem: Concurrent Conflicting Edits

User A and User B both see the document `"CAT"`.
- User A inserts `'H'` at index 0 (intending `"CHAT"`).
- User B inserts `'S'` at index 3 (intending `"CATS"`).
- If both send raw positional commands without synchronization:
  - User A gets: `"CHAT"` -> inserts `'S'` at index 3 -> `"CHAST"` (Corrupted).
  - User B gets: `"CATS"` -> inserts `'H'` at index 0 -> `"HCATS"` (Different state!).
- **Requirement:** Eventual consistency without data loss, preserving user intention, with sub-50ms local typing latency.

---

## 2. Operational Transformation (OT) vs CRDTs

| Dimension | Operational Transformation (OT) | CRDTs (Conflict-Free Replicated Data Types) |
|---|---|---|
| **Pioneered By** | Google Docs, Apache Wave | Figma, Apple Notes, Yjs, Automerge |
| **Topology** | **Centralized Server Required** (linearizes all operations) | **Decentralized / Peer-to-Peer** or Server-Assisted |
| **Mechanics** | Transforms client operation indexes against concurrent server operations | Assigns globally unique fractional positional IDs (e.g. Logoot, RGA, LWW-Set) |
| **Offline Editing** | High complexity; heavy divergence causes transformation matrix explosion | Seamless local merges; mathematical proof of eventual convergence without server arbiter |
| **Memory Overhead** | Low (tombstones cleared quickly) | Higher (characters need unique UUIDs + logical clocks) |

---

## 3. High-Level Architecture (Figma / Modern Collaborative App)

```
[Client 1] ──WebSocket──┐
                        ├──► [WebSocket Gateway & Presence Node]
[Client 2] ──WebSocket──┤             │
                        │             ▼
[Client 3] ──WebSocket──┘    [Document Room State Manager]
                                     │
                     ┌───────────────┴───────────────┐
                     ▼                               ▼
             [Redis Pub/Sub]             [Snapshot Worker / S3]
     (Broadcasts cursor coordinates,     (Periodically compacts
      selection boxes, CRDT ops)          CRDT log to durable disk)
```

---

## 4. Staff L5 Interview Rubric

- **Rejected (L3/L4):** Proposes sending the entire document string over WebSocket on every keystroke, or suggests locking the document during edits.
- **Hire (L4/L5):** Distinguishes between OT and CRDTs; explains why OT requires a central server to assign total order; models cursor presence over lightweight UDP/WebSockets separated from durable document operations.
- **Strong Hire (L5+):** Explains fractional indexing in CRDTs (e.g., generating position `0.5` between `0` and `1`); solves the interleaving dilemma (two users typing simultaneously at the same index having distinct user-ID tiebreakers); explains tombstoning for deletions and snapshot compaction to prevent memory leaks.
