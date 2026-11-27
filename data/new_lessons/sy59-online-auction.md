# Lesson 59 — Case Study: Online Auction (eBay)

> **Priority:** ★★★☆☆ (proposed; the curriculum data holds the final rating) — an auction looks like "store the highest bid", and the interview is in what that hides: bids are maximums, the last seconds are one hot row, and the end is a clock rule.
>
> **Study time:** 75 minutes. **Do this after:** Flash Sale & Ticket Reservation (Ticketmaster); Time, Clocks and Ordering; Scaling Patterns II: Large Blobs, Long-Running Tasks and Real-Time Updates.
>
> **Level:** extended.

An auction is a serial log of bids for one item, resolved by a pure function, closed by a clock. This lesson builds proxy bidding (the price you see is derived from maximums, not from the last bid), a per-item writer whose ledger can be replayed to prove no bid was lost, and the closing rules (hard close, soft close, settlement), as code checked in `test/lesson_code/sy59_check.py` against a ledger model, replay after a thread race and a simulation of late bids; capacity numbers come from `capacity_check_e.py`. Conditional writes are taught in Flash Sale & Ticket Reservation (Ticketmaster), clocks in Time, Clocks and Ordering and push fan-out in Scaling Patterns II, and are linked, not repeated.

---

## 1. Mental Model

> **An auction is a log of bids per item, in one order, resolved by a pure function. The log is the truth; the price is derived; the end is decided by one server's clock. Everything hard is at the end: one hot row, one clock, a crowd.**

- **A bid is a maximum, not a price.** The system raises the leader's visible bid only as far as needed to stay ahead, up to the maximum. eBay's help page describes exactly this: you enter the most you will pay and eBay raises your bid in increments, only as far as that limit.
- **Raising your own maximum does not change the price.** The price moves when a competitor's bid is accepted. The checks found this the hard way (section 5): a price recomputed from the top two maximums disagrees with it.
- **One writer per item.** Bids for an item are serialised, so the ledger order is the truth, and replaying the ledger must reproduce the stored state.
- **The end is a rule, not an event.** A bid at or after the end is refused by comparing the server's clock with the end time; nothing has to fire.
- **Late bids are a design choice.** A hard close rewards bidders who arrive in the last second and loses the ones whose packet is slow; a soft close extends the end when a bid lands inside a window, with a cap.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "highest bid wins", "increment" | a bid is a maximum; price = one increment over the runner-up's maximum, capped at the leader's |
| "two people bid at the same moment" | one writer per item, a ledger with a sequence number; the earlier maximum wins a tie |
| "bid sniping", "last-second bids" | hard close versus soft close (window, extension, a hard cap); say what each costs |
| "who decides the auction ended" | one server clock compared with the end time inside the bid transaction |
| "thousands watching a hot item" | coalesce price updates (one per second per watcher), not one push per bid |
| "winner never pays" | a second-chance offer to the runner-up at their maximum, from the ledger |
| "reserve price" | a hidden minimum: if the leader's maximum is below it, no sale (taught briefly, not built) |
| "show bid history" | the ledger, with maximums hidden from other bidders (a product rule) |

---

## 3. Requirements and Capacity

**Functional.** List an item with a start price and an end time; place a bid (a maximum); see the current price and leader; watch live; close at the end; settle with the winner. **Out of scope:** search and categories, seller tools, payments and shipping (see Case Study: Hotel and Flight Booking for the reserve-charge-confirm flow), fraud and shill-bid detection, reserve prices (a homework item).

**Non-functional.** Bids are applied in one order per item; a bid is never silently lost or applied twice; the price is a deterministic function of the ledger; a hot item in its last seconds stays correct and the watchers see a price that is recent, not necessarily every change.

**Capacity estimate.** Every input is **assumed**; no company figures were read. Results are reproduced by `capacity_check_e.py`.

| Input (assumed) | Value |
|---|---|
| live auctions | 20,000,000 |
| bids per day | 10,000,000 |
| share of the day's bids in the busiest hour | 15% |
| ledger row | 100 bytes |
| a hot item's last 10 seconds | 3,000 bids, 50,000 watchers |
| watcher update policy | at most one price push per second |
| soft close | window 10 s, extension 10 s, at most 300 s past the original end |

