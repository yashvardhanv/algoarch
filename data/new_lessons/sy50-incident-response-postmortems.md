# Lesson 50 — Incident Response and Blameless Postmortems

> **Priority:** ★★★☆☆ (proposed; the curriculum data holds the final rating) — "tell me about an outage you handled" and "how do you stop it happening again?" are standard senior questions, and the strong answer is a process, not a story about heroics.
>
> **Study time:** 55 minutes. **Do this after:** SLOs, SLIs and Error Budgets, and Overload, Load Shedding and Cascading Failures.
>
> **Level:** extended.

The reliability lessons so far are about how a system behaves. This one is about what people do when it misbehaves at 2 p.m. on a Thursday, and what they do afterwards. An incident has two jobs on two clocks. The first, over minutes, is to stop users being hurt. The second, over days, is to change the system and the team so the same thing is harder to repeat. Teams that blur the two chase root causes while customers wait, or write postmortems that nobody acts on. This lesson takes the process from the Google SRE books, works it on an **invented, clearly illustrative incident**, and tests the arithmetic and the checklist logic with code. It reuses the error-budget arithmetic of the SLO lesson and the retry-loop failure of the overload lesson, so read those first.

---

## 1. Mental Model

> **Run the incident to stop the pain; write the postmortem to change the system. During the incident, mitigate first and diagnose second, with named roles so that one person decides and everyone else does not freelance. After it, write down what happened without blaming anyone, and judge the document by the action items that change things, not by how well it reads.**

What follows from it:

- **Mitigation does not need a root cause.** Customers care that errors stop, not that you understand them. You need to know where the problem is, not exactly why, to roll back, drain a region or shed load.
- **Structure scales response; heroics do not.** A few people with clear roles outperform a crowd of capable people each trying a fix.
- **People act on the information they had.** If a postmortem concludes that someone should have been more careful, it has found nothing fixable. The question that has an answer is why the system let the mistake through.
- **A postmortem is a promise to change something.** Without owned, tracked, verifiable action items it is a story.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "walk me through an incident you handled" | timeline, your role, the mitigation before the diagnosis, what changed afterwards |
| "how would you run a major outage?" | declare early; incident commander, ops lead, communications lead; a shared document; explicit handoffs |
| "the rollback did not fix it" | the trigger is gone but something sustains the failure (retries, a cold cache); cut the loop, shed load |
| "a deploy caused it; whose fault?" | blameless: which checks could have stopped it and why they did not |
| "how do you stop repeats?" | action items that are owned, prioritised, tracked and verifiable, plus preventive changes over training |
| "when do you write a postmortem?" | criteria defined before the incident: user impact, data loss, on-call intervention, long resolution, a monitoring miss |
| "how do you know the service is back?" | a stated exit criterion, such as a period of nominal behaviour |

---

## 3. Running the Incident

### Why an unstructured response fails

The Google SRE book's chapter on managing incidents (read 2026-11-26) opens with an incident that spirals out of control. Three hazards cause it. **A sharp focus on the technical problem** leaves the on-call engineer too busy to think about the larger picture. **Poor communication** means nobody knows what anyone else is doing and business leaders hear nothing. **Freelancing**: a well-meaning engineer pushes a change without coordinating with anyone, and it makes the situation worse. The chapter's point is that everybody was doing their job as they saw it; the process, not the people, was missing.

### Roles, a shared record, and a handoff

The same chapter, and the SRE Workbook's incident-response chapter (read 2026-11-26), set out the shape. The Workbook calls the aims the three Cs: **coordinate** the response, **communicate** within and outside the team, and keep **control** of the incident. The roles:

| Role | Job |
|---|---|
| Incident commander (IC) | holds the high-level state, assigns roles, and by default holds every role not yet delegated |
| Ops lead | applies operational tools to mitigate; the book says the operations group should be the only one modifying the system during an incident |
| Communications lead | the public face: periodic updates to responders and stakeholders, and keeping the incident document accurate |
| Planning (in the SRE book) | longer-term work: filing bugs, handoffs, tracking how the system has diverged so it can be reverted |

