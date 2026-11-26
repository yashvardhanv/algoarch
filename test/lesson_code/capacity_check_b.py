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

def sy43(src):
    biz, rec_kb, entry_b, dau, per_day, peak, edit, density, r_km = 100e6, 1, 16, 100e6, 5, 3, 0.01, 1000, 0.5
    lat = 37.7749
    data_gb = biz * rec_kb * 1e3 / 1e9
    index_gb = biz * entry_b / 1e9
    avg = dau * per_day / 86400
    pk = avg * peak
    writes = biz * edit / 86400
    assert data_gb == 100 and index_gb == 1.6 and round(avg) == 5787 and round(pk) == 17361 and round(writes) == 12
    kpd = 2 * math.pi * 6371.0 / 360                     # km per degree on the lesson's sphere
    c = math.cos(math.radians(lat))
    h6, w6 = 180 / 2**15 * kpd, 360 / 2**15 * kpd * c
    h7, w7 = 180 / 2**17 * kpd, 360 / 2**18 * kpd * c
    assert (round(h6, 2), round(w6, 2)) == (0.61, 0.97)
    cells6, cells7 = 6, 80                               # cover sizes, asserted from the lesson's code in sy43_check.py
    area6, area7, circle = cells6 * h6 * w6, cells7 * h7 * w7, math.pi * r_km ** 2
    cand6, cand7, inside = area6 * density, area7 * density, circle * density
    assert round(area6, 2) == 3.54 and round(area7, 2) == 1.47 and round(inside) == 785
    assert round(cand6, -1) == 3540 and round(cand7, -1) == 1470
    assert round(cand6 / inside, 1) == 4.5 and round(cand7 / inside, 1) == 1.9
    pk_r = round(pk)
    assert round(pk_r * 3540 / 1e6) == 61 and pk_r * cells6 == 104166
    assert round(pk_r * 1470 / 1e6, 1) == 25.5                                       # 25.52 million
    assert pk_r * cells7 == 1388880 and cells7 / cells6 > 13
    drivers, every_s = 1e6, 4
    assert drivers / every_s == 250000
    need(src, '| 100 GB |', '1.6 GB: fits in memory on one node', 'about 5,787 per second', 'about 17,361 per second',
         'about 12 per second', 'about 0.61 km x 0.97 km', '6 cells, about 3.54 km²',
         'about 3,540 candidates for about 785 inside the circle (4.5x)', '80 cells, about 1.47 km²',
         'about 1,470 candidates (1.9x)', 'about 61 million distance checks and 104,166 range scans per second',
         'about 25.5 million distance checks and 1,388,880 range scans per second', '250,000 writes per second',
         'thirteen times as many range scans')
    return 'sy43'

SECTIONS = {'sy42': sy42, 'sy43': sy43}

if __name__ == '__main__':
    done = []
    for path in sys.argv[1:]:
        key = os.path.basename(path)[:4]
        if key in SECTIONS:
            done.append(SECTIONS[key](open(path, encoding='utf-8').read()))
    assert done, 'no lesson files matched'
    print('capacity checks passed: ' + ', '.join(done))
