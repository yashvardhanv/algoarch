"""Reproduces every capacity and sizing number in the wave 3 task 6 case studies (sy70 to sy73) and checks that each
lesson states the same figures. Usage: capacity_check_i.py <lesson.md> [...]; each file is matched by id prefix."""
import sys, os, math


def need(src, *phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the computed figure: %r' % p


def forbid(src, *phrases):
    for p in phrases:
        assert p not in src, 'lesson text still contains stale wording: %r' % p


def sy70(src):
    dau, per_user = 10_000_000, 100                      # assumptions
    swipes = dau * per_user
    assert swipes == 1_000_000_000 and round(swipes / 86400) == 11574 and round(swipes / 86400 * 3) == 34722
    right = swipes * 0.30                                # assumed right-swipe share
    assert right == 300_000_000 and round(right / 86400) == 3472 and round(right / 86400 * 3) == 10417
    matches = right * 0.05                               # assumed share finding a prior like
    assert matches == 15_000_000 and round(matches / 86400) == 174
    entry = 8 + 8 + 8
    assert entry == 24 and round(right * entry / 1e9, 1) == 7.2 and round(right * entry * 365 / 1e12, 1) == 2.6
    n = 100 * 365 * 3
    assert n == 109_500
    m = math.ceil(-n * math.log(0.01) / math.log(2) ** 2)
    assert round(n * 8 / 1024) == 855 and round(m / 8 / 1024) == 128
    assert 5000 / 100 == 50 and 50000 / 100 == 500 and 8000 / 100 == 80
    # a pool can never be larger than the users who exist near the viewer: an assumed 5,000 profiles is under 0.1% of the 10M
    assert 5000 < dau * 0.001
    need(src, '11,574 per second', '34,722 per second', '3,472 per second', '10,417', '174 per second', '7.2 GB per day',
         '2.6 TB per year', '855 KiB', '128 KiB', '109,500', '50 days or 500 days')
    forbid(src, 'Tinder uses', 'Tinder stores', 'Tinder runs')
    return 'sy70'


def lesson_ns(src):
    import re
    ns = {}
    for b in re.findall(r"```python\n(.*?)```", src, re.S):
        exec(b, ns)
    return ns


def sy71(src):
    import random
    ns = lesson_ns(src)
    per_day, peak_x, pts = 5_000_000, 10, 3600
    assert round(per_day / 86400) == 58 and round(per_day / 86400 * peak_x) == 579
    raw = pts * 16
    assert raw == 57_600 and per_day * raw == 288_000_000_000
    assert round(per_day / 86400 * peak_x * 2) == 1157
    scan, grid = pts * 20_000_000, pts * 9 * 5
    assert scan == 72_000_000_000 and grid == 162_000 and round(scan / grid) == 444_444
    # synthetic winding track: 1 hour at 3 m/s, one point per second (illustrative)
    rng = random.Random(71)
    lat, lon, h, ll = 40.0, -75.0, 0.0, []
    for _ in range(pts):
        ll.append((round(lat, 5), round(lon, 5)))
        h += rng.uniform(-0.05, 0.05)
        lat += 3 * math.cos(h) / 111195
        lon += 3 * math.sin(h) / (111195 * math.cos(math.radians(40)))
    enc = ns['encode_polyline'](ll)
    assert len(enc) == 7208 and round(raw / len(enc), 1) == 8.0
    xy = [((b + 75) * 111195 * math.cos(math.radians(40)), (a - 40) * 111195) for a, b in ll]
    kept = ns['rdp'](xy, 5)
    assert len(kept) == 64
    keptll = [ll[xy.index(q)] for q in kept]
    assert len(ns['encode_polyline'](keptll)) == 252
    need(src, '58 per second', '579 per second', '57,600 bytes', '288 GB', '7,208 bytes', '8.0 times', '64 of 3,600 points', '252 bytes',
         '1,157', '72 billion', '162,000', '444,444')
    forbid(src, 'Strava uses ', 'Strava stores each', 'Strava runs ')
    return 'sy71'


def sy72(src):
    games, secs, moves = 100_000, 600, 80
    assert games * 2 == 200_000 and games * moves / secs == 13_333.333333333334
    mps = games * moves / secs
    assert round(mps * 3) == 40_000
    starts = games / secs
    assert round(starts) == 167 and round(starts * 86400 / 1e6, 1) == 14.4
    assert round(starts * 2) == 333 and round(1000 / 3 * 10) == 3333
    assert games * 1.5 / 1000 == 150.0                                        # KB per game 1.5 -> MB total
    assert moves * 32 == 2560 and round(starts * 86400 * 2560 / 1e9, 1) == 36.9
    need(src, '100,000', '13,333', '40,000 messages per second', '167', '14.4 million', '333', '3,333', '150 MB', '2,560 bytes', '36.9 GB')
    forbid(src, 'Lichess uses Glicko-2 for', 'chess.com uses', 'Lichess pairs players by')
    return 'sy72'


def sy73(src):
    products, budget_day = 20_000_000, 100_000_000
    assert round(budget_day / 86400) == 1157 and round(products / budget_day * 24, 1) == 4.8
    lo, hi = 0.25, 24
    per_hour = budget_day / 24
    assert products / hi <= per_hour <= products / lo
    assert round(products / hi * 24) == 20_000_000 and round(products / lo * 24) == 1_920_000_000
    changes = products * 0.03
    assert changes == 600_000 and round(changes / 86400, 1) == 6.9
    assert budget_day * 16 == 1_600_000_000 and changes * 16 == 9_600_000 and round(budget_day / changes) == 167
    assert products * 3 == 60_000_000
    notes = changes * 3 * 0.10
    assert round(notes) == 180_000 and round(notes / 86400, 1) == 2.1
    # hot product: targets spread evenly over [50%, 100%] of the old price, a 5 percent drop
    watchers = 200_000
    assert round(watchers * 0.05 / 0.50) == 20_000
    # a day cannot hold more fetches per second than the budget says, and changes cannot exceed products
    assert changes < products
    need(src, '20 million', '100 million fetches per day', '1,157 per second', '4.8 hours', '1.92 billion', '600,000 per day', '6.9 per second',
         '1.6 GB per day', '9.6 MB per day', '167 times smaller', '60 million', '180,000 per day', '2.1 per second', '20,000 alerts crossed', '200,000')
    forbid(src, 'CamelCamelCamel uses', 'Keepa uses', 'Amazon blocks', 'Google Shopping uses')
    return 'sy73'


SECTIONS = {'sy70': sy70, 'sy71': sy71, 'sy72': sy72, 'sy73': sy73}
done = []
for path in sys.argv[1:]:
    key = os.path.basename(path)[:4]
    if key not in SECTIONS:
        continue
    done.append(SECTIONS[key](open(path, encoding='utf-8').read()))
assert done, 'no lessons matched'
print('capacity checks passed: ' + ', '.join(done))
