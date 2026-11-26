# Lesson 55 — Case Study: File Sync and Storage (Dropbox / Google Drive)

> **Priority:** ★★★★☆ — a favourite at product-infrastructure companies, and the best exercise in this course for content hashing, journals and conflict handling.
>
> **Study time:** 75 minutes. **Do this after:** Distributed Object Storage (sy35) and Scaling Patterns II: Blobs, Long-Running Tasks and Real-Time Updates (sy52).
>
> **Level:** core.

A sync service keeps a folder identical on many devices and on a server, including devices that were offline for a week
and two people editing the same file. **Overlap with sy35 and sy52:** sy35 designs the storage tier (chunk stores,
erasure coding, commit data before metadata) and sy52 designs resumable uploads. This lesson starts above them. It is
about the client, the metadata journal, what crosses the wire when a file changes, conflicts, moves and notifications.
Storage internals appear only where they constrain sync. The code (chunking, a journal-and-cursor protocol, conflict
copies, directory moves) is checked in `test/lesson_code/sy55_check.py`, and every capacity number in
`test/lesson_code/capacity_check_c.py`.

---

## 1. Mental Model

> **File sync is a replicated append-only journal of file versions plus a content-addressed block store. A file version
> is a short list of block hashes; devices exchange journal rows and move only the blocks the other side lacks.**

What follows from it:

- **Metadata and bytes are separate systems.** The journal is small, ordered and strongly consistent; the block store
  is huge, immutable and dumb (the control-plane and data-plane split of sy35).
- **A device is a cursor.** It remembers how far into each namespace's journal it has read and asks for rows after that.
- **Sync cost is proportional to what changed, not to file size,** but only if the chunking survives edits (section 5).
- **Offline is normal, not an error.** Reconciling long-diverged copies is the product, so conflict handling must be
  designed, not patched in.
- **Identity must outlive names.** A move is one change to one object only if files and folders have stable ids.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "sync a folder across devices" | per-namespace journal, per-device cursor, long-poll notification |
| "do not re-upload the whole file" | split into blocks, hash each, upload only blocks the server lacks |
| "edit a large file, small change" | block-level delta; content-defined chunks if edits insert or delete bytes |
| "same file uploaded by many users" | content-addressed blocks: identical hash, one stored copy |
| "two people edit the same file" | optimistic concurrency on a base version, keep both on conflict |
| "move a folder" | stable ids, a move is one pointer change; reject moves that create cycles |
| "shared folders" | the shared folder is its own namespace, mounted in each member's tree |
| "does not fit on my laptop" | placeholder files, download on demand |
| "upload while the other device is waiting" | stream blocks through to the receiver before the commit |

---

## 3. Requirements and Capacity

**Functional.** Create, edit, delete, move and rename files and folders; sync to all of a user's devices and to
collaborators; share folders; resume interrupted transfers; keep version history. **Out of scope:** real-time co-editing
(sy38), search, previews, sharing permissions in detail.

**Non-functional.** Never lose or corrupt user data (durability beats freshness). Converge: once devices stop changing
files and sync, every device holds the same tree. Efficient: bytes sent proportional to change. Fresh: a change on one
device appears on others within seconds.

**Capacity estimate.** Inputs are **assumptions**; every result is reproduced by `test/lesson_code/capacity_check_c.py`.

| Input (assumed) | Value |
|---|---|
| daily active users | 100 million |
| file changes per user per day | 20 |
| peak to average | 3 |
| average changed file | 2 MB |
| journal row (path, blocklist, ids, times) | 300 bytes |
| block size, hash size | 4 MB, 32 bytes (SHA-256) |
| data under management | 1 exabyte |
| block-index entry | 64 bytes |
| devices per active user | 2, each holding one idle long-poll connection |
| long-poll connections per server | 100,000 |
| other devices notified per change | 1.5 |
| new device first sync | 50 GB over a 100 Mbit/s link |

