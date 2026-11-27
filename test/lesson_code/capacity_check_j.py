"""Capacity checks for wave 3, letter j (sy77 now; sy74 to sy76 may add sections). Reproduces every
capacity number in the lesson and fails if stale wording or a wrong figure appears in the text."""
import sys, re
text = open(sys.argv[1], encoding='utf-8').read()

# ---- sy77: DNS at scale ---------------------------------------------------------------------------------------------
N, TOTAL, TTL = 1_000_000, 20_000, 60
H = sum(1 / i for i in range(1, N + 1))
rates = [TOTAL / (i * H) for i in range(1, N + 1)]
up = sum(q / (1 + q * TTL) for q in rates)
live = sum(q * TTL / (1 + q * TTL) for q in rates)
tail = [q for q in rates if q * TTL < 1]
assert round(H, 2) == 14.39
assert round(rates[0]) == 1390 and round(rates[-1], 4) == 0.0014 and round(1 / rates[-1] / 60) == 12   # one every 12 minutes
assert round(up) == 3564 and round(100 * (1 - up / TOTAL), 1) == 82.2
assert round(live) == 213814 and round(live * 100 / 1e6) == 21                                          # MB at 100 bytes per entry
assert len(tail) == 916625 and round(100 * sum(tail) / TOTAL, 1) == 17.3
hot, cold = 1000 / (1 + 1000 * TTL), 0.001 / (1 + 0.001 * TTL)
assert round(1 / hot) == 60 and round(100 * 1000 * TTL / (1 + 1000 * TTL), 3) == 99.998
assert round(100 * 0.001 * TTL / (1 + 0.001 * TTL), 1) == 5.7
auth = {t: 100_000 * 2 / (1 + 2 * t) for t in (5, 60, 300)}
ceil = {t: 100_000 / t for t in (5, 60, 300)}
assert [round(auth[t]) for t in (5, 60, 300)] == [18182, 1653, 333]
assert [round(ceil[t]) for t in (5, 60, 300)] == [20000, 1667, 333]
assert all(auth[t] < ceil[t] for t in auth)                      # the load never reaches the resolvers / TTL ceiling
assert round(auth[5] / auth[60], 1) == 11.0                       # a 12x TTL cut is an 11x bill
stale = {t: t / 2 * 2 * t / (1 + 2 * t) for t in (5, 60, 300)}
assert [round(stale[t], 1) for t in (5, 60, 300)] == [2.3, 29.8, 149.8]
assert round(rates[0] * 0.2) == 278                               # clients asking during one 200 ms refresh of the hottest name

# the numbers are in the lesson, spelled the way the lesson spells them
for must in ('1,390 per second', '3,564 per second out of 20,000', '82.2%', '213,814 entries, 21 MB', '916,625 of 1,000,000',
             '17.3% of the queries', '99.998%', '5.7%', '18,182 / 1,653 / 333', '20,000 / 1,667 / 333', '2.3 / 29.8 / 149.8',
             'about 278 clients', 'removes 277', '**29** address records', 'costs **20** upstream attempts', 'an 11x authoritative bill'):
    assert must in text, must
# stale wording that must not come back
for must_not in ('12x authoritative', 'a 12x increase', 'five queries, five upstream', 'guarantees clients obey'):
    assert must_not not in text, must_not
# no claim about a named operator's behaviour
for op in ('Cloudflare', 'Route 53', 'Route53', 'Google Public DNS', 'Akamai', 'Verisign', 'Quad9', 'OpenDNS'):
    assert op not in text, op
print("capacity_check_j (sy77) passed")
