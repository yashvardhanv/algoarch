"""Runs the python blocks of the sy54 web crawler lesson against independent references: the RFC 3986 dot-segment
algorithm, a regex robots matcher, a post-hoc audit of a simulated fetch log, a set-based duplicate eliminator, a
birthday-collision measurement and a breadth-first reference crawl."""
import re, sys, random, collections, hashlib
from urllib.parse import urlsplit, urljoin

src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
assert len(blocks) >= 5, 'expected the lesson code blocks'
ns = {}
for b in blocks:
    exec(b, ns)
canonicalize, remove_dot_segments = ns['canonicalize'], ns['remove_dot_segments']
parse_robots, robots_policy = ns['parse_robots'], ns['robots_policy']
Frontier, host_of = ns['Frontier'], ns['host_of']
BatchDue, fingerprint = ns['BatchDue'], ns['fingerprint']
Budget, owner, crawl, pld = ns['Budget'], ns['owner'], ns['crawl'], ns['pld']

# ---- 1. canonical URLs -------------------------------------------------------------------------------------------
def rfc_dots(inp):                       # RFC 3986 section 5.2.4, two-buffer version, transcribed literally
    out = ''
    while inp:
        if inp.startswith('../'): inp = inp[3:]
        elif inp.startswith('./'): inp = inp[2:]
        elif inp.startswith('/./'): inp = '/' + inp[3:]
        elif inp == '/.': inp = '/'
        elif inp.startswith('/../'):
            inp = '/' + inp[4:]; out = out[:out.rfind('/')] if '/' in out else ''
        elif inp == '/..':
            inp = '/'; out = out[:out.rfind('/')] if '/' in out else ''
        elif inp in ('.', '..'): inp = ''
        else:
            i = inp.find('/', 1)
            if i == -1: i = len(inp)
            out += inp[:i]; inp = inp[i:]
    return out

assert rfc_dots('/a/b/c/./../../g') == '/a/g'          # the RFC's own worked example
assert rfc_dots('mid/content=5/../6') == 'mid/6'
rng = random.Random(54)
for _ in range(3000):
    p = '/' + '/'.join(rng.choice(['a', 'b', '.', '..', '', 'c']) for _ in range(rng.randint(0, 7)))
    assert remove_dot_segments(p) == rfc_dots(p), p
assert remove_dot_segments('/a/b/c/./../../g') == '/a/g'

cases = {
    'HTTP://Example.COM:80/a/./b/../c#frag': 'http://example.com/a/c',
    'https://example.com:443': 'https://example.com/',
    'http://example.com': 'http://example.com/',
    'http://example.com:/': 'http://example.com/',
    'http://example.com:8080/x?q=1&a=2': 'http://example.com:8080/x?q=1&a=2',
    'http://example.com/a/b/..': 'http://example.com/a/',
    'http://example.com/../../x': 'http://example.com/x',
    'http://example.com/%7euser/%7Efoo%2f': 'http://example.com/~user/~foo%2F',
    'http://example.com/a//b': 'http://example.com/a//b',
    'http://example.com/p?x=1#top': 'http://example.com/p?x=1',
    'https://example.com:80/': 'https://example.com:80/',
}
for raw, want in cases.items():
    assert canonicalize(raw) == want, (raw, canonicalize(raw), want)
for raw in list(cases) + ['http://a.com/%41%62?%7e']:
    c = canonicalize(raw)
    assert canonicalize(c) == c, raw                    # idempotent
assert canonicalize(urljoin('http://H.com/a/b/c', '../d#x')) == 'http://h.com/a/d'

# ---- 2. robots.txt -----------------------------------------------------------------------------------------------
def ref_allowed(rules, path):
    """Longest matching pattern wins; equal length goes to allow; no match means allowed. Regex oracle."""
    best = None
    for allow, pat in rules:
        if pat == '': continue
        rx = ''.join('.*' if ch == '*' else re.escape(ch) for ch in (pat[:-1] if pat.endswith('$') else pat))
        rx += r'\Z' if pat.endswith('$') else ''
        if re.match(rx, path, re.S):
            key = (len(pat), allow)
            if best is None or key > best: best = key
    return True if best is None else best[1]

