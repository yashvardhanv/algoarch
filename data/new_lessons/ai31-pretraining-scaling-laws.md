# Lesson 31 — Pretraining Data and Scaling Laws

> **Priority:** ★★★☆☆ — a depth round for model-training and research-engineering loops: "what goes into the pretraining set?" and "given a compute budget, how big a model?"
>
> **Study time:** 60 minutes. **Do this after:** Lessons 29 and 30 (a small language model; attention and the Transformer block).
>
> **Level:** extended.

Two decisions shape a pretrained model before anyone writes a training loop: which text it reads, and how much compute is split between model size and amount of text. The first is a data-engineering problem (duplicates, overlap with the test set, mixtures); the second has an empirical answer that changed once and is still argued about. This lesson builds the pieces you can implement in an interview (near-duplicate detection with MinHash, a contamination check, a power-law fit and the compute-optimal allocation) and is careful to say which claims come from the two papers it read and which are the lesson's own arithmetic on synthetic data.

---

## 1. Mental Model

> **Pretraining spends a compute budget on two things: parameters `N` and training tokens `D`. Loss falls as a power law in each, with a floor. Where you put a fixed budget (roughly `6 N D` FLOPs) decides the loss you reach, and the data you train on decides what the loss measures: duplicated or leaked text makes the number look better than the model is.**

What follows from it:

- **A power law is a straight line on log-log axes, until the floor.** Loss that approaches a nonzero floor is not a pure power law, and fitting one anyway understates how fast the reducible part is falling (section 5).
- **Size and data trade off at fixed compute.** More parameters means fewer tokens for the same budget. The compute-optimal point balances the two terms; the early scaling-law work and the later compute-optimal work disagreed about where it is (section 6).
- **Data quality is a loss-measurement problem too.** If test text is in the training set, or if one sentence appears 60,000 times, the loss on "held-out" text no longer tells you what you think.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "how do you deduplicate a web-scale corpus?" | exact match by hash; near-duplicates by MinHash with locality-sensitive hashing; exact repeated substrings by suffix structures (section 3) |
| "what is MinHash?" | a signature whose entries agree with probability equal to the Jaccard similarity of the shingle sets |
| "how do you stop test-set leakage?" | n-gram overlap between training and evaluation text, then remove or report (section 4) |
| "how big a model for this compute budget?" | `C ~ 6 N D`, then the compute-optimal split (section 6); mention the 1:1 scaling result |
| "what is a scaling law?" | a fitted relation, usually a power law, between loss and `N`, `D` or compute, valid in the range it was fitted |
| "can we extrapolate it?" | cautiously: it is an empirical fit, sensitive to the constants (section 6) |
| "why not train the biggest model?" | at fixed compute it may be undertrained; also inference cost scales with `N` |
| "multiple epochs over the same data?" | not covered by the fits read here; both papers' analyses assume less than one epoch |

---

## 3. Deduplication

Lee et al. ("Deduplicating Training Data Makes Language Models Better") report that existing language-modelling datasets contain many near-duplicate examples and long repetitive substrings, that over 1% of the unprompted output of models trained on them is copied verbatim from the training data, and that one 61-word sentence appeared over 60,000 times in C4. After deduplication, models emitted memorised text ten times less often and needed fewer training steps for the same or better accuracy. They built two tools: a suffix array to remove substrings that occur verbatim in more than one example (they chose a minimum matching length of 50 tokens), and MinHash to remove whole examples with high n-gram overlap with another example.

Below is the second tool in miniature, with every moving part exposed.

1. **Shingles.** Turn a document into the set of its `k`-word windows. Near-identical documents share most shingles.
2. **Jaccard similarity.** `|A ∩ B| / |A ∪ B|` of two shingle sets. Exact, but comparing all pairs is quadratic in the corpus.
3. **MinHash.** Hash every shingle with a random hash function and keep the minimum. For one random function, two sets have the same minimum exactly when the smallest element of their union is in both, which has probability equal to their Jaccard similarity. With 128 functions the fraction of agreeing positions estimates the similarity.
4. **LSH banding.** Cut the 128-entry signature into `b` bands of `r` rows. Two documents become a candidate pair if all `r` rows agree in at least one band. For true similarity `s` that happens with probability `1 - (1 - s^r)^b`: an S-curve that is near 0 for dissimilar pairs and near 1 for similar ones, with its steep part tunable through `b` and `r`.
5. **Verify.** Compute the exact Jaccard for each candidate and merge only if it passes the threshold. LSH proposes, the exact check decides, so a bad collision cannot merge unrelated documents.
6. **Cluster.** Union-find over the verified pairs; keep the earliest document of each cluster.