The IC keeps a **live incident document**, ideally editable by several people at once and kept somewhere that does not depend on the broken system. The SRE book's advice is explicit: use a template, keep the key facts at the top, and retain it for the postmortem. Command is handed off clearly: the outgoing commander says the incoming person is now the commander and does not leave until they acknowledge. Responders gather in one place (a war room or a chat channel) so decisions and actions are in one record.

When to declare is a decision made before the incident. The SRE book's rule of thumb is that an event is an incident if you need to involve a second team, if customers can see it, or if it is unsolved after an hour of focused analysis. Its stated preference is to declare early and close it out if it turns out simple, rather than start the machinery hours in. The Workbook's principles agree: maintain a clear line of command, designate roles, keep a working record, and declare incidents early and often.

### Mitigate before you diagnose

The Workbook's second case study (read in full) is a Kubernetes cluster-creation outage in one region that ran 6 hours and 40 minutes, drew 41 people into the chat channel, spawned seven task forces and produced 28 postmortem action items. The first responder declared an incident but did not put a formal structure in place; the book says a formal structure arrived about two hours after the first page, when a more experienced responder took command. The finding that matters here is about order. The chapter says an active incident should be handled as: **assess the impact, mitigate the impact, find the root cause, then fix the cause and write the postmortem**. It argues that a *generic mitigation*, a blunt action available before the cause is understood such as rolling back a recent release or draining a region, would have mitigated the outage by about 10 a.m., roughly two hours before it was fixed, and says the right time to build such tools is before the incident. It also says plainly that customers do not care whether you fully understand the cause; they want the errors to stop.

The first Workbook case shows the opposite failure. A team mitigated a quota problem three times without finding the root cause, kept rolling out the release, and did not declare an incident; the chapter says that after the first mitigation it would have been better to hold the rollout until the cause was known. The third case, a datacenter power incident handled well, shows what declaring early and delegating buys.

### Practice, and what to have ready

Incident management skill fades unless used, says the SRE book, so teams use the framework for ordinary cross-team changes and role-play past incidents. The Workbook describes Google's disaster-recovery testing and "Wheel of Misfortune" role-plays, and PagerDuty's weekly failure-injection exercises where a trainee acts as incident commander. Its preparation list is short: choose a communication channel in advance, keep a list of contacts to page, agree the criteria for declaring an incident, and prepare two or three message templates so no one writes the first public update under stress. The PagerDuty case also rotated the commander and on-call engineers every four hours in a response that lasted more than ten hours, and recorded the call so the timeline could be rebuilt.

One more recurring point from the SRE book's emergency-response chapter (read 2026-11-26): its change-induced emergency was a configuration push that crash-looped a fleet because a change judged low risk had gone through a lighter canary than an earlier, riskier push, and the combination of settings it triggered had not been exercised. The lesson it states is to canary regardless of perceived risk. Keep that in mind for the invented incident below.

---

## 4. Deep Dive 1: An Invented Incident, Worked (Illustrative)

Everything in this section is invented for teaching and does not describe a real company. A service, the orders API, takes 2,000 requests per second and has a 99.9% success SLO over 30 days. At 14:02 a configuration push lowers the timeout for calls to a payment provider from 2,000 ms to 200 ms. Calls that need more than 200 ms now time out, clients retry, and the retries keep the service overloaded even after the push is rolled back (the loop from the overload lesson). The timeline, as the incident commander's document would hold it:

```python
def minutes(hhmm):
    """'14:09' -> minutes since midnight."""
    h, m = hhmm.split(':')
    return int(h) * 60 + int(m)

TIMELINE = [
    ('14:02', 'trigger',      'config push lowers the payment-provider timeout from 2000 ms to 200 ms'),
    ('14:03', 'impact_start', 'first checkout requests fail with timeouts'),
    ('14:09', 'page',         'burn-rate alert pages the orders on-call'),
    ('14:11', 'ack',          'on-call acknowledges and starts reading dashboards'),
    ('14:16', 'declare',      'incident declared: customers affected and the payments team is needed'),
    ('14:18', 'roles',        'incident commander, ops lead and communications lead named'),
    ('14:24', 'mitigation',   'rollback of the config push started'),
    ('14:31', 'mitigation',   'rollback complete; errors continue (retries keep the service overloaded)'),
    ('14:38', 'effective',    'shed non-critical traffic and cap retries; errors begin to fall'),
    ('14:52', 'mitigated',    'error ratio back under 0.1% and holding'),
    ('15:22', 'closed',       'exit criterion met: 30 minutes of nominal performance'),
]

def incident_metrics(timeline, exit_criterion_min=30):
    """Intervals in minutes from a timeline of (hh:mm, kind, note). Raises if the events are out of order or a
    required kind is missing. Every interval runs from the start of user impact; 'effective' marks the first action
    that actually moved the error ratio and 'mitigated' the moment the impact ended."""
    t = [(minutes(h), k, n) for h, k, n in timeline]
    if any(b[0] < a[0] for a, b in zip(t, t[1:])):
        raise ValueError('events are not in time order')
    first = {}
    for m, k, _ in t:
        first.setdefault(k, m)
    for need in ('trigger', 'impact_start', 'page', 'ack', 'declare', 'effective', 'mitigated', 'closed'):
        if need not in first:
            raise ValueError('missing event: ' + need)
    return {
        'time_to_detect': first['page'] - first['impact_start'],
        'time_to_ack': first['ack'] - first['page'],
        'time_to_declare': first['declare'] - first['impact_start'],
        'time_to_first_effective': first['effective'] - first['impact_start'],
        'time_to_mitigate': first['mitigated'] - first['impact_start'],
        'time_to_close': first['closed'] - first['impact_start'],
        'exit_criterion_met': first['closed'] - first['mitigated'] >= exit_criterion_min,
    }
```

Computed from that timeline (minutes from the start of user impact at 14:03):

| Interval | Minutes |
|---|---|
| detect (impact to page) | 6 |
| acknowledge (page to ack) | 2 |
| declare | 13 |
| first effective mitigation | 35 |
| mitigate | 49 |
| close | 79 |

What the numbers say, with the information the responders had at each point:

- **Detection was fast and declaration was slow.** The page came 6 minutes after impact, and the incident was declared 13 minutes after impact, 7 minutes after the page, though the SRE book's customer-visibility question was already answered by the alert itself. A page template carrying the declare checklist is the cheap fix, and it appears as an action item below.
- **The rollback was a reasonable first move that did not work.** Reverting the push at 14:24 was the generic mitigation and the right call on the available evidence. It did not help because the trigger was not the sustaining effect: retries kept the service overloaded. The effective action came at 14:38, 35 minutes after impact, and was the load-shedding and retry cap that the overload lesson describes. The postmortem's job is to turn that discovery into a runbook step so that shedding follows a failed rollback at once instead of seven minutes later.
- **The close came after an exit criterion.** The incident was closed at 15:22 because the service held nominal behaviour for 30 minutes after mitigation. The SRE book's example postmortem closes its incident with the same kind of exit criterion, 30 minutes of nominal performance.

### What it cost

The impact is a count of failed requests, as in the SLO lesson: 20% of requests failed for 6 minutes, 35% for the next 29, and 3% for the last 14:

```python
PROFILE = [('14:03', '14:09', 0.20), ('14:09', '14:38', 0.35), ('14:38', '14:52', 0.03)]   # error fraction by interval

def bad_requests(profile, rate_per_s):
    """Failed requests: for each (start, end, error fraction) interval, minutes x 60 x rate x fraction."""
    return sum((minutes(b) - minutes(a)) * 60 * rate_per_s * f for a, b, f in profile)

def budget_spent(bad, rate_per_s, slo, window_days=30):
    """(error budget in requests, share of it spent) for a success-ratio SLO over the window at a steady rate."""
    total = rate_per_s * 86_400 * window_days
    budget = (1 - slo) * total
    return budget, bad / budget
```

