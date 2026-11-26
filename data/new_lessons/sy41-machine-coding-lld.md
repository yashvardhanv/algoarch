# Lesson 41 — Machine Coding: Parking Lot, Splitwise & In-Memory DB

> **Priority:** ★★★★☆ — the 60 to 90 minute round where you must ship working, extensible code, not a diagram.
>
> **Study time:** 75 minutes. **Do this after:** Low-Level Design (LLD) & Machine Coding.
>
> **Level:** extended. Worth doing if your loops include a machine coding round.

A machine coding round hands you a prompt like "build a parking lot" and grades what runs at the end: correct
behaviour on the interviewer's cases, a clean place to add the next rule, and no race on shared state. Most people
lose points the same three ways: money in floats, a business rule smeared across five classes, and "thread-safe"
claimed but never tested. This lesson builds the three classic prompts end to end, each with its invariant, its
extension point and a test that proves the rule, all checked by `test/lesson_code/sy41_check.py`.

---

## 1. Mental Model

> **A machine coding solution is one small core that enforces the invariant in exactly one place, plus a
> strategy object for every rule the interviewer is likely to change next.**

What follows from it:

- **Name the invariant first.** Parking lot: a spot holds at most one vehicle. Splitwise: every expense's shares sum
  to its total, so all balances sum to zero. Key-value DB: a read after expiry or rollback never sees the old value.
- **Guard the invariant with one lock, held for the whole check-then-act.** A lock around half of it is a race.
- **Inject what varies:** the fee rule, the split rule, the clock. An injected clock is what makes TTL testable.
- **Money is an integer** number of the smallest unit. Floats cannot represent 0.1 exactly, and the remainder of a
  three-way split has to go to someone by a rule you state.
- **A demo `main()` is not a test.** Ship assertions for the interviewer's cases and one for the concurrency rule.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "vehicles of different sizes", "assign the nearest spot" | a min-heap of free spots per spot size; try sizes smallest first |
| "pricing may change", "weekend rates" | a fee strategy object passed to the lot; integer minutes in, integer cents out |
| "split equally / by exact amounts / by percent" | split functions that return integer shares summing exactly to the total |
| "simplify debts", "fewest payments" | net balance per person, then greedy matching (at most n-1 payments); exact minimum by subset DP for small n |
| "keys expire" | absolute expiry times, lazy check on read, plus a heap-driven sweep |
| "BEGIN / ROLLBACK / COMMIT, nested" | a stack of undo logs, one per open transaction |
| "make it thread-safe" | one lock per aggregate held across check-then-act, and a threaded test that would fail without it |

---

## 3. The Round: Timeline and What Is Graded

| Minutes (of 90) | Do | Output |
|---|---|---|
| 0 to 10 | ask for the operations, the inputs and the exact output format; write two sample cases | a list of operations and their error cases |
| 10 to 20 | entities, enums and the invariant, written as a comment | classes with fields, no logic |
| 20 to 60 | the core, the strategies, errors for bad input | code that passes the sample cases |
| 60 to 75 | the lock and a threaded test; one extension the interviewer asks for | proof the rule holds under concurrency |
| 75 to 90 | a short driver and a walkthrough | a demo you can run in front of them |

Scope rules that save the round: no database, no framework, no REST layer unless asked. Keep state in memory behind
the class, so a later "now persist it" is a new repository class, not a rewrite.

Visual (planned): the three designs side by side, each showing the core class, its strategy objects and the single lock.

---

## 4. Parking Lot

**Requirements.** Spots come in three sizes on several levels. A motorcycle fits any spot, a car fits compact or
large, a truck needs a large spot. Park returns a ticket and a spot; leave returns the fee. Rule for assignment: the
smallest spot size that fits, then the lowest level, then the lowest spot number. Fees: free for the first 15
minutes, then each started hour at the vehicle's hourly rate, each 24-hour block capped.

**Scale, briefly.** A machine coding round grades code, not capacity. The one sizing question is cost per
operation: with a heap per spot size, park and leave are `O(log S)` for `S` spots, against `O(S)` for scanning a list.

**Data model.** `free[size]` is a min-heap of `(level, number)`; `tickets[id]` holds spot, vehicle type, entry time
and plate; `parked[plate]` stops the same plate parking twice.

