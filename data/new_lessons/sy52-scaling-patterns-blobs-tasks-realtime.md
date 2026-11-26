# Lesson 52 — Scaling Patterns II: Large Blobs, Long-Running Tasks and Real-Time Updates

> **Priority:** ★★★★★ — video upload, report export and live notifications show up in half the case studies, and the follow-up is always "what happens when the connection drops halfway?".
>
> **Study time:** 75 minutes. **Do this after:** Scaling Patterns I: Reads, Writes and Contention, and Idempotency, Outbox & Sagas.
>
> **Level:** core.

A request and its response promise an answer within seconds, over one connection, from one server. Three kinds of work break that promise. A 3 GB file does not fit in a request you can afford to hold open. A report that takes four minutes outlives every timeout between the client and your code. An update the server wants to send the moment something changes has no request to ride on. The fix is the same each time: take the work out of the request, and keep the state that makes retrying safe somewhere durable, because the connection is the one thing you cannot rely on. This lesson builds that state three ways (an upload ledger, a task record with leases, an event log with positions), tests each against injected failures, and checks the arithmetic that decides between the options. Every number below is produced by the code in this file.

---

## 1. Mental Model

> **When work does not fit in a request, move it out of the request and make progress a stored fact, not a property of a connection. A blob's progress is the set of parts or the offset the storage has persisted. A task's progress is a record with a state, a lease and an attempt number. A stream's progress is the id of the last event the client applied. After any failure the client asks what is stored and continues from there.**

What follows from it:

- **Retry safety comes from position.** An upload part has a number, a byte range has an offset, a task has an attempt number, an event has an id. Repeating a request with the same position changes nothing the second time, so the client can retry without thinking.
- **The expensive path is the one that restarts from zero.** One failure in a 10 GiB upload that must start over costs the whole transfer; one failure when the storage remembers costs one block.
- **Every long-lived thing needs an end.** Abandoned uploads, stuck tasks and idle connections each hold resources that nobody will release unless something expires them.
- **Pick the weakest mechanism that meets the latency.** Polling, long polling, server-sent events and WebSockets are a ladder, and each rung costs more connections or more state.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "users upload videos / large files" | direct-to-storage upload with a signed URL; multipart or offset-resumable |
| "upload fails at 90% on a flaky connection" | resume from the stored part list or offset, not from zero |
| "generate a report / run a model / transcode" | accept, return an operation id (202), run on a worker, client polls or is notified |
| "a worker dies halfway" | a lease with a heartbeat, an attempt number as a fencing token, idempotent effects |
| "show new messages / prices / progress live" | server-sent events if the data flows one way; WebSockets if the client also sends often |
| "the client reconnects and misses events" | event ids, `Last-Event-ID`, a bounded replay window, a snapshot after a gap |
| "a million users, one update per user per hour" | not polling: compute requests per second for each option first |
| "what if the signed URL leaks?" | short expiry, one URL per part, scope to one key, treat it as a bearer token |

---

## 3. Large Blobs

### Keep the bytes out of your servers

Suppose users upload 3 GiB files, two new uploads begin each second, and each client manages 10 MiB per second. Each upload then lasts 307 seconds. Little's law (connections open equals arrival rate times time spent) says that if the uploads pass through your application tier, **614 connections are held open at all times and 6,144 MiB per second flows through machines whose job is business logic**. Those numbers are illustrative; the shape is general. The bytes should go from the client straight to object storage, and your servers should only decide who may upload what.

The mechanism is a **signed URL**. The Amazon S3 documentation (read 2026-11-26) says anyone with valid credentials can create one, that creating it happens locally (S3 sees nothing until the URL is used), that the URL is only as powerful as the credentials of whoever signed it, and that presigned URLs are bearer tokens: whoever holds the URL can use it. Two details matter for design. S3 checks the expiry when the request arrives, so a download that began before expiry continues, but a client that drops and tries to restart after expiry fails. And a URL made from temporary credentials dies when those credentials do, even if you asked for longer. The flow:

1. Client asks your API to upload a file of a given size and type. The API authenticates, authorises, writes an `uploads` row (status `PENDING`) and returns URLs for the parts.
2. Client sends the bytes straight to storage, part by part.
3. Client (or a storage event) tells the API the upload is complete; the API verifies size and checksum and flips the row to `READY`.

Because a URL is a bearer token, issue **one URL per part with a short expiry** rather than one long-lived URL for the whole file: a leaked URL then exposes one part for minutes, and a resume after a long pause simply asks for fresh URLs. The S3 page also says its logs identify the signer, not the later user of the URL, so record who you issued each URL to at issuance time.

### Two ways storage remembers progress

