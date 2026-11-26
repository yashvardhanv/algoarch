"""Runs the python blocks from data/new_lessons/ai31-pretraining-scaling-laws.md against brute-force references."""
import re, sys, math, random
src = open(sys.argv[1], encoding='utf-8').read()
ns = {}
for b in re.findall(r"```python\n(.*?)```", src, re.S):
    exec(b, ns)
g = lambda n: ns[n]
words, shingles, jaccard = g('words'), g('shingles'), g('jaccard')
make_params, minhash, estimate_jaccard = g('make_params'), g('minhash'), g('estimate_jaccard')
candidate_pairs, dedup, ngram_set, contaminated = g('candidate_pairs'), g('dedup'), g('ngram_set'), g('contaminated')
fit_power_law, fit_with_floor = g('fit_power_law'), g('fit_with_floor')
rnd = random.Random(31)

# ---- shingles and Jaccard against brute force ----
assert words("Hello, World! It's 3 o'clock") == ["hello", "world", "it's", "3", "o'clock"]
for _ in range(100):
    w = [rnd.choice("abcde") for _ in range(rnd.randint(0, 12))]
    text = " ".join(w); k = rnd.randint(1, 4)
    want = {" ".join(w[i:i + k]) for i in range(len(w) - k + 1)} if len(w) >= k else ({" ".join(w)} if w else set())
    assert shingles(text, k) == want
assert jaccard({1, 2, 3}, {2, 3, 4}) == 0.5 and jaccard(set(), set()) == 1.0 and jaccard({1}, set()) == 0.0

# ---- MinHash estimates Jaccard without bias; the LSH S-curve matches 1-(1-s^r)^b ----
def pair(inter, only):
    common = {f"c{i}" for i in range(inter)}
    return common | {f"a{i}" for i in range(only)}, common | {f"b{i}" for i in range(only)}
for inter, only, s in ((30, 15, 0.5), (42, 9, 0.7), (48, 6, 0.8)):
    A, Bs = pair(inter, only); assert abs(jaccard(A, Bs) - s) < 1e-12
    ests = []
    for seed in range(60):
        p = make_params(128, seed)
        ests.append(estimate_jaccard(minhash(A, p), minhash(Bs, p)))
    mean = sum(ests) / len(ests)
    assert abs(mean - s) < 0.02, (s, mean)
    assert estimate_jaccard(minhash(A, make_params(128, 0)), minhash(A, make_params(128, 0))) == 1.0
    hits = 0
    for seed in range(200):
        p = make_params(128, 1000 + seed)
        sigs = [minhash(A, p), minhash(Bs, p)]
        hits += (0, 1) in candidate_pairs(sigs, 16, 8)
    want = 1 - (1 - s ** 8) ** 16
    assert abs(hits / 200 - want) < 0.09, (s, hits / 200, want)
# identical signatures collide in every band; disjoint sets almost never
sig_a = minhash({"x y z"}, make_params(32, 1))
assert candidate_pairs([sig_a, sig_a], 4, 8) == {(0, 1)}
assert candidate_pairs([minhash({"p"}, make_params(32, 1)), minhash({"q"}, make_params(32, 1))], 4, 8) == set()

# ---- dedup against exact all-pairs clustering ----
def brute_keep(docs, k, t):
    shs = [shingles(d, k) for d in docs]
    parent = list(range(len(docs)))
    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x
    for i in range(len(docs)):
        for j in range(i + 1, len(docs)):
            if jaccard(shs[i], shs[j]) >= t:
                ri, rj = find(i), find(j); parent[max(ri, rj)] = min(ri, rj)
    return [i for i in range(len(docs)) if find(i) == i]
docs, truth = g('planted_corpus')()
exact = brute_keep(docs, 3, 0.7)
assert len(exact) == 150, len(exact)                                  # the planted structure is what the brute force sees
keep = dedup(docs)
assert set(exact) <= set(keep) and len(keep) - len(exact) <= 3        # LSH may miss a pair, never invent one
assert all(i in keep for i in range(150))                             # originals come first and survive
for j in range(150, len(docs)):                                       # byte-identical copies always collide
    if docs[j] in docs[:150]:
        assert j not in keep