```python
import heapq, threading
from enum import Enum

class Size(Enum):
    SMALL = 1
    COMPACT = 2
    LARGE = 3

# the smallest spot size each vehicle fits; it may also take any larger spot
VEHICLE_MIN_SPOT = {'motorcycle': Size.SMALL, 'car': Size.COMPACT, 'truck': Size.LARGE}

class LotFull(Exception):
    pass

class ParkingLot:
    """Assignment: smallest fitting spot size, then lowest (level, number).
    Invariant: a spot is in exactly one place, a free heap or one ticket. One lock guards both."""
    def __init__(self, layout, fee_policy):
        self.size_of = dict(layout)                        # (level, number) -> Size
        self.free = {s: [] for s in Size}
        for spot, size in layout.items():
            self.free[size].append(spot)
        for h in self.free.values():
            heapq.heapify(h)
        self.tickets, self.parked, self.next_ticket = {}, {}, 1
        self.fee_policy = fee_policy
        self.lock = threading.Lock()

    def park(self, plate, vehicle_type, now):
        with self.lock:                                    # check (any free spot?) and act (take it) together
            if plate in self.parked:
                raise ValueError('already parked: ' + plate)
            need = VEHICLE_MIN_SPOT[vehicle_type]
            for size in Size:                              # SMALL, COMPACT, LARGE: smallest first
                if size.value >= need.value and self.free[size]:
                    spot = heapq.heappop(self.free[size])
                    break
            else:
                raise LotFull(vehicle_type)
            tid = self.next_ticket
            self.next_ticket += 1
            self.tickets[tid] = (spot, vehicle_type, now, plate)
            self.parked[plate] = tid
            return tid, spot

    def leave(self, tid, now):
        with self.lock:
            spot, vehicle_type, entered, plate = self.tickets.pop(tid)   # KeyError: unknown or reused ticket
            del self.parked[plate]
            heapq.heappush(self.free[self.size_of[spot]], spot)
        return self.fee_policy.fee(vehicle_type, entered, now)
```

The fee rule is a separate object, so "weekend rates" or "per-minute billing" is a new class and the lot does not
change:

```python
class HourlyFee:
    """Integer minutes in, integer cents out. Free up to `grace` minutes; otherwise every started hour is
    charged, and each 24-hour block costs at most `daily_cap`."""
    def __init__(self, rates, grace=15, daily_cap=None):
        self.rates, self.grace, self.daily_cap = rates, grace, daily_cap

    def fee(self, vehicle_type, entered, left):
        minutes = left - entered
        if minutes < 0:
            raise ValueError('left before entering')
        if minutes <= self.grace:
            return 0
        rate = self.rates[vehicle_type]
        days, rest = divmod(minutes, 24 * 60)
        started_hours = -(-rest // 60)                     # ceiling division
        cap = self.daily_cap
        full_day = 24 * rate if cap is None else min(24 * rate, cap)
        last_day = started_hours * rate if cap is None else min(started_hours * rate, cap)
        return days * full_day + last_day
```

Worked case: a car at 200 cents an hour with a 1,500 cent daily cap, parked for 26 hours 10 minutes. One full day
costs `min(24 x 200, 1,500) = 1,500`; the remaining 2 hours 10 minutes start 3 hours, `3 x 200 = 600`; total 2,100.
A tempting shortcut charges `days x daily_cap` for full days, which overcharges whenever the cap is above 24 hours of
the rate; the check catches that by recomputing every fee minute by minute.

**Concurrency rule, tested.** With 20 spots and 50 threads parking at once, exactly 20 succeed, 30 get `LotFull`, and
no spot appears on two tickets. The check runs that with a barrier so the threads start together.

---

## 5. Splitwise: Shares, Balances, Simplification

**Requirements.** Add an expense paid by one person and split equally, by exact amounts or by percent; show who owes
whom; settle up in few payments.

**Shares must sum to the total, in integer cents.** Equal split of 1,000 among three is 334, 333, 333: the remainder
goes to the first people in the list, a rule you say out loud. Percent split uses largest remainder.

```python
def split_equal(total, users):
    q, r = divmod(total, len(users))
    return {u: q + (1 if i < r else 0) for i, u in enumerate(users)}

def split_exact(total, shares):
    if sum(shares.values()) != total:
        raise ValueError('shares do not add up to the total')
    return dict(shares)

def split_percent(total, percents):
    """Integer percents summing to 100. Floor every share, then give the leftover cents to the largest
    fractional parts (ties to the earlier user)."""
    if sum(percents.values()) != 100:
        raise ValueError('percents must sum to 100')
    users = list(percents)
    raw = {u: total * percents[u] for u in users}         # in hundredths of a cent
    share = {u: raw[u] // 100 for u in users}
    left = total - sum(share.values())
    for u in sorted(users, key=lambda u: (-(raw[u] % 100), users.index(u)))[:left]:
        share[u] += 1
    return share
```

