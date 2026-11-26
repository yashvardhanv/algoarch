"""Runs the python blocks from data/new_lessons/ai29-language-model-from-scratch.md against reference checks."""
import re, sys, math, random, itertools
src = open(sys.argv[1], encoding='utf-8').read()
ns = {}
for b in re.findall(r"```python\n(.*?)```", src, re.S):
    exec(b, ns)
g = lambda n: ns[n]
V, VOCAB, IDX, START = g('V'), g('VOCAB'), g('IDX'), g('START')
make_words, split_words, pairs = g('make_words'), g('split_words'), g('pairs')
fit_counts, count_prob, mean_nll, sample_word = g('fit_counts'), g('count_prob'), g('mean_nll'), g('sample_word')
LogLinear, loss_and_grad, train, softmax = g('LogLinear'), g('loss_and_grad'), g('train'), g('softmax')
generator_nll = g('generator_nll')
random.seed(29)

# ---- corpus and split ----
ws = make_words(500, 3)
assert ws == make_words(500, 3) and ws != make_words(500, 4)
assert all(2 <= len(w) // 2 <= 4 and len(w) % 2 == 0 for w in ws)
for w in ws:                                   # every vowel from one group, consonant/vowel alternating
    cons, vows = w[0::2], w[1::2]
    assert all(c in "ptkmnl" for c in cons) and (all(v in "ei" for v in vows) or all(v in "aou" for v in vows)), w
dup = ws + ws[:50]
tr, va = split_words(dup)
assert not set(tr) & set(va) and set(tr) | set(va) == set(ws) and len(tr) + len(va) == len(set(ws))
assert len(va) == len(set(ws)) - int(len(set(ws)) * 0.8)

# ---- pairs and counts against a brute-force scan ----
def brute_counts(words, ctx):
    out = {}
    for w in words:
        s = "." * ctx + w + "."
        for i in range(len(w) + 1):
            key = (s[i:i + ctx], s[i + ctx])
            out[key] = out.get(key, 0) + 1
    return out
for ctx in range(4):
    c = fit_counts(tr, ctx); b = brute_counts(tr, ctx)
    assert {(k, ch): n for k, row in c.items() for ch, n in row.items()} == b
    assert sum(b.values()) == sum(len(w) + 1 for w in tr) == len(list(pairs(tr, ctx)))
    for alpha in (0.0, 0.1, 1.0):
        for k in list(c)[:20]:
            tot = sum(n for (kk, ch), n in b.items() if kk == k)
            for ch in VOCAB:
                want = (b.get((k, ch), 0) + alpha) / (tot + alpha * V)
                assert abs(count_prob(c, k, ch, alpha) - want) < 1e-12
            assert abs(sum(count_prob(c, k, ch, 0.1) for ch in VOCAB) - 1) < 1e-12
# unseen context: alpha=0 gives probability 0 (so NLL is infinite); smoothing gives uniform
c3 = fit_counts(tr[:10], 3)
assert count_prob(c3, "zzz", "a", 0.0) == 0.0 and abs(count_prob(c3, "zzz", "a", 0.5) - 1 / V) < 1e-12
assert mean_nll(lambda a, b: count_prob(c3, a, b, 0.0), va, 3) == math.inf

# ---- uniform baseline: ln V, perplexity V ----
uni = mean_nll(lambda a, b: 1 / V, va, 1)
assert abs(uni - math.log(V)) < 1e-12 and abs(math.exp(uni) - V) < 1e-9
m0 = LogLinear(2)
assert abs(loss_and_grad(m0, list(pairs(tr, 2)))[0] - math.log(V)) < 1e-12      # zero weights = uniform

# ---- the generator's own loss is the true floor ----
total = 0.0
for k in (2, 3):
    for grp in ("ei", "aou"):
        syl = [c + v for c in "ptkmnl" for v in grp]
        for combo in itertools.product(syl, repeat=k):
            w = "".join(combo)
            total += math.exp(-generator_nll([w]) * (len(w) + 1))
assert abs(total - 4 * 0.5 / 3) < 1e-9, total                                    # probabilities add up
big = make_words(30000, 9); btr, bva = big[:25000], big[25000:]     # raw draws: the floor assumes the generator's own distribution, so no dedup here
cc = fit_counts(btr, 3)
fl = generator_nll(bva)
est = mean_nll(lambda a, b: count_prob(cc, a, b, 0.01), bva, 3)
assert 0.0 < est - fl < 0.1, (est, fl)     # a 3-char context cannot count syllables, so it stays a little above the floor

# ---- gradient vs finite differences, random weights, all positions ----
for ctx in (1, 2):
    m = LogLinear(ctx)
    for j in range(ctx):
        for r in range(V):
            for v in range(V):
                m.W[j][r][v] = random.uniform(-1, 1)
    batch = random.sample(list(pairs(tr, ctx)), 40)
    _, grad = loss_and_grad(m, batch)
    for _ in range(25):
        j, r, v = random.randrange(ctx), random.randrange(V), random.randrange(V)
        old = m.W[j][r][v]; h = 1e-6
        m.W[j][r][v] = old + h; up = loss_and_grad(m, batch)[0]
        m.W[j][r][v] = old - h; dn = loss_and_grad(m, batch)[0]
        m.W[j][r][v] = old
        assert abs((up - dn) / (2 * h) - grad[j][r][v]) < 1e-7, (ctx, j, r, v)
    assert abs(sum(m.prob(batch[0][0], ch) for ch in VOCAB) - 1) < 1e-12

# ---- counting IS the optimum of the log-linear bigram: gradient vanishes at log-counts ----
cnt = fit_counts(tr, 1); mb = LogLinear(1)
for k, row in cnt.items():
    tot = sum(row.values())
    for v, ch in enumerate(VOCAB):
        mb.W[0][IDX[k]][v] = math.log(row[ch] / tot) if ch in row else -60.0
l, gr = loss_and_grad(mb, list(pairs(tr, 1)))
assert max(abs(x) for a in gr for b in a for x in b) < 1e-9
assert abs(l - mean_nll(lambda a, b: count_prob(cnt, a, b, 0.0), tr, 1)) < 1e-9

# ---- sampling follows the model ----
rnd = random.Random(1)
c1 = fit_counts(tr, 1)
first = {ch: 0 for ch in VOCAB}
words = [sample_word(lambda a, b: count_prob(c1, a, b, 0.1), 1, rnd) for _ in range(20000)]
for w in words:
    assert all(ch in VOCAB and ch != START for ch in w) and len(w) <= 12
    if w: first[w[0]] += 1
nonempty = sum(first.values())
for ch in VOCAB:
    p = count_prob(c1, START, ch, 0.1)
    if ch != START:
        assert abs(first[ch] / len(words) - p) < 0.02, (ch, first[ch] / len(words), p)

# ---- the lesson's experiments ----
lines = g('demo')()
for line in lines:
    assert line in src, "lesson's printed output out of date: " + line
R = g('RESULTS')
fl = R['floor']
for n in (632, 40):
    trn = [R[(n, c)][0] for c in range(4)]; val = [R[(n, c)][1] for c in range(4)]
    assert trn == sorted(trn, reverse=True), trn                 # more context always fits train better
    assert min(val) > fl
assert min(range(4), key=lambda c: R[(632, c)][1]) == 2           # val picks context 2, not 3
assert R[(40, 1)][1] < R[(40, 2)][1] < R[(40, 3)][1]              # tiny data: val gets worse as context grows
assert R[(40, 3)][1] - R[(40, 3)][0] > 1.0                        # a gap of over a nat between train and val
hist = R['curve']
assert abs(hist[0][1] - hist[0][2]) < 1e-9 and abs(hist[0][1] - math.log(V)) < 1e-9
assert all(hist[i][1] > hist[i + 1][1] for i in range(len(hist) - 1))
sw = R['sweep']
assert sw[0.01] > 2.3 and sw[100.0] > math.log(V) and min(sw, key=sw.get) in (1.0, 10.0)
assert abs(R['bigram'][0] - R['bigram'][1]) < 0.05                      # close on validation (an observation, not a theorem)
assert R['bigram_train'][0] >= R['bigram_train'][1] - 1e-9                # counting minimises TRAINING loss: this one is a theorem
assert R[("mix", 1)] > 0.3 and R[("mix", 2)] < 0.1
print("ai29 code checks passed")
