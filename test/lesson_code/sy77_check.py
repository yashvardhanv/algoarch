"""Runs the python blocks of data/new_lessons/sy77-dns-at-scale.md against independent references.
Checks: wire-size arithmetic against a byte-level parser, resolver semantics (TTL boundary, zero TTL, clamp,
negative caching, serve-stale, failure recheck), coalescing, and the rate formula against a Poisson simulation."""
import re, sys, random, struct, math
src = open(sys.argv[1], encoding='utf-8').read()
ns = {}
for b in re.findall(r"```python\n(.*?)```", src, re.S):
    exec(b, ns)
encode_name, build_a_response, max_a_records = ns['encode_name'], ns['build_a_response'], ns['max_a_records']
Zone, Resolver, burst = ns['Zone'], ns['Resolver'], ns['burst']
upstream_rate, authoritative_qps, live_entries = ns['upstream_rate'], ns['authoritative_qps'], ns['live_entries']

# ---- wire format: parse the bytes back independently --------------------------------------------------------
def parse(pkt):
    ident, flags, qd, an, ns_, ar = struct.unpack('!HHHHHH', pkt[:12])
    i = 12
    while pkt[i] != 0:
        i += 1 + pkt[i]
    i += 1 + 4                                   # root label, qtype, qclass
    answers = []
    for _ in range(an):
        assert pkt[i] & 0xC0 == 0xC0             # a compression pointer to the question name
        assert struct.unpack('!H', pkt[i:i + 2])[0] & 0x3FFF == 12
        t, c, ttl, rdlen = struct.unpack('!HHIH', pkt[i + 2:i + 12])
        answers.append((t, c, ttl, pkt[i + 12:i + 12 + rdlen]))
        i += 12 + rdlen
    assert i == len(pkt), "trailing bytes"
    return an, answers
for n in (0, 1, 5, 29, 30):
    got, ans = parse(build_a_response('www.example.com', n, ttl=77))
    assert got == n and all(a == (1, 1, 77, bytes([192, 0, 2, 1])) for a in ans)
assert encode_name('www.example.com') == b'\x03www\x07example\x03com\x00'
assert encode_name('example.com.') == encode_name('example.com')
assert len(build_a_response('www.example.com', 0)) == 12 + 17 + 4
assert max_a_records('www.example.com') == 29                          # the figure quoted in the lesson
assert len(build_a_response('www.example.com', 29)) <= 512 < len(build_a_response('www.example.com', 30))
random.seed(5)
for _ in range(300):                                                    # random names, random limits
    labels = [''.join(random.choice('abcdefghij') for _ in range(random.randint(1, 20))) for _ in range(random.randint(1, 4))]
    name = '.'.join(labels)
    limit = random.choice((512, 512, 1232, 4096))
    ref = (limit - 12 - (len(encode_name(name)) + 4)) // 16
    assert max_a_records(name, limit) == ref, (name, limit)
    assert len(build_a_response(name, ref)) <= limit < len(build_a_response(name, ref + 1))

# ---- resolver semantics --------------------------------------------------------------------------------------
def fresh(**kw):
    z = Zone({'a.example': ('192.0.2.1', 60), 'zero.example': ('192.0.2.9', 0), 'big.example': ('192.0.2.7', 10**9)},
             soa_minimum=300, soa_ttl=3600, outages=kw.pop('outages', ()))
    return z, Resolver(z, **kw)
z, r = fresh()
assert r.resolve('a.example', 0) == ('OK', '192.0.2.1', 60, 'upstream')
assert r.resolve('a.example', 59.5) == ('OK', '192.0.2.1', 0.5, 'cache')
assert r.resolve('a.example', 60)[3] == 'upstream'                      # at exactly the TTL the entry is expired
assert z.queries == 2
z, r = fresh()
for t in (0, 0.25, 0.5, 0.75, 1, 1.0001):
    assert r.resolve('zero.example', t)[3] == 'upstream'                # TTL 0 is never cached, not even for a moment