**Keep a net balance per person, not a pairwise matrix.** Positive means the group owes you. Every expense adds the
total to the payer and subtracts each share, so the sum of all balances stays zero; that sum is the invariant to assert.

```python
class Ledger:
    def __init__(self):
        self.net = {}                                      # user -> cents; positive = is owed
        self.lock = threading.Lock()

    def add_expense(self, payer, total, shares):
        if sum(shares.values()) != total:
            raise ValueError('shares do not add up to the total')
        with self.lock:
            self.net[payer] = self.net.get(payer, 0) + total
            for u, s in shares.items():
                self.net[u] = self.net.get(u, 0) - s

    def record_payment(self, frm, to, amount):
        with self.lock:
            self.net[frm] = self.net.get(frm, 0) + amount
            self.net[to] = self.net.get(to, 0) - amount
```

**Simplification.** Splitwise's help article says its "simplify debts" setting reduces the number of payments and
never changes anyone's total balance. Only the net balances matter, so any set of payments that zeroes every balance
is a valid settlement. The greedy one: the largest debtor pays the largest creditor as much as one of them needs.

```python
def simplify(net):
    """Greedy settlement: each payment zeroes at least one person, so at most (non-zero people - 1) payments.
    Not always the minimum."""
    assert sum(net.values()) == 0, 'balances must sum to zero'
    creditors = [(-v, u) for u, v in net.items() if v > 0]
    debtors = [(v, u) for u, v in net.items() if v < 0]
    heapq.heapify(creditors)
    heapq.heapify(debtors)
    payments = []
    while creditors:
        c, cu = heapq.heappop(creditors)
        d, du = heapq.heappop(debtors)
        amount = min(-c, -d)
        payments.append((du, cu, amount))
        if -c > amount:
            heapq.heappush(creditors, (c + amount, cu))
        if -d > amount:
            heapq.heappush(debtors, (d + amount, du))
    return payments
```

Why at most `n - 1`: each payment brings at least one person to zero, and the last payment zeroes two. Why not
minimal: take balances Asha -40, Ben -30, Chen +20, Dev +20, Esha +30. Greedy has Asha pay Esha 30 first and needs
**four** payments. The minimum is **three**: Ben pays Esha 30, Asha pays Chen 20 and Dev 20, because {Ben, Esha} is a
group whose balances already sum to zero. In general a group of `k` people summing to zero settles in `k - 1`
payments, so the minimum is `n` minus the largest number of disjoint zero-sum groups. Finding that is a subset
problem; for a trip-sized group this DP is exact:

```python
def min_payments(net):
    """Exact minimum number of payments: n - (most disjoint zero-sum groups). O(2^n * n), fine for n <= ~18."""
    vals = [v for v in net.values() if v != 0]
    n = len(vals)
    total = [0] * (1 << n)
    groups = [0] * (1 << n)          # most zero-sum groups that partition the people in mask (when total is 0)
    for mask in range(1, 1 << n):
        low = mask & -mask
        total[mask] = total[mask ^ low] + vals[low.bit_length() - 1]
        groups[mask] = max(groups[mask ^ (1 << i)] for i in range(n) if mask >> i & 1) + (total[mask] == 0)
    return n - groups[(1 << n) - 1]
```

In the round, ship `simplify`, state its bound and the counterexample, and offer the DP if asked for the true
minimum. The check compares `min_payments` with an enumeration of every partition of the group, and confirms greedy
payments always zero every balance and never exceed `n - 1`.

---

## 6. In-Memory Key-Value DB with TTL and Transactions

**Requirements.** `set(key, value, ttl=None)`, `get`, `delete`, `incr`; keys can expire; `begin`, `commit` and
`rollback`, nested. Redis is the reference people have in mind, so know where this design matches it and where it
does not.

- **Expiry.** Store the absolute expiry time. Redis's `EXPIRE` page describes two mechanisms: a key is expired
  passively when someone reads it, and periodically Redis tests random keys that have a TTL and deletes the expired
  ones. Here the read check is the same; the sweep uses a heap of expiry times instead of random sampling, so it
  touches only keys that are due. Like Redis, a plain `set` clears the TTL and `incr` keeps it.
- **Transactions.** Redis `MULTI`/`EXEC` queues commands and runs them without interleaving, and its docs say Redis
  does **not** support rollback. The usual machine coding prompt asks for real `ROLLBACK`, which means an undo log:
  the first time a transaction touches a key, save the entry it replaced.

