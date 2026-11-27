"""Capacity checks for wave 3, letter j (sy77 now; sy74 to sy76 may add sections). Reproduces every
capacity number in the lesson and fails if stale wording or a wrong figure appears in the text."""
import sys, re
text = open(sys.argv[1], encoding='utf-8').read()
text75 = open(sys.argv[2], encoding='utf-8').read() if len(sys.argv) > 2 else None
text76 = open(sys.argv[3], encoding='utf-8').read() if len(sys.argv) > 3 else None
text74 = open(sys.argv[4], encoding='utf-8').read() if len(sys.argv) > 4 else None

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
    assert polls5 / polls30 == 6
    for must in ('1,667 per second (10,000 per second at 5 s)', '2,000,000, all local: 1,200 times more than the polls',
                 '333 MB/s', '0.5 MB/s: 667 times less', '10 GB, spread over one polling interval', '27.8 MB/s on average',
                 '20 MB: 500 times less', '15 s mean, 30 s max / 2.5 s mean, 5 s max', 'a 6x shorter interval is 6x the polls'):
        assert must in text75, must
    for must_not in ('capacity_check_k', 'guarantee that every server', 'two flags with the same salt expose identical', 'Two flags become one flag', 'Different flags need different salts', 'only because of the salt'):
        assert must_not not in text75, must_not
    for vendor in ('LaunchDarkly', 'Unleash', 'Split.io', 'Optimizely', 'Flagsmith', 'Statsig', 'GrowthBook', 'Netflix', 'Facebook'):
        assert vendor not in text75, vendor
    print("capacity_check_j (sy75) passed")


# ---- sy76: social graph and people you may know ------------------------------------------------------------------------
if text76 is not None:
    USERS, FRIENDS, ID, HUB, SHARDS, KEPT = 100_000_000, 200, 8, 1_000_000, 100, 100
    entries = USERS * FRIENDS
    assert entries == 20_000_000_000 and entries * ID / 1e9 == 160.0
    one = FRIENDS * FRIENDS
    assert one == 40_000 and one * ID == 320_000
    assert one * ID / (KEPT * ID) == 400.0
    base = USERS * FRIENDS * FRIENDS
    hub = HUB * HUB
    assert base == 4 * 10**12 and hub == 10**12 and hub / base == 0.25 and round(100 * hub / (base + hub)) == 20
    touched = lambda S, d: S * (1 - (1 - 1 / S) ** d)
    assert round(touched(SHARDS, 200), 1) == 86.6 and round(touched(SHARDS, 10), 1) == 9.6
    assert round(touched(SHARDS, 1000), 1) == 100.0 and abs(touched(SHARDS, 1000) - 99.996) < 5e-4
    assert USERS * KEPT * ID / 1e9 == 80.0
    assert base / (20_000_000 * 1000) == 200.0
    for must in ('20 billion, 160 GB at 8 bytes', '320 KB, against 800 B for a stored list: 400 times more', '4 x 10^12',
                 '20% of the new total of 5 x 10^12', '86.6 of 100', '100.0 of 100 (99.996)', '80 GB', '200 seconds',
                 'a fifth of the job', '9.6 shards', 'factors of 40 to 50', '25 times fewer', '`1/log 2 = 1.44` against `1/log 22 = 0.32`'):
        assert must in text76, must
    for must_not in ('capacity_check_k', 'under a third of the unguarded work'):
        assert must_not not in text76, must_not
    for company in ('Facebook', 'LinkedIn', 'Instagram', 'Twitter', 'TikTok', 'Meta', 'Pinterest', 'Snapchat'):
        assert company not in text76, company
    print("capacity_check_j (sy76) passed")


# ---- sy74: news aggregator ---------------------------------------------------------------------------------------------
if text74 is not None:
    FEEDS, GAP, ITEMS, FULL, SHORT, CHANGED, DAYS = 100_000, 900, 5_000_000, 50_000, 300, 0.15, 7
    polls = FEEDS / GAP
    assert round(polls) == 111 and round(ITEMS / 86400) == 58
    full_bw = polls * FULL / 1e6
    cond_bw = polls * (CHANGED * FULL + (1 - CHANGED) * SHORT) / 1e6
    assert round(full_bw, 1) == 5.6 and round(cond_bw, 2) == 0.86 and round(full_bw / cond_bw, 1) == 6.4
    kept = ITEMS * DAYS
    assert kept == 35_000_000 and kept * 800 / 1e9 == 28.0 and kept * 400 / 1e9 == 14.0 
    KEY_H, KEY_FULL, ID_B = 8, 5 * 8, 8                      # hashed key, the model's 5-minimum key, the item id
    assert kept * 20 * (KEY_H + ID_B) / 1e9 == 11.2 and kept * 20 * (KEY_FULL + ID_B) / 1e9 == 33.6 and kept * 20 == 700_000_000
    assert kept * 20 * ID_B / 1e9 == 5.6                    # the old figure counted the id only: a table entry needs its key too
    assert round(ITEMS / 86400 * 20 / polls, 1) == 10.4     # lookups are about ten times the polls, not fewer
    assert round(ITEMS / 86400 * 20) == 1157
    curve = {s: 1 - (1 - s ** 5) ** 20 for s in (0.5, 0.6, 0.7, 0.8, 0.9)}
    assert [round(100 * curve[s], 1) for s in (0.5, 0.6, 0.7)] == [47.0, 80.2, 97.5]
    assert round(100 * curve[0.8], 2) == 99.96 and round(100 * curve[0.9], 6) == 99.999998
    import math
    score = lambda n, age, hl=6: (1 + math.log2(n)) * 0.5 ** (age / hl)
    assert round(score(16, 12), 2) == 1.25 and score(8, 24) == 0.25 and score(4, 0) / score(2, 0) == 1.5   # the ranking examples in the lesson
    for must in ('111 per second', '58 per second', '5.6 MB/s', '0.86 MB/s: 6.4 times less', '35 million', '28 GB (14 GB if each minimum is cut to 4 bytes)',
                 '11.2 GB', '33.6 GB', '700 million', '1,157 per second', '1.5 times, not double', 'a quarter of a typical gap', '| 0.5 | 47.0% |', '| 0.6 | 80.2% |', '| 0.7 | 97.5% |', '| 0.8 | 99.96% |', '99.999998%',
                 '101 of 125 true pairs (81%)', 'all 156 true pairs', '`4.0 x 0.0625 = 0.25`'):
        assert must in text74, must
    for must_not in ('99.99998%', 'more than 99% of the true pairs', 'capacity_check_k', '5.6 GB', 'fewer than the polls', 'hundreds of millions of kept', 'a different job', 'double what two', 'unbiased'):
        assert must_not not in text74, must_not
    for company in ('Google News', 'Apple News', 'Flipboard', 'Feedly', 'SmartNews', 'Reddit', 'Twitter', 'Facebook'):
        assert company not in text74, company
    print("capacity_check_j (sy74) passed")
