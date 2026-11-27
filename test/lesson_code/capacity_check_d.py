"""Reproduces every capacity and sizing number in the wave 3 case studies (so far sy68) and checks that each lesson states
the same figures. Usage: capacity_check_d.py <lesson.md> [...]; each file is matched to its section by id prefix."""
import sys, os


def need(src, *phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the computed figure: %r' % p


def forbid(src, *phrases):
    for p in phrases:
        assert p not in src, 'lesson text still contains stale wording: %r' % p


def sy68(src):
    # ---- assumptions (the lesson labels these as assumptions) ----
    clients, lease_s, heavy_lease_s = 50_000, 12, 60              # lease values are Chubby's default and its stated heavy-load ceiling
    zk_timeout_s = 10                                             # ZooKeeper-style session timeout; clients ping after s/3 of idleness
    locks, hold_h = 5_000, 6                                      # coarse-grained: a few thousand locks held for hours
    fine_ops = 100_000                                            # fine-grained comparison: one lock cycle per request
    # ---- figures read from the papers (Chubby section 4.1, ZooKeeper Table 1); inputs, not results ----
    chubby_direct, chubby_max_clients = 22_000, 90_000
    rpc_low, rpc_high, keepalive_share, acquire_ppm = 1_000, 2_000, 0.93, 31
    zk_write_ops = {3: 21_000, 5: 18_000, 7: 14_000, 9: 12_000, 13: 8_000}   # ZooKeeper Table 1, 0% reads, 1 KB requests

    ka = clients / lease_s
    ka_heavy = clients / heavy_lease_s
    cadence_s = 7                                                 # the paper: lease 12 s, KeepAlives exchanged every 7 s
    ka7 = clients / cadence_s
    heavy_cadence = cadence_s * heavy_lease_s / lease_s           # assumed: the cadence scales with the lease
    ka_heavy7 = clients / heavy_cadence
    assert round(ka) == 4167 and round(ka7) == 7143 and round(heavy_cadence) == 35 and round(ka_heavy7) == 1429
    assert round(ka7 / ka_heavy7) == 5
    lo, hi = rpc_low * keepalive_share, rpc_high * keepalive_share
    assert (round(lo), round(hi)) == (930, 1860)
    snapshot7 = chubby_direct / cadence_s
    assert round(snapshot7) == 3143 and not (lo <= snapshot7 <= hi)     # does NOT reconcile with the snapshot: say so
    assert round(chubby_direct / lease_s) == 1833                       # only agrees if the cadence equalled the lease
    assert round(chubby_max_clients / lease_s) == 7500 and round(chubby_max_clients / heavy_lease_s) == 1500
    acq_lo, acq_hi = rpc_low * acquire_ppm / 1e6, rpc_high * acquire_ppm / 1e6
    assert (round(acq_lo, 3), round(acq_hi, 3)) == (0.031, 0.062)
    pings = clients / (zk_timeout_s / 3)
    assert round(pings) == 15000
    cycles = locks / (hold_h * 3600)
    assert round(cycles, 2) == 0.23 and round(2 * cycles, 2) == 0.46
    fine_writes = 2 * fine_ops
    assert fine_writes == 200_000
    assert round(fine_writes / zk_write_ops[3], 1) == 9.5 and round(fine_writes / zk_write_ops[13]) == 25
    assert zk_write_ops[3] // 2 == 10_500
    window_lo, window_hi = 2 * zk_timeout_s / 3, zk_timeout_s
    assert round(window_lo, 2) == 6.67 and window_hi == 10
    # thundering herd: names returned by getChildren while a queue of n waiters drains (closed forms, checked by simulation in sy68_check.py)
    n = 1000
    chain = n * (n - 1) // 2
    herd = (n - 1) * n * (2 * n - 1) // 6
    assert (chain, herd, herd // chain) == (499_500, 332_833_500, 666)
    arrival = n * (n + 1) // 2
    assert arrival == 500_500
    # sequence counter: a signed 32-bit counter per parent node (ZooKeeper programmer's guide)
    limit = 2 ** 31 - 1
    assert limit == 2_147_483_647
    days = lambda rate: limit / rate / 86400
    assert round(days(1000), 1) == 24.9 and round(days(100), 1) == 248.6 and round(days(10) / 365.25, 1) == 6.8
    assert round(days(cycles) / 365.25) == 294                    # only if all 5,000 locks shared ONE parent
    per_lock = 1 / (hold_h * 3600)                                # one lock: acquired once per hold
    assert round(days(per_lock) / 365.25 / 1e6, 2) == 1.47        # millions of years for a single lock directory
    # Chubby's DNS comparison (paper arithmetic): every process looks up every other, 60 s TTL
    procs, ttl = 3000, 60
    assert procs * procs == 9_000_000 and procs * procs / ttl == 150_000
    batch = 100
    assert procs * (procs // batch) == 90_000
    # fail-over against the grace period (paper figures)
    election_max, grace = 30, 45
    assert election_max < grace
    need(src, '4,167 if renewals', '7,143 KeepAlives per second', '1,429 per second', '3,143 per second', '930 to 1,860', '1.47 million years', 
         '0.23 acquisitions per second', '0.46 writes per second', '200,000 writes per second',
         '9.5 times', '25 times', '10,500 lock cycles per second', '6.67 to 10 seconds',
         '499,500', '332,833,500', '666 times', '500,500', '2,147,483,647', '24.9 days', '248.6 days', '6.8 years', '294 years',
         '150,000 lookups per second', 'longest election')
    forbid(src, 'Redlock is safe', 'millions of locks per second', '833 per second, five times fewer')
    return 'sy68'


SECTIONS = {'sy68': sy68}
done = []
for path in sys.argv[1:]:
    key = os.path.basename(path)[:4]
    if key not in SECTIONS:
        continue
    done.append(SECTIONS[key](open(path, encoding='utf-8').read()))
assert done, 'no lessons matched'
print('capacity checks passed: ' + ', '.join(done))
