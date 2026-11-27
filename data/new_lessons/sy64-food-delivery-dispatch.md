# Lesson 64 — Case Study: Food Delivery Dispatch (DoorDash / Swiggy)

> **Priority:** ★★★☆☆ (proposed; the curriculum data holds the final rating) — "assign the nearest driver" is the answer everyone gives, and it is wrong in a way you can measure; the interesting part is matching in batches, timing against a kitchen and not double-booking a human who may say no.
>
> **Study time:** 85 minutes. **Do this after:** Proximity Service & Location-Based Systems; Flash Sale & Ticket Reservation (Ticketmaster); Scaling Patterns II: Large Blobs, Long-Running Tasks and Real-Time Updates.
>
> **Level:** extended.

A delivery order has three parties with three clocks: a customer who wants it soon, a kitchen that finishes when it finishes and a courier who is somewhere else and can decline. Dispatch is the system that chooses which courier gets which order, when. This lesson builds the parts an interview probes as a tested model in `test/lesson_code/sy64_check.py`: the cost of a pairing, optimal matching in a time window against greedy (the gap is measured), candidate pruning (and what it loses), batching two orders onto one courier, and the offer and accept protocol. Capacity numbers come from `test/lesson_code/capacity_check_g.py`. Finding candidates near a point is the job of Proximity Service & Location-Based Systems and is not repeated.

---

## 1. Mental Model

> **Dispatch is a small optimisation solved over and over in short windows, with predictions as its inputs and a human at the end who may refuse. The quality of the answer depends far more on the predicted times and on deciding jointly than on the speed of the search.**

- **Decide jointly, not in arrival order.** Giving each order the nearest free courier as it arrives can take the courier the next order needed; solving the window as one assignment cannot be worse (section 5 measures how often it is better).
- **The courier's cost is not distance, it is time against the food.** A courier who arrives early waits; one who arrives late cools the food. The prediction of when the kitchen is ready is part of the cost (section 6).
- **Batching trades speed for efficiency.** Putting two orders on one courier saves courier time and delays someone; the system needs an explicit limit on that delay.
- **An offer is a lease the courier may let lapse.** A reply that arrives after the order moved on must be refused, which is the fencing idea again (section 7).
- **The compute is small; the inputs are the hard part.** One metro at peak is a few dozen orders per window (section 3).

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "assign the nearest driver" | candidate set by geography, then a joint assignment over the window; show why greedy loses (section 5) |
| "driver arrives before the food is ready" | cost includes predicted food-ready time; courier wait is a priced term |
| "pick up two orders at once" | route with precedence (pickup before drop) and a cap on added delay per order (section 6) |
| "driver does not respond" | offer with a deadline, a version per offer, re-offer; a late accept is refused (section 7) |
| "millions of drivers" | partition by region; each region is its own small problem |
| "surge, incentives, supply forecasting" | out of scope here; say it is a separate loop that changes supply, and name it |

---

## 3. Requirements and Capacity

**Functional.** Accept orders with a restaurant, a destination and a predicted ready time; track courier locations; match orders to couriers; offer, accept, decline and re-offer; support a courier carrying two orders; re-dispatch when a courier drops out. **Out of scope:** pricing, payments, customer ETA display, courier pay, forecasting and incentives.

**Non-functional.** Low added delay per order (a decision within a window); no order ever assigned to two couriers and no courier assigned past a load cap; availability of dispatch within a region independent of other regions.

**Capacity estimate.** Every input is *assumed* by this lesson, not any company's figure; every result is reproduced by `capacity_check_g.py`.

| Input | Value |
|---|---|
| orders in one metro per day | 50,000 *(assumed)* |
| share of the day's orders in the peak hour | 12% *(assumed)* |
| dispatch window | 20 s *(assumed; a recent DoorDash paper reports 20-second dispatch runs, section 9)* |
| couriers online at peak | 4,000 *(assumed)* |
| time an order is held by a courier, accept to drop | 25 min *(assumed)* |
| location ping | every 5 s per courier *(assumed)* |
| candidates kept per order | 20 *(assumed)* |
| offer acceptance probability | 0.7, time wasted per refused offer 15 s *(assumed)* |