txt = "User-agent: foobot\nAllow: /example/page/\nDisallow: /example/page/disallowed.gif\n"   # RFC 9309 section 5.2
r = robots_policy(200, txt)
assert not r.can_fetch('foobot', '/example/page/disallowed.gif')
assert r.can_fetch('foobot', '/example/page/other.gif') and r.can_fetch('foobot', '/elsewhere')
assert robots_policy(200, 'user-agent: *\nallow: /x\ndisallow: /x\n').can_fetch('bot', '/x')    # tie -> allow
g = robots_policy(200, 'user-agent: *\ndisallow: /*.gif$\n')
assert not g.can_fetch('bot', '/a/b.gif') and g.can_fetch('bot', '/a/b.gif?x=1') and g.can_fetch('bot', '/a/b.png')
g = robots_policy(200, 'user-agent: *\ndisallow: /this/*/exactly$\n')
assert not g.can_fetch('bot', '/this/x/y/exactly') and g.can_fetch('bot', '/this/x/exactly/more')
# group selection: the specific group replaces '*', same-token groups merge, token matching ignores case
g = robots_policy(200, 'user-agent: *\ndisallow: /star\n\nuser-agent: ExampleBot\ndisallow: /one\n\n'
                       'user-agent: examplebot\ndisallow: /two\n')
assert g.can_fetch('ExampleBot', '/star') and not g.can_fetch('EXAMPLEBOT', '/one') and not g.can_fetch('examplebot', '/two')
assert not g.can_fetch('other', '/star') and g.can_fetch('other', '/one')
assert robots_policy(200, 'user-agent: a\ndisallow: /\n').can_fetch('b', '/anything')        # no group, no star: allowed
g = robots_policy(200, 'user-agent: a\nuser-agent: b\ndisallow: /shared\n')                  # consecutive lines share a group
assert not g.can_fetch('a', '/shared') and not g.can_fetch('b', '/shared')
g = robots_policy(200, 'disallow: /orphan\nuser-agent: *\ndisallow: /real\n')                # rule before any group is ignored
assert g.can_fetch('x', '/orphan') and not g.can_fetch('x', '/real')
assert robots_policy(200, 'user-agent: *\ndisallow:\n').can_fetch('x', '/anything')          # empty disallow allows all
assert robots_policy(200, 'user-agent: *\ndisallow: /\n').can_fetch('x', '/robots.txt')      # /robots.txt is implicitly allowed
assert robots_policy(404, '').can_fetch('x', '/private') and robots_policy(403, '').can_fetch('x', '/private')
assert not robots_policy(500, '').can_fetch('x', '/') and not robots_policy(503, 'user-agent: *\nallow: /').can_fetch('x', '/')
assert not robots_policy(None, '').can_fetch('x', '/')                                       # unreachable: assume disallow
g = robots_policy(200, 'User-Agent: X # comment\nDisallow: /a # trailing\n# whole line\nDISALLOW: /b\nbroken line\n')
assert not g.can_fetch('x', '/a') and not g.can_fetch('x', '/b') and g.can_fetch('x', '/c')
alphabet = 'ab/.'
for _ in range(4000):
    rules = []
    for _ in range(rng.randint(0, 5)):
        pat = '/' + ''.join(rng.choice(alphabet + '*') for _ in range(rng.randint(0, 4)))
        if rng.random() < 0.3: pat += '$'
        rules.append((rng.random() < 0.5, pat))
    text = 'user-agent: *\n' + ''.join(('allow: ' if a else 'disallow: ') + p + '\n' for a, p in rules)
    pol = robots_policy(200, text)
    for _ in range(6):
        path = '/' + ''.join(rng.choice(alphabet) for _ in range(rng.randint(0, 6)))
        if path == '/robots.txt': continue
        assert pol.can_fetch('bot', path) == ref_allowed(rules, path), (text, path)