```python
import hashlib, math, random, re

# ---------- 1. Near-duplicate detection: shingles, MinHash, LSH banding ----------
def words(text):
    return re.findall(r"[a-z0-9']+", text.lower())

def shingles(text, k=3):
    """The set of k-word windows of a document."""
    w = words(text)
    if len(w) < k:
        return {" ".join(w)} if w else set()
    return {" ".join(w[i:i + k]) for i in range(len(w) - k + 1)}

def jaccard(a, b):
    return len(a & b) / len(a | b) if (a or b) else 1.0

P61 = (1 << 61) - 1

def make_params(n, seed):
    """n random hash functions h(x) = (a*x + b) mod P61."""
    rnd = random.Random(seed)
    return [(rnd.randrange(1, P61), rnd.randrange(P61)) for _ in range(n)]

def minhash(shingle_set, params):
    """For each hash function keep the smallest value over the set. Two sets agree on one
    position with probability equal to their Jaccard similarity."""
    base = [int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "big") for s in shingle_set]
    return [min((a * x + b) % P61 for x in base) for a, b in params]

def estimate_jaccard(sig1, sig2):
    return sum(x == y for x, y in zip(sig1, sig2)) / len(sig1)

def candidate_pairs(sigs, bands, rows):
    """Two documents become a candidate pair if ALL `rows` entries of at least one band match.
    P(candidate) = 1 - (1 - s^rows)^bands for true similarity s."""
    if not sigs:
        return set()
    assert len(sigs[0]) == bands * rows
    out = set()
    for band in range(bands):
        buckets = {}
        for i, sig in enumerate(sigs):
            buckets.setdefault(tuple(sig[band * rows:(band + 1) * rows]), []).append(i)
        for ids in buckets.values():
            out.update((a, b) for x, a in enumerate(ids) for b in ids[x + 1:])
    return out

def dedup(docs, k=3, threshold=0.7, bands=16, rows=8, seed=0, verify=True):
    """Keep the first document of every near-duplicate cluster. Returns indices to keep."""
    shs = [shingles(d, k) for d in docs]
    params = make_params(bands * rows, seed)
    sigs = [minhash(s, params) for s in shs]
    parent = list(range(len(docs)))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for a, b in candidate_pairs(sigs, bands, rows):
        if not verify or jaccard(shs[a], shs[b]) >= threshold:    # LSH proposes, exact Jaccard decides
            ra, rb = find(a), find(b)
            parent[max(ra, rb)] = min(ra, rb)                      # the root is always the earliest document
    return [i for i in range(len(docs)) if find(i) == i]
```

The check script holds this code to four standards: shingles match a brute-force window scan; the MinHash estimate averages to the true Jaccard over many seeds for pairs built with known similarity; the measured candidate rate at similarity 0.5, 0.7 and 0.8 matches the S-curve formula; and, on a planted corpus, the kept set always contains the kept set of the exact all-pairs clustering (LSH can miss a pair, never invent one). A mutation that removes the verification step is caught by a permissive-LSH test where false candidate pairs merge unrelated documents.

Choosing `(b, r)`: the steep part of the S-curve sits near `(1/b)^(1/r)`. With `b = 16`, `r = 8` that is about 0.71, which is why a 0.7 threshold is a reasonable pairing. Trade-off: more bands and fewer rows raise recall and the number of candidates to verify.

---

## 4. Train/Test Overlap

Deduplication within a corpus is one problem; overlap between the training corpus and the evaluation sets is another, and Lee et al. report that train-test overlap affects over 4% of the validation sets of standard datasets. They also describe the GPT-3 practice of removing training examples with a 13-gram overlap with any evaluation example. A simple version of that check:

```python
# ---------- 2. Exact shared windows: train/eval contamination ----------
def ngram_set(tokens, n):
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}

def contaminated(train_docs, eval_docs, n=8):
    """Indices of eval documents sharing at least one n-word window with any training document."""
    seen = set()
    for d in train_docs:
        seen |= ngram_set(words(d), n)
    return [i for i, d in enumerate(eval_docs) if ngram_set(words(d), n) & seen]
```

An exact-window check catches copies, not paraphrases. A model can still have seen the same information worded differently, and a low contamination count is not proof of a clean benchmark.

---

## 5. Fitting a Power Law, and Why the Floor Matters

Kaplan et al. ("Scaling Laws for Neural Language Models") found that loss scales as a power law with model size, dataset size and compute, with trends spanning more than seven orders of magnitude, and that other architectural details such as width or depth have minimal effects within a wide range. Their fits take the form `L(N) = (N_c / N)^alpha_N` with `alpha_N ~ 0.076` (non-embedding parameters) and `L(D) = (D_c / D)^alpha_D` with `alpha_D ~ 0.095` (tokens), each when the other factor is not the bottleneck.

You can fit such a law with least squares on logarithms: `log L = log c - alpha log N`. Two traps:

- **It is only valid where it was fitted.** Outside the range, you are extrapolating.
- **A floor changes the slope you measure.** If the loss really approaches a nonzero constant `E` (Hoffmann et al. call it the entropy of natural text under their model of the loss), then plain log-log fitting of `L` measures a flatter slope than the reducible part's true exponent. The demo below makes that concrete on synthetic data: true exponent `0.34`, floor `1.7`.

---

## 6. Compute-Optimal Allocation

Hoffmann et al. ("Training Compute-Optimal Large Language Models") trained over 400 models from 70 million to over 16 billion parameters on 5 to 500 billion tokens and concluded that for compute-optimal training the model size and the number of training tokens should be scaled equally: every doubling of model size should be matched by a doubling of tokens. They tested the prediction with Chinchilla, 70B parameters on 1.4 trillion tokens, using the compute of Gopher (280B parameters, 300B tokens) and report that it outperformed Gopher and several larger models on a broad set of downstream tasks. They estimated the optimum by three approaches that gave comparable exponents (about 0.46 to 0.50 for model size, 0.50 to 0.54 for tokens, per their Table 2). They approximate training cost as `FLOPs(N, D) ~ 6 N D`, citing Kaplan et al.

Kaplan et al.'s earlier fixed-budget analysis found, in contrast, that most of a larger budget should go to model size: `N` grows as `C_min^0.73`, and the dataset size sublinearly (`D ~ N^0.74`); they describe training very large models and stopping significantly short of convergence. The two papers disagree about the best split. This lesson does not adjudicate: it reports both, and shows how to compute the answer under a stated model of loss.

The third approach in the Chinchilla paper fits the parametric form `L(N, D) = E + A / N^alpha + B / D^beta`. The paper reports, in its appendix, the fit `E = 1.69`, `A = 406.4`, `B = 410.7`, `alpha = 0.34`, `beta = 0.28`. Minimising it under `6 N D = C` gives power laws: `N_opt = G (C/6)^a`, `D_opt = (C/6)^b / G`, with `a = beta / (alpha + beta)`, `b = alpha / (alpha + beta)` and `G = (alpha A / (beta B))^(1/(alpha + beta))`. The code implements that closed form and, independently, a brute-force search over model sizes.