| Result | Arithmetic | Value |
|---|---|---|
| average bid rate | 10,000,000 / 86,400 | 116 bids per second |
| busiest hour | 1,500,000 / 3,600 | 417 bids per second |
| ledger growth | 10,000,000 x 100 bytes | 1.0 GB per day, 365 GB per year |
| the hot item | 3,000 / 10 s | 300 bids per second on one row: 3.3 ms of serial time per bid |
| one push per accepted bid | 300 x 50,000 | 15,000,000 messages per second for a single item: not buildable |
| at most one push per second per watcher | 50,000 x 1 | 50,000 messages per second, 300 times fewer |
| stepwise raising, $1.00 to $100.00 | table increments | 131 raises (16 + 40 + 75) |
| worst-case extra time from soft close | the cap | 300 seconds |

The platform-wide rate is tiny (116 to 417 bids per second). **The load is one item in its last seconds**: 300 bids per second all queue on one row, and every accepted bid would fan out to the whole audience. The fix for the first is a single writer with a cheap transaction (section 6); for the second, coalescing (section 7). The 131 is why proxy bidding is also a write-saving design: two proxies climbing $1.00 to $100.00 would otherwise be 131 stored raises; the resolver does it in one call.

---

## 4. API and Data Model

```
POST /v1/items/{id}/bids   { max_bid_cents, idempotency_key } -> { outcome, price_cents, leading: bool }
GET  /v1/items/{id}        -> { price_cents, leader: hidden, end_at, bid_count, state }
```

| Table | Columns | Note |
|---|---|---|
| `auctions` | item, start, leader, leader_max, price, end_at, hard_end, state | the current state: derived, and rebuildable from the ledger |
| `bids` | seq, item, bidder, max_bid, at, outcome | the ledger: **every attempt**, accepted or not, in serial order |

Money is integer cents. A bidder's maximum is secret from other bidders; the price is public.

---

## 5. Deep Dive 1: Proxy Bidding as a Pure Function

eBay's automatic bidding page (read 2026-11-27) says you enter the highest price you will pay and the system bids on your behalf, in increments, to keep you in the lead up to that limit; the increment is smaller at low prices and larger at high ones, with this table (the code carries it as `LADDER`):

| Current price | Increment | Current price | Increment |
|---|---|---|---|
| $0.01 to $0.99 | $0.05 | $100.00 to $249.99 | $2.50 |
| $1.00 to $4.99 | $0.25 | $250.00 to $499.99 | $5.00 |
| $5.00 to $24.99 | $0.50 | $500.00 to $999.99 | $10.00 |
| $25.00 to $99.99 | $1.00 | $1,000.00 to $2,499.99 | $25.00 |
| | | $2,500.00 to $4,999.99 | $50.00 |
| | | $5,000.00 and up | $100.00 |

The page also says that the price occasionally rises by less than the table increment, because someone placed a bid slightly above your automatic amount, and that an immediate outbid usually means another bidder's maximum is higher than yours. **What it does not say**, and what this lesson therefore chooses and labels as its own: which price selects the increment (here, the competing bid's amount), how a tie is broken (here, the earlier maximum wins) and what the smallest accepted bid is (here, the current price plus its increment).

