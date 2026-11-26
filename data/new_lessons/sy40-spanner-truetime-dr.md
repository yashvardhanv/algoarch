# Lesson 40 — Distributed Transactions, Spanner TrueTime & Multi-Region DR

> **Priority:** ★★★★★ — the senior-loop follow-up to any design with money or inventory across regions: "what happens to a transaction when a region dies?"
>
> **Study time:** 60 minutes. **Do this after:** Distributed Consensus & Raft, and Idempotency, Outbox & Sagas.
>
> **Level:** advanced. Optional for a crash plan; worth doing if your target loops probe distributed databases or multi-region architecture.

A transaction that touches two shards needs every shard to commit or none to. Two-phase commit does that,
and it has one famous weakness: a participant that has voted yes cannot decide alone. Spanner keeps two-phase
commit but makes every participant a replicated Paxos group, and adds a clock API that admits its own
uncertainty, which lets it give every transaction a timestamp consistent with real time. This lesson works
through the blocking case with a decision procedure you can check, simulates TrueTime's commit wait against
its invariant, and turns Spanner's published numbers and Google Cloud's documented configurations into a
disaster-recovery answer with RPO and RTO you can defend.

---

## 1. Mental Model

> **Atomic commit across shards is a decision that must survive failures. Make the decision-makers
> replicated (Paxos groups), and make timestamps honest about clock error (TrueTime intervals): then you can
> order transactions globally by waiting out the uncertainty instead of coordinating.**

What follows from it:

- **2PC blocks because the decision lives in one place.** A prepared participant that cannot reach the
  coordinator cannot know the outcome. Replicating the coordinator removes the single place.
- **A timestamp is only useful if it is consistent with real time.** Spanner's rule: if T1 commits before T2
  starts, T1's timestamp is smaller. Local clocks cannot promise that; an interval with a known error bound can.
- **The price of the guarantee is a wait of about twice the clock uncertainty.** Spanner's paper puts the average
  uncertainty at about 4 ms, so the wait is small, and it overlaps replication.
- **Disaster recovery is quorum placement.** Where the voting replicas sit decides write latency, what a region
  failure costs (RTO), and whether any acknowledged write can be lost (RPO).

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "transfer between accounts on different shards, all or nothing" | 2PC over replicated (consensus) participants, or a single-shard design if you can co-locate |
| "the coordinator crashed after prepare" | the termination rule below: who can decide, and when you are blocked |
| "reads must see every earlier committed write, anywhere" | external consistency: commit timestamps plus commit wait (Spanner) |
| "consistent snapshot / audit read across the whole database" | a read at a timestamp, served by replicas whose safe time has passed it |
| "survive a region outage with zero data loss" | synchronous quorum across regions (RPO zero), accept higher write latency |
| "cheap DR, some loss acceptable" | asynchronous replica in another region; RPO = replication lag x write rate |
| "long business process across services" | sagas, not 2PC (see the sagas lesson) |

---

## 3. Requirements and Capacity

**Scenario.** A payments ledger: transfers between accounts that may live on different shards; balances must
never be observed inconsistently; the service must survive the loss of a zone, and the business wants an answer
for the loss of a region.

**Numbers from the Spanner paper (OSDI 2012)** and **assumptions** (labelled). Every derived number is
reproduced by `test/lesson_code/capacity_check.py`.

| Quantity | Value | Source |
|---|---|---|
| clock uncertainty ε | sawtooth from about 1 to 7 ms per poll interval; about 4 ms average | paper, Section 3 |
| poll interval and drift rate | 30 s and 200 microseconds per second | paper, Section 3 |
| drift part of ε | 30 s x 200 us/s = 6 ms, plus about 1 ms communication delay = 7 ms peak | derived |
| expected commit wait | at least 2 x average ε = 8 ms | derived from the paper's rule |
| measured write latency, one replica, commit wait off vs on | 9.4 ms vs 14.4 ms: about 5 ms of added write latency (the paper does not give ε for that run) | paper, Table 3 |
| Paxos leader lease | 10 s by default | paper, Sections 2.1 and 4.1.1 |
| write rate (assumed) | 5,000 transactions/s | assumption |
| async replication lag at failure (assumed) | 2 s | assumption |
| data lost on failover to an async replica | 2 s x 5,000 = 10,000 committed transactions | derived |
| allowed downtime per year at 99.99% vs 99.999% | 52.56 vs 5.256 minutes | derived (525,600 minutes per year) |