```python
class KVStore:
    """Single-session store. Every call is atomic under one lock. Time comes from an injected clock."""
    def __init__(self, clock):
        self.clock = clock
        self.data = {}            # key -> (value, expire_at or None)
        self.expiries = []        # heap of (expire_at, key); may hold stale entries
        self.undo = []            # one dict per open transaction: key -> entry it replaced (None = absent)
        self.lock = threading.Lock()

    def _entry(self, key):
        e = self.data.get(key)
        if e is None or (e[1] is not None and e[1] <= self.clock()):
            return None           # passive expiry: an expired entry reads as absent
        return e

    def _put(self, key, entry):
        if self.undo and key not in self.undo[-1]:
            self.undo[-1][key] = self.data.get(key)        # first touch at this level: remember what was there
        if entry is None:
            self.data.pop(key, None)
        else:
            self.data[key] = entry
            if entry[1] is not None:
                heapq.heappush(self.expiries, (entry[1], key))

    def set(self, key, value, ttl=None):
        with self.lock:
            self._put(key, (value, None if ttl is None else self.clock() + ttl))

    def get(self, key):
        with self.lock:
            e = self._entry(key)
            return None if e is None else e[0]

    def delete(self, key):
        with self.lock:
            existed = self._entry(key) is not None
            self._put(key, None)
            return existed

    def incr(self, key, by=1):
        with self.lock:                                    # read, add and write as one step
            e = self._entry(key)
            value = (0 if e is None else e[0]) + by
            self._put(key, (value, None if e is None else e[1]))
            return value

    def ttl(self, key):
        """Seconds left; -1 if the key has no expiry; None if it does not exist."""
        with self.lock:
            e = self._entry(key)
            if e is None:
                return None
            return -1 if e[1] is None else e[1] - self.clock()

    def begin(self):
        with self.lock:
            self.undo.append({})

    def rollback(self):
        with self.lock:
            if not self.undo:
                raise RuntimeError('no transaction')
            for key, old in self.undo.pop().items():
                if old is None:
                    self.data.pop(key, None)
                else:
                    self.data[key] = old
                    if old[1] is not None:
                        heapq.heappush(self.expiries, (old[1], key))

    def commit(self):
        with self.lock:
            if not self.undo:
                raise RuntimeError('no transaction')
            top = self.undo.pop()
            if self.undo:                                  # nested: the parent must still be able to undo these
                for key, old in top.items():
                    self.undo[-1].setdefault(key, old)

    def sweep(self, limit=None):
        """Active expiry: delete due keys, skipping heap entries made stale by a later write."""
        with self.lock:
            now, removed = self.clock(), 0
            while self.expiries and self.expiries[0][0] <= now and (limit is None or removed < limit):
                exp, key = heapq.heappop(self.expiries)
                e = self.data.get(key)
                if e is not None and e[1] == exp:
                    del self.data[key]
                    removed += 1
            return removed
```

Three details interviewers probe:

1. **Nested commit merges into the parent with `setdefault`.** The parent keeps its own, older saved entry; if you
   overwrite it, a later outer rollback restores the inner value instead of the original.
2. **Rollback after expiry.** Restoring an entry whose time has passed is harmless: it reads as absent, and its heap
   entry is pushed again so the sweep can delete it.
3. **One transaction stack means one session.** That is what the prompt usually asks for. Several clients with
   their own transactions need per-session undo logs and a rule for conflicting writes (Redis's answer is `WATCH`:
   the transaction aborts if a watched key changed); say so rather than pretend the lock gives isolation.

The check replays thousands of random operations, clock moves and nested transactions against a reference that
copies the whole dictionary on every `begin`, and runs eight threads of `incr` that must add up exactly.

---

## 7. Failure Modes

| Failure | Effect | Fix |
|---|---|---|
| check-then-act outside the lock | two cars on one spot; oversold anything | hold one lock across the whole check and the write |
| float money | shares that do not sum to the total; `0.1 + 0.2` style drift | integer cents and a stated remainder rule |
| fee rule inside `ParkingLot.leave` | every pricing change edits the core class | a fee strategy passed in |
| `time.time()` called inside the store | TTL cannot be tested without sleeping | inject the clock |
| expired keys only removed on read | memory grows with keys nobody reads again | a sweep (heap here; random sampling in Redis) |
| nested commit overwrites the parent's undo entry | outer rollback restores the wrong value | `setdefault` when merging |
| greedy settlement presented as "minimum" | wrong claim under questioning | state the `n - 1` bound and the counterexample |

