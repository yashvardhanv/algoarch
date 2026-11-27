"""Capacity checks for wave 3, letter j (sy77 now; sy74 to sy76 may add sections). Reproduces every
capacity number in the lesson and fails if stale wording or a wrong figure appears in the text."""
import sys, re
text = open(sys.argv[1], encoding='utf-8').read()
text75 = open(sys.argv[2], encoding='utf-8').read() if len(sys.argv) > 2 else None

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

# ---- sy75: feature flags and config service --------------------------------------------------------------------------
if text75 is not None:
    SERVERS, SNAP, UNCHANGED, PUBLISHES = 50_000, 200_000, 300, 10
    polls30, polls5 = SERVERS / 30, SERVERS / 5
    evals = 100_000 * 20
    assert round(polls30) == 1667 and round(polls5) == 10000
    assert evals == 2_000_000 and round(evals / polls30) == 1200
    full_bw = polls30 * SNAP / 1e6
    short_bw = polls30 * UNCHANGED / 1e6
    assert round(full_bw) == 333 and short_bw == 0.5 and round(full_bw / short_bw) == 667
    publish = SERVERS * SNAP / 1e9
    assert publish == 10.0 and round(SERVERS * SNAP / 30 / 1e6) == 333     # the whole fleet fetches inside one interval
    assert PUBLISHES * publish == 100.0 and round(PUBLISHES * publish * 1e9 / 3600 / 1e6, 1) == 27.8
    relay = 100 * SNAP / 1e6
    assert relay == 20.0 and round(publish * 1e3 / relay) == 500
    assert (30 / 2, 30, 5 / 2, 5) == (15, 30, 2.5, 5) and polls5 / polls30 == 6
    for must in ('1,667 per second (10,000 per second at 5 s)', '2,000,000, all local: 1,200 times more than the polls',
                 '333 MB/s', '0.5 MB/s: 667 times less', '10 GB, spread over one polling interval', '27.8 MB/s on average',
                 '20 MB: 500 times less', '15 s mean, 30 s max / 2.5 s mean, 5 s max', 'a 6x shorter interval is 6x the polls'):
        assert must in text75, must
    for must_not in ('capacity_check_k', 'guarantee that every server'):
        assert must_not not in text75, must_not
    for vendor in ('LaunchDarkly', 'Unleash', 'Split.io', 'Optimizely', 'Flagsmith', 'Statsig', 'GrowthBook', 'Netflix', 'Facebook'):
        assert vendor not in text75, vendor
    print("capacity_check_j (sy75) passed")