| Result | Arithmetic | Value |
|---|---|---|
| orders per minute at peak | 50,000 x 12% / 60 | 100 per minute |
| orders per window | 100 x 20 / 60 | about 33 |
| orders held at once | Little's law: 100 per minute x 25 min | 2,500, a 62.5% busy share of 4,000 couriers |
| idle couriers to match against | 4,000 - 2,500 | 1,500 |
| full cost matrix | 33 x 1,500 | 49,500 cells |
| pruned to 20 per order | 33 x 20 | 660 cells |
| location updates | 4,000 / 5 | 800 per second per metro |
| offers per order | 1 / 0.7 | 1.43; 6.4 s of expected waiting from refused offers |

Four conclusions. **Matching is tiny:** 33 orders against 1,500 couriers per window. Speed of the solver is not the issue, and a design that opens with "we need a distributed matching engine" has the problem wrong. **The cost of a cell is the cost:** 49,500 route-time predictions per window is where the compute goes, which is why candidates are pruned by geography first (section 5 measures what pruning can lose). **Little's law as a sanity check:** 2,500 orders held at once cannot exceed what couriers can carry; without batching that is 62.5% busy, which is plausible, and had the table said 1,500 couriers the same demand would need 1.7 orders per courier at all times. **Refusals are a latency tax:** at a 0.7 acceptance rate each order costs 1.43 offers and about 6.4 seconds of waiting on average, a third of a 20-second window, with a tail: 2.7% of orders need four or more offers and wait 45 seconds or more at 15 seconds per refusal; so the protocol and the acceptance prediction matter.

---

## 4. API and Data Model

```
POST /orders          {restaurant, destination, ready_estimate, created}            -> order_id
PUT  /couriers/{id}/location  {lat, lng, ts}                                         (800 per second per metro)
dispatch_cycle(region, now)   -> [(order, courier)]  and offers sent
POST /offers/{order}/accept   {courier, offer_id}    -> 200 | 409 (stale or lapsed)
POST /offers/{order}/decline  {courier, offer_id}
order   {id, state: open | offered | assigned | done, courier, offer_id, expires}
courier {id, position, load, open_offer}
```

State per region lives in one place (one process or one shard per region, replicated), because the whole point is a consistent snapshot of orders and couriers for the window. Orders and couriers are routed by region (Proximity Service & Location-Based Systems covers the cell keys). Courier positions are soft state, rebuilt from pings; orders and assignments are durable.

---

## 5. Deep Dive 1: Matching a Window, Optimally

**The cost of one pairing.** The courier drives to the restaurant, waits if the food is not ready, then drives to the customer. The lesson's cost is the customer's wait (drop time minus creation time) plus a weight times the courier's idle time. The weights are a policy choice; a published system adjusts such a weight (section 9). The model uses a grid and Manhattan distance, which is enough to show the structure, not a route engine.

```python
SPEED, WAIT_W, BIG = 0.5, 0.5, 10 ** 9           # km per minute (30 km/h), weight on courier idle time, "not a candidate"

def dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def eta(courier_pos, order, now, speed=SPEED, wait_weight=WAIT_W):
    """order = {'rest', 'cust', 'ready', 'created'}. Returns (drop time, courier wait, cost)."""
    arrive = now + dist(courier_pos, order['rest']) / speed
    pickup = max(arrive, order['ready'])                       # an early courier waits for the food
    drop = pickup + dist(order['rest'], order['cust']) / speed
    wait = pickup - arrive
    return drop, wait, (drop - order['created']) + wait_weight * wait

def cost_matrix(orders, couriers, now, speed=SPEED, wait_weight=WAIT_W):
    return [[eta(c, o, now, speed, wait_weight)[2] for c in couriers] for o in orders]

def prune(M, k):
    """Keep each order's k cheapest couriers; the rest become BIG. A stand-in for 'candidates from a geo index'."""
    out = []
    for row in M:
        keep = set(sorted(range(len(row)), key=lambda j: (row[j], j))[:k])
        out.append([x if j in keep else BIG for j, x in enumerate(row)])
    return out
```

