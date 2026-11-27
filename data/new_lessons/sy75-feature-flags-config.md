# Lesson 75 — Case Study: Feature Flags and Config Service

> **Priority:** ★★★☆☆ (proposed; the curriculum data holds the final rating) — flags are how every large service ships code without shipping risk, and the interview question is rarely "build one" but "how does a flag turn off in seconds, and what if the flag service is down".
>
> **Study time:** 55 minutes. **Do this after:** Caching Patterns and Consistent Hashing; Overload, Load Shedding and Cascading Failures; Scaling Patterns I: Reads, Writes and Contention.
>
> **Level:** extended.

A feature flag is a function from a request to a value, decided by configuration instead of code. This lesson builds one in three parts, each checked by script in `test/lesson_code/sy75_check.py`: how a flag is evaluated (rules, a percentage rollout by hashing, a kill switch), how the configuration reaches thousands of servers (conditional polling, a last-known-good copy that never throws), and how long a change takes to arrive (a propagation simulation). Capacity numbers come from `capacity_check_j.py`. No operator's engineering material was read (see Sources).

---

## 1. Mental Model

> **Evaluation is local and fast; distribution is where the engineering is. The flag service never sees a request; it only publishes a versioned snapshot, and every server decides for itself with a pure function of that snapshot and the request.**

- **A flag evaluation must never fail the request.** If the snapshot is missing, stale or malformed, the caller's own default is the answer.
- **A percentage rollout is a hash, not a coin.** The same user must land in the same bucket every time, on every server, and growing from 5% to 25% must add users, never swap them.
- **Different flags need different salts,** or the same unlucky 5% of users see every experiment.
- **The time to turn something off is the time to distribute a snapshot,** which is set by the polling interval, not by how fast the operator clicks.
- **The service's load is polls, not evaluations:** thousands per second against millions.

*Visual (planned): users as dots in a 100 x 100 grid, a slider that grows the rollout from 0 to 100% with the dots lighting up and never going out, and a second flag in another colour with an independent split. Not built yet.*

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "roll out to 5%, then 25%, then everyone" | hash the user id with a per-flag salt into 10,000 buckets; serve if the bucket is below the percentage (section 4) |
| "turn it off immediately if errors spike" | a kill switch checked before everything else; time to take effect is the propagation interval (section 6) |
| "the flag service is down" | clients keep the last good snapshot and fall back to a default compiled into the caller; never let evaluation throw (section 5) |
| "a million flag checks per second" | evaluate in-process from a local snapshot; the service sees polls |
| "the same user must see the same experience" | stable hashing on a user id, and for anonymous visitors a stable device or cookie id |
| "two experiments must not interfere" | distinct salts per flag, and check the overlap is about the product of the percentages |
| "a bad config reached everyone at once" | stage the rollout of the config itself and validate before publishing |

---

## 3. Requirements and Capacity

**Functional.** Define flags with a default, optional targeting rules and an optional percentage rollout; change them without a deploy; evaluate them in services and clients; turn any flag off quickly. **Out of scope:** an experiment-analysis pipeline, an audit UI, per-environment promotion, client-side SDKs for browsers and phones (the same idea with a different delivery path).

**Non-functional.** Evaluation must add negligible latency and no new failure mode; a change must reach every server within a known bound; the service going down must not take the fleet with it.

**Capacity estimate.** Every input is an assumption of this lesson (marked *assumed*); every result is reproduced by `capacity_check_j.py` (letter shared with `sy77`).

| Input | Value |
|---|---|
| application servers polling | 50,000 *(assumed)* |
| polling interval | 30 seconds *(assumed)*, with 5 seconds as the alternative |
| size of the full snapshot | 200 KB *(assumed)* |
| size of an unchanged ("not modified") reply | 300 bytes *(assumed)* |
| publishes per hour | 10 *(assumed)* |
| requests per second across the fleet | 100,000, each evaluating 20 flags *(assumed)* |
| relay tier | 100 relays, each serving 500 servers *(assumed)* |

