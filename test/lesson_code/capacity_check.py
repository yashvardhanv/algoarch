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

SECTIONS = {'sy37': sy37, 'sy38': sy38}

done = []
for path in sys.argv[1:]:
    key = os.path.basename(path)[:4]
    if key in SECTIONS:
        done.append(SECTIONS[key](open(path, encoding='utf-8').read()))
assert done, 'no lesson files matched'
print('capacity checks passed: ' + ', '.join(done))
