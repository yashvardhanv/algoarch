"""Runs the python blocks from data/new_lessons/sy48-slos-error-budgets.md against reference checks: the burn-rate
arithmetic against the Google SRE Workbook's published figures, the alert-policy simulator against a brute-force
window average, and every number the lesson prints against the code that produced it."""
import re, sys, math, random

src = open(sys.argv[1], encoding='utf-8').read()
ns = {}
for b in re.findall(r"```python\n(.*?)```", src, re.S):
    exec(b, ns)

def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the computed figure: %r' % p

def close(a, b, tol=1e-9):
    return abs(a - b) <= tol * max(1.0, abs(b))

burn_rate, hours_to_exhaust, budget_spent = ns['burn_rate'], ns['hours_to_exhaust'], ns['budget_spent']
SLO, PERIOD = ns['SLO'], ns['PERIOD']
assert SLO == 0.999 and PERIOD == 43200

# ---------------------------------------------------------------- arithmetic published in the SRE Workbook, chapter 5
assert close(burn_rate(0.001), 1) and close(burn_rate(0.01), 10) and close(burn_rate(1.0), 1000) and close(burn_rate(0.002), 2)
assert close(hours_to_exhaust(0.001), 720) and close(hours_to_exhaust(0.002), 360) and close(hours_to_exhaust(0.01), 72)
assert close(hours_to_exhaust(1.0) * 60, 43.2)                                  # a total outage: 43 minutes
assert close(hours_to_exhaust(0.035), 720 / 35) and round(hours_to_exhaust(0.035), 1) == 20.6   # "20.5 hours" on the page
assert round(hours_to_exhaust(1.0, slo=0.99999) * 3600, 2) == 25.92             # five nines: 26 seconds
assert round(hours_to_exhaust(0.01, slo=0.99999) * 60, 1) == 43.2               # 1% canary at five nines: 43 minutes
assert close(budget_spent(60, 14.4), 0.02) and close(budget_spent(360, 6), 0.05) and close(budget_spent(4320, 1), 0.10)
assert close(budget_spent(60, 36), 0.05) and close(budget_spent(36 * 60, 1), 0.05)       # strategies 2 and 4 both mean 5%
det = ns['detection_seconds']
assert round(det(1.0, 10, 1), 3) == 0.6                                         # strategy 1: 0.6 s for a total outage
assert round(det(1.0, 36 * 60, 1), 1) == 129.6                                  # strategy 2: 2 min 10 s
assert round(det(1.0, 60, 36), 1) == 129.6                                      # strategy 4: the same, with a 1 h window
assert det(0.035, 60, 36) is None                                               # a 35x burn never trips the 36x rule
assert round(det(0.035, 60, 14.4) / 60, 1) == 24.7
assert ns['allowed_failures'](3663253, 0.97) == 109897 and ns['allowed_failures'](3663253, 0.90) == 366325
assert ns['allowed_failures'](3663253, 0.99) == 36632 and ns['allowed_failures'](1000000, 0.999) == 1000
assert ns['allowed_failures'](2500000, 0.9999) == 250
assert round(14066 / 109897 * 100, 1) == 12.8 and round(72000 / 109897 * 100, 1) == 65.5
# the low-traffic example: 10 requests an hour, one failure
assert round(10 * 24 * 30 * 0.001, 1) == 7.2 and round(1 / (10 * 24 * 30 * 0.001) * 100, 1) == 13.9
assert round(burn_rate(0.1), 6) == 100.0                                         # the page prints 1,000x; the ratio is 100x

# ---------------------------------------------------------------- composition and traffic weighting
serial, parallel, outage_cost = ns['serial_availability'], ns['parallel_availability'], ns['outage_cost']
assert close(serial([0.9995, 0.999, 0.9999]), 0.9995 * 0.999 * 0.9999) and serial([]) == 1.0
assert close(parallel(0.999, 2), 0.999999) and close(parallel(0.9, 3), 0.999) and parallel(0.5, 1) == 0.5
assert close(0.9995 * parallel(0.999, 2), 0.999499000500)
assert ns['traffic'](14) == 1.0 and abs(ns['traffic'](2) - 0.2) < 1e-12
peak, trough = outage_cost(14, 10), outage_cost(2, 10)
assert peak > trough and round(10 / 43.2, 3) == 0.231 and round(peak, 3) == 0.386 and round(trough, 3) == 0.077
# daily traffic averages to 0.6 of peak, so a flat-traffic outage of the same length costs 10 / (43.2) of the budget
assert abs(sum(ns['traffic'](m / 60) for m in range(1440)) / 1440 - 0.6) < 1e-9
need('99.84%', '99.9999%', '99.9499%', '38.6%', '7.7%', '23.1%')

# ---------------------------------------------------------------- alert policies against a brute-force reference
Policy, POLICIES, scenario, evaluate = ns['Policy'], ns['POLICIES'], ns['scenario'], ns['evaluate']
BUDGET_RATE = ns['BUDGET_RATE']

