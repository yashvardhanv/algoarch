# Lesson 73 — Case Study: Price Tracker and Alerts

> **Priority:** ★★☆☆☆ (proposed; the curriculum data holds the final rating) — it looks like a crawler question but is mostly about deciding how often to look, not mistaking a scraping glitch for a price drop, and telling the right people exactly once.
>
> **Study time:** 60 minutes. **Do this after:** Web Crawler; Distributed Task Scheduler; Notification System; Scaling Patterns I: Reads, Writes and Contention.
>
> **Level:** extended.

Users paste a product link and a target price; the service watches the page and emails or pushes when the price falls to the target. The data is simple. The difficulty is a budget of fetches that cannot cover everything as often as users would like, a source (a web page) that sometimes lies by accident, and an alert rule that must neither spam nor miss. The code is checked in `test/lesson_code/sy73_check.py`; capacity figures come from `capacity_check_i.py`. Crawling mechanics are not re-taught (see Web Crawler), nor delivery of notifications (see Notification System).

---

## 1. Mental Model

> **Every fetch is a purchase from a fixed budget, so the design question is where to spend it. Every price you read is a noisy measurement, so the design question is when to believe it. Every alert is a promise to a person, so the design question is when to stop repeating it.**

- **Spend polls where staleness costs most.** Cost grows with the number of watchers and with how often the price changes; the best interval shrinks only with the square root of that weight (section 5), so a product with 100 times the weight gets 10 times the polling, not 100 times.
- **A scraped price is a claim to confirm, not a fact.** A single odd reading (a parse error, a "0", a coupon banner) should not page anyone (section 6).
- **An alert is a state machine, not an event.** Fire once when the price crosses the target, re-arm only when it recovers by a margin (section 6).
- **Index crossings, do not scan watchers.** A price drop affects the alerts whose thresholds lie in a narrow band, and a sorted structure finds that band without touching the rest (section 7).
- **Store changes, not polls.** A price history is a step function; keep its steps (section 8).

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "check prices regularly for millions of products" | a polling budget split by weight, intervals bounded above and below (section 5) |
| "don't send false alerts" | confirmation of a new price before it is believed; ignore failed parses (section 6) |
| "don't spam when the price flaps around the target" | fire once, re-arm with hysteresis (section 6) |
| "notify everyone whose target is met" | per-product sorted thresholds; query the crossed band (section 7) |
| "show the price history and the lowest in 90 days" | change-only log with the carried-in price (section 8) |
| "what if the site blocks us" | politeness and robots rules, official feeds where they exist; see Web Crawler |
| "cheap check whether the page changed" | conditional requests (validators and 304); the page may still differ in ways that do not matter |

---

## 3. Requirements and Capacity

**Functional.** Add a product by link; set a target price; see the current price and history; get notified (email, push) when the price reaches the target; stop tracking.

**Non-functional.** Prices are as fresh as the budget allows, with an explicit upper bound on staleness; an alert fires once per dip; a bad scrape does not alert; fetching respects each site's rules; the system continues when a site is down or slow.

**Capacity.** Every input is an assumption chosen to size the design (not data about any service); outputs are computed in `capacity_check_i.py`.

| Quantity | Assumption or derivation | Result |
|---|---|---|
| Tracked products | assumed | 20 million |
| Poll budget | assumed | 100 million fetches per day, about 1,157 per second |
| Average interval | 20 million products / 100 million per day | 4.8 hours |
| Feasible range | between one poll per 24 hours each and one per 15 minutes each | 20 million to 1.92 billion polls per day, so the budget is inside it |
| Price changes | assumed 3 percent of products change price on a given day | 600,000 per day, about 6.9 per second |
| History: every poll | 100 million x 16 bytes | 1.6 GB per day |
| History: changes only | 600,000 x 16 bytes | 9.6 MB per day, 167 times smaller |
| Alerts | assumed 3 per product | 60 million |
| Alert notifications | 600,000 changes x 3 watchers x an assumed 10 percent crossing | about 180,000 per day, about 2.1 per second |
| Hot product | 200,000 watchers, targets spread evenly from 50 to 100 percent of the old price, a 5 percent drop | 20,000 alerts crossed; a full scan touches 200,000 |