| Result | Arithmetic | Value |
|---|---|---|
| file changes | 100 million x 20 / 86,400 | 23,148 file changes per second, 69,444 per second at the 3x peak |
| if every change re-sent the whole file | 23,148 x 2 MB | 46.3 GB/s, about 370 Gbit/s |
| journal growth | 100 million x 20 | 2 billion journal rows per day |
| journal bytes | 2 billion x 300 B | 600 GB per day, 219 TB per year |
| blocklist of a 100 MB file | 25 blocks | 25 hashes x 32 bytes = 800 bytes |
| blocks in 1 EB | 10¹⁸ / 4 MB | 250 billion blocks |
| block index | 250 billion x 64 B | 16 TB |
| notification connections | 100 million x 2 | 200 million long-poll connections |
| notification servers | 200 million / 100,000 | 2,000 servers |
| notification rate | 23,148 x 1.5 | 34,722 notifications per second |
| first sync of a new device | 50 GB x 8 / 100 Mbit/s | 4,000 seconds, about 67 minutes |

Four conclusions. **Never move whole files:** 46.3 GB/s is the cost of the naive design, and block-level delta is what
removes it. **The journal is small and the block index is moderate:** 16 TB fits a sharded relational cluster, which is
what Dropbox says it used for its block index (section 9). **The expensive part is connections:** 200 million idle
connections mean notification fan-out, not storage, is the first thing to design. **A first sync takes over an hour,**
which is the case for downloading only what the user opens.

Visual (planned): two devices and a server; a blocklist commit returning "need blocks", the block upload, the second commit, and the other device's long-poll waking to read the new journal row.

---

## 4. API and Data Model

The model follows what Dropbox's engineers describe for their file system (2014): a **namespace** is the root of a
directory tree; each user has a root namespace, and a shared folder is a namespace that can be mounted in several
users' roots. Every file is identified by a namespace and a relative path. A file's content is a **blocklist**, the list
of SHA-256 hashes of its 4 MB blocks (the last block may be smaller). The metadata database is an **append-only
journal**: each row is one version of one file, with a journal id (JID) that increases within the namespace. Two kinds of
server: a **block server** holding hash to encrypted bytes with no idea what files are, and a **metadata server** holding
users, namespaces and the journal.

```
commit(ns, path, blocklist, base)  -> ok(jid) | need_blocks(hashes) | conflict(head_jid)
store(hash, bytes)                 -> ok
list(ns, cursor)                   -> journal rows with jid > cursor
notify: long-poll connection per device; answers "something changed in ns X"
```

Two details are this lesson's design, not something the Dropbox posts state: the `base` argument (the JID the client's
edit was made on, which makes the commit an optimistic-concurrency check), and the "conflicted copy" naming. What Dropbox
describes is the commit that answers "need blocks", the block upload, the retry, and the cursor-based `list`.

Because the commit is refused until every block exists, **the journal never points at a missing block**: data first,
metadata second, the same ordering as in sy35.

---

## 5. Deep Dive 1: Chunking and Delta

Hash a file in **fixed-size blocks** and a change inside a block costs one block. But insert a few bytes near the
front and every later block shifts, so every later hash changes and the whole tail is re-uploaded. **Content-defined
chunking** cuts at positions chosen by the content: a rolling hash over a small window is computed at every byte, and
a chunk ends where the hash's top bits are zero. An insert changes the bytes only near itself; once the window moves
past the insert, the boundaries are the same as before, so the later chunks hash to the same values.

The Low-Bandwidth Network File System (LBFS, 2001) did this with Rabin fingerprints over a 48-byte window, a boundary
when the low 13 bits equal a chosen value (so an expected chunk of about 8 KB for random data), a minimum chunk of 2 KB
and a maximum of 64 KB. The limits exist because the pathological cases are real: a boundary at every byte would make
the hash list as large as the file, and a long run with no boundary gives enormous chunks.

