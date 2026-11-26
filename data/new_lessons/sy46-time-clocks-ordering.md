# Lesson 46 — Time, Clocks and Ordering

> **Priority:** ★★★★☆ (proposed; the curriculum data holds the final rating) — every "who wins when two writes conflict?" and "is this read allowed to be stale?" question is a question about ordering without a shared clock.
>
> **Study time:** 60 minutes. **Do this after:** Replication & Sharding, and CAP Theorem to PACELC. Distributed Consensus & Raft is the natural next step.
>
> **Level:** core.

Two machines cannot agree on what time it is, and a message takes longer to arrive than the gap between two events. So "which write came first?" has no answer you can read off a clock. CAP, PACELC and the consistency ladder name the guarantees; this lesson builds the machinery under them. You will implement three kinds of logical timestamp and measure what each one gets right, reproduce the version-vector example from the Dynamo paper, watch last-writer-wins throw away a write that a user had read, and write a small linearizability checker that tells a stale read from a legal one. Every figure comes from code in this file, checked against brute force.

---

## 1. Mental Model

> **Without a shared clock, the only order a system can know is the order information could have travelled. Event `a` happened before event `b` if a chain of steps within a process and messages between processes leads from `a` to `b`. Every other pair is concurrent. A timestamp is a promise about how much of that structure it preserves.**

What follows from it:

- **A wall clock preserves none of it.** Two nodes' clocks disagree by an unknown amount, so a later, causally dependent write can carry the smaller timestamp.
- **A Lamport clock preserves one direction.** If `a` happened before `b`, then `L(a) < L(b)`. The reverse is false: a smaller number does not mean "earlier" or "caused".
- **A vector clock preserves the whole relation** at the price of one counter per node. It can say "concurrent", which is the only way to detect a real conflict.
- **A hybrid logical clock (HLC) keeps the Lamport direction and stays close to physical time,** in a single 64-bit-sized value. It cannot say "concurrent" either.
- **Linearizability is a different kind of statement.** It is about the **real-time order of operations**, and it is a property of a recorded history, not of any timestamp. You test it by searching, and the search is exponential in the worst case.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "two replicas accepted conflicting writes, who wins?" | decide whether losing a write is acceptable; if not, version vectors and surface the conflict |
| "last-write-wins" | name its price (a causally later write can lose) and say which clock stamps it |
| "order all events consistently across nodes" | Lamport timestamp with a node-id tie-break |
| "detect concurrent updates" | version vector or vector clock |
| "timestamps readable as dates, but causally safe" | hybrid logical clock |
| "a read must never return older data than a completed write" | that is linearizability: a leader, a quorum with care, or consensus; clocks alone do not give it |
| "total order of one entity's events" | a sequencer (one leader, a log offset, a version column), not timestamps |
| "external consistency across data centres" | bounded clock uncertainty plus waiting (see the Spanner lesson), not NTP |

---

## 3. Deep Dive 1: Last-Writer-Wins on Skewed Clocks

The HLC paper (read 2026-11-26) summarises the practical state of physical time. NTP can usually hold clocks within tens of milliseconds over the public internet, and about a millisecond on a local network under ideal conditions; asymmetric routes and congestion can cause errors of 100 ms or more; and leap seconds and non-monotonic updates can make timestamps go backwards. Last-writer-wins (LWW) resolves a conflict by keeping the write with the larger timestamp. When the stamp is a physical clock, here is what that does:

```python
def lww_scenario():
    """Node A's clock is right. Node B's clock is 300 ms slow. B reads A's write, then writes its own."""
    write_a = (10_000, 'cart=[book]')                    # A writes at true time 10,000 (wall stamp 10,000)
    # B receives it at true time 10,020 (its clock reads 9,720) and writes at true time 10,100 (reads 9,800)
    write_b = (10_100 - 300, 'cart=[book,pen]')
    wall_winner = max(write_a, write_b)[1]

    h_a = hlc_send((0, 0), 10_000)                       # the same story with hybrid logical clocks
    h_b = hlc_recv((0, 0), h_a, 10_020 - 300)
    h_b_write = hlc_send(h_b, 10_100 - 300)
    hlc_winner = max((h_a, 'cart=[book]'), (h_b_write, 'cart=[book,pen]'))[1]
    return wall_winner, hlc_winner
```