What dominates: the fetch budget, not storage or notifications. Notifications are two per second; fetches are over a thousand per second and each is an outbound request to a third party.

---

## 4. API and Data Model

```
POST   /trackers          {url, target_price, currency}      -> {tracker_id}
GET    /trackers/{id}     -> current price, state, history summary
DELETE /trackers/{id}
GET    /products/{id}/history?from&to
```

| Store | Key | Notes |
|---|---|---|
| products | canonical URL hash | URL after canonicalisation (see Web Crawler), site adapter, last validators |
| observations | transient | raw scraped price with fetch time; short retention |
| confirmed price | product id | output of the observation filter |
| history | (product id, time) | one row per confirmed change |
| alerts | (product id, user id) | threshold, armed flag, last fired time |
| schedule | product id | next poll time, derived from the interval allocation |

Prices are integers in the smallest currency unit (cents), never floats, in every comparison below.

---

## 5. Deep Dive 1: Where to Spend the Polls

Suppose product `i` is polled every `I_i` hours. If its price changes at a random moment, the expected delay before the change is noticed is `I_i / 2`. Each such delay hurts in proportion to the number of watchers and to how often the price changes, so give product `i` a weight `w_i` (watchers times changes per day, an assumption you can measure) and minimise the total expected delay cost `sum(w_i * I_i / 2)` while the total poll rate `sum(1 / I_i)` equals the budget. Setting the derivative to zero (a Lagrange multiplier) gives `I_i` proportional to `1 / sqrt(w_i)`. The derivation is the lesson's own, under the stated model; it is not taken from any source.

```python
import math, bisect


def intervals(weights, budget, lo, hi):
    """Polling interval per product (hours) that minimises sum(w * I / 2) when the total poll rate is `budget` per hour
    and each interval stays in [lo, hi]. The optimum is I = clamp(K / sqrt(w)); K is found by bisection."""
    n = len(weights)
    assert n / hi <= budget <= n / lo, 'the budget cannot be spent within the interval bounds'
    roots = [math.sqrt(w) for w in weights]

    def rate(k):
        return sum(1 / min(hi, max(lo, k / r)) for r in roots)

    k_lo, k_hi = lo * min(roots), hi * max(roots)            # at k_lo every interval is lo, at k_hi every interval is hi
    for _ in range(200):
        mid = (k_lo + k_hi) / 2
        if rate(mid) > budget:                               # polling too often: raise K, which lengthens every interval
            k_lo = mid
        else:
            k_hi = mid
    k = (k_lo + k_hi) / 2
    return [min(hi, max(lo, k / r)) for r in roots]


def stale_cost(weights, ivs):
    """Expected delay before a change is noticed is I / 2; weight it by watchers x change rate."""
    return sum(w * i / 2 for w, i in zip(weights, ivs))
```

Worked example (budget one poll per hour in total, four products with weights 1, 4, 16 and 100): the intervals are 17, 8.5, 4.25 and 1.7 hours, the cost is 144.5, and polling all four equally every 4 hours (the same budget) costs 242, which is about 67 percent more (equivalently, the optimum is about 40 percent cheaper). The check pins those numbers, and then tests optimality on 120 random instances: 400 random feasible allocations per instance (same total rate, inside the bounds) never beat it, and moving a small amount of poll rate from any product to any other never helps. It also shows that equal intervals and intervals proportional to `1 / w` cost more on a five-product instance, so the square root matters: dividing by `w` over-polls the hot product and starves the rest.

**Bounds.** Intervals are clamped to a minimum (do not hammer a site; one poll per 15 minutes at most) and a maximum (every product is looked at at least daily). With the clamps the optimum is still `clamp(K / sqrt(w))`, with K chosen so the total rate equals the budget, which is what the bisection does. The check includes an instance where both clamps bind: weights 1, 1,000 and 1,000,000, budget 3 polls per hour, bounds 0.5 and 24 hours gives intervals 24, 1.043 and 0.5 hours, the quietest product at the maximum and the hottest at the minimum. The function refuses a budget that cannot be spent inside the bounds.

Visual (planned): intervals against the square root of the weight, with the two clamps flattening the ends.

**Honest limits.** The model assumes the price changes at a random moment and that all staleness is equally costly. In practice sales are scheduled (a flash sale starts at noon), so a good scheduler also uses what it knows: poll more near expected events. It also assumes weights are known; for a new product use a default and learn.

