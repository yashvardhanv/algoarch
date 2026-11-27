# Lesson 63 — Case Study: Email Service (Gmail)

> **Priority:** ★★★☆☆ (proposed; the curriculum data holds the final rating) — email is the classic "store and forward with no central owner" system, and an answer that treats it as a single database with an inbox table misses delivery, trust and sync.
>
> **Study time:** 85 minutes. **Do this after:** Scaling Patterns I: Reads, Writes and Contention; Scaling Patterns II: Large Blobs, Long-Running Tasks and Real-Time Updates; Distributed Search (for the search box); Overload, Load Shedding and Cascading Failures.
>
> **Level:** extended.

A mail system is three problems under one name. Moving a message between organisations that do not trust each other (SMTP: retries, duplicates, bounces). Deciding whether the sender is who it claims (SPF, DKIM, DMARC). And showing each user one consistent mailbox on a phone, a laptop and a web page (a per-user log with identifiers that never repeat). This lesson builds a small tested model of each, in `test/lesson_code/sy63_check.py`; capacity numbers come from `test/lesson_code/capacity_check_g.py`. **No engineering post or paper about Gmail's internals was read for this lesson**, so the design is the general approach, grounded in the protocol documents (RFCs) that were read and in one Google help page; see Sources. Search over mail is the inverted-index problem of Distributed Search and is not repeated.

---

## 1. Mental Model

> **Mail is a chain of custody, not a call. Each hop takes responsibility by saying "250" and then must deliver or bounce. The only thing a sender knows is whether it heard that 250, so the protocol is at-least-once and duplicates are the price of never losing mail. The mailbox the user sees is a different object: an append-only log per user whose ids are never reused.**

- **Accepting is a promise.** After the final dot the receiver "is accepting responsibility for delivering or relaying the message" (RFC 5321, 6.1). Do your spam and policy rejection before the dot, while saying no is free.
- **A lost reply is not a lost message.** The receiver kept it, the sender never heard, the sender retries: two copies. Dedupe is a heuristic you add, never a guarantee (section 5).
- **The mailbox is a log with tombstones.** New, changed and deleted messages are three kinds of event; sync is "give me what changed since my position", and it must be able to say "you are too far behind, start over" (section 6).
- **Identity is claimed in the message and proved in DNS.** The visible From domain is whatever the sender typed; SPF, DKIM and DMARC check that something the receiver can verify matches it (section 7).

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "design Gmail / an email service" | split into receive path (SMTP in, checks, store), send path (queue, retry, bounce), mailbox sync, search; say which you will deep dive |
| "what if the receiving server is down" | the sender queues and retries: at least 30 minutes between tries, give up after days, then a bounce (section 5) |
| "a user got the same message twice" | at-least-once delivery after a lost reply; dedupe on (recipient, Message-ID, content hash) in a window, and say what it misses |
| "phone and laptop must agree" | per-mailbox UIDs plus a change counter and tombstones; a "cannot calculate, resync" escape (section 6) |
| "stop spoofing and phishing" | SPF and DKIM verified, DMARC alignment against the visible From domain, then policy (section 7) |
| "attachments make it huge" | store the body once as a blob, per-user rows point at it; link, do not repeat (Scaling Patterns II) |
| "search my mail" | per-user index over the log; see Distributed Search |

---

## 3. Requirements and Capacity

**Functional.** Receive mail for the users' domains; send mail to any domain; show a mailbox (messages, flags or labels, threads); sync to several clients; search; bounce on failure; reject or quarantine forged and unwanted mail. **Out of scope:** calendar, contacts, the web UI, ML spam models (we show where their verdict plugs in, section 7).

**Non-functional.** Never lose accepted mail; an accepted message appears in the mailbox quickly; a user's mailbox is consistent across clients; the system survives a dead destination for days.

**Capacity estimate.** Every input below is *assumed* by this lesson, not any company's figure; every result is reproduced by `capacity_check_g.py`.