The wall-clock winner is `cart=[book]`. The user's second edit was made **after reading the first and 100 ms later in real time**, yet it loses silently, with no error and no conflict flagged. The HLC winner is `cart=[book,pen]`, because B's clock, on receiving A's message, moved past A's stamp (the HLC functions are in section 4).

How often does this bite? That depends on skew against the gap between causally related events, so measure it. The simulation in section 4 runs random executions on four nodes, with physical clocks offset from true time and never going backwards, and counts causally ordered pairs of events whose wall timestamps are **not** increasing (100 runs of 60 steps each, offsets as listed):

| Spread of clock offsets | Causally ordered pairs | Wall stamps out of order | Share |
|---|---|---|---|
| 0 ms | 100,496 | 0 | 0.0% |
| 5 ms | 100,496 | 68 | 0.1% |
| 75 ms | 100,496 | 4,386 | 4.4% |
| 350 ms | 100,496 | 23,733 | 23.6% |

With perfect clocks the wall timestamp is a fine order; the error grows with skew relative to how close together causally related events are. The step sizes are a modelling choice (a few milliseconds between events), so read the table as the shape of the effect, not as a forecast for a particular system. The rule that follows: **LWW with wall clocks is safe only where losing a write is acceptable** (a "last seen" field, a cache), and the stamp should be a logical or hybrid clock where causality matters.

---

## 4. Deep Dive 2: Happened-Before and Three Logical Timestamps

Lamport's paper (read 2026-11-26) defines "happened before" without any physical clock: events in one process are ordered; sending a message happens before receiving it; and the relation is transitive. Two events neither of which happened before the other are **concurrent**: neither could have affected the other. The paper gives clocks that satisfy the **Clock Condition** (if `a` happened before `b`, then `C(a) < C(b)`) using two rules: a process increments its clock between any two events, and on receiving a message it sets its clock above the message's timestamp. Putting that into code, with the vector clock and the hybrid logical clock from the HLC paper (its Figure 5) next to it:

```python
import random

def lamport_tick(l):                       # local or send event
    return l + 1

def lamport_recv(l, lm):                   # receive a message stamped lm
    return max(l, lm) + 1

def vc_tick(v, i):                         # vector clock of node i
    v = list(v)
    v[i] += 1
    return tuple(v)

def vc_recv(v, vm, i):
    return vc_tick(tuple(max(a, b) for a, b in zip(v, vm)), i)

def vc_leq(a, b):
    return all(x <= y for x, y in zip(a, b))

def vc_relation(a, b):
    """'equal', 'before', 'after' or 'concurrent'."""
    if a == b:
        return 'equal'
    if vc_leq(a, b):
        return 'before'
    if vc_leq(b, a):
        return 'after'
    return 'concurrent'

def hlc_send(state, pt):
    """Hybrid logical clock, send or local event. state is (l, c); pt is this node's physical clock."""
    l0, c0 = state
    l = max(l0, pt)
    return (l, c0 + 1 if l == l0 else 0)

def hlc_recv(state, msg, pt):
    l0, c0 = state
    lm, cm = msg
    l = max(l0, lm, pt)
    if l == l0 == lm:
        c = max(c0, cm) + 1
    elif l == l0:
        c = c0 + 1
    elif l == lm:
        c = cm + 1
    else:
        c = 0
    return (l, c)
```

The HLC keeps `l` as the largest physical time the node has heard of, and uses the counter `c` only to order events that share an `l`; when physical time moves past `l`, the counter resets, which is what keeps it small. The paper shows why the obvious version (`max(l + 1, pt)`) lets the clock drift from physical time without bound in a messaging loop, and proves that `l` stays at or above the physical clock and that, whenever it is above, it equals the physical time of some event that happened before it (Theorems 2 and 3).

To measure the clocks you need ground truth. The simulation below records every event with all four timestamps and, separately, the **set of events that happened before it** (a bitmask built from the two edge kinds). Physical clock of node `i` is true time plus a fixed offset:

```python
def simulate(seed, n=4, steps=60, offsets=(0, 40, -35, 10)):
    """Random executions. Each event gets a wall, Lamport, vector and HLC timestamp, plus `before`:
    a bitmask of every event that happened before it (via process order and send -> receive)."""
    rng = random.Random(seed)
    t = 1000
    lam, vec, hlc = [0] * n, [(0,) * n for _ in range(n)], [(0, 0)] * n
    last, inflight, events = [None] * n, [], []

    def add(node, kind, src=None):
        before = 0
        for p in (last[node], src):
            if p is not None:
                before |= events[p]['before'] | (1 << p)
        events.append(dict(id=len(events), node=node, kind=kind, src=src, wall=t + offsets[node],
                           lamport=lam[node], vector=vec[node], hlc=hlc[node], before=before))
        last[node] = len(events) - 1
        return last[node]

    for _ in range(steps):
        t += rng.randint(1, 5)
        i = rng.randrange(n)
        pt = t + offsets[i]
        mine = [m for m in inflight if m['to'] == i]
        if mine and rng.random() < 0.5:
            m = rng.choice(mine)
            inflight.remove(m)
            lam[i] = lamport_recv(lam[i], m['lamport'])
            vec[i] = vc_recv(vec[i], m['vector'], i)
            hlc[i] = hlc_recv(hlc[i], m['hlc'], pt)
            add(i, 'receive', m['send'])
        else:
            lam[i], vec[i], hlc[i] = lamport_tick(lam[i]), vc_tick(vec[i], i), hlc_send(hlc[i], pt)
            ev = add(i, 'local')
            if rng.random() < 0.6:
                j = rng.choice([x for x in range(n) if x != i])
                events[ev]['kind'] = 'send'
                inflight.append(dict(to=j, send=ev, lamport=lam[i], vector=vec[i], hlc=hlc[i]))
    return events

def happened_before(events, a, b):
    return bool(events[b]['before'] >> a & 1)

def total_order(events):
    """Lamport's total order: by timestamp, ties broken by node id."""
    return sorted(events, key=lambda e: (e['lamport'], e['node']))
```

Messages can be delivered out of order, as in the paper's model. The check recomputes happened-before with a separate depth-first search over the same edges and requires the bitmask to agree. Now count, over 100 runs (offsets 0, +40, -35, +10 ms, so a 75 ms spread):

```python
def survey(runs=100, **kw):
    out = dict(ordered=0, concurrent=0, wall_wrong=0, lamport_wrong=0, hlc_wrong=0, vector_wrong=0,
               lamport_orders_concurrent=0)
    for seed in range(runs):
        ev = simulate(seed, **kw)
        for b in range(len(ev)):
            for a in range(b):
                if happened_before(ev, a, b):
                    out['ordered'] += 1
                    out['wall_wrong'] += ev[a]['wall'] >= ev[b]['wall']
                    out['lamport_wrong'] += not ev[a]['lamport'] < ev[b]['lamport']
                    out['hlc_wrong'] += not ev[a]['hlc'] < ev[b]['hlc']
                    out['vector_wrong'] += vc_relation(ev[a]['vector'], ev[b]['vector']) != 'before'
                else:
                    out['concurrent'] += 1
                    out['lamport_orders_concurrent'] += ev[a]['lamport'] != ev[b]['lamport']
                    out['vector_wrong'] += vc_relation(ev[a]['vector'], ev[b]['vector']) != 'concurrent'
    return out

def skew_sweep(runs=100):
    """(spread in ms, causally ordered pairs, pairs whose wall stamps are not increasing) for four skew levels."""
    rows = []
    for offs in [(0, 0, 0, 0), (0, 3, -2, 1), (0, 40, -35, 10), (0, 200, -150, 50)]:
        s = survey(runs, offsets=offs)
        rows.append((max(offs) - min(offs), s['ordered'], s['wall_wrong']))
    return rows
```

| Timestamp | Causally ordered pairs it gets wrong | Concurrent pairs it gets wrong |
|---|---|---|
| wall clock | 4,386 of 100,496 (4.4%) | cannot say "concurrent" |
| Lamport | 0 of 100,496 | 70,364 of 76,504 are put in a strict order anyway |
| vector | 0 of 100,496 | 0 of 76,504 |
| HLC | 0 of 100,496 | cannot say "concurrent" |

Reading it:

1. **Lamport and HLC never invert a causal pair** (the Clock Condition holds in all 100,496 pairs), and the vector clock classifies every pair correctly.
2. **A Lamport number carries no information about concurrency.** Of 76,504 concurrent pairs, 70,364 have different Lamport values, so comparing values would "order" them. `L(a) < L(b)` does not mean `a` happened before `b`; the check also asserts that this actually occurs in the runs.
3. **The Lamport order is still useful: it is a total order.** Sorting by `(L, node)` breaks every tie, and the check confirms that this order never puts an effect before its cause. Lamport's paper uses this to build a distributed mutual-exclusion algorithm: every request is timestamped, every process keeps a queue ordered by `(timestamp, process)`, and a process may enter when its request is first in its queue and it has heard a later-stamped message from every other process. The paper also states the cost: every process must take part, so a single failed process halts the others. That is the gap that fault-tolerant consensus (Raft lesson) fills.
4. **The same paper warns about the order the system cannot see.** If a person issues a request on one computer, phones a friend who issues another on a different computer, the second can receive the lower timestamp, because the system never saw the phone call. Lamport's two remedies are to pass the timestamp through the outside channel (the user carries it) or to use well-synchronised physical clocks.
5. **HLC stays near physical time.** The check asserts `l >= pt` at every event and `l - pt` never above the skew spread (75 ms here). That is the paper's Corollary 1 with the clock-synchronisation bound set to the spread: `l` is some earlier event's physical time (Theorem 3), and no earlier event can be ahead of the current one by more than the bound.

| | Wall | Lamport | Vector | HLC |
|---|---|---|---|---|
| `a -> b` implies `ts(a) < ts(b)` | no | yes | yes | yes |
| `ts(a) < ts(b)` implies `a -> b` | no | no | yes | no |
| Can detect concurrent | no | no | yes | no |
| Size | 64 bits | one integer | one integer per node | `(l, c)`, fits 64-bit NTP format per the paper |
| Close to real time | up to skew | no | no | yes |

Visual (planned): a space-time diagram of three processes with messages, showing Lamport and vector stamps on each event and the concurrent pairs highlighted.

---

## 5. Deep Dive 3: Version Vectors in a Store

A vector clock stored with a value is a **version vector**: a map from node to counter. Dynamo's paper (read 2026-11-26) uses exactly this. Each version of an object has a clock; a version whose counters are all less than or equal to another's is an ancestor and can be dropped; otherwise the versions are in conflict and the **client** reconciles them on the next write. The paper's worked example has nodes `Sx`, `Sy`, `Sz`:

```python
def dict_relation(a, b):
    nodes = sorted(set(a) | set(b))
    return vc_relation(tuple(a.get(k, 0) for k in nodes), tuple(b.get(k, 0) for k in nodes))

D1, D2 = {'Sx': 1}, {'Sx': 2}                      # one node writes twice: D2 overwrites D1
D3 = {'Sx': 2, 'Sy': 1}                            # a different node handles the third write
D4 = {'Sx': 2, 'Sz': 1}                            # a client that read D2 writes via a third node
D5 = {'Sx': 3, 'Sy': 1, 'Sz': 1}                   # a client read both D3 and D4 and reconciled them
# dict_relation(D1, D2) == 'before';  dict_relation(D3, D4) == 'concurrent';  dict_relation(D3, D5) == 'before'
```

`D3` and `D4` are concurrent: each contains a change the other lacks, so both are kept and returned together on a read. The paper reports that in a 24-hour window of its shopping-cart service, 99.94% of requests saw exactly one version, and that more divergent versions came from concurrent writers (it mentions automated clients) than from failures.

The clock grows when more nodes coordinate writes for an object. Dynamo's remedy is truncation: store a timestamp with each `(node, counter)` entry, and when the clock passes a threshold (the paper says "say 10") drop the oldest entry. The paper notes that this loses the ability to derive descendant relationships exactly, and that the problem had not surfaced in production. It is worth seeing what exactly can go wrong:

```python
def truncate(clock, stamps, limit):
    """Past `limit` entries, drop the entry whose node updated the object longest ago (Dynamo's rule)."""
    clock = dict(clock)
    while len(clock) > limit:
        del clock[min(clock, key=lambda k: stamps[k])]
    return clock
```

With `stamps = {'x': 5, 'y': 1, 'z': 9}` and a limit of two entries (deliberately small, to make the effect visible; every clock below is truncated when it is stored):