```python
# ---------- 3. Scaling laws: fitting a power law, and the compute-optimal split ----------
def fit_power_law(xs, ys):
    """Least squares on log y = log c - alpha * log x. Returns (alpha, c) for y = c * x^-alpha."""
    lx, ly = [math.log(x) for x in xs], [math.log(y) for y in ys]
    mx, my = sum(lx) / len(lx), sum(ly) / len(ly)
    slope = sum((a - mx) * (b - my) for a, b in zip(lx, ly)) / sum((a - mx) ** 2 for a in lx)
    return -slope, math.exp(my - slope * mx)

def fit_with_floor(xs, ys, steps=4000):
    """y = E + c * x^-alpha: scan the floor E, fit the rest in log space, keep the best fit."""
    best = None
    for s in range(steps):
        E = min(ys) * s / steps                        # candidate floors in [0, min(y))
        alpha, c = fit_power_law(xs, [y - E for y in ys])
        sse = sum((math.log(E + c * x ** -alpha) - math.log(y)) ** 2 for x, y in zip(xs, ys))
        if best is None or sse < best[0]:
            best = (sse, E, alpha, c)
    return best[1:]

# Constants reported by Hoffmann et al. (Chinchilla paper, equation 10) for  L(N, D) = E + A/N^alpha + B/D^beta
E, A, B, ALPHA, BETA = 1.69, 406.4, 410.7, 0.34, 0.28

def loss(N, D):
    return E + A / N ** ALPHA + B / D ** BETA

def optimal_split(C):
    """Minimise loss(N, D) subject to 6*N*D = C. Closed form from the paper: N = G (C/6)^a, D = (C/6)^b / G."""
    G = (ALPHA * A / (BETA * B)) ** (1 / (ALPHA + BETA))
    a, b = BETA / (ALPHA + BETA), ALPHA / (ALPHA + BETA)
    return G * (C / 6) ** a, (C / 6) ** b / G

def grid_optimum(C, points=20000):
    """Brute force: try model sizes on a fine log grid, spend the rest of the budget on tokens."""
    best = None
    for i in range(points):
        N = 10 ** (6 + 8 * i / points)                 # 1e6 .. 1e14 parameters
        D = C / (6 * N)
        l = loss(N, D)
        if best is None or l < best[0]:
            best = (l, N, D)
    return best[1], best[2]
```

```python
RESULTS = {}

def planted_corpus(seed=7):
    """150 distinct synthetic documents of 80 words, plus exact copies and light edits of some of them."""
    rnd = random.Random(seed)
    vocab = [f"w{i}" for i in range(400)]
    weights = [1 / (r + 1) for r in range(400)]            # a few common words, a long tail
    docs = [" ".join(rnd.choices(vocab, weights, k=80)) for _ in range(150)]
    truth = list(range(150))                                # truth[i] = index of the original it copies
    for i in rnd.sample(range(150), 30):                    # exact duplicates
        docs.append(docs[i]); truth.append(i)
    for i in rnd.sample(range(150), 40):                    # near duplicates: 2 of 80 words replaced
        w = docs[i].split()
        for j in rnd.sample(range(80), 2):
            w[j] = rnd.choice(vocab)
        docs.append(" ".join(w)); truth.append(i)
    return docs, truth

def demo():
    L = []
    docs, truth = planted_corpus()
    keep = dedup(docs)
    shs = [shingles(d) for d in docs]
    truly_dup = {j for j in range(len(docs)) if truth[j] != j}
    RESULTS["kept"] = len(keep)
    dropped = set(range(len(docs))) - set(keep)
    caught = len(dropped & truly_dup)
    wrongly = len(dropped - truly_dup)
    L.append(f"{len(docs)} documents: 150 distinct + 30 exact copies + 40 light edits")
    L.append(f"MinHash-LSH (128 hashes, 16 bands x 8 rows) kept {len(keep)}; dropped {caught} of {len(truly_dup)} planted duplicates, {wrongly} wrongly")
    RESULTS["caught"], RESULTS["planted"], RESULTS["wrong"] = caught, len(truly_dup), wrongly
    # the S-curve: how likely is a pair to be proposed, as a function of its true similarity
    for s in (0.3, 0.5, 0.7, 0.8, 0.9):
        L.append(f"  similarity {s}: probability a pair is proposed = {1 - (1 - s ** 8) ** 16:.4f}")
    # scaling laws on synthetic data
    Ns = [1e6 * 4 ** i for i in range(8)]
    ys = [1.7 + 400 / n ** 0.34 for n in Ns]
    naive = fit_power_law(Ns, ys)[0]
    e_fit, alpha_fit, _ = fit_with_floor(Ns, ys)
    RESULTS["naive"], RESULTS["floor_fit"] = naive, (e_fit, alpha_fit)
    L.append(f"synthetic loss = 1.7 + 400/N^0.34: plain log-log slope {naive:.3f}; with a fitted floor E={e_fit:.2f}, alpha={alpha_fit:.3f}")
    C = 5.76e23
    n1, d1 = optimal_split(C); n2, d2 = grid_optimum(C)
    RESULTS["opt"] = ((n1, d1), (n2, d2))
    L.append(f"budget 5.76e23 FLOPs: closed form N={n1 / 1e9:.1f}B params, D={d1 / 1e12:.2f}T tokens; grid search N={n2 / 1e9:.1f}B")
    gopher, chin = loss(280e9, 300e9), loss(70e9, 1.4e12)
    RESULTS["gc"] = (gopher, chin)
    L.append(f"fitted loss: 280B params on 300B tokens {gopher:.3f}; 70B params on 1.4T tokens {chin:.3f}")
    L.append(f"exponents: N grows as C^{BETA / (ALPHA + BETA):.3f}, D as C^{ALPHA / (ALPHA + BETA):.3f}")
    return L

if __name__ == "__main__":
    print("\n".join(demo()))
```