| Input | Value |
|---|---|
| active users | 100 million *(assumed)* |
| inbound delivery attempts per user per day | 200, of which 85% are refused before the message body is stored (spam, unknown user, failed checks) *(assumed)* |
| stored messages per user per day | 30 = 200 x 15% |
| average stored message | 75 KB *(assumed; mostly attachments)* |
| replication | 3 copies *(assumed)* |
| sent per user per day | 5 *(assumed)* |
| outbound deferred on the first try | 3%, mean residence in the retry queue 2 hours *(assumed)* |

| Result | Arithmetic | Value |
|---|---|---|
| stored messages | 100 M x 30 / 86,400 | 3 billion per day, 34,722 per second on average |
| connection attempts | 100 M x 200 / 86,400 | 231,481 per second, 196,759 of them refused |
| bytes stored | 3 billion x 75 KB | 225 TB per day, 675 TB per day replicated |
| one user's mailbox growth | 30 x 75 KB x 365 | 821 MB per year |
| outbound mail | 100 M x 5 / 86,400 | 5,787 per second |
| retry queue depth | 3% x 500 M x 2 h / 24 h | 1.25 million messages in flight |
| tries before giving up | the schedule of section 5, 5 days | 43 tries, the last one at or after the give-up time |

Four conclusions. **The edge is mostly saying no:** 196,759 of 231,481 attempts per second never reach storage, so every check must be cheap and must come before the data (the "refuse early" lesson of Overload, Load Shedding and Cascading Failures). **Storage is attachments:** 675 TB per day replicated is blob storage, not database rows; the metadata is a rounding error beside it. **Sizing the queue is a residence-time question:** 1.25 million messages in flight is small; the risk is not size but a destination that stays down for days while mail piles up (backoff and give-up bound it). **One mailbox is small:** 821 MB a year per user, so a mailbox is one shard's worth of work and never needs cross-shard transactions.

---

## 4. API and Data Model

```
SMTP in:   EHLO / MAIL FROM:<r> / RCPT TO:<u> / DATA ... "." -> 250 | 4yz (try later) | 5yz (never)
SMTP out:  lookup MX(domain) -> connect in preference order -> same dialogue as a client
mailbox:   append(flags) -> uid        set_flags(uid, flags)        expunge(uid)
sync:      changes_since(modseq) -> (changed {uid: flags}, vanished [uid]) | "too old, resync"
tables:    blob(hash -> bytes)   message(mailbox, uid, blob, flags, modseq)   tomb(mailbox, uid, modseq)
           mailbox(id, uidvalidity, next_uid, highest_modseq)    outq(msg, rcpt, first, next, tries, state)
```

MX records carry a preference that a sending server must use (RFC 5321, section 5). A mailbox row's `uidvalidity` changes only if UIDs cannot be preserved. The message body is stored once as a blob keyed by its hash and each recipient gets a small row: this is this lesson's design choice, not a described Gmail design. Labels versus folders is a presentation choice: a message with several labels is one row with a set, a folder is a set of size one; IMAP exposes mailboxes, so a label model must map to them, and how any product does that was not read.

---

## 5. Deep Dive 1: Delivery, Retries, Bounces and Duplicates

**What the standard asks.** (RFC 5321, 4.5.4.1.) After a failed attempt the sender must delay retrying; the interval "SHOULD be at least 30 minutes"; retries go on until the message is sent or the sender gives up, which "generally needs to be at least 4-5 days"; the parameters must be configurable. It also reports experience favouring "two connection attempts in the first hour" and then one every two or three hours. A 4yz reply means try later, a 5yz reply means never. If a message is accepted and then cannot be delivered, a notification must go back using a null reverse-path (`MAIL FROM:<>`), and a server must not send a notification to a null address, which stops bounce loops (RFC 5321 6.1, and the notification rules of RFC 3464 for the per-recipient report). The model below follows these; the doubling is this lesson's choice.