- A descendant `{'x': 2, 'y': 1, 'z': 1}` of the stored ancestor `{'x': 2, 'y': 1}` has three entries, so `y` (the oldest) is dropped and it becomes `{'x': 2, 'z': 1}`, which now compares as **concurrent** with its own ancestor: a *false conflict*. Safe, but it costs a reconciliation.
- A genuinely concurrent version `{'x': 1, 'y': 1, 'z': 1}` (concurrent with `{'x': 2, 'z': 1}`) also truncates to `{'x': 1, 'z': 1}`, which now compares as **before** `{'x': 2, 'z': 1}`. The system would discard it as an ancestor: a write is lost *silently*.

The second case is this lesson's own derivation from the truncation rule, not something the paper reports; the paper says only that reconciliation becomes less precise. The pattern to remember: **anything that removes entries from a version vector can turn "concurrent" into "ordered"**, and that direction loses data.

---

## 6. Deep Dive 4: Linearizability, Checked

Jepsen's definition (read 2026-11-26): linearizability means every operation appears to take effect atomically, in some order, consistent with the real-time order of the operations: if operation A completes before B begins, B must take effect after A. It is a single-object model, and it cannot be totally or sticky available under a partition. Sequential consistency keeps only the order within each process, so a process may read arbitrarily stale state, though once it has seen another process's operation it can never see an earlier state. The two differ exactly where real time matters, for example when you tell someone through a side channel to go and look.

A **linearizability checker** takes a sequential specification (here, a register that starts at 0) and a recorded concurrent history, and decides whether some ordering of the operations respects both the specification and real time. The Porcupine write-up (read 2026-11-26) states that the decision problem is NP-complete in general and that checkers use a search procedure with tricks to prune it. This one is a memoised depth-first search over "which operations are already placed, and what does the register hold":

```python
from collections import namedtuple

Op = namedtuple('Op', 'client kind value call ret')   # kind 'w' or 'r'; for a read, value is what it returned

def check(ops, init=0, real_time=True):
    """Is this register history linearizable (real_time=True) or sequentially consistent (False)?
    Returns (answer, number of (placed-set, register value) states explored)."""
    n = len(ops)
    must_precede = [0] * n                 # bitmask of the operations that have to come before ops[i]
    for i, a in enumerate(ops):
        for j, b in enumerate(ops):
            if i == j:
                continue
            same_client_earlier = b.client == a.client and b.call < a.call
            real_time_earlier = real_time and b.ret < a.call
            if same_client_earlier or real_time_earlier:
                must_precede[i] |= 1 << j
    seen, full, calls = set(), (1 << n) - 1, [0]

    def search(done, state):
        calls[0] += 1
        if done == full:
            return True
        if (done, state) in seen:
            return False
        seen.add((done, state))
        for i, op in enumerate(ops):
            if done >> i & 1 or must_precede[i] & ~done:
                continue
            if op.kind == 'w':
                ok, nxt = True, op.value
            else:
                ok, nxt = op.value == state, state
            if ok and search(done | 1 << i, nxt):
                return True
        return False

    answer = search(0, init)
    check.calls = calls[0]                   # how many times search ran, to confirm the memo does its job
    return answer, len(seen)
```

An operation may be placed next only if everything that must precede it is already placed (real-time order, plus program order within a client) and, for a read, the value it returned equals the register's current value. Three histories, each with times as `(call, return)`:

| History | Verdict as linearizable | As sequentially consistent |
|---|---|---|
| **A stale read:** client A writes 1 during (0, 1); later, client B reads 0 during (2, 3) | no: the write completed before the read began | **yes**: the read can be ordered before the write, since B and A have no program order between them |
| **Reads going backwards:** a write of 1 stays open during (0, 10); client A reads 1 during (1, 2); then client B reads 0 during (3, 4) | no: A saw the write, so it took effect before A's read ended, which is before B's read began | **yes**: order B's read, then the write, then A's read |
| **Concurrent reads straddling a write:** write 1 during (0, 10); A reads 0 during (1, 2); B reads 1 during (3, 4) | yes: the write takes effect between the two reads | yes |

The first two histories are the classic ways a "strongly consistent" store fails a real-time check while still looking sane to each client separately. The check confirms the three verdicts, and, over 220 random histories of up to seven operations generated from a real atomic register (with some read results corrupted), that `check` agrees with a brute-force search over **every** ordering, in both modes, with both answers occurring at least eight times in each mode.

