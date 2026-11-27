"""Runs the python blocks of data/new_lessons/sy75-feature-flags-config.md against independent references:
bucketing (nesting, uniformity, independence), evaluation order, never-throw client behaviour, conditional
fetches, and a propagation simulation."""
import re, sys, random, hashlib, itertools
src = open(sys.argv[1], encoding='utf-8').read()
ns = {}
for b in re.findall(r"```python\n(.*?)```", src, re.S):
    exec(b, ns)
bucket, evaluate, ConfigServer, FlagClient = ns['bucket'], ns['evaluate'], ns['ConfigServer'], ns['FlagClient']

def flag(key, salt='s', percent=None, serve=True, default=False, rules=(), enabled=True):
    f = {'key': key, 'salt': salt, 'enabled': enabled, 'default': default, 'rules': list(rules)}
    f['rollout'] = None if percent is None else {'percent': percent, 'serve': serve}
    return f

# ---- bucketing ---------------------------------------------------------------------------------------------------
assert all(0 <= bucket('f', 's', i) < 10000 for i in range(2000))
assert bucket('f', 's', 'u1') == bucket('f', 's', 'u1')
assert bucket('f', 's', 'u1', buckets=100) < 100
diff_salt = sum(bucket('f', 's1', i) != bucket('f', 's2', i) for i in range(2000))
diff_key = sum(bucket('f1', 's', i) != bucket('f2', 's', i) for i in range(2000))
assert diff_salt > 1990 and diff_key > 1990                               # salt and flag key both feed the hash
N = 200_000
counts = [0] * 100
for i in range(N):
    counts[bucket('f', 's', i) // 100] += 1
assert max(abs(c - N / 100) for c in counts) < 5 * (N / 100) ** 0.5 * 1.0 + 1, counts   # about 5 sigma around 2,000

# ---- a ramp is nested, and exact at the ends -----------------------------------------------------------------------
ids = range(60_000)
def exposed(percent, key='f', salt='s'):
    f = flag(key, salt, percent)
    return {i for i in ids if evaluate(f, {'id': i})[0] is True}
prev = set()
for p in (0, 1, 5, 25, 50, 100):
    cur = exposed(p)
    assert prev <= cur, p                                                  # nobody leaves the rollout as it grows
    assert abs(len(cur) - len(ids) * p / 100) <= 5 * (len(ids) * p / 100 * (1 - p / 100)) ** 0.5 + 1, (p, len(cur))
    prev = cur
assert exposed(0) == set() and len(exposed(100)) == len(ids)              # 0% is nobody, 100% is everybody
# two flags with different salts split independently; the same salt would correlate them completely
a, b = exposed(50, 'fa', 'sa'), exposed(50, 'fb', 'sb')
assert abs(len(a & b) / len(ids) - 0.25) < 0.01, len(a & b)
c, d = exposed(50, 'fa', 'same'), exposed(50, 'fa', 'same')
assert c == d and len(c & d) == len(c)

# ---- evaluation order -----------------------------------------------------------------------------------------------
rule_vip = {'when': {'tier': ['vip']}, 'serve': 'vip-value'}
rule_two = {'when': {'tier': ['pro', 'vip'], 'country': ['IN']}, 'serve': 'in-pro'}
f = flag('x', percent=100, serve='rolled', default='dflt', rules=[rule_vip, rule_two])
assert evaluate(f, {'id': 1, 'tier': 'vip'}) == ('vip-value', 'TARGETING_MATCH')   # rules beat the rollout
assert evaluate(f, {'id': 1, 'tier': 'pro', 'country': 'IN'}) == ('in-pro', 'TARGETING_MATCH')
assert evaluate(f, {'id': 1, 'tier': 'pro', 'country': 'US'}) == ('rolled', 'SPLIT')   # every attribute of a rule must match
assert evaluate(f, {'tier': 'free'}) == ('dflt', 'DEFAULT')                             # no id: cannot be bucketed, never crashes
assert evaluate(flag('x', percent=0, default='dflt'), {'id': 1}) == ('dflt', 'DEFAULT')
off = flag('x', percent=100, default='dflt', rules=[rule_vip], enabled=False)
assert evaluate(off, {'id': 1, 'tier': 'vip'}) == ('dflt', 'DISABLED')                  # the kill switch beats every rule
assert evaluate(flag('x', rules=[{'when': {}, 'serve': 'all'}]), {'id': 1}) == ('all', 'TARGETING_MATCH')  # an empty condition matches everyone

# ---- the server and the client ---------------------------------------------------------------------------------------
snap1 = {'f': flag('f', percent=100, serve='on', default='off')}
server = ConfigServer(snap1)
assert server.fetch(None, 0) == (200, snap1, 1)
assert server.fetch(1, 1) == (304, None, 1)                              # unchanged: no body
server.publish({'f': flag('f', percent=100, serve='on2', default='off')})
assert server.fetch(1, 2)[0] == 200 and server.fetch(2, 3)[0] == 304
assert server.full_sends == 2 and server.fetches == 4

server = ConfigServer(snap1, outages=[(100, 200)])
cl = FlagClient(server, poll_interval=30, phase=0)
assert cl.get('f', {'id': 1}, 'builtin') == ('builtin', 'ERROR')           # before the first fetch: the caller's default
cl.tick(0)
assert cl.get('f', {'id': 1}, 'builtin') == ('on', 'SPLIT')
assert cl.get('nope', {'id': 1}, 'builtin') == ('builtin', 'ERROR')        # an unknown flag is an error, not a crash
cl.tick(10)
assert server.fetches == 1                                                # not due yet: no request
cl.tick(30); cl.tick(60); cl.tick(90)
assert server.fetches == 4 and server.full_sends == 1                     # three conditional polls, no repeated bodies
cl.tick(120)                                                              # during the outage
assert cl.get('f', {'id': 1}, 'builtin') == ('on', 'STALE')                # last good config, labelled as possibly out of date
server.publish({'f': flag('f', percent=100, serve='on2', default='off')})
cl.tick(150)
assert cl.get('f', {'id': 1}, 'builtin') == ('on', 'STALE')                # still down
cl.tick(210)
assert cl.get('f', {'id': 1}, 'builtin') == ('on2', 'SPLIT')               # recovered, new value seen, no longer stale
# garbage in a snapshot never raises out of get()
bad = FlagClient(ConfigServer({'g': {'key': 'g'}}), poll_interval=1)
bad.tick(0)
assert bad.get('g', {'id': 1}, 'safe') == ('safe', 'ERROR')

# ---- propagation: a publish reaches clients within one interval, half of it on average ---------------------------------
def propagation(period, n, seed, step=0.25):
    rnd = random.Random(seed)
    srv = ConfigServer({'f': flag('f', percent=100, serve='on', default='off')})
    clients = [FlagClient(srv, period, phase=rnd.uniform(0, period)) for _ in range(n)]
    t, t_pub, seen = 0.0, 4 * period, {}
    while len(seen) < n:
        if abs(t - t_pub) < step / 2:
            srv.publish({'f': flag('f', percent=100, serve='off-now', default='off', enabled=False)})   # the kill switch
        for i, c in enumerate(clients):
            c.tick(t)
            if t >= t_pub and i not in seen and c.get('f', {'id': 1}, 'builtin')[1] == 'DISABLED':
                seen[i] = t - t_pub
        t += step
    return list(seen.values())
for period in (30, 5):
    lag = propagation(period, 600, seed=period)
    mean = sum(lag) / len(lag)
    assert abs(mean - period / 2) < period * 0.05, (period, mean)
    assert max(lag) <= period + 0.5, (period, max(lag))
print("sy75 code checks passed")
