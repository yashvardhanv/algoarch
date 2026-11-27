# Lesson 58 — Case Study: Hotel and Flight Booking (Airbnb / Booking.com)

> **Priority:** ★★★★☆ (proposed; the curriculum data holds the final rating) — a booking is the cleanest case of inventory that spans many rows (every night of a stay) with money moving outside your database, and interviewers probe the overlap, the retry and the crash.
>
> **Study time:** 80 minutes. **Do this after:** Flash Sale & Ticket Reservation (Ticketmaster); Idempotency, Outbox & Sagas; Scaling Patterns I: Reads, Writes and Contention.
>
> **Level:** extended.

A hotel room is not a seat. A seat is one row; a stay is a run of nights that must all be free, or none is taken, and the same room can be sold again the day the guest leaves. The money moves through a payment provider you do not control, so booking is three steps (reserve, charge, confirm) with a crash possible between any two. This lesson builds the night-by-night inventory, an overbooking rule, availability bitmaps and the reserve-charge-confirm flow as code checked in `test/lesson_code/sy58_check.py` against a list-based model, an exact binomial and crash injection at every point; capacity numbers come from `capacity_check_e.py`. Holds with expiry, conditional updates and idempotency keys are taught in Flash Sale & Ticket Reservation (Ticketmaster) and Idempotency, Outbox & Sagas, and are linked, not repeated.

---

## 1. Mental Model

> **Availability is a count per room type per night. A stay is a multi-row write that must be all-or-nothing. The payment happens outside the database, so every booking is a flow with crash points, and the design is the recovery rule for each one. Search may show stale availability; the booking write may not.**

- **A stay is a half-open range of nights.** Check-in day included, check-out day not: a guest leaving on the 3rd and another arriving on the 3rd do not collide. Inclusive ranges lose a night of revenue or double-book it.
- **A single-unit listing is a room type with total 1.** The same table and the same conditional update serve both; only a declarative no-overlap constraint is specific to the single-unit case.
- **Overbooking is a policy with a price,** computed from the show-up rate and what a bumped guest costs. It assumes guests fail independently; a shared event breaks that.
- **Search is a read of a copy; booking is a write to the record.** They disagree for a moment, and the lesson is what the user sees when they do.
- **Reserve, charge, confirm** is a saga: the provider call sits between two transactions, so retries must be safe at every step.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "book a room for a date range" | per-night inventory rows; one conditional `UPDATE ... WHERE sold + n <= total` over the nights; all nights updated or none |
| "an Airbnb home: one guest at a time" | the same with total 1, or a no-overlap constraint on date ranges (PostgreSQL exclusion constraint) |
| "check-out and check-in on the same day" | half-open ranges: nights `d_in` to `d_out - 1` |
| "hotels sell more rooms than they have" | an overbooking limit from the show-up rate and the cost of walking a guest (section 6) |
| "search must be fast, bookings are rare" | a denormalised availability index for search (bitmaps per listing); recheck in the system of record at booking |
| "charge the card, then confirm" | reserve with expiry, idempotent charge, confirm that re-checks expiry; a reconciliation job (section 7) |
| "flight plus hotel" | several reservations: one transaction if co-located, otherwise a saga with cancel as the compensation |
| "user retries after a timeout" | an idempotency key per booking attempt; the same key with a different request is an error |

---

## 3. Requirements and Capacity

**Functional.** Search by place, dates and guests; see price and availability; reserve for a time; pay; confirm; cancel; one booking spans several nights (or, for flights, several segments). **Out of scope:** ranking, pricing and promotions, host or hotel onboarding, seat selection (the seat map is Flash Sale & Ticket Reservation (Ticketmaster)), refund policy.

**Non-functional.** Never sell a night beyond its total (except by a deliberate overbooking limit); a confirmed booking is durable and was paid for; a crash at any step ends in a state a job or a retry can finish; search stays fast while bookings are rare.

**Capacity estimate.** Every input is **assumed**; no company's figures were read. Results are reproduced by `capacity_check_e.py`.

| Input (assumed) | Value |
|---|---|
| peak searches | 50,000 per second |
| look-to-book ratio | 500 searches per booking |
| nights per stay | 3 on average |
| single-unit listings | 5,000,000, one availability bit per night for 365 nights |
| hotel inventory | 500,000 hotels x 6 room types x 365 nights, 16 bytes per (type, night) row |
| a hot hotel on a peak date | 40 rooms left, 2,000 booking attempts in one minute |
| reservation time to live | 10 minutes |

