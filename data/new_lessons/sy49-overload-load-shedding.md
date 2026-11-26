# Lesson 49 — Overload, Load Shedding and Cascading Failures

> **Priority:** ★★★★★ — "what happens when this dependency gets slow?" ends most reliability follow-ups, and the strong answer explains why the system does not recover on its own.
>
> **Study time:** 60 minutes. **Do this after:** Resilience: Rate Limiting & Circuit Breakers, and SLOs, SLIs and Error Budgets.
>
> **Level:** core.

The Resilience lesson gave you the toolbox: timeouts, retry budgets and jitter, circuit breakers, bulkheads, rate limiters, shedding versus backpressure, CoDel and LIFO, and shedding by priority. This lesson builds the model underneath it and runs it. It answers four questions the toolbox leaves open. Why does removing the trigger not restore health? How big does a trigger have to be before it tips a system over? When two defences look equivalent, which one actually breaks the loop? And what do Google and Amazon add beyond that toolbox: client-side throttling that stops rejected requests from becoming the load, criticality classes, and the arithmetic of a fleet that crashes as fast as it restarts. All numbers below are produced by the code in this file; the paper figures it reproduces are checked.

---

## 1. Mental Model

> **Overload is a loop, not a level. Past capacity a server does extra work for each useful result (queueing, timeouts, retries, cold caches, error handling), so goodput falls as offered work rises, and the extra work is itself new load. If that loop is strong enough the system has a second stable state, a collapsed one, and removing whatever started it does not leave it.**

What follows from it:

- **Goodput, not throughput, is the number.** Goodput is the part of the work that completes with low enough latency for the client to use it. A server can be busy at 100% CPU with goodput near zero.
- **The trigger is not the root cause; the sustaining effect is.** The metastable-failure papers (read 2026-11-26) say it directly: many triggers lead to the same failure state, so the loop is what you fix.
- **Efficient systems live close to the cliff.** A cache with a 90% hit rate lets a database that handles 300 queries per second sit behind an application serving 3,000. That is a design choice to run in what the papers call the vulnerable state: healthy until a trigger arrives.
- **Defences work by cutting the loop at one of three points:** refuse work early and cheaply, cut the amplification (retries, wasted work), or choose which work to keep (newest, most critical).
- **Recovery needs a corrective push,** and the push has a size: reducing load far enough, or discarding the stale work, not "waiting it out".

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "the database had a 10-second blip and the site stayed down for an hour" | a metastable failure; look for the sustaining effect (retries, cold cache, queue of abandoned work) |
| "p99 is fine, but some requests never finish" | bimodal latency: thread-seconds, not averages; fail fast and shorten deadlines |
| "the service rejects requests but CPU is still pegged" | rejection is not free; client-side throttling and cheaper rejection |
| "one of many services is over quota" | per-customer limits so only the offender sees errors |
| "protect checkout, sacrifice recommendations" | criticality classes, shed lower ones sooner |
| "restart everything" | check for a cold-cache or crash-loop effect first; restarting can add load |
| "we cleared the cache and it never refilled" | a look-aside cache under timeouts; fill with higher priority than serving |
| "how do you test it?" | push load past the break and apply a trigger; see whether it quiesces |

---

## 3. The Arithmetic of the Cliff

Bronson, Aghayev, Charapko and Zhu (HotOS 2021, read 2026-11-26) give a worked example that the rest of this lesson simulates. A stateless web app sends one query per user request to a database, and a second query if the first has not returned in 1 second. The database answers in under 100 ms while load is below 300 QPS, and an order of magnitude slower above that. The app is running at 280 QPS when a 10-second network outage hits the switch in front of the database. When connectivity returns, everything lost in the outage is retransmitted, requests and retries together; the database overloads, every query times out, and retries keep the offered load near 560 QPS, so goodput is zero. The paper's account of recovery: reduce the app's load below 150 QPS, or limit retries to under 20 QPS.

The two numbers are one-line arithmetic. Call the first the **hidden capacity** and the second the **retry room** (the paper uses "hidden capacity" for the load below which a system self-heals):