That is 1,412,400 failed requests against a 30-day error budget of 5,184,000, so **27.2% of the budget in one incident**. The example budget policy in the SLO lesson treats an incident that uses more than 20% of the budget over four weeks as a trigger for a postmortem with at least one top-priority action item. This one crosses it. The check recomputes the cost minute by minute and compares.

### Who needs a postmortem

The SRE book's postmortem chapter (read 2026-11-26) says criteria should be defined before an incident, lists common triggers, and adds that any stakeholder may request one. This function encodes that list with illustrative thresholds:

```python
def needs_postmortem(incident, user_visible_min=15, resolve_min=60):
    """The triggers the Google SRE book lists, with this lesson's thresholds, which are illustrative:
    user-visible degradation past a threshold, data loss, on-call intervention (rollback, rerouting of
    traffic), a long resolution time, a monitoring failure, or any stakeholder asking for one."""
    why = []
    if incident.get('user_visible_min', 0) >= user_visible_min:
        why.append('user-visible for %d min or more' % user_visible_min)
    if incident.get('data_loss'):
        why.append('data loss')
    if incident.get('intervention'):
        why.append('on-call intervention')
    if incident.get('resolve_min', 0) >= resolve_min:
        why.append('resolution took %d min or more' % resolve_min)
    if incident.get('found_by_humans'):
        why.append('monitoring did not catch it')
    if incident.get('requested'):
        why.append('a stakeholder asked for one')
    return why
```

For this incident (49 minutes of impact, a rollback and shedding, 79 minutes from the start of impact to close) it returns three reasons. The code is a checklist, not judgement; its value is that the criteria are written down in advance, not decided in the middle of an argument.

---

## 5. Deep Dive 2: The Postmortem and Its Action Items

The SRE book's example postmortem and the Workbook's good postmortem (both read 2026-11-26) give the shape. Header: date, authors, status, summary. Then impact, root causes and trigger, resolution, detection, action items, lessons learned (what went well, what went wrong, where we got lucky), timeline and supporting data. The Workbook's checklist of qualities: clear and with context for readers outside the team; **numbers for impact** (a well-informed estimate beats none); a root-cause section that goes below the proximate cause; action items that are concrete; prompt publication (its good example was circulated less than a week after the incident; its bad example four months); one owner; wide sharing. The book's example footnotes add that a technique like the 5 Whys can help find contributing factors, and that "knee-jerk" action items are often too extreme or costly and need re-scoping.

For the invented incident, the filled-in postmortem, abbreviated:

| Field | Content (illustrative) |
|---|---|
| Summary | A configuration push cut the payment-provider timeout to 200 ms; checkout failed for 49 minutes |
| Impact | 1,412,400 failed requests (27.2% of the 30-day budget); about 35% of checkout requests failed between 14:09 and 14:38 (20% before that, 3% until 14:52); no data loss |
| Trigger | The 14:02 push, which set a timeout lower than the provider's normal latency |
| Contributing factors | Nothing checked the value against the provider's latency; the change took a full rollout rather than a canary; retries to the provider were uncapped, so the overload outlived the rollback; the runbook had no "rollback did not recover" branch |
| Detection | A burn-rate alert paged in 6 minutes |
| What went well | Fast detection; a clear commander by 14:18; rollback available |
| What went wrong | Seven minutes from page to declare; the first mitigation did not address the sustaining effect |
| Where we got lucky | The payments team lead was already in the channel for an unrelated review |
| Action items | The five below |

