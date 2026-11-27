"""Reproduces every capacity and sizing number in the wave 3 task 5 case studies (sy66, sy67, sy69) and checks that each
lesson states the same figures. Usage: capacity_check_h.py <lesson.md> [...]; each file is matched to its section by id prefix."""
import sys, os
import math
from math import comb


def need(src, *phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the computed figure: %r' % p


def forbid(src, *phrases):
    for p in phrases:
        assert p.lower() not in src.lower(), 'lesson text still contains stale wording: %r' % p


def p_slow(n, k, q):
    return sum(comb(n, j) * q ** j * (1 - q) ** (n - j) for j in range(n - k + 1, n + 1))


def solve_q(n, k, target):
    lo, hi = 0.0, 0.5
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if p_slow(n, k, mid) <= target else (lo, mid)
    return lo


def sy66(src):
    # ---- assumptions (labelled *assumed* in the lesson) ----
    lines_s, peak_x, line_b = 100_000, 3, 300
    buffer_h = 6
    expand, replicas, compress = 1.2, 1, 8             # full-text store size factor incl. index; one replica; chunk compression
    shard_gb = 30                                      # ES docs: aim for 10 GB to 50 GB per shard
    services, pods, levels = 200, 5_000, 5
    scan_bps = 500e6
    raw_day = lines_s * line_b * 86_400
    assert raw_day == 2.592e12 and lines_s * line_b == 30e6 and lines_s * peak_x * line_b == 90e6
    buf = lines_s * peak_x * line_b * buffer_h * 3600
    assert round(buf / 1e12, 2) == 1.94 and round(3 * buf / 1e12, 2) == 5.83
    full_day = raw_day * expand * (1 + replicas)
    assert round(full_day / 1e12, 2) == 6.22 and round(3 * full_day / 1e12, 1) == 18.7
    primary_day = raw_day * expand
    assert round(primary_day / 1e12, 2) == 3.11
    shards_day = -(-primary_day // (shard_gb * 1e9))
    assert shards_day == 104
    chunk_day = raw_day / compress
    assert chunk_day == 324e9 and round(chunk_day * 365 / 1e12) == 118
    assert round(full_day / chunk_day, 1) == 19.2
    # like-for-like retention: the full-text store keeps 30 days searchable (3 hot, 27 on cheaper tiers, indices still counted)
    days_ft = 30
    assert round(full_day * days_ft / 1e12) == 187
    per_pod_indices = pods * days_ft                   # one index per pod per day, one primary shard each
    assert per_pod_indices == 150_000 and per_pod_indices / 3000 == 50.0
    shard_b = primary_day / pods
    assert round(shard_b / 1e6, 1) == 622.1 and round(10e9 / shard_b) == 16
    assert shards_day * days_ft == 3120 and round(shards_day * days_ft / 3000, 2) == 1.04      # one primary per index
    assert round(per_pod_indices / (shards_day * days_ft), 1) == 48.1
    # what the 19x is made of: index 1.2x, compression 8x, one replica counted for one store only
    assert round(expand * compress, 1) == 9.6 and round(expand * (1 + replicas) * compress, 1) == 19.2
    assert abs(full_day / chunk_day - expand * (1 + replicas) * compress) < 1e-9
    assert pods * levels == 25_000
    lines_day = lines_s * 86_400
    assert lines_day == 8_640_000_000
    svc_hour = raw_day / services / 24
    assert svc_hour == 540e6 and round(svc_hour / scan_bps, 2) == 1.08
    full_scan = raw_day / scan_bps
    assert round(full_scan) == 5184 and round(full_scan / 100, 1) == 51.8
    need(src, '2.592 TB per day', '30 MB per second average, 90 MB per second at peak', '1.94 TB (5.83 TB with three copies)',
         '6.22 TB; 18.7 TB for 3 hot days, 187 TB for 30 days', '| 104 (one primary per index) |', '324 GB; 118 TB for a year', '150,000 indices, 50 GB of master heap',
         '622 MB (stored primary size), 16 times', '3,120 shards', '48 times', '25,000 streams', '8.64 billion a day', '540 MB, about 1.1 s',
         '5,184 worker-seconds, 52 s on 100 workers', '1.2 x 8 = 9.6', '1.2 x 2 x 8 = 19.2')
    forbid(src, 'searchable immediately', 'delete the old lines one by one', '1,825,000', '608 GB', 'the cost gap between the designs is the index', 'the index is most of the cost')
    return 'sy66'


def sy67(src):
    import math
    peak_bps, hit, parent_hit = 20e12, 0.95, 0.8
    nic_bps, util, obj_b = 40e9, 0.5, 500e3
    origin = peak_bps * (1 - hit)
    assert round(origin / 1e12, 6) == 1.0
    assert round(origin * (1 - parent_hit) / 1e12, 6) == 0.2
    assert round(peak_bps * (1 - 0.90) / 1e12, 6) == 2.0 and round((1 - 0.90) / (1 - hit), 6) == 2.0
    servers = peak_bps / (nic_bps * util)
    assert servers == 1000
    rps = peak_bps / (obj_b * 8)
    assert rps == 5e6 and rps / servers == 5000
    n, p = 40_000_000, 0.001                                   # the Akamai paper's worked example
    m = -n * math.log(p) / math.log(2) ** 2
    assert round(m / 1e6, 1) == 575.1 and round(m / 8 / 2 ** 20, 1) == 68.6 and round(m / n * math.log(2)) == 10
    fpr = (1 - math.exp(-10 * n / m)) ** 10
    assert 0.00099 < fpr < 0.00101      # k rounds 9.97 to 10, so the rate is the design 0.1%
    recompute_max, dns_ttl = 30, 20
    assert recompute_max + dns_ttl == 50
    assert round((1 - 5738 / 10209) * 100) == 44                # the paper's disk-write figures
    need(src, '| 1 Tbps |', '| 0.2 Tbps |', '2 Tbps: twice as much', '| 1,000 |', '5 million, 5,000 per server',
         '575.1 million bits, 68.6 MB, 10 hash functions', 'up to 30 s + 20 s = 50 s', '10,209', '5,738', '44%',
         '400 million distinct objects', '74%')
    forbid(src, 'a purge reaches every cache automatically', 'the CDN always serves fresh content')
    return 'sy67'


def sy69(src):
    # ---- assumptions (labelled *assumed* in the lesson) ----
    nodes, n_rep = 200, 3                       # the paper: measurements on a couple hundred nodes; N = 3 typical
    keys, value_b = 1_000_000_000, 1000
    puts, gets = 300_000, 1_000_000
    per_node_bytes = keys * value_b * n_rep / nodes
    assert per_node_bytes == 15e9
    wr = puts * n_rep / nodes
    rd = gets * n_rep / nodes                   # the coordinator asks all N and waits for R (paper, section 4.5)
    assert (wr, rd) == (4500, 15000)
    assert round(p_slow(3, 3, .01) * 100, 2) == 2.97 and round(p_slow(3, 2, .01) * 100, 4) == 0.0298
    assert round(p_slow(3, 1, .01) * 100, 4) == 0.0001
    assert round(solve_q(3, 2, 0.001) * 100, 2) == 1.84 and round(solve_q(3, 3, 0.001) * 100, 3) == 0.033
    hint_bytes = wr * value_b * 3600            # upper bound: every write keeps its own hint
    assert hint_bytes == 16.2e9
    crossover = per_node_bytes / (wr * value_b)
    assert round(crossover) == 3333 and round(crossover / 60) == 56
    leaves_log2, differing, hash_b = 20, 100, 20
    hashes = 1 + 2 * differing * leaves_log2
    assert hashes == 4001 and hashes * hash_b == 80_020 and 1_000_000 * hash_b == 20_000_000
    # the paper's version-count figures do not sum to 100 percent
    parts = [99.94, 0.00057, 0.00047, 0.00009]
    assert round(sum(parts), 4) == 99.9411
    need(src, '4,500 per second', '15,000 per second', '2.97%', '0.0298%', '0.0001%', '1.84% at W = 2', '0.033% at W = 3',
         '16.2 GB', '3,333 s (56 minutes)', '4,001 hashes', '15 GB', '99.9411%')
    forbid(src, 'R + W > N always reads the latest write, sloppy or not', '1.83%')
    return 'sy69'


SECTIONS = {'sy66': sy66, 'sy67': sy67, 'sy69': sy69}
done = []
for path in sys.argv[1:]:
    key = os.path.basename(path)[:4]
    if key not in SECTIONS:
        continue
    done.append(SECTIONS[key](open(path, encoding='utf-8').read()))
assert done, 'no lessons matched'
print('capacity checks passed: ' + ', '.join(done))