| Result | Arithmetic | Value |
|---|---|---|
| bookings | 50,000 / 500 | 100 bookings per second |
| night rows touched | 100 x 3 | 300 row updates per second (200 short transactions: reserve and confirm) |
| single-unit availability bitmaps | 5,000,000 x 365 / 8 bytes | 228 MB |
| hotel inventory rows | 500,000 x 6 x 365 | 1,095,000,000 rows, 17.5 GB |
| reservations held at once, if the 100 per second all held for the full time (a lower bound: attempts, including abandoned ones, run higher) | 100 per second x 600 s | 60,000 reservations, 180,000 room-nights: 0.016% of the rows |
| a hot hotel | 2,000 per minute | 33.3 attempts per second; the 40 rooms are all held after 1.2 seconds |

The write path is 0.2% of the request rate (100 bookings per second against 50,000 searches), so a booking database is not the bottleneck and search is. Reservations held at once are a rounding error across the whole inventory, **but not for one hot hotel**: the last 40 rooms are all held within about a second, then every other guest sees "sold out" while most holders abandon. That is the Flash Sale & Ticket Reservation (Ticketmaster) hold problem again, handled with a short time to live and a visible countdown, not with a bigger database.

---

## 4. API and Data Model

```
GET  /v1/search?place=..&check_in=..&check_out=..&guests=..   -> [ { listing_id, price, rooms_left, quote_id } ]
POST /v1/bookings   { idempotency_key, listing_or_room_type, check_in, check_out, rooms, quote_id }  -> { booking_id, state }
POST /v1/bookings/{id}/pay      { idempotency_key, payment_method }   -> { state }
POST /v1/bookings/{id}/cancel
```

| Table | Columns | Note |
|---|---|---|
| `inv` | (room type, night) primary key, total, sold | `CHECK (sold >= 0 AND sold <= total)` is the seat belt behind the conditional update |
| `bookings` | id, idempotency key (unique), guest, room type, d_in, d_out, rooms, state, expires | state: PENDING, CONFIRMED, CANCELLED, EXPIRED |
| search index | per listing: an availability bitmap, price tiers, location cell | rebuilt or patched from `inv`; may lag |
| payments | provider reference per idempotency key, amount, refunded flag | the provider honours the key too |

The quote carried from search to booking is a price the user saw; the booking path decides whether it still holds (a changed price is a different message from "sold out").

---

## 5. Deep Dive 1: Inventory by Night, All or Nothing

One `UPDATE` adds the rooms to `sold` on every night of the stay, and only on nights where the room still fits. If the number of rows changed is not the number of nights, some night was full or missing, and the whole thing is undone (a savepoint here, so that expired reservations reclaimed a moment earlier stay reclaimed). A zero-night stay would change zero rows and "succeed", so the function refuses it first. Expiry differs from Flash Sale & Ticket Reservation (Ticketmaster), where it is a predicate in the `WHERE` clause and nothing has to run. Counters cannot be a predicate, so a pending reservation past its time is released explicitly, by the next `reserve` (a lazy reclaim) or by `expire`; this is the one new mechanism here.