Trigger and contributing factors are different things. The Workbook's good example separates a trigger (an operation re-run by a person) from root causes in the system (an API that treated an empty list as "no filter", a workflow with no rate limit, no cross-check on destructive work). Amazon's public summary of its February 2017 S3 disruption (read 2026-11-26) has the same shape in prose: a command with an incorrectly entered input removed more servers than intended, which is the trigger. The text then spends its effort on the system: the tool allowed too much capacity to be removed too quickly, so it was changed to remove capacity more slowly and to refuse to take a subsystem below its minimum; the restart paths had not been exercised at that scale for years; and the status dashboard depended on the failing service, so status was posted another way until it could be updated.

### Action items that survive review

The Workbook's critique of a weak postmortem is a list: items mostly about mitigation with nothing preventive, all the same priority, vague wording such as "improve" or "make better", a postmortem owned by four people, action items with no owner, no tracking bug, and one item to "train humans" which it calls less reliable than changing the system. It also says the postmortems after a user-affecting outage must have at least one P0 or P1 bug, attributing that rule to Google's VP for 24/7 Operations. Here are the five items for the invented incident:

```python
ITEMS = [
    {'id': 1, 'kind': 'prevent',  'priority': 'P0', 'owner': 'payments-platform lead', 'tracking': 'ORD-4101',
     'text': 'CI rejects any provider timeout below 3x that provider\'s p99 latency; the push that caused this fails the build'},
    {'id': 2, 'kind': 'prevent',  'priority': 'P1', 'owner': 'orders deploy owner', 'tracking': 'ORD-4102',
     'text': 'Config changes roll out to 5% of the fleet and hold 10 minutes with the error ratio under 0.5% before the rest'},
    {'id': 3, 'kind': 'prevent',  'priority': 'P1', 'owner': 'orders tech lead', 'tracking': 'ORD-4103',
     'text': 'Cap retries to the payment provider at 10% of requests, and add a test that fails if the cap is exceeded'},
    {'id': 4, 'kind': 'mitigate', 'priority': 'P1', 'owner': 'orders on-call lead', 'tracking': 'ORD-4104',
     'text': 'Runbook step "rollback did not recover: enable load shedding" with a switch, exercised in the next game day'},
    {'id': 5, 'kind': 'detect',   'priority': 'P2', 'owner': 'orders on-call lead', 'tracking': 'ORD-4105',
     'text': 'The page text carries the declare checklist, and an alert fires if no incident is declared within 5 minutes of a page'},
]
```

Each names a verifiable end state (a build that fails, a hold of 10 minutes under 0.5% errors, a cap, an exercise, an alert within 5 minutes), has one owner, a priority and a tracking id, and the set has preventive items and top-priority items. The code below turns the Workbook's list into a linter. It is a heuristic (it can be gamed and it will sometimes be wrong), but running it catches the lazy cases before review does:

```python
import re

VAGUE = ('improve', 'make better', 'look into', 'consider', 'review', 'investigate', 'enhance')

HUMAN = (r'train(s|ing)?', r'remind(s|er)?', r'be more careful', r'pays? attention', r'educate', r'tell people', r'learns? to')

NUMBER = re.compile(r"\d+(\.\d+)?\s?(%|x\b|ms\b|s\b|seconds?\b|minutes?\b|min\b|hours?\b|days?\b)", re.I)
VERIFIABLE = re.compile(r"\b(reject|block|refuse|fail|alert|limit|cap|require|disallow|test|exercise|canary)(s|es|ed|d|ing)?\b", re.I)

PRIORITIES = ('P0', 'P1', 'P2', 'P3', 'P4')

def lint_action_items(items, user_affecting=True):
    """Flags for a postmortem's action items, from the Workbook's list of what makes them weak: no single owner,
    no tracking bug, no priority, a vague or unverifiable end state, an item that tries to fix people instead of the
    system; and for the set: nothing preventive, one priority for everything, no top-priority item after a
    user-affecting outage; and a postmortem with no action items at all. Returns a list of (item id or None, flag)."""
    if not items:
        return [(None, 'no action items')]
    flags = []
    for it in items:
        text = it['text'].lower()
        owner = it.get('owner', '')
        if not owner.strip() or re.search(r'[,;/&]|\band\b', owner):
            flags.append((it['id'], 'owner'))
        if not it.get('tracking', '').strip():
            flags.append((it['id'], 'tracking'))
        if it.get('priority') not in PRIORITIES:
            flags.append((it['id'], 'priority'))
        if any(text.startswith(v) for v in VAGUE) and not NUMBER.search(text):
            flags.append((it['id'], 'vague'))
        elif not (NUMBER.search(text) or VERIFIABLE.search(text)):
            flags.append((it['id'], 'unverifiable'))
        if any(re.search(r'\b' + h + r'\b', text) for h in HUMAN):
            flags.append((it['id'], 'fixes people'))
    if not any(i['kind'] == 'prevent' for i in items):
        flags.append((None, 'nothing preventive'))
    if len(items) > 1 and len({i.get('priority') for i in items}) == 1:
        flags.append((None, 'one priority for all'))
    if user_affecting and not any(i.get('priority') in ('P0', 'P1') for i in items):
        flags.append((None, 'no P0 or P1'))
    return flags

LOUD = ('careless', 'ridiculous', 'stupid', 'idiot', 'negligent', 'incompetent', 'sloppy', 'blame', 'blamed',
        'should have known', 'ignored', 'unbelievable')

def blame_flags(text):
    """The loud cases only: judgemental words and exclamation marks. Review has to catch the quiet ones."""
    low = text.lower()
    out = [w for w in LOUD if re.search(r'\b' + re.escape(w) + r'\b', low)]      # whole words: 'blameless' is fine
    if '!' in text:
        out.append('!')
    return out
```

Here is the linter on a deliberately bad set of three items for the same incident: "Improve alerting" with two owners and no tracking id; "Train engineers to be more careful with config pushes"; "Look into the retry behaviour" with no owner. It raises 10 flags:

| Item | Flag |
|---|---|
| 1 | owner |
| 1 | tracking |
| 1 | vague |
| 2 | unverifiable |
| 2 | fixes people |
| 3 | owner |
| 3 | vague |
| set | nothing preventive |
| set | one priority for all |
| set | no P0 or P1 |

The five real items produce none. The check compares the linter with a second implementation on 2,000 random item sets, and tests each rule with a one-field change from a good item.

---

## 6. Deep Dive 3: Blameless Does Not Mean Unaccountable

The SRE book's postmortem chapter says blameless postmortems focus on contributing causes without indicting any individual or team, assume everyone involved had good intentions and acted on the information they had, and rest on the point that you cannot fix people but you can fix systems and processes. Its example contrasts a finger-pointing complaint with a blameless version that makes the same request for a rewrite in terms of the work and the team. The Workbook adds concrete signs of a blameful document (naming one person as the sole cause, "careless" and exclamation marks, a judgement on whoever mishandled a handoff) and the reason it matters: people who fear being shamed hide facts that are critical to preventing a recurrence.

Blameless is not the same as consequence-free for the system. Accountability moves to the action items: an owner, a date, a tracked bug. A cheap language check catches the loud cases:

- `blame_flags("The engineer was careless and ignored the checklist!")` returns `careless`, `ignored` and `!`.
- `blame_flags("The checklist step was skipped because it was not in the runbook.")` returns nothing, and it is the better sentence: it points at the runbook.

The quiet cases need a human reviewer. The Workbook describes a senior leader asking why nobody listened to a warning, and a colleague turning it into a question about which warning signs might have been heeded and why they were dismissed. The practical rule is to ask the second kind of question: not who did it, but what made the wrong action look right with the information available.

---

## 7. After the Postmortem

