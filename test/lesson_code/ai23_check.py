"""Runs the python code blocks from data/new_lessons/ai23-vllm-serving.md against reference checks,
and asserts every worked number the lesson prose states."""
import re, sys, random, math
from collections import Counter
src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
ns = {}
for b in blocks:
    exec(b, ns)
kv_cache_bytes, reserved_vs_used = ns['kv_cache_bytes'], ns['reserved_vs_used']
BlockAllocator, Sequence = ns['BlockAllocator'], ns['Sequence']
attention_naive, attention_tiled = ns['attention_naive'], ns['attention_tiled']
sample, residual, speculative_step = ns['sample'], ns['residual'], ns['speculative_step']
acceptance_rate, expected_tokens, walltime_factor = ns['acceptance_rate'], ns['expected_tokens'], ns['walltime_factor']
random.seed(23)

# --- KV cache size: the vLLM paper's OPT-13B numbers, and the formula against a per-element count
assert kv_cache_bytes(1, 40, 5120) == 819_200 and kv_cache_bytes(1, 40, 5120) / 1024 == 800
assert kv_cache_bytes(2048, 40, 5120) == 1_677_721_600
assert 12 * 10**9 // kv_cache_bytes(1, 40, 5120) == 14_648
assert kv_cache_bytes(1, 32, 8 * 128) == 131_072            # drill 1
for _ in range(200):
    # independent count: build the cache as explicit nested lists of K and V entries and count the bytes
    t, L, heads, hd, bpv = random.randint(0, 6), random.randint(1, 4), random.randint(1, 4), random.randint(1, 8), random.choice([1, 2, 4])
    cache = [{kind: [[[0] * hd for _ in range(heads)] for _ in range(t)] for kind in ('k', 'v')} for _ in range(L)]
    n_values = sum(len(vec) for layer in cache for kind in layer.values() for tok in kind for vec in tok)
    assert kv_cache_bytes(t, L, heads * hd, bpv) == n_values * bpv

# --- waste comparison: the lesson's illustrative run, and paged waste < one block per sequence
assert reserved_vs_used([120, 900, 300, 2048], 2048, 16) == (3368, 8192, 3392)
assert round(3368 / 8192, 2) == 0.41 and round(3368 / 3392, 2) == 0.99
for _ in range(300):
    bs = random.choice([1, 8, 16, 32]); mx = random.randint(1, 600)
    lens = [random.randint(1, mx) for _ in range(random.randint(1, 10))]
    used, cont, paged = reserved_vs_used(lens, mx, bs)
    assert used == sum(lens) and cont == len(lens) * mx
    assert paged == sum(math.ceil(n / bs) * bs for n in lens)
    assert used <= paged < used + bs * len(lens) and paged <= cont + bs * len(lens)

# --- paged allocator: random appends/forks/frees against plain python lists
def check_invariants(alloc, seqs, n_blocks):
    refs = Counter(b for s in seqs for b in s.table)
    for b in range(n_blocks):
        assert alloc.ref[b] == refs.get(b, 0), (b, alloc.ref[b], refs.get(b, 0))
    assert sorted(alloc.free) == [b for b in range(n_blocks) if refs.get(b, 0) == 0]
    for s in seqs:
        assert len(s.table) == math.ceil(s.length / alloc.block_size)
        assert len(s.table) * alloc.block_size - s.length < alloc.block_size   # waste: at most the tail
        for i, b in enumerate(s.table[:-1]):
            assert len(alloc.data[b]) == alloc.block_size                    # only the tail is partial

for trial in range(300):
    n_blocks, bs = random.randint(1, 24), random.choice([1, 2, 4, 16])
    alloc = BlockAllocator(n_blocks, bs)
    seqs, ref = [], []
    tok = 0
    for step in range(200):
        op = random.random()
        if op < 0.6 or not seqs:
            if not seqs or random.random() < 0.15:
                seqs.append(Sequence(alloc)); ref.append([])
            i = random.randrange(len(seqs))
            before = (list(seqs[i].table), seqs[i].length, list(alloc.free))
            try:
                seqs[i].append(tok); ref[i].append(tok)
            except MemoryError:
                # failed allocation must leave the sequence and the pool unchanged
                assert (seqs[i].table, seqs[i].length, alloc.free) == before
                assert not alloc.free
            tok += 1
        elif op < 0.8:
            i = random.randrange(len(seqs))
            seqs.append(seqs[i].fork()); ref.append(list(ref[i]))
        else:
            i = random.randrange(len(seqs))
            seqs[i].free(); seqs.pop(i); ref.pop(i)
        for s, r in zip(seqs, ref):
            assert s.tokens() == r and s.length == len(r)
        check_invariants(alloc, seqs, n_blocks)

