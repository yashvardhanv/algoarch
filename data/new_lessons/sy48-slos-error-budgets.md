# Lesson 48 — SLOs, SLIs and Error Budgets

> **Priority:** ★★★★☆ — reliability prompts end with "how would you know it's working, and when do you page someone?", and the answer is an SLO with an alert you can defend.
>
> **Study time:** 60 minutes. **Do this after:** Observability: Metrics, Tracing & Alerting, and Resilience: Rate Limiting & Circuit Breakers.
>
> **Level:** core.

Observability gave you the metrics and a one-paragraph definition of SLI, SLO and error budget. This lesson is the engineering behind that paragraph. It shows how to write an SLI so that the budget is a count of bad events you can subtract from, how request-based budgets and dependency chains change the arithmetic, and how six ways of alerting on a budget differ when you run them against the same six incidents. The last part is the one interviewers probe: "your page fires at 2 a.m. for something that cost 0.02% of the month, and misses the slow leak that costs 20%; fix the alert." Every number below comes from code in this file, and the figures that appear in Google's SRE Workbook are checked against it.

---

## 1. Mental Model

> **An SLO turns "is it reliable enough?" into arithmetic. An SLI is a ratio of good events to total events; the SLO is the target for that ratio over a window; the error budget is the number of bad events the window allows. Alerts, release gates and prioritisation are all functions of how fast you are spending that number.**

What follows from it:

- **Count events, not minutes.** A ratio SLI makes the budget a number of failed requests. A 99.9% SLO over 3 million requests is 3,000 failures; an incident that causes 1,500 costs half the budget, whatever the clock says.
- **The budget is spent at a rate, and the rate is the signal.** Burn rate is the error ratio divided by the budget ratio; at 1 you exhaust exactly the budget at the end of the window, at 1,000 you exhaust it in about 43 minutes of a 30-day window.
- **An alert is a classifier with four numbers to trade:** precision, recall, detection time and reset time. A good alert design is a point on that surface, not a threshold.
- **A target below 100% is a decision, not a failure.** Someone with authority over feature velocity owns it, and a written policy says what happens when the budget is gone.
- **Dependencies set a ceiling.** You cannot promise more nines than the chain of things you depend on, unless you design around them.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "define SLIs for this service" | specification first (what the user cares about), then an implementation (where and how you measure), per component type |
| "how many nines can we promise?" | multiply serial dependencies; do not assume replicas fail independently |
| "how do you alert on the SLO?" | multiwindow, multi-burn-rate; name what simpler rules miss |
| "what happens when we run out of budget?" | the error budget policy: who does what, and who arbitrates a disagreement |
| "an outage at peak versus at night" | request-based budgets weight by traffic; a time-based count does not |
| "low-traffic service, alerts are noisy" | synthetic traffic, combine related services, change the client, or relax the SLO |
| "five nines" | a total outage exhausts the budget in seconds; defend it by limiting blast radius, not by alerting |
| "why not 100%?" | cost grows steeply, users cannot perceive it, and every change would break it |

---

## 3. SLIs: Specification, Implementation, and Where You Measure

Google's SRE Workbook (read 2026-11-26) recommends writing an SLI as the ratio of **good events to total events**, so it ranges from 0% (nothing works) to 100% (nothing is broken) and the error budget is simply 100% minus the SLO. It then splits the work in two:

- **SLI specification:** the outcome you believe matters to users, independent of how it is measured ("the proportion of home-page requests that load in under 400 ms").
- **SLI implementation:** the specification plus a way to measure it. One specification has several implementations that differ in **quality** (how closely they track the user's experience), **coverage** (how many users they see) and **cost**.

Candidate measurement points, from cheapest to closest to the user: application server logs, load-balancer metrics, black-box probes, and client-side instrumentation. A server-side success rate is blind to every failure that never reached the server, which is why the Observability lesson told you to measure at the point closest to the user that you control. The Workbook's own worked example uses load-balancer metrics because they were already available and are closer to the user than server logs.

The kinds of SLI it suggests, by component type:

| Component | SLIs worth considering |
|---|---|
| Request-driven (an HTTP or RPC service) | availability (good responses over all), latency (requests faster than a threshold over all), quality (undegraded responses over all, if the service degrades gracefully) |
| Pipeline | freshness (data updated within a threshold), correctness (records producing the right output), coverage (jobs or records processed) |
| Storage | durability (records written that can still be read), plus latency and availability |

Three working rules from the same sources:

1. **Use thresholds, not averages, for latency.** An average hides a long tail. The SRE book's example is a system where a typical request takes about 50 ms while 5% are twenty times slower, and the average barely moves. Use several grades: for example, 90% of requests faster than one threshold and 99% faster than a larger one.
2. **Keep the set small.** The book suggests a handful of indicators, and the Workbook says five or fewer SLI types. If you cannot win a prioritisation argument by quoting an SLO, it is probably not worth having.
3. **Group request types into classes instead of one SLO per endpoint.** The Workbook's example buckets: CRITICAL (login-like requests, 99.99%), HIGH_FAST and HIGH_SLOW (99.9% with different latency thresholds), LOW (99%, no latency target) and NO_SLO. These are an illustration of the technique, not values to copy.

---

## 4. Budget Arithmetic

The code defines the constants used everywhere below: a 99.9% SLO over a 30-day window, with time in minutes.

```python
import math

SLO = 0.999
PERIOD = 30 * 24 * 60            # minutes in the 30-day window
BUDGET_RATE = 1 - SLO            # allowed error ratio

def allowed_failures(requests, slo):
    """The error budget as a count of events."""
    return math.floor(requests * (1 - slo) + 1e-9)

def burn_rate(error_ratio, slo=SLO):
    """How many times faster than 'exactly the whole budget by the end of the window' this is."""
    return error_ratio / (1 - slo)

def hours_to_exhaust(error_ratio, slo=SLO, period_hours=30 * 24):
    return period_hours / burn_rate(error_ratio, slo)

def budget_spent(window_minutes, burn, period_minutes=PERIOD):
    """Fraction of the whole window's budget consumed by `window_minutes` at `burn`."""
    return burn * window_minutes / period_minutes
```

**Budgets as counts.** The Workbook's worked example has 3,663,253 requests in four weeks. A 97% availability SLO allows `allowed_failures(3663253, 0.97)` = 109,897 failures; "90% of requests faster than 450 ms" allows 366,325 slow ones; "99% faster than 900 ms" allows 36,632. In that example a bad release that caused 14,066 errors spent 12.8% of the availability budget, and a 20-hour database restore that caused about 72,000 errors spent 65.5%. The Workbook's point is how to use the numbers: if the company sees two or three bad releases a year and one server failure in five years, releases cost about twice as much budget on average and are the better thing to fix. The budget turns a debate into a ranked list.

**Burn rate and time to exhaustion.** `hours_to_exhaust` gives the same figures as the Workbook's table:

| Burn rate | Error ratio at 99.9% | Time to exhaust a 30-day budget |
|---|---|---|
| 1 | 0.1% | 30 days (720 hours) |
| 2 | 0.2% | 15 days |
| 10 | 1% | 3 days (72 hours) |
| 1,000 | 100% | 43.2 minutes |

At five nines (99.999%) a total outage exhausts a 30-day budget in 25.92 seconds, shorter than the collection interval of many monitoring systems, so no alert can defend that target. The Workbook's answer is to design so that a 100% outage is very unlikely: roll a change out to 1% of users first, and at a 1% error ratio the same budget lasts 43.2 minutes.

**Request-based budgets weight by traffic.** The SRE book explains that Google defines availability as a request success rate rather than uptime, because a globally distributed service is almost never fully down. A consequence is that **the same outage costs different amounts at different times of day**. With an assumed daily traffic shape (100% of peak at 14:00, 20% at 02:00, averaging 60% of peak) a total outage of ten minutes costs:

```python
def traffic(hour):
    """Assumed daily shape: 100% of peak at 14:00, 20% at 02:00."""
    return 0.6 + 0.4 * math.cos(2 * math.pi * (hour - 14) / 24)

def outage_cost(start_hour, minutes):
    """Share of a 30-day request budget (99.9%) spent by a total outage, when traffic follows `traffic`."""
    per_minute = [traffic(m / 60) for m in range(24 * 60)]
    bad = sum(per_minute[(start_hour * 60 + i) % 1440] for i in range(minutes))
    total = sum(per_minute) * 30
    return bad / (total * (1 - SLO))
```

At 14:00 it costs 38.6% of the budget; at 02:00, 7.7%; a time-based count ("ten of 43.2 permitted minutes") says 23.1% for both. The traffic shape is an assumption, so read the ratio, about five to one, as the effect and not a forecast. This is why request-based SLIs line up with user harm, and why a deploy window at night spends less budget.

**Dependencies set a ceiling.** If every part of a request path has to work, availabilities multiply:

```python
def serial_availability(parts):
    """Every part must work: the availabilities multiply (independent failures assumed)."""
    out = 1.0
    for a in parts:
        out *= a
    return out

def parallel_availability(a, copies):
    """At least one of `copies` independent replicas works."""
    return 1 - (1 - a) ** copies
```

Three components at 99.95%, 99.9% and 99.99% give a path of 99.84%, below every one of them. The Workbook warns against "mathing your way out": two zones of a 99.9% service look like `parallel_availability(0.999, 2)` = 99.9999%, but only if failures are independent, and in practice replicas share dependencies, failure domains and control planes. Add one shared component at 99.95% and the pair is capped at `0.9995 x 0.999999` = 99.9499%, which is the shared component's availability for practical purposes. The Workbook's guidance for a critical dependency is that its reliability should be at least that of the interaction it supports, or you engineer around it with caching, store-and-forward or graceful degradation.

---

## 5. Deep Dive: Which Alert Fires, and When

The Workbook's chapter on alerting (read 2026-11-26) evaluates an alert on four attributes: **precision** (how many alerts were significant), **recall** (how many significant events alerted), **detection time**, and **reset time** (how long it keeps firing after the problem is over). It walks through six rules in increasing fidelity. This simulator runs all six against the same six incidents, at one-minute resolution with constant traffic, against a 99.9% SLO over 30 days.

```python
class Policy:
    """Fires when any (long, short, burn) condition holds: the burn rate over the long window is at least `burn`
    and, if a short window is given, so is the burn rate over the short window. `hold` requires the condition
    to stay true for that many consecutive minutes (the 'for:' clause of a monitoring rule)."""
    def __init__(self, name, conditions, hold=1):
        self.name, self.conditions, self.hold = name, conditions, hold

    def fired(self, errors):
        """errors[t] = error ratio during minute t (constant traffic). Returns a list of booleans."""
        prefix = [0.0]
        for e in errors:
            prefix.append(prefix[-1] + e)
        def mean(t, w):
            lo = max(0, t + 1 - w)
            return (prefix[t + 1] - prefix[lo]) / w          # minutes before the series starts count as error-free
        out, run = [], 0
        for t in range(len(errors)):
            hit = any(mean(t, lg) >= b * BUDGET_RATE - 1e-12 and (sh is None or mean(t, sh) >= b * BUDGET_RATE - 1e-12)
                      for lg, sh, b in self.conditions)
            run = run + 1 if hit else 0
            out.append(run >= self.hold)
        return out

POLICIES = [
    Policy('P1 short window', [(10, None, 1)]),
    Policy('P2 long window', [(36 * 60, None, 1)]),
    Policy('P3 duration', [(1, None, 1)], hold=60),
    Policy('P4 burn rate', [(60, None, 36)]),
    Policy('P5 multi burn', [(60, None, 14.4), (360, None, 6), (3 * 1440, None, 1)]),
    Policy('P6 multiwindow', [(60, 5, 14.4), (360, 30, 6), (3 * 1440, 360, 1)]),
]
```

P1 alerts when the 10-minute error ratio reaches the SLO's own ratio. P2 does the same over 36 hours (5% of the budget). P3 uses a one-minute rate with a one-hour `for:` clause. P4 is a one-hour window at 36x burn (also 5%). P5 combines 14.4x over one hour, 6x over six hours and 1x over three days, which spend 2%, 5% and 10% of the budget; P6 adds a short window to each condition, one-twelfth of the long one, which the Workbook recommends as a guideline. The 14.4 / 6 / 1 values and their window sizes are the Workbook's starting numbers for a 99.9% SLO; `budget_spent(60, 14.4)`, `budget_spent(360, 6)` and `budget_spent(4320, 1)` reproduce 2%, 5% and 10%.

Before simulating, the closed form for a constant error ratio. A burn-rate rule over a window of `w` minutes at threshold `b` trips when the window's mean error ratio reaches `b x (1 - SLO)`, so a constant ratio `e` gets there after `b x (1 - SLO) / e` of the window:

```python
def detection_seconds(error_ratio, window_minutes, burn_threshold, slo=SLO):
    """How long a constant error ratio takes to trip 'burn rate over the window >= threshold'; None if it never does."""
    needed = burn_threshold * (1 - slo)
    if error_ratio < needed:
        return None
    return needed / error_ratio * window_minutes * 60
```

For a total outage (`e = 1`) the 10-minute rule at 1x trips after 0.6 seconds and the 36-hour rule at 1x after 129.6 seconds (the Workbook's "2 minutes and 10 seconds"); the one-hour rule at 36x also takes 129.6 seconds. A 3.5% ratio never reaches the 36x threshold (`detection_seconds(0.035, 60, 36)` is `None`), but it reaches 14.4x on a one-hour window after 24.7 minutes. The simulator below runs at one-minute resolution, so anything under a minute shows as 1 minute.

The incidents:

```python
PRE, POST = 4400, 6000          # error-free minutes before the incident (history) and after it (to measure reset)

def scenario(pattern):
    return [0.0] * PRE + pattern + [0.0] * POST

def evaluate(policy, pattern):
    """(minutes from start of incident to first alert or None, share of the 30-day budget spent by then,
    minutes the alert keeps firing after the incident ends)."""
    errors = scenario(pattern)
    fired = policy.fired(errors)
    first = next((t for t in range(PRE, len(errors)) if fired[t]), None)
    if first is None:
        return None, None, None
    spent = sum(errors[PRE:first + 1]) * 1.0 / (BUDGET_RATE * PERIOD)
    end = PRE + len(pattern)
    last = max((t for t in range(end, len(errors)) if fired[t]), default=end - 1)
    return first - PRE + 1, spent, last - end + 1

SCENARIOS = {
    'blip: 0.1% errors for 10 min': [0.001] * 10,
    'total outage, 5 min': [1.0] * 5,
    'total outage, 60 min': [1.0] * 60,
    '3.5% errors (35x) for 21 h': [0.035] * 1260,
    '0.2% errors (2x) for 3 days': [0.002] * 4320,
    '5 min on, 5 min off for 1 h': ([1.0] * 5 + [0.0] * 5) * 6,
}

def compare_policies():
    """{scenario: {policy name: (minutes to first alert, share of budget spent by then, minutes still firing after)}}"""
    return {s: {p.name: evaluate(p, pat) for p in POLICIES} for s, pat in SCENARIOS.items()}
```

Each cell is the **time to the first alert, with the share of the 30-day budget already spent at that moment**. The incidents cost 0.0% (the blip; precisely 0.02%), 11.6%, 138.9%, 102.1%, 20.0% and 69.4% of the budget respectively.

| Incident | P1 | P2 | P3 | P4 | P5 | P6 |
|---|---|---|---|---|---|---|
| blip: 0.1% errors for 10 min | 10 min (0.02%) | never | never | never | never | never |
| total outage, 5 min | 1 min (2.31%) | 3 min (6.94%) | never | 3 min (6.94%) | 1 min (2.31%) | 1 min (2.31%) |
| total outage, 60 min | 1 min (2.31%) | 3 min (6.94%) | 60 min (138.89%) | 3 min (6.94%) | 1 min (2.31%) | 1 min (2.31%) |
| 3.5% errors (35x) for 21 h | 1 min (0.08%) | 62 min (5.02%) | 60 min (4.86%) | never | 25 min (2.03%) | 25 min (2.03%) |
| 0.2% errors (2x) for 3 days | 5 min (0.02%) | 1080 min (5.00%) | 60 min (0.28%) | never | 2160 min (10.00%) | 2160 min (10.00%) |
| 5 min on, 5 min off for 1 h | 1 min (2.31%) | 3 min (6.94%) | never | 3 min (6.94%) | 1 min (2.31%) | 1 min (2.31%) |

And the reset time, for the 60-minute total outage:

| | P1 | P2 | P3 | P4 | P5 | P6 |
|---|---|---|---|---|---|---|
| minutes the alert keeps firing after a 60-minute outage ends | 9 | 2,157 | 0 | 57 | 4,315 | 359 |

Reading it, policy by policy:

- **P1 (short window at the SLO ratio)** detects everything, which is the trouble: it also pages on the blip, which spent 0.02% of the budget, and on a 2x burn five minutes in. A service running at exactly its SLO ratio would page continually. The Workbook's example of the cost is up to 144 alerts a day while still meeting the SLO. Good recall, poor precision.
- **P2 (36-hour window)** fixes precision by waiting for 5% of the budget to go, and pays in reset time: after a total outage the alert keeps firing for 2,157 minutes, about 36 hours, because the long window still contains the incident. The Workbook calls the reset time very poor.
- **P3 (the `for:` clause)** has the same detection time (60 minutes) for a total outage and for a 0.2% error rate, so by the time it fires on the total outage 138.89% of the budget is gone. Intermittent trouble resets its timer: the five-on-five-off spikes, which spend 69.4% of the budget, never alert. The Workbook recommends against duration clauses for SLO alerting for these reasons.
- **P4 (one burn rate)** fires quickly and resets in under an hour (57 minutes here; the Workbook gives 58) but only notices burns of 36x and above. A 3.5% error rate (35x) never alerts and exhausts the whole budget in 20.6 hours (the Workbook says 20.5), and a 2x burn never alerts either. Low recall.
- **P5 (several burn rates)** catches the slow burns through the three-day condition, but that same condition keeps firing for 4,315 minutes, about three days, after a five-minute outage: 5 minutes of total failure is 0.116% of 3 days, above the 0.1% ratio. The Workbook notes the longer reset time and the need to suppress duplicate alerts when several conditions fire together.
- **P6 (multiwindow, multi-burn-rate)** has no false alert on the blip, misses none of the five significant incidents, pages at 2.31% of the budget on outages and 2.03% on the 35x burn, and **stops firing within 359 minutes** because the short window ends the alert when the errors stop. The slowest piece is the ticket-level condition (three days of 1x, with a six-hour short window), which is why its reset is six hours rather than minutes. The check confirms that P6 is the only one of the six with no false alert, no miss, and every reset within six hours.

The Workbook recommends P6 in most cases and says the cost is many parameters to manage. Its remedy: choose the parameters once and apply them to every service instead of tuning each, and group request types into a few classes.

**Where multiwindow breaks down.** Three cases the Workbook calls out:

1. **Low traffic.** With 10 requests an hour, one failed request is a 10% error ratio for that hour, which on the page's arithmetic is a burn rate of 100x (the page itself prints 1,000x; the other figures on that line, 7.2 failed requests allowed in 30 days and 13.9% of the budget for one failure, reproduce, so treat the 1,000x as a slip). Its options: generate synthetic traffic (which can hide real-user failures that the probes do not see), combine related services into one SLO, change the client (retries with backoff and jitter; a fallback path) so one failure matters less, or lower the SLO and accept fewer pages.
2. **Low targets.** At a 90% SLO a 100% outage spends only 1.4% of the budget in an hour, so a page rule that needs 2% in an hour can never fire; the windows need re-tuning.
3. **Extreme targets.** See the 25.92-second figure above.

Visual (planned): the six alert rules as detection-time versus error-rate curves, with the budget spent at each point marked.

---

## 6. The Error Budget Policy and Choosing Targets

An SLO without consequences is a dashboard. The Workbook lists what has to hold before you can run on error budgets: stakeholders have approved the SLO as fit for the product; the people who defend it agree it can be met under normal conditions; the organisation has committed to using the budget for decisions, formalised in a **written policy**; and there is a process for refining the SLO. The policy states who does what when the budget is spent. Its example (the Appendix B policy for a game service, read 2026-11-26) is a useful shape to copy:

| Situation | The example policy says |
|---|---|
| service within its SLO | releases proceed under the normal release policy |
| the error budget for the preceding four weeks is exceeded | halt all changes and releases other than the highest-priority bugs and security fixes until the service is back within its SLO |
| the cause was the team's own bug or a procedural error; a postmortem finds a hard dependency to soften | the team works on reliability |
| the cause was a company-wide network problem, another team's service (which is itself frozen), or out-of-scope users (load tests, penetration testers) | the team may continue feature work |
| one incident consumes more than 20% of the budget over four weeks | a postmortem with at least one top-priority action item |
| disagreement about the calculation or the actions | escalate to a named senior owner for a decision |

Notice what makes it work: it is not a punishment, it names exceptions in advance (so the argument is not held during the incident), and it has an escalation path. The Workbook adds that the policy doubles as a test of the SLO. If product management thinks users suffer long before the policy bites, the SLO is too loose; if engineering cannot defend it without toil, it is too tight.

How to pick the numbers, from the SRE book's chapter on SLOs and the Workbook (both read 2026-11-26):

- **Do not pick a target from current performance.** It may lock you into a target that needs heroics. The Workbook allows starting from current performance if you have no other information and a way to iterate, and recommends rounding down to manageable values.
- **Start looser and tighten.** The book says to start with a loose target you can tighten rather than a strict one you must relax.
- **Keep an internal margin.** An internal SLO tighter than the one you publish gives room to react to chronic problems before users see them.
- **Do not overachieve.** Users build on what you deliver, not what you promise. The book's example is Google's Chubby lock service, where SRE deliberately takes the global instance down in a quarter if it has been too reliable, so that dependants cannot assume it never fails.
- **Choose the window deliberately.** Rolling windows match user memory (a bad last day of the month does not vanish on the first); calendar windows match business planning but leave you guessing about the rest of the period. The Workbook suggests a four-week rolling window as a general default, in whole weeks so that each window has the same weekends, with weekly summaries for prioritisation and quarterly ones for planning.
- **Improve the SLO with evidence.** Compare error budget losses with support tickets and known incidents. Budget loss with no complaints suggests the SLO is too tight or measures the wrong thing; complaints without budget loss mean coverage is missing, and the fix is a tighter SLO or an SLI measured closer to the user. A tighter target you cannot yet meet can be kept as an **aspirational SLO** that the policy says needs no action.

---

## 7. Failure Modes

| Failure | Effect | Mitigation |
|---|---|---|
| SLI measured at the server only | failures before the server are invisible; "99.99%" while users see 97% | measure at the load balancer or client, and compare |
| average latency as the SLI | long tail hidden | threshold SLIs with two grades |
| alert on the raw error ratio | pages on events worth 0.02% of the budget | burn-rate alerts with a significance floor |
| long window only | the alert fires for days after recovery | add the short window |
| `for:` clause as the long window | the same detection time for a total outage as for a minor one; flapping errors never alert | burn rate over a real window |
| one parameter set per service | 100 services, 100 hand-tuned rules, nobody understands them | classes of requests, one parameter set |
| no written budget policy | the budget is spent, nothing changes | an approved policy with owners and escalation |
| SLO tighter than the chain beneath it | permanently out of budget | compute the serial ceiling; degrade gracefully around weak dependencies |
| synthetic probes mask real failures | green dashboard, unhappy users | probes complement, not replace, real-traffic SLIs |

---

## 8. What Real Systems Document

All read 2026-11-26. The SRE Workbook documents ratio SLIs, the specification-implementation split, the four-week example with its budgets, the burn-rate table, the six alerting strategies with their stated pros and cons, the low-traffic, low-target and extreme-target cases, and the request-class buckets. The SRE book documents the SLI, SLO and SLA definitions, the preference for percentiles over means, safety margins and the Chubby example, and request-based availability. Appendix B of the Workbook gives the example error budget policy. **Not claimed:** how any particular company's SLOs are set today; and the simulator's numbers are for this lesson's constant-traffic, one-minute model, not a measurement of any service.

---

## 9. Pitfalls Checklist

1. **Quoting an SLO without its window, its SLI definition and where it is measured.** "99.9%" alone is not a target.
2. **Treating the budget as minutes.** It is events; an outage at peak costs more than at night.
3. **Alerting on error ratio above the SLO's own ratio.** It pages on the blip and on any sustained rate just over the SLO.
4. **Long window with no short window.** It cannot stop paging for hours or days after recovery.
5. **A single burn-rate rule.** It misses the slow leak that spends the budget.
6. **Duration clauses as windows.** A fixed delay, and flapping errors reset them.
7. **Multiplying nines for replicas** and ignoring the shared dependency.
8. **No policy.** The budget is an opinion until someone must act when it is spent.
9. **Picking the SLO from last month's graph.** You commit to heroics.
10. **Ignoring low-traffic services.** One failure is a huge burn rate; decide the remedy before the pager does.

---

## Drills

1. A service handles 3,663,253 requests in four weeks with a 97% availability SLO. How many failures does it allow, and what share does a release that causes 14,066 errors spend?
2. Compute the burn rate and time to exhaustion of a 30-day, 99.9% budget at a 1% error ratio, and the share of the budget spent in one hour at 14.4x.
3. Why does a 99.999% target make alerting nearly useless for total outages, and what does the Workbook suggest instead?
4. A three-day alert window rule keeps firing for three days after a five-minute total outage. Why, and what fixes it without losing the slow-burn detection?
5. Explain why a `for: 1h` clause detects a total outage and a 0.2% error rate in the same time, and why intermittent errors defeat it.
6. Two zones of a 99.9% service share a control plane at 99.95%. What availability can you promise, and why is `99.9999%` wrong?
7. The same ten-minute outage spends 38.6% of the budget at 14:00 and 7.7% at 02:00 in this lesson's model. Why, and what does it say about when to deploy?
8. Write the three rows of an error budget policy: what happens within budget, over budget because of your own bug, and over budget because of a dependency you do not own. Who decides disagreements?

---

## Homework

1. Add a seventh incident to `SCENARIOS` (a 10x burn for 6 hours) and a seventh policy of your own; justify its parameters with `budget_spent`.
2. Replace the constant traffic in `Policy.fired` with the diurnal `traffic` curve: use request counts for the windows (errors divided by requests, not a mean of minute ratios) and rerun the table. What changes at night?
3. Write an SLI specification and two implementations for the rate-limiter or leaderboard service from an earlier lesson, and say what each implementation misses.
4. Pick a service you know, list its serial dependencies, and compute the ceiling on its availability; mark the ones you could degrade around.
5. Draft a one-page SLO document and error budget policy using the Workbook's list of what the documents contain (authors, reviewers, approvers, dates, rationale, escalation path).
6. Read the Workbook's chapter on alerting end to end and write down the one claim you would test in your own system first.

---

## Sources

All read 2026-11-26.

- Beyer, Murphy, Rensin, Kawahara and Thorne (eds.), *The Site Reliability Workbook*, chapter 2 *Implementing SLOs*, sre.google/workbook/implementing-slos/. Read through the section on modelling dependencies; the sections after it were not read.
- *The Site Reliability Workbook*, chapter 5 *Alerting on SLOs*, sre.google/workbook/alerting-on-slos/. Read in full.
- *The Site Reliability Workbook*, appendix B *Example Error Budget Policy*, sre.google/workbook/error-budget-policy/. Read in full.
- Beyer, Jones, Petoff and Murphy (eds.), *Site Reliability Engineering*, chapter 4 *Service Level Objectives*, sre.google/sre-book/service-level-objectives/. Read in full.
- *Site Reliability Engineering*, chapter 3 *Embracing Risk*, sre.google/sre-book/embracing-risk/. Read the risk, availability and error-budget sections; the remainder was not read.

## Further reading (not consulted)

The Workbook's appendix A (an example SLO document) and chapter 3 (SLO case studies); the SRE book's availability table appendix; OpenSLO and similar specification formats. None were read for this revision.

*Last reviewed: 2026-11-26.*