The lesson uses a simpler gear-style rolling hash (one shift, one table lookup and one add per byte; **not** the Rabin
fingerprint LBFS used), with the same three knobs: average size (`bits`), minimum and maximum. Dropbox's own
description says files are cut into 4 MB blocks; it does not say anything about content-defined chunking, so the code
below is a design alternative, not Dropbox's.

```python
import hashlib, random, collections

def sha(data):
    return hashlib.sha256(data).hexdigest()

def fixed_chunks(data, size):
    return [data[i:i + size] for i in range(0, len(data), size)]

_rng = random.Random(2026)
GEAR = [_rng.getrandbits(64) for _ in range(256)]
MASK64 = (1 << 64) - 1

def cdc_chunks(data, bits, lo, hi):
    """Cut where the top `bits` bits of the rolling hash are zero, never below lo bytes, always by hi bytes."""
    chunks, start, h, shift = [], 0, 0, 64 - bits
    for i, byte in enumerate(data):
        h = ((h << 1) + GEAR[byte]) & MASK64       # a byte's influence is shifted out after 64 steps
        size = i + 1 - start
        if (size >= lo and h >> shift == 0) or size >= hi:
            chunks.append(data[start:i + 1])
            start = i + 1
    if start < len(data):
        chunks.append(data[start:])
    return chunks
```

The check compares `cdc_chunks` with a version that recomputes the 64-byte window hash from scratch at every byte (so
rolling state cannot hide a bug), on 60 random inputs and parameter sets, and verifies the size limits and that the
chunks concatenate to the input. Then the experiment: 60 random 30,000-byte files, each with 7 bytes inserted near
the front. With 64-byte fixed blocks, more than 80% of blocks changed in every trial. With content-defined chunks
(about 80 bytes on average: the 16-byte minimum plus a mean of 64 beyond it; maximum 512) at most 8 chunks changed in any trial and under 4 on average. An
overwrite of the same length, on the other hand, changes exactly one fixed block, so fixed blocks are not wasteful when
edits are in place (typical for databases and virtual-disk images, less so for documents that are rewritten).

The trade-offs to say aloud: content-defined chunks cost CPU on every byte, produce variable sizes (more metadata,
harder to align to storage), and have a worse worst case unless you cap sizes. Fixed blocks are simpler and cheap, and
the 4 MB size keeps the blocklist short. The Dropbox streaming-sync post also notes that clients use compression and
rsync to shrink the individual store and retrieve requests, so delta can happen inside a block as well.

---

## 6. Deep Dive 2: The Journal, Cursors and Conflicts

**The upload.** The client chunks the file, hashes the blocks and calls `commit` with the blocklist. If the metadata
server does not know all the hashes it replies "need blocks" and names the missing ones; for a brand new file that is
all of them. The client uploads those (in requests of bounded size; the 2014 post's diagram uses 8 MB and says other
values were tried) and commits again, which now succeeds, appending a row to the journal. The file exists when the row
does. **Dedup is a side effect:** a file whose blocks all exist, such as a copy under a new name or a file another user
already uploaded, commits with nothing uploaded.

**The download.** An idle client holds a long-poll connection to a notification server. When told something changed it
calls `list` with its cursor for each namespace and gets only newer rows, then fetches the blocks it lacks (checking
its local files and its deleted-file cache first) and rebuilds the file.

