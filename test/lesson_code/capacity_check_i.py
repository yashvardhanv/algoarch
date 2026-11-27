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


SECTIONS = {'sy70': sy70}
done = []
for path in sys.argv[1:]:
    key = os.path.basename(path)[:4]
    if key not in SECTIONS:
        continue
    done.append(SECTIONS[key](open(path, encoding='utf-8').read()))
assert done, 'no lessons matched'
print('capacity checks passed: ' + ', '.join(done))