# ---- 3. the polite frontier: audit the fetch log after a simulated crawl ----------------------------------------
def simulate(seed, wait_factor=10):
    rr = random.Random(seed)
    hosts = ['h%d.example' % i for i in range(rr.randint(1, 9))]
    n = rr.randint(1, 70)
    urls = ['http://%s/p%d' % (rr.choice(hosts), i) for i in range(n)]
    info = {u: (rr.randint(0, 2), rr.randint(1, 5), [urls[j] for j in rr.sample(range(i + 1, n), min(n - i - 1, rr.randint(0, 3)))])
            for i, u in enumerate(urls)}                                     # priority, fetch seconds, children (a DAG)
    fr = Frontier(3, rr.randint(1, 4), wait_factor, random.Random(seed))
    seen = set(urls[:rr.randint(1, 3)])
    for u in sorted(seen): fr.add(u, info[u][0])
    workers, now, running, log = rr.randint(1, 5), 0, [], []
    while True:
        while len(running) < workers:
            u = fr.pop(now)
            if u is None: break
            running.append((now + info[u][1], u)); log.append((u, now, now + info[u][1]))
        assert len(fr.back) <= fr.n_back
        ev = [min(running)[0]] if running else []
        if len(running) < workers:
            t = fr.next_ready()
            if t is not None and t > now: ev.append(t)
        if not ev: break
        now = min(ev)
        for end, u in sorted(r for r in running if r[0] <= now):
            running.remove((end, u))
            for c in info[u][2]:
                if c not in seen: seen.add(c); fr.add(c, info[c][0])
            fr.done(u, end, info[u][1])
    return seen, log, info, fr

for seed in range(400):
    wf = 1 + seed % 12                                          # the multiplier is a parameter, not a constant
    seen, log, info, fr = simulate(seed, wf)
    assert sorted(u for u, _, _ in log) == sorted(seen), seed                 # every discovered URL fetched exactly once
    assert fr.pending() == 0
    by_host = collections.defaultdict(list)
    for u, s, e in log: by_host[host_of(u)].append((s, e))
    for h, spans in by_host.items():
        spans.sort()
        for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
            took = e1 - s1
            assert s2 >= e1 + wf * took, (seed, h, spans)        # never overlaps, and waits wf x the last download time

# one host, one worker: spacing is exact and nothing is skipped
fr = Frontier(1, 1, 10, random.Random(0))
for i in range(3): fr.add('http://solo.example/%d' % i, 0)
now, starts = 0, []
while fr.pending() or fr.next_ready() is not None or fr.back:
    u = fr.pop(now)
    if u is None:
        now = fr.next_ready(); continue
    starts.append(now); now += 2; fr.done(u, now, 2)
assert starts == [0, 22, 44], starts
fr = Frontier(1, 1, 3, random.Random(0))                        # another multiplier: wait 3x the 2 second download
for i in range(3): fr.add('http://solo.example/%d' % i, 0)
now, starts = 0, []
while fr.pending() or fr.next_ready() is not None or fr.back:
    u = fr.pop(now)
    if u is None:
        now = fr.next_ready(); continue
    starts.append(now); now += 2; fr.done(u, now, 2)
assert starts == [0, 8, 16], starts

# a host whose queue drained must still be rate limited when new URLs for it arrive later
fr = Frontier(1, 2, 10, random.Random(0))
fr.add('http://late.example/a', 0)
u = fr.pop(0); fr.done(u, 3, 3)                               # queue for late.example is now empty
fr.add('http://late.example/b', 0)
assert fr.pop(4) is None and fr.next_ready() == 33 and fr.pop(33) == 'http://late.example/b'

# priority bias: with one URL per host and one worker, priority 0 comes out earlier on average than priority 2
fr = Frontier(3, 6, 10, random.Random(5))
for i in range(90): fr.add('http://p%d.example/x' % i, i % 3)
order, now = [], 0
while fr.pending() or fr.back:
    u = fr.pop(now)
    if u is None: now = fr.next_ready(); continue
    order.append(int(host_of(u)[1:].split('.')[0]) % 3); fr.done(u, now + 1, 1); now += 1