| | Numbered parts (S3 multipart) | Contiguous offset (tus, Google Cloud Storage resumable) |
|---|---|---|
| Unit of progress | a part number and its checksum | a byte offset |
| Order | any order, in parallel | one contiguous stream |
| Who knows what is stored | the client keeps its own list of part numbers and checksums | the server; the client asks (a `HEAD` in tus, a status query in Google's) |
| Repeating a request | the same part number replaces the part | a request at a stale offset is refused (tus: 409 Conflict) and changes nothing |
| A request that fails midway | the part is not stored; resend the whole part | tus: the server should keep what arrived; resume from the new offset |
| Completion | a request listing every part number and checksum | when the offset reaches the length |
| Cleanup | parts are billed until completed or aborted; no expiry unless you add a lifecycle rule | tus: optional `Upload-Expires`; Google: the session lasts a week |

This table comes from three documents read on 2026-11-26. S3's multipart page: parts uploaded independently and in any order, part numbers 1 to 10,000 (they need not be consecutive, unless checksums are used, when they must start at 1 and be consecutive), a retransmitted part with the same number overwrites the old one, the complete call needs the part numbers and ETags, the page says to keep your own list rather than use the listing, and parts are billed until you complete or stop the upload (with a lifecycle rule recommended to delete incomplete uploads). The tus 1.0.0 protocol: `HEAD` returns `Upload-Offset`; `PATCH` must carry the current offset or the server answers 409 and leaves the upload alone; the server should store as much of a request as it received; optional checksum (460 on mismatch), expiry and concatenation extensions. Google's resumable-upload page: a session URI valid for a week that works as an authentication token; bytes once persisted cannot be overwritten, so resending from an earlier offset is ignored up to the persisted point; chunks are multiples of 256 KiB; and the page's advice is to avoid chunking unless you need it.

The S3 limits decide the part size for large objects:

```python
from math import ceil

MIB, GIB = 1 << 20, 1 << 30

MAX_PARTS, MIN_PART, MAX_PART = 10_000, 5 * MIB, 5 * GIB          # the S3 multipart limits in the documentation page

def min_part_bytes(object_bytes):
    """Smallest part size that fits the object in at most 10,000 parts, and not below the 5 MiB minimum."""
    return max(MIN_PART, ceil(object_bytes / MAX_PARTS))

def max_object_bytes():
    """The largest object the part limits allow: 10,000 parts of 5 GiB."""
    return MAX_PARTS * MAX_PART

def part_count(object_bytes, part_bytes):
    return ceil(object_bytes / part_bytes)

def api_calls(object_bytes, part_bytes):
    """Calls for a multipart upload: one to start, one per part, one to complete."""
    return part_count(object_bytes, part_bytes) + 2

def held_connections(arrivals_per_s, seconds_each):
    """Connections open at once (Little's law: arrival rate times time in system)."""
    return arrivals_per_s * seconds_each
```

Parts must be at least 5 MiB (except the last) and there can be at most 10,000, so a 100 GiB object needs parts of at least 10.24 MiB, and the 5 GiB part maximum times 10,000 parts gives the 48.8 TiB object limit in the page. The documentation's own example, a 100 GB object in 100 MB parts, is 1,002 calls: one to start, 1,000 parts, one to complete.

### Deep dive 1: how big should a chunk be?

A resumable protocol exists because failures happen mid-transfer. Model the transfer as blocks (1 MiB each) where every block independently fails with probability `p`, a failure kills the request in flight, and the failed block still counts as sent. Two behaviours differ in what survives a failure: numbered parts keep nothing from a failed request, so the whole part is sent again; an offset protocol keeps the blocks that arrived.

```python
def expected_sent(total, chunk, p, resume_partial=False):
    """Expected blocks put on the wire to upload `total` blocks in requests of `chunk` blocks when each block
    fails independently with probability p. A failure kills the current request and the failed block counts as sent.
    resume_partial=False: the server keeps nothing from a failed request, so the whole chunk is sent again.
    resume_partial=True (offset protocols): the blocks before the failure persist and only the rest is sent again."""
    q = 1 - p
    if p == 0:
        return float(total)
    if resume_partial:
        return total / q
    full, rest = divmod(total, chunk)
    one = lambda c: (1 - q ** c) / (p * q ** c)
    return full * one(chunk) + (one(rest) if rest else 0.0)

def expected_requests(total, chunk, p, resume_partial=False):
    """Expected number of requests: whole chunks again after a failure, or one extra request per failure."""
    q = 1 - p
    full, rest = divmod(total, chunk)
    if resume_partial:
        return full + (1 if rest else 0) + total * p / q
    return full / q ** chunk + (1 / q ** rest if rest else 0.0)

def best_chunk(total, p, overhead, resume_partial=False):
    """Chunk size in blocks that minimises blocks sent plus `overhead` block-times per request, over all sizes."""
    return min(range(1, total + 1), key=lambda c: (expected_sent(total, c, p, resume_partial)
                                                   + overhead * expected_requests(total, c, p, resume_partial), c))
```

A 10 GiB object is 10,000 blocks; take `p = 0.001` (one block in a thousand fails, an **illustrative** rate) and charge each request the time of 2 blocks for the round trip and status check. The last two columns are the total cost in block-times: for numbered parts, and for offset resume.

| Chunk (blocks) | Blocks sent (parts) | Requests (parts) | Cost, numbered parts | Cost, offset resume |
|---|---|---|---|---|
| 10 | 10,055 | 1,010 | 12,075 | 12,030 |
| 61 | 10,316 | 174 | 10,665 | 10,358 |
| 100 | 10,523 | 111 | 10,744 | 10,230 |
| 1000 | 17,196 | 27 | 17,251 | 10,050 |
| 10000 | 22,135,948 | 22,137 | 22,180,222 | 10,032 |

- **One request for the whole file is hopeless without resume.** With numbered parts and a single 10,000-block request, the expected transfer is 22 million blocks: 2,214 times the file. The chance that all 10,000 blocks get through is `0.999^10000`, about 0.0045%.
- **Numbered parts have a sweet spot.** Small chunks pay request overhead (12,075 at 10 blocks), large ones pay for resending (17,251 at 1,000). The best size here is 61 blocks. The shape matters more than the number: it moves with the failure rate and the cost of a request.
- **With an offset, chunking only costs.** The best chunk for offset resume is the whole file, because a failure wastes at most the block that failed. That is the Google page's advice to avoid chunking. Its reasons to chunk anyway are the real ones: a source generated on the fly that you do not want to buffer, and clients (browsers) with request-size limits. The check confirms the formulas against a summation form, brute force over every size, and the lossy-network simulation below.
- **Parallelism is a separate benefit of numbered parts.** The S3 page lists throughput from parallel parts, quick recovery, pause and resume, and starting before the final size is known. None of that appears in the cost table.

### Deep dive 2: the bookkeeping that survives retries

Both protocols come down to a small ledger on the storage side and a loop on the client side. The code below models both with a simulated network: each block fails with probability `p` and kills the request, and an acknowledgement can be lost (the server did the work; the client does not know).

```python
import random

class Conflict(Exception):
    """The upload's offset is not the one the client sent (HTTP 409 in tus)."""

class PartStore:
    """Numbered-part upload (S3 multipart style). Parts arrive in any order; a part is stored only if the whole
    request arrived; the same part number again replaces the old one; completion needs the full list of parts."""
    def __init__(self, total_parts):
        self.total_parts, self.parts, self.done = total_parts, {}, None

    def put_part(self, n, blocks):
        if not 1 <= n <= self.total_parts:
            raise ValueError('part number out of range')
        self.parts[n] = tuple(blocks)

    def complete(self, manifest):
        if sorted(manifest) != list(range(1, self.total_parts + 1)) or any(n not in self.parts for n in manifest):
            raise ValueError('missing parts')
        self.done = [b for n in sorted(manifest) for b in self.parts[n]]
        return self.done

class OffsetStore:
    """Contiguous-offset upload (tus style). The server's offset is the truth. A request must name the current
    offset or it is refused with Conflict and changes nothing; whatever part of a request arrived is kept."""
    def __init__(self, length):
        self.length, self.data = length, []

    def head(self):
        return len(self.data)

    def patch(self, offset, blocks, arrived=None):
        if offset != len(self.data):
            raise Conflict(len(self.data))
        keep = list(blocks) if arrived is None else list(blocks)[:arrived]
        self.data.extend(keep)
        if len(self.data) > self.length:
            raise ValueError('past the declared length')
        return len(self.data)

class Flaky:
    """Network between client and server: each block fails with probability p (the request dies there and later
    blocks do not arrive); an acknowledgement is lost with probability ack_loss. Counts the blocks put on the wire."""
    def __init__(self, p, ack_loss=0.0, seed=0):
        self.p, self.ack_loss, self.rng = p, ack_loss, random.Random(seed)
        self.blocks_sent = self.requests = self.heads = 0

    def transmit(self, blocks):
        """Returns how many leading blocks arrive, and whether the request got through whole."""
        self.requests += 1
        for i in range(len(blocks)):
            self.blocks_sent += 1
            if self.rng.random() < self.p:
                return i, False
        return len(blocks), True

    def ack_lost(self):
        return self.rng.random() < self.ack_loss

def upload_parts(source, chunk, store, net, seed=1):
    """Send numbered parts in a random order, retrying each until acknowledged, then complete with the list of
    parts the client itself recorded (the S3 page says to keep your own list rather than trust a listing)."""
    chunks = [source[i:i + chunk] for i in range(0, len(source), chunk)]
    order = list(range(1, len(chunks) + 1))
    random.Random(seed).shuffle(order)
    acked = set()
    for n in order:
        while n not in acked:
            got, whole = net.transmit(chunks[n - 1])
            if not whole:
                continue                                  # a half-sent part is not stored; send it again
            store.put_part(n, chunks[n - 1])
            if not net.ack_lost():
                acked.add(n)
    return store.complete(sorted(acked))

def upload_offset(source, chunk, store, net):
    """Resume from the server's offset. After a request whose answer arrived the client trusts the new offset;
    after a failure or a lost answer it asks (a HEAD) where the server is, and sends the rest from there."""
    off = store.head()
    while off < len(source):
        blocks = source[off:off + chunk]
        got, whole = net.transmit(blocks)
        new = store.patch(off, blocks, None if whole else got)
        if whole and not net.ack_lost():
            off = new
        else:
            net.heads += 1
            off = store.head()
    return store.data
```

What the tests establish, with injected failures at three severities and chunk sizes from 1 to 200:

- **Both uploads rebuild the source exactly,** including with lost acknowledgements, random part order, and a lost answer after a part was stored (the part is simply stored again, as the same number replaces it).
- **The part ledger refuses to complete without every part,** with a duplicate, or with a part never uploaded, and rejects part numbers outside the range. Completion takes the client's own list, as the S3 page recommends.
- **The offset guard does the work.** A client that repeats a `PATCH` at a stale offset after a lost answer gets `Conflict` and the data is unchanged; the check runs such a blind client and sees the refusal. The real client avoids it by asking where the server is whenever an answer is missing.
- **The simulation agrees with the formulas.** Averaged over 400 runs of 200 blocks in 20-block chunks at `p = 0.01`, numbered parts send within 2% of `expected_sent` (222.6 blocks) and offset resume within 2% of 202.0.

What the design needs around the ledger: an `uploads` table (upload id, owner, key, size, part count, status, created), expiry for abandoned uploads (S3 does not expire them by itself; Google's session lasts a week), and a completion step that verifies the final object. S3 can validate a full-object checksum on completion and fails the request with a digest error on a mismatch. Google's page says you cannot check intermediate chunks of a resumable upload, only the final object, and recommends supplying an MD5 for it. tus defines a per-request checksum extension.

Visual (planned): a 10-part upload with parts arriving out of order and one retried, beside a byte bar with an offset marker that moves after each acknowledged request.

---

## 4. Long-Running Tasks

### Return a handle, not the answer

For work longer than a request can wait, the API accepts the job, stores it, and returns at once with a handle. Google's API improvement proposal AIP-151 (read 2026-11-26) names the pattern: a method that may take significant time returns an `Operation` instead of its result, "a token that can be used to track progress and retrieve the result". The `Operation` has a `done` flag, a `metadata` message for progress, and either a `response` or an `error` when done. The proposal's rule of thumb is that 10 seconds is a significant time, it suggests operations may expire about 30 days after completion, and it says a resource that does not allow parallel operations must answer `ABORTED` if you start another. On a plain HTTP API the same shape is `POST /exports` answered with `202 Accepted` and a `Location` of `/operations/{id}`, and `GET /operations/{id}` answering with the state. Make `POST` safe to retry with a client-supplied request id (see the Idempotency lesson), or a lost response creates a second job.

### Deep dive 3: a task record with a lease

A worker can die at any moment, and a slow one is indistinguishable from a dead one. The task record has to say who owns it now, for how long, and which attempt that is.

| State | Meaning | Leaves by |
|---|---|---|
| `QUEUED` | waiting for a worker | `claim` |
| `RUNNING` | a worker holds a lease | `complete`, `fail`, `cancel`, or the lease running out |
| `SUCCEEDED`, `FAILED`, `CANCELLED` | terminal | nothing: they never change |

A worker **claims** a task and gets the attempt number as a **fencing token**. Every later call (`heartbeat`, `complete`, `fail`) must carry it. A heartbeat extends the lease. A reaper returns tasks whose lease has expired to `QUEUED`, or marks them `FAILED` when attempts are used up.

```python
import random

QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED = 'QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED'

TERMINAL = {SUCCEEDED, FAILED, CANCELLED}

class TaskStore:
    """Durable task records with leases. A worker claims a task and gets a fencing token (the attempt number);
    every later call from that worker must present it. A lease that is not renewed in time is reclaimed by reap()."""
    def __init__(self, lease_s, max_attempts):
        self.lease_s, self.max_attempts, self.tasks = lease_s, max_attempts, {}

    def submit(self, task_id):
        """Idempotent: submitting an id that exists changes nothing, so a retried request does not enqueue twice."""
        self.tasks.setdefault(task_id, {'state': QUEUED, 'attempts': 0, 'lease_until': None,
                                        'progress': 0, 'result': None, 'error': None})
        return task_id

    def claim(self, now):
        for tid, t in self.tasks.items():                 # dicts keep submission order
            if t['state'] == QUEUED:
                t.update(state=RUNNING, attempts=t['attempts'] + 1, lease_until=now + self.lease_s)
                return tid, t['attempts']                 # the attempt number is the fencing token
        return None

    def _mine(self, tid, token):
        t = self.tasks.get(tid)
        return t if t and t['attempts'] == token and t['state'] in (RUNNING, CANCELLED) else None

    def heartbeat(self, tid, token, now, progress=None):
        t = self._mine(tid, token)
        if t is None:
            return 'stale'
        if t['state'] == CANCELLED:
            return 'cancelled'                            # the worker learns to stop at its next heartbeat
        t['lease_until'] = now + self.lease_s
        if progress is not None:
            t['progress'] = progress
        return 'ok'

    def complete(self, tid, token, result):
        t = self._mine(tid, token)
        if t is None or t['state'] != RUNNING:
            return False
        t.update(state=SUCCEEDED, result=result, progress=100, lease_until=None)
        return True

    def fail(self, tid, token, error):
        t = self._mine(tid, token)
        if t is None or t['state'] != RUNNING:
            return 'stale'
        if t['attempts'] < self.max_attempts:
            t.update(state=QUEUED, lease_until=None)
            return 'retry'
        t.update(state=FAILED, error=error, lease_until=None)
        return 'failed'

    def cancel(self, tid):
        t = self.tasks.get(tid)
        if t is None or t['state'] in TERMINAL:
            return False
        t.update(state=CANCELLED, lease_until=None)
        return True

    def reap(self, now):
        """Reclaim every running task whose lease has run out; returns their ids."""
        out = []
        for tid, t in self.tasks.items():
            if t['state'] == RUNNING and t['lease_until'] <= now:
                if t['attempts'] < self.max_attempts:
                    t.update(state=QUEUED, lease_until=None)
                else:
                    t.update(state=FAILED, error='lease expired on the last attempt', lease_until=None)
                out.append(tid)
        return out

    def get(self, tid):
        """What a client polling GET /operations/{id} sees: done is true exactly when the state is terminal."""
        t = self.tasks[tid]
        view = {'state': t['state'], 'done': t['state'] in TERMINAL, 'progress': t['progress']}
        if t['state'] == SUCCEEDED:
            view['result'] = t['result']
        if t['state'] == FAILED:
            view['error'] = t['error']
        return view

def run_fleet(n_tasks, workers, crash_p, lease_s=5, max_attempts=3, work_s=8, seed=0, horizon=5000):
    """Second-by-second simulation. Each claim does `work_s` seconds of work and heartbeats every second; with
    probability crash_p the worker dies at a random second during that work, silently. Returns
    (seconds until every task is terminal, {state: count}, total claims)."""
    rng = random.Random(seed)
    store = TaskStore(lease_s, max_attempts)
    for i in range(n_tasks):
        store.submit(i)
    busy = {}                                             # worker -> (task, token, seconds left, crash_at or None)
    claims = 0
    for now in range(horizon):
        store.reap(now)
        for w in range(workers):
            if w not in busy:
                got = store.claim(now)
                if got:
                    claims += 1
                    crash_at = rng.randrange(work_s) if rng.random() < crash_p else None
                    busy[w] = [got[0], got[1], work_s, crash_at]
        for w in list(busy):
            tid, token, left, crash_at = busy[w]
            if crash_at is not None and work_s - left == crash_at:
                del busy[w]                               # the worker is gone; nobody tells the store
                continue
            if store.heartbeat(tid, token, now) != 'ok':
                del busy[w]
                continue
            busy[w][2] -= 1
            if busy[w][2] == 0:
                store.complete(tid, token, 'done')
                del busy[w]
        if all(t['state'] in TERMINAL for t in store.tasks.values()):
            counts = {}
            for t in store.tasks.values():
                counts[t['state']] = counts.get(t['state'], 0) + 1
            return now, counts, claims
    raise RuntimeError('not finished')
```

The scenario the check walks through:

| Time | Event | Result |
|---|---|---|
| 0 | worker A claims task `t`, token 1, lease until 5 | `RUNNING` |
| 3 | A heartbeats with progress 40 | lease until 8 |
| 8 | reaper runs; A has gone silent (a long pause, say) | `t` back to `QUEUED` |
| 9 | worker B claims `t`, token 2 | `RUNNING`, attempt 2 |
| 10 | A wakes up and heartbeats with token 1 | `stale`: A must stop |
| 10 | A calls `complete` with token 1 | refused, the result is dropped |
| 11 | B completes with token 2 | `SUCCEEDED` |

- **The token stops a late worker from overwriting a newer result,** and no lock service is involved because the store itself compares the number. This is the same idea as the fencing token in the flash-sale lesson, applied to tasks.
- **Execution is at least once, not exactly once.** Task `t` ran, at least partly, twice: A may have finished its side effects before it was fenced out. The effects therefore have to be idempotent (write results under a key derived from the task id, charge with an idempotency key). The store protects its own record, not the world outside it.
- **A task that keeps killing workers must stop.** After `max_attempts` the task becomes `FAILED` with an error instead of cycling forever. A poison task that crashes every worker is the usual reason.
- **Cancellation is cooperative.** `cancel` marks the record; a running worker learns at its next heartbeat (`cancelled`) and must stop, and its `complete` is refused.
- **Submitting twice is harmless.** `submit` with an existing id changes nothing.

The fleet simulation puts 1,000 tasks on 20 workers. Each task takes 8 seconds, leases are 5 seconds, tasks get 3 attempts, and a claiming worker dies silently at a random second with probability `c`. Closed forms say each task makes `(1 - c^3) / (1 - c)` claims on average and fails with probability `c^3`:

| Crash rate | Seconds to finish | Succeeded | Failed | Claims | Expected claims |
|---|---|---|---|---|---|
| 0% | 399 | 1000 | 0 | 1000 | 1000 |
| 10% | 440 | 999 | 1 | 1124 | 1110 |
| 20% | 468 | 993 | 7 | 1268 | 1240 |
| 40% | 530 | 939 | 61 | 1553 | 1560 |

At a 40% crash rate, 61 of 1,000 tasks fail permanently (the formula says 64), 553 extra claims are made, and the batch takes a third longer. The lease length shows up as the wait before a dead worker's task is retried, so a short lease finds failures sooner and fences out slow workers more often. The check compares the store with a second implementation that replays an event log, on 300 random operation sequences with random times, and asserts every return value agrees.

What to add around it: a visibility-style retry delay so a failing task does not spin, a dead-letter list for `FAILED` tasks that someone looks at, polling with backoff on the client (or a notification when `done`), and, for jobs with many dependent steps, a workflow engine instead of hand-built state (see the Idempotency, Outbox & Sagas lesson). Retention matters here too: AIP-151's 30-day suggestion is a policy about how long finished records are kept.

Visual (planned): the task lifecycle as a state diagram, with the scenario above as a swimlane of worker A, the reaper and worker B.

---

## 5. Real-Time Updates

### The ladder, and its arithmetic

| Mechanism | How it works | Cost |
|---|---|---|
| short polling | client asks every `T` seconds | a request every `T` per client, most of them empty; average staleness `T/2` |
| long polling | the server holds the request until there is an event or a timeout; the client re-asks at once | one held request per client; headers on every message |
| server-sent events | one long-lived HTTP response the server keeps writing to; built-in reconnect and event ids | one open connection per client, one direction |
| WebSocket | an HTTP upgrade into a two-way message channel | one open connection per client, both directions, your own resume logic |

RFC 6202 (read 2026-11-26) describes polling and its two push alternatives. It says short polling's cost depends strongly on the latency you can accept; that long polling gives an average latency near one network transit but a maximum of over three (response, next request, response); that a long-poll client under load degrades gracefully because queued events go out in one response; that every long-poll message carries a full set of HTTP headers; and that holding requests open costs resources at gateways and proxies. For timeouts it says experiments have worked at up to 120 seconds, that 30 seconds is the generally safer choice, and that the browser default of 300 seconds is longer than most network infrastructure tolerates.

Take 1,000,000 users and one event per user per hour (278 events per second overall):

```python
from math import exp

def poll_load(users, interval_s):
    """Requests per second when every user polls every `interval_s` seconds."""
    return users / interval_s

def long_poll_load(users, timeout_s, per_user_event_rate):
    """Requests per second with long polling: each request is held until an event (rate lam per user) or the
    timeout, then replaced at once, so a user makes lam / (1 - exp(-lam * T)) requests per second."""
    lam = per_user_event_rate
    return users / timeout_s if lam == 0 else users * lam / (1 - exp(-lam * timeout_s))

def keepalive_rate(connections, period_s):
    """Comment lines per second the server writes to keep idle streams alive."""
    return connections / period_s

def reconnect_rate(clients, spread_s):
    """New connections per second when `clients` reconnect at random times spread evenly over `spread_s` seconds."""
    return clients / spread_s
```

| Approach | Requests or writes per second | Mean staleness | Share of requests that carry an event |
|---|---|---|---|
| poll every 5 s | 200,000 | 2.5 s | 0.14% |
| poll every 1 s | 1,000,000 | 0.5 s | 0.03% |
| long poll, 30 s timeout | 33,472 | about one transit | most requests end in a timeout |
| SSE or WebSocket | 1,000,000 open connections, 278 pushes per second | about one transit | all |

Push wins on requests, loses on connections held open, and adds a cost people forget: keeping idle connections alive. The standard for server-sent events suggests a comment line about every 15 seconds to stop legacy proxies dropping the connection, and `keepalive_rate(1_000_000, 15)` is 66,667 small writes per second. WebSocket has pings for the same purpose; the RFC says an endpoint may send one any time as a keepalive and the other end must answer. Another cost is the thundering reconnect: when a server holding 100,000 connections restarts, spreading the reconnects evenly over 2 seconds still means `reconnect_rate(100_000, 2)` = 50,000 new connections per second at the survivors. The SSE standard lets a server set the reconnect delay (`retry:`), and says a client may add exponential backoff; add jitter on top.

### Deep dive 4: resuming a stream

The failure that decides the design is not "the connection dropped", it is "which events did I miss?". The WHATWG HTML standard (section 9.2, read 2026-11-26) gives server-sent events the pieces for the answer. The stream is `text/event-stream`, UTF-8, made of fields separated by line breaks and events ended by a blank line. The `id` field sets the client's *last event id*, and when the client reconnects it sends that value in the `Last-Event-ID` header. The `retry` field sets the reconnect delay. A comment line starts with a colon. An event cut off before its blank line is never dispatched. The parser below implements those rules, and the check runs the standard's own examples through it (the four-block `first event` example, the `YHOO` example, the empty-data example, and the two equal events), plus carriage-return line endings, a byte-order mark, an `id` with a NUL, and 3,000 random strings against a second, character-at-a-time parser.

```python
import re

def parse_event_stream(text, last_id=''):
    """Parse a text/event-stream the way the WHATWG HTML standard (section 9.2) describes. Lines end in CRLF, LF or
    CR; a blank line dispatches; `:` starts a comment; fields are event, data, id, retry. An event cut off before its
    blank line is dropped. Returns (events, last event id string, reconnection time in ms or None); each event is
    (type, data, lastEventId)."""
    if text.startswith('\ufeff'):
        text = text[1:]                                   # one leading byte order mark is stripped
    events, retry = [], None
    data, etype, id_buf = [], '', last_id
    lines = re.split(r'\r\n|\n|\r', text)
    if lines and lines[-1] == '':
        lines.pop()                                       # the text ended with a line terminator
    complete = text.endswith(('\n', '\r'))                # a last line with no terminator is never dispatched
    for i, line in enumerate(lines):
        if i == len(lines) - 1 and not complete:
            break                                         # an unterminated final line is incomplete
        if line == '':
            last_id = id_buf                              # the id buffer is not reset: it stays until the server changes it
            if data:                                      # an event with no data lines is not dispatched
                events.append((etype or 'message', '\n'.join(data), last_id))
            data, etype = [], ''
            continue
        if line.startswith(':'):
            continue
        name, sep, value = line.partition(':')
        if sep and value.startswith(' '):
            value = value[1:]
        if name == 'event':
            etype = value
        elif name == 'data':
            data.append(value)
        elif name == 'id':
            if '\0' not in value:
                id_buf = value
        elif name == 'retry':
            if value.isascii() and value.isdigit():
                retry = int(value)
    return events, last_id, retry
```

The `Last-Event-ID` header only says where the client got to. The server needs a log to answer from, and a log is bounded, so the answer has three cases: the missed events, nothing, or "I no longer have them". The last case needs a **snapshot**:

```python
import random

class EventLog:
    """Server side of a resumable stream of increments. Ids count up from 1 and only the newest `keep` events are
    kept; the running total is kept separately so a snapshot is always available."""
    def __init__(self, keep):
        self.keep, self.events, self.next_id, self.total = keep, [], 1, 0

    def append(self, delta):
        self.events.append((self.next_id, delta))
        self.total += delta
        self.next_id += 1
        del self.events[:-self.keep]

    def since(self, last_id):
        """Events with id > last_id, or None when the log no longer reaches back that far (the client has a gap)."""
        oldest = self.events[0][0] if self.events else self.next_id
        if last_id < oldest - 1:
            return None
        return [e for e in self.events if e[0] > last_id]

    def serve(self, last_id):
        """The response to a (re)connection that sent Last-Event-ID: the missed events, or a snapshot after a gap."""
        missed = self.since(last_id)
        if missed is None:
            return 'event: snapshot\nid: %d\ndata: %d\n\n' % (self.next_id - 1, self.total)
        return ''.join('id: %d\ndata: %d\n\n' % e for e in missed)

class Subscriber:
    """Client side: applies increments once each, in order, and keeps the last event id for the next reconnect."""
    def __init__(self):
        self.total, self.last_id, self.snapshots = 0, 0, 0

    def receive(self, text):
        """Feed whatever arrived of a response (it may end mid-event). Returns the number of events applied."""
        events, _, _ = parse_event_stream(text, str(self.last_id) if self.last_id else '')
        applied = 0
        for etype, data, eid in events:
            n = int(eid)
            if etype == 'snapshot':
                self.total, self.last_id = int(data), n
                self.snapshots += 1
            elif n == self.last_id + 1:
                self.total += int(data)
                self.last_id = n
                applied += 1
            elif n > self.last_id + 1:
                raise ValueError('gap: have %d, got %d' % (self.last_id, n))
            # n <= last_id is a duplicate and is ignored
        return applied

def run_stream(seed, keep, events=200):
    """The server appends increments in random bursts. After each burst the client reconnects with its last event
    id, and in 70% of the reconnects the connection dies at a random character of the response. At the end one
    clean reconnect. Returns (client total and last id equal the server's, snapshots the client had to take)."""
    rng = random.Random(seed)
    log, sub = EventLog(keep), Subscriber()
    made = 0
    while made < events:
        for _ in range(rng.randrange(1, 12)):
            log.append(rng.randrange(1, 10))
            made += 1
        text = log.serve(sub.last_id)
        cut = rng.randrange(len(text) + 1) if rng.random() < 0.7 else len(text)
        sub.receive(text[:cut])
    sub.receive(log.serve(sub.last_id))
    return (sub.total, sub.last_id) == (log.total, log.next_id - 1), sub.snapshots
```

`run_stream` makes the server append increments in bursts while the client reconnects after each burst, and cuts the connection at a random character 70% of the time. Over 200 runs per row, the client's total and last id equal the server's in every run, and this is how often a snapshot was needed:

| Events kept in the log | Snapshots needed in 200 runs |
|---|---|
| 2 | 2,171 |
| 5 | 1,920 |
| 50 | 0 |

- **Cut anywhere, the client never applies half an event.** The parser drops a partial event, so the events parsed from a cut response are always a prefix of the full stream; the client's last id therefore always names a whole event.
- **Increments are not idempotent, and the stream is still correct.** A duplicate (an id at or below the last applied) is ignored, and a gap raises an error instead of being applied. The log's `since` returns only events above the client's id, so duplicates are not sent in the first place; the client check is the second line of defence.
- **The retention window is a requirement.** With 2 events kept, nearly every reconnect after a burst needs a snapshot; with 50 none did, because the bursts were shorter than the window. Size the log to cover your longest tolerated disconnect, and always have the snapshot path, because a phone that was off for a day will exceed any window.
- **WebSockets give you none of this.** The sections of RFC 6455 read here define the opening handshake (an HTTP upgrade, so it works on the usual HTTP ports and through proxies), messages made of frames, and ping and pong. They define no event ids, acknowledgements or replay, so a WebSocket application builds the same log, ids and snapshot itself, which is why SSE is the lighter choice when data flows only one way.

Visual (planned): a timeline of event ids with a connection drop, the reconnect carrying `Last-Event-ID`, and the two outcomes: replay from the log, or a snapshot after a gap.

### Choosing

| Need | Choose | Watch for |
|---|---|---|
| a status page that changes every few seconds, few users | short polling with backoff | request volume grows with users divided by interval |
| server to browser, one direction, resumable | server-sent events | client limits on connections per server, proxies and buffering, keepalive cost |
| both directions, frequent client messages (chat, games, collaboration) | WebSocket | resume and ordering are yours; connection state on the server |
| an environment where only ordinary request and response works | long polling | held requests at gateways, 30 s timeouts, headers on every message |
| huge fan-out of rare events | push with a pub/sub tier routing events to the servers holding the connections | reconnect storms, snapshot load |

---

## 6. Failure Modes

| Failure | Effect | Mitigation |
|---|---|---|
| uploads proxied through app servers | connections and bandwidth exhausted by a few large uploads | direct-to-storage with signed URLs |
| a signed URL leaks | anyone can upload or read until it expires | short expiry, one URL per part, scope to one key |
| resume after URL expiry | the request is refused | issue new URLs on resume |
| one request for a whole large file | an enormous expected transfer under failure | chunk it, or use an offset protocol |
| chunks too small | request overhead dominates | choose the size from failure rate and per-request cost |
| abandoned multipart uploads | parts billed forever | a lifecycle rule or a sweeper; record uploads in your own table |
| completion without checking | a corrupt or partial object becomes visible | verify checksum and size before `READY` |
| worker dies mid-task | the task sits `RUNNING` forever | lease, heartbeat, reaper |
| a stale worker finishes late | an old result overwrites a new one | fencing token compared by the store |
| a poison task | crashes every worker that claims it | `max_attempts`, then `FAILED` and a dead-letter list |
| non-idempotent effects | duplicate emails, charges | idempotency keys derived from the task id |
| a reconnecting client misses events | silently wrong UI | event ids, `Last-Event-ID`, replay window, snapshot after a gap |
| all clients reconnect together | a reconnect storm after a deploy | jittered backoff, server-set `retry`, connection draining |
| idle connections dropped by proxies | clients flap | keepalive comments or pings |

---

## 7. What Real Systems Document

All read 2026-11-26. S3 documents multipart upload (limits, part overwrite, checksums, billing of incomplete uploads) and presigned URLs (bearer-token semantics, expiry checked per request). The tus project publishes a complete resumable-upload protocol with the 409 offset guard. Google Cloud Storage documents resumable sessions, persisted-offset resume and the advice not to chunk without a reason. Google's AIP-151 documents the long-running operation resource. The WHATWG HTML standard documents the event-stream format and reconnect behaviour, and RFC 6202 and RFC 6455 document long polling and the WebSocket opening handshake and control frames. What none of these tells you is your own failure rate or request cost, which is why the chunk-size table is a model to adapt, not a recommendation.

---

## 8. Pitfalls Checklist

1. **Routing large uploads through the API tier.** Count held connections with Little's law before you do.
2. **One request per large file with no resume.** Expected cost explodes with size and failure rate.
3. **A signed URL treated like a credential-free link.** It is a bearer token; give it a short expiry and one purpose.
4. **Chunking for its own sake with an offset protocol.** It adds requests and saves nothing; chunk only for memory or client limits.
5. **No cleanup for abandoned uploads.** The storage bill is the symptom.
6. **Running the work in the request handler.** Anything near your longest timeout needs a handle and a worker.
7. **Treating a missing heartbeat as proof the worker is dead.** It may only be slow; the fencing token, not the lease, protects correctness.
8. **Retrying a task without idempotent effects.** At-least-once execution duplicates the side effects.
9. **Pushing events with no ids.** A reconnecting client cannot tell what it missed.
10. **Unbounded or missing replay.** Bound the log, and keep a snapshot path for clients beyond it.
11. **Forgetting what idle connections cost.** Keepalives and reconnect storms are the bills of push.

---

## Drills

1. Two 3 GiB uploads begin per second at 10 MiB per second each. How many connections are open and how much data flows through your tier if the bytes go through the API, and what does direct upload change?
2. A 100 GiB object: what is the smallest part size S3 allows, and how many calls does a 100 GB upload in 100 MB parts make?
3. Why does a client that resumes an S3 multipart upload need its own list of parts, and what does an offset protocol use instead?
4. In the chunk-size table, why is 61 blocks best for numbered parts but the whole file best with offset resume, and what two reasons does the Google page give for chunking anyway?
5. A client sends `PATCH` at offset 0, the server stores it but the answer is lost, and the client sends the same request again. What happens in tus, and what should the client have done instead?
6. Walk through the lease scenario: why is the heartbeat from worker A at time 10 refused, why is the result dropped, and what must the task's side effects be?
7. With 3 attempts and a 20% crash rate, what share of tasks fails permanently and how many claims does a task make on average?
8. A phone reconnects with `Last-Event-ID: 41` but the log only holds events 60 to 80. What does the server send, and what does the client do with it? What happens if the connection dies halfway through that response?

---

## Homework

1. Change `p` and the per-request overhead in `best_chunk` and find where the best numbered-part chunk reaches 10 times the size you got; explain it from the formula.
2. Add per-part signed URLs to the upload client: each URL expires after a configurable number of simulated seconds, and a retry after expiry must ask for a new one. Count the extra requests.
3. Add a checksum to each part in `PartStore` and make `complete` verify them; inject corruption in `Flaky` and show completion failing.
4. Add a retry delay with exponential backoff and a dead-letter list to `TaskStore`, then rerun the fleet at 40% crashes and report how long the poison tasks take to surface.
5. Add a slow-worker model to `run_fleet` (a pause longer than the lease, not a crash) and count how many tasks are executed twice and how many results are fenced out.
6. Write a WebSocket version of the stream: client messages carry the last id, the server replays or snapshots. Compare the code with the SSE version and say what the browser did for free in the SSE one.
7. Read the WHATWG event-stream section end to end and find a case the parser here handles differently from the standard, if there is one.

---

## Sources

All read 2026-11-26.

- Amazon S3 User Guide, *Uploading and copying objects using multipart upload*, docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html. Read in full except the permissions table at the end. Source for part semantics, checksums, the 1,002-call example, billing and the lifecycle-rule recommendation.
- Amazon S3 User Guide, *Amazon S3 multipart upload limits*, docs.aws.amazon.com/AmazonS3/latest/userguide/qfacts.html. Read in full. Source for 10,000 parts, 5 MiB to 5 GiB parts, 48.8 TiB.
- Amazon S3 User Guide, *Sharing objects with presigned URLs*, docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html. Read in full. The page is about downloads in its examples; the expiry and bearer-token statements are general to presigned URLs on the page.
- tus.io, *Resumable upload protocol 1.0.0*, tus.io/protocols/resumable-upload. Read in full except the linked FAQ.
- Google Cloud documentation, *Resumable uploads*, cloud.google.com/storage/docs/resumable-uploads. Read in full. The step-by-step "Performing resumable uploads" page it links to was not read.
- Google, AIP-151 *Long-running operations*, google.aip.dev/151. Read in full. The `google.longrunning` protocol definitions it references were not read.
- WHATWG, *HTML Living Standard*, section 9.2 Server-sent events, html.spec.whatwg.org/multipage/server-sent-events.html. Read in full except the closing implementation-advice paragraph.
- Loreto et al., RFC 6202 *Known Issues and Best Practices for the Use of Long Polling and Streaming in Bidirectional HTTP*, rfc-editor.org/rfc/rfc6202. Read sections 1 and 2 and sections 5.1 to 5.6; the streaming and technology-overview sections were not read.
- Fette and Melnikov, RFC 6455 *The WebSocket Protocol*, rfc-editor.org/rfc/rfc6455. Read sections 1.1 to 1.3 (in part), 5.5.2, 5.5.3, 5.6 and 5.7. The framing, masking, closing and security sections were not read, so statements about what the protocol does not define are limited to those sections.

## Further reading (not consulted)

The `google.longrunning.Operations` API reference (including cancel and wait); the Temporal and AWS Step Functions documentation for durable workflows; the AWS SQS visibility-timeout documentation, which is the same lease idea in a queue; Netflix, Slack and Discord engineering posts on running millions of WebSocket connections; the tus FAQ and implementations page. None was read for this lesson, and the models here are this lesson's own.

*Last reviewed: 2026-11-26.*