**The cost is real.** With `n` overlapping writes and a final read of a value nobody wrote, no ordering can succeed, so the search must exhaust its state space. The count the check reproduces is exactly `n x 2^(n-1) + 1`:

| Overlapping writes `n` | States explored |
|---|---|
| 4 | 33 |
| 6 | 193 |
| 8 | 1,025 |
| 10 | 5,121 |
| 12 | 24,577 |

Memoisation keeps this from being `n!`, but the growth is exponential, which is why checkers of real histories use the tricks the Porcupine post describes, and why you keep histories short and the number of concurrent clients small when testing. This sketch handles only completed operations; real checkers must also decide what an operation that never returned might have done.

**Where clocks fit.** The checker never reads a timestamp for ordering; it uses the call and return times of the **test harness**, which is a single observer. A real system can provide linearizability with no synchronised clocks at all (a leader or a consensus log orders operations), or with them, by bounding uncertainty and waiting it out (the Spanner lesson). What clocks alone cannot give you is a linearizable store.

---

## 7. Choosing an Ordering in Practice

| Need | Use | Why not timestamps |
|---|---|---|
| order of one entity's changes | a sequence number from its single writer: a leader, a log offset, a row version | a counter has no skew, and gaps show lost events |
| reject a stale writer after failover | a monotonically increasing token (epoch or fencing token) checked by the resource | a clock cannot tell a paused process from a dead one |
| detect concurrent edits to a replicated value | version vectors | LWW would pick one without telling you |
| a total order that respects causality, no leader | Lamport timestamps with node-id tie-break | the order is arbitrary among concurrent events; fine when any consistent order will do |
| human-readable stamps plus causality | HLC | wall clocks can invert causal pairs |
| a read must see every completed write | a linearizable store: leader reads, consensus, or reads with a quorum protocol that provides it | replicas ordered by time can still return stale data |

---

## 8. Failure Modes

| Failure | Effect | Mitigation |
|---|---|---|
| node clock steps backwards (NTP correction, leap second) | timestamps repeat or invert | monotonic clock for durations; HLC for stamps; never subtract wall clocks to measure elapsed time |
| LWW on wall clocks | a causally later write silently loses | HLC or version vectors; accept LWW only where loss is harmless |
| version vector grows with every coordinator | metadata dominates small values | bound coordinators (preference list); prune knowing the cost (section 5) |
| pruning a vector entry | concurrent versions compare as ordered; a write is lost | avoid pruning by bounding which nodes may coordinate writes for an object; if you prune, expect false conflicts and possible silent loss |
| comparing Lamport numbers as if causal | false "caused by" claims | use vectors when you need concurrency |
| linearizability test with many clients | checker never finishes | shorter histories, fewer keys, smaller client counts, a faster checker |
| stale read after a leader change | a deposed leader answers from old state | read through the log or a lease the clock bound protects, and fence |

---

## 9. What Real Systems Document

All read 2026-11-26. Lamport (1978) defines happened-before, the Clock Condition, the two implementation rules, the `(clock, process)` total order, the mutual-exclusion algorithm and the anomaly of events outside the system. The HLC paper (Kulkarni et al.) gives the algorithm used above, the drift counter-example to the naive version and the bounds, and summarises NTP accuracy and the leap-second problem. Dynamo's paper shows vector clocks as version metadata, the client-side reconciliation, the clock truncation rule and one 24-hour measurement. Jepsen's pages define linearizability, sequential consistency, causal consistency and strict serializability and their availability limits. The Porcupine post states the NP-completeness and the practical search approach. **Not claimed:** which production databases use HLCs or vector clocks today; this lesson read no source for that.

---

## 10. Pitfalls Checklist