```python
class Crash(Exception):
    pass

class BlockStore:
    def __init__(self):
        self.blocks, self.bytes_in = {}, 0

    def has(self, h):
        return h in self.blocks

    def put(self, data):
        self.bytes_in += len(data)                       # counts everything received, so re-uploads show up
        self.blocks[sha(data)] = data

class MetaServer:
    def __init__(self, store):
        self.store, self.journal = store, collections.defaultdict(list)   # ns -> [(jid, path, blocklist|None)]

    def head(self, ns, path):
        for jid, p, bl in reversed(self.journal[ns]):
            if p == path:
                return jid, bl
        return 0, None

    def commit(self, ns, path, blocklist, base):
        if blocklist is not None:                        # None means delete
            missing = [h for h in dict.fromkeys(blocklist) if not self.store.has(h)]
            if missing:
                return 'need_blocks', missing
        jid, _ = self.head(ns, path)
        if jid != base:
            return 'conflict', jid                       # the file changed since the edit's base version
        rows = self.journal[ns]
        rows.append((len(rows) + 1, path, None if blocklist is None else tuple(blocklist)))
        return 'ok', len(rows)

    def list(self, ns, cursor):
        return self.journal[ns][cursor:]

class Client:
    def __init__(self, name, meta, store, ns, chunker):
        self.name, self.meta, self.store, self.ns, self.chunker = name, meta, store, ns, chunker
        self.files, self.dirty, self.base, self.cursor = {}, set(), {}, 0

    def write(self, path, data):
        self.files[path] = data
        self.dirty.add(path)

    def remove(self, path):
        self.files.pop(path, None)
        self.dirty.add(path)

    def _blocklist(self, data):
        return None if data is None else [sha(c) for c in self.chunker(data)]

    def _conflict(self, path, lost_to):
        data = self.files.pop(path, None)
        self.dirty.discard(path)
        if data is not None:                             # keep our version under a new name; a lost delete is just dropped
            copy = '%s (conflicted copy %s, v%d)' % (path, self.name, lost_to)   # client and journal id keep names unique
            while copy in self.files:
                copy += ' again'
            self.files[copy] = data
            self.dirty.add(copy)

    def push(self, crash_after_blocks=None, crash_after_commit=False):
        for path in sorted(self.dirty):
            data = self.files.get(path)
            chunks = {} if data is None else {sha(c): c for c in self.chunker(data)}
            bl, sent = self._blocklist(data), 0
            while True:
                status, arg = self.meta.commit(self.ns, path, bl, self.base.get(path, 0))
                if status == 'need_blocks':
                    for h in arg:
                        if crash_after_blocks is not None and sent >= crash_after_blocks:
                            raise Crash()
                        self.store.put(chunks[h])
                        sent += 1
                elif status == 'conflict' and data is not None and self.meta.head(self.ns, path)[1] is None:
                    self.base[path] = arg                # deleted under our edit: the edit wins, commit it on top of the delete
                else:
                    break
            if status == 'ok':
                if crash_after_commit:
                    raise Crash()
                self.base[path] = arg
                self.dirty.discard(path)
                continue
            head_jid, head_bl = self.meta.head(self.ns, path)
            if head_bl == (None if bl is None else tuple(bl)):   # the same content is already the head (we crashed after commit)
                self.base[path] = head_jid
                self.dirty.discard(path)
            else:
                self._conflict(path, head_jid)

    def pull(self):
        for jid, path, bl in self.meta.list(self.ns, self.cursor):
            self.cursor = jid
            if jid <= self.base.get(path, 0):
                continue                                 # our own commit, already applied
            if path in self.dirty:
                if self._blocklist(self.files.get(path)) == (None if bl is None else list(bl)):
                    self.base[path] = jid
                    self.dirty.discard(path)
                    continue                             # both sides made the same change
                if bl is None and self.files.get(path) is not None:
                    self.base[path] = jid                # remote delete under our pending edit: the edit wins
                    continue
                self._conflict(path, jid)
            self.base[path] = jid
            if bl is None:
                self.files.pop(path, None)
            else:
                self.files[path] = b''.join(self.store.blocks[h] for h in bl)
```

**Conflicts.** Offline editing makes them certain, so the protocol must decide. Two rules. **Edit against edit:** an edit
is made on top of a base version, the server accepts a commit only if that base is still the file's head, and a refused
or surprised client keeps its version under a new name instead of overwriting anyone. The name carries the client and
the journal id it lost to (`f (conflicted copy B, v7)`). Without the client, two devices losing to the same version
choose the same name; without the id, one device's second conflict reuses its first copy's name. The `again` suffix in
the code is only a last resort, and the check asserts the exact names. **Edit against delete:** the edit wins in
every arrival order. If the delete was pushed first, the editor's commit is refused, sees that the head is a delete and
re-commits on top of it, so the file comes back at its original path; if the edit was pushed first, the deleter's commit
is refused and dropped. (A deliberate product choice: losing a delete costs a stray file, losing an edit costs work.)
Nothing is lost, and the versions are visible for a human to merge.

