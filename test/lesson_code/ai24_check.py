"""Runs the python code blocks from data/new_lessons/ai24-semantic-caching.md against reference checks,
and asserts every worked number the lesson prose states."""
import re, sys, random, math
src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
ns = {}
for b in blocks:
    exec(b, ns)
normalize, cosine, SemanticCache = ns['normalize'], ns['cosine'], ns['SemanticCache']
calibrate_threshold, route, alpha_for_budget = ns['calibrate_threshold'], ns['route'], ns['alpha_for_budget']
expected_cost, cascade_cost = ns['expected_cost'], ns['cascade_cost']
random.seed(24)

def ref_cos(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))

for _ in range(200):
    a = [random.uniform(-1, 1) for _ in range(5)]; b = [random.uniform(-1, 1) for _ in range(5)]
    assert abs(cosine(normalize(a), normalize(b)) - ref_cos(a, b)) < 1e-12

# --- cache vs an independent reference model (list of dicts, explicit last-used clock)
class RefCache:
    def __init__(self, threshold, capacity, ttl):
        self.t, self.cap, self.ttl = threshold, capacity, ttl
        self.items, self.clock = [], 0
    def live(self, now):
        self.items = [e for e in self.items if now - e['at'] < self.ttl]
    def get(self, scope, emb, now):
        self.live(now)
        cands = [e for e in self.items if e['scope'] == scope]
        if not cands:
            return None
        best = max(cands, key=lambda e: (ref_cos(emb, e['emb']), -e['used']))
        if ref_cos(emb, best['emb']) < self.t:
            return None
        self.clock += 1; best['used'] = self.clock
        return best['ans']
    def put(self, scope, emb, ans, now):
        self.live(now)
        if len(self.items) >= self.cap:
            self.items.remove(min(self.items, key=lambda e: e['used']))
        self.clock += 1
        self.items.append({'scope': scope, 'emb': emb, 'ans': ans, 'at': now, 'used': self.clock})

def near_threshold(c, scope, emb, now, thr):
    """True if some live in-scope similarity is within 1e-9 of the threshold or of a tie (float noise)."""
    sims = sorted(ref_cos(emb, e['emb']) for e in c.items if e['scope'] == scope and now - e['at'] < c.ttl)
    return any(abs(s - thr) < 1e-9 for s in sims) or any(abs(x - y) < 1e-9 for x, y in zip(sims, sims[1:]))

hits = misses = 0
for trial in range(300):
    thr, cap, ttl = random.choice([0.0, 0.5, 0.8, 0.95]), random.randint(1, 8), random.randint(1, 30)
    c, r = SemanticCache(thr, cap, ttl), RefCache(thr, cap, ttl)
    now = 0
    for step in range(120):
        now += random.randint(0, 3)
        scope = random.choice(['tenantA', 'tenantB'])
        emb = [random.choice([-1, 0, 1]) + random.uniform(-0.3, 0.3) for _ in range(3)]
        if random.random() < 0.5:
            if near_threshold(r, scope, emb, now, thr):
                continue
            got, want = c.get(scope, emb, now), r.get(scope, emb, now)
            assert got == want, (trial, step, got, want)
            if got is None: misses += 1
            else: hits += 1
            if got is not None:
                assert got[0] == scope                     # answers are tagged with their scope below
        else:
            ans = (scope, step)
            c.put(scope, emb, ans, now); r.put(scope, emb, ans, now)
        assert len(c.entries) <= cap
assert hits > 1000 and misses > 1000, (hits, misses)

# expiry: an entry at age == ttl is gone
c = SemanticCache(0.9, 5, ttl=10)
c.put('s', [1, 0], 'x', now=0)
assert c.get('s', [1, 0], now=9) == 'x' and c.get('s', [1, 0], now=10) is None
# best match, not first match above threshold
c = SemanticCache(0.5, 5, ttl=100)
c.put('s', [1, 1], 'ok-ish', 0); c.put('s', [1, 0.01], 'best', 0)
assert c.get('s', [1, 0], 1) == 'best'
# scope isolation
assert c.get('other', [1, 0], 1) is None

# --- threshold calibration vs brute force over every candidate threshold
def ref_calibrate(labelled, minp):
    ok_ts = []
    for t in {s for s, _ in labelled}:
        served = [ok for s, ok in labelled if s >= t]
        if served and sum(served) / len(served) >= minp:
            ok_ts.append(t)
    if not ok_ts:
        return None
    t = min(ok_ts)
    served = [ok for s, ok in labelled if s >= t]
    return (t, sum(served) / len(served), len(served) / len(labelled))
for _ in range(500):
    lab = [(round(random.random(), 2), random.random() < 0.6) for _ in range(random.randint(1, 25))]
    for minp in (0.5, 0.75, 0.9, 1.0):
        assert calibrate_threshold(lab, minp) == ref_calibrate(lab, minp), (lab, minp)

LAB = [(0.97, True), (0.95, True), (0.93, False), (0.92, True), (0.90, True),
       (0.88, False), (0.86, True), (0.84, False), (0.80, False), (0.75, False)]
assert calibrate_threshold(LAB, 0.9) == (0.95, 1.0, 0.2)
assert calibrate_threshold(LAB, 0.75) == (0.90, 0.8, 0.5)
assert calibrate_threshold(LAB, 0.8) == (0.90, 0.8, 0.5)          # drill 4
p093 = [ok for s, ok in LAB if s >= 0.93]
assert round(sum(p093) / len(p093), 2) == 0.67

# --- routing
assert route(0.7, 0.5) == 'strong' and route(0.5, 0.5) == 'strong' and route(0.49, 0.5) == 'weak'
for _ in range(500):
    scores = [round(random.random(), 2) for _ in range(random.randint(1, 30))]
    frac = random.choice([0.0, 0.1, 0.25, 0.5, 1.0])
    a = alpha_for_budget(scores, frac)
    limit = math.floor(frac * len(scores))
    sent = sum(route(s, a) == 'strong' for s in scores)
    assert sent <= limit
    # brute force: no smaller candidate threshold also satisfies the budget
    feasible = [x for x in sorted(set(scores)) + [float('inf')] if sum(s >= x for s in scores) <= limit]
    assert a == min(feasible)

# --- cost model vs counting a population of 1000 queries
def ref_cost(hit, strong, cs, cw, cl, n=1000):
    hits = round(hit * n); misses = n - hits; to_strong = round(strong * misses)
    return (n * cl + to_strong * cs + (misses - to_strong) * cw) / n
for hit, strong in [(0, 1), (0.2, 0.3), (0.4, 0.25), (0.5, 0.0), (1.0, 0.7)]:
    assert abs(expected_cost(hit, strong, 100, 5, 0.5) - ref_cost(hit, strong, 100, 5, 0.5)) < 1e-9
assert abs(expected_cost(0, 1, 100, 5, 0) - 100) < 1e-12
assert abs(expected_cost(0.2, 0.3, 100, 5, 0.5) - 27.3) < 1e-9
assert abs(expected_cost(0.4, 0.25, 100, 5, 0.5) - 17.75) < 1e-9   # drill 7
assert abs(cascade_cost(0.7, 5, 100) - 35) < 1e-9
assert cascade_cost(0.0, 5, 100) > 100                               # drill 8: nothing accepted
print("ai24 code checks passed")