| Result | Arithmetic | Value |
|---|---|---|
| polls arriving at the service | 50,000 / 30 | 1,667 per second (10,000 per second at 5 s) |
| evaluations per second | 100,000 x 20 | 2,000,000, all local: 1,200 times more than the polls |
| bandwidth if every poll returned the whole snapshot | 1,667 x 200 KB | 333 MB/s |
| bandwidth when unchanged polls return a short reply | 1,667 x 300 B | 0.5 MB/s: 667 times less |
| cost of one publish | 50,000 x 200 KB | 10 GB, spread over one polling interval: 333 MB/s for 30 seconds |
| ten publishes an hour | 10 x 10 GB | 100 GB per hour, 27.8 MB/s on average |
| the same publish through the relay tier | 100 x 200 KB leaves the origin | 20 MB: 500 times less |
| time for a change to reach the fleet, interval 30 s / 5 s | uniform phases: half the interval on average, one interval at most | 15 s mean, 30 s max / 2.5 s mean, 5 s max |

Three conclusions. **Conditional polling makes steady state nearly free and a publish expensive:** 0.5 MB/s when nothing changes, but every change makes the whole fleet fetch the whole body inside one interval, exactly as if every poll were a full fetch (333 MB/s for 30 s). **The fix for the expensive part is a relay tier, not a faster origin:** 100 relays cut the origin's bytes per publish from 10 GB to 20 MB in this model (and add a hop of delay that the model does not count). **The polling interval is a dial between load and reaction time:** a 6x shorter interval is 6x the polls (10,000 per second) for a 6x faster kill switch (5 s at worst).

---

## 4. Evaluation: Rules, Hashing and a Kill Switch

```python
import hashlib

def bucket(flag_key, salt, unit_id, buckets=10000):
    """A stable bucket in [0, buckets) for this unit and flag: the same on every server, every time."""
    digest = hashlib.sha256(f"{salt}:{flag_key}:{unit_id}".encode()).digest()
    return int.from_bytes(digest[:8], 'big') % buckets

def evaluate(flag, ctx):
    """Returns (value, reason). Order: kill switch, targeting rules, percentage rollout, default."""
    if not flag.get('enabled', True):
        return (flag['default'], 'DISABLED')
    for rule in flag.get('rules', []):
        if all(ctx.get(attr) in allowed for attr, allowed in rule['when'].items()):
            return (rule['serve'], 'TARGETING_MATCH')
    rollout = flag.get('rollout')
    if rollout and ctx.get('id') is not None:
        if bucket(flag['key'], flag['salt'], ctx['id']) < rollout['percent'] * 100:
            return (rollout['serve'], 'SPLIT')
    return (flag['default'], 'DEFAULT')
```

The reason strings (`DISABLED`, `TARGETING_MATCH`, `SPLIT`, `DEFAULT`) are among the reason values the OpenFeature specification lists, chosen here so the model's output reads like a real client's; the bucketing, the 10,000 buckets and the order of checks are this lesson's design, not a standard.

What the check proves, with a deterministic hash so it can use exact tests:

- **A ramp only adds users.** For 0, 1, 5, 25, 50 and 100 percent over 60,000 ids, each exposed set contains the previous one, and each size is within five binomial standard deviations of the target. 0% exposes nobody and 100% everybody. Swapping `<` for `<=` would put bucket 0 into a 0% rollout.
- **The hash is uniform enough.** 200,000 ids fall into 100 groups of buckets, none further than five standard deviations from 2,000.
- **Flags are independent only because of the salt.** Two flags at 50% with different salts overlap in about 25% of users (within 1%); two flags with the same salt expose identical sets. Dropping the salt or the flag key from the hash string is caught.
- **The order is the contract.** A matching rule beats the rollout; a rule needs every one of its attributes; a missing user id cannot be bucketed and falls to the default; the kill switch beats every rule, including a targeted VIP; a rule with no conditions matches everyone (a trap, listed in the pitfalls).

---

## 5. Distribution: Conditional Polling and a Client That Never Throws