The check enumerates **all 24 orderings of the four actions** (A pushes, B pushes, A pulls, B pulls) for edit against
edit and, separately, for edit against delete; in every one both devices converge to the same tree, equal to a replay of
the journal, with the right contents present. It runs three clients editing one file in every push order (all three
edits must survive), and two rounds of the same conflict (the first copy must survive the second). It also checks an
edit on top of a pulled change (no conflict), pulling your own earlier commit while a newer edit is pending, a crash
after uploading 4 of 10 blocks (the retry sends only the other 6, total bytes received equal the file's size, no journal
row ever points at a missing block), and a crash after the commit but before the client noted it. For that last case
the immediate retry is a no-op. If someone else builds on the commit before the retry, **pull before you push**: a client
that pushes first gets a conflicted copy of its own, already committed version. That is clutter, not loss, and the check
asserts both outcomes. Finally 300 seeded random runs of three clients with edits, deletes, pushes, pulls and crashes
must end with every client equal to the journal replay, and a further quiet round must append nothing.

The seeded random runs are not decoration. Dropbox's Nucleus post says the engine's control thread is deterministic
for fixed inputs and scheduling, so a random seed generates a filesystem, a schedule and perturbations that can be
replayed exactly, and millions of such scenarios run daily. The same idea scales down: a conflict bug that depends on
interleaving is only fixable if the failing interleaving can be re-run.