Output (produced by the check script, which fails if this block drifts from the code):

```text
220 documents: 150 distinct + 30 exact copies + 40 light edits
MinHash-LSH (128 hashes, 16 bands x 8 rows) kept 151; dropped 69 of 70 planted duplicates, 0 wrongly
  similarity 0.3: probability a pair is proposed = 0.0010
  similarity 0.5: probability a pair is proposed = 0.0607
  similarity 0.7: probability a pair is proposed = 0.6133
  similarity 0.8: probability a pair is proposed = 0.9470
  similarity 0.9: probability a pair is proposed = 0.9999
synthetic loss = 1.7 + 400/N^0.34: plain log-log slope 0.108; with a fitted floor E=1.70, alpha=0.340
budget 5.76e23 FLOPs: closed form N=32.2B params, D=2.98T tokens; grid search N=32.2B
fitted loss: 280B params on 300B tokens 1.993; 70B params on 1.4T tokens 1.937
exponents: N grows as C^0.452, D as C^0.548
```

Reading it:

1. **Dedup.** The planted corpus has 70 duplicates; the pipeline drops 69 and none of the 150 distinct documents. The miss is a near-duplicate pair that the S-curve did not propose: recall below 100% is the price of LSH, and is why the table of S-curve probabilities is part of the answer to "how confident are you the corpus is deduplicated?".
2. **The S-curve.** At similarity 0.5 a pair is proposed about 6% of the time; at 0.8, 94.7%; at 0.9 essentially always.
3. **The floor.** The synthetic loss is `1.7 + 400 / N^0.34`. Plain log-log fitting reports a slope of `0.108`, a third of the true exponent; fitting the floor recovers `E = 1.70` and `alpha = 0.340`. (This is the lesson's own synthetic experiment, not a finding about real models.)
4. **The allocation.** For a budget of `5.76e23` FLOPs, the figure the paper gives for Gopher's training, the closed form with equation-10 constants gives about 32B parameters and 3T tokens, and the grid search lands on the same size. The paper's text projects about 40B parameters for this budget under its parametric approach. The difference is a reminder that extrapolations from fitted constants are sensitive: this lesson did not trace which exact fit produced the paper's 40B, so treat both numbers as showing the method, not as a recommendation.
5. **Exponents.** From the equation-10 constants, `N` grows as `C^0.452` and `D` as `C^0.548`: close to equal scaling, as the paper's headline says.
6. **Loss.** Under the fitted formula, the 70B/1.4T model's loss (`1.937`) is below the 280B/300B model's (`1.993`) at about the same compute. That is the formula's prediction, which is not the same as the measured downstream results the paper reports.

What this does not tell you: the fits assume less than one epoch of data (Hoffmann et al. say their runs are all under one epoch and leave multi-epoch training for future work); they say nothing about data quality; and they optimise training loss per unit of training compute, not total cost. The Chinchilla paper itself notes that a smaller model reduces inference cost considerably and eases downstream use on smaller hardware; if a model will serve a great deal of traffic, the right size under a training-only budget is not the right size under a lifetime-cost view. That last step is reasoning from the quoted statement, not a sourced rule.

---

## 7. Pitfalls Checklist

1. **Splitting before deduplicating.** Duplicates straddle the split and the validation loss lies.
2. **Treating MinHash as exact.** It samples; set `(b, r)` from the S-curve and measure recall on planted duplicates.
3. **Skipping the exact verification.** LSH collisions are not similarity.
4. **Using exact-match contamination checks as proof of a clean benchmark.** Paraphrases pass.
5. **Fitting a power law to a loss that has a floor** and reporting the exponent.
6. **Extrapolating beyond the fitted range** as if it were a law of nature.
7. **Quoting the "20 tokens per parameter" rule** or any single ratio without saying which paper, which constants and which compute range. Neither paper read here is cited for that figure.
8. **Forgetting inference cost.** Training-compute-optimal is not lifetime-cost-optimal.
9. **Assuming repeated data behaves like fresh data.** The fits here do not cover it.

---

## Drills

1. Two documents have 100 shingles each and share 80. What is the Jaccard similarity, and what do you expect 128 MinHash entries to show?
2. With 16 bands of 8 rows, what is the probability that a pair of true similarity 0.6 is proposed? Compute it, then say what a smaller `r` does to recall and to the number of candidates.
3. Why does the pipeline verify candidates with the exact Jaccard before merging?
4. Explain why `P(two MinHash entries agree) = Jaccard` holds for one random hash function.
5. A training set contains one sentence 60,000 times. Give two effects on the model and one on the loss number.
6. Your benchmark shows no 13-gram overlap with the training set. What can and can you not conclude?
7. Derive `N_opt` and `D_opt` from `L = E + A/N^alpha + B/D^beta` and `6 N D = C`, and check that `N * D * 6 = C`.
8. A colleague says "we should train a 175B model on 300B tokens because that is what the last big model did." Give the argument from the compute-optimal fit, then give one reason it might still be the right choice.

---

## Homework

1. Run the dedup code on a corpus of your own (for instance, the text of a few hundred README files) and report how many near-duplicate clusters it finds at two thresholds.
2. Measure recall of the LSH stage on planted duplicates at similarities 0.6, 0.7, 0.8, 0.9 for `(16, 8)`, `(32, 4)` and `(8, 16)`, and compare with the formula.
3. Add the exact-substring tool in miniature: find all windows of 20 words that occur in more than one document and report the most repeated.
4. Fit the floor-aware power law to the loss values of a small model family that you train yourself (the language model of Lesson 29 at several sizes counts).
5. Compute `N_opt` and `D_opt` for three budgets with the equation-10 constants and with `alpha = beta`, and describe how the answer shifts.
6. Read Hoffmann et al., section 3, and write down what differs between the three approaches; do not skip the caveats.

---

## Sources

Read on 26 November 2026:

- Hoffmann et al., "Training Compute-Optimal Large Language Models", arXiv:2203.15556, full text (ar5iv rendering). Used for the abstract claims, the model and token counts of Gopher and Chinchilla, the `6ND` approximation, the exponent summary, the parametric form and its reported constants, the 40B projection for the Gopher budget, the single-epoch caveat and the remark on inference cost.
- Kaplan et al., "Scaling Laws for Neural Language Models", arXiv:2001.08361, full text (ar5iv rendering). Used for the power-law forms and exponents quoted, the statement about architectural details, the fixed-budget conclusion and `N ~ C_min^0.73`, `D ~ N^0.74`.
- Lee et al., "Deduplicating Training Data Makes Language Models Better", arXiv:2107.06499, full text (ar5iv rendering). Used for the memorisation and duplicate-count statistics, the 4% train-test overlap, the two deduplication tools, the 50-token minimum, and the description of GPT-3's 13-gram overlap filter (as described by these authors, not read in the GPT-3 paper).

Not consulted, and nothing above relies on them: later work that refits or questions the compute-optimal constants, the GPT-3, Gopher, C4 and other corpus papers themselves, quality-filtering and data-mixture studies, and any data about proprietary training sets. Quality filtering and mixture design are named only; this lesson says nothing about how they are done.

*Last reviewed: 26 November 2026.*
