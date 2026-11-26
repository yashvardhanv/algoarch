"""Runs the python blocks from data/new_lessons/ai28-autodiff-gradient-descent.md against reference checks."""
import re, sys, math, random
src = open(sys.argv[1], encoding='utf-8').read()
ns = {}
for b in re.findall(r"```python\n(.*?)```", src, re.S):
    exec(b, ns)
Value, numeric_grad = ns['Value'], ns['numeric_grad']
Momentum, Adam, sgd_step = ns['Momentum'], ns['Adam'], ns['sgd_step']
random.seed(28)

# ---- 1. engine vs central finite differences on random expression DAGs ----
def build(vals, rnd, depth, pool):
    """Random expression over the leaves; reuses sub-expressions so nodes have several parents."""
    if depth == 0 or rnd.random() < 0.15:
        return rnd.choice(vals)
    kind = rnd.choice(['add', 'mul', 'sub', 'tanh', 'exp', 'reuse', 'div', 'pow', 'logsq', 'relu'])
    if kind == 'reuse' and pool:
        return rnd.choice(pool) * build(vals, rnd, depth - 1, pool)
    a = build(vals, rnd, depth - 1, pool); pool.append(a)
    if kind in ('add', 'mul', 'sub'):
        b = build(vals, rnd, depth - 1, pool)
        return a + b if kind == 'add' else a * b if kind == 'mul' else a - b
    if kind == 'tanh': return a.tanh()
    if kind == 'exp': return (a * 0.3).exp()
    if kind == 'div': return a / (a * a + 1.5)
    if kind == 'pow': return (a * a + 1.0) ** 0.5
    if kind == 'logsq': return (a * a + 1.0).log()
    return a.relu() + a * 0.1
def f_of(seed, depth):
    def f(*xs):
        rnd = random.Random(seed)
        vals = [x if isinstance(x, Value) else Value(x) for x in xs]
        return build(vals, rnd, depth, [])
    return f
checked = 0
for t in range(300):
    n = random.randint(1, 3)
    xs = [random.uniform(-1.5, 1.5) for _ in range(n)]
    f = f_of(t, random.randint(1, 6))
    leaves = [Value(x) for x in xs]
    out = f(*leaves); out.backward()
    num = numeric_grad(lambda *a: f(*a).data, xs)
    for l, g in zip(leaves, num):
        assert abs(l.grad - g) < 1e-5 * max(1.0, abs(g)), (t, l.grad, g)
        checked += 1
assert checked > 300

# ---- 2. accumulation: a node used twice gets the SUM of both paths ----
x = Value(3.0); y = x * x + x            # dy/dx = 2x + 1 = 7
y.backward(); assert abs(x.grad - 7.0) < 1e-12, x.grad
a = Value(2.0); b = a * a; c = b * b     # c = a^4, dc/da = 4a^3 = 32 ; b is used twice
c.backward(); assert abs(a.grad - 32.0) < 1e-12, a.grad
# diamond: z = (x+1)*(x+2) -> 2x+3
x = Value(1.5); z = (x + 1) * (x + 2); z.backward(); assert abs(x.grad - 6.0) < 1e-12
# a second backward() without zeroing accumulates (documented behaviour); zeroing restores it
x = Value(2.0); y = x * 3.0
y.backward(); y.backward(); assert x.grad == 6.0
# constants on either side and operator coverage
x = Value(2.0)
assert (1 - x).data == -1.0 and (6 / x).data == 3.0 and (-x).data == -2.0
q = 6 / x; q.backward(); assert abs(x.grad - (-6 / 4)) < 1e-12, x.grad
v = Value(-1.0); w = v.relu(); w.backward(); assert v.grad == 0.0 and w.data == 0.0
v = Value(0.0); w = v.relu(); w.backward(); assert v.grad == 0.0   # documented convention at the kink
v = Value(2.0); w = v.relu(); w.backward(); assert v.grad == 1.0

# ---- 3. deep graph must not hit the recursion limit ----
x = Value(1.0001); h = x
for _ in range(5000):
    h = h * 1.0001
h.backward()
assert abs(x.grad - 1.0001 ** 5000) / 1.0001 ** 5000 < 1e-9, x.grad

# ---- 4. optimizers vs independent reference implementations ----
def ref_momentum(grad_fn, p, lr, mu, steps):
    v = [0.0] * len(p); out = []
    for _ in range(steps):
        g = grad_fn(p)
        v = [mu * vi + gi for vi, gi in zip(v, g)]
        p = [pi - lr * vi for pi, vi in zip(p, v)]
        out.append(p)
    return out
def ref_adam(grad_fn, p, lr, b1, b2, eps, steps):
    m = [0.0] * len(p); s = [0.0] * len(p); out = []
    for t in range(1, steps + 1):
        g = grad_fn(p)
        m = [b1 * mi + (1 - b1) * gi for mi, gi in zip(m, g)]
        s = [b2 * si + (1 - b2) * gi * gi for si, gi in zip(s, g)]
        p = [pi - lr * (mi / (1 - b1 ** t)) / (math.sqrt(si / (1 - b2 ** t)) + eps)
             for pi, mi, si in zip(p, m, s)]
        out.append(p)
    return out
qg = lambda p: [p[0], 25.0 * p[1]]
for lr, mu in [(0.01, 0.9), (0.02, 0.5)]:
    opt = Momentum(lr, mu); p = [1.0, 1.0]; got = []
    for _ in range(40):
        p = opt.step(p, qg(p)); got.append(p)
    ref = ref_momentum(qg, [1.0, 1.0], lr, mu, 40)
    assert all(abs(a - b) < 1e-12 for u, w in zip(got, ref) for a, b in zip(u, w))
opt = Adam(0.1); p = [1.0, 1.0]; got = []
for _ in range(60):
    p = opt.step(p, qg(p)); got.append(p)
ref = ref_adam(qg, [1.0, 1.0], 0.1, 0.9, 0.999, 1e-8, 60)
assert all(abs(a - b) < 1e-12 for u, w in zip(got, ref) for a, b in zip(u, w))
assert sgd_step([1.0, 2.0], [0.5, -1.0], 0.1) == [0.95, 2.1]

# Adam's first step has size ~lr whatever the gradient scale (bias correction), in both directions
for g in (1e-3, 1.0, 1e3, -1e3):
    new = Adam(0.01).step([0.0], [g])[0]
    assert abs(new - (-0.01 * (1 if g > 0 else -1))) < 1e-6, (g, new)
# and an optimizer must not mutate the caller's list
p = [1.0, 1.0]; Adam(0.1).step(p, [1.0, 1.0]); assert p == [1.0, 1.0]

# ---- 5. the lesson's experiments: stability bound and ranking, and printed numbers match ----
demo_lines = ns['demo']()
for line in demo_lines:
    assert line in src, "lesson's printed output out of date: " + line
res = ns['RESULTS']
assert res['sgd_lr0.07'] < 1e-2 and res['sgd_lr0.09'] > 1e6          # lr past 2/L = 0.08 diverges
assert res['momentum'] < res['sgd_lr0.07'] * 1e-6                    # tuned momentum beats tuned SGD by orders of magnitude
assert res['momentum_untuned'] > res['sgd_lr0.07']                    # but mu=0.9 with a small lr does not
assert res['adam'] < 1e-3
assert abs(res['fit_w'] - 2.0) < 1e-2 and abs(res['fit_b'] - 1.0) < 1e-2   # engine trains a real model
print("ai28 code checks passed")