1. **Using wall-clock timestamps to order causally related writes.** Skew inverts them (4.4% of causal pairs at a 75 ms spread in the simulation).
2. **Believing `L(a) < L(b)` means `a` caused `b`.** It only means `b` is not earlier; 70,364 of 76,504 concurrent pairs had different Lamport values.
3. **LWW for data that matters,** without saying what it silently discards.
4. **Using the HLC or Lamport clock to detect conflicts.** Neither can say "concurrent"; a version vector can.
5. **Pruning version vectors without naming the failure.** Dropping an entry can turn a concurrent write into an apparent ancestor.
6. **Measuring durations with the wall clock.** Use a monotonic clock; wall clocks step.
7. **Confusing linearizability with serializability,** or with "replicas agree eventually". Linearizability is about real-time order of single-object operations.
8. **Testing linearizability with unrecorded histories** (assertions on each client's own reads). Record the whole history with call and return times and check it.
9. **Treating a clock as an ordering for a single entity** when a sequence number from its writer is free and exact.
10. **Ignoring the order the system cannot see** (a phone call, another channel): if it matters, carry the timestamp through it.

---

## Drills

1. Node A's clock is 300 ms behind node B's. A reads B's write and writes in response 100 ms later. Which write does wall-clock LWW keep, and which does an HLC keep? Show the HLC stamps.
2. State the Clock Condition. Give two events where `L(a) < L(b)` but `a` did not happen before `b`.
3. Compare `[(Sx,2),(Sy,1)]` with `[(Sx,2),(Sz,1)]` and with `[(Sx,3),(Sy,1),(Sz,1)]`. Which pairs are concurrent, and what must a client do on a read that returns the first two?
4. Why can pruning a version-vector entry lose a write? Build the smallest example.
5. Is "write completed at 12:00:00, a read at 12:00:01 returns the old value" linearizable? Is it sequentially consistent? What extra fact would change your answer for the second?
6. Why is linearizability checking exponential, what does memoising `(placed set, state)` bound the work by, and what is the count for 10 overlapping writes and an impossible read?
7. In the HLC update on receive, when does the counter reset to 0, and why does that keep `c` small?
8. You need a per-order event stream whose order every consumer agrees on. Why is a per-order sequence number from the owning partition better than timestamps?

---

## Homework

1. Run `survey` with more nodes (8 and 16) and report how the vector clock's size changes against the number of concurrent pairs it correctly identifies.
2. Add message loss and duplication to `simulate`; check which of the four timestamps' guarantees survive and which assumptions (the paper assumes messages are eventually received) you had to change.
3. Implement Lamport's mutual-exclusion algorithm (five rules in the paper) on top of `lamport_tick` and `lamport_recv`; check that no two processes are in the critical section at once, and then crash one process and describe what happens.
4. Extend `check` to a key-value store (a register per key) and to a queue specification; compare the number of explored states on the same histories.
5. Add incomplete operations (invoked, never returned) to `check`: an operation may or may not have taken effect. Write the rule and test it against brute force.
6. Read the HLC paper's sections 4 to 6 (not read for this lesson) and write one page on what it claims about NTP faults and snapshot reads, with page references.

---

## Sources

All read 2026-11-26.

- Lamport, *Time, Clocks, and the Ordering of Events in a Distributed System* (CACM, July 1978), lamport.azurewebsites.net/pubs/time-clocks.pdf. Read from the introduction through the physical-clock conditions PC1 and PC2; the physical clock synchronisation algorithm and its bound were not read.
- Kulkarni, Demirbas, Madeppa, Avva, Leone, *Logical Physical Clocks and Consistent Snapshots in Globally Distributed Databases*, cse.buffalo.edu/tech-reports/2014-04.pdf. Read the abstract, the introduction (including the NTP accuracy discussion), the problem statement and the HLC algorithm of section 3 with its theorem statements; proofs and sections 4 to 6 were not read.
- DeCandia et al., *Dynamo: Amazon's Highly Available Key-value Store* (SOSP 2007), allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf. Read sections 4.4 and 4.5 (data versioning, vector clocks, truncation, R and W) and the version-count measurement in 6.3.
- Jepsen, *Linearizability*, *Sequential Consistency*, *Causal Consistency* and *Strong Serializability* pages, jepsen.io/consistency/models/. Read in full.
- Athalye, *Testing Distributed Systems for Linearizability*, anishathalye.com/testing-distributed-systems-for-linearizability/. Read in full.

## Further reading (not consulted)

Herlihy and Wing, *Linearizability: A Correctness Condition for Concurrent Objects* (1990; the copy at the URL tried returned a 404 and the paper was not read); the Spanner paper (covered in the Spanner lesson, not re-read here); Wing and Gong's checking algorithm. The linearizability checker here is this lesson's own memoised search and was not derived from those papers.

*Last reviewed: 2026-11-26.*