The 2PC scalability table in the paper gives the cost of more participants (3 zones, 25 spanservers each):
mean latency 17.0 ms with 1 participant, 42.7 ms with 50, 71.4 ms with 100 and 150.5 ms with 200. The paper
calls 50 participants reasonable and says latency starts to rise noticeably at 100. Design to touch few shards.

---

## 4. API and Data Model

```
BEGIN; read balance(A); read balance(B); write A -= 100; write B += 100; COMMIT   -> commit_ts
READ  balances AT TIMESTAMP t          (snapshot read, lock-free, any sufficiently up-to-date replica)
READ  balances STRONG                  (read-only transaction at a timestamp chosen by the system)
```

- Each account row lives in one shard; each shard is a **Paxos group** of replicas in different zones or regions,
  with one long-lived leader holding a timed lease (10 s by default).
- A read-write transaction takes locks at the leaders (two-phase locking; reads use wound-wait to avoid deadlock),
  buffers its writes at the client, and commits with 2PC across the groups it touched.
- Every committed version carries its commit timestamp; old versions are kept for snapshot reads until garbage-collected.

---

## 5. Deep Dive 1: When 2PC Blocks, Exactly

In 2PC the coordinator asks each participant to **prepare**; a participant that votes yes promises to commit if
told to, and cannot change its mind. The coordinator commits only if every participant voted yes. Suppose the
coordinator becomes unreachable. What can a participant decide by asking the participants it can still reach?

```python
def termination(reachable, n_unreachable):
    """Coordinator unreachable. reachable: states of participants we can ask, each 'working' (has not voted),
    'prepared' (voted yes, waiting), 'aborted' or 'committed'. n_unreachable: other participants we cannot ask.
    Returns 'commit', 'abort' or 'blocked'. Reachable 'working' participants agree to abort when asked."""
    if 'committed' in reachable:
        return 'commit'              # only the coordinator's commit decision lets anyone commit
    if 'aborted' in reachable or 'working' in reachable:
        return 'abort'               # someone did not (or will not) vote yes, so commit is impossible
    return 'blocked'                 # everyone reachable is prepared: the decision may exist and be either
```

The check derives the same answers by brute force: it enumerates every hidden state of the unreachable
participants and every possible coordinator decision consistent with the protocol, and calls an outcome safe
only if it holds in every consistent world. The important row: **if every participant you can reach is prepared,
you are blocked**, even with zero unreachable participants, because the coordinator may have decided either way
and told no one. Locks stay held until the coordinator returns.

**Spanner's answer is not a new commit protocol.** Each participant and the coordinator is a Paxos group: a
participant leader logs its prepare record through Paxos, and the coordinator leader logs the commit (or abort)
record through Paxos. The decision is therefore replicated state, not one machine's memory, so losing a leader
means electing another one that has the log, not waiting for a crashed machine to come back. The paper notes Gray and Lamport's Paxos-based non-blocking commit costs more
messages than 2PC, which matters over wide-area links; layering 2PC over Paxos groups keeps 2PC's message
pattern and gets availability from replication.

---

## 6. Deep Dive 2: TrueTime and Commit Wait, Simulated

TrueTime's `TT.now()` returns an interval `[earliest, latest]` guaranteed to contain the absolute time;
`TT.after(t)` is true once `t` has definitely passed. Spanner's two rules for a read-write transaction `T`:

- **Start:** the coordinator leader assigns a commit timestamp `s` no less than `TT.now().latest` computed after the
  commit request arrives (and above any timestamp it assigned before).
- **Commit wait:** no client may see `T`'s data until `TT.after(s)` is true.

Together they give the **external consistency invariant**: if `T1` commits (in absolute time) before `T2` starts,
then `s1 < s2`. The proof is four lines: `s1 < commit time of T1` (commit wait), `commit of T1 < start of T2`
(assumption), `start of T2 <= arrival of T2's commit request` (causality), `arrival <= s2` (start rule).

```python
def tt_now(abs_time, offset, eps):
    """TrueTime on a server whose clock reads abs_time + offset, with |offset| <= eps (integer microseconds)."""
    local = abs_time + offset
    return local - eps, local + eps

def tt_after(t, abs_time, offset, eps):
    return tt_now(abs_time, offset, eps)[0] > t

def commit(arrival, offset, eps, last_ts, paxos_done):
    """Coordinator leader. arrival: absolute time the commit request arrives; last_ts: the leader's last timestamp;
    paxos_done: absolute time the commit record is replicated. Returns (s, absolute time T becomes visible)."""
    s = max(tt_now(arrival, offset, eps)[1], last_ts + 1)          # start rule, monotonic per leader
    visible = s - offset + eps + 1                                 # first instant with tt_after(s) true
    return s, max(visible, paxos_done)                             # the wait overlaps Paxos replication
```