**Being a good citizen.** A site can refuse automated access. RFC 9309 (read on 27 November 2026) says the rules in robots.txt "are not a form of access authorization", requires a crawler to assume complete disallow if the file cannot be reached because of server errors in the 500 range, and says a cached copy should not be used for more than 24 hours unless the file is unreachable. Conditional requests (RFC 9110, `If-None-Match` and the 304 response) let a server answer "unchanged" without sending the page, which cuts transfer cost but not the request count. Per-host rate limits, identification and fallbacks belong to Web Crawler; whether scraping a particular site is allowed by its terms is a legal question this lesson does not answer. Where a retailer offers a feed or an API, prefer it.

---

## 6. Deep Dive 2: Believing a Price, Alerting Once

A scrape produces a number or a failure. Failures (a parse that returns nothing, a zero) must be ignored. Successes can still be wrong: a mislabelled "was" price, a banner with a coupon, a page in the middle of an update. The filter below believes a changed price only when it has been observed several times in a row, and treats a return to the known price as evidence that the odd reading was noise. The alert is a two-state machine.

```python
class Tracker:
    """Turns raw scraped observations into confirmed prices. A new price must be seen `confirm` times in a row."""
    def __init__(self, confirm=2):
        self.confirm, self.price, self.pending, self.count = confirm, None, None, 0

    def observe(self, p):
        if p is None or p <= 0:                      # a failed parse is not a price: it neither confirms nor resets
            return None
        if self.price is None:
            self.price = p
            return p
        if p == self.price:
            self.pending, self.count = None, 0       # back to the known price: forget the suspicious one
            return None
        self.count = self.count + 1 if p == self.pending else 1
        self.pending = p
        if self.count >= self.confirm:
            self.price, self.pending, self.count = p, None, 0
            return p
        return None


def rearm_level(threshold, pct):
    return threshold + (threshold * pct + 99) // 100                 # integer cents, rounded up


class Alert:
    """The definition: fire once when the confirmed price is at or below the target; re-arm when it climbs back by `pct` percent."""
    def __init__(self, threshold, pct=5):
        assert pct >= 1, 'with no margin a price sitting on the target would flap'
        self.thr = threshold
        self.rearm_at = rearm_level(threshold, pct)
        self.armed = True

    def on_price(self, p):
        if self.armed and p <= self.thr:
            self.armed = False
            return True
        if not self.armed and p >= self.rearm_at:
            self.armed = True
        return False
```

**The filter** is checked against a direct definition (after a first valid price, a new price is confirmed once the last `confirm` valid observations all agree on it) over 1,500 random observation sequences with `confirm` of 1, 2 and 3, including invalid readings. Hand cases pin the rest: a one-sample glitch (100, 1, 100) is ignored; a flapping one (100, 1, 100, 1, 100) is ignored; zeros and missing values neither confirm nor reset a pending change; going back to the known price clears a pending one.

**The cost of confirming** is one extra poll of delay, and it has an honest limit. A price that changes at every poll never repeats, so it is never confirmed (the check pins 100, 90, 95, 85, 92, 88 giving only the baseline). That is the opposite of what you want for the hot, volatile products, which this section later says suffer least. A tolerance (prices within a small percentage count as the same, homework 3) or a confirm count of 1 for sources you trust is the usual answer.

**The delay itself:** a real drop from 102.00 to 95.00 is confirmed at the second poll, so the alert is one poll interval later than a naive one. That is the trade, and it is why the interval allocation matters: heavily watched products have short intervals, so the delay is short where it hurts most.

**The alert** fires when the confirmed price is at or below the target, then disarms until the price climbs back to the re-arm level, here 5 percent above the target (rounded up in whole cents). With a target of 100.00: prices 120.00, 99.00, 98.00, 101.00, 99.00 fire once (at 99.00); 101.00 does not re-arm because the level is 105.00. Prices 99.00, 106.00, 99.00 fire twice. A price of exactly 100.00 fires; 100.01 does not; exactly 105.00 re-arms; 104.99 does not. The check compares the machine with a second definition written as a scan (fire when at or below the target and, since the last firing, a price at or above the re-arm level has been seen) over 2,000 random sequences and four re-arm percentages (1, 3, 5 and 10). A margin of 0 is refused by the class: with the re-arm level equal to the target, a price sitting on the target would flap.