pos = {p: [i for i, v in enumerate(order) if v == p] for p in (0, 1, 2)}
mean = {p: sum(v) / len(v) for p, v in pos.items()}
assert len(order) == 90 and mean[0] < mean[1] < mean[2], mean

# ---- 4. duplicate URL eliminator, fingerprints, collisions -------------------------------------------------------
for seed in range(300):
    rr = random.Random(seed)
    bits = rr.choice([8, 16, 64])
    due, ref_seen, got, want = BatchDue(bits), set(), [], []
    for _ in range(rr.randint(1, 120)):
        if rr.random() < 0.15:
            got += due.flush()
            assert due.F == sorted(set(due.F))                                 # the 'disk file' stays sorted and unique
        else:
            u = 'http://x.example/%d' % rr.randint(0, 40)
            due.submit(u)
            fp = fingerprint(u, bits)
            if fp not in ref_seen and fp not in {fingerprint(w, bits) for w in want}:
                want.append(u)
            ref_seen.add(fp)
    got += due.flush()
    assert got == want, (seed, bits, got, want)
due = BatchDue(64)
for u in ['http://a/1', 'http://a/2', 'http://a/1']: due.submit(u)
assert due.flush() == ['http://a/1', 'http://a/2']
due.submit('http://a/2'); due.submit('http://a/3')
assert due.flush() == ['http://a/3'] and due.flush() == []
assert fingerprint('x', 64) < 2 ** 64 and fingerprint('x', 16) < 2 ** 16 and fingerprint('x', 64) == fingerprint('x', 64)
# birthday model: expected colliding pairs is n(n-1)/2 / 2^bits; measure it with a 16 bit fingerprint
n, trials, tot = 2000, 30, 0
for t in range(trials):
    c = collections.Counter(fingerprint('http://m.example/%d/%d' % (t, i), 16) for i in range(n))
    tot += sum(v * (v - 1) // 2 for v in c.values())
expected = n * (n - 1) / 2 / 2 ** 16
assert 0.8 * expected < tot / trials < 1.2 * expected, (tot / trials, expected)

# ---- 5. host ownership and budgets -------------------------------------------------------------------------------
for h in ['a.example', 'b.example', 'c.org']:
    assert all(owner(h, k) == owner(h, k) and 0 <= owner(h, k) < k for k in (1, 3, 64))
cnt = collections.Counter(owner('host%d.example' % i, 16) for i in range(16000))
assert len(cnt) == 16 and min(cnt.values()) > 800 and max(cnt.values()) < 1200, cnt
b = Budget(per_link=10, floor=5)
assert b.cap(set()) == 5 and b.cap({'x', 'y', 'z'}) == 30

assert pld('s0.spam.example') == 'spam.example' and pld('a.b.c.example.com') == 'example.com' and pld('localhost') == 'localhost'
assert pld('spam.example:1000') == 'spam.example' and pld('www.good.example:8080') == 'good.example'     # the port is not part of the domain
assert pld('10.0.1.5') == '10.0.1.5' and pld('172.16.1.5') == '172.16.1.5' and pld('10.0.1.5:81') == '10.0.1.5'
assert pld('[::1]:8080') == '[::1]' and pld('[2001:db8::1]') == '[2001:db8::1]'                      # IP literals are their own domain
assert pld('a.b.co.uk') == 'co.uk'          # known limitation: the two-label rule is wrong for public suffixes like co.uk

# ---- 6. the whole loop on a fake web, against a breadth-first reference --------------------------------------------
def make_web(seed):
    rr = random.Random(seed)
    hosts = ['h%d.example.com' % i for i in range(rr.randint(1, 6))]
    web, robots = {}, {}
    for h in hosts:
        rules = rr.choice(['', 'disallow: /p1\n', 'disallow: /p2$\nallow: /p2/ok\n', 'disallow: /p*3\n'])
        robots[h.lower()] = ('user-agent: *\n' + rules) if rules and rr.random() < 0.8 else None
        if rr.random() < 0.15: robots[h.lower()] = 'BOOM'                     # marker: server error on robots.txt
    pages = ['http://%s/p%d%s' % (h, i, rr.choice(['', '/ok'])) for h in hosts for i in range(rr.randint(1, 6))]
    mirror_body, mirror_links = 'MIRROR BODY', rr.sample(pages, min(len(pages), 3))
    def shout(k):                                                   # same URL, upper-case scheme and host
        q = urlsplit(k); return 'HTTP://' + q.netloc.upper() + q.path
    for i, p in enumerate(pages):
        kids = rr.sample(pages, min(len(pages), rr.randint(0, 4)))
        hrefs = [rr.choice([k, k + '#frag', shout(k)]) for k in kids]
        if rr.random() < 0.2: hrefs.append(urlsplit(p).path + '/../' + urlsplit(p).path.lstrip('/'))   # relative, with dots
        if rr.random() < 0.2: hrefs.append('mailto:x@y.z')
        if rr.random() < 0.15:
            web[p] = (200, mirror_body, list(mirror_links))                         # mirrors: same body, same links
        else:
            web[p] = (200, 'body %d' % i, hrefs)
    return web, robots, pages

def ref_crawl(web, robots, seeds):
    pols = {}
    for h, t in robots.items():
        pols[h] = robots_policy(500 if t == 'BOOM' else (200 if t else 404), t or '')
    def ok(u):
        s = urlsplit(u)
        return pols.get(s.netloc, robots_policy(404, '')).can_fetch('algobot', s.path)
    seen, q, fetched = set(), collections.deque(), set()
    def norm(u): return canonicalize(u)
    for s in seeds:
        if norm(s) not in seen: seen.add(norm(s)); q.append(norm(s))
    while q:
        u = q.popleft()
        if not ok(u) or u not in web: continue
        fetched.add(u)
        for h in web[u][2]:
            if not h.lower().startswith('http'): continue
            c = norm(urljoin(u, h))
            if c not in seen: seen.add(c); q.append(c)
    return fetched

for seed in range(250):
    web, robots, pages = make_web(seed)
    def fetch(url):
        s = urlsplit(url)
        if s.path == '/robots.txt':
            t = robots.get(s.netloc)
            return (500, '', []) if t == 'BOOM' else ((200, t, []) if t else (404, '', []))
        canon = canonicalize(url)
        if canon in web: return web[canon]
        return (404, '', [])
    seeds = pages[:2]
    stats = {}
    got = crawl(fetch, seeds, 'algobot', Budget(per_link=10 ** 6, floor=10 ** 6), stats=stats)
    want = ref_crawl(web, robots, seeds)
    assert set(got) == want and len(got) == len(set(got)), (seed, sorted(set(got) ^ want))
    bodies = {web[u][1] for u in got if u in web}
    assert stats['processed'] == len(bodies), (seed, stats, len(bodies))       # content-seen: one processing per distinct body

# robots rules see the query string: /a?x=1 is blocked, /a?x=2 is not
qweb = {'http://q.example/a?x=1': (200, 'one', []), 'http://q.example/a?x=2': (200, 'two', [])}
def fetch_q(url):
    s = urlsplit(url)
    if s.path == '/robots.txt': return (200, 'user-agent: *' + chr(10) + 'disallow: /a?x=1' + chr(10), [])
    return qweb.get(url, (404, '', []))
assert crawl(fetch_q, list(qweb), 'algobot', Budget(per_link=10 ** 6, floor=10 ** 6)) == ['http://q.example/a?x=2']

# spider trap: a host that mints a new URL on every fetch stops at its budget while the rest of the web finishes
good = {'http://good.example/a': (200, 'A', ['http://good.example/b', 'http://trap.example/0']),
        'http://good.example/b': (200, 'B', ['http://other.example/c']),
        'http://other.example/c': (200, 'C', [])}
def fetch_trap(url):
    s = urlsplit(url)
    if s.path == '/robots.txt': return (404, '', [])
    if s.netloc == 'trap.example':
        k = int(s.path[1:]); return (200, 'trap page %d' % k, ['http://trap.example/%d' % (k + 1)])
    return good.get(url, (404, '', []))
got = crawl(fetch_trap, ['http://good.example/a'], 'algobot', Budget(per_link=10, floor=7))
traps = [u for u in got if 'trap.example' in u]
assert len(traps) == 10 and len(got) == 13, (len(traps), len(got))            # one linking domain -> budget 10

# a farm on one hostname with a new port per page: ports do not make new domains
def fetch_ports(url):
    s = urlsplit(url)
    if s.path == '/robots.txt': return (404, '', [])
    if s.netloc.startswith('spam.example:'):
        k = int(s.netloc.split(':')[1]); return (200, 'port page %d' % k, ['http://spam.example:%d/' % (k + 1)])
    return {'http://good.example/a': (200, 'A', ['http://spam.example:1000/'])}.get(url, (404, '', []))
got = crawl(fetch_ports, ['http://good.example/a'], 'algobot', Budget(per_link=10, floor=5), max_pages=3000)
assert len([u for u in got if 'spam.example' in u]) == 10 and len(got) == 11, len(got)
# IP literals: two different networks must not share a budget just because their last two octets agree
def fetch_ip(url):
    s = urlsplit(url)
    if s.path == '/robots.txt': return (404, '', [])
    if s.netloc in ('10.0.1.5', '172.16.1.5'):
        k = int(s.path[1:] or 0); return (200, 'ip %s %d' % (s.netloc, k), ['http://%s/%d' % (s.netloc, k + 1)])
    return {'http://good.example/a': (200, 'A', ['http://10.0.1.5/', 'http://172.16.1.5/'])}.get(url, (404, '', []))
got = crawl(fetch_ip, ['http://good.example/a'], 'algobot', Budget(per_link=10, floor=5))
per = collections.Counter(urlsplit(u).netloc for u in got)
assert per['10.0.1.5'] == 10 and per['172.16.1.5'] == 10, per          # one linking domain each: a cap of 10 apiece

# two hosts of one domain linking to a site count as ONE linking domain
def fetch_two(url):
    s = urlsplit(url)
    if s.path == '/robots.txt': return (404, '', [])
    if s.netloc == 'trap.example':
        k = int(s.path[1:]); return (200, 'trap page %d' % k, ['http://trap.example/%d' % (k + 1)])
    return {'http://www.good.example/a': (200, 'A', ['http://blog.good.example/b', 'http://trap.example/0']),
            'http://blog.good.example/b': (200, 'B', ['http://trap.example/0'])}.get(url, (404, '', []))
got = crawl(fetch_two, ['http://www.good.example/a'], 'algobot', Budget(per_link=10, floor=5))
assert len([u for u in got if 'trap.example' in u]) == 10, len(got)

# a farm of subdomains: one fresh host per page. The budget is per registered domain, so the farm stops at its cap
def fetch_farm(url):
    s = urlsplit(url)
    if s.path == '/robots.txt': return (404, '', [])
    if s.netloc.endswith('.spam.example'):
        k = int(s.netloc.split('.')[0][1:]); return (200, 'farm page %d' % k, ['http://s%d.spam.example/' % (k + 1)])
    return {'http://good.example/a': (200, 'A', ['http://s0.spam.example/'])}.get(url, (404, '', []))
got = crawl(fetch_farm, ['http://good.example/a'], 'algobot', Budget(per_link=10, floor=5))
assert len([u for u in got if 'spam.example' in u]) == 10 and len(got) == 11, len(got)      # one linking domain: cap 10
# limitation, measured: five domains that link to each other raise each other's caps (4 linking domains each: cap 40)
def fetch_ring(url):
    s = urlsplit(url)
    if s.path == '/robots.txt': return (404, '', [])
    k, n = int(s.netloc[1]), int(s.path[1:])
    return (200, 'ring %d %d' % (k, n), ['http://f%d.example/%d' % (k, n + 1)] + ['http://f%d.example/0' % j for j in range(5) if j != k])
got = crawl(fetch_ring, ['http://f0.example/0'], 'algobot', Budget(per_link=10, floor=5))
per_domain = collections.Counter(urlsplit(u).netloc for u in got)
assert set(per_domain.values()) == {40} and len(per_domain) == 5, per_domain          # 4x the single-trap cap of 10
print('sy54 code checks passed')
