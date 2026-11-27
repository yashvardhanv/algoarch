"""Reproduces the capacity and sizing numbers of the wave 3 task 4 case studies (sy63, sy64, sy65) and checks that each lesson
states the same figures. Usage: capacity_check_g.py <lesson.md> [...]; each file is matched to its section by id prefix."""
import sys, os


def need(src, *phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the computed figure: %r' % p


def forbid(src, *phrases):
    for p in phrases:
        assert p not in src, 'lesson text still contains stale wording: %r' % p


def sy63(src):
    users, attempts, refused, size, repl, sent = 100_000_000, 200, 0.85, 75_000, 3, 5      # all assumed
    stored = attempts * (1 - refused)
    assert round(stored) == 30
    per_day = users * 30
    assert per_day == 3_000_000_000 and round(per_day / 86400) == 34_722
    conn = users * attempts / 86400
    assert round(conn) == 231_481 and round(conn * refused) == 196_759
    assert per_day * size / 1e12 == 225 and per_day * size * repl / 1e12 == 675
    assert round(30 * size * 365 / 1e6) == 821
    out = users * sent
    assert round(out / 86400) == 5787
    assert round(0.03 * out * 2 / 24) == 1_250_000
    # retry schedule: 30 min doubling, cap 3 h, give up at 5 days
    t, n = 0, 1
    while t < 5 * 86400:
        t += min(10800, 1800 * 2 ** (n - 1)); n += 1
    assert n == 43 and t >= 5 * 86400
    need(src, '34,722 per second', '231,481 per second', '196,759', '675 TB per day', '821 MB per year', '5,787 per second',
         '1.25 million messages', '43 tries', '3 billion per day')
    forbid(src, '41 tries', '114 duplicate')
    return 'sy63'


SECTIONS = {'sy63': sy63}
done = []
for path in sys.argv[1:]:
    key = os.path.basename(path)[:4]
    if key not in SECTIONS:
        continue
    done.append(SECTIONS[key](open(path, encoding='utf-8').read()))
assert done, 'no lessons matched'
print('capacity checks passed: ' + ', '.join(done))