```python
# Money is integer cents. LADDER is eBay's published increment table (automatic bidding help page): (lowest price, increment).
LADDER = [(1, 5), (100, 25), (500, 50), (2500, 100), (10000, 250), (25000, 500),
          (50000, 1000), (100000, 2500), (250000, 5000), (500000, 10000)]

def increment(price):
    for low, inc in reversed(LADDER):
        if price >= low:
            return inc
    raise ValueError('price below one cent')

def new_auction(start, end_at, hard_end=None):
    return {'start': start, 'leader': None, 'leader_max': 0, 'price': start, 'end_at': end_at,
            'hard_end': end_at if hard_end is None else hard_end}

def resolve(a, bidder, m):
    """One bid = a MAXIMUM. Returns (new state, outcome). The shown price is derived: one increment above the
    runner-up's maximum, never above the leader's. Raising your own maximum does not move the price."""
    if a['leader'] is None:
        if m < a['start']:
            return a, 'TOO_LOW'
        return {**a, 'leader': bidder, 'leader_max': m, 'price': a['start']}, 'LEADING'
    if bidder == a['leader']:
        if m <= a['leader_max']:
            return a, 'NO_CHANGE'
        return {**a, 'leader_max': m}, 'RAISED'
    if m < a['price'] + increment(a['price']):           # the smallest bid that can move the price
        return a, 'TOO_LOW'
    if m > a['leader_max']:                              # a new leader, who pays one increment over the old maximum
        price = min(m, a['leader_max'] + increment(a['leader_max']))
        return {**a, 'leader': bidder, 'leader_max': m, 'price': price}, 'LEADING'
    # the leader holds (an equal maximum loses: it arrived later); the price rises to one increment over this bid
    return {**a, 'price': min(a['leader_max'], m + increment(m))}, 'OUTBID'

def extended_end(a, now, window, extend):
    """Soft close: an accepted bid in the last `window` seconds pushes the end to now + extend, never past hard_end."""
    if window and now >= a['end_at'] - window:
        return min(a['hard_end'], max(a['end_at'], now + extend))
    return a['end_at']
```

**What `resolve` does.** The first bid at or above the start price leads at the start price. The leader raising their own maximum changes nothing visible. A challenger must bid at least the current price plus one increment, else `TOO_LOW`. A challenger above the leader's maximum becomes the leader and pays one increment over the old maximum, or their own maximum if that is less (the page's "increase by less"). A challenger at or below the leader's maximum loses, and the price rises to one increment over the challenger's bid, never above the leader's maximum. An equal maximum loses to the earlier one.

**The checks.**

- **Table.** `increment` is compared with a separately written copy of the table at **every cent up to $6,000** (600,000 prices), plus every bracket start, and a price below one cent is refused. A comparison on a few values would miss a boundary typo; this one cannot.
- **Ledger model.** 2,500 random bid sequences (up to 14 bids each, five bidders, six start prices, maximums from one cent to $7,000 and many near earlier maximums, ties and off-by-one cases included) are run through `resolve` and through a ledger model that decides acceptance from its own rule, finds the leader as the highest maximum (earlier wins), and finds the price by searching for the lowest amount at least one increment above the runner-up's maximum (a linear scan for small values, a binary search for large ones, the scan checking the search).
- **A finding.** The first version of that model computed the price from the top two maximums alone, and disagreed with `resolve` after the leader raised their own limit: a runner-up at 48,119 cents had pushed the price up to the leader's limit of 48,120; the leader then raised the limit to 490,860, and the model said the price should jump to the runner-up plus an increment (48,619). `resolve` keeps 48,120, and a fixed check now pins it. The price is not a function of the maximums alone; it is a function of the history, because it moves only when a challenger's bid is accepted. The model now takes the highest value produced at challenger events, which matches the eBay page's description that it places a higher bid for you when someone else bids.
- **Hand-worked cases.** An equal maximum loses; $24.99 over a $100 maximum prices at $25.49, crossing the bracket; $5.99 against a $5.50 price is too low because the minimum is $6.00; lowering your own limit is `NO_CHANGE`; a first bid one cent below the start is refused.

---

## 6. Deep Dive 2: One Writer per Item, and a Ledger You Can Replay

Two bids at the same instant need an order. In the store below, each bid runs in one `BEGIN IMMEDIATE` transaction that reads the auction row, applies `resolve`, writes the new state and appends the attempt to `bids`. The autoincrement `seq` is the serial order; there is no other. (In a sharded system the same role is played by routing every bid for an item to one shard or one actor; the conditional-write alternative, an optimistic version check with retry, is the technique of Flash Sale & Ticket Reservation (Ticketmaster).) Server time decides: `now >= end_at` is too late, a bid exactly at the end is refused.