**Through the whole pipeline.** With the series 102.00, 102.00, 1.00, 102.00, 102.00, 95.00, 95.00, 95.00 and a target of 100.00, an alert fed the raw readings fires on the 1.00 glitch and then, never re-armed because the price stays below 105.00, stays silent for the real drop at 95.00. The filtered pipeline ignores the glitch and fires once, with 95.00, at the second reading of the real drop. That is two defects in one series, a false alert and a missed one, both from the unfiltered reading.

**Product decisions.** A target set while the price is already at or below it fires at once (`PriceBook.add` returns True; `Alert` given the current price does the same); the alternative is to wait for the next crossing, which silently drops the alert if the price never rises. Not decided by the code: whether to alert on a drop to any lower price (a "percent off" alert); currency conversion; out-of-stock products whose price vanishes (the filter ignores them, which is a choice).

---

## 7. Deep Dive 3: Finding the Alerts a Price Change Affects

For a popular product, hundreds of thousands of users have a target. When the confirmed price falls from `old` to `new`, the alerts that become true are exactly those with a target `t` where `new <= t < old`: targets at or above `old` were already satisfied, and targets below `new` are still not met. But the alert is a two-state machine (section 6), and the other half of its life, re-arming, is a **rise**: a disarmed alert comes back when the price climbs to its re-arm level. An index that is consulted only on drops never sees rises, so alerts would fire once in their lives. The design therefore keeps two sorted indexes per product, and both bands are two binary searches.

- **Armed alerts**, keyed by target. A drop from `old` to `new` fires the armed band `[new, old)` and moves those alerts to the other index.
- **Disarmed alerts**, keyed by re-arm level. A rise from `old` to `new` re-arms the band `old < level <= new`, moving them back.

```python
class ThresholdIndex:
    """Entries sorted by (key in cents, user id). band(lo, hi) is every entry with lo <= key < hi, found by two binary searches."""
    def __init__(self):
        self.t = []

    def add(self, key, uid):
        bisect.insort(self.t, (key, uid))

    def remove(self, key, uid):
        i = bisect.bisect_left(self.t, (key, uid))
        if i < len(self.t) and self.t[i] == (key, uid):
            del self.t[i]

    def band(self, lo, hi):
        if lo >= hi:
            return []
        i = bisect.bisect_left(self.t, (lo, -1))
        j = bisect.bisect_left(self.t, (hi, -1))
        return [uid for _, uid in self.t[i:j]]

    def crossed(self, old, new):
        """A drop from old to new crosses exactly the targets t with new <= t < old: not met before, met now."""
        return self.band(new, old)


class PriceBook:
    """All alerts of one product. An armed alert sits in `armed`, keyed by its target; a disarmed one sits in `disarmed`,
    keyed by its re-arm level. A drop fires the armed band it crosses; a rise re-arms the disarmed band it climbs through."""
    def __init__(self, pct=5):
        self.pct, self.price = pct, None
        self.armed, self.disarmed, self.alerts = ThresholdIndex(), ThresholdIndex(), {}   # alerts: uid -> (target, re-arm level)

    def add(self, uid, thr):
        """Returns True if the alert fires at once because the price is already at or below the target."""
        assert uid not in self.alerts
        rearm = rearm_level(thr, self.pct)
        self.alerts[uid] = (thr, rearm)
        if self.price is not None and self.price <= thr:
            self.disarmed.add(rearm, uid)
            return True
        self.armed.add(thr, uid)
        return False

    def remove(self, uid):
        if uid in self.alerts:
            thr, rearm = self.alerts.pop(uid)
            self.armed.remove(thr, uid)
            self.disarmed.remove(rearm, uid)

    def on_change(self, new):
        """Called with each confirmed price change. Returns the users to notify."""
        old = float('inf') if self.price is None else self.price
        self.price = new
        fired = self.armed.crossed(old, new)
        for uid in fired:
            thr, rearm = self.alerts[uid]
            self.armed.remove(thr, uid)
            self.disarmed.add(rearm, uid)
        for uid in self.disarmed.band(old + 1, new + 1):             # rise: old < re-arm level <= new
            thr, rearm = self.alerts[uid]
            self.disarmed.remove(rearm, uid)
            self.armed.add(thr, uid)
        return fired
```