# fork sharing: 40-token prefix, block 16 -> 3 shared blocks; token 41 copies only the tail (drill 4)
alloc = BlockAllocator(10, 16)
a = Sequence(alloc)
for t in range(40):
    a.append(t)
b = a.fork()
assert a.table == b.table and len(a.table) == 3 and all(alloc.ref[x] == 2 for x in a.table)
b.append(999)
assert a.table[:2] == b.table[:2] and a.table[2] != b.table[2]
assert a.tokens() == list(range(40)) and b.tokens() == list(range(40)) + [999]
assert len(alloc.free) == 10 - 4

# --- online softmax attention vs an independent reference, including huge scores
def ref_attention(q, keys, values):
    s = [sum(x * y for x, y in zip(q, k)) for k in keys]
    mx = max(s)
    e = [math.exp(v - mx) for v in s]
    z = math.fsum(e)
    return [math.fsum(e[i] * values[i][j] for i in range(len(keys))) / z for j in range(len(values[0]))]
for _ in range(300):
    d, dv, n = random.randint(1, 6), random.randint(1, 5), random.randint(1, 40)
    scale = random.choice([0.1, 1, 30, 300])
    q = [random.uniform(-1, 1) * scale for _ in range(d)]
    K = [[random.uniform(-1, 1) for _ in range(d)] for _ in range(n)]
    V = [[random.uniform(-5, 5) for _ in range(dv)] for _ in range(n)]
    want = ref_attention(q, K, V)
    for out in [attention_naive(q, K, V)] + [attention_tiled(q, K, V, t) for t in (1, 3, 7, n, n + 5)]:
        assert all(abs(x - y) <= 1e-9 * (1 + abs(y)) for x, y in zip(out, want)), (out, want)

# --- speculative sampling
def rand_dist(vocab):
    w = [random.random() ** 3 for _ in vocab]
    z = sum(w)
    return {t: x / z for t, x in zip(vocab, w)}
vocab = list('abcde')
# exact: P(emit y) = q(y) min(1, p/q) + (1 - alpha) residual(y) must equal p(y)
for _ in range(500):
    p, q = rand_dist(vocab), rand_dist(vocab)
    alpha = acceptance_rate(p, q)
    assert abs(alpha - sum(min(p[t], q[t]) for t in vocab)) < 1e-12
    if alpha > 1 - 1e-9:
        continue
    r = residual(p, q)
    assert abs(sum(r.values()) - 1) < 1e-9 and all(v >= 0 for v in r.values())
    for y in vocab:
        emitted = q[y] * min(1.0, p[y] / q[y]) + (1 - alpha) * r[y]
        assert abs(emitted - p[y]) < 1e-9, (y, emitted, p[y])
# sample() is exact on a grid of uniforms
d = {'x': 0.25, 'y': 0.5, 'z': 0.25}
grid = Counter(sample(d, lambda u=u: (u + 0.5) / 1000) for u in range(1000))
assert grid == Counter({'x': 250, 'y': 500, 'z': 250}), grid

# Monte Carlo of the whole step: emitted tokens at each position follow p; mean length matches the formula
P = {'the': 0.5, 'a': 0.3, 'cat': 0.2}
Q = {'the': 0.7, 'a': 0.1, 'cat': 0.2}
gamma = 4
rng = random.Random(7)
pos = [Counter() for _ in range(gamma + 1)]
total_len, N = 0, 120_000
for _ in range(N):
    drafts = [sample(Q, rng.random) for _ in range(gamma)]
    out = speculative_step([P] * (gamma + 1), [Q] * gamma, drafts, rng.random)
    assert 1 <= len(out) <= gamma + 1
    total_len += len(out)
    for i, t in enumerate(out):
        pos[i][t] += 1
for i in range(2):
    n_i = sum(pos[i].values())
    for t in P:
        assert abs(pos[i][t] / n_i - P[t]) < 0.01, (i, t, pos[i][t] / n_i)
assert abs(total_len / N - expected_tokens(0.8, gamma)) < 0.03, total_len / N

# the lesson's worked numbers
assert abs(acceptance_rate(P, Q) - 0.8) < 1e-12
assert round(expected_tokens(0.8, 4), 2) == 3.36 and round(walltime_factor(0.8, 4, 0.05), 2) == 2.80
assert round(expected_tokens(0.8, 8), 2) == 4.33 and round(walltime_factor(0.8, 8, 0.05), 2) == 3.09
# expected_tokens equals the direct sum of P(at least k accepted)
for alpha in (0.1, 0.5, 0.8, 0.95):
    for g in range(0, 10):
        assert abs(expected_tokens(alpha, g) - sum(alpha ** k for k in range(g + 1))) < 1e-12
print("drill 8:", round(walltime_factor(0.6, 3, 0.1), 3))
print("ai23 code checks passed")