```python
import hashlib

def classify(code):
    return 'ok' if 200 <= code < 300 else 'defer' if 400 <= code < 500 else 'fail'

def retry_delay(attempt, base=1800, cap=10800):
    """Seconds to wait after the attempt-th failure: 30 minutes, doubling, capped at 3 hours."""
    return min(cap, base * 2 ** (attempt - 1))

class OutQueue:
    """Outbound queue, one record per (message, recipient): SMTP outcomes are per recipient, so are retries and bounces."""
    def __init__(self, give_up=5 * 86400):
        self.give_up, self.items, self.dsns = give_up, {}, []
    def submit(self, mid, rcpts, now, sender):
        for r in rcpts:
            self.items[(mid, r)] = {'sender': sender, 'first': now, 'next': now, 'tries': 0, 'state': 'queued'}
    def due(self, now):
        return sorted(k for k, v in self.items.items() if v['state'] == 'queued' and v['next'] <= now)
    def state(self, mid, r): return self.items[(mid, r)]['state']
    def attempts(self, mid, r): return self.items[(mid, r)]['tries']
    def next_due(self, mid, r): return self.items[(mid, r)]['next']
    def report(self, mid, r, code, now):
        it = self.items[(mid, r)]
        if it['state'] != 'queued':
            return                                       # a finished recipient never comes back
        it['tries'] += 1
        kind = classify(code)
        if kind == 'ok':
            it['state'] = 'delivered'
        elif kind == 'fail' or now - it['first'] >= self.give_up:
            it['state'] = 'bounced'
            if it['sender'] != '':                       # never bounce a bounce: the null sender gets no notification
                self.dsns.append({'mid': mid, 'rcpt': r, 'to': it['sender'], 'return_path': '',
                                  'reason': 'rejected' if kind == 'fail' else 'giveup'})
        else:
            it['next'] = now + retry_delay(it['tries'])
```

The check pins the edges: a try due at exactly 1,800 seconds and not at 1,799; the give-up one second before five days (still retried) and at five days (bounced); the give-up clock starts at submission, not at the first failure; a bounced recipient and a delivered one stay finished. With this schedule a recipient that always answers 4yz gets **43 tries including the final one** (the try at or after five days, whose failure triggers the bounce), the figure in the capacity table. A shorter retry cap multiplies that count and with it the load on a destination that is already down.

**The duplicate.** The window the standard cannot close: the receiver stores the message and sends 250, and the 250 is lost. The sender sees a timeout, treats it as a failure and retries; the receiver stores it again. RFC 5321 (6.1) says a receiver must "seek to minimize the time required to respond to the final dot" to avoid duplicates after timeouts, which reduces the window and does not remove it. Experiment, in the check: 1,000 messages, 10% of the final replies lost, sender retrying as above. A receiver with no memory ends with 1,000 messages plus **120 duplicate copies**; one with the window below stores exactly 1,000. (Illustrative: a seeded simulation.)

```python
class Inbox:
    """Receiver-side dedupe: the same (recipient, Message-ID, content hash) inside the window is a retry, not new mail."""
    def __init__(self, window=6 * 86400):
        self.window, self.seen, self.store = window, {}, []
    def accept(self, rcpt, message_id, body, now):
        key = (rcpt, message_id, hashlib.sha256(body.encode()).hexdigest())
        t = self.seen.get(key)
        if t is not None and now - t <= self.window:
            return 'duplicate'                           # retries do not refresh the clock: it runs from first sight
        self.seen[key] = now
        self.store.append(key)
        return 'stored'
```

The key choices are each a test: **Message-ID alone is not enough**, because RFC 5322 says a message "SHOULD" have one and that the identifier is meant to be unique, which a sloppy sender or a copy-and-edit does not honour, so the hash separates two different bodies that share an id; **the recipient is part of the key**, since one message to two recipients is two deliveries; **the window must be at least the sender's give-up time**, or a retry on day five lands outside it. The honest hole: a retry later than the window, and a sender that regenerates the Message-ID on each try, are stored twice. Duplicates are a user-visible annoyance, so the trade is correct: losing a message is worse.