`Alert` stays as the definition of one alert's behaviour; `PriceBook` is the same behaviour for all of a product's alerts at once. The check holds them to each other end to end. It feeds 1,500 random scripts of raw observations (including failed parses and glitches) and alert creations and deletions through `Tracker` and `PriceBook`, and compares every firing, with its position, against one independent `Alert` per user fed the confirmed prices, so neither the index nor the filter can be wrong without the comparison noticing. The lesson's earlier draft, where the index passed only drops to the alert, is the failure this guards against: with a target of 100.00 and confirmed prices 120.00, 99.00, 110.00, 99.00, the machine alone fires twice but an index-driven pipeline that never sees the rise fires once. The check pins the two-alert answer. It also pins an alert created while the price is already below its target (fires at once), an alert created before any price is known, deletion from whichever index holds the alert, and that every live alert is in exactly one index.

The index alone is compared with a scan of its rows over 300 random indexes of up to 40 entries with keys in a narrow range (80 to 120, so ties are everywhere), including random removals and 30 random `(old, new)` pairs each. Edge cases fixed by hand tests: `crossed(100, 90)` excludes the alert at 100 (met before) and includes 90; no drop returns nothing; removing twice is harmless; user ids 9 and 10 at one target come back in numeric order. In the sizing table the hot product with 200,000 targets spread evenly over half its price loses 5 percent: the band holds 20,000 alerts instead of the 200,000 a scan would touch, and the disarmed index is touched only by rises.

This is the same structure as a sorted set with a score-range query; see Real-Time Gaming Leaderboard for the Redis form of that. At the scale in the table it fits in memory per product, and products can be sharded by product id.

---

## 8. Deep Dive 4: The Price History

A price over time is a step function: constant between changes. Storing every poll writes the same number millions of times (the table: 1.6 GB a day against 9.6 MB). Storing only changes is small, but it makes "price at time t" and "lowest in a window" slightly subtle.

```python
class History:
    """Store a price only when it changes; the price at any time is the last change at or before it."""
    def __init__(self):
        self.ts, self.ps, self.last_seen = [], [], None

    def record(self, t, price):
        if self.last_seen is not None and t < self.last_seen:
            raise ValueError('observation older than the last one stored')
        self.last_seen = t
        if self.ps and self.ps[-1] == price:
            return False
        self.ts.append(t)
        self.ps.append(price)
        return True

    def at(self, t):
        i = bisect.bisect_right(self.ts, t) - 1
        return self.ps[i] if i >= 0 else None

    def lowest(self, t0, t1):
        """Lowest price in effect at any moment of [t0, t1]: the price carried in at t0 counts, not only the changes inside."""
        cands = [self.at(t0)] + self.ps[bisect.bisect_right(self.ts, t0):bisect.bisect_right(self.ts, t1)]
        cands = [c for c in cands if c is not None]
        return min(cands) if cands else None
```

The `History` class records a change only when the price differs from the last one, raises an error for an observation older than the last one stored (an explicit check, which `python -O` does not strip; equal timestamps are accepted), and answers `at(t)` with a binary search for the last change at or before `t`. `lowest(t0, t1)` is where bugs live: the lowest price in a window must include the price **carried in** at `t0`, not just the changes inside the window. If a product dropped to 90 a month ago and has not changed since, the lowest price over the last week is 90 though there is no change row in that week. The check compares `at` and `lowest` against a full per-tick series on 400 random histories with 40 random windows each, including windows that contain no change.

Chart downsampling (one point per day, or the minimum and maximum per bucket) belongs on top of this log, not in it; the log stays exact so alerts and statistics can be recomputed.

---

## 9. Failure Modes