```python
import sqlite3
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE inv (rtype TEXT NOT NULL, night INTEGER NOT NULL, total INTEGER NOT NULL, sold INTEGER NOT NULL DEFAULT 0,
                  PRIMARY KEY (rtype, night), CHECK (sold >= 0 AND sold <= total));
CREATE TABLE bookings (id INTEGER PRIMARY KEY AUTOINCREMENT, idem TEXT UNIQUE NOT NULL, guest TEXT NOT NULL,
                       rtype TEXT NOT NULL, d_in INTEGER NOT NULL, d_out INTEGER NOT NULL, rooms INTEGER NOT NULL,
                       state TEXT NOT NULL, expires INTEGER NOT NULL);
"""

class IdempotencyMismatch(Exception):
    pass

@contextmanager
def txn(conn):
    conn.execute('BEGIN IMMEDIATE')
    try:
        yield
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise

def _release(conn, rtype, d_in, d_out, rooms):
    conn.execute("UPDATE inv SET sold = sold - ? WHERE rtype = ? AND night >= ? AND night < ?", (rooms, rtype, d_in, d_out))

def _reclaim(conn, now):
    """Pending reservations whose time ran out give their rooms back. Runs inside every reserve."""
    for bid, rt, a, b, n in conn.execute("SELECT id, rtype, d_in, d_out, rooms FROM bookings "
                                         "WHERE state = 'PENDING' AND expires <= ?", (now,)).fetchall():
        _release(conn, rt, a, b, n)
        conn.execute("UPDATE bookings SET state = 'EXPIRED' WHERE id = ?", (bid,))

def reserve(conn, idem, guest, rtype, d_in, d_out, rooms, now, ttl):
    """Nights d_in .. d_out-1 (the check-out day is not a night). All nights or none.
    Returns the booking id, or None if any night is full. The same idem with the same request returns the same id."""
    if d_out <= d_in or rooms < 1:
        raise ValueError('a stay needs at least one night and one room')
    args = (guest, rtype, d_in, d_out, rooms)
    with txn(conn):
        row = conn.execute("SELECT id, guest, rtype, d_in, d_out, rooms FROM bookings WHERE idem = ?", (idem,)).fetchone()
        if row:
            if tuple(row[1:]) != args:
                raise IdempotencyMismatch(idem)
            return row[0]
        _reclaim(conn, now)                           # stays committed even if this request fails
        conn.execute('SAVEPOINT stay')
        cur = conn.execute("UPDATE inv SET sold = sold + ? WHERE rtype = ? AND night >= ? AND night < ? "
                           "AND sold + ? <= total", (rooms, rtype, d_in, d_out, rooms))
        if cur.rowcount != d_out - d_in:              # a full night, or a night with no inventory row: undo the rest
            conn.execute('ROLLBACK TO stay')
            conn.execute('RELEASE stay')
            return None
        conn.execute('RELEASE stay')
        cur = conn.execute("INSERT INTO bookings (idem, guest, rtype, d_in, d_out, rooms, state, expires) "
                           "VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)", (idem, *args, now + ttl))
        return cur.lastrowid

def confirm(conn, bid, now):
    """Confirm only if the reservation is still alive at write time. Idempotent."""
    with txn(conn):
        cur = conn.execute("UPDATE bookings SET state = 'CONFIRMED' WHERE id = ? AND state = 'PENDING' AND expires > ?", (bid, now))
        if cur.rowcount == 1:
            return True
        row = conn.execute("SELECT state FROM bookings WHERE id = ?", (bid,)).fetchone()
        return row is not None and row[0] == 'CONFIRMED'

def cancel(conn, bid):
    with txn(conn):
        row = conn.execute("SELECT rtype, d_in, d_out, rooms, state FROM bookings WHERE id = ?", (bid,)).fetchone()
        if row is None or row[4] not in ('PENDING', 'CONFIRMED'):
            return False
        _release(conn, *row[:4])
        conn.execute("UPDATE bookings SET state = 'CANCELLED' WHERE id = ?", (bid,))
        return True

def expire(conn, bid, now):
    """Give a reservation up: only if it is still pending and past its time, in one conditional statement."""
    with txn(conn):
        cur = conn.execute("UPDATE bookings SET state = 'EXPIRED' WHERE id = ? AND state = 'PENDING' AND expires <= ?", (bid, now))
        if cur.rowcount != 1:
            return False
        _release(conn, *conn.execute("SELECT rtype, d_in, d_out, rooms FROM bookings WHERE id = ?", (bid,)).fetchone())
        return True

def rooms_left(conn, rtype, d_in, d_out):
    """What a search page may show: the tightest night. A read, so it can be stale by the time you click."""
    low, nights = conn.execute("SELECT MIN(total - sold), COUNT(*) FROM inv WHERE rtype = ? AND night >= ? AND night < ?",
                               (rtype, d_in, d_out)).fetchone()
    return low if nights == d_out - d_in else 0
```