The check pins the cost against hand cases: food ready at 10 and a courier 2 away at speed 1 waits 8 and drops at 14 (cost 18 with weight 0.5); a courier who arrives exactly when the food is ready waits 0; with the weight at 0 the early and the just-in-time courier tie at 14, and with it the early courier costs more, which is the whole reason the term exists.

**Greedy and its trap.** Process orders as they arrive and give each the cheapest free courier. Two orders and two couriers with costs `[[1, 2], [2, 100]]`: order 0 takes courier 0 at cost 1, leaving order 1 to courier 1 at cost 100 (total 101); the optimum is order 0 to courier 1 and order 1 to courier 0 (total 4). The optimal assignment is the Hungarian algorithm (also called Kuhn-Munkres): O(n squared times m) for n orders and m columns, which at 33 by 1,500 is a trivial number of steps.

```python
def hungarian(cost):
    """Min-cost assignment of n rows to m >= n columns. Returns (total, column of each row)."""
    n, m, INF = len(cost), len(cost[0]), float('inf')
    u, v, p, way = [0] * (n + 1), [0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minv, used = [INF] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], INF, 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    col = [None] * n
    for j in range(1, m + 1):
        if p[j]:
            col[p[j] - 1] = j - 1
    return sum(cost[i][col[i]] for i in range(n)), col

def match(cost, penalty):
    """Orders may stay unassigned for this window at a price `penalty`: add one dummy column per order, and make any real
    cell at or above the penalty worse than its dummy. Returns the courier index per order, or None."""
    n, m = len(cost), len(cost[0])
    wide = [[c if c < penalty else penalty + 1 for c in row] + [penalty] * n for row in cost]
    _, col = hungarian(wide)
    return [j if j < m else None for j in col]

def greedy(cost, penalty):
    taken, out = set(), []
    for row in cost:
        free = [j for j in range(len(row)) if j not in taken and row[j] < penalty]
        j = min(free, key=lambda j: (row[j], j)) if free else None
        out.append(j)
        taken.add(j)
    return out
```

Why the penalty and the dummy columns: with fewer couriers than orders, or couriers too far to be sensible, the right answer is "wait for the next window", and the matching must be allowed to say so rather than force a terrible pairing. What the check does: 1,500 random matrices (up to 6 orders against up to 7 couriers, costs up to a million, three penalty levels) against a brute force over every partial matching, requiring the same total, no courier used twice and nothing assigned at or above the penalty; a matrix with 12-digit costs against all permutations; and more orders than couriers. **Measured (illustrative, seeded random instances): greedy was worse than the optimum on 1,079 of 2,000 random instances** (2 to 6 orders, 2 to 8 couriers, random costs); it is never better. Random costs are not a city, so read the figure as "the trap is common", not as a prediction for your traffic.

**Pruning, and what it loses.** Scoring every courier for every order is the 49,500 cells of section 3. Keeping only each order's k best couriers (in production, the couriers a geo index returns near the restaurant) cuts it to 660. It is not free: two orders can have the same best candidates, and pruning removes the courier that the joint answer wanted. **Measured: with the 3 nearest-in-cost couriers per order, pruned matching was worse than the full matching on 81 of 1,000 random instances** (3 to 8 orders, 8 to 14 couriers); with k equal to all couriers it never was. The right k is a measured trade between ETA calls and lost quality, and a region with sparse couriers needs a larger k, since a short list may contain nobody feasible. The check asserts that pruning never beats the full matching and equals it at full k.

**Windows, not instants.** Waiting 20 seconds before deciding delays every order by up to a window and buys the ability to match jointly; a shorter window is faster and decides closer to greedy. This is a policy dial, not a constant of nature, and a system may also close a window early when an order has waited long enough.