```python
class ConfigServer:
    """Holds one versioned snapshot. The version doubles as the entity tag."""
    def __init__(self, snapshot, outages=()):
        self.version, self.snapshot, self.outages = 1, snapshot, list(outages)
        self.fetches = self.full_sends = 0

    def publish(self, snapshot):
        self.version += 1
        self.snapshot = snapshot

    def fetch(self, etag, now):
        if any(s <= now < e for s, e in self.outages):
            raise ConnectionError('config service unreachable')
        self.fetches += 1
        if etag == self.version:
            return (304, None, self.version)                  # unchanged: a header and no body
        self.full_sends += 1
        return (200, self.snapshot, self.version)


class FlagClient:
    def __init__(self, server, poll_interval, phase=0.0):
        self.server, self.interval, self.next_poll = server, poll_interval, phase
        self.etag, self.flags, self.failed = None, {}, False

    def tick(self, now):
        """Call from a timer. Polls when due; on failure keeps the last good snapshot."""
        if now < self.next_poll:
            return
        self.next_poll = now + self.interval
        try:
            status, snapshot, etag = self.server.fetch(self.etag, now)
        except ConnectionError:
            self.failed = True
            return
        self.failed = False
        if status == 200:
            self.flags, self.etag = snapshot, etag

    def get(self, key, ctx, default):
        """Never raises. Returns (value, reason); the caller's default on any abnormal case."""
        try:
            flag = self.flags.get(key)
            if flag is None:
                return (default, 'ERROR')                     # nothing loaded yet, or an unknown flag
            value, reason = evaluate(flag, ctx)
            return (value, 'STALE' if self.failed else reason)
        except Exception:
            return (default, 'ERROR')
```

The conditional fetch is the standard HTTP one: RFC 9110 describes `If-None-Match` as the way a client updates a stored response using its entity tags, so that the server can reply `304 Not Modified` when the stored copy still matches. Here the entity tag is the integer version, the lesson's simplification of an opaque tag.

The client's guarantees follow the OpenFeature specification's rules for a client: evaluation takes a flag key, a required default value and a context; abnormal execution (network failure, unhandled error) must return the default and must not throw. The `STALE` reason is the specification's "non-authoritative or possibly out of date"; using it whenever the last poll failed is this lesson's choice. The check shows: before the first fetch the caller's default comes back with reason `ERROR`; an unknown key does the same; three conditional polls send no repeated body; during an outage the last good value is served as `STALE`; after recovery the new value is seen and the label clears; and a snapshot whose flag is malformed never raises out of `get`.

---

## 6. Deep Dive: How Fast Can You Turn Something Off

The kill switch is a published snapshot with `enabled` false. It reaches each server at that server's next poll, so the delay is the time from the publish to a uniformly random point in the polling cycle:

| Interval | Mean delay | Worst case | Polls per second (50,000 servers) |
|---|---|---|---|
| 30 s | 15 s | 30 s | 1,667 |
| 5 s | 2.5 s | 5 s | 10,000 |

The check simulates 600 clients with random phases, publishes a kill switch and measures when each returns the `DISABLED` reason; the mean is within 5% of half the interval and no client exceeds one interval (plus the quarter-second simulation step). It assumes no failures: a client in an outage keeps the old snapshot until it can poll, which is the price of "never throw". If a flag must turn off faster than polling allows, the options are a push channel from the service (not modelled here and not sourced) or a second, much shorter poll for a small set of kill switches only. Both add load and failure modes; say so rather than claim the number.

**A bad config.** The fleet applies whatever snapshot it receives. Two defences matter more than speed: validate before publishing (the model has no validator) and publish the config itself in stages, so a bad snapshot meets a fraction of servers first. The nested ramp of section 4 is the same idea for users; staging the snapshot is not modelled.

---

## 7. Failure Modes

| Failure | What goes wrong | What the design does |
|---|---|---|
| flag service down | no new snapshots | clients keep serving the last good one, labelled `STALE`; new servers need a compiled-in default |
| snapshot corrupt or flag malformed | an evaluation might raise | `get` catches it and returns the caller's default with reason `ERROR` |
| unknown flag key | typo or flag not yet published | the caller's default and `ERROR` |
| rollout percent changed downward | users who had the feature lose it | nested buckets make this a clean cut, but it is a visible change for those users |
| same salt on two flags | experiments are perfectly correlated | distinct salts per flag |
| rule with no conditions | matches everybody | the check pins this behaviour; validate rules before publishing |
| whole fleet fetches a big snapshot at once | origin bandwidth burst after each publish | a relay tier or jittered polling (relay modelled only as arithmetic) |
| polling too slow for a kill switch | harm continues for up to one interval | shorten the interval for a small set of kill switches |