**What 5yz and 4yz mean for the user.** A 5yz at the first hop is cheap and immediate (the sender's own server tells the user). A bounce after acceptance goes out as a new message to the return path, with one report per failed recipient, and the check asserts that a bounce for a bounce is never generated, on both paths: a permanent 5yz and a 4yz still failing at the five-day give-up. Accepting mail you will later bounce is the "backscatter" problem: the bounce goes to a forged sender who never wrote the message, which is another reason to refuse early (section 7).

---

## 6. Deep Dive 2: One Mailbox, Many Clients

IMAP (RFC 3501) gives each message a 32-bit **UID**, assigned in strictly ascending order within a mailbox, never renumbered within a session and, with the mailbox's **UIDVALIDITY** value, forming a 64-bit identifier that "MUST NOT refer to any other message in the mailbox or any subsequent mailbox with the same name forever". If a mailbox is deleted and recreated, the server must keep going from the old UIDs or assign a new UIDVALIDITY. UIDs are not contiguous. That is the identity half. The change half is the mod-sequence of IMAP CONDSTORE (RFC 7162): a counter that gives every message a value, increasing with each change, so a client can ask for everything changed since the value it last saw; the same RFC adds VANISHED for expunged UIDs. JMAP (RFC 8620) gives the same idea a state string per data type, a "changes" call, and an error `cannotCalculateChanges` when the server cannot compute the delta ("usually" because the state is too old); then the client must discard its cache. It says servers SHOULD be able to calculate changes from any state given to a client within the last 30 days. This lesson models the shared shape (the exact protocols differ).

```python
class Mailbox:
    def __init__(self, uidvalidity):
        self.uidvalidity, self.next_uid, self.highest_modseq = uidvalidity, 1, 0
        self.msgs = {}            # uid -> (flags, modseq of the last change)
        self.tombs = {}           # uid -> modseq of its expunge: the "vanished" log
        self.tomb_floor = 0       # deltas from before this are no longer computable
    def _bump(self):
        self.highest_modseq += 1
        return self.highest_modseq
    def append(self, flags=()):
        uid, self.next_uid = self.next_uid, self.next_uid + 1        # a counter, never max(uid)+1: expunging the top must not free its UID
        self.msgs[uid] = (frozenset(flags), self._bump())
        return uid
    def set_flags(self, uid, flags):
        if uid not in self.msgs:
            return False                                             # a STORE racing an EXPUNGE must not resurrect the message
        self.msgs[uid] = (frozenset(flags), self._bump())
        return True
    def expunge(self, uid):
        del self.msgs[uid]
        self.tombs[uid] = self._bump()
    def compact(self):
        self.tombs.clear()
        self.tomb_floor = self.highest_modseq
    def snapshot(self):
        return {u: f for u, (f, _) in self.msgs.items()}
    def changes_since(self, modseq):
        if modseq < self.tomb_floor:
            return None                                              # too old: the caller must resync from scratch
        changed = {u: f for u, (f, m) in self.msgs.items() if m > modseq}
        return changed, sorted(u for u, m in self.tombs.items() if m > modseq)

class Replica:
    """What a client keeps: a cache of the mailbox and the position it has synced to."""
    def __init__(self):
        self.uidvalidity, self.modseq, self.msgs = None, 0, {}
    def sync(self, mb):
        if mb.uidvalidity != self.uidvalidity:                       # same UIDs may now be different mail: throw the cache away
            self.uidvalidity, self.modseq, self.msgs = mb.uidvalidity, 0, {}
        delta = mb.changes_since(self.modseq)
        if delta is None:
            self.msgs = mb.snapshot()
        else:
            changed, gone = delta
            for u in gone:
                self.msgs.pop(u, None)
            self.msgs.update(changed)
        self.modseq = mb.highest_modseq
```

What the check does to it: 400 seeded random runs of appends, flag changes, expunges, compactions, new mailboxes with a higher UIDVALIDITY and three replicas syncing at random moments must always equal the mailbox's own snapshot; UIDs are never reused over 500 operations that expunge the highest message (the `max(uid) + 1` bug appears the moment the newest message is deleted and a new one arrives: a client holding the old UID now sees different mail under it); a client at exactly the compaction floor gets a delta and one just below it gets `None` and then a full resync that includes the expunge the tombstone no longer remembers; and a mailbox re-created with UIDVALIDITY 11 replaces the cache of UIDVALIDITY 10 rather than merging into it. UIDs and mod-sequences above 100 are used so a string-ordered comparison ("9" above "10") fails.

**Costs and limits.** A tombstone per expunged message costs a row until compaction, which is why compaction exists and why "resync from scratch" must be a supported, rare path: with the 821 MB a year of section 3 and a full-state listing of every UID and its flags, a resync is a few hundred kilobytes of metadata, not the bodies. `set_flags` on an unknown UID does nothing and the check asserts it, so a flag change racing an expunge cannot resurrect the message. The model is single-writer: read `highest_modseq` and compute the delta under the same snapshot, or a change landing in between is lost to the next sync. Sorting and threading are client or index work above the log.

---

## 7. Deep Dive 3: Is the Sender Who It Says? (SPF, DKIM, DMARC)

The visible From domain (RFC 5322) is just text. **SPF** (RFC 7208) checks the connecting IP against DNS records for the envelope sender (the "MAIL FROM" identity; a check of the HELO name comes first if there is one). **DKIM** (RFC 6376) verifies a cryptographic signature whose `d=` tag names the signing domain. Neither says anything about the visible From, so a forger signs with its own domain and passes. **DMARC** (RFC 7489) adds **identifier alignment**: a pass counts only if the authenticated domain matches the From domain. In relaxed mode the organizational domains must be equal; in strict mode, only an exact match. The RFC's own example: a signature with `d=example.com` aligns, in relaxed mode, with `alerts@news.example.com`, and fails in strict mode; `d=com` never aligns because `com` is a public suffix and cannot be an organizational domain. Then the domain owner's published policy (none, quarantine, reject, with a percentage) tells the receiver what to do with a failure.

```python
def org_domain(d, suffixes):
    """One label below the longest public suffix; a name that IS a public suffix has no organizational domain."""
    labels = d.lower().split('.')
    best = 1                                         # an unlisted TLD still counts as a one-label suffix
    for k in range(1, len(labels) + 1):
        if '.'.join(labels[-k:]) in suffixes:
            best = max(best, k)
    return '.'.join(labels[-(best + 1):]) if len(labels) > best else None

def aligned(auth, frm, mode, suffixes):
    if mode == 's':
        return auth.lower() == frm.lower()
    a = org_domain(auth, suffixes)
    return a is not None and a == org_domain(frm, suffixes)

def dmarc_result(frm, spf, dkims, spf_mode, dkim_mode, suffixes):
    """spf = (result, domain); dkims = [(result, d= domain)]. One aligned pass of either kind is enough."""
    if spf[0] == 'pass' and aligned(spf[1], frm, spf_mode, suffixes):
        return 'pass'
    return 'pass' if any(r == 'pass' and aligned(d, frm, dkim_mode, suffixes) for r, d in dkims) else 'fail'
```

The check compares `aligned` against an independently written walk down the ancestors, over every pair of 15 names (including `evil-example.com` against `example.com`, `me.github.io` against `you.github.io` and `co.uk` itself), and 3,000 random message verdicts against a second implementation. The plausible bugs it catches: matching with `endswith` and no dot boundary, which makes `evil-example.com` align with `example.com`; treating `com` or `co.uk` as an organizational domain, which lets any `.co.uk` sender align with any other; counting a *failed* check because the domain aligns; and counting an *unaligned* pass, the forger who signs with a domain it owns. The public-suffix set is a real, large list the receiver must keep current; the model's four-entry set is only for testing.

**What it cannot do.** It proves a domain, not a person, and a lookalike domain passes with its own valid records. Mail that is forwarded or passes through a list can break the checks, since the forwarder's IP is not in the original domain's SPF record and a list that edits the message breaks the signature (RFC 7489 discusses forwarding as a source of such failures; the later mitigation was not read). So a receiver treats DMARC failure plus a policy of `reject` as strong, and everything else as one input to a spam score.

**Google's published sender rules (read).** The Gmail sender guidelines page (read 27 November 2026, through a summarising fetch, so partly) asks all senders to authenticate with SPF or DKIM, have valid forward and reverse DNS, use TLS, and keep the spam rate reported in Postmaster Tools below 0.3% (it recommends below 0.10%); bulk senders (more than 5,000 messages per day) must set up SPF, DKIM and DMARC and support one-click unsubscribe for marketing mail. It says nothing here about Gmail's internal architecture. For design: the **receiving side's reputation signals feed back to senders as rules**, so an outbound sender that wants delivery runs the same checks on its own mail.

**Where the spam verdict plugs in.** The refusal at the edge (section 3's 85%) is the cheap layers: connection reputation, recipient exists, authentication, then a score from content and history. A quarantined message is stored in a spam folder as an ordinary append to the mailbox log; a refused message gets a 5yz during the dialogue, so the sender's own server issues the bounce, not you.

---

## 8. Failure Modes

| Failure | What happens | Defence |
|---|---|---|
| destination down for days | queue grows; each message retried with backoff | cap at 3 hours, give up at 5 days, bounce (43 tries) |
| lost 250 after the final dot | sender retries; the receiver holds the message twice | dedupe window at least the give-up time (120 duplicates without it in the simulation) |
| message accepted then undeliverable | a bounce to the return path, possibly forged | refuse before the dot; never bounce the null sender |
| expunged top UID reused | a client's cached UID names different mail | `next_uid` is a counter, not max plus one |
| client offline past tombstone compaction | cannot compute the delta | return "resync" and resend the state; do not guess |
| mailbox deleted and recreated | same UIDs, different mail | new UIDVALIDITY; client drops its cache |
| forged From | recipient trusts the visible name | DMARC alignment and policy |
| spammer on your own users' accounts | your outbound IPs get a bad reputation | outbound rate limits, the same checks on outbound mail |
| hot user (a mailing list address) | one mailbox shard takes all writes | the blob is stored once, per-user rows are small; fan out in batches |

---

## 9. What Real Systems Did

Only what was read. The protocol documents above (RFCs 5321, 5322, 3464, 3501, 7162, 8620, 6376, 7208 and 7489) describe the mechanisms; the Google page describes sender expectations. **Not read, so nothing is claimed:** Gmail's storage system, its spam filter, how labels are stored, its indexing, any Google paper on mail. The same holds for other providers. The shape in this lesson (blob store plus per-user log plus index) is the general design that the protocols force, not a description of a specific product.

---

## 10. Pitfalls

1. Treating send as a function call: no outbound queue, no retries, no per-recipient state.
2. Retrying a 5yz, or giving up on a 4yz in minutes (the standard wants days).
3. Accepting first and filtering later, which creates the bounce you then send to a forged address.
4. Bouncing a bounce (a null return path must get no notification).
5. Deduping on Message-ID alone, or with a window shorter than the retry period.
6. `max(uid) + 1` for the next UID.
7. Syncing by timestamp. Clocks differ and two changes share a second; a counter does not.
8. No resync path when the tombstones are gone.
9. Ignoring UIDVALIDITY, so a recreated mailbox merges into a stale cache.
10. Aligning domains with `endswith` or treating a public suffix as a registrable domain.
11. Storing the attachment per recipient instead of once.
12. Claiming a specific Gmail internal ("it uses X") with no source.

---

## Drills

1. A destination answers 451 to every try. Using the lesson's schedule, when are the third and fourth tries (seconds after submission), and why is a 5-day give-up consistent with the standard?
2. The receiver stored a message and the sender never heard 250. What does the sender do, what does the user see, and what are two ways the receiver can avoid the duplicate?
3. Why must the dedupe key contain the content hash and the recipient, and what makes the window hole unavoidable?
4. A message is accepted for `a@x` and `b@y`; `b@y` is permanently unreachable a day later. What is sent, to where, with which return path, and what if the original sender was `<>`?
5. You expunge UID 40, the highest, then append a message. A client cached UID 40. What breaks if the new UID is 40, and what should it be?
6. A phone last synced at mod-sequence 500; the server compacted tombstones at 600. What does `changes_since(500)` return and what does the phone do? What about a client at 600?
7. `d=example.com` signs a message with From `alerts@news.example.com`; policy says reject on failure. Relaxed mode: pass or fail? Strict? What if `d=mailer.net` signs it and SPF passes for `bounce.mailer.net`?
8. At 231,481 connection attempts per second with 85% refused, which checks go before the DATA command and why does a 5yz there cost the receiver almost nothing?

---

## Homework

1. Run `test/lesson_code/sy63_check.py` and change the retry cap from 3 hours to 12 hours: which assertions fail and what is the new number of tries?
2. Add a `Mailbox.move(uid, other)` that expunges here and appends there. What does a client see on each side, and which UIDs are used?
3. Extend `Inbox` with a time-ordered expiry so `seen` does not grow forever, and test that the window edge is unchanged.
4. Implement CONDSTORE's rule "any two STORE operations get increasing mod-sequences" under two concurrent writers using a lock, and write the interleaving test that fails without it.
5. Read RFC 5321 section 4.5.4 and RFC 7489 section 6.6 and write two paragraphs on what a receiver should do with a message that fails DMARC with policy `quarantine` and `pct=50`.
6. Practice: design a scheduled-send feature on top of the queue; say which table changes and how a cancel interacts with a retry in flight.

---

## Sources

All accessed 27 November 2026. RFCs fetched as text and searched with grep; passages quoted or paraphrased above were read in context, the documents were not read end to end.

- RFC 5321 (SMTP): retry and give-up guidance (4.5.4.1), responsibility on 250 (6.1), null reverse-path for notifications, MX preference, the time-to-reply remark. RFC 5322 (message format): the Message-ID field. RFC 3464 (delivery status notifications): per-recipient fields (headings and first sections).
- RFC 3501 (IMAP4rev1): UID and UIDVALIDITY (2.3.1.1). RFC 7162 (CONDSTORE and QRESYNC): mod-sequence and VANISHED (introduction and 3.2 headings). RFC 8620 (JMAP core): state strings, `cannotCalculateChanges`, the 30-day remark.
- RFC 7208 (SPF): the MAIL FROM and HELO identities, the mailing-list remark. RFC 6376 (DKIM): the `d=` tag. RFC 7489 (DMARC): identifier alignment (3.1), policy values, forwarding as a failure source.
- Google, "Email sender guidelines" (support.google.com/a/answer/81126): read through a summarising fetch, so exact wording was not checked line by line; the figures 5,000, 0.3% and 0.10% are as reported by it.

**Not consulted:** any Gmail engineering post or paper; Cyrus, Dovecot or Exim documentation; RFC 8617 (ARC); how real providers size or shard storage. The capacity inputs are this lesson's assumptions. Simulation figures (120 duplicates) are illustrative: a seeded Python run on 3.13. The model, the dedupe key and the retry doubling are this lesson's, not any provider's.

*Last reviewed: 27 November 2026.*