# verification is what protects you from false candidates: use a permissive LSH (1 row per band => many false pairs)
perm_ok = dedup(docs, bands=128, rows=1, verify=True)
perm_bad = dedup(docs, bands=128, rows=1, verify=False)
assert set(exact) <= set(perm_ok) and len(perm_ok) <= len(exact) + 3
assert len(perm_bad) < len(exact) - 20                                # without it, unrelated documents get merged
assert dedup([]) == [] and dedup(["a b"]) == [0] and dedup(["a b", "a b"]) == [0]
assert dedup(["one two three four five", "completely different words entirely here"]) == [0, 1]

# ---- contamination: shared n-word windows against a brute-force substring search ----
for _ in range(200):
    tr = [" ".join(rnd.choice("abc") for _ in range(rnd.randint(0, 14))) for _ in range(rnd.randint(1, 4))]
    ev = [" ".join(rnd.choice("abc") for _ in range(rnd.randint(0, 14))) for _ in range(rnd.randint(1, 5))]
    n = rnd.randint(1, 5)
    def has(e):
        et = e.split()
        return any(et[i:i + n] == t.split()[j:j + n] for t in tr for i in range(len(et) - n + 1) for j in range(len(t.split()) - n + 1))
    assert contaminated(tr, ev, n) == [i for i, e in enumerate(ev) if has(e)]
assert contaminated(["the cat sat on the mat today"], ["a cat sat on the mat"], 5) == [0]
assert contaminated(["the cat sat on the mat today"], ["a cat sat on a mat"], 5) == []

# ---- power-law fitting ----
xs = [10 ** i for i in range(2, 9)]
al, c = fit_power_law(xs, [7.0 * x ** -0.3 for x in xs])
assert abs(al - 0.3) < 1e-9 and abs(c - 7.0) < 1e-6
ys = [1.7 + 400 / x ** 0.34 for x in [1e6 * 4 ** i for i in range(8)]]
Ns = [1e6 * 4 ** i for i in range(8)]
naive = fit_power_law(Ns, ys)[0]
E0, a0, _ = fit_with_floor(Ns, ys)
assert naive < 0.5 * 0.34, naive                                       # ignoring the floor understates the exponent badly
assert abs(E0 - 1.7) < 0.02 and abs(a0 - 0.34) < 0.005, (E0, a0)

# ---- compute-optimal split ----
loss, optimal_split, grid_optimum = g('loss'), g('optimal_split'), g('grid_optimum')
assert abs(loss(70e9, 1.4e12) - (1.69 + 406.4 / (70e9) ** 0.34 + 410.7 / (1.4e12) ** 0.28)) < 1e-12
for C in (1e19, 5.76e23, 1e26):
    N, D = optimal_split(C)
    assert abs(6 * N * D / C - 1) < 1e-9
    gN, gD = grid_optimum(C)
    assert abs(gN / N - 1) < 0.01 and abs(gD / D - 1) < 0.01, (C, N, gN)
    for f in (0.9, 1.1):                                               # nudging the split either way hurts
        assert loss(N * f, C / (6 * N * f)) > loss(N, D)
n1, _ = optimal_split(1e21); n2, _ = optimal_split(2e21)
assert abs(n2 / n1 - 2 ** (0.28 / 0.62)) < 1e-9
# symmetric exponents (alpha = beta, A = B) mean "grow N and D equally"
old = {k: ns[k] for k in ("ALPHA", "BETA", "A", "B")}
ns["ALPHA"] = ns["BETA"] = 0.3; ns["A"] = ns["B"] = 400.0
na, da = optimal_split(1e21); nb, db = optimal_split(4e21)
assert abs(nb / na - 2) < 1e-9 and abs(db / da - 2) < 1e-9 and abs(na - da) / na < 1e-9
ns.update(old)

# ---- the lesson's printed numbers ----
for line in g('demo')():
    assert line in src, "lesson's printed output out of date: " + line
R = g('RESULTS')
assert R['wrong'] == 0 and R['caught'] >= R['planted'] - 2
assert abs(R['opt'][0][0] / R['opt'][1][0] - 1) < 0.01
assert R['gc'][1] < R['gc'][0]
print("ai31 code checks passed")