---

## 8. What Real Systems Did

No flag vendor's or company's engineering material was read for this lesson. The two standards it uses are the OpenFeature specification (the client rules on defaults, no exceptions, reasons and error codes) and RFC 9110 (conditional requests). The bucketing, the rule order, the relay tier, the polling model and every number are this lesson's own design and assumptions; they are labelled as such and are not claims about how any product works.

---

## 9. Pitfalls Checklist

1. **A flag check that can throw.** The caller's default must be the answer to any failure.
2. **A random number instead of a hash.** The same user flips between experiences on every request.
3. **Reusing one salt.** Two flags become one flag.
4. **Re-bucketing on every ramp step.** Users swap instead of being added; keep the salt fixed while ramping.
5. **A rule with no conditions.** It is "everyone", and it silently overrides the rollout.
6. **Treating the interval as free.** Shorter polling multiplies load and does not help a client in an outage.
7. **Counting evaluations as service load.** They are local; polls are the load.
8. **A kill switch that depends on the system that is failing.** If the snapshot cannot be fetched, the flag cannot turn off.

---

## Drills

1. 50,000 servers poll every 10 seconds. How many polls per second, and what is the mean and worst-case time for a change to arrive?
2. A snapshot is 500 KB and 20,000 servers poll every 20 seconds. Bandwidth if every poll returned the body; bandwidth if unchanged polls return 300 bytes; bandwidth during the 20 seconds after a publish.
3. Explain, using the nested-ramp check, why growing a rollout from 5% to 25% adds users and never moves anyone out. What changes if the salt is regenerated at each step?
4. Two experiments, each at 20%, use distinct salts. About what share of users sees both? What if they share a salt?
5. The service is unreachable at server start. What does the first evaluation return, with which reason, and how does a team make that default safe?
6. Change `<` to `<=` in the bucket comparison. What does a 0% rollout do, and which check fails?
7. A kill switch must take effect within 2 seconds at 50,000 servers. Price the polling answer and name one alternative with its cost.
8. A rule `{'when': {}, 'serve': 'on'}` appears in a flag. What does it do, and where in the lesson's order would it have to sit to stay harmless?

---

## Homework

1. Add a validator to the model: reject a snapshot with a rule that has no conditions, a rollout percent outside 0 to 100, or a flag without a default. Write the checks first.
2. Add jitter to `FlagClient.next_poll` and measure, by simulation, how it changes the origin's bandwidth burst after a publish and the worst-case delay.
3. Implement the relay tier from section 3 as a second `ConfigServer` the clients poll, and measure how the mean propagation delay changes when each hop polls every 30 seconds.
4. Read the OpenFeature client evaluation section on evaluation context and the handling of the targeting key, and extend `evaluate` with an error code for a missing id.

---

## Sources

All read on 27 November 2026.

- OpenFeature, *Specification: Section 1, Flag Evaluation* (github.com/open-feature/spec, `specification/sections/01-flag-evaluation.md`, read in part: the client's typed evaluation methods taking a flag key, a required default value and an evaluation context; the rule that a client must not throw and must return the default value on abnormal execution; the reason and error code fields of evaluation details).
- OpenFeature, *Specification: Types* (`specification/types.md`, read in full): the list of reason values (including `TARGETING_MATCH`, `SPLIT`, `DEFAULT`, `DISABLED`, `STALE`, `ERROR`) and the error codes.
- IETF, *RFC 9110, HTTP Semantics* (rfc-editor.org/rfc/rfc9110.txt, read in part: the `If-None-Match` section and its use in conditional GET with a `304 (Not Modified)` response).
- Not read: any feature-flag or configuration product's documentation or engineering writing, the OpenFeature provider specification beyond its list of reasons, and any study of rollout practice.

## Further reading (not consulted)

- The OpenFeature provider and evaluation-context sections.
- Engineering write-ups of flag and configuration systems at large companies.
- Literature on progressive delivery and canary analysis.

*Last reviewed: 27 November 2026.*