**The checks.** The code runs against a list-based model that keeps every booking in a list and recomputes each night's occupancy by scanning, on 400 random operation sequences (reserve, retry with the same or a changed request, confirm, cancel, time passing, 3 to 20 nights, totals 1 to 4, stays up to six nights, some running past the inventory window). After **every** operation the counters must equal the scan, nothing may exceed its total, the booking states must agree, and the return values must match. Fixed cases pin the boundaries: a stay checking out on the 3rd and another checking in on the 3rd both fit; overlapping stays do not; a stay running past the inventory window is refused and leaves no night half-booked; zero nights and zero rooms are errors; confirm at exactly the expiry second fails and one second earlier succeeds; a retry after expiry returns the dead booking, so the client must use a new key; the same key with a changed request is an error (Stripe's idempotency documentation describes the same refusal when parameters differ). Twelve threads then hammer one database file and the counters must still equal what the bookings table implies. That test cannot tell the conditional update from check-then-write, because `BEGIN IMMEDIATE` serialises everything; the no-oversell claim is defended by the lock, the conditional update and the `CHECK`, and demonstrated by the model comparison, not by the threads.

**What the constraint adds.** In PostgreSQL, a single-unit listing can also be protected declaratively: a range column plus `EXCLUDE USING GIST (listing WITH =, during WITH &&)` rejects any overlapping row (the PostgreSQL range-type documentation shows this for room reservations, with the `btree_gist` extension for the equality part, and notes that `UNIQUE` is usually unsuitable for range types). It cannot express "up to 6 of this room type", so per-night counters remain the general tool. The `CHECK` in the schema above is the same idea for counters: if some code path forgets the condition, the database refuses the write instead of overselling quietly.

**In a row-locking database,** the same `UPDATE` is serialised per row; PostgreSQL's documentation says a blocked update waits for the first transaction and, if that commits, re-evaluates the `WHERE` clause on the updated row at read committed. Update the night rows in a fixed order to avoid deadlocks between overlapping stays; this lesson's SQLite model has one writer, so that is advice, not something these checks exercise.

**Flights are the same table.** Room type becomes flight plus fare class, and a night becomes a flight date. A connecting itinerary is several reservations: in one transaction when the inventory is in one database, otherwise a saga with `cancel` as the compensation. How airline systems actually allocate fare classes was not read for this lesson.

---

## 6. Deep Dive 2: Overbooking Is a Number, Not a Hunch

Guests cancel and no-show, so selling exactly the capacity leaves rooms empty. Sell `L` bookings for `C` rooms; each guest shows up independently with probability `p`. A guest who shows and gets a room earns `r`; a guest who shows and finds none costs `c` (rebooking, compensation). The expected profit is `r*E[min(S, C)] - c*E[max(S - C, 0)]` with `S` shows out of `L`. Adding one more booking changes the profit only if that guest shows (probability `p`): if at least `C` of the first `L` already showed, the newcomer is walked (`-c`); otherwise, the newcomer fills a room (`+r`). So accept the next booking exactly while

`P(at least C of the L booked show) < r / (r + c)`.

The marginal probability only rises with `L`, so the first `L` that reaches the ratio is the optimum. The code computes this and an independent function computes the profit.

```python
from math import comb

def overflow_prob(L, C, p):
    """P(at least C of the L booked guests show up), each showing independently with probability p."""
    return sum(comb(L, k) * p ** k * (1 - p) ** (L - k) for k in range(C, L + 1))

def best_limit(C, p, r, c):
    """How many bookings to accept for C rooms. Guest shows: earns r if there is a room, costs c (walk the guest) if not.
    The L+1-th booking pays exactly while P(at least C of the first L show) < r / (r + c)."""
    assert 0 < p <= 1 and r > 0 and c > 0
    L = C
    while overflow_prob(L, C, p) < r / (r + c):
        L += 1
    return L

def expected_profit(L, C, p, r, c):
    return sum(comb(L, k) * p ** k * (1 - p) ** (L - k) * (r * min(k, C) - c * max(k - C, 0)) for k in range(L + 1))
```

**Checks.** `best_limit` is compared with an exact distribution built by convolving one guest at a time (independent of `math.comb`) and a brute-force maximum over every limit up to 1.4 C / p + 30, on 120 random parameter sets with capacities from 1 to 120, show-up rates 0.3 to 0.99 and walk costs 0.2 to 10 times the room's value; the optimum's profit must match the brute-force maximum, and the rule must give `L = C` for guests who always show and no more than one extra booking for a ruinous walk cost. A Monte Carlo run of 20,000 simulated nights agrees with the closed form.

