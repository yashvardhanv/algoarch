"""Runs the python blocks from data/new_lessons/ai30-attention-transformer-block.md against naive references."""
import re, sys, math, random
src = open(sys.argv[1], encoding='utf-8').read()
ns = {}
for b in re.findall(r"```python\n(.*?)```", src, re.S):
    exec(b, ns)
g = lambda n: ns[n]
attention, multi_head, block, layer_norm = g('attention'), g('multi_head'), g('block'), g('layer_norm')
causal_mask, positional_encoding, init_params = g('causal_mask'), g('positional_encoding'), g('init_params')
matmul, softmax, add, split_heads, feed_forward = g('matmul'), g('softmax'), g('add'), g('split_heads'), g('feed_forward')
rnd = random.Random(30)
mx = lambda A, B: max(abs(a - b) for ra, rb in zip(A, B) for a, b in zip(ra, rb))
rm = lambda n, d: [[rnd.gauss(0, 1) for _ in range(d)] for _ in range(n)]

# ---- naive per-query reference (explicit loops, its own softmax) ----
def naive_attention(Q, K, V, causal):
    out, W = [], []
    for i, q in enumerate(Q):
        dk = len(q)
        keys = range(i + 1) if causal else range(len(K))
        sc = {j: sum(q[t] * K[j][t] for t in range(dk)) / math.sqrt(dk) for j in keys}
        z = sum(math.exp(s) for s in sc.values())
        w = [math.exp(sc[j]) / z if j in sc else 0.0 for j in range(len(K))]
        W.append(w)
        out.append([sum(w[j] * V[j][t] for j in range(len(V))) for t in range(len(V[0]))])
    return out, W

for trial in range(200):
    n, dk, dv = rnd.randint(1, 7), rnd.randint(1, 6), rnd.randint(1, 5)
    causal = trial % 2 == 0
    n_k = n if causal else rnd.randint(1, 7)
    Q, K, V = rm(n, dk), rm(n_k, dk), rm(n_k, dv)
    for M in (K, Q):
        for r in M:
            r[:] = [x * rnd.choice([1, 5]) for x in r]                # include large scores
    mask = causal_mask(n) if causal else None
    out, W = attention(Q, K, V, mask)
    nout, nW = naive_attention(Q, K, V, causal)
    assert mx(out, nout) < 1e-9 and mx(W, nW) < 1e-9, trial
    assert all(abs(sum(r) - 1) < 1e-9 for r in W)
    if causal:
        assert all(W[i][j] == 0.0 for i in range(n) for j in range(i + 1, n))
assert attention([[1.0, 0.0]], [[9000.0, 0.0], [0.0, 0.0]], [[1.0], [2.0]])[0] == [[1.0]]   # huge scores: no overflow

# ---- scaling is by sqrt(d_k) ----
_, w = attention([[2.0, 0.0, 0.0, 0.0]], [[1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0]], [[0.0], [0.0]])
assert abs(w[0][0] - softmax([2.0 / 2.0, 0.0])[0]) < 1e-12            # dot 2, sqrt(4) = 2

# ---- multi-head equals per-head attention on sliced weights, concatenated, then Wo ----
for trial in range(40):
    h = rnd.choice([1, 2, 4]); d = h * rnd.randint(1, 3); n = rnd.randint(1, 6)
    X = rm(n, d); Wq, Wk, Wv, Wo = (rm(d, d) for _ in range(4))
    dk = d // h; causal = trial % 2 == 0
    heads = []
    for i in range(h):
        sl = lambda Wm: [row[i * dk:(i + 1) * dk] for row in Wm]
        heads.append(naive_attention(matmul(X, sl(Wq)), matmul(X, sl(Wk)), matmul(X, sl(Wv)), causal)[0])
    ref = matmul([[x for hd in heads for x in hd[i]] for i in range(n)], Wo)
    got = multi_head(X, Wq, Wk, Wv, Wo, h, causal_mask(n) if causal else None)
    assert mx(got, ref) < 1e-9, trial
    assert len(split_heads(X, h)) == h and len(split_heads(X, h)[0][0]) == dk

# ---- positional encoding: the paper's formula, and "a fixed offset is a fixed rotation" ----
pe = positional_encoding(30, 16)
for pos in range(30):
    for i in range(8):
        ang = pos / 10000 ** (2 * i / 16)
        assert abs(pe[pos][2 * i] - math.sin(ang)) < 1e-12 and abs(pe[pos][2 * i + 1] - math.cos(ang)) < 1e-12