```python
import sqlite3
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE auctions (item TEXT PRIMARY KEY, start INTEGER NOT NULL, leader TEXT, leader_max INTEGER NOT NULL,
                       price INTEGER NOT NULL, end_at REAL NOT NULL, hard_end REAL NOT NULL, state TEXT NOT NULL);
CREATE TABLE bids (seq INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT NOT NULL, bidder TEXT NOT NULL,
                   max_bid INTEGER NOT NULL, at REAL NOT NULL, outcome TEXT NOT NULL);
"""

@contextmanager
def txn(conn):
    conn.execute('BEGIN IMMEDIATE')                      # one writer per auction at a time: the bid order is the ledger order
    try:
        yield
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise

def open_auction(conn, item, start, end_at, hard_end=None):
    a = new_auction(start, end_at, hard_end)
    conn.execute("INSERT INTO auctions VALUES (?, ?, NULL, 0, ?, ?, ?, 'OPEN')", (item, start, start, a['end_at'], a['hard_end']))

def _load(conn, item):
    r = conn.execute("SELECT start, leader, leader_max, price, end_at, hard_end, state FROM auctions WHERE item = ?", (item,)).fetchone()
    if r is None:
        raise KeyError(item)
    return {'start': r[0], 'leader': r[1], 'leader_max': r[2], 'price': r[3], 'end_at': r[4], 'hard_end': r[5]}, r[6]

def place_bid(conn, item, bidder, m, now, window=0, extend=0):
    """Server time decides. now >= end_at is too late. Every attempt, accepted or not, is appended to the ledger."""
    with txn(conn):
        a, state = _load(conn, item)
        if state != 'OPEN' or now >= a['end_at']:
            outcome = 'CLOSED'
        else:
            new, outcome = resolve(a, bidder, m)
            if outcome in ('LEADING', 'RAISED', 'OUTBID'):
                new['end_at'] = extended_end(a, now, window, extend)
                conn.execute("UPDATE auctions SET leader = ?, leader_max = ?, price = ?, end_at = ? WHERE item = ?",
                             (new['leader'], new['leader_max'], new['price'], new['end_at'], item))
        conn.execute("INSERT INTO bids (item, bidder, max_bid, at, outcome) VALUES (?, ?, ?, ?, ?)", (item, bidder, m, now, outcome))
        return outcome

def close(conn, item, now):
    """Idempotent. Returns (winner, price) or None for no sale."""
    with txn(conn):
        a, state = _load(conn, item)
        if state == 'OPEN' and now >= a['end_at']:
            state = 'SOLD' if a['leader'] else 'NO_SALE'
            conn.execute("UPDATE auctions SET state = ? WHERE item = ?", (state, item))
        if state == 'SOLD':
            return a['leader'], a['price']
        return None

def runner_up(conn, item):
    """For a second-chance offer when the winner does not pay: the best accepted maximum among the other bidders."""
    a, _ = _load(conn, item)
    return conn.execute("SELECT bidder, MAX(max_bid) AS m FROM bids WHERE item = ? AND bidder != ? AND outcome IN ('LEADING', 'RAISED', 'OUTBID') "
                        "GROUP BY bidder ORDER BY m DESC, MIN(seq) LIMIT 1", (item, a['leader'])).fetchone()
```

**The replay check.** Twelve threads race 30 bids each at random times against one item in one database file, with a soft close and a cap. The ledger must then hold all 360 attempts with sequence numbers 1 to 360 and no gaps. Feeding the ledger back through the pure functions in sequence order must reproduce **every recorded outcome** and the stored leader, maximum, price and end time. A lost update, a race that applied two bids to the same state, or a bid that never reached the ledger breaks that equality. The same replay runs on 200 single-threaded auctions with random bids; there the check also compares `runner_up` with the best accepted maximum among the other bidders, computed from the ledger by hand.

**Closing.** `close` is idempotent and compares the same clock: before the end it does nothing; at the end it records `SOLD` or `NO_SALE`; any bid after that is `CLOSED`. A job that closes auctions must be safe to run twice and late, because the predicate (`now >= end_at`) is what refuses bids, not the job.