**The numbers (illustrative: invented show-up and cost figures, not from any source).** 100 rooms, 90% of guests show, a walked guest costs three times a room night. The rule gives **limit 109**; expected profit rises from 90.00 to **96.16** room-night units; the expected number of walked guests is **0.49**; the chance that at least one guest is walked is **0.227**; expected empty rooms fall from 10.00 to 2.39.

**The hole in the model.** Independent guests are an assumption. Suppose instead that a storm or an event moves everyone together: the show-up rate is 85% on half the nights and 95% on the other half (still 90% on average). With the same limit of 109, the expected walked guests rise to **1.83** and the chance of at least one walked guest to **0.458**, double the independent figure. An overbooking limit tuned on average rates under-counts the bad nights. The remedy is a lower limit for dates with correlated risk (events, holidays), not a better formula; and the walk policy (rebook nearby, compensate) is a product decision this lesson does not model.

---

## 7. Deep Dive 3: Search Versus Booking, and the Flow With Crash Points

**Search is a read of a copy.** For single-unit listings a bitmap of free nights per listing answers "is this whole range free?" with one mask and compare: bit `d` set means night `d` is free. Python integers are not limited to a machine word, so a 365-night bitmap is one integer; the checks use widths of 8, 31, 64, 65, 120, 365 and 400 against a night-by-night loop, because a shift written for 64 bits fails exactly at the width where it stops fitting. Keep the brackets in `(avail & m) == m`: Python's bitwise operators bind tighter than comparisons, so here they are optional (a mutation test that removed them survived, which is how this lesson's first draft, which claimed otherwise, was caught), but in C, Java and JavaScript `==` binds tighter than `&`, so the bracket-free form is a different test in C and JavaScript and a compile error in Java (`int & boolean`). The index can lag the record, so the user may see a room that is gone; the booking step rechecks, and the page must say "no longer available" or "price changed", not fail silently.

```python
def night_mask(d_in, d_out):
    return ((1 << (d_out - d_in)) - 1) << d_in           # one bit per night, bit d set = night d

def is_free(avail, d_in, d_out):
    m = night_mask(d_in, d_out)
    return (avail & m) == m                               # brackets are optional in Python, required in C, Java and JavaScript

def take(avail, d_in, d_out):
    return avail & ~night_mask(d_in, d_out)
```

**The booking flow.** Reserve is one database transaction. The charge is a call to a provider; its idempotency key is the booking's key, so repeating it charges once (Stripe's documentation describes keys honoured by its API; Airbnb's post describes keys for its own payment services). Confirm is a second transaction that succeeds only if the reservation has not expired. A crash can fall after each step, and the code defines what each leaves:

| Crash after | State | What finishes it |
|---|---|---|
| reserve | pending, no charge | a retry with the same key continues; if the time has run out, the retry returns `EXPIRED` without charging; the rooms free up at the next reservation |
| charge | pending, charged | a retry confirms; with no retry, `reconcile` refunds once the reservation can no longer be confirmed and releases the rooms |
| confirm | confirmed, charged | a retry finds the same booking and answers `CONFIRMED` again |
| charge slower than the reservation | confirm refused | the flow refunds at once |

