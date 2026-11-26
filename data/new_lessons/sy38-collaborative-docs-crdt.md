# Lesson 38 — Real-Time Collaborative Whiteboard & Docs (Google Docs / Figma)

> **Priority:** ★★★★★ — "design Google Docs" is a standard prompt, and the follow-ups go straight to concurrent edits.
>
> **Study time:** 60 minutes. **Do this after:** the Real-Time Chat case study (WebSockets and fan-out) and CAP Theorem to PACELC.
>
> **Level:** extended. Worth doing if your loops include product infrastructure or editor-style products.

Two people edit the same paragraph at the same moment, each sees their own keystroke instantly, and a
second later both screens must show the same text with neither edit lost. That is the whole problem.
The rest of the design (WebSocket fan-out, persistence, presence) is ordinary; this lesson spends its time
on the part interviewers probe: **how concurrent edits converge**, with the two real answers worked in code
(operational transformation and a sequence CRDT), and what Google Docs and Figma said they actually do.

---

## 1. Mental Model

> **An edit is not a new document; it is an operation on the document the author saw. When operations
> cross in flight, either rewrite them against each other (operational transformation) or give every
> character an identity so operations never needed positions in the first place (CRDTs).**

What follows from it:

- **Positions are the enemy.** "Insert at index 3" means something different once someone else inserted at
  index 1. OT fixes the index; a sequence CRDT replaces it with "insert after character `x`".
- **Apply locally first, reconcile later.** Typing latency must not include a round trip, so every design
  applies the user's own edit immediately and treats remote edits as the thing to reconcile.
- **A central server simplifies everything.** If the server puts all operations in one order, each client
  only reconciles against that order. Figma's server defines the order of property changes; Google's 2010
  description of Docs routes every change from an editor through the server to the other editors.
- **Presence is not content.** Cursors and selections change more often than text (the capacity table assumes
  ten times as often) and need no history; keep them on a separate, lossy path.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "rich text, many editors, a server we control" | OT against a server-ordered log, or a sequence CRDT relayed by the server |
