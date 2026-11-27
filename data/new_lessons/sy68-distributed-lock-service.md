# Lesson 68 — Case Study: Distributed Lock Service (Chubby, ZooKeeper)

> **Priority:** ★★★☆☆ (proposed; the curriculum data holds the final rating) — "only one instance may do this" is the core of leader election, schedulers and failover, and most answers stop at an expiring key and never ask what the old holder does next.
>
> **Study time:** 80 minutes. **Do this after:** Time, Clocks and Ordering; Distributed Consensus & Raft; Overload, Load Shedding and Cascading Failures.
>
> **Level:** extended.

A distributed lock sounds like a mutex with a network in the middle. It is not: a mutex knows when its holder has gone, a lock service only knows it has stopped hearing from it. This lesson builds the parts of Chubby and ZooKeeper that interviews probe (leases, the ephemeral-sequential recipe, fencing tokens, the herd on release) as a small model, checked in `test/lesson_code/sy68_check.py` against a naive reference and a simulated client that pauses and resumes; capacity numbers come from `capacity_check_d.py`. Consensus is not re-taught (see Distributed Consensus & Raft), nor why clocks prove little (see Time, Clocks and Ordering).

---

## 1. Mental Model

> **A lock over a network is a lease on a clock you do not share. The service can promise to record at most one holder; it cannot promise the holder knows its lease ended. So safety lives not in the lock but in a number that grows with every grant and is checked by the resource being protected.**