The check simulates hundreds of transactions arriving at servers whose clocks are off by random amounts within
`eps`, with random replication delays, and confirms on every pair that commit-before-start implies a smaller
timestamp. It also confirms that each wait, measured from arrival to the moment `TT.after(s)` holds, is
`2 * eps + 1` microseconds when the start rule picks `TT.now().latest`: the "expected wait is at least 2ε" of the
paper, at integer resolution. Remove the commit wait, or take `s` from the local clock instead of `latest`, and
the check finds a pair that breaks the invariant.

**Reads.** A replica can serve a read at timestamp `t` if `t <= t_safe`, the minimum of the highest applied Paxos
write's timestamp and (if a transaction is prepared but not committed) just below the earliest prepare timestamp.
A strong read-only transaction gets `s_read = TT.now().latest` and may wait for `t_safe` to catch up; no locks, so
writes are not blocked. An idle Paxos group advances its safe time through `MinNextTS`, by default every 8 seconds,
so in the worst case an idle healthy replica can serve reads more than 8 seconds old.

**Why the uncertainty is small.** Each datacenter has time masters, most with GPS receivers and some with atomic
clocks ("Armageddon masters"), chosen because their failure modes differ. Every machine's daemon polls several
masters, rejects liars with a variant of Marzullo's algorithm, and between polls widens ε by a conservative drift
rate. Machines whose clocks drift beyond the bound are evicted. The paper reports bad CPUs as 6 times more likely
than bad clocks, and describes a roughly hour-long rise in ε when 2 time masters in a datacenter were shut down for
maintenance.

---

## 7. Deep Dive 3: Multi-Region DR, With the Numbers Written Down

| Strategy | RPO (data lost) | RTO (time to recover) | Write latency floor |
|---|---|---|---|
| async replica in another region | replication lag x write rate: 10,000 transactions in the assumed scenario | promote the replica and repoint clients; measure your own | local |
| Spanner regional (3 read-write replicas in 3 zones) | zero (follows from the synchronous quorum; not stated in the docs read) | the database stays available if one zone fails | in-region quorum |
| Spanner dual-region (6 replicas, 3 per region, writes need 2 voting replicas in each region) | zero: Google's docs say no data loss during a regional outage | manual failover to one region usually completes within a minute; Google-managed automatic failover can take up to 45 minutes | cross-region round trip |
| Spanner multi-region (two read-write regions plus a witness, in most configurations) | zero (follows from the synchronous quorum; not stated in the docs read) | automatic leader failover during regional disruptions | cross-region round trip to form a quorum |

The documented availability targets are 99.99% for regional and 99.999% for dual- and multi-region configurations:
52.56 versus 5.256 minutes of allowed downtime a year. Google's DR page also lists the logical failures replication
does not fix: point-in-time recovery within the last 7 days, backups retained up to one year, cross-region backup
copies, and deletion protection. **Replication protects against losing machines; backups and PITR protect against
your own bad writes.** Say both.

How commit wait and distance interact: the wait (about 2ε, overlapped with Paxos) dominates when replicas are close,
and the round trip dominates when they are far. The paper's future-work section says TrueTime may noticeably affect
performance for applications replicating across nearby datacenters, which is the same point.

What the paper's availability experiment shows: with all leaders in one zone and that zone killed without warning,
throughput drops almost to zero until leases expire; because leases are 10 seconds, all groups had new leaders about
10 seconds after the kill. With a soft kill (leaders told to hand off first), the drop was around 3 to 4 percent.
**Planned failover should hand off leadership first.**

Visual (planned): a timeline of one transaction: commit request arrives, s = TT.now().latest, Paxos replication and commit wait overlapping, TT.after(s) becomes true, locks released.

---

## 8. Failure Modes