def reference_fired(policy, errors):
    out, run = [], 0
    for t in range(len(errors)):
        def mean(w):
            window = [errors[i] if i >= 0 else 0.0 for i in range(t - w + 1, t + 1)]
            return sum(window) / w
        hit = any(mean(lg) / BUDGET_RATE >= b - 1e-6 and (sh is None or mean(sh) / BUDGET_RATE >= b - 1e-6)
                  for lg, sh, b in policy.conditions)
        run = run + 1 if hit else 0
        out.append(run >= policy.hold)
    return out

rng = random.Random(8)
for _ in range(60):
    errors = [rng.choice([0.0, 0.0, 0.0005, 0.001, 0.01, 0.2, 1.0]) for _ in range(rng.randint(5, 120))]
    pol = Policy('t', [(rng.randint(1, 30), rng.choice([None, rng.randint(1, 10)]), rng.choice([1, 3, 14.4]))
                       for _ in range(rng.randint(1, 3))], hold=rng.randint(1, 4))
    got, want = pol.fired(errors), reference_fired(pol, errors)
    mism = [t for t in range(len(errors)) if got[t] != want[t]]
    assert not mism, (pol.conditions, pol.hold, mism[:3])
assert Policy('x', [(2, None, 1)]).fired([0.0, 0.001, 0.0, 0.0]) == [False, False, False, False]   # mean 0.0005 < 0.001
assert Policy('x', [(1, None, 1)]).fired([0.0, 0.001, 0.0, 0.0]) == [False, True, False, False]
assert Policy('x', [(1, None, 1)], hold=2).fired([0.0, 0.001, 0.001, 0.0]) == [False, False, True, False]
assert Policy('x', [(3, 1, 1)]).fired([0.003, 0.0, 0.0, 0.0]) == [True, False, False, False]       # short window clears it

assert [p.name for p in POLICIES] == ['P1 short window', 'P2 long window', 'P3 duration', 'P4 burn rate',
                                      'P5 multi burn', 'P6 multiwindow']
assert POLICIES[3].conditions == [(60, None, 36)] and POLICIES[5].conditions == [(60, 5, 14.4), (360, 30, 6), (4320, 360, 1)]
assert POLICIES[2].hold == 60 and len(scenario([1.0])) == ns['PRE'] + 1 + ns['POST']

table = ns['compare_policies']()
names = [p.name for p in POLICIES]
sc = list(ns['SCENARIOS'])
assert len(sc) == 6

def first(s, p):
    return table[s][p][0]

# the blip spends 0.02% of the budget: only the first policy pages on it
blip = sc[0]
assert [first(blip, p) is not None for p in names] == [True, False, False, False, False, False]
assert round(table[blip][names[0]][1] * 100, 2) == 0.02
# the Workbook's claims about each weaker policy
assert first(sc[3], 'P4 burn rate') is None                      # 35x burn: strategy 4 never alerts
assert first(sc[5], 'P3 duration') is None and first(sc[1], 'P3 duration') is None   # spikes and a 5-minute outage
assert first(sc[4], 'P4 burn rate') is None                      # a 2x burn is below its threshold
assert first(sc[2], 'P3 duration') == 60 and first(sc[4], 'P3 duration') == 60       # fixed delay whatever the severity
assert table[sc[2]]['P2 long window'][2] > 2000 and table[sc[2]]['P5 multi burn'][2] > 4000
assert table[sc[2]]['P6 multiwindow'][2] <= 360 and table[sc[2]]['P4 burn rate'][2] < 60
# P6 is the only one with no false alert, no miss, and a reset of six hours or less on every significant scenario
def profile(p):
    false = sum(1 for s in sc if first(s, p) is not None and sum(ns['SCENARIOS'][s]) / (BUDGET_RATE * PERIOD) < 0.02)
    miss = sum(1 for s in sc if first(s, p) is None and sum(ns['SCENARIOS'][s]) / (BUDGET_RATE * PERIOD) >= 0.02)
    reset = max((table[s][p][2] or 0) for s in sc)
    return false, miss, reset
prof = {p: profile(p) for p in names}
good = [p for p, (f, m, r) in prof.items() if f == 0 and m == 0 and r <= 360]
assert good == ['P6 multiwindow'], prof
assert prof['P1 short window'][0] == 1 and prof['P3 duration'][1] >= 2 and prof['P4 burn rate'][1] >= 2

def cell(r):
    return 'never' if r[0] is None else '%d min (%.2f%%)' % (r[0], r[1] * 100)
for s in sc:
    need('| %s | %s |' % (s, ' | '.join(cell(table[s][p]) for p in names)))
need('| minutes the alert keeps firing after a 60-minute outage ends | %s |'
     % ' | '.join(format(table[sc[2]][p][2], ',') for p in names))
for s in sc:
    pct = sum(ns['SCENARIOS'][s]) / (BUDGET_RATE * PERIOD) * 100
    need('%.1f%%' % pct)

# ---------------------------------------------------------------- figures in the prose
assert round(5 / 4320 * 100, 3) == 0.116
need('0.116%', '13% and 65%', '109,897', '366,325', '36,632', '12.8%', '65.5%', '7.2 failed requests', '13.9%', '100x', '1,000x',
     '43.2 minutes', '25.92 seconds', '20.6 hours', '129.6 seconds', '24.7 minutes')
print('sy48 code checks passed')