```python
class Crash(Exception):
    pass

class Psp:
    """A payment provider that honours idempotency keys: the same key charges once."""
    def __init__(self):
        self.charges, self.refunded = {}, set()
    def charge(self, idem, amount):
        self.charges.setdefault(idem, amount)
    def refund(self, idem):
        self.refunded.add(idem)

def state_of(conn, bid, now):
    """The state as of `now`: a pending reservation past its time counts as expired even before anyone reclaims it."""
    state, expires = conn.execute("SELECT state, expires FROM bookings WHERE id = ?", (bid,)).fetchone()
    return 'EXPIRED' if state == 'PENDING' and expires <= now else state

def book(conn, psp, idem, guest, rtype, d_in, d_out, rooms, amount, now, ttl=600, crash_at=None, paid_at=None):
    """reserve (database) -> charge (outside, idempotent) -> confirm (database). A retry with the same key resumes."""
    bid = reserve(conn, idem, guest, rtype, d_in, d_out, rooms, now, ttl)
    if bid is None:
        return 'SOLD_OUT'
    if state_of(conn, bid, now) in ('EXPIRED', 'CANCELLED'):
        return 'EXPIRED'                                  # a dead reservation: do not charge, start over with a new key
    if crash_at == 'after_reserve':
        raise Crash()
    psp.charge(idem, amount)
    if crash_at == 'after_charge':
        raise Crash()
    if not confirm(conn, bid, now if paid_at is None else paid_at):
        psp.refund(idem)                                  # the reservation ran out while the guest was paying
        return 'EXPIRED'
    if crash_at == 'after_confirm':
        raise Crash()
    return 'CONFIRMED'

def reconcile(conn, psp, now, after_read=None):
    """Periodic job. A charge whose reservation is dead is refunded. A pending reservation is given up only through
    expire(), so a guest who confirms between our read and our decision wins: the conditional update then changes nothing."""
    for idem in list(psp.charges):
        if idem in psp.refunded:
            continue
        row = conn.execute("SELECT id, state FROM bookings WHERE idem = ?", (idem,)).fetchone()
        if after_read:
            after_read(idem)                              # test seam: lets a retry run between the read and the decision
        if row is None or row[1] in ('EXPIRED', 'CANCELLED') or (row[1] == 'PENDING' and expire(conn, row[0], now)):
            psp.refund(idem)
```

**The checks.** Every crash point is run with and without a retry; after each, with a reconciliation pass, two things must hold: a charge is kept if and only if its booking is confirmed (so the guest is never charged for nothing, and never given a room for free), and the inventory counters equal the occupancy the bookings table implies. A fuzz of 250 sequences adds random crashes, retries, slow payments and time passing, and ends with the same invariants. The first version of `reconcile` had two flaws that these checks now pin. It cancelled with a plain `cancel`, which accepts a confirmed booking, so a reconcile that had read `PENDING` could cancel and refund a booking whose guest had just been told `CONFIRMED` (a retry from a worker whose clock read 599 against an expiry of 600); and the first fuzz hid the hazard by never letting time go backwards. Now `reconcile` gives a reservation up only through `expire`, one conditional update that changes nothing unless the booking is still pending and past its time, so `confirm` and `expire` cannot both win. A second check runs `reconcile` while the reservation is still alive and requires it to leave a charged pending booking alone, so the retry confirms. **What is not solved:** the model takes `now` from the caller, so two callers with skewed clocks can disagree about expiry; the conditional transitions make the outcome consistent (one winner), not the clocks agree. Production code should take the time from the database inside the transaction.

Airbnb's description of its payments framework shows the same shape from the other side: record the request and take a lease on its key in a transaction, do the network call outside any database transaction, record the result in another; classify errors as retryable or not; do not read idempotency data from a lagging replica, because a retry could then miss the first response and charge twice.

---

## 8. Failure Modes

