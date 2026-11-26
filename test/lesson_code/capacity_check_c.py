"""Reproduces every capacity-estimate number in the case studies sy54 to sy56 and checks that each lesson states the
same figures. Usage: capacity_check_c.py <lesson.md> [...]; each file is matched to its section by id prefix."""
import sys, os, math

def need(src, *phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the computed figure: %r' % p

def sy54(src):
    pages, cycle_days, page_kb, links, latency_s, wait_factor = 10e9, 30, 300, 40, 1.0, 10
    seen, fp_bytes, shards, hosts, rel_share = 50e9, 8, 64, 100e6, 0.8
    rate = pages / (cycle_days * 86400)
    bw = rate * page_kb * 1e3
    store_pb = pages * page_kb * 1e3 / 1e15
    due = rate * links
    cycle_s = latency_s + wait_factor * latency_s
    busy_hosts = rate * cycle_s
    big_site_days = 10e6 * cycle_s / 86400
    fp_gb = seen * fp_bytes / 1e9
    pairs = seen * (seen - 1) / 2 / 2 ** (8 * fp_bytes)
    cross = (1 - rel_share) * (1 - 1 / shards)
    robots = hosts / 86400
    assert round(rate) == 3858 and round(bw * 8 / 1e9, 1) == 9.3 and store_pb == 3.0
    assert round(due) == 154321 and round(rate * latency_s) == 3858
    assert cycle_s == 11 and round(busy_hosts) == 42438 and round(big_site_days) == 1273
    assert fp_gb == 400 and round(pairs) == 68 and seen / shards == 781250000
    assert round(cross * 100, 1) == 19.7 and round(robots) == 1157
    # Mercator's disk-based duplicate URL eliminator: seeks, submissions and the downloads they allow
    seek_s, miss_one_in, links_per_page = 8e-3, 6, 10
    seeks = 1 / seek_s
    submissions = seeks * miss_one_in
    assert seeks == 125 and submissions == 750 and submissions / links_per_page == 75
    # the report says a billion pages in a month needs "about 400 pages every second"; exact division gives 386
    paper_rate = 1e9 / (30 * 86400)
    assert round(paper_rate) == 386 and round(rate / paper_rate) == 10      # this lesson's cycle is ten times larger
    need(src, '3,858 pages per second', '9.3 Gbit/s', '| 3 PB |', '154,321 URLs per second',
         '3,858 fetches in flight', '42,438 hosts', 'one request every 11 seconds', '1,273 days',
         '400 GB', 'about 68 colliding pairs', '125 seeks', '750 DUE submissions', '75 downloads per second',
         '781,250,000 URLs', 'about 19.7%', '1,157 robots.txt fetches per second', 'about 400 pages every second', '386 by exact division',
         'ten times that')
    return 'sy54'

def sy55(src):
    dau, per_user, peak, mb, row_b, devices, conn_per_server = 100e6, 20, 3, 2, 300, 2, 100000
    block_mb, blocklist_mb, hash_b, eb, entry_b, others = 4, 100, 32, 1e18, 64, 1.5
    new_gb, link_mbit = 50, 100
    up_mb_s, down_mb_s = 1.2, 5
    events = dau * per_user / 86400
    whole_file = events * mb / 1e3
    rows_day = dau * per_user
    journal_gb_day = rows_day * row_b / 1e9
    journal_tb_year = rows_day * row_b * 365 / 1e12
    blocks_in_list = blocklist_mb / block_mb
    blocks = eb / (block_mb * 1e6)
    index_tb = blocks * entry_b / 1e12
    conns = dau * devices
    notif = events * others
    first_sync_s = new_gb * 1e9 * 8 / (link_mbit * 1e6)
    seq = 1 / up_mb_s + 1 / down_mb_s                       # seconds per MB, upload then download
    overlap = 1 / up_mb_s                                   # download hidden behind the slower upload
    saving = 1 - overlap / seq
    assert round(events) == 23148 and round(events * peak) == 69444
    assert round(whole_file, 1) == 46.3 and round(whole_file * 8) == 370
    assert rows_day == 2e9 and journal_gb_day == 600 and journal_tb_year == 219
    assert blocks_in_list == 25 and blocks_in_list * hash_b == 800
    assert blocks == 2.5e11 and index_tb == 16
    assert conns == 2e8 and conns / conn_per_server == 2000 and round(notif) == 34722
    assert first_sync_s == 4000 and round(first_sync_s / 60) == 67 and round(saving * 100) == 19
    # a 100 MB file with a few bytes inserted at the front: fixed 4 MB blocks all change
    assert 100 / 4 == 25
    need(src, '23,148 file changes per second', '69,444 per second', '46.3 GB/s', '370 Gbit/s',
         '2 billion journal rows per day', '600 GB per day', '219 TB per year', '25 hashes x 32 bytes = 800 bytes',
         '250 billion blocks', '| 16 TB |', '200 million long-poll connections', '2,000 servers',
         '34,722 notifications per second', '4,000 seconds, about 67 minutes', 'about 19%')
    return 'sy55'

def sy56(src):
    views, peak, vids, id_b, count_b, cell_b, ss_b = 5e9, 3, 1e9, 8, 8, 4, 24
    eps, delta, minutes, m = 1e-4, 0.01, 60, 10000
    avg = views / 86400
    n_hour = views / 24
    n_min = views / 1440
    exact_hour_gb = min(vids, n_hour) * (id_b + count_b) / 1e9          # a window holds at most as many keys as events
    exact_min_mb = min(vids, n_min) * (id_b + count_b) / 1e6
    width, depth = math.ceil(math.e / eps), math.ceil(math.log(1 / delta))
    cells = width * depth
    sketch_kb = cells * cell_b / 1e3
    sketches_mb = cells * cell_b * minutes / 1e6
    err = eps * n_hour
    ss_kb = m * ss_b / 1e3
    ss_mb = m * ss_b * minutes / 1e6
    h = math.log(vids) + 0.5772156649                       # harmonic number H(n), n large
    rank = lambda r: n_hour / (r * h)
    cutoff = 1 / (eps * h)
    gap = lambda r: n_hour / (h * r * (r + 1))
    ordered = max(r for r in range(1, 1000) if gap(r) > eps * n_hour)       # adjacent ranks r, r+1 still separated by the error
    ratio_lo, ratio_hi = exact_hour_gb * 1e3 / sketches_mb, exact_hour_gb * 1e3 / ss_mb
    hot = avg * peak / h
    assert round(avg) == 57870 and round(avg * peak) == 173611 and round(n_hour) == 208333333
    assert round(exact_hour_gb, 1) == 3.3 and round(exact_min_mb, 1) == 55.6 and round(exact_min_mb * minutes / 1e3, 1) == 3.3
    assert round(n_min) == 3472222
    assert (width, depth, cells) == (27183, 5, 135915) and round(sketch_kb) == 544 and round(sketches_mb, 1) == 32.6
    assert round(err) == 20833 and m == round(1 / eps) and round(ss_kb) == 240 and round(ss_mb, 1) == 14.4
    assert round(h, 1) == 21.3 and round(rank(10), -3) == 978000 and round(rank(100), -2) == 97800
    assert round(rank(1000), -1) == 9780 and int(cutoff) == 469
    assert round(100 / h, 1) == 4.7 and round(hot, -1) == 8150
    assert ordered == 21 and round(gap(100)) == 968
    assert round(ratio_lo, -1) == 100 and round(ratio_hi, -1) == 230
    assert minutes * m == 600000
    # the per-minute bucket guarantee: N_minute / m per bucket, and 60 buckets add up to the hourly bound
    assert round(60 * (views / 1440) / m) == 20833
    # drill 5: the same sketch at epsilon 1e-3 has a 10x wider error and a 10x smaller width
    assert math.ceil(math.e / 1e-3) == 2719
    need(src, '57,870 views per second', '173,611 views per second', '208,333,333 views', '| 3.3 GB |', '| 55.6 MB |', 'about 100 to 230 times', '| about 968 views |', '| rank 21 |',
         '27,183', '135,915 cells', '| 544 KB |', '| 32.6 MB |', '| 20,833 views |', '10,000 counters', '| 240 KB |', '| 14.4 MB |',
         'H = 21.3', 'about 978,000 views', 'about 97,800 views', 'about 9,780 views', 'rank 469', '4.7%',
         '8,150 views per second', '600,000 candidates')
    assert src.count('| 3.3 GB |') >= 2
    return 'sy56'

SECTIONS = {'sy54': sy54, 'sy55': sy55, 'sy56': sy56}

if __name__ == '__main__':
    done = []
    for path in sys.argv[1:]:
        key = os.path.basename(path)[:4]
        if key in SECTIONS:
            done.append(SECTIONS[key](open(path, encoding='utf-8').read()))
    assert done, 'no lesson files matched'
    print('capacity checks passed: ' + ', '.join(done))