- **"Two holders" happens in beliefs, never in the service's records:** a client paused past its lease has not found out.
- **A lease check before an action proves nothing about the action.** Check and act are two instants, and a stall fits between them.
- **A fencing token turns "who holds the lock" into "which write is newest",** which the resource can answer from numbers alone.
- **Consensus only makes the record trustworthy;** the pause problem stays open.
- **Coarse-grained is a design choice.** Chubby's paper expects locks held for hours or days: few acquisitions, constant keep-alives. That sizes everything.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "leader election", "only one scheduler may run" | an ephemeral lock; the leader passes its token to everything it mutates |
| "a distributed lock to protect a shared resource" | lock plus fencing token checked by the resource; if it cannot check, say so and name weaker options (section 8) |
| "what if the holder crashes, or is only slow (GC pause, stalled VM)" | a crash frees the lock between two thirds of the timeout and all of it later (section 6); a stall looks the same to the service and not to the client: fencing |
| "thousands of clients wait for one lock" | each waiter watches the entry just below its own, so a release wakes one client |
| "a lock per request, 50,000 a second" | not a lock-service workload (section 3): give each key one owner, or use conditional writes on the store |
| "why not an expiring key in a cache?" | the same lease and pause problem, and no token unless you build one (no such product's documentation was read) |

---

## 3. Requirements and Capacity

**Functional.** Sessions kept alive by heartbeat; exclusive locks by name with a queue of waiters; small files with change notification; ephemeral nodes that vanish with their session; a token with every grant. **Out of scope:** shared locks, access control, cross-cell mirroring, the consensus protocol.

**Non-functional.** Availability and clear semantics over speed (the Chubby paper's emphasis). Never two *recorded* holders. A bounded time to notice a dead holder. A leader failure must not drop held locks.

**Capacity estimate.** Inputs marked *assumed* are this lesson's, not any company's. Inputs marked *paper* are figures the cited papers print, used as inputs. Every result is reproduced by `capacity_check_d.py`.

| Input | Value |
|---|---|
| client processes in one cell | 50,000 *(assumed; below the 90,000 the Chubby paper says one master served)* |
| lease extension per KeepAlive | 12 s default, about 60 s under heavy load *(paper)* |
| ZooKeeper-style session timeout | 10 s *(assumed)*; clients ping after s/3 idle *(paper)* |
| coarse-grained locks | 5,000 locks, each held 6 hours on average *(assumed)* |
| fine-grained comparison | one lock cycle per request, 100,000 requests per second *(assumed)* |
| one lock cycle | 2 writes (create the node, delete it); the reads are ignored *(assumed)* |
| one Chubby cell snapshot | 22,000 direct clients, 1,000 to 2,000 RPCs per second, 93% KeepAlive, Acquire 31 per million *(paper, section 4.1)* |
| saturated writes, 0% reads, 1 KB | 21,000 per second with 3 servers, 8,000 with 13 *(paper, Table 1, 2010 hardware)* |

| Result | Arithmetic | Value |
|---|---|---|
| KeepAlives, 12 s lease | 50,000 / 12 | 4,167 KeepAlives per second |
| KeepAlives, 60 s lease | 50,000 / 60 | 833 per second, five times fewer |
| cross-check with the snapshot | 22,000 / 12 | 1,833 per second, inside the 930 to 1,860 that 93% of 1,000 to 2,000 implies |
| coarse-grained acquisitions | 5,000 / (6 x 3,600) | 0.23 acquisitions per second, 0.46 writes per second |
| fine-grained lock cycles | 100,000 x 2 | 200,000 writes per second |
| against the write ceiling | 200,000 / 21,000 and / 8,000 | 9.5 times and 25 times too many |
| dead holder keeps the lock | between 2s/3 and s, s = 10 | 6.67 to 10 seconds |
| herd, 1,000 waiters drain | names listed: chain, against all watching the holder | 499,500 against 332,833,500: 666 times |
| sequence counter, signed 32-bit | 2,147,483,647 / creates per second | 24.9 days at 1,000 per second, 248.6 days at 100, 6.8 years at 10, 294 years at 0.23 |

Five conclusions. **KeepAlives are the load, not locks:** 4,167 per second against 0.46 writes, the same shape as the paper's snapshot. A longer lease cuts that five-fold (load shedding, as in Overload, Load Shedding and Cascading Failures) but, since the master promises not to end a session before its lease runs out, it also lengthens how long a dead holder keeps its lock (an inference from the paper's definition of the lease, not a number it prints). **Fine-grained locking does not fit:** 200,000 writes per second is 9.5 to 25 times the paper's saturated benchmark, and even 10,500 lock cycles per second, half its best 21,000 writes, is a ceiling that ignores the recipe's reads. **Detection is a window:** a client pinging every s/3 is noticed between 2s/3 and s after it dies. **The herd is quadratic:** building a queue of N costs N(N+1)/2 names even with the good recipe. **An election must fit inside the grace period:** the longest the Chubby paper reports is 30 s, the default grace 45 s.

Visual (planned): lock nodes 1 to 5, each waiter pointing at the node below it.

---

## 4. API and Data Model

```
open_session(ttl) -> sid                 keepalive(sid) -> ok | expired
enqueue(sid, lock, guid) -> seq          create "lock/<guid>-n_", EPHEMERAL | SEQUENTIAL; same guid returns the same node
children(lock) -> [seq]                  exists_watch(node) -> bool (one-shot)        release(sid, seq) -> bool
session {id, last_heard, ttl}    node {lock, seq, session, guid}    token = seq (this lesson's choice, section 8)
```

Chubby makes the lock a first-class object (`Acquire`, `Release`, `GetSequencer`, `CheckSequencer`); a node's metadata has a lock generation number that increases when the lock goes from free to held. ZooKeeper's paper says it is not a lock service and has no lock operations: locks are a client-side recipe over ephemeral and sequential znodes, versioned writes and watches. Both keep the database in memory: small coordination data only.

---

## 5. What the Service Needs From Consensus

Chubby (paper): the master wins a majority vote and promises no other master for a few seconds; typically five replicas, three up; the master alone serves reads while its master lease holds; session state is recorded in the database, or rebuilt by a new master that then waits out the worst-case lease. ZooKeeper (paper): Zab, an atomic broadcast, makes writes linearizable; a majority is needed (2f + 1 servers tolerate f failures); any server answers reads from its local copy, so a read can be stale unless preceded by `sync`.

Why a lock service rather than a consensus library? The Chubby paper: a lock changes little of an existing system's shape (elect a master with a lock, send the acquisition count with each write, reject lower counts); results can be advertised in a small file; programmers know locks; clients progress with fewer servers of their own. It adds that programmers who think they know how to use locks are usually wrong in a distributed system. The rest of this lesson is about that.

---

## 6. Deep Dive 1: Leases, Sessions and KeepAlive

**Chubby.** The master blocks a KeepAlive until the client's lease is nearly over, then returns it with a later end (12 s by default) and the client sends the next at once, so one call is nearly always parked at the master. The reply also carries events and cache invalidations, so a client cannot keep its session without acknowledging them. The client keeps a **local lease**, shorter than the master's: it assumes the reply spent a long time in flight and that the master's clock runs a bounded factor fast. When it runs out the session is **in jeopardy**: the cache is emptied, the application is told, and the client waits a **grace period** (45 s by default) for a KeepAlive to get through; if one does, the session is safe again, otherwise it has expired.

```python
def local_deadline(sent_at, lease, drift):
    """Chubby-style local lease end: count from when the KeepAlive was SENT, and assume the server's clock may run
    up to (1 + drift) times faster than ours."""
    return sent_at + lease / (1 + drift)
```

The check draws 3,000 combinations of lease, send time, delay and server clock rate inside the drift bound, asserts the local deadline never passes the server's real expiry, and asserts the extreme case is tight. The other conservative rule is the caller's: pass the time the request *left*, not the time the reply arrived.

**ZooKeeper.** The client asks for a timeout and the server answers with one it can give (the documentation: between 2 and 20 ticks). The client pings after s/3 idle and tries another server after 2s/3 of silence. The cluster expires the session when it hears nothing for **more than** the timeout, deletes its ephemeral nodes and notifies watchers. The documentation adds the sentence this lesson turns on: the client of an expired session is still disconnected, and **will not be told until it reconnects**.

**How long does a dead holder keep the lock?** The last ping came 0 to s/3 before the crash and the session ends s after that ping, so the lock frees between 2s/3 and s after the crash: 6.67 to 10 seconds at s = 10. The check crashes a client at 400 phases of one ping period and asserts both ends (the lesson's arithmetic on the paper's ping rule; it assumes exact pings until death).

**The timeout is a trade:** short detects a crash fast and also expires a client that was only stalled; long rides out pauses and keeps a dead holder's lock longer. Neither removes the pause problem.

---

## 7. Deep Dive 2: The Ephemeral-Sequential Recipe

ZooKeeper's recipe: create `lock/<guid>-n_` (ephemeral, sequential); list the children without a watch; if yours is lowest you hold the lock; otherwise set an existence watch on the node just below yours and wait; when it fires, list again. Unlock deletes your node, and a crash does it for you.

```python
class LockService:
    """One ZooKeeper-style lock directory and its sessions. Time is an argument; no real clock is read."""
    def __init__(self, ttl, lock_delay=0.0):
        self.ttl, self.lock_delay = ttl, lock_delay
        self.last_heard = {}      # session id -> time the service last heard from it
        self.nodes = {}           # sequence number -> (session id, guid): the ephemeral sequential children
        self.watches = {}         # sequence number -> clients to wake when that node goes away
        self.next_seq = self.next_sid = 1
        self.free_after = 0.0     # lock-delay: no grant before this time once a holder was lost
        self.events = []          # audit trail for the checks
        self.names_listed = 0     # child names returned by children(): the cost of looking

    def _expire(self, now):
        for sid, t in sorted(self.last_heard.items(), key=lambda kv: kv[1]):
            if now - t > self.ttl:                           # "more than the timeout": exactly ttl is still alive
                for seq in [s for s, (owner, _) in self.nodes.items() if owner == sid]:
                    if seq == min(self.nodes):               # the holder was lost: start the lock-delay
                        self.free_after = max(self.free_after, t + self.ttl + self.lock_delay)
                    self._delete(seq)
                for waiting in self.watches.values():        # watches die with their session
                    waiting[:] = [c for c in waiting if c.sid != sid]
                del self.last_heard[sid]
                self.events.append(('expired', t + self.ttl, sid))

    def _delete(self, seq):
        del self.nodes[seq]
        woken = self.watches.pop(seq, [])                    # a watch is a one-time trigger
        self.events.append(('delete', seq, len(woken)))
        for c in woken:
            c.wake()

    def _live(self, sid, now):
        self._expire(now)
        if sid not in self.last_heard:
            return False
        self.last_heard[sid] = now                           # any message counts as a heartbeat
        return True

    def open_session(self, now):
        self._expire(now)
        sid, self.next_sid = self.next_sid, self.next_sid + 1
        self.last_heard[sid] = now
        return sid

    def heartbeat(self, sid, now):
        return self._live(sid, now)

    def enqueue(self, sid, now, guid):                       # create(".../<guid>-n_", EPHEMERAL | SEQUENTIAL)
        if not self._live(sid, now):
            return None
        for seq, (owner, g) in self.nodes.items():
            if owner == sid and g == guid:                   # a retry after a lost reply finds its own node
                return seq
        seq, self.next_seq = self.next_seq, self.next_seq + 1
        self.nodes[seq] = (sid, guid)
        return seq

    def release(self, sid, seq, now):                        # delete(node): only its owner, only while the session lives
        if not self._live(sid, now) or self.nodes.get(seq, (None,))[0] != sid:
            return False
        self._delete(seq)
        return True

    def children(self, sid, now):                            # getChildren(lock), no watch
        if not self._live(sid, now):
            return None
        self.names_listed += len(self.nodes)
        return sorted(self.nodes)

    def exists_watch(self, sid, now, seq, client):           # exists(node, watch=true): set only if the node is there
        if not self._live(sid, now) or seq not in self.nodes:
            return False
        self.watches.setdefault(seq, []).append(client)
        return True

    def holder(self, now):                                   # the grant the service itself vouches for
        self._expire(now)
        return min(self.nodes) if self.nodes and now >= self.free_after else None
```

```python
class LockClient:
    """The recipe's client. One step() is one round trip; the caller chooses the interleaving."""
    def __init__(self, svc, sid, guid):
        self.svc, self.sid, self.guid = svc, sid, guid
        self.seq = self.pred = None
        self.state = 'new'        # new -> list -> held, or list -> watch -> wait -> list ...; 'lost' once the session is gone

    def wake(self):               # the service calls this when the watched node is deleted
        if self.state == 'wait':
            self.state = 'list'

    def _target(self, kids):      # watch the node just below ours, so a release wakes one client
        return max(k for k in kids if k < self.seq)

    def step(self, now):
        s = self.svc
        if self.state == 'new':
            self.seq = s.enqueue(self.sid, now, self.guid)
            self.state = 'list' if self.seq is not None else 'lost'
        elif self.state == 'list':
            kids = s.children(self.sid, now)
            if kids is None or self.seq not in kids:
                self.state = 'lost'
            elif kids[0] == self.seq:
                self.state = 'held'
            else:
                self.pred, self.state = self._target(kids), 'watch'
        elif self.state == 'watch':
            self.state = 'wait' if s.exists_watch(self.sid, now, self.pred, self) else 'list'   # already gone: look again
        return self.state

    def heartbeat(self, now):
        if not self.svc.heartbeat(self.sid, now):
            self.state = 'lost'   # the client learns this only when a message gets through
        return self.state != 'lost'

    def release(self, now):
        ok = self.svc.release(self.sid, self.seq, now)
        self.state = 'done'
        return ok
```

Four behaviours, each of which a plausible implementation gets wrong, and each pinned by the check.

**1. Grants are first in, first out, and match a naive reference.** 300 random sequences of operations (time jumping by up to 9) run against a dumb reference: a list in arrival order and a table of last-touch times, aliveness recomputed each time. Holder, children and every return value must agree. Boundaries too: silence of exactly one timeout is alive, a hair more is expired for good; sequence numbers are never reused.

**2. A watch on a node already gone must send the client back to look.** Between "list" and "watch" the holder can release; a client that waits anyway sleeps forever. The check builds that interleaving, and 200 random schedules assert no live client ends stuck.

**3. A waiter in the middle dies.** Only its successor wakes (every deletion in every run woke at most one client), lists again, finds it is *not* lowest, and watches the holder. Waking is not winning.

**4. A lost create reply must not queue a client behind itself.** The recipes page warns that `create` can succeed while the reply is lost. A blind retry leaves two nodes: the first holds the lock, and the client waits on it, though only its own session can delete it. The guid in the name lets the retry find its node; the check asserts one node after retries and builds the failure without it.

**The herd.** ZooKeeper's paper shows a lock where every waiter watches the lock node, then one where each watches its predecessor. The check runs both on one service, counting clients woken and names listed while N waiters drain: chain, one woken per release and `N(N-1)/2` names; everyone watching the holder, `N-1` woken, then `N-2`, and so on, and `(N-1)N(2N-1)/6` names. Both match the simulation for N of 2, 5 and 50 (1,225 names against 40,425 names at 50); at 1,000 waiters it is 499,500 against 332,833,500. Building the queue is quadratic either way (500,500 names), so the recipe suits a handful of contenders for a coarse lock.

---

## 8. Deep Dive 3: The Pause, and What Fencing Fixes

So far the record is correct. Now the belief. One trace, session timeout 10:

| Time | What happens |
|---|---|
| 0 | A takes the lock with token 1 and writes `a1` |
| 3, 6 | A's heartbeats reach the service; the last is at 6, so A's lease runs to 16 |
| 9 | A checks its lease: valid. Then it stalls (a long garbage collection, a stalled VM, a suspended process) |
| just after 16 | the service has heard nothing for more than 10, expires A's session and deletes node 1 |
| 17 | B takes the lock with token 2 and writes `b1` |
| 20 | A wakes. Its code believes it holds the lock, so it writes `a2` |

```python
class Store:
    """The protected resource. With fenced=True it remembers the highest token seen and refuses lower ones."""
    def __init__(self, fenced):
        self.fenced, self.max_token, self.value, self.accepted = fenced, 0, 0, []

    def _admit(self, token):
        if self.fenced and token < self.max_token:
            return False
        self.max_token = max(self.max_token, token)
        return True

    def claim(self, token):       # a new holder announces itself before it reads anything
        return self._admit(token)

    def read(self):
        return self.value

    def write(self, token, value):
        if not self._admit(token):
            return False
        self.value = value
        self.accepted.append((token, value))
        return True


def pause_trace(fenced, ttl=10):
    """A takes the lock at 0; its last heartbeat reaches the service at 6; at 9 it checks its lease (valid until 16)
    and stalls until 20. The service expires A just after 16; B takes over at 17."""
    svc, store = LockService(ttl), Store(fenced)
    a = svc.open_session(0)
    a_token = svc.enqueue(a, 0, 'a')
    store.write(a_token, 'a1')
    svc.heartbeat(a, 3)
    svc.heartbeat(a, 6)
    a_thinks_it_holds = 9 < 6 + ttl                          # A's own check, made before the stall
    b = svc.open_session(17)
    b_token = svc.enqueue(b, 17, 'b')
    assert svc.holder(17) == b_token                         # the service has one holder, and it is B
    store.claim(b_token)
    store.write(b_token, 'b1')
    stale_write_accepted = store.write(a_token, 'a2')        # A wakes at 20 and writes with the token it holds
    return store.value, stale_write_accepted, a_thinks_it_holds


def counter_trace(order, ttl=10):
    """A and B each add 1 to a counter in a fenced store. A reads 5 and stalls; B takes over; A's late write arrives
    when `order` says. Returns (final value, whether A's write was accepted)."""
    svc, store = LockService(ttl), Store(True)
    a = svc.open_session(0)
    ta = svc.enqueue(a, 0, 'a')
    store.claim(ta)
    store.write(ta, 5)
    a_read = store.read()
    b = svc.open_session(11)
    tb = svc.enqueue(b, 11, 'b')
    if order == 'read_then_claim':       # B reads first and claims later: A's write slips in between
        b_read = store.read()
        a_ok = store.write(ta, a_read + 1)
        store.claim(tb)
    elif order == 'slip_then_claim':     # A's write lands before B claims, but B reads after claiming
        a_ok = store.write(ta, a_read + 1)
        store.claim(tb)
        b_read = store.read()
    else:                                # 'claim_then_read': B claims first, so A's write is refused
        store.claim(tb)
        a_ok = store.write(ta, a_read + 1)
        b_read = store.read()
    store.write(tb, b_read + 1)
    return store.value, a_ok
```

A store that ignores tokens ends with `a2`: the stale write is accepted though A's lease check had passed (`('a2', True, True)`). A store that remembers the highest token and refuses lower ones ends with `b1` (`('b1', False, True)`). The recipes page says that at any snapshot "no two clients think they hold the same lock". Read as a statement about the znodes, that is the service's record; the page mentions neither pauses nor tokens (it was searched for both), so this trace is the case it leaves out. The Chubby paper states the failure generally (a request from a process that held the lock arrives after another has acquired it and acted) and gives the remedy: a **sequencer** with the lock name, mode and generation number, passed with each request, which the receiving server checks against Chubby or against the most recent one it has seen. The second form is `Store`.

**The token is this lesson's choice.** The model uses the lock node's sequence number: holders get the lock in increasing sequence order, and every simulated run asserts the service-side holder never goes backwards. Chubby uses a lock generation number. The ZooKeeper programmer's guide gives the limit: the sequence counter is a signed 32-bit integer kept by the parent node and wraps negative after 2,147,483,647 creates: 24.9 days at 1,000 creates per second under one parent, 248.6 days at 100, 6.8 years at 10, 294 years at the coarse-grained 0.23. A wrapped token goes backwards; rotate to a new lock directory long before, or use a wider number such as the creation transaction id the guide describes (untested here).

**Fencing has a hole, measured.** The store learns of token 2 only when B first speaks. If A's late write lands between B's acquisition and that first contact, it is accepted. Whether it costs anything depends on what B does first (A and B each add 1 to a counter that starts at 5):

| Order | A's write | Final | Verdict |
|---|---|---|---|
| B reads, then claims; A's write lands between | accepted | 6 | two acknowledged increments, one visible: **lost update** |
| A's write lands, then B claims, then B reads | accepted | 7 | consistent: B saw it |
| B claims, A's write arrives, B reads | refused | 6 | consistent: A was told no |

The rule is **claim before you read**: a new holder's first act is to present its token to the resource, and only then does it read state it will build on. The check runs all three orders.

**At scale.** 200 seeded schedules of five clients: each takes the lock once, reads a counter, may stall up to three timeouts, may freeze at random or die, then writes value plus one. A run is wrong if the counter differs from the number of acknowledged increments. Illustrative of this model, not of any production system:

| Store and discipline | Runs with a lost update |
|---|---|
| ignores tokens | in 87 of 200 runs |
| checks tokens, claims after reading | in 15 of 200 runs |
| checks tokens, claims before reading | in 0 of 200 runs |

In 91 of 200 runs at least two clients believed they held the lock at once while the service had one holder; the same run asserts that a client whose session is alive and believes it holds the lock *is* that holder. "0 of 200" means the discipline survived these schedules, not every schedule.

**Lock-delay** is the Chubby paper's imperfect option for servers that cannot check tokens. When a lock frees because its holder failed, the service withholds it for a stated delay (up to a minute in the paper); a clean release is not delayed. The idea is to let requests already in flight land first. A packet sent at 9 crawls through the network after A dies; B polls every half second. With no delay, B starts at 10.5: a packet that took 1 s has landed, one that took 2 s lands after B has read. With a 60 s delay B starts at 70: a 30 s packet is safe and a 100 s packet still wins. The check asserts all four cases.

```python
def delayed_packet_trace(lock_delay, packet_delay, ttl=10.0, poll=0.5):
    """A's last write leaves at t=9 and crawls through the network; A then dies. B polls every half second and starts
    (reads the store) when the service grants it the lock. Returns (when B started, whether A's packet had landed)."""
    svc = LockService(ttl, lock_delay)
    a = svc.open_session(0.0)
    svc.enqueue(a, 0.0, 'a')
    b = svc.open_session(0.0)
    tb = svc.enqueue(b, 0.0, 'b')
    t = 0.0
    while svc.holder(t) != tb:
        t += poll
        svc.heartbeat(b, t)
    return t, 9.0 + packet_delay < t
```

Nothing bounds packet delay on an asynchronous network, which is why the paper calls it imperfect.

**If the resource cannot check a token:** put the check in a proxy in front of it; or make the resource do a compare-and-swap on a version (Chubby's `SetContents` takes a content generation number for this, ZooKeeper's `setData` an expected version), which fences with no lock at all when the lock protects that same state; or use lock-delay and say the risk remains. Never say the lock alone makes it safe.

---

## 9. Deep Dive 4: Notification and Caching

Chubby's paper says its most popular use turned out to be as a name server, which is reads and watching, not locking. **Chubby caches consistently and invalidates.** Clients cache data, metadata and the absence of files. On a change the master blocks the write while it sends invalidations (carried on KeepAlive replies) and proceeds when every client has acknowledged or its lease has lapsed, so one slow client can delay a write by up to its lease. **ZooKeeper's reads are local and watches one-shot:** a watch fires once, carries no data, and the client re-reads and re-sets it; two changes before the re-read give one event, which is harmless. The ZooKeeper authors: leases only bound the effect of a slow client, watches avoid it, at the price of reads that can be stale without `sync`.

**Why invalidation beat time-to-live, in the paper's arithmetic.** 3,000 processes that each look up every other make 9,000,000 lookups; at a 60 s time-to-live that is 150,000 lookups per second, against the 50,000 per second the paper gives for one DNS server. An invalidated cache costs a fixed KeepAlive per client. Even so, starting such a job brought the master to its knees until entries were grouped about 100 to a lookup, which by this lesson's arithmetic is 90,000 lookups.

---

## 10. Failure Modes

| What breaks | What you see | Defence |
|---|---|---|
| holder paused past its lease | a stale write after a new holder started | fencing token checked at the resource; claim before you read |
| local lease timer on a clock that jumps or drifts | the client thinks its lease is valid after it ended | deadline from the send time with a drift bound, on a monotonic clock (the lesson's advice) |
| partition from the service | the client cannot renew and is expired | stop acting after the local lease; granting needs a majority |
| master or leader failover | sessions in jeopardy, clients blocked for seconds | grace longer than the longest election (45 s against 30 s); do not crash on the event |
| keep-alive overload | sessions drop above about 90,000 clients (paper) | longer leases under load |
| split brain | the service side: two masters; the client side: two clients acting as holder (91 of 200 simulated runs) | a majority vote plus a master lease, so no second master exists while the first lease holds (Chubby paper); tokens for the client side |
| herd on release | every waiter wakes and lists the queue | watch the predecessor |
| lock-delay too short | a delayed packet lands after the new holder starts | tokens; the delay only narrows the window |

---

## 11. What Real Systems Did

- **Chubby** (Burrows, OSDI 2006, read 2026-11-27): a lock service for coarse-grained locking and small files; GFS appoints its master with it, and Bigtable elects a master, finds its servers and lets clients find the master. Its snapshot figures, used above, are from 2006 and "typical of cells in Google" in its words.
- **ZooKeeper** (Hunt et al., USENIX ATC 2010, read 2026-11-27): a coordination kernel at Yahoo!. Its applications are Katta (shard assignment, master failover), the Fetching Service of the Yahoo! crawler and Yahoo! Message Broker. Its stated trade: wait-free operations, FIFO client order, linearizable writes, local reads that may be stale.
- No engineering write-up from any other company on building a lock or leader-election service was read. The model, the token choice, the claim-before-read rule and the simulation are this lesson's own, not what Google or Yahoo! ran.

---

## 12. Pitfalls Checklist

1. **Believing the lock proves exclusion.** The service proves a record; a token checked at the resource proves the write is current.
2. **Checking the lease, then acting later.** A stall fits between them.
3. **Reading before presenting the token.** Claim first (claiming after reading lost updates in 15 of 200 runs).
4. **A token from a clock or a per-client counter.** It must grow with every grant.
5. **Every waiter watching the holder.** One release wakes all and each lists the queue.
6. **A watch without handling "already gone".** The wake-up is lost.
7. **Retrying `create` with no idempotency key.** You queue behind yourself.
8. **Reading "my node is lowest" as "I know I lead".** Acknowledge the role visibly, and still fence.
9. **A lock per request.** The write ceiling is tens of thousands per second.
10. **Crashing on a failover or disconnect event.** Quiesce and wait.

---

## Drills

1. The service records one holder at all times, yet two clients act as the holder. Walk the trace by time: who is wrong, and why can neither tell?
2. With a 10 s timeout and pings every s/3, how long can a dead holder keep the lock, and why is it not simply 10 s?
3. Why does a waiter watch the node just below its own, and what happens when that node's session expires?
4. A client creates its lock node, the reply is lost, and it retries. What goes wrong without a guid, and what do other clients see?
5. The protected resource is a database you cannot change. Give three options and the residual risk of each.
6. In the counter table, why does "B reads, then claims" lose an acknowledged update while "A's write lands, then B claims, then B reads" does not?
7. A team wants a lock per request at 50,000 requests per second. Answer with the write-ceiling arithmetic and propose an alternative.

---

## Homework

1. Run `python test/lesson_code/sy68_check.py data/new_lessons/sy68-distributed-lock-service.md`. Make `Store._admit` refuse equal tokens and find the first failing assertion; then remove the `max_token` update and repeat.
2. Make lock-delay part of `LockClient` (the client asks the service for the grant) and measure the change in `delayed_packet_trace`.
3. Replace the sequence number with a 64-bit counter kept by the service, and check that a wrapped 32-bit token breaks the store while the wider one does not.
4. Add shared (read) locks following the recipes page, with a brute-force check of read and write ordering.

---

## Sources

All read 2026-11-27. The model, the figures marked *assumed* and the simulation are this lesson's own.

- Mike Burrows, *The Chubby lock service for loosely-coupled distributed systems*, OSDI 2006, usenix.org/legacy/event/osdi06/tech/full_papers/burrows/burrows.pdf. Read from abstract to conclusion, references skimmed. The extraction scrambled Figure 2 and the section 4.1 table, so the table values used (22,000 direct clients, 1,000 to 2,000 RPCs per second, KeepAlive 93%, Acquire 31 per million) were taken in reading order and checked against the prose, as were the leases, grace period, elections and 90,000 clients. The proxy and partitioning sections were read, not used.
- Hunt, Konar, Junqueira, Reed, *ZooKeeper: Wait-free coordination for Internet-scale systems*, USENIX ATC 2010, usenix.org/legacy/event/atc10/tech/full_papers/Hunt.pdf. Sections 1 to 7 read, including Table 1 and the lock recipes; graphs and references not examined.
- Apache ZooKeeper 3.9 documentation, *Recipes and Solutions*, zookeeper.apache.org/doc/r3.9.3/recipes.html. Read in full (the unversioned `/doc/current/` address returned a not-found page).
- Apache ZooKeeper 3.9 documentation, *Programmer's Guide*, zookeeper.apache.org/doc/r3.9.3/zookeeperProgrammers.html. Read the parts on ephemeral and sequence nodes, zxid, sessions, watches and consistency guarantees; the rest was skimmed or not read.

## Further reading (not consulted)

The Zab paper; *Paxos Made Live*; the Curator recipes library and the ZooKeeper source; etcd and Consul documentation; documentation or essays on locks built from an expiring key in a cache, and the debate about them. None were read, so no claim is made about them.

*Last reviewed: 27 November 2026.*