for k in (1, 5, 11):
    for pos in range(10):
        for i in range(8):
            a = k / 10000 ** (2 * i / 16)
            s, c = pe[pos][2 * i], pe[pos][2 * i + 1]
            assert abs(pe[pos + k][2 * i] - (s * math.cos(a) + c * math.sin(a))) < 1e-9
            assert abs(pe[pos + k][2 * i + 1] - (c * math.cos(a) - s * math.sin(a))) < 1e-9
assert positional_encoding(3, 5)[2][4] == math.sin(2 / 10000 ** (4 / 5))          # odd d: last slot is a sine

# ---- layer norm: per token, scale-invariant, gain and bias applied after ----
X = rm(6, 12)
Y = layer_norm(X, [1.0] * 12, [0.0] * 12, eps=1e-12)
for r in Y:
    assert abs(sum(r) / 12) < 1e-9 and abs(sum(v * v for v in r) / 12 - 1) < 1e-6
assert mx(layer_norm([[7 * v for v in r] for r in X], [1.0] * 12, [0.0] * 12, 1e-12), Y) < 1e-6
assert mx(layer_norm(X, [2.0] * 12, [3.0] * 12, eps=1e-12), [[2 * v + 3 for v in r] for r in Y]) < 1e-6
# a row of identical values has zero variance: eps keeps it finite
assert all(abs(v) < 1e-6 for v in layer_norm([[4.0] * 5], [1.0] * 5, [0.0] * 5)[0])

# ---- block: residual wiring, shapes, position-wise parts ----
d, h, dff = 8, 2, 16
P = init_params(d, dff, rnd)
Xs = rm(5, d)
assert len(block(Xs, P, h)) == 5 and all(len(r) == d for r in block(Xs, P, h))
Z0 = dict(P)
Z0["Wo"] = [[0.0] * d for _ in range(d)]; Z0["W2"] = [[0.0] * d for _ in range(dff)]
assert mx(block(Xs, Z0, h), layer_norm(layer_norm(Xs, P["g1"], P["b1"]), P["g2"], P["b2"])) < 1e-9   # sublayers off -> only the residual path
assert feed_forward([[-1.0]], [[1.0]], [0.0], [[1.0]], [0.0]) == [[0.0]] and feed_forward([[2.0]], [[1.0]], [0.0], [[3.0]], [1.0]) == [[7.0]]   # ReLU in the middle
f_all = feed_forward(Xs, P["W1"], P["c1"], P["W2"], P["c2"])
for i in range(5):                                                               # the feed-forward treats each token alone
    assert mx([f_all[i]], feed_forward([Xs[i]], P["W1"], P["c1"], P["W2"], P["c2"])) < 1e-12

# ---- causal masking leaks nothing from the future, through the WHOLE block ----
for trial in range(30):
    n = rnd.randint(2, 7); X = rm(n, d); t = rnd.randrange(1, n)
    X2 = [r[:] for r in X]; X2[t] = rm(1, d)[0]
    o1, o2 = block(X, P, h, causal_mask(n)), block(X2, P, h, causal_mask(n))
    assert mx(o1[:t], o2[:t]) == 0.0, "a future token changed an earlier output"
    assert mx(o1[t:t + 1], o2[t:t + 1]) > 1e-6                                   # the changed token itself moves
    if t + 1 < n:
        assert mx(o1[t + 1:], o2[t + 1:]) > 1e-9                                 # later positions DO see it
    u1, u2 = block(X, P, h), block(X2, P, h)
    assert mx(u1[:t], u2[:t]) > 1e-9                                             # control: without the mask there is a leak
# once positions are added, reordering the past changes a later output
n = 5; X = rm(n, d); pe = positional_encoding(n, d)
a = block(add(X, pe), P, h, causal_mask(n))[-1]
b = block(add([X[1], X[0]] + X[2:], pe), P, h, causal_mask(n))[-1]
assert mx([a], [b]) > 1e-6

# ---- the lesson's printed experiments, and the parameter formula ----
for line in g('demo')():
    assert line in src, "lesson's printed output out of date: " + line
assert g('n_params')(init_params(512, 2048, random.Random(0))) == 4 * 512 * 512 + 2 * 512 * 2048 + 2048 + 512 + 4 * 512
print("ai30 code checks passed")
