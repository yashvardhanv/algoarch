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
         '1.25 million messages', '43 tries, the last one at or after the give-up time', '3 billion per day')
    forbid(src, '41 tries', '114 duplicate')
    return 'sy63'


def sy64(src):
    orders_day, peak_share, window_s, couriers, held_min, ping_s, k = 50_000, 0.12, 20, 4_000, 25, 5, 20      # all assumed
    per_min = orders_day * peak_share / 60
    assert round(per_min) == 100
    per_window = per_min * window_s / 60
    assert round(per_window) == 33 and int(per_window) == 33
    held = per_min * held_min                                    # Little's law
    assert round(held) == 2500 and round(held / couriers, 4) == 0.625
    idle = couriers - round(held)
    assert idle == 1500
    cells, pruned = 33 * idle, 33 * k
    assert (cells, pruned) == (49_500, 660)
    assert couriers / ping_s == 800
    p_acc, wasted_s = 0.7, 15
    assert round(1 / p_acc, 2) == 1.43 and round((1 / p_acc - 1) * wasted_s, 1) == 6.4
    assert round(0.3 ** 3, 3) == 0.027 and 3 * wasted_s == 45 and round((1 / p_acc - 1) * wasted_s / window_s, 2) == 0.32
    assert round(held / 1500, 1) == 1.7                            # the prose's counterfactual: 1,500 couriers carrying everything
    need(src, '100 per minute', 'about 33', '2,500', '62.5%', '49,500 cells', '660 cells', '800 per second', '1.43 offers', '6.4 seconds', '1.7 orders per courier', '2.7% of orders need four or more offers', '45 seconds or more')
    forbid(src, '1,182 of 2,000', '63 of 1,000', '1,380 of 1,500', 'more than a window')
    return 'sy64'


def sy65(src):
    V, mbps, T, ladder, edges, hit = 1_000_000, 3, 2, 15, 100, 0.98          # all assumed
    msgs, size, per_node, cap, renditions = 500, 150, 100_000, 20, 5
    assert V * mbps / 1e6 == 3.0                                             # Tbps
    assert V / T == 500_000
    assert mbps * T / 8 == 0.75
    assert ladder * 3600 / 8 / 1000 == 6.75                                  # GB per hour
    assert round(V / T * (1 - hit)) == 10_000
    assert edges * renditions / T == 250
    assert msgs * V == 500_000_000 and round(msgs * V * size * 8 / 1e9) == 600
    assert round(msgs * V * size * 8 / 1e9 / (V * mbps / 1e6 * 1000), 2) == 0.2     # a fifth of the video egress
    assert cap * V == 20_000_000 and round(cap * V * size * 8 / 1e9) == 24
    assert round(24 / (V * mbps / 1e6 * 1000), 3) == 0.008
    assert cap * size == 3000 and V // per_node == 10
    frame = cap * size
    assert frame == 3000 and 120 * frame == 360_000 and 100_000 * 10 * frame == 3_000_000_000
    assert 1000 / msgs == 2                                          # a 1,000-message ring is 2 s of the 500 per second room
    d = 1.5
    assert (3 * 2 + d, 4 * 2 + d) == (7.5, 9.5) and (3 * 6 + d, 4 * 6 + d) == (19.5, 25.5)
    need(src, '3 Tbps', '500,000 per second', '0.75 MB', '6.75 GB per hour', '10,000 per second', '250 per second',
         '500 million deliveries per second, 600 Gbps', '20% of the video egress', '24 Gbps, 0.8% of the video',
         '1 million frames per second', '10 nodes', '360 KB per room', '3 GB of resume traffic', 'two minutes of history', '7.5 to 9.5 seconds', '19.5 to 25.5 seconds')
    forbid(src, '1,000 join instants', 'many HLS examples', 'reloads at least every', 'A message costs one hop')
    return 'sy65'


SECTIONS = {'sy63': sy63, 'sy64': sy64, 'sy65': sy65}
done = []
for path in sys.argv[1:]:
    key = os.path.basename(path)[:4]
    if key not in SECTIONS:
        continue
    done.append(SECTIONS[key](open(path, encoding='utf-8').read()))
assert done, 'no lessons matched'
print('capacity checks passed: ' + ', '.join(done))