---

## 6. Deep Dive 2: Timing Against the Kitchen, and Batching

**Predictions are inputs.** The dispatch decision is only as good as three predictions: the time the food is ready, the courier's travel time and the delivery time. DoorDash's 2020 GTC talk (section 9) describes machine learning predicting food preparation, travel and delivery times, with an optimisation layer, a mixed-integer program, that takes those predictions, a cost function and constraints and picks the assignments. A bad ready-time prediction is worse than a slow solver: the courier arrives and waits, or arrives late and the food sits. The cost function above prices both sides.

**Batching.** A courier carrying two orders must visit four stops with each pickup before its own drop. The lesson's route cost sums each customer's wait plus the weighted idle time at kitchens, and returns "infeasible" for an order of stops that drops before it picks up, picks twice or leaves an order out.

```python
from itertools import permutations

def run_route(start, t0, orders, seq, speed=SPEED):
    """Drive the stops in order: ('p', i) picks up order i, ('d', i) delivers it. Returns ({order: drop time}, total wait) or None."""
    pos, t, wait, picked, drops = start, t0, 0, set(), {}
    for kind, i in seq:
        o = orders[i]
        if kind == 'p':
            if i in picked:
                return None
            t += dist(pos, o['rest']) / speed
            pos = o['rest']
            if t < o['ready']:
                wait += o['ready'] - t
                t = o['ready']
            picked.add(i)
        else:
            if i not in picked or i in drops:
                return None
            t += dist(pos, o['cust']) / speed
            pos = o['cust']
            drops[i] = t
    return (drops, wait) if len(drops) == len(orders) else None

def route_cost(start, t0, orders, seq, speed=SPEED, wait_weight=WAIT_W):
    r = run_route(start, t0, orders, seq, speed)
    return None if r is None else sum(t - orders[i]['created'] for i, t in r[0].items()) + wait_weight * r[1]

def best_route(start, t0, orders, speed=SPEED, wait_weight=WAIT_W):
    """Exact: every ordering of the stops. Fine for two or three orders (at most 720 sequences)."""
    stops = [('p', i) for i in range(len(orders))] + [('d', i) for i in range(len(orders))]
    best = None
    for s in permutations(stops):
        c = route_cost(start, t0, orders, list(s), speed, wait_weight)
        if c is not None and (best is None or c < best[0]):
            best = (c, list(s))
    return best

def insert_best(start, t0, orders, seq, new, speed=SPEED, wait_weight=WAIT_W):
    """Cheapest insertion of order `new` into an existing route: try every pair of positions (pickup no later than drop)."""
    best = None
    for pi in range(len(seq) + 1):
        for di in range(pi, len(seq) + 1):
            cand = seq[:pi] + [('p', new)] + seq[pi:di] + [('d', new)] + seq[di:]
            c = route_cost(start, t0, orders, cand, speed, wait_weight)
            if c is not None and (best is None or c < best[0]):
                best = (c, cand)
    return best

def batch_ok(start, t0, orders, seq, max_extra, speed=SPEED):
    """The rule that keeps batching honest: nobody is more than max_extra later than they would be alone with this courier."""
    r = run_route(start, t0, orders, seq, speed)
    if r is None:
        return False
    for i, t in r[0].items():
        solo = run_route(start, t0, [orders[i]], [('p', 0), ('d', 0)], speed)[0][0]
        if t - solo > max_extra:
            return False
    return True
```

