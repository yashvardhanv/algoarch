"""Reproduces every capacity and sizing number in the wave 3 case studies sy57 to sy59 and checks that each lesson states
the same figures. Usage: capacity_check_e.py <lesson.md> [...]; each file is matched to its section by id prefix."""
import sys, os


def need(src, *phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the computed figure: %r' % p


def forbid(src, *phrases):
    for p in phrases:
        assert p not in src, 'lesson text still contains stale wording: %r' % p


def sy57(src):
    # ---- figures read from Bast et al., "Route Planning in Transportation Networks" (2015): inputs, not results ----
    vertices, arcs = 18_000_000, 42_500_000                       # Western Europe benchmark (PTV)
    dij_scans, dij_us = 9_326_696, 2_195_080                      # Table 1, Dijkstra, random pairs, one core of an Intel X5680
    bidir_us = 1_205_660
    ch_scans, ch_us = 280, 110                                    # Table 1, CH (distance only)
    ch_path_ms, crp_path_ms, crp_custom_ms = 0.21, 1.81, 370      # Table 2 (travel time, no turn costs), CRP customization "roughly 370 ms"
    # ---- assumptions (the lesson labels these as assumptions) ----
    peak_qps = 50_000                                             # route requests per second at peak, one region
    drivers, ping_s, ping_bytes = 1_000_000, 5, 100               # navigating drivers in the region, one GPS ping per 5 s, bytes per ping
    bucket_min, bytes_per_bucket, profiles, profile_id_bytes = 15, 1, 1000, 2
    # ---- results ----
    graph_bytes = arcs * 8 + vertices * 4                         # 4 B head + 4 B weight per arc, 4 B offset per vertex
    assert round(graph_bytes / 2 ** 30, 2) == 0.38
    ratio = dij_us / ch_us
    assert round(ratio) == 19_955
    cores = lambda us: peak_qps * us / 1e6                        # cores 100% busy
    assert round(cores(dij_us)) == 109_754 and round(cores(bidir_us)) == 60_283
    assert round(cores(ch_us), 1) == 5.5 and round(cores(ch_path_ms * 1000), 1) == 10.5
    assert round(cores(crp_path_ms * 1000), 1) == 90.5
    pings = drivers / ping_s
    assert pings == 200_000 and pings * 60 == 12_000_000
    assert round(pings * ping_bytes / 1e6) == 20
    assert round(100 * pings * 60 / arcs, 1) == 28.2              # upper bound: even if every ping hit a different arc
    buckets = 7 * 24 * 60 // bucket_min
    assert buckets == 672
    per_arc_series = arcs * buckets * bytes_per_bucket
    assert round(per_arc_series / 1e9, 1) == 28.6
    shared = arcs * profile_id_bytes + profiles * buckets * bytes_per_bucket
    assert round(shared / 1e6) == 86 and round(per_arc_series / shared) == 333
    assert round(100 * crp_custom_ms / 1000 / 60, 2) == 0.62      # refresh once a minute: share of one 12-core server
    need(src, '9,326,696', '2,195,080', '110 microseconds', '19,955 times', '50,000 route requests per second',
         '109,754 cores', '10.5 cores', '90.5 cores', '200,000 pings per second', '12,000,000', '28.2%', '28.6 GB', '86 MB',
         '333 times', '370 ms', '0.38 GiB')
    forbid(src, 'Google uses contraction hierarchies', 'Google Maps uses contraction')
    return 'sy57'


def sy58(src):
    # ---- assumptions (every input is the lesson's own; no company figures were read) ----
    searches, look_to_book, nights = 50_000, 500, 3
    listings, days = 5_000_000, 365
    hotels, room_types, row_bytes = 500_000, 6, 16
    hot_rooms, hot_attempts_per_min, ttl_s = 40, 2_000, 600
    # ---- results ----
    bookings = searches / look_to_book
    assert bookings == 100
    assert bookings * nights == 300 and bookings * 2 == 200                 # row updates; reserve and confirm transactions
    assert round(100 * bookings / searches, 1) == 0.2
    bitmap_bytes = listings * days / 8
    assert round(bitmap_bytes / 1e6) == 228
    rows = hotels * room_types * days
    assert rows == 1_095_000_000 and round(rows * row_bytes / 1e9, 1) == 17.5
    held = bookings * ttl_s
    assert held == 60_000 and held * nights == 180_000
    assert round(100 * held * nights / rows, 3) == 0.016
    per_s = hot_attempts_per_min / 60
    assert round(per_s, 1) == 33.3 and round(hot_rooms / per_s, 1) == 1.2
    need(src, '100 bookings per second', '300 row updates per second', '228 MB', '1,095,000,000 rows', '17.5 GB', '60,000 reservations',
         '180,000 room-nights', '0.016%', '33.3 attempts per second', '1.2 seconds', '0.2% of the request rate', '50,000 searches')
    forbid(src, 'Airbnb stores', 'Booking.com uses', 'Airbnb uses')
    return 'sy58'


SECTIONS = {'sy57': sy57, 'sy58': sy58}
done = []
for path in sys.argv[1:]:
    key = os.path.basename(path)[:4]
    if key not in SECTIONS:
        continue
    done.append(SECTIONS[key](open(path, encoding='utf-8').read()))
assert done, 'no lessons matched'
print('capacity checks passed: ' + ', '.join(done))
