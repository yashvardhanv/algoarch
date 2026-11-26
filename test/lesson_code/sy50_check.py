"""Runs the python blocks from data/new_lessons/sy50-incident-response-postmortems.md against independent references:
the timeline intervals against datetime arithmetic, the error-budget cost against a minute-by-minute count, the
action-item linter against a second implementation on random items, and every number the lesson prints."""
import re, sys, random, itertools
from datetime import datetime

src = open(sys.argv[1], encoding='utf-8').read()
ns = {}
for b in re.findall(r"```python\n(.*?)```", src, re.S):
    exec(b, ns)

def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the computed figure: %r' % p

# ---------------------------------------------------------------- the timeline
minutes, TIMELINE, incident_metrics = ns['minutes'], ns['TIMELINE'], ns['incident_metrics']
for h in range(24):
    for m in (0, 1, 9, 30, 59):
        t = '%02d:%02d' % (h, m)
        assert minutes(t) == (datetime.strptime(t, '%H:%M') - datetime.strptime('00:00', '%H:%M')).seconds // 60

def ref_metrics(timeline):
    at = {}
    for hhmm, kind, _ in timeline:
        at.setdefault(kind, datetime.strptime(hhmm, '%H:%M'))
    d = lambda a, b: int((at[b] - at[a]).total_seconds() // 60)
    return {'time_to_detect': d('impact_start', 'page'), 'time_to_ack': d('page', 'ack'),
            'time_to_declare': d('impact_start', 'declare'), 'time_to_first_effective': d('impact_start', 'effective'),
            'time_to_mitigate': d('impact_start', 'mitigated'), 'time_to_close': d('impact_start', 'closed'),
            'exit_criterion_met': d('mitigated', 'closed') >= 30}
m = incident_metrics(TIMELINE)
assert m == ref_metrics(TIMELINE)
assert [m[k] for k in ('time_to_detect', 'time_to_ack', 'time_to_declare', 'time_to_first_effective',
                       'time_to_mitigate', 'time_to_close')] == [6, 2, 13, 35, 49, 79] and m['exit_criterion_met'] is True
kinds = [k for _, k, _ in TIMELINE]
assert kinds.index('trigger') < kinds.index('impact_start') < kinds.index('page') < kinds.index('declare') < kinds.index('effective')
assert kinds.count('mitigation') == 2 and kinds.index('mitigation') < kinds.index('effective') < kinds.index('mitigated')
# the first attempt (a rollback) did not help: the effective action came later than every attempt
assert minutes(TIMELINE[kinds.index('effective')][0]) > minutes(TIMELINE[len(kinds) - 1 - kinds[::-1].index('mitigation')][0])
# the exit criterion is a threshold on the gap between mitigation and closing
late = [e if e[1] != 'closed' else ('15:21', 'closed', e[2]) for e in TIMELINE]
assert incident_metrics(late)['exit_criterion_met'] is False and incident_metrics(late, exit_criterion_min=29)['exit_criterion_met'] is True
for bad in (TIMELINE[::-1], [e for e in TIMELINE if e[1] != 'page'], [e for e in TIMELINE if e[1] != 'effective']):
    try:
        incident_metrics(bad)
        raise AssertionError('accepted a broken timeline')
    except ValueError:
        pass
for label, v in (('detect (impact to page)', 6), ('acknowledge (page to ack)', 2), ('declare', 13), ('first effective mitigation', 35), ('mitigate', 49), ('close', 79)):
    need('| %s | %d |' % (label, v))

# ---------------------------------------------------------------- the cost in error budget
PROFILE, bad_requests, budget_spent = ns['PROFILE'], ns['bad_requests'], ns['budget_spent']
def minute_by_minute(profile, rate):
    total = 0.0
    for a, b, f in profile:
        for _ in range(minutes(a), minutes(b)):
            total += rate * 60 * f
    return total
assert abs(bad_requests(PROFILE, 2000) - minute_by_minute(PROFILE, 2000)) < 1e-6
assert abs(bad_requests(PROFILE, 2000) - 1_412_400) < 1e-6 and bad_requests([], 2000) == 0
budget, share = budget_spent(1_412_400, 2000, 0.999)
assert round(budget) == 5_184_000 and round(share * 100, 1) == 27.2
assert round(budget_spent(0, 2000, 0.999)[1], 9) == 0 and abs(budget_spent(budget, 2000, 0.999)[1] - 1) < 1e-9
assert round(budget_spent(1_412_400, 2000, 0.99)[0]) == 51_840_000                   # a looser SLO has ten times the budget
assert round(budget_spent(1_412_400, 2000, 0.999, window_days=7)[0]) == round(2000 * 86400 * 7 * 0.001)
need('1,412,400', '5,184,000', '27.2%')
whole = budget_spent(bad_requests([('14:03', '14:52', 0.35)], 2000), 2000, 0.999)[1]
assert round(whole * 100, 1) == 39.7                                                   # drill 4
assert share > 0.20                                                                    # over the example policy's 20% line

pm = ns['needs_postmortem']
assert pm({}) == []
assert pm({'user_visible_min': 14}) == [] and pm({'user_visible_min': 15}) == ['user-visible for 15 min or more']
assert pm({'data_loss': True}) == ['data loss'] and pm({'intervention': True}) == ['on-call intervention']
assert pm({'resolve_min': 59}) == [] and pm({'resolve_min': 60}) == ['resolution took 60 min or more']
assert pm({'found_by_humans': True}) == ['monitoring did not catch it'] and pm({'requested': True}) == ['a stakeholder asked for one']
assert pm({'user_visible_min': 49, 'intervention': True, 'resolve_min': 80}) == [
    'user-visible for 15 min or more', 'on-call intervention', 'resolution took 60 min or more']
assert len(pm({'user_visible_min': 99, 'data_loss': True, 'intervention': True, 'resolve_min': 999, 'found_by_humans': True,
               'requested': True})) == 6
assert pm({'user_visible_min': 20}, user_visible_min=30) == []
assert pm({'user_visible_min': 10, 'resolve_min': 30, 'found_by_humans': True}) == ['monitoring did not catch it']   # drill 5

# ---------------------------------------------------------------- the action-item linter
ITEMS, lint, blame = ns['ITEMS'], ns['lint_action_items'], ns['blame_flags']
assert lint(ITEMS) == [] and [i['id'] for i in ITEMS] == [1, 2, 3, 4, 5]

def ref_lint(items, user_affecting=True):
    """Second implementation: one table of per-item predicates, one of per-set predicates."""
    vague_starts = ('improve', 'make better', 'look into', 'consider', 'review', 'investigate', 'enhance')
    human_bits = ('train', 'remind', 'be more careful', 'pay attention', 'educate', 'tell people', 'learn to')
    verifiable_words = ('reject', 'block', 'refuse', 'fail', 'alert', 'limit', 'cap', 'require', 'disallow', 'test', 'exercise', 'canary')
    if len(items) == 0:
        return [(None, 'no action items')]
    out = []
    for it in items:
        t = it['text'].lower()
        has_digit = any(c.isdigit() for c in t)
        o = it.get('owner', '')
        multi = (',' in o) or (';' in o) or ('/' in o) or ('&' in o) or (' and ' in (' ' + o + ' '))
        if o.strip() == '' or multi:
            out.append((it['id'], 'owner'))
        if it.get('tracking', '').strip() == '':
            out.append((it['id'], 'tracking'))
        if it.get('priority') not in ['P0', 'P1', 'P2', 'P3', 'P4']:
            out.append((it['id'], 'priority'))
        starts_vague = any(t.startswith(v) for v in vague_starts)
        verifiable = has_digit or any(re.search(r'\b' + w, t) for w in verifiable_words)
        if starts_vague and not has_digit:
            out.append((it['id'], 'vague'))
        elif not verifiable:
            out.append((it['id'], 'unverifiable'))
        if any(h in t for h in human_bits):
            out.append((it['id'], 'fixes people'))
    if all(i['kind'] != 'prevent' for i in items):
        out.append((None, 'nothing preventive'))
    if len(items) > 1 and len(set(i.get('priority') for i in items)) == 1:
        out.append((None, 'one priority for all'))
    if user_affecting and all(i.get('priority') not in ('P0', 'P1') for i in items):
        out.append((None, 'no P0 or P1'))
    return out

texts = ['Improve alerting', 'Improve alerting for 3 of the services', 'Cap retries at 10% of requests', 'Train engineers to be careful',
         'Remind people to read the runbook', 'Add a test that fails when the timeout is under 1000 ms', 'Look into the retry behaviour',
         'Review the dashboards', 'Rewrite the config loader', 'Alert when more than 5% of hosts are drained', 'Educate the team on retries',
         'Block pushes that lower a timeout']
owners = ['orders lead', '', 'a, b', 'a and b', 'a/b', 'a & b', 'brand owner', '   ', 'x; y']
for seed in range(2000):
    rng = random.Random(seed)
    items = [{'id': i, 'kind': rng.choice(('prevent', 'mitigate', 'detect', 'process')),
              'priority': rng.choice(('P0', 'P1', 'P2', 'P3', 'high', None)), 'owner': rng.choice(owners),
              'tracking': rng.choice(('', 'T-1', ' ')), 'text': rng.choice(texts)} for i in range(rng.randrange(0, 5))]
    ua = rng.random() < 0.5
    assert lint(items, ua) == ref_lint(items, ua), (seed, items)

one = lambda **kw: [dict({'id': 1, 'kind': 'prevent', 'priority': 'P1', 'owner': 'orders lead', 'tracking': 'T-1',
                          'text': 'Cap retries at 10% of requests'}, **kw)]
assert lint(one()) == []
assert lint(one(owner='a, b')) == [(1, 'owner')] and lint(one(owner='a and b')) == [(1, 'owner')] and lint(one(owner='')) == [(1, 'owner')]
assert lint(one(owner='brand lead')) == []                                                      # 'and' inside a word is not a list
assert lint(one(tracking='')) == [(1, 'tracking')] and lint(one(priority='high'), user_affecting=False) == [(1, 'priority')] and lint(one(priority='high')) == [(1, 'priority'), (None, 'no P0 or P1')]
assert lint(one(text='Improve alerting')) == [(1, 'vague')] and lint(one(text='Improve alerting for 3 services')) == []
assert lint(one(text='Rewrite the loader')) == [(1, 'unverifiable')]
assert lint(one(text='Train engineers to be careful with 3 checks')) == [(1, 'fixes people')]
assert lint(one(kind='mitigate')) == [(None, 'nothing preventive')]
assert lint(one(priority='P2')) == [(None, 'no P0 or P1')]
assert lint(one(priority='P2'), user_affecting=False) == []
assert lint([]) == [(None, 'no action items')] and lint([], user_affecting=False) == [(None, 'no action items')]
assert (None, 'one priority for all') in lint(ITEMS[:1] + [dict(ITEMS[1], priority='P0')])
assert lint(ITEMS[:2] + [dict(ITEMS[2], priority='P2')]) == []

BAD = [
    {'id': 1, 'kind': 'mitigate', 'priority': 'P2', 'owner': 'orders team, platform team', 'tracking': '', 'text': 'Improve alerting'},
    {'id': 2, 'kind': 'mitigate', 'priority': 'P2', 'owner': 'someone', 'tracking': 'ORD-1',
     'text': 'Train engineers to be more careful with config pushes'},
    {'id': 3, 'kind': 'mitigate', 'priority': 'P2', 'owner': '', 'tracking': 'ORD-2', 'text': 'Look into the retry behaviour'},
]
flags = lint(BAD)
assert flags == [(1, 'owner'), (1, 'tracking'), (1, 'vague'), (2, 'unverifiable'), (2, 'fixes people'), (3, 'owner'), (3, 'vague'),
                 (None, 'nothing preventive'), (None, 'one priority for all'), (None, 'no P0 or P1')]
for item_id, flag in flags:
    need('| %s | %s |' % ('set' if item_id is None else item_id, flag))
need('10 flags')

assert blame('The engineer was careless and ignored the checklist!') == ['careless', 'ignored', '!']
assert blame('The checklist step was skipped because it was not in the runbook.') == []
assert blame('RIDICULOUS') == ['ridiculous'] and blame('') == [] and blame('Fine!') == ['!']
assert blame('Nobody could have known') == []                                                 # not every sentence about knowing is a flag
need('careless', 'ridiculous')

print('sy50 code checks passed')