| "offline editing for hours, peer-to-peer, or no trusted server" | a CRDT (for text: a sequence CRDT such as RGA, or a library like Yjs or Automerge) |
| "shapes on a canvas, properties like colour and position" | per-property last-writer-wins with server ordering (Figma's approach) |
| "ordering of layers or list items" | fractional indexing, with re-spacing when precision runs out |
| "show other people's cursors" | a separate ephemeral presence channel, throttled, never persisted |
| "the document keeps growing" | tombstone compaction and snapshots plus an operation log |

---

## 3. Requirements and Capacity

**Functional.** Create, open and edit documents; concurrent editing with every edit preserved; see
collaborators' cursors; offline edits merge on reconnect; version history and undo.

**Non-functional.** Local keystroke feels instant (no network wait); all editors converge to the same
text; an acknowledged edit is never lost.

**Capacity estimate.** Inputs are **assumptions** for the exercise; results are reproduced by
`test/lesson_code/capacity_check.py`.

| Input (assumed) | Value |
|---|---|
| documents open at peak | 1 million |
| active editors per open document | 2 on average |
| edit operations per active editor | 1 per second |
| wire size per operation | 50 bytes |
| presence updates per active editor (unthrottled / throttled) | 10 per second / 2 per second |
| CRDT metadata per character (id 16 B + anchor 16 B + char 4 B) | 36 bytes |

| Result | Arithmetic | Value |
|---|---|---|
| active editors | 1M x 2 | 2 million WebSocket connections |
| edit operations in | 2M x 1 | 2 million per second |
| edit operations out (each to 1 other editor on average) | 2M x (2 - 1) | 2 million per second |
| edit ingress bandwidth | 2M x 50 B | 100 MB/s |
| presence messages out, unthrottled vs throttled | 2M x 10 x 1; 2M x 2 x 1 | 20 million vs 4 million per second |
| one document: 150,000 characters ever typed, 50,000 deleted | 150,000 x 36 B | 5.4 MB of metadata for 100,000 visible characters (54 bytes per visible character) |

Two lessons from the table: **presence, not text, dominates message volume**, so throttle it and keep it
off the durable path; and **a naive sequence CRDT stores far more than the text**, which is why real
libraries compress runs of characters and compact tombstones.

Visual (planned): clients connected over WebSockets to a per-document session server, which appends to an operation log and periodically writes a snapshot.

---

## 4. API and Data Model

```
WS  /docs/{id}/session            client -> server: {op, base_version}; server -> clients: {op, version}
GET /docs/{id}?at=version         snapshot + ops since the snapshot
WS  /docs/{id}/presence           {user, cursor, selection}, ephemeral, last value wins
```

- **Operation log** (durable, append-only, per document): `(doc_id, version, op, author, time)`.
- **Snapshots**: the materialised document every N operations, so opening a document replays only the tail.
- **Session server**: all editors of one document connect to the same server, which orders operations. Figma
  describes spinning up a separate process per multiplayer document that everyone editing it connects to.
  Route sessions by document id; the routing layer must send every editor of a document to the same place.

---

## 5. Deep Dive 1: Operational Transformation, Worked

Start from `CAT`. Ana inserts `H` at index 1 (`CHAT`); concurrently Ben inserts `S` at index 3 (`CATS`).
If each applies the other's operation as sent, Ana gets `CHAST` and Ben gets `CHATS`: they diverge. OT
transforms the incoming operation against the concurrent local one first: Ben's insert at 3 comes after
Ana's insert at 1, so on Ana's side it shifts to index 4, and both get `CHATS`.

```python
def apply(doc, op):
    """op: ('ins', pos, char, site) or ('del', pos, site)."""
    if op is None:
        return doc
    if op[0] == 'ins':
        return doc[:op[1]] + op[2] + doc[op[1]:]
    return doc[:op[1]] + doc[op[1] + 1:]

def transform(a, b):
    """Rewrite a so that it can be applied after b, where a and b were made concurrently on the same text.
    Equal-position inserts are ordered by site id. Returns None if a has nothing left to do."""
    if a is None or b is None:
        return a
    if b[0] == 'ins':
        if a[0] == 'ins':
            if a[1] < b[1] or (a[1] == b[1] and a[3] < b[3]):
                return a
            return ('ins', a[1] + 1, a[2], a[3])
        return a if a[1] < b[1] else ('del', a[1] + 1, a[2])
    if a[0] == 'ins':
        return a if a[1] <= b[1] else ('ins', a[1] - 1, a[2], a[3])
    if a[1] == b[1]:
        return None                       # both deleted the same character
    return a if a[1] < b[1] else ('del', a[1] - 1, a[2])
```

The property that makes two sites converge is: applying `a` then `transform(b, a)` gives the same text
as applying `b` then `transform(a, b)`. The check tests it on thousands of random pairs and, separately,
compares the result with an identity-based model (each character tracked by identity, so "what the authors
meant" is computed without positions).

This pairwise property is enough when there is **one server that orders operations**: each client only
transforms its pending operations against the server's sequence. Google's 2010 description of Docs is
consistent with this shape (the protocol details were promised for a later post, which was not read): every edit is one of insert text, delete text or apply style; the document is stored as a revision
log replayed to display it; edits go from an editor to the server and then to the other editors, and each
editor transforms incoming changes against its local version. Their examples include transforming a style
range against an insert (the range grows) and noting that two different style changes do not conflict.

**Why OT is considered hard:** every pair of operation types needs its own transform, each with tie cases;
Figma's write-up says they avoided OT because it was more complex than their problem needed.

---

## 6. Deep Dive 2: A Sequence CRDT (RGA), Worked

A CRDT gives each character a permanent identity, so no operation ever needs rewriting. In RGA, each
insertion gets a unique timestamp id `(counter, replica)` and names the character it was typed after (its
**anchor**). The document is a tree of anchors, read in depth-first pre-order with siblings in descending
id order; deletes keep the character as a **tombstone** because later inserts may still anchor to it.

```python
HEAD = (0, '')

class RGA:
    """Replicated Growable Array, operation-based. Ops: ('ins', id, anchor_id, char) and ('del', id)."""
    def __init__(self, replica):
        self.replica, self.clock = replica, 0
        self.children = {HEAD: []}      # anchor id -> ids inserted right after it, in descending id order
        self.char, self.deleted, self.pending = {}, set(), []

    def _order(self):
        """All ids in document order (tombstones included): pre-order, larger ids first among siblings."""
        out, stack = [], list(reversed(self.children[HEAD]))
        while stack:
            node = stack.pop()
            out.append(node)
            stack.extend(reversed(self.children[node]))
        return out

    def _visible(self):
        return [i for i in self._order() if i not in self.deleted]

    def text(self):
        return ''.join(self.char[i] for i in self._visible())

    def insert(self, index, ch):
        """Local insert before visible position `index`; returns the op to broadcast."""
        anchor = HEAD if index == 0 else self._visible()[index - 1]
        self.clock += 1
        op = ('ins', (self.clock, self.replica), anchor, ch)
        self._apply(op)
        return op

    def delete(self, index):
        op = ('del', self._visible()[index])
        self._apply(op)
        return op

    def receive(self, op):
        """Remote op, in any order: ops whose anchor or target has not arrived wait in `pending`."""
        self.pending.append(op)
        progress = True
        while progress:
            progress = False
            for o in list(self.pending):
                if (o[2] in self.children) if o[0] == 'ins' else (o[1] in self.char):
                    self.pending.remove(o)
                    self._apply(o)
                    progress = True

    def _apply(self, op):
        if op[0] == 'del':
            self.deleted.add(op[1])
            return
        _, oid, anchor, ch = op
        if oid in self.char:
            return                                    # duplicate delivery
        self.clock = max(self.clock, oid[0])          # Lamport rule: later local ids beat everything seen
        self.char[oid], self.children[oid] = ch, []
        sib, i = self.children[anchor], 0
        while i < len(sib) and sib[i] > oid:
            i += 1
        sib.insert(i, oid)
```

Why it is correct, in three sentences you can say aloud:

1. **Convergence:** the final tree depends only on the set of operations (each node's anchor and id are fixed),
   and sibling order is a fixed rule on ids, so any delivery order gives the same text.
2. **Intention for local edits:** a new local id has a counter above everything the replica has seen
   (the `max` line), so it sorts first among its anchor's existing children and lands exactly where the user typed.
3. **Causality:** an insert is applied only after its anchor exists, a delete only after its target exists.

The check runs three replicas through random local edits, random partial syncs and random delivery orders,
and confirms: every local edit changes the local text exactly like a plain list edit; all replicas converge;
and duplicates and out-of-order delivery are harmless.

**Interleaving, the follow-up question.** Kleppmann et al. (2019) show that Logoot and LSEQ, which give each
character a position from a dense ordered set, can interleave two people's concurrent insertions character by
character. RGA does not, for text typed in order: if one user types ` Alice` and another ` Charlie` at the same
spot in `Hello!`, the only results are `Hello Alice Charlie!` or `Hello Charlie Alice!`. The check confirms
this case. The same paper describes a lesser anomaly in RGA when a user moves the cursor back and inserts
again during the concurrent session.

**Cost.** Every character carries an id and an anchor, and deleted characters stay. The capacity table above
puts a naive version at 54 bytes per visible character for a document with a third of its characters deleted.
Yjs's README describes three mitigations: merging runs of sequentially typed characters into one struct,
dropping the content of deleted structs, and garbage-collecting tombstones when their order no longer matters
(for example when the parent was deleted). It also says tombstones cannot in general be collected while a
unique order must be kept.

---

## 7. Deep Dive 3: Figma's Server-Ordered Properties

Figma's 2019 write-up is a useful contrast because it is not a text editor. Its document is a tree of objects,
modelled as `Map<ObjectID, Map<Property, Value>>`, and:

- **Properties are last-writer-wins, ordered by the server.** Two clients changing different properties never
  conflict; the same property on the same object ends with the last value the server received. No timestamps
  are needed because the server defines the order. Simultaneous edits to one text value therefore keep one
  value, never a merge, which they accept for a design tool.
- **No flicker:** a client discards incoming server values that conflict with its own unacknowledged change,
  because its own change is the best prediction of the final value.
- **Unique ids without the server:** each client has a unique client id embedded in the object ids it creates,
  so creation works offline.
- **Tree moves:** the parent link is a property of the child; the server rejects a reparent that would form a
  cycle.
- **Order among siblings:** fractional indexing, a position between 0 and 1, with inserts taking the average of
  their neighbours. The parent link and position are one property so they change atomically.
- **Undo:** an undo changes redo history at the time of the undo, so undoing, copying and redoing leaves the
  document unchanged.
- **Reconnect:** after offline editing, the client downloads a fresh copy and reapplies its offline edits on top.

Fractional indexing has a precision limit worth computing:

```python
def midpoint(lo, hi):
    """A position strictly between lo and hi, or an error when floating point has run out."""
    m = (lo + hi) / 2
    if not lo < m < hi:
        raise ValueError('no float left between these positions; re-space the list')
    return m
```

Starting between 0.5 and 1 and inserting repeatedly at the same spot (always right after 0.5), the gap halves
each time; after 52 inserts there is no double left between the neighbours (the check counts this). Real
implementations use arbitrary-precision strings or re-space positions; say which in the interview.

---

## 8. Failure Modes

| Failure | Effect | Mitigation |
|---|---|---|
| session server crashes | in-flight ops not yet in the durable log are lost from the server's view | clients keep unacknowledged ops and resend on reconnect; ops carry unique ids so resends are idempotent |
| client offline for hours | large divergence to reconcile | CRDT merge, or Figma's approach: fetch fresh state, replay local edits |
| two clients reparent A under B and B under A | a cycle | server rejects the second; client temporarily hides the cycle until the server answers |
| document grows without bound | slow open, memory pressure | snapshots, tombstone compaction where safe, run-length merging of ids |
| hot document (thousands of viewers) | one session server saturated | separate read-only viewers from editors; fan out viewers through a broadcast tier |
| presence flood | message volume many times the edit volume | throttle, drop stale cursor updates, never persist |

---

## 9. Pitfalls Checklist

1. **Sending the whole document per keystroke**, or locking the document while one person types.
2. **Claiming OT needs no server.** Pairwise transforms are enough only against one agreed order; say where it comes from.
3. **Saying "Figma uses CRDTs" without the qualifier.** Figma's post says it is inspired by CRDTs but is not using true CRDTs, because its server is the authority.
4. **Forgetting tombstones.** A deleted character may still be an anchor; deleting it outright breaks later inserts.
5. **Ignoring the Lamport rule.** Without raising the local clock past remote ids, a new local insert can land in the wrong place.
6. **Assuming convergence means readable.** Interleaving anomalies converge to garbage; know which algorithms avoid them.
7. **Putting presence on the durable path.**
8. **Floating-point fractional indexes without a re-spacing plan.**

---

## Drills

1. In the `CAT` example, what does `transform` return for Ben's op on Ana's side, and why?
2. Two users insert at the same index at the same time. What decides the order in `transform`, and why must both sides use the same rule?
3. Why does `transform` return `None` for two deletes of the same character?
4. In `RGA`, why is a new local insert guaranteed to appear right after its anchor?
5. Why must `receive` hold an op whose anchor has not arrived, rather than inserting it at the end?
6. Give the two possible merge results for ` Alice` and ` Charlie` typed at the same spot, and explain why RGA rules out a jumble.
7. Using the capacity table, why should presence be throttled before edit traffic?
8. After how many same-spot inserts does a float fractional index fail between 0.5 and 1, and what do you do then?

---

## Homework

1. Add `('style', start, end, attr)` to `transform` so a style range grows over an insert inside it, as in Google's example; extend the check.
2. Add a `compact()` to `RGA` that removes tombstones with no children and no pending references; prove in the check that text is unchanged.
3. Write a state-based PN-Counter (two G-Counters merged by element-wise max) for a "likes" counter and test merge order independence.
4. Design the persistence: operation log plus snapshots. How often do you snapshot, and what does opening a document cost?
5. Read the Kleppmann et al. interleaving paper's Section 3 and reproduce the lesser anomaly with `RGA`.

---

## Sources

All read 2026-11-26.

- John Day-Richter (Google), *What's different about the new Google Docs: Conflict resolution*, Google Drive Blog,
  22 September 2010, drive.googleblog.com/2010/09/whats-different-about-new-google-docs_22.html. Source for the three
  change types, the revision log, the transform examples, and the editor-to-server-to-editors flow.
- Evan Wallace, *How Figma's multiplayer technology works*, Figma Blog, 16 October 2019,
  figma.com/blog/how-figmas-multiplayer-technology-works/. Source for every Figma statement in Section 7, the
  process per document, and Figma's view of OT.
- Kleppmann, Gomes, Mulligan and Beresford, *Interleaving anomalies in collaborative text editors*, PaPoC 2019,
  martin.kleppmann.com/papers/interleaving-papoc19.pdf. Source for RGA's anchor tree, pre-order traversal with
  descending siblings, tombstones, and the Logoot/LSEQ and RGA anomalies.
- Yjs README, github.com/yjs/yjs (the introduction and "Yjs CRDT Algorithm" section). Source for the tombstone and
  struct-merging mitigations.
- Wikipedia, *Conflict-free replicated data type*, en.wikipedia.org/wiki/Conflict-free_replicated_data_type (body
  read). Background for state-based versus operation-based CRDTs and the PN-Counter in the homework.

## Further reading (not consulted)

Shapiro, Preguiça, Baquero and Zawirski, *A comprehensive study of Convergent and Commutative Replicated Data Types*
(INRIA, 2011; the archive page asked for a bot check, so it was not read); Ellis and Gibbs, *Concurrency control in
groupware systems* (1989); the third post in Google's 2010 series (the page did not load); Roh et al., the original
RGA paper; the Automerge documentation.

*Last reviewed: 2026-11-26.*
