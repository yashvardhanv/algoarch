"""Reproduces every capacity and sizing number in the wave 3 task 3 case studies (sy60, sy61, sy62) and checks that each
lesson states the same figures. Usage: capacity_check_f.py <lesson.md> [...]; each file is matched to its section by id prefix."""
import sys, os


def need(src, *phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the computed figure: %r' % p


def forbid(src, *phrases):
    for p in phrases:
        assert p not in src, 'lesson text still contains stale wording: %r' % p


def sy60(src):
    # ---- assumptions (labelled in the lesson) ----
    users, subs_each, contest_s = 10_000, 6, 2 * 3600
    peak_share, peak_s = 0.25, 600
    compile_s, tests, per_test_s = 2.0, 30, 0.15
    full_share, early_share, early_tests = 0.4, 0.6, 6
    util = 0.6
    subs = users * subs_each
    avg, peak = subs / contest_s, subs * peak_share / peak_s
    assert subs == 60_000 and round(avg, 1) == 8.3 and peak == 25
    ran = full_share * tests + early_share * early_tests
    assert round(ran, 1) == 15.6
    per = compile_s + ran * per_test_s
    assert round(per, 2) == 4.34
    busy = peak * per
    assert round(busy, 1) == 108.5 and round(busy / util) == 181 and round(avg * per / util) == 60   # 60.3 -> "61" below
    assert round(avg * per / util + 0.5) == 61
    # sanity: a submission can never cost more than compile plus every test at the limit, and the mix is a proper split
    assert full_share + early_share == 1 and early_tests <= tests and per <= compile_s + tests * 2.0
    assert compile_s / per > 0.45                                              # "nearly half"
    fleet = 60
    cap_rate = fleet / per
    backlog = (peak - cap_rate) * peak_s
    assert round(backlog) == 6705 and round(backlog / cap_rate) == 485
    assert peak > cap_rate
    need(src, '60,000', '8.3 per second; 25 per second', '15.6 per submission', '4.34 core-seconds', '108.5', '181', '| 61 |',
         '6,705 queued', '485 seconds', '2.0 of 4.34', 'eight-minute')
    forbid(src, 'LeetCode runs', 'LeetCode uses')
    return 'sy60'


def sy61(src):
    import math
    layers = (150, 500, 1500)                       # simulcast layers, assumed
    audio, top_audio = 32, 3                        # assumed
    nic_mbps, plan = 10_000, 0.5
    rooms, size, relay_share = 1000, 25, 0.10
    mesh = {n: (n - 1) * layers[-1] for n in (4, 8, 25, 100)}
    assert mesh == {4: 4500, 8: 10500, 25: 36000, 100: 148500}
    up = sum(layers) + audio
    assert up == 2182
    down = (size - 2) * layers[0] + layers[-1] + top_audio * audio          # 23 thumbnails + the speaker + 3 audio
    assert down == 5046 and (size - 1) * layers[0] - layers[0] + layers[-1] + top_audio * audio == down
    ingress, egress = size * up / 1000, size * down / 1000
    assert (round(ingress, 2), round(egress, 2)) == (54.55, 126.15)
    per_card = math.floor(nic_mbps * plan / egress)
    assert per_card == 39 and per_card * size == 975
    people = rooms * size
    total_gbps = people * down / 1e6
    assert round(total_gbps) == 126 and math.ceil(total_gbps * 1000 / (nic_mbps * plan)) == 26
    relayed = people * relay_share
    assert relayed == 2500 and round(relayed * (down + up) / 1e6, 2) == 18.07
    # sanity: no receiver can be sent more streams than there are other people; mesh needs n-1 uplink copies
    assert size - 1 >= top_audio and (size - 2) + 1 == size - 1
    need(src, '4,500; 10,500; 36,000; 148,500 kbps', '2,182 kbps', '5,046 kbps', '54.55 Mbps in; 126.15 Mbps out', '39 rooms, 975 participants',
         '126 Gbps out: 26 server cards', '18.07 Gbps', '10.5 Mbps at 8 people', '148.5 Mbps at 100', '2130706431')
    forbid(src, 'Zoom uses', 'Google Meet uses')
    return 'sy61'


def sy62(src):
    tracks = 8_000_000                              # paper, 2010
    kbps, track_s = 160, 240                        # paper's q5 average; 4-minute track assumed
    mix = {'server': 8.8, 'peers': 35.8, 'cache': 55.4}   # paper
    assert round(sum(mix.values()), 1) == 100.0
    mb = kbps * 1000 / 8 * track_s / 1e6
    assert round(mb, 1) == 4.8
    lib_tb = tracks * mb / 1e6
    assert round(lib_tb, 1) == 38.4
    three = lib_tb * (96 + 160 + 320) / 160
    assert round(three, 2) == 138.24
    head = 0.12 * tracks
    assert head == 960_000 and round(head * mb / 1e6, 3) == 4.608
    assert int(5000 / mb) == 1041                    # a 5 GB cache; the paper says about 1,000 tracks
    listeners = 1_000_000
    gbps = listeners * kbps / 1e6
    assert gbps == 160
    srv = gbps * mix['server'] / 100
    assert round(srv, 2) == 14.08
    nop2p = gbps * (mix['server'] + mix['peers']) / 100
    assert round(nop2p, 2) == 71.36 and round(nop2p / srv, 2) == 5.07
    assert round(listeners / track_s) == 4167
    assert round((390 - 265) / 265 * 100) == 47 and round((1.8 - 1.0) / 1.0 * 100) == 80
    # origin load with a CDN: egress x (1 - hit ratio)
    cdn = gbps * (1 - mix['cache'] / 100)               # bytes played from the device cache never reach the CDN
    assert round(cdn, 2) == 71.36 and round(gbps / cdn, 2) == 2.24
    assert round(cdn * 0.10, 2) == 7.14 and round(cdn * 0.01, 2) == 0.71 and round(cdn * 0.05, 2) == 3.57
    assert cdn * 0.10 < gbps * 0.10                    # the old figure (16 Gbps) charged the CDN for device-cache bytes
    # sanity: the head cannot be larger than the library and 12% of 8M tracks fits what 960,000 x 4.8 MB says
    assert head < tracks and head * mb < lib_tb * 1e6
    need(src, '4.8 MB', '38.4 TB', '138.24 TB', '4.608 TB', '1,041 tracks', '160 Gbps', '14.08 Gbps', '71.36 Gbps', '5.07 times', '4,167 plays per second',
         '47% slower median start; 80% more stutter', '7.14 Gbps at the origin', '0.71 Gbps', '2.24 times')
    forbid(src, '16 Gbps at the origin', '1.6 Gbps', 'few dozen servers')
    forbid(src, 'Spotify uses peer-to-peer today', 'Spotify still uses')
    return 'sy62'


SECTIONS = {'sy60': sy60, 'sy61': sy61, 'sy62': sy62}
done = []
for path in sys.argv[1:]:
    key = os.path.basename(path)[:4]
    if key not in SECTIONS:
        continue
    done.append(SECTIONS[key](open(path, encoding='utf-8').read()))
assert done, 'no lessons matched'
print('capacity checks passed: ' + ', '.join(done))