assert z.queries == 6
z, r = fresh(max_ttl=100)
assert r.resolve('big.example', 0)[2] == 100 and r.resolve('big.example', 99)[3] == 'cache' and r.resolve('big.example', 100)[3] == 'upstream'
z, r = fresh()
assert r.resolve('nope.example', 0) == ('NXDOMAIN', None, 300, 'upstream')          # min(SOA minimum 300, SOA ttl 3600)
assert r.resolve('nope.example', 299)[3] == 'cache' and r.resolve('nope.example', 299)[0] == 'NXDOMAIN'
assert r.resolve('nope.example', 300)[3] == 'upstream'
z2 = Zone({}, soa_minimum=3600, soa_ttl=60)
assert z2.query('x', 0) == ('NXDOMAIN', None, 60)                      # the other operand of the min
# outage without serve-stale: the answer disappears the moment the entry expires
z, r = fresh(outages=[(100, 400)])
r.resolve('a.example', 0)
assert r.resolve('a.example', 59)[3] == 'cache'
assert r.resolve('a.example', 100) == ('SERVFAIL', None, 0, 'failure')
# outage with serve-stale: old answer, 30 s hand-out TTL, until max_stale after expiry
z, r = fresh(outages=[(100, 400)], serve_stale=True, max_stale=200)
r.resolve('a.example', 0)
assert r.resolve('a.example', 100) == ('OK', '192.0.2.1', 30, 'stale')
assert r.resolve('a.example', 259)[3] == 'stale'                        # 60 + 200 = 260 is the last second boundary
assert r.resolve('a.example', 260)[0] == 'SERVFAIL'
# serve-stale INSIDE the failure-recheck window: the attempt at 100 failed, so 101 and 129 must not query upstream, and must still be stale
z, r = fresh(outages=[(100, 400)], serve_stale=True, max_stale=200)
r.resolve('a.example', 0)
assert r.resolve('a.example', 100)[3] == 'stale' and z.queries == 2
assert r.resolve('a.example', 101) == ('OK', '192.0.2.1', 30, 'stale') and z.queries == 2     # inside the recheck window: stale, no new attempt
assert r.resolve('a.example', 129)[3] == 'stale' and z.queries == 2
assert r.resolve('a.example', 130)[3] == 'stale' and z.queries == 3                           # the recheck is due: one attempt, still stale
# once max_stale has passed, a query inside the recheck window is a failure, not stale
assert r.resolve('a.example', 259)[3] == 'stale'
assert r.resolve('a.example', 260)[0] == 'SERVFAIL'
# negative answers are not served stale (the lesson's simplification)
z, r = fresh(outages=[(1000, 2000)], serve_stale=True)
r.resolve('nope.example', 0)
assert r.resolve('nope.example', 1000)[0] == 'SERVFAIL'
# the recheck is per name: a failure of one name does not suppress the first attempt for another
z, r = fresh(outages=[(0, 600)])
r.resolve('a.example', 0)
assert z.queries == 1
r.resolve('big.example', 1)
assert z.queries == 2                                                    # a different name is still tried at once
r.resolve('a.example', 2)
assert z.queries == 2                                                    # the first name is still inside its own window
# failure recheck: a name queried every second during a 600 s outage costs 20 upstream attempts, not 600
z, r = fresh(outages=[(0, 600)])
for t in range(600):
    r.resolve('a.example', t)
assert z.queries == 20, z.queries
# recovery: the first success after the outage caches normally
assert r.resolve('a.example', 600)[3] == 'upstream' and r.resolve('a.example', 601)[3] == 'cache'
# the same outage with a shorter recheck costs proportionally more
z, r = fresh(outages=[(0, 600)], recheck=10)
for t in range(600):
    r.resolve('a.example', t)
assert z.queries == 60

# ---- coalescing ---------------------------------------------------------------------------------------------
random.seed(9)
for _ in range(300):
    times = sorted(random.uniform(0, 3) for _ in range(random.randint(0, 40)))
    rtt = random.choice((0.0, 0.05, 0.3, 1.0))
    assert burst(times, rtt, True) == (1 if times else 0)
    ref = (1 + sum(1 for t in times[1:] if t < times[0] + rtt)) if times else 0
    assert burst(times, rtt, False) == ref, (times, rtt)
assert burst([0.0] * 500, 0.2, False) == 500 and burst([0.0] * 500, 0.2, True) == 1
assert burst([0.0, 0.2], 0.2, False) == 1                               # an arrival exactly at the response time is a cache hit

# ---- the rate formula against a simulation --------------------------------------------------------------------
def simulate(lam, ttl, horizon, seed):
    rnd = random.Random(seed)
    z = Zone({'n': ('192.0.2.1', ttl)})
    res = Resolver(z)
    t = 0.0
    while True:
        t += rnd.expovariate(lam)
        if t > horizon:
            break
        res.resolve('n', t)
    return z.queries / horizon
for lam, ttl in ((0.5, 10), (5, 2), (0.05, 60), (20, 1), (0.01, 5)):
    horizon = 80000 / lam
    got = simulate(lam, ttl, horizon, seed=int(lam * 100 + ttl))
    want = upstream_rate(lam, ttl)
    assert abs(got - want) / want < 0.03, (lam, ttl, got, want)
assert upstream_rate(1000, 60) < 0.0167 and upstream_rate(0.001, 60) > 0.00094
assert abs(authoritative_qps(100000, 2.0, 60) - 1652.89) < 0.01
assert authoritative_qps(100000, 2.0, 60) < 100000 / 60                 # never above the R / T ceiling
assert abs(live_entries([1.0, 1.0], 9) - 1.8) < 1e-9
# a name nobody asks for is never cached; a name asked for constantly is always cached
assert live_entries([1e-9], 60) < 1e-6 and abs(live_entries([1e9], 60) - 1.0) < 1e-6

# ---- staleness after a change, from the cache state itself ------------------------------------------------------
rnd = random.Random(3)
lam, ttl, t_change, n = 2.0, 10, 100.0, 2000
total = 0.0
for _ in range(n):
    z = Zone({'n': ('192.0.2.1', ttl)})
    res = Resolver(z)
    t = 0.0
    while True:
        t += rnd.expovariate(lam)
        if t > t_change:
            break
        res.resolve('n', t)
    entry = res.cache['n']
    total += max(0.0, entry[2] - t_change)                               # how long this resolver still hands out the old address
mean = total / n
want = ttl / 2 * lam * ttl / (1 + lam * ttl)
assert abs(mean - want) < 0.3, (mean, want)
print("sy77 code checks passed")