**Streaming sync (latency).** Without it, a large file is uploaded in full and committed before any other device learns
of it, and only then downloaded. Dropbox's 2014 post describes letting the downloader prefetch blocks while the upload is
still going: the metadata server remembers the blocklist from the first, failed commit (in memcache, not the durable
journal, since losing it is harmless), the receiver's `list` returns those pending blocklists, and the receiver
prefetches into a cache that is purged if the commit never happens. They report up to a 2x improvement in
multi-client sync time for large new files, and about 25% in a test with about 1.2 up and 5 down ("mb/s" in the
post's own notation). A model gives the same shape: upload and download in sequence take 1/1.2 + 1/5 time units per
unit of data; overlapped, the faster side hides behind the slower, leaving 1/1.2; that is a saving of about 19%, near the
reported 25% and bounded by the slow link, which is why the gain approaches 2x only when both directions are equally fast.

---

## 7. Deep Dive 3: Identity, Moves and Cycles

Sync Engine Classic, in Dropbox's description, represented a move as a delete at the old path plus an add at the new, and
files lacked an identifier stable across moves. A transient failure that applies the delete but not the add makes the
file vanish for everyone though the user only moved it. The rewrite (Nucleus, shipped to all users in 2020) gives
files and folders globally unique ids, makes moves atomic regardless of subtree size, and keeps client and server views
checkable against each other, because a strong data model makes invalid states detectable.

The hard case the post uses: Alberto and Beatrice are offline; Alberto moves `Archives` into `January`, Beatrice moves
`Drafts` into `Archives`. Applying both would make `Archives` the parent of `Drafts`, `Drafts` the parent of `January`
and `January` the parent of `Archives`: a cycle. (The cycle the post names implies `January` started inside `Drafts`.)
Classic duplicated the directories; Nucleus keeps the originals and the final state depends on which engine uploads its
move first. A server that stores the tree as `child -> parent` can enforce this with one walk up the ancestors.

```python
class Tree:
    def __init__(self):
        self.parent, self.name, self._next = {0: None}, {0: ''}, 1   # node 0 is the root

    def add(self, parent, name):
        n, self._next = self._next, self._next + 1
        self.parent[n], self.name[n] = parent, name
        return n

    def path_of(self, n):
        parts = []
        while n != 0:
            parts.append(self.name[n])
            n = self.parent[n]
        return '/' + '/'.join(reversed(parts))

    def is_under(self, node, ancestor):              # is `node` inside `ancestor`, or the same node?
        while node is not None:
            if node == ancestor:
                return True
            node = self.parent[node]
        return False

    def move(self, node, new_parent):
        if node == 0 or self.is_under(new_parent, node):
            return False                             # would put a folder inside itself
        self.parent[node] = new_parent               # one pointer, however big the subtree
        return True
```

The check builds the post's three folders: the first move succeeds, the second is refused, and with the arrival order
swapped the other move is the one refused. Then 300 random trees with 40 random moves each are compared with a brute
force that applies the move to a copy and searches the whole graph for a cycle: the decisions match every time, the
tree stays acyclic, and each accepted move changes exactly one parent pointer, including a chain 1,000 folders deep.
The loser's client must then rebase: drop the refused move from its pending list and show the user the real tree.

---

## 8. Failure Modes

| What breaks | What you see | Defence |
|---|---|---|
| crash between block upload and commit | orphan blocks | harmless: nothing references them; a background job collects blocks no row uses (sy35) |
| crash after commit, before the client records it | client re-pushes | detect "head already has this blocklist" and treat as done |
| two devices edit offline | divergent versions | base-version check, conflicted copy named by client and journal id, never overwrite |
| delete versus edit | surprising loss | the edit wins in either arrival order (re-commit on top of the delete, or drop the delete) |
| cycle from concurrent moves | corrupt tree | reject the later move; client rebases |
| notification lost | device stale until it next polls | cursor-based `list` makes catch-up idempotent; also poll slowly as a backstop |
| local filesystem quirks | file differs between platforms | Dropbox's engineers describe separate behaviour on each OS and file system; test per platform and treat "durability everywhere" as hard |
| huge shared folder | every member is stale on every change | per-namespace cursors, send deltas, do not re-list the world |
| client claims hashes it does not hold | access to someone else's block | the 2014 post says the metaserver checks that the hashes are known and that the user has access; how possession is proven is not described there, so design it explicitly |

---

## 9. What Real Companies Did

- **Dropbox, file system and sync protocol** (Nipunn Koorapati, *Streaming File Synchronization*, 10 July 2014, read in
  full 2026-11-26): namespaces, 4 MB blocks hashed with SHA-256, the blocklist, the append-only server file journal with
  a per-namespace JID, block server versus metadata server, client cursors, `commit`, `store_batch`, `list`,
  `retrieve_batch`, long-poll to a notification server, and streaming sync with its reported gains.
- **Dropbox, sync engine rewrite** (Sujay Jayakar, *Rewriting the heart of our sync engine*, 9 March 2020, read in
  full): why Sync Engine Classic's data model stopped scaling, stable ids, strong consistency between client and
  server, atomic moves, single-threaded deterministic control thread in Rust, seeded simulation testing; reports
  hundreds of billions of files, trillions of revisions, exabytes of data, hundreds of millions of devices (their
  figures, as of 2020).
- **Dropbox, storage** (James Cowling, *Inside the Magic Pocket*, 6 May 2016, read in full): blocks up to 4 MB, keyed by
  SHA-256, immutable; a separate system (FileJournal) records file changes so storage can stay immutable; blocks are
  aggregated into 1 GB buckets, replicated at first and later erasure coded; each block stored in at least two zones;
  a block index implemented as a sharded MySQL cluster; open volumes take writes and closed volumes are immutable.
  This is the sy35 territory seen from Dropbox's side.
- **LBFS** (Muthitacharoen, Chen and Mazières, SOSP 2001, read in part, see Sources): content-defined chunking by Rabin fingerprint,
  and its window, mask and chunk limits as quoted above.
- Google Drive, OneDrive, Box and iCloud were not studied; no claim is made about how they sync.

---

## 10. Pitfalls Checklist

1. **Uploading whole files** because the change is "just one save".
2. **Committing metadata before the blocks exist,** so the journal can point at nothing.
3. **Fixed blocks only,** then wondering why inserting a line at the top of a file re-sends it all (or the reverse:
   expensive chunking for in-place workloads).
4. **No base version,** so the second writer silently overwrites the first.
5. **Treating a move as delete plus add.**
6. **Idempotence missing:** a retry after a crash creates a duplicate or a spurious conflict.
7. **Polling instead of long-poll or push,** or the reverse with no catch-up path when a notification is lost.
8. **Assuming a clean shutdown:** every step between "bytes sent" and "row committed" needs a defined crash outcome.
9. **Forgetting first-sync cost:** an hour to download 50 GB is a product problem, not a networking one.
10. **Quoting Dropbox's 2014 or 2020 numbers as a target** instead of using them as shapes.

---

## Drills

1. Why must the metadata server refuse a commit whose blocks are not all stored, and what is the cost of the opposite
   order?
2. Insert one byte at the start of a 100 MB file. How many 4 MB blocks change, and how many content-defined chunks of
   about 4 MB would you expect to change?
3. From the capacity table: how large is the blocklist of a 100 MB file, and why is the journal not the storage
   problem?
4. Two devices edit `report.docx` from the same base while offline. Walk through what the server answers to each push
   and what each device ends up with.
5. A device crashes after its commit succeeded but before it recorded the new JID. What does the retry see, and what
   must it do?
6. Show the move sequence that forms a cycle from three folders and two moves, and state which move the server refuses
   in each arrival order.
7. Why does streaming sync keep the pre-commit blocklist in memcache rather than the journal, and what must the
   receiver do if the commit never happens?
8. Compute the saving from overlapped upload and download when upload is 1 unit per second and download 10, and when
   both are equal.

---

## Homework

1. Replace the gear hash with a polynomial rolling hash (Rabin-Karp style) and rerun the 7-byte-insert experiment;
   compare the changed-chunk counts.
2. Add per-namespace cursors and shared folders: one namespace mounted into two users' trees; check that both see the
   same journal.
3. Add version history and restore: keep old rows, add a `restore(path, jid)` that commits an old blocklist as a new row.
4. Add a deleted-file cache on the client and make `pull` check it before asking the block store; count blocks saved.
5. Implement block garbage collection: blocks referenced by no journal row and older than a grace period; prove it
   never deletes a block of an in-flight upload.
6. Read the Nucleus post and Magic Pocket post again and list every invariant they say the system checks.

---

## Sources

All read 2026-11-26.

- Nipunn Koorapati, *Streaming File Synchronization*, Dropbox Tech Blog, 10 July 2014, dropbox.tech/infrastructure/streaming-file-synchronization (read in full).
- Sujay Jayakar, *Rewriting the heart of our sync engine*, Dropbox Tech Blog, 9 March 2020, dropbox.tech/infrastructure/rewriting-the-heart-of-our-sync-engine (read in full).
- James Cowling, *Inside the Magic Pocket*, Dropbox Tech Blog, 6 May 2016, dropbox.tech/infrastructure/inside-the-magic-pocket (read in full).
- Athicha Muthitacharoen, Benjie Chen, David Mazières, *A Low-bandwidth Network File System*, SOSP 2001, pdos.csail.mit.edu/papers/lbfs:sosp01/lbfs.pdf (abstract, introduction, the chunking sections and the evaluation of chunk sizes read; the protocol sections skimmed).

## Further reading (not consulted)

Tridgell and Mackerras, the rsync algorithm; later Dropbox posts on Nucleus internals; Google Drive and OneDrive engineering
material; papers on conflict-free replicated data types for file trees. None were read for this revision.

*Last reviewed: 26 November 2026.*
