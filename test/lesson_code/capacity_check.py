"""Reproduces every capacity-estimate number in the system design case studies sy37 to sy40, and checks that
each lesson states the same figures. Usage: capacity_check.py <lesson.md> [<lesson.md> ...]; each file is
matched to its section by its id prefix (sy37-, sy38-, sy39-, sy40-)."""
import sys, math, os

def need(src, *phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the computed figure: %r' % p

def sy37(src):
    docs, source_kb, ratio, shard_gb, copies = 200e6, 2, 1.5, 40, 2
    qps, writes, cpu_ms = 20000, 2000, 2
    raw_gb = docs * source_kb * 1e3 / 1e9
    disk_gb = raw_gb * ratio
    shards = math.ceil(disk_gb / shard_gb)
    per_shard = docs / shards
    total_tb = disk_gb * copies / 1e3
    shard_searches = qps * shards
    cores = shard_searches * cpu_ms / 1000
    routed = qps * 1 * cpu_ms / 1000
    assert (raw_gb, disk_gb, shards) == (400, 600, 15)
    assert round(per_shard / 1e6, 1) == 13.3 and per_shard < 200e6          # inside Elastic's 200M guidance
    assert 10 <= disk_gb / shards <= 50                                    # inside the 10-50 GB guidance
    assert (shards * copies, total_tb) == (30, 1.2)
    assert shard_searches == 300000 and cores == 600 and round(cores / 0.6) == 1000 and routed == 40
    assert writes * copies == 4000
    # deep pagination on 15 shards
    assert (0 + 10, shards * (0 + 10)) == (10, 150)
    assert (10000 + 10, shards * (10000 + 10)) == (10010, 150150)
    # async translog: 5 s window at 2,000 writes/s
    assert writes * 5 == 10000
    need(src, '400 GB', '600 GB', '| 15 |', 'about 13.3 million', '30 copies, 1.2 TB', '300,000 per second',
         '600 cores busy; 1,000 cores at 60%', '40 cores busy', '4,000 document writes/s',
         '| 10,010 | 150,150 |', '| 10 | 150 |', 'up to 10,000 lost')
    return 'sy37'

def sy38(src):
    docs, editors_per_doc, ops_per_s, op_bytes = 1e6, 2, 1, 50
    presence_raw, presence_throttled, meta_bytes = 10, 2, 16 + 16 + 4
    editors = docs * editors_per_doc
    ops_in = editors * ops_per_s
    ops_out = ops_in * (editors_per_doc - 1)
    ingress_mb = ops_in * op_bytes / 1e6
    pres_raw = editors * presence_raw * (editors_per_doc - 1)
    pres_thr = editors * presence_throttled * (editors_per_doc - 1)
    typed, deleted = 150000, 50000
    meta_mb = typed * meta_bytes / 1e6
    visible = typed - deleted
    assert meta_bytes == 36
    assert editors == 2e6 and ops_in == 2e6 and ops_out == 2e6 and ingress_mb == 100
    assert pres_raw == 20e6 and pres_thr == 4e6
    assert meta_mb == 5.4 and visible == 100000 and typed * meta_bytes / visible == 54
    need(src, '2 million WebSocket connections', '| 2 million per second |', '100 MB/s',
         '20 million vs 4 million per second', '5.4 MB of metadata for 100,000 visible characters',
         '54 bytes per visible character', '| 36 bytes |')
    return 'sy38'

def sy39(src):
    players, entry_bytes, writes, rank_reads, shard_limit, shards, replicas = 50e6, 100, 5000, 50000, 50000, 4, 2
    mem_gb = players * entry_bytes / 1e9
    primary_ops = writes + rank_reads
    assert mem_gb == 5 and primary_ops == 55000 and primary_ops > shard_limit
    assert mem_gb / shards == 1.25 and writes / shards == 1250
    assert rank_reads * shards == 200000                       # every rank asks every shard
    per_node = rank_reads / (1 + replicas)
    assert round(per_node) == 16667
    # packing budget
    season = 90 * 86400
    assert season == 7776000 and season < 2**23 == 8388608 and 2**20 == 1048576
    assert (2**20 - 1) * 2**23 + (2**23 - 1) < 2**43 <= 2**53
    need(src, '| 5 GB |', '55,000 per second: above the assumed 50,000', '1.25 GB and 1,250 writes/s per shard',
         '200,000 shard operations/s, 50,000 on every shard', 'about 16,667 rank reads/s per node',
         '7,776,000 seconds', '2^23 = 8,388,608', 'points < 1,048,576')
    return 'sy39'

def sy40(src):
    poll_s, drift_us_per_s, comm_ms, eps_avg_ms = 30, 200, 1, 4        # from the Spanner paper, Section 3
    drift_ms = poll_s * drift_us_per_s / 1000
    assert drift_ms == 6 and drift_ms + comm_ms == 7
    assert 2 * eps_avg_ms == 8
    assert round(14.4 - 9.4, 1) == 5.0                                   # Table 3: 1 replica vs commit wait off
    writes, lag_s = 5000, 2                                              # assumptions
    assert writes * lag_s == 10000
    minutes = 365 * 24 * 60
    assert minutes == 525600
    assert round(minutes * 1e-4, 2) == 52.56 and round(minutes * 1e-5, 3) == 5.256
    need(src, '30 s x 200 us/s = 6 ms', '= 7 ms peak', 'at least 2 x average ε = 8 ms', '9.4 ms vs 14.4 ms: about 5 ms',
         '2 s x 5,000 = 10,000 committed transactions', '52.56 vs 5.256 minutes', '525,600 minutes per year',
         '10,000 transactions in the assumed scenario')
    return 'sy40'

SECTIONS = {'sy37': sy37, 'sy38': sy38, 'sy39': sy39, 'sy40': sy40}

done = []
for path in sys.argv[1:]:
    key = os.path.basename(path)[:4]
    if key in SECTIONS:
        done.append(SECTIONS[key](open(path, encoding='utf-8').read()))
assert done, 'no lesson files matched'
print('capacity checks passed: ' + ', '.join(done))