| What breaks | What happens | Mitigation |
|---|---|---|
| Parse failure returns 0 or nothing | false "price dropped to 0" | validity gate in the filter |
| One-sample glitch | false alert | confirm count |
| Site redesign | every parse fails or returns another number | adapter versioning, alarm on a spike in parse failures per site |
| Price flaps around the target | alert storm | re-arm margin |
| Target set above the current price | immediate alert or never | explicit product rule |
| Site blocks or rate-limits | prices go stale | back off per host; lengthen interval; use feeds |
| Budget cut | intervals lengthen for everyone | the allocation preserves the order of importance; set the maximum interval |
| Burst of changes in a hot product | notification spike | per-user rate limits, batching (see Notification System) |
| History query ignores carried-in price | wrong lowest price | include `at(t0)` (tested) |
| Clock skew between fetchers | out-of-order observations | stamp readings with the time the result is stored, on one clock per product; `History` raises on an older stamp and the caller logs it and re-queues the poll rather than silently dropping a real price (tested) |
| Index sees only drops | alerts fire once in their lives | second index for re-arming; end-to-end test (section 7) |
| Every poll shows a new price | the filter never confirms | tolerance or confirm count 1 (section 6) |

---

## 10. What Real Companies Did

No engineering source for a price-tracking product was read for this lesson, and the lesson makes no claim about how any such service works. The design is the general approach, assembled from first principles and checked here. The only external documents read are two Internet standards: RFC 9309 (the Robots Exclusion Protocol) and RFC 9110 (HTTP semantics), used for the robots rules and the conditional-request description in section 5.

---

## 11. Pitfalls Checklist

1. Believing a single scrape.
2. Treating a failed parse as a price of zero.
3. Alerting on every reading at or below the target instead of on a crossing, or indexing only the drops so nothing ever re-arms.
4. Re-arming at the target itself, so a price hovering at 99.99 and 100.01 spams.
5. Equal polling for all products, or polling in proportion to the weight instead of its square root.
6. Scanning every watcher of a hot product on each change.
7. Floats for money.
8. A "lowest in window" that ignores the price carried into the window.
9. Ignoring robots rules and per-host limits.
10. Claiming how a named price-tracking site works.

---

## Drills

1. Four products have weights 1, 4, 16 and 100 and the budget is one poll per hour. What are the intervals, and why is the cost 144.5 rather than 242?
2. Why is the best interval proportional to `1 / sqrt(w)` and not to `1 / w`?
3. What does `intervals` do when the budget is below `n / hi`? Why is that the right behaviour?
4. Readings are 100, 1, 100, 100 and the target is 50 (re-arm 5 percent). What do an alert fed the raw readings and the filtered pipeline do?
5. The target is 100.00 and the re-arm margin is 5 percent. After the alert fires at 99.00, which of 101.00, 104.99 and 105.00 re-arms it?
6. Why must `crossed(old, new)` exclude a target equal to `old`?
7. A product dropped to 90 thirty days ago and has not changed. What is `lowest` over the last seven days, and what bug would produce something else?
8. What does the confirmation count cost you, and how does the interval allocation reduce that cost where it matters?

---

## Homework

1. Add a "percent off the 30-day high" alert type to `Alert` and `History`; decide what the 30-day high is when there are no changes in the window; test against a per-tick series.
2. Extend `intervals` with a per-product forced minimum interval during a known sale window and check that the budget is still met by raising the other intervals.
3. Make `Tracker` accept a tolerance (prices within 1 percent count as equal) and show a case where the strict version flaps.
4. Replace `ThresholdIndex` with a sorted set kept in Redis (`ZADD`, `ZRANGEBYSCORE`) in pseudocode and say which of the lesson's tests you would port.
5. Simulate 1,000 products with weights drawn from a power law and compare equal polling, polling proportional to the weight and `intervals` on total weighted delay.

---

## Sources

All read on 27 November 2026.

- IETF, *RFC 9309, Robots Exclusion Protocol* (rfc-editor.org/rfc/rfc9309.txt), read in part: the "unavailable", "unreachable" and caching sections and the introductory statement that the rules are not access authorization.
- IETF, *RFC 9110, HTTP Semantics* (rfc-editor.org/rfc/rfc9110.txt), read in part: the `If-None-Match` and 304 sections.
- Nothing for price-tracker products: no engineering article from a price-tracking service was read. The interval allocation, the filter, the alert machine and the index are this lesson's own, derived and tested here.

## Further reading (not consulted)

- Cho and Garcia-Molina's work on how often to re-crawl pages.
- Retailer product-feed and affiliate API documentation.
- Literature on hysteresis and alert fatigue.

*Last reviewed: 27 November 2026.*