| What breaks | What you see | Defence |
|---|---|---|
| check-then-write on availability | two guests, one night | one conditional update; rowcount must equal the nights; a `CHECK` behind it |
| inclusive end date | a lost night, or a double booking on the changeover day | half-open ranges, tested at the boundary |
| partial update of a multi-night stay | some nights taken for a refused booking | all or nothing: savepoint or transaction rollback |
| zero-night or zero-room request | an empty booking that "succeeds" | validate before updating |
| overbooking tuned on average show-up rates | a bad night walks many guests | a lower limit for correlated dates; measure the walk rate |
| stale search results | "sold out" after clicking, or a changed price | recheck at booking; say which one happened |
| crash after the charge | a charged guest with no booking | idempotent retry plus reconciliation that refunds |
| payment slower than the reservation | confirm refused after charging | refund at once; shorter payment timeouts than the reservation time |
| hot hotel, last rooms | rooms held by guests who never pay | short time to live, a visible countdown, release on abandon |
| idempotency data on a lagging replica | a retry misses the first result and charges again | read it from the primary (Airbnb's post) |
| same key, different request | silently returns the first booking | compare the request and refuse (tested) |

---

## 9. What Real Companies Did

- **Airbnb, payments idempotency** (Airbnb Tech Blog, 16 April 2019, read 2026-11-27): a library ("Orpheus") for idempotent API calls. A request has an idempotency key; its record is written and read on a sharded primary (the post says master); each request takes a database lease on its key, with an expiry that should exceed the call's timeout; the request is split into a database phase, the network call and a second database phase, with no network calls inside database transactions and no database access during the call; errors are classified retryable or not; responses are recorded. The post reports "five nines" consistency for payments. It is about payments, not about availability or calendars.
- **Stripe** (API reference, read 2026-11-27): an idempotency key per request; for the version described, the first response (including errors) is saved and returned on retries with the same key, and a retry whose parameters differ from the original is refused.
- **PostgreSQL** (range types, `CREATE TABLE`, transaction isolation documentation, read 2026-11-27): range types with `&&` overlap, exclusion constraints with a GiST index, and the behaviour of a blocked `UPDATE` at read committed.
- **No source was read on how Airbnb, Booking.com or an airline reservation system stores availability or sets overbooking limits.** The inventory design, the overbooking rule and the flow here are the general approach, not a description of any company's system.

---

## 10. Pitfalls Checklist

1. **Inclusive end date.** The check-out day is not a night.
2. **Updating nights one at a time without undoing.** Count the rows changed and compare with the nights.
3. **Letting an empty range through.** Zero rows changed equals zero nights, and the check passes.
4. **`avail & m == m` in C, Java or JavaScript.** There `==` binds tighter than `&` (a wrong test in C and JavaScript, a compile error in Java); write `(avail & m) == m` everywhere.
5. **Trusting search availability at booking time.** It is a copy.
6. **Calling the provider inside a database transaction.** Reserve, then call, then confirm.
7. **A charge without a way to give it back.** Every crash point needs a retry or a reconciliation.
8. **Overbooking on the average show-up rate.** Measure the bad nights.
9. **Reusing a key for a different request.** Compare and refuse.
10. **Reading idempotency records from a replica.**

---

## Drills

1. A guest books the 1st to the 3rd and another books the 3rd to the 5th, one room. Both succeed. Show why with the nights each takes, and name the bug in an inclusive version.
2. The `UPDATE` changes 2 rows for a 3-night stay. What happened, and why must the 2 changes be undone?
3. Why does a single-unit listing not need counters in PostgreSQL, and what can the exclusion constraint not express?
4. Derive the rule `P(at least C of L show) < r / (r + c)` from the effect of adding one booking.
5. With the section 6 numbers, why does a 90% average show-up rate hide a risk, and what would you change for a holiday weekend?
6. Walk the flow for a crash after the charge with no retry. Who finishes the booking, and what does the guest see?
7. The payment takes 15 minutes and the reservation lasts 10. What does the flow do, and what does the guest experience?
8. A retry arrives with the same key and a different date range. What should the API return, and why is "return the first booking" wrong?

---

## Homework

1. Run `sy58_check.py` on this file. Remove the `ValueError` guard in `reserve` and find the first failing assertion; then change `night < ?` to `night <= ?` and find which fails.
2. Add a price to each night and make `reserve` refuse if the quoted total no longer matches; test it against a reference that sums nights.
3. Replace the lazy reclaim with a sweeper job and check which crash-point rows in section 7 change.
4. Model a correlated shock with three show-up rates and find the limit that keeps the chance of walking a guest under 5%.

---

## Sources

All read 2026-11-27. The model, the code, the overbooking figures and every number marked *assumed* are this lesson's own.

- Airbnb Tech Blog (Jon Chew and Ninad Khisti), *Avoiding double payments in a distributed payments system*, 16 April 2019, medium.com/airbnb-engineering/avoiding-double-payments-in-a-distributed-payments-system-2981f6b070bb. Read in full as extracted text. Source for everything said about Airbnb.
- Stripe, *API reference: Idempotent requests*, docs.stripe.com/api/idempotent_requests. Read the section on idempotency keys.
- PostgreSQL documentation, *Range Types* (section 8.17, including exclusion constraints on ranges), postgresql.org/docs/current/rangetypes.html; *CREATE TABLE* (the `EXCLUDE` clause), postgresql.org/docs/current/sql-createtable.html; *Transaction Isolation* (read committed behaviour for `UPDATE`), postgresql.org/docs/current/transaction-iso.html. Read the passages cited.

## Further reading (not consulted)

Airbnb or Booking.com engineering posts on calendars and search availability; airline reservation and revenue-management literature on fare classes and overbooking; the PostgreSQL explicit locking chapter on deadlocks; the SQLite transaction documentation. None were read, so no claim is made about them.

*Last reviewed: 27 November 2026.*