**What the hot item does to the row.** 300 bids per second is 3.3 ms per bid in series (section 3). A transaction that reads one row, runs a pure function and writes two rows fits that budget with room; one that calls another service inside the transaction does not. Keep network calls out of the bid transaction (the rule Airbnb's payments post gives for its idempotency library, section 9).

---

## 7. Deep Dive 3: The Ending, Late Bids and Settlement

**Hard close.** The end time is fixed. A bidder whose maximum is the highest but whose bid arrives after the end loses to a lower bidder whose bid arrived earlier. That is not a bug in the store; it is the rule, and bidders who wait for the last seconds (eBay's own help text describes this tactic, "bid sniping", as waiting until the last few seconds to prevent others from bidding) are exposed to network delay.

**Soft close.** An accepted bid inside the last `window` seconds moves the end to `now + extend`, never past `hard_end`. Only **accepted** bids extend (a rejected bid must not, or anyone could keep the auction open for free: checked), the window boundary is inclusive (a bid exactly `window` seconds before the end counts as inside it, tested with an extension longer than the window so that the difference shows; one millisecond earlier does not), and the cap bounds the worst case at 300 seconds.

**Measured here (illustrative: a toy population, not eBay data).** Six bidders with values drawn uniformly from $10 to $100. Each bids their value as a maximum, truthfully. Half send in the last 3 seconds (snipers); the other half send earlier. Every bid takes a random 0 to 4 seconds to arrive. Over 6,000 auctions each:

| Rule | Highest-value bidder wins | Bids rejected as late |
|---|---|---|
| hard close | 87.6% | 12.2% |
| soft close, 10 s window, 10 s extension | 95.7% | 4.2% |

The hard-close figure is what arithmetic predicts: a sniper (half of bidders) is late when the delay exceeds 3 seconds (a quarter of the time), 12.5% of the highest-value bidders lose, and the simulation gives 12.4%. The soft close recovers most of that because a bid that lands in the window pulls the end later, and later snipers land inside it; it does not recover all, because a sniper arriving after the original end with no earlier extension is still too late. **This is the lesson's model, with invented behaviour; real bidders adapt to the rule, which a fixed simulation cannot show.** The eBay pages read for this lesson do not say whether eBay extends auctions, so this lesson does not say what eBay does.

**Settlement.** `close` returns the winner and the price; payment is a separate flow with its own idempotency and crash points (see Case Study: Hotel and Flight Booking). If the winner does not pay, eBay's help page on Second Chance Offers describes the seller offering the item to another bidder at the amount of that bidder's last bid, valid for 1, 3, 5 or 7 days. `runner_up` above is the ledger query behind that: the best accepted maximum among the other bidders.

**Watching.** Do not push every accepted bid to every watcher: 300 bids per second to 50,000 watchers is 15,000,000 messages per second. Send each watcher the latest price at most once per second (50,000 per second) and keep the bid acknowledgement to the bidder immediate and separate. The transport (long polling, server-sent events, WebSockets) is Scaling Patterns II: Large Blobs, Long-Running Tasks and Real-Time Updates; the auction-specific point is that **a watcher's price is allowed to lag by a second, a bidder's answer is not**.

---

## 8. Failure Modes

| What breaks | What you see | Defence |
|---|---|---|
| read-modify-write without one writer | a lost bid; two leaders | one transaction per bid, a ledger, the replay check |
| a bid exactly at the end | disputes | one clock, `now >= end_at` refuses, tested at the boundary |
| clocks differ between servers | a bid accepted by one server after another closed it | the check and the write use the same database clock; see Time, Clocks and Ordering |
| a rejected bid extends a soft close | an auction held open by noise | extend only on accepted bids |
| soft close without a cap | an auction that never ends | `hard_end` |
| equal maximums | the later bidder wins (or neither does) | earlier wins; the ledger sequence settles it |
| price recomputed from maximums alone | the price jumps when the leader raises their limit | derive it at challenger events (section 5) |
| every bid pushed to every watcher | a message storm on the hot item | at most one push per second per watcher |
| winner does not pay | an unsold item | second-chance offer to the runner-up from the ledger |
| float money | rounding in increments | integer cents |
| closing job run twice or late | a double sale | idempotent `close`; the predicate refuses late bids |

---

## 9. What Real Companies Did

- **eBay, automatic bidding and increments** (eBay Help, "Automatic bidding", read 2026-11-27): the entered amount is the most the bidder will pay; eBay bids on their behalf in increments up to it; the increment table above; "occasionally bids increase by less"; an immediate outbid usually means a higher maximum.
- **eBay, Second Chance Offers** (eBay Help, read 2026-11-27): a seller may offer the item to a non-winning bidder at the amount of that bidder's last bid, with 1, 3, 5 or 7 days to accept. The same page's related-article list gives one-sentence descriptions of bid sniping and of reserve prices (the minimum the seller will accept; below it the item does not sell); only those sentences were seen.
- **Pages not read.** eBay's own pages on bid sniping, reserve prices, how bidding works and bid retraction returned a bot-verification page when fetched, and were not read; no attempt was made to get around it. **No source was read on eBay's architecture, its bid ordering, its close rule or its capacity.** The data model, the one-writer ledger and the soft-close option here are the general approach, not eBay's.
- **Airbnb** (Airbnb Tech Blog, 16 April 2019, read 2026-11-27): its payments idempotency library keeps network calls out of database transactions; used here only as a design rule for the bid transaction. The post is about payments, not auctions.

---

## 10. Pitfalls Checklist

1. **Storing the last bid as the price.** A bid is a maximum; the price is derived.
2. **Recomputing the price from the maximums.** Raising your own limit would move it; derive it at challenger events.
3. **Unordered bids.** One writer, one ledger, one sequence.
4. **Using two clocks** for "is it still open" and "when did the bid arrive".
5. **`>` where `>=` belongs** at the end time, or at the soft-close window edge.
6. **Letting a rejected bid extend the auction.**
7. **A soft close with no cap.**
8. **Pushing every bid to every watcher.**
9. **Floats for money.**
10. **Claiming what eBay does** without a source: its tie rule, its close rule and its architecture are not in the pages read.

---

## Drills

1. A has a $100 maximum on an item starting at $1.00. B bids $24.99. What is the price, who leads, and what is the smallest bid that can now move it?
2. A leads with a $10.00 maximum and B bids exactly $10.00. Who leads, what is the price, and why?
3. The leader raises their limit from $10 to $50 while a runner-up sits at $9.99. What does the price do, and why does a formula using only the two maximums disagree?
4. Two bids for the same item arrive in the same millisecond on two servers. How does the design order them, and how would you prove afterwards that none was lost?
5. Explain the 87.6% and 95.7% figures: why is the hard-close loss near 12.5%, and why does a soft close not recover everything?
6. A rejected bid arrives inside the soft-close window. Should the end move? What happens if it does?
7. The hot item has 300 bids per second and 50,000 watchers. What do you send to whom, and how many messages per second is that?
8. The winner does not pay. Using only the ledger, who gets the second-chance offer, and at what amount?

---

## Homework

1. Run `sy59_check.py` on this file. Change the tie rule (`m <= leader_max` to `m < leader_max` in the challenger branch) and find which assertion fails first; then make a rejected bid extend the end.
2. Add a hidden reserve: if `leader_max` is below it at close, the result is `NO_SALE`; if the leader's maximum reaches it, the price becomes at least the reserve. Decide the rule and test it against a ledger model.
3. Replace the single `BEGIN IMMEDIATE` with an optimistic version column and retries, and use the replay check to prove no update is lost.
4. Add an automatic settlement job that closes due auctions, and check it is safe to run twice and at the same instant as a bid.

---

## Sources

All read 2026-11-27. The code, the tie rule, the minimum-bid rule, the soft close, the simulation and every number marked *assumed* or *illustrative* are this lesson's own.

- eBay Help, *Automatic bidding*, ebay.com/help/buying/bidding/automatic-bidding?id=4014. Read in full. Source for automatic bidding and the increment table.
- eBay Help, *Responding to Second Chance Offers*, ebay.com/help/buying/bidding/bid-increments?id=4017 (the address I requested as the increments page returned this article). Read in full. Source for second-chance offers, and for the one-sentence descriptions of bid sniping and reserve prices in its related-article list.
- Airbnb Tech Blog, *Avoiding double payments in a distributed payments system* (16 April 2019), read as extracted text; used for one design rule only.
- eBay Help pages on bid sniping, reserve prices, how bidding works and retracting a bid: fetched, but returned a bot-verification page; not read.

## Further reading (not consulted)

Roth and Ockenfels on last-minute bidding and auction end rules; auction theory texts (second-price and ascending auctions); any account of how eBay or another auction site orders bids or closes auctions; the PostgreSQL and SQLite transaction documentation. None were read, so no claim is made about them.

*Last reviewed: 27 November 2026.*