| Failure | Effect | Mitigation |
|---|---|---|
| 2PC coordinator lost, participants prepared | blocked, locks held | coordinator as a replicated group; a new leader finishes the commit |
| leader zone lost without warning | writes to its groups stall until leases expire (10 s by default) | spread leaders; hand off leadership before planned maintenance |
| clock uncertainty spikes (time master outage, overload) | commit waits grow, write latency rises | multiple masters per datacenter, mixed GPS and atomic references; monitor ε |
| prepared transaction holds safe time back | reads at later timestamps wait | fine-grained safe time per key range (the paper's refinement) |
| hot shard or too many participants | 2PC latency rises with participant count | co-locate data that is written together; keep transactions small |
| logical corruption replicated everywhere | every replica is wrong at once | point-in-time recovery, backups, deletion protection |
| network partition between the two regions of a dual-region setup | both regions look healthy, writes cannot form a quorum | Google's docs: fail over manually to the default leader region, fail back later |

---

## 9. What Real Systems Did (Dated)

- **Google F1 (paper, 2012):** the advertising backend moved from manually sharded MySQL, whose last resharding took
  over two years, to Spanner, with 5 replicas (2 on the US west coast, 3 on the east coast). In 24 hours of
  F1-perceived measurements, single-site commits averaged 72.3 ms and multi-site commits 103.0 ms.
- **Google Cloud Spanner (docs, read 2026-11-26):** external consistency by default under serializable isolation; the
  docs explain it with a deposit then a debit that must never be seen in the other order, and describe it as stronger
  than linearizability (which says nothing about transactions) and than serializability (which allows reordering).

---

## 10. Pitfalls Checklist

1. **Saying 2PC "cannot handle coordinator failure" without the precise case**: blocked only when everyone you can reach is prepared.
2. **Saying TrueTime gives exact time.** It gives an interval; the guarantee comes from waiting it out.
3. **Forgetting the start rule.** Commit wait alone is not enough: `s` must be at least `TT.now().latest` at arrival.
4. **Quoting "zero RPO" for an async replica.** RPO is lag times write rate.
5. **Ignoring the lease in RTO.** A hard leader loss costs up to the lease length.
6. **Replication as backup.** A bad write replicates perfectly; you still need PITR and backups.
7. **Many-shard transactions.** 2PC latency grows with participants; design for few.
8. **Confusing linearizability with external consistency** in a transactional system.

---

## Drills

1. All three participants you can reach are prepared and none is unreachable. What does `termination` return, and why can you not commit?
2. Write the four-line proof that commit wait plus the start rule give `s1 < s2`.
3. In `commit`, why is `visible` equal to `s - offset + eps + 1`, and what is the wait from arrival?
4. With ε at its 7 ms peak, what is the minimum commit wait? Where does the 7 ms come from?
5. Why can a read-only transaction run without locks, and what can make it wait?
6. A business asks for RPO zero and RTO under a minute across regions. Which configuration, and what does each write pay?
7. An async standby lags 2 s at 5,000 writes/s. What is lost on failover?
8. Why does the paper's leader-hard experiment take about 10 seconds to recover?

---

## Homework

1. Extend the TrueTime simulation with read-only transactions at `TT.now().latest` and check they see every transaction
   committed before they started.
2. Model `t_safe` for one Paxos group with prepared transactions and test that a read at `t <= t_safe` never misses a later commit.
3. Change `termination` so that a reachable participant can also learn the decision from the coordinator's replicated log, and
   show when blocking disappears.
4. Design the payments ledger's placement: which accounts share a shard, where leaders live, and the expected participants per transfer.
5. Read Sections 3 and 4 of the Spanner paper and redo Drill 4 from the paper's numbers alone.

---

## Sources

All read 2026-11-26.

- Corbett et al., *Spanner: Google's Globally-Distributed Database*, OSDI 2012,
  usenix.org/system/files/conference/osdi12/osdi12-final-16.pdf (read in full as extracted text; tables and figures
  came through as text, so Figure 5 and 6 values were not read). Source for TrueTime, the start and commit-wait rules
  and proof, leases, safe time, MinNextTS, read-only transactions, 2PC over Paxos, Tables 3, 4 and 6, the
  availability experiment, the TrueTime reliability observations and the F1 case study.
- Google Cloud, *Spanner: TrueTime and external consistency*, cloud.google.com/spanner/docs/true-time-external-consistency.
  Source for the banking example and the comparisons with linearizability, serializability and strong consistency.
- Google Cloud, *Regional, dual-region, and multi-region configurations*, cloud.google.com/spanner/docs/instance-configurations
  (regional, dual-region and the start of the multi-region sections). Source for replica layouts, quorum rules, failover
  times, availability figures and zero RPO for dual-region only.
- Google Cloud, *Disaster recovery overview*, cloud.google.com/spanner/docs/backup/disaster-recovery-overview. Source for
  PITR (7 days), backup retention (one year), cross-region backup copies, deletion protection and 99.999% for multi-region.

## Further reading (not consulted)

Gray and Lamport, *Consensus on Transaction Commit* (2006); Skeen's three-phase commit; Corbett et al.'s later Spanner
papers; CockroachDB's documentation on hybrid logical clocks; Jepsen analyses of distributed databases. None were read for this revision.

*Last reviewed: 2026-11-26.*