```python
def stable_load_limit(capacity, attempts_per_request=2):
    """Below this load the system recovers from any trigger even if every request is retried."""
    return capacity / attempts_per_request

def extra_retry_room(capacity, load):
    """Retries per second the system can absorb on top of its load; above this the retry loop sustains itself."""
    return capacity - load
```

`stable_load_limit(300)` is 150 QPS and `extra_retry_room(300, 280)` is 20 QPS. The same paper's second example is a look-aside cache: a 90% hit rate lets the application serve 3,000 QPS in front of a 300 QPS database, so a cache loss is a 10x amplification, and the cache cannot refill because the application's timeouts make every fill attempt look like a failure:

```python
def cache_loss_amplification(hit_rate):
    """Database queries per user request after the cache is lost, relative to before."""
    return 1 / (1 - hit_rate)
```

**Advertised versus hidden capacity.** The paper separates the load the system serves in good times (3,000 QPS here) from the load at which it would still self-heal if the cache vanished (300 QPS, what the database can carry alone). Operating between the two is the vulnerable state. Its advice for finding the boundary is an experiment you can run, and section 4 does: run at a load level, apply a trigger, and see whether the system quiesces without intervention.

Three more sizing facts, from the Google SRE book chapter on cascading failures (read 2026-11-26):

```python
def bimodal_goodput_share(threads, qps, fast_s, slow_fraction, deadline_s):
    """Share of requests that can be served when `slow_fraction` of them hold a thread until the deadline."""
    demand = qps * (1 - slow_fraction) * fast_s + qps * slow_fraction * deadline_s      # busy threads wanted
    return min(1.0, threads / demand)

def queue_wait(queue_length, threads, service_s):
    """Seconds a request waits behind a full queue in front of `threads` workers, plus its own service time."""
    return queue_length / threads * service_s + service_s

def max_load_for_recovery(total_capacity, healthy_fraction):
    """A crash-looping fleet stabilises only when the load fits what its healthy part can carry."""
    return total_capacity * healthy_fraction
```