---

## 8. What Real Systems Document

- **Splitwise** (help article, read 2026-11-26): "simplify debts" restructures who pays whom inside a group to reduce
  the number of payments, never changes anyone's total balance, re-runs when an expense or payment is added, and
  treats each currency separately. The article does not describe the algorithm, so nothing here claims to be theirs.
- **Redis** (`EXPIRE` and transactions pages, read 2026-11-26): passive plus periodic sampled expiry; expiry stored as
  absolute Unix time, so clock changes matter; `SET` clears a TTL while `INCR` keeps it; `MULTI`/`EXEC` without
  rollback; `WATCH` for optimistic check-and-set.
- **System Design Primer** parking lot solution (source read 2026-11-26): models vehicle sizes, levels and spots, and
  lets a bus take several large spots, but leaves the spot search as an unimplemented stub, which is exactly the part
  a machine coding round grades.

---

## 9. Pitfalls Checklist

1. **No stated invariant,** so nothing tells you where the lock goes.
2. **Locking the write but not the check.** The race is between "is a spot free" and "take it".
3. **Floats for money,** or an equal split whose shares do not sum to the total.
4. **A god class:** pricing, assignment and printing in one method, so the first extension is a rewrite.
5. **Reading the system clock inside the logic,** then trying to test TTL with `sleep`.
6. **Claiming greedy debt simplification is optimal.** It is bounded by `n - 1`, not minimal.
7. **Nested transactions that forget the outer undo log** on inner commit.
8. **No threaded test,** so "thread-safe" is an unproven claim.

---

## Drills

1. Why does `ParkingLot.park` hold the lock across both the free-spot check and the `heappop`? Describe the bad
   interleaving without it.
2. A truck arrives when only compact spots are free. What does `park` do, and what would you change to support a
   bus that takes several adjacent large spots?
3. Compute the fee for a car at 200 cents an hour, 1,500 cent daily cap, 15 minute grace, parked 49 hours 1 minute.
4. Split 1,001 cents as 33%, 33%, 34%. Which user gets the leftover cent, and why?
5. Show that `simplify` makes at most `n - 1` payments, and give balances where it makes more than the minimum.
6. Why is the minimum number of payments `n` minus the most disjoint zero-sum groups?
7. Inside a nested transaction you `set` a key that the outer transaction already changed, then commit the inner one
   and roll back the outer one. Trace the undo logs.
8. Why can rollback safely restore an entry whose expiry time has already passed?

---

## Homework

1. Add a `Bus` that needs five adjacent large spots on one level; keep `park` `O(log S)` per level if you can, and
   test it against a scan.
2. Add a `WeekendFee` strategy without editing `ParkingLot`; test it with fixed timestamps.
3. Extend `Ledger` to several currencies kept separately, as Splitwise's article describes.
4. Give `KVStore` per-session transactions with `WATCH`-style abort on conflict, and write a threaded test of two
   sessions that conflict.
5. Solve LeetCode 465 (Optimal Account Balancing) with `min_payments`; then solve LeetCode 1797 (Design
   Authentication Manager), which is TTL with an injected clock.
6. Time-box a full 90 minute mock of one prompt here with the timeline in section 3, then compare your code with
   this lesson's.

---

## Sources

All read 2026-11-26.

- Splitwise Help Center, *What is Simplify Debts?*, kb.splitwise.com/balances-and-expenses/what-is-simplify-debts (read
  through a summarising fetch). Source for the behaviour of the setting: fewer payments, totals unchanged, re-run on new
  expenses, per-currency.
- Redis, *EXPIRE*, redis.io/docs/latest/commands/expire/. Source for passive and periodic expiry, absolute expiry
  times, which commands clear or keep a TTL, and the replica `DEL` behaviour.
- Redis, *Transactions*, redis.io/docs/latest/develop/using-commands/transactions/. Source for `MULTI`/`EXEC`
  isolation, errors inside a transaction, no rollback, and `WATCH`.
- Python documentation, *threading*, docs.python.org/3/library/threading.html (read through a summarising fetch).
  Source for `Lock` versus `RLock` and locks as context managers.
- System Design Primer, `solutions/object_oriented_design/parking_lot/parking_lot.py`, github.com/donnemartin/system-design-primer
  (raw file read). Source for its class layout and the unimplemented spot search.

## Further reading (not consulted)

The rest of the System Design Primer's object-oriented design exercises; Splitwise engineering posts, if any; the
Redis source for active expiry (`expire.c`). None were read for this revision.

*Last reviewed: 2026-11-26.*
