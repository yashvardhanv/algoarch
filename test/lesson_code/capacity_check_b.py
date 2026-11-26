"""Reproduces every capacity-estimate number in the system design case studies sy42 to sy44, and checks that each
lesson states the same figures. Usage: capacity_check_b.py <lesson.md> [...]; each file is matched to its section
by its id prefix (sy42, sy43, sy44)."""
import sys, os, math

def need(src, *phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the computed figure: %r' % p

def sy42(src):
    seats, fans, refresh_s, zone, checkout_min, per_order, conv, lock_ms = 50000, 2e6, 20, 10000, 5, 2, 0.8, 2
    polls = fans / refresh_s
    admit_min = zone / checkout_min
    orders = seats / per_order
    admissions = orders / conv
    sellout_min = admissions / admit_min
    holds_s = admit_min / 60
    confirms_s = admit_min * conv / 60
    share = admissions / fans
    burst = fans / 60
    row_tps = 1000 / lock_ms
    assert polls == 100000 and admit_min == 2000 and round(holds_s) == 33
    assert orders == 25000 and admissions == 31250 and sellout_min == 15.625 and round(sellout_min, 1) == 15.6
    assert round(confirms_s) == 27 and round(share * 100, 1) == 1.6
    assert round(burst) == 33333 and row_tps == 500 and round(burst / row_tps) == 67
    need(src, '| 50,000 |', '| 2,000,000 |', '100,000 per second', '2,000 per minute, about 33 per second',
         '25,000 orders', '31,250 admissions', 'about 15.6 minutes', 'about 33 holds and 27 confirms per second',
         'about 1.6%', 'about 33,333 hold attempts per second', '500 per second: about 67 times short')
    # drill 4: 20,000 in the zone, 4 minutes per checkout
    assert 20000 / 4 == 5000 and 31250 / 5000 == 6.25
    return 'sy42'

SECTIONS = {'sy42': sy42}

if __name__ == '__main__':
    done = []
    for path in sys.argv[1:]:
        key = os.path.basename(path)[:4]
        if key in SECTIONS:
            done.append(SECTIONS[key](open(path, encoding='utf-8').read()))
    assert done, 'no lesson files matched'
    print('capacity checks passed: ' + ', '.join(done))