- **Bimodal latency.** A frontend with 1,000 threads serves 1,000 QPS in 100 ms, so 100 threads are busy. If 5% of requests never complete (the book's example is an unavailable key range) and the deadline is 100 seconds, those requests want 5,000 threads' worth of work: `bimodal_goodput_share(1000, 1000, 0.1, 0.05, 100)` is 0.196, so **19.6% of requests are served and 80.4% fail**, though only 5% were doomed. With a 10-second deadline the demand is 595 threads and everything that can succeed does; the book's advice is deadlines far shorter than orders of magnitude over the mean, and failing fast when a backend is known to be unavailable.
- **Queue sizing.** A queue ten times the thread count with 100 ms service time makes a request on a full queue wait 1.1 seconds (`queue_wait(100, 10, 0.1)`), mostly in the queue. The book prefers short queues, at most about half the thread pool for steady traffic, and notes that Gmail often uses queueless servers and relies on failover instead.
- **Crash loops.** A service healthy at 10,000 QPS that starts crashing at 11,000 does not stabilise when load drops to 9,000: only the healthy part of the fleet carries traffic. If 10% of servers are healthy, `max_load_for_recovery(10000, 0.1)` is 1,000 QPS, which is what the book says the rate must fall to. The healthy fraction depends on how fast tasks start, how fast they reach full speed, and how long a fresh task survives the load.

---

## 4. Deep Dive 1: Run the Loop

This simulator is the paper's example made executable. One client tier sends queries to one database queue at one-tenth-of-a-second ticks. A request that has not completed after `timeout` seconds gets one retry when the retry policy allows. The database serves its queue at `capacity` per second and, crucially, **cannot know that a client has given up**, so a query served after its timeout is wasted work. That one assumption is the sustaining effect.

```python
from collections import deque

def simulate(load, capacity=300, timeout=1.0, retries='unlimited', lifo=False, drop_stale=False,
             outage=(20, 30), seconds=240, dt=0.1):
    """One client tier in front of one database. Each user request makes one query; if it has not completed within
    `timeout` seconds the client sends one more (a retry) when `retries` allows. The database serves its queue at
    `capacity` queries per second but cannot know a client has given up, so a query served after its timeout is
    wasted work. `load` and `retries` may be numbers/strings or functions of the time in seconds.
    retries: 'none', 'unlimited', or ('budget', ratio): at most `ratio` retries per new request.
    Returns the goodput (completed requests) in each second."""
    queue, waiting, goodput = deque(), deque(), [0] * seconds
    carry, tokens, ticks = 0.0, 0.0, int(round(seconds / dt))
    for i in range(ticks):
        now = i * dt
        qps = load(now) if callable(load) else load
        mode = retries(now) if callable(retries) else retries
        carry += qps * dt
        new, carry = int(carry), carry - int(carry)
        for _ in range(new):
            req = [now, False]                       # [arrival time, completed]
            queue.append((req, now))
            waiting.append(req)
            if isinstance(mode, tuple):
                tokens = min(tokens + mode[1], 100.0)
        while waiting and now - waiting[0][0] >= timeout - 1e-9:
            req = waiting.popleft()
            if req[1] or mode == 'none':
                continue
            if isinstance(mode, tuple):
                if tokens < 1:
                    continue
                tokens -= 1
            queue.append((req, now))
        budget = 0 if outage[0] <= now < outage[1] else int(round(capacity * dt))
        while budget and queue:
            req, sent = queue.pop() if lifo else queue.popleft()
            if drop_stale and (now - sent >= timeout or req[1]):
                continue                             # the server skips work nobody is waiting for, at no cost
            budget -= 1
            if not req[1] and now - sent < timeout:
                req[1] = True
                goodput[int(now)] += 1
    return goodput

def recovery_seconds(goodput, load, outage_end, share=0.9, hold=5):
    """Seconds after the outage ends until goodput stays at `share` of the offered load for `hold` seconds; None if never."""
    for t in range(outage_end, len(goodput) - hold + 1):
        if all(goodput[t + k] >= share * (load(t + k) if callable(load) else load) for k in range(hold)):
            return t - outage_end
    return None
```

The check compares it with a separately written implementation (different data structures) over 72 parameter combinations, and verifies invariants: goodput never exceeds capacity, nothing completes while the database is down, steady state at 280 QPS gives exactly 280 per second.

**Experiment 1: how big a trigger does it take?** The database goes down for `d` seconds at `t = 20`. Each cell is the time from the end of the outage until goodput is back, for the plain FIFO queue with unlimited retries, or "never" if it has not recovered 600 seconds later:

```python
def trigger_table(loads=(100, 140, 150, 200, 250, 280), outages=(1, 2, 5, 10, 30), horizon=600):
    """{load: {outage seconds: seconds from the end of the outage until goodput is back, or None}} for the plain
    FIFO queue with unlimited retries. The outage starts at t = 20."""
    return {load: {d: recovery_seconds(simulate(load, outage=(20, 20 + d), seconds=20 + d + horizon), load, 20 + d)
                   for d in outages} for load in loads}
```

| Load (QPS) | 1 s outage | 2 s | 5 s | 10 s | 30 s |
|---|---|---|---|---|---|
| 100 | 0 s | 1 s | 7 s | 17 s | 57 s |
| 140 | 0 s | 8 s | 50 s | 120 s | 400 s |
| 150 | 0 s | never | never | never | never |
| 200 | 0 s | never | never | never | never |
| 250 | never | never | never | never | never |
| 280 | never | never | never | never | never |

The boundary falls exactly where the paper's arithmetic says: at 140 QPS (below `stable_load_limit(300)` = 150) every outage is survived, though the recovery time climbs steeply near the edge (120 seconds for a 10-second outage, against 17 at 100 QPS). At 150 QPS and above a 2-second outage already tips the system. At 250 and above one second is enough. This is the paper's trigger intensity idea in numbers: **the closer you run to advertised capacity, the smaller the blip that kills you.** It is also why "it survived last quarter's incident" is weak evidence. The model is deliberately idealised (one retry, FIFO queue, instant stale work), so use the thresholds as a method, not as a prediction for your database.

**Experiment 2: which defence breaks the loop?** Same system, same 10-second outage, load 280 QPS, so the baseline never recovers:

```python
def defence_table(load=280, outage=(20, 30)):
    """Seconds until goodput is back to 90% of the offered load (None: not within the run), same 10 s outage."""
    end = outage[1]
    rows = {}
    rows['nothing (FIFO, unlimited retries)'] = recovery_seconds(simulate(load, outage=outage, seconds=300), load, end)
    rows['no retries at all'] = recovery_seconds(simulate(load, retries='none', outage=outage, seconds=300), load, end)
    rows['retry budget, 10% of new requests'] = recovery_seconds(simulate(load, retries=('budget', 0.1), outage=outage, seconds=300), load, end)
    rows['serve the newest first (LIFO)'] = recovery_seconds(simulate(load, lifo=True, outage=outage, seconds=300), load, end)
    rows['database skips abandoned queries'] = recovery_seconds(simulate(load, drop_stale=True, outage=outage, seconds=300), load, end)
    stop = lambda t: 'unlimited' if t < 60 else 'none'
    rows['operator stops retries at t = 60 s'] = recovery_seconds(simulate(load, retries=stop, outage=outage, seconds=1200), load, 60)
    cut = lambda t: load if t < 60 or t >= 200 else 100
    rows['operator cuts load to 100 QPS from t = 60 s to 200 s'] = recovery_seconds(simulate(cut, outage=outage, seconds=500), cut, 60)
    brief = lambda t: load if t < 60 or t >= 140 else 140
    rows['operator cuts load to 140 QPS from t = 60 s to 140 s'] = recovery_seconds(simulate(brief, outage=outage, seconds=500), brief, 60)
    return rows
```

| Defence | Time until goodput is back |
|---|---|
| nothing (FIFO, unlimited retries) | never |
| no retries at all | 127 s |
| retry budget, 10% of new requests | never |
| serve the newest first (LIFO) | 0 s |
| database skips abandoned queries | 0 s |
| operator stops retries at t = 60 s | 643 s |
| operator cuts load to 100 QPS from t = 60 s to 200 s | 131 s |
| operator cuts load to 140 QPS from t = 60 s to 140 s | never |

Reading the table is the lesson:

- **Turning retries off from the start does not prevent the outage's damage:** during the 10 seconds, 2,800 requests queued up; the database works through them at the spare 20 QPS, and each one is already older than the timeout, so it is wasted. The model recovers in 127 seconds, which the check matches to the backlog arithmetic: `(2,800 - 300) / (300 - 280)` = 125 s. A system with a short blip and zero retries still has a two-minute brownout.
- **A retry budget is not enough on its own.** At 280 QPS a 10% budget lets the offered load reach about 308, still above the 300 the database can serve, so the backlog never drains. A budget stops the amplification from reaching 2x; it does not create headroom. This is the sharpest reason to read "retry budget" as one defence among several.
- **LIFO and "skip abandoned work" recover immediately,** because both remove the sustaining effect itself: the queue is no longer full of work whose client has left. LIFO serves the newest requests first, which still have their clients; skipping stale work makes the wasted service free. In production this corresponds to deadline propagation and cancellation, and it is the closest thing in the table to a fix rather than a mitigation.
- **Operator actions take longer than the instinct suggests.** Stopping retries 30 seconds into the collapse still needs 643 seconds, because by then the stale backlog is large. Cutting load to 100 QPS works in 131 seconds, but cutting to 140 QPS and restoring at t = 140 never recovers: the cut was too mild and too short, and the restored load re-enters the loop. Both mirror the papers' statement that leaving the metastable state needs a strong corrective push such as dramatically reducing load.
- **The characteristic metric is queueing delay, not QPS.** The paper notes that queueing delay stays resilient to changes in workload where QPS does not, which is why shedders watch time in queue (the CoDel idea in the Resilience lesson).

Visual (planned): goodput against offered load for the stable, vulnerable and metastable regions, with the 150 and 300 QPS boundaries marked, and a time series of one run per defence.

---

## 5. Deep Dive 2: Admission Control That Costs Less Than the Work

Shedding load makes the queue short and the work useful, but **rejecting is not free**. The SRE book (chapter on handling overload, read 2026-11-26) warns that when a rejection costs nearly as much as serving (a simple memory lookup, where protocol overhead dominates), a backend can be overloaded while most of its CPU goes on saying no. The model: if rejecting one request costs a fraction `r` of serving one, goodput is the largest `a` with `a + r x (offered - a) <= capacity`.

```python
def goodput_with_rejection_cost(offered, capacity, reject_cost):
    """Requests per second actually served when rejecting one costs `reject_cost` of serving one."""
    if offered <= capacity:
        return offered
    return max(0.0, min(offered, (capacity - reject_cost * offered) / (1 - reject_cost)))
```

For a backend with capacity 1,000 requests per second, goodput as the offered load rises from 1x to 3x capacity:

| Cost of a rejection | 1x | 1.5x | 2x | 3x |
|---|---|---|---|---|
| 10% of serving | 1,000 | 944 | 889 | 778 |
| 50% of serving | 1,000 | 500 | 0 | 0 |

When rejection is cheap, shedding holds goodput close to capacity. When rejection costs half of serving, **a backend at twice its capacity has zero goodput**, even though every individual decision it makes is correct. The fix the book describes is to move the rejection to the **client**.

**Adaptive throttling.** Each client task keeps, for the last two minutes, the number of requests its application attempted and the number the backend accepted. Normally they are equal. Once attempts exceed `K` times accepts, the client starts rejecting new requests locally, with a probability that rises as the gap grows; requests rejected locally never reach the network. The book prefers `K = 2`, reports that backends then end up rejecting about one request for each they serve, and says lowering `K` to 1.1 means one rejection per ten accepted. A caveat on the code: the probability is printed in the book as an equation image that this lesson could not read as text, so the formula below is the commonly quoted form (zero below the cutoff, rising above it). It is consistent with both statements the book makes, and the check reproduces both, but treat it as a reconstruction.

```python
def throttle_equilibrium(attempts, capacity, k=2.0, window=120, seconds=600):
    """Client-side adaptive throttling, fluid version. Each second the clients reject locally with probability
    max(0, (requests - k * accepts) / (requests + 1)), where both counts cover the last `window` seconds.
    Returns (requests sent to the backend per second, requests it accepts) at the end."""
    hist = deque()
    for _ in range(seconds):
        requests, accepts = sum(h[0] for h in hist), sum(h[1] for h in hist)
        p = max(0.0, (requests - k * accepts) / (requests + 1))
        sent = attempts * (1 - p)
        accepted = min(sent, capacity)
        hist.append((attempts, accepted))
        if len(hist) > window:
            hist.popleft()
    return sent, accepted
```

With clients attempting 3,000 requests per second against a backend that can accept 1,000: at `K = 2` the clients send 2,000 and the backend accepts 1,000 (rejecting 1,000); at `K = 1.1` they send 1,100 and it rejects 100. Below capacity the throttle does nothing (800 attempts: 800 sent). The trade-off the book states for `K`: a larger value wastes more backend work on rejections but spreads recovery news to clients faster, which is why it generally prefers 2.

**Retries across layers, Google's way.** Besides budgets, the book describes a per-request limit of three attempts and a per-client rule that retries are allowed only while they are under 10% of requests. For the worst case (a datacenter accepting little and rejecting most), the first cap alone allows growth to just under 3x, and adding the 10% ratio brings it to 1.1x. It also has backends answer "overloaded; don't retry" when their histograms of attempt counts suggest others are overloaded too, and it says a retry should happen only at the layer immediately above the one rejecting, to avoid a combinatorial explosion. Contrast with your own design: one retrying layer, with the budget enforced there.

**Criticality and per-customer limits.** The book's four criticality values are CRITICAL_PLUS, CRITICAL (the default for production traffic), SHEDDABLE_PLUS (the default for batch) and SHEDDABLE. Criticality propagates down the call tree by default and is set close to the user. An overloaded task rejects lower criticalities sooner, with higher utilisation thresholds for higher ones (the book gives no numbers), and per-customer quotas ensure that in a global overload the customer who exceeded their allocation sees the errors. A model with **illustrative** thresholds:

```python
THRESHOLDS = {'CRITICAL_PLUS': 1.00, 'CRITICAL': 0.95, 'SHEDDABLE_PLUS': 0.85, 'SHEDDABLE': 0.75}   # illustrative

def shed_plan(offered, capacity):
    """Admit classes in order of criticality; a class is admitted only while total utilisation stays under its threshold."""
    admitted, used = {}, 0.0
    for cls in THRESHOLDS:                                   # most critical first
        room = max(0.0, THRESHOLDS[cls] * capacity - used)
        admitted[cls] = min(offered.get(cls, 0.0), room)
        used += admitted[cls]
    return admitted
```

For a capacity of 100 and an offered load of 130:

| Class | Offered | Admitted |
|---|---|---|
| CRITICAL_PLUS | 13 | 13 |
| CRITICAL | 52 | 52 |
| SHEDDABLE_PLUS | 39 | 20 |
| SHEDDABLE | 26 | 0 |

The check confirms two properties on random inputs: total admitted never exceeds the capacity, and a lower class is never admitted while a higher one is being rejected. The cost of the model is also visible: the thresholds leave headroom unused. The book's own signal for a task's utilisation is mostly CPU, with an "executor load average" (the count of active threads, smoothed) as the most generally useful one, and the case against modelling capacity as queries per second is that request cost varies by client and over time, so measure capacity in resources.

---

## 6. Deep Dive 3: Cascades and the Way Out

How one overloaded component takes down the rest, from the same chapter:

- **Capacity loss redistributes load.** Cluster B fails and its traffic goes to cluster A, which now gets 1,200 QPS instead of 1,000, runs out of resources, and serves fewer successful requests than before.
- **Resource exhaustion feeds on itself.** More in-flight requests use more RAM; a Java service's garbage collector then burns CPU (the "GC death spiral"); less CPU slows requests, which raises in-flight count. A shrinking cache hit rate sends more requests to the backend. The book notes the causal chain during an outage is rarely fully diagnosed, and gives an example that runs from a poorly tuned GC to a backend failing health checks.
- **Health checks can kill the service.** If half the tasks are starting up and the other half are overloaded and failing health checks, the scheduler's restarts make things worse; the book suggests temporarily disabling health checks, and separating process health (for the scheduler) from service health (for the load balancer).
- **Caches become capacity.** A *latency cache* lets a service meet its load with an empty cache; a *capacity cache* does not. Caches added for speed often end up as hard dependencies, which is the paper's "cache loss" case again.
- **Intra-layer calls form cycles.** Backends that proxy to each other are exposed to distributed deadlock and to proxying that increases exactly when load is high. The book recommends always going downward in the stack: tell the client to retry elsewhere instead of proxying.
- **Triggers** the book lists: process death, process updates that touch many tasks at once, new rollouts, organic growth, planned drains, request-profile changes, and loss of slack CPU that you were treating as a safety net.

**Recovery, in the book's order.** Increase resources if you have idle ones (it may not suffice in a death spiral); stop health-check failures; restart servers that are wedged only after identifying the cause, canarying the change and doing it slowly (a cold cache can make a restart worse); and, as the large hammer, **drop traffic**: fix the trigger, cut load enough that crashing stops (the book says to consider being aggressive and letting through 1% if the whole service is crash-looping), let tasks become healthy, then ramp up gradually so caches warm. Use lower-priority shedding first if you have it. If the cause is not fixed, the collapse returns as soon as the traffic does. Compare with section 4: cutting to 100 QPS held for 140 seconds works; cutting to 140 QPS and restoring early does not.

---

## 7. Shedding in Production: Four Operational Costs

From Amazon's Builders' Library article on load shedding (read 2026-11-26):

1. **False positives.** Shedding when the service actually had capacity is an availability loss you caused. Amazon aims for a false-positive rate of zero; a regular non-zero rate means the shedder is too sensitive or hosts are being constantly overloaded (a balancing or scaling issue).
2. **Metrics pollution.** Rejections are fast, so if 60% of traffic is shed, median latency can look excellent while accepted requests are slow. Keep shed requests out of the latency metric and count them separately.
3. **It can blind autoscaling.** If load shedding trips at about the same CPU target as reactive scaling, shedding holds CPU down and the scaler never sees the signal.
4. **It hides headroom.** A fleet with a shedder can run closer to its rejection point than CPU suggests, so capacity for losing an Availability Zone has to be tested rather than inferred.

The article's other advice is the test discipline of section 4: load test past the break and watch whether goodput plateaus; an availability that falls rapidly to zero as load rises is the sign that shedding is missing; and measure client-perceived as well as server-side availability and latency.

---

## 8. What Studies of Real Outages Say

Huang et al. (OSDI 2022, read in part 2026-11-26) studied public incident reports and report 22 metastable failures from 11 organisations, including at least 4 of 15 major outages at AWS over the preceding decade. In their data, retry policy is the most common sustaining effect (over half the studied incidents), direct load shedding was used to recover in over 55% of cases, about 45% of triggers were engineer errors such as bad configuration or deployments, and about 35% were load spikes (some incidents had more than one trigger). Outages ran from 1.5 to 73.53 hours, with 4 to 10 hours the most common range among those reporting durations. The paper also adds that a trigger can reduce capacity, not only raise load, and that background work such as garbage collection can sustain a failure by degrading capacity. These are one paper's counts from public reports, with the authors' stated caveats about report detail; use them as orientation, not as base rates for your system.

---

## 9. Failure Modes

| Failure | Effect | Mitigation |
|---|---|---|
| retries during overload | the offered load stays above capacity after the trigger is gone | one retrying layer, a budget, jittered backoff; and discard abandoned work |
| FIFO queue full of timed-out work | goodput near zero with the CPU busy | newest-first or skip stale queries; propagate deadlines and cancel |
| cheap rejections that are not cheap | the backend collapses at 2x load | client-side throttling; reject earlier in the stack |
| shedding that is too sensitive | false positives and lost availability | tune from data; alarm on the shed rate |
| cache loss on a look-aside cache | database overload, the cache cannot refill | read-through cache with a permissive fill timeout; warm before taking traffic; slow ramp |
| deadlines far above mean latency | a few doomed requests take every thread | deadlines near the useful bound; fail fast |
| crash loop | each restart is hit with the whole load | cut traffic to what the healthy fraction carries, ramp up |
| health checks that restart overloaded tasks | capacity falls as load rises | separate process and service health; disable temporarily |
| operator drops load too briefly | the system re-enters the loop when load returns | hold the cut until goodput is back, restore gradually |

---

## 10. Pitfalls Checklist

1. **Reading "the trigger ended" as "the incident ended".** The sustaining effect is the incident.
2. **Calling a retry budget a fix.** At 280 QPS into a 300 QPS database a 10% budget still never recovers in the model.
3. **A queue of abandoned work.** FIFO with no cancellation serves dead requests while live ones time out.
4. **Treating rejection as free.** At a 50% rejection cost, 2x load means zero goodput.
5. **Measuring load in QPS.** Request cost changes; use CPU and queueing delay.
6. **Averages for latency under bimodal failure.** 5% of requests holding a thread to a 100-second deadline fails 80% of traffic.
7. **Restoring load as soon as the dashboard turns green.** Hold the cut, then ramp.
8. **Restarting into a cold cache.** It can add the load you were trying to remove.
9. **Never exercising the degraded mode.** The book's warning: the code path you never use is the one that often does not work.
10. **A load test that stops at capacity.** Test beyond the break, with a trigger, and see whether the system quiesces.

---

## Drills

1. A database handles 300 QPS and the application retries once after a 1-second timeout. What load is safe against any trigger, what retry rate can a system at 280 QPS absorb, and how are they derived?
2. A 90% cache hit rate lets 3,000 QPS be served in front of a 300 QPS database. What is the amplification after cache loss, and why can a look-aside cache not refill during the overload?
3. In the trigger table, why does a 1-second outage tip the system at 250 QPS but not at 200 QPS?
4. Why does disabling retries 30 seconds into the collapse take 643 seconds in the model, and what would cut that to zero?
5. Compute the goodput of a backend with capacity 1,000, offered 2,000, when a rejection costs 50% of serving. What changes if the clients throttle at `K = 2`?
6. A frontend has 1,000 threads, 1,000 QPS and 100 ms requests; 5% never complete. What share is served with a 100-second deadline and with a 10-second one?
7. A fleet healthy at 10,000 QPS crash-loops at 11,000. Why does dropping to 9,000 not help, and what load does the book say to drop to when 10% of tasks are healthy?
8. Give one reason each that load shedding can hurt: false positives, autoscaling, latency metrics, and AZ headroom.

---

## Homework

1. Add a second retry attempt and an exponential backoff with full jitter to `simulate`; rerun `trigger_table` and say whether the hidden capacity changes.
2. Add a bounded queue (reject when full) and a CoDel-style rule on time in queue; compare with LIFO and with skipping abandoned work in `defence_table`.
3. Add a second database behind the first and a failover rule that sends retries there; measure whether the failure becomes contagious.
4. Model the look-aside cache from the paper: a 90% hit rate, a cache loss, and a fill path that times out; compare a read-through cache with a permissive fill timeout.
5. Run `throttle_equilibrium` with a rejection cost: charge the backend `r` per rejected request and find `K` that maximises goodput at 3x offered load.
6. Read the Bronson et al. paper's section 3 and section 4 end to end and write down which of its recommended techniques your last system implements.

---

## Sources

All read 2026-11-26.

- Bronson, Aghayev, Charapko, Zhu, *Metastable Failures in Distributed Systems* (HotOS 2021), sigops.org/s/conferences/hotos/2021/papers/hotos21-s11-bronson.pdf. Read in full except the references. Source for the retry and look-aside examples and numbers (300, 280, 560, 150, 20, 3,000, 10x), the stable, vulnerable and metastable states, hidden versus advertised capacity and trigger intensity.
- Huang et al., *Metastable Failures in the Wild* (OSDI 2022), usenix.org/system/files/osdi22-huang-lexiang.pdf. Read the abstract, introduction, section 2 (including Table 1 and the findings on triggers, sustaining effects and mitigation) and the start of section 3; sections 4 to 6 were not read.
- Beyer, Jones, Petoff and Murphy (eds.), *Site Reliability Engineering*, chapter 21 *Handling Overload*, sre.google/sre-book/handling-overload/. Read in full. The rejection-probability equation is an image on the page and was not read as text.
- *Site Reliability Engineering*, chapter 22 *Addressing Cascading Failures*, sre.google/sre-book/addressing-cascading-failures/. Read through the immediate-steps section ("Enter Degraded Modes" onward not read).
- Amazon Builders' Library (AWS Builder Center), *Using load shedding to avoid overload*, aws.amazon.com/builders-library/using-load-shedding-to-avoid-overload/. Read in part (through the discussion of automatic scaling and Availability Zone failure; the remainder was not read).

## Further reading (not consulted)

The Netflix concurrency-limits work; Facebook's CoDel-and-LIFO queue discipline write-ups; the original CoDel paper (Nichols and Jacobson); the Universal Scalability Law papers the Amazon article cites; Google's SRE Workbook chapters on managing load. None were read for this revision, and the simulator here is this lesson's own model, not a reproduction of any of them.

*Last reviewed: 2026-11-26.*