The check works the small cases by hand (two orders, the first at once and the second's kitchen ready at 6: picking both up first gives drops at 8 and 10 with a 5-minute wait; serving the first and then the second gives 3 and 10 with a 1-minute wait, so the weighted costs are 20.5 and 13.5) and compares `best_route` with an independently written enumerator (6 and 90 valid sequences for 2 and 3 orders). **Cheapest insertion is a heuristic, and it is measured:** adding orders one at a time, it matched the exact route on **1,377 of 1,500** random instances of 1 to 3 orders (always for one order), and was never cheaper than the exact route. The misses come from an early commitment that a later order would have wanted undone. Real routing at scale uses heuristics for the same reason; Pickup-and-delivery routing is, as a general operations-research fact (not something taken from a DoorDash source here), a hard combinatorial problem, so exact search is limited to a few stops and real systems use heuristics; this lesson does not describe anyone's method.

**The limit on batching.** A batch is acceptable if `batch_ok` holds: each order's drop time is within `max_extra` of its solo time with that courier. The check asserts the boundary (5 minutes passes where the first order is 5 later, 4.99 fails) and that an infeasible route is never ok. A recent DoorDash paper describes the trade directly: batching can improve courier efficiency while faster execution reduces lateness, and over-batching in congestion can increase lateness (section 9). The weights and caps are knobs; whoever runs the marketplace sets them.

---

## 7. Deep Dive 3: Offers, Refusals and Never Double-Booking

The matching gives a pairing; a courier then sees an offer and may accept, decline or ignore it. The order's state machine is: open, offered (to one courier, with a deadline and an offer id), assigned, done. Rules: an order can be offered to one courier at a time; a courier has at most one open offer and at most `max_load` assigned orders; an accept counts only if the order is still offered to that courier **with that offer's id** and the deadline has not passed; an offer that lapses returns the order to open and the next offer gets a **new** id; accept and decline are both fenced by that id, since a delayed decline of an old offer must not cancel the new one.

```python
class Dispatch:
    def __init__(self, ttl, max_load=2):
        self.ttl, self.max_load = ttl, max_load
        self.orders, self.load, self.offered_to, self.next_offer = {}, {}, {}, 1
    def add_order(self, oid):
        self.orders[oid] = {'state': 'open', 'courier': None, 'offer': None, 'expires': None}
    def offer(self, oid, courier, now):
        o = self.orders[oid]
        if o['state'] != 'open' or courier in self.offered_to or self.load.get(courier, 0) >= self.max_load:
            return None
        o.update(state='offered', courier=courier, offer=self.next_offer, expires=now + self.ttl)
        self.offered_to[courier] = oid
        self.next_offer += 1
        return o['offer']
    def _live(self, oid, courier, offer_id):
        o = self.orders[oid]
        return o['state'] == 'offered' and o['courier'] == courier and o['offer'] == offer_id
    def _release(self, oid):
        o = self.orders[oid]
        self.offered_to.pop(o['courier'], None)
        o.update(state='open', courier=None, offer=None, expires=None)
    def accept(self, oid, courier, offer_id, now):
        if not self._live(oid, courier, offer_id) or now > self.orders[oid]['expires']:
            return False
        if self.load.get(courier, 0) >= self.max_load:   # the cap holds at the commit point, whatever offers were out
            self._release(oid)
            return False
        self.offered_to.pop(courier)
        self.orders[oid]['state'] = 'assigned'
        self.load[courier] = self.load.get(courier, 0) + 1
        return True
    def decline(self, oid, courier, offer_id, now):
        if not self._live(oid, courier, offer_id):
            return False
        self._release(oid)
        return True
    def expire(self, now):
        for oid, o in self.orders.items():
            if o['state'] == 'offered' and now > o['expires']:
                self._release(oid)
    def complete(self, oid):
        o = self.orders[oid]
        if o['state'] != 'assigned':
            return False
        o['state'] = 'done'
        self.load[o['courier']] -= 1
        return True
```

The failure the offer id exists for: courier A's offer lapses, the order is re-offered to B, and A's accept, delayed on a bad connection, arrives afterwards. Without the id check, A's late accept, arriving while the order is merely offered to someone, or while it was re-offered to A itself, can win. The check runs each case: wrong courier, wrong id, accept at exactly the deadline (counts), one tick later (does not), the late accept from A after B took the order (refused, B assigned, A's load 0), the same courier re-offered the same order (the old id stays dead), decline by the wrong courier (refused), **a late decline of the old offer id after the same courier was re-offered the order (refused, the new offer stays live and can be accepted)**, one open offer per courier, the load cap at offer time and again at accept time (a courier pushed to the cap behind the offer's back cannot accept) and a double completion freeing nothing. Then 150 seeded random interleavings of offers, accepts with any offer id ever issued (fresh or stale), declines, expiries and completions, asserting after every step that the orders recorded as assigned are exactly the orders whose accept returned true (each at most once), every courier's load equals the orders assigned to it and never exceeds 2, every courier has at most one open offer, and the open-offer index matches the order states.

This is the same idea as the hold in Flash Sale & Ticket Reservation (a row with an expiry that a conditional update and the confirm step re-check, so a lapsed hold cannot be used) and the attempt number of Scaling Patterns II (a lease plus a counter the receiver checks); here the "resource" is the order record, which the dispatch service owns, so a single compare inside one process or one row is enough. Chubby-style tokens (Case Study: Distributed Lock Service) are for resources you do not own.

**What the state machine does not cover.** A courier who accepts and then disappears (the order is assigned and nobody is moving): a separate watchdog on the courier's pings reopens the order; it is a timeout on `assigned` with its own rules, not modelled here. A restaurant that cancels or delays: the ready time changes, so the cost of an already-assigned courier changes and the system may re-plan; also not modelled.

---

## 8. Failure Modes

| Failure | What happens | Defence |
|---|---|---|
| bad ready-time prediction | couriers wait or food cools | cost with a wait term; refresh the prediction; re-plan before the pickup |
| greedy dispatch | locally best, globally worse (1,079 of 2,000 instances in the simulation) | match the window jointly |
| pruning too tight | the best joint answer is not among the candidates (81 of 1,000) | measure k; widen in sparse regions |
| offer lapses, late accept | two couriers think they have the order | offer id compared on accept |
| courier at the load cap offered another | an order assigned beyond the cap | the cap is enforced at accept (the commit point) and checked at offer time to avoid wasted offers; one open offer per courier |
| courier vanishes after accepting | the order is held by nobody | watchdog on pings (not modelled) |
| a region's dispatch is down | that region stops matching | one state per region; other regions are unaffected |
| over-batching in a rush | late orders pile up | per-order cap on added delay (`batch_ok`) |

---

## 9. What Real Systems Did

Only what was read; nothing here describes Swiggy's design (no Swiggy engineering source could be fetched).

- **DoorDash, GTC talk "How Machine Learning Powers On-Demand Logistics at DoorDash" (25 March 2020):** the logistics engine balances supply and demand, plans routes and matches dashers to deliveries; the matching is described as the vehicle routing problem; machine learning predicts food prep, travel and delivery times and an optimisation step takes those predictions, a cost function and constraints and solves with mixed-integer programming.
- **DoorDash research paper on objective weights (arXiv, 2026):** in a three-sided marketplace, "the optimizer" maps orders, couriers, constraints and objective weights to assignments, and a learned policy picks a store-level multiplier on a delivery-speed weight; lower weights make batching more attractive, higher weights favour faster completion; its own measurements are ASAP (customer wait from order creation to drop-off) and XCAT (courier active time beyond the direct trip); the policy runs on each dispatch run, reported as hundreds of millions of daily inferences at a 20-second cadence. The paper is about learning those weights, not about how the optimizer works.

**Not read:** DoorDash's engineering blog posts on dispatch, batching and routing (the site refused automated fetches; only search snippets were seen, so nothing from them is stated as fact); anything from Swiggy; Uber's or Instacart's material. The grid and Manhattan distance, the cost weights, the cap on added delay, the offer-id state machine and every figure in the capacity table are this lesson's.

---

## 10. Pitfalls

1. "Nearest driver" with no discussion of joint assignment.
2. Ignoring the kitchen: distance-only cost sends couriers to wait or arrive late.
3. Forcing every order into this window's matching when waiting a window is better.
4. Scoring every courier for every order (49,500 cells) instead of pruning to candidates, and not measuring what pruning loses.
5. Batching with no cap on the delay it adds to each order.
6. Accepting on (order, courier) alone: a late accept wins.
7. Reusing an offer id for a re-offer.
8. Enforcing the load cap in only one place: it must hold at accept, the commit point (offer-time checks and one open offer per courier only avoid wasted offers), or a courier with several open offers can accept past the cap.
9. One global dispatch process for all cities.
10. Claiming a company's algorithm ("DoorDash uses X") with no source.

---

## Drills

1. Orders O1 and O2, couriers C1 and C2, costs `[[3, 5], [4, 20]]`. What does greedy give, what does the optimum give, and what are the totals?
2. A courier is 2 minutes from the kitchen and the food is ready in 10. What is the courier's wait, and what is the cost's wait term at weight 0.5?
3. Why does the lesson's matching add one dummy column per order and set real cells at or above the penalty to penalty plus 1?
4. At 100 orders a minute and a 20-second window, how many orders does one window hold, and why is the matching itself not the bottleneck?
5. Pruning to 3 candidates per order lost quality on 81 of 1,000 instances. Name one reason a sparse region needs a larger k than a dense one.
6. Two orders are batched; order 1 would be delivered at minute 3 alone and minute 8 in the batch. With a cap of 4, is the batch acceptable? What would you change?
7. Courier A's offer lapses at t = 15; the order goes to B at 16; A's accept arrives at 16.5. What does the protocol return and which check decides it?
8. Little's law says 2,500 orders are held at once. You have 1,500 couriers. What load does that imply and which design change does it force?

---

## Homework

1. Run `test/lesson_code/sy64_check.py` and change `WAIT_W` to 0: which assertion fails, and what changes about which courier wins in the first test?
2. Replace the penalty with a per-order priority (older orders get a higher penalty). Show a case where the older order wins a courier the newer one would have taken.
3. Add a time-to-ready refresh: when the ready estimate for an assigned order rises by 5 minutes, re-score the assigned courier against an idle one and decide whether to swap. Write the test.
4. Implement the watchdog from section 7: reopen an assigned order if the courier's ping is older than a threshold; list the new races it creates with accept and complete.
5. Extend `insert_best` to try inserting all orders in every order (instead of index order) and measure how often that closes the 1,377 of 1,500 gap.
6. Practice: sketch dispatch for scheduled orders (placed an hour ahead) where couriers are reserved in advance; say what changes in the cost and the offer.

---

## Sources

All accessed 27 November 2026.

- DoorDash, GTC 2020 slides "How Machine Learning Powers On-Demand Logistics at DoorDash" (Gary Ren, 25 March 2020), developer.download.nvidia.com: the PDF was downloaded and its text read in full (306 lines of slide text): the logistics engine, the vehicle routing problem framing, ML predictions feeding a mixed-integer-programming layer. Slides, so thin on detail.
- "Multi-Agent Reinforcement Learning from Delayed Marketplace Feedback for Objective-Weight Adaptation in Three-Sided Dispatch" (Wu, Hou, Xie, DoorDash, arXiv 2606.13604, June 2026): the introduction, section 2 (formulation, state, reward including ASAP and XCAT) and the abstract read; the appendices, the training and the experiment sections were not.

**Not consulted:** DoorDash engineering blog posts (access refused; search snippets only), any Swiggy engineering writing (unreachable), Uber or Instacart dispatch papers, the Kuhn-Munkres original paper or a textbook (the Hungarian code is a standard potentials implementation checked here against brute force, not against a source). The capacity inputs, the cost function, the delay cap and the offer protocol are this lesson's. Simulation figures (1,079 of 2,000; 81 of 1,000; 1,377 of 1,500) are illustrative: seeded Python runs on 3.13 of random instances.

*Last reviewed: 27 November 2026.*