- **Review it.** The SRE book's rule: an unreviewed postmortem might as well not exist. It names review questions (was key data collected, is the impact assessed, is the root cause deep enough, are action items at the right priority, were stakeholders told) and says to share widely.
- **Track the actions to closure.** The Workbook says to reward closing action items as well as writing postmortems, or the process produces documents with nothing done. Google files action items as bugs in a central tracker so closure can be monitored.
- **Look across incidents.** The SRE book's chapter on tracking outages describes a tool that receives every alert, lets people group alerts into incidents and tag them by cause, and so supports counting incidents per week separately from alerts per week, and finding the infrastructure component behind most incidents. One incident rarely shows the pattern; twenty tagged ones do.
- **Ask why it repeats.** The Workbook's questions when similar incidents recur: are action items taking too long to close, is feature work crowding out reliability work, are the right items being captured, is the service overdue for a rewrite, are people applying quick fixes to a deeper problem.
- **Tie it to the budget.** An incident that consumes a large part of the error budget is the natural trigger for a postmortem with a top-priority item and, under a budget policy, for reliability work taking priority. That is the SLO lesson's policy.

### Telling it in an interview

A good account has five beats: what the system and impact were (with a number), what your role was, what you did first and why (mitigation before diagnosis, with what you knew at the time), what you learned about the system, and what changed afterwards (an action item that shipped, ideally one that would have prevented or shortened it). Avoid the two weak shapes: the hero story (alone at 3 a.m.) and the blame story (someone else's mistake). If the incident was yours, say so plainly and describe the safeguard that now exists.

---

## 8. Failure Modes

| Failure | Effect | Mitigation |
|---|---|---|
| no declared criteria | the incident is declared late or never | written criteria, declare early |
| everyone debugging, nobody coordinating | duplicate work, conflicting changes | one incident commander; only the ops lead changes the system |
| diagnosing before mitigating | users hurt longer than necessary | generic mitigations built in advance: rollback, drain, shed |
| mitigation that removes the trigger but not the loop | the system stays down after the rollback | look for the sustaining effect; shed load |
| incident record kept in the broken system | no timeline, no coordination | out-of-band channel and document |
| unclear handoff | two commanders or none | explicit handoff with acknowledgement |
| a blameful postmortem | hidden facts next time | blameless language, review for it |
| vague action items | nothing changes | one owner, priority, tracking id, verifiable end state |
| fixing people instead of systems | the same mistake with a new person | prevent with checks, limits and automation |
| postmortem never reviewed or shared | no learning outside the team | scheduled review, wide sharing |
| actions never closed | the incident repeats | track to closure; reward closure |

---

## 9. What Real Systems Document

All read 2026-11-26. The Google SRE book documents the incident-command roles, the live incident document, handoff, declaration criteria, the postmortem philosophy, review and triggers, three emergency case studies and an example postmortem with its template fields. The SRE Workbook documents the three Cs, four incident case studies including PagerDuty's, the assess-mitigate-diagnose order, preparation and drills, a contrasting bad and good postmortem with the reasons, incentives, failure patterns and tooling. Amazon's S3 summary shows how a public postmortem separates trigger from system causes and lists the changes made. None of them gives you a response-time target to quote; the intervals in this lesson are for an invented incident.

---

## 10. Pitfalls Checklist

1. **Waiting to be sure before declaring.** The cost of declaring a small incident is small; the cost of a late declaration is not.
2. **Letting several people change production at once.** Only the ops lead changes the system.
3. **Looking for the root cause while users hurt.** Mitigate first, with a generic action if you have one.
4. **Declaring victory when the trigger is gone.** A retry loop or a cold cache can keep the service down.
5. **A postmortem with no numbers for impact.** An estimate is better than none.
6. **Writing "human error" as the cause.** Ask what made the action look right.
7. **Action items without an owner, priority, tracking id or verifiable end state.** They will not close.
8. **Training as the main fix.** Change the system so the mistake is caught or harmless.
9. **A postmortem nobody reviews, or that arrives months late.** Memory fades; the repeat does not.
10. **Never practising.** The first time you use the process should not be during a real outage.

---

## Drills

1. List the three hazards of an unmanaged incident from the SRE book and say which one the second engineer making an unannounced change illustrates.
2. In the invented incident, the page came after 6 minutes and the incident was declared after 13. Which of the three declaration questions were true at the page, and what cheap change closes the gap?
3. Why did the rollback fail to end the incident, and which lesson in this course explains the loop?
4. Compute the share of the error budget spent if the error ratio were 35% for the whole 49 minutes at 2,000 requests per second under a 99.9% SLO. How does it compare with 27.2%?
5. Run `needs_postmortem` on an incident with 10 user-visible minutes, no data loss, no intervention, 30 minutes to resolve, found by a customer report. What does it return, and which trigger is the one that matters?
6. Why does the lesson's bad item "Train engineers to be more careful" draw two flags, and what would you write instead?
7. Rewrite this sentence blamelessly: "The on-call ignored the dashboard and was careless with the rollback." What question should the postmortem ask instead?
8. The S3 summary names a mistyped input as the trigger. Which system causes does it list, and which changes address each?

---

## Homework

1. Write a postmortem for an outage you were part of (or a public one you have read), using the field table in section 5, with a numeric impact, a trigger separated from contributing factors, and five action items. Run them through `lint_action_items`.
2. Change `TIMELINE` so the rollback works at 14:31 and compute the new `incident_metrics` and budget cost.
3. Extend `incident_metrics` to flag a timeline where declaration is more than 5 minutes after the page, and add the page-to-declare interval to the output.
4. Write blameless rewrites for five blameful sentences you have heard in real postmortem meetings, and add the words you caught to `LOUD` only if a lint would have helped.
5. Pick a recent public postmortem from a cloud provider and mark its trigger, contributing factors, mitigation and the changes it announced against the template here.
6. Plan a 45-minute Wheel of Misfortune: take your postmortem, assign roles, and decide what the facilitator reveals at each step.
7. Read the SRE Workbook postmortem chapter end to end, including the good and bad examples, and list three things its bad example does that your last postmortem also did.

---

## Sources

All read 2026-11-26.

- Beyer, Jones, Petoff and Murphy (eds.), *Site Reliability Engineering*, chapter 14 *Managing Incidents*, sre.google/sre-book/managing-incidents/. Read in full.
- *Site Reliability Engineering*, chapter 15 *Postmortem Culture: Learning from Failure*, sre.google/sre-book/postmortem-culture/. Read in full.
- *Site Reliability Engineering*, chapter 13 *Emergency Response*, sre.google/sre-book/emergency-response/. Read in full.
- *Site Reliability Engineering*, chapter 16 *Tracking Outages*, sre.google/sre-book/tracking-outages/. Read the Escalator, Outalator, aggregation, tagging and analysis sections; the closing reporting section was read in part.
- *Site Reliability Engineering*, appendix D *Example Postmortem*, sre.google/sre-book/example-postmortem/. Read in full.
- Beyer, Murphy, Rensin, Kawahara and Thorne (eds.), *The Site Reliability Workbook*, chapter 9 *Incident Response*, sre.google/workbook/incident-response/. Read in full.
- *The Site Reliability Workbook*, chapter 10 *Postmortem Culture: Learning from Failure*, sre.google/workbook/postmortem-culture/. Read in full.
- Amazon Web Services, *Summary of the Amazon S3 Service Disruption in the Northern Virginia (US-EAST-1) Region*, aws.amazon.com/message/41926/. Read in full. It is dated by its own text to 28 February 2017.

## Further reading (not consulted)

The PagerDuty incident-response documentation (response.pagerduty.com) and its postmortem templates; Etsy's blameless-postmortems and debriefing-facilitation writing, which the Etsy page refused to serve to an automated client; the SRE Workbook's postmortem template and checklist materials; the Incident Command System documentation from FEMA that the SRE book cites; academic work on root-cause analysis and "just culture". None was read for this lesson. The incident, its numbers and the linter here are this lesson's own.

*Last reviewed: 2026-11-26.*
