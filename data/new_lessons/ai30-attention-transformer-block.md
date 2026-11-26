# Lesson 30 — Attention and the Transformer Block

> **Priority:** ★★★★★ — "explain attention" is asked in nearly every ML-engineering loop; the follow-ups (why divide by the square root, why a mask, why positions, what is in a block) are where answers separate.
>
> **Study time:** 90 minutes. **Do this after:** the language-model-from-scratch lesson (Lesson 29). You need matrix multiplication and the softmax.
>
> **Level:** core.

A language model has to let each token's representation depend on the tokens around it. Recurrent networks pass information one step at a time; attention lets every position read from every other position directly, in one step. A Transformer layer is attention plus a few small pieces (a feed-forward network, residual connections, layer normalisation) that make a deep stack trainable. This lesson implements one layer in pure Python lists, then tests it against a naive per-query reference and checks that a causal mask leaks nothing from the future.

*Visual (planned): a token-by-token attention heat map for one head, with the causal mask shown as a greyed-out upper triangle, and a slider that changes the key dimension to show the softmax saturating without scaling.*

---

## 1. Mental Model

> **Attention is a soft lookup. Each token makes a query; every token offers a key and a value; the query is compared with all keys, the comparison scores become weights through a softmax, and the output is the weighted average of the values. A Transformer layer is that lookup, then a per-token feed-forward network, each wrapped in a residual connection and a normalisation.**

What follows from it:

- **Everything is a weighted average.** The weights are non-negative and sum to one per query, so each output is a convex combination of the value rows: it lies in their convex hull and cannot leave the range the values span. Nothing in that formula knows the order of the tokens.
- **Order has to be added.** Without a positional signal, shuffling the input shuffles the output and nothing else (section 5 shows it).
- **A mask is a rule about who may look at whom.** For next-token prediction a token must not see later tokens, or training would just copy the answer. The mask is applied before the softmax, as minus infinity, so those weights are exactly zero.
- **Only attention mixes tokens.** The feed-forward network, the normalisation and the residual additions all act on each token separately. That is why the leak test in section 6 can be so strong: if attention is masked, nothing else can carry information backwards.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "explain attention in one minute" | the soft-lookup picture, then `softmax(Q K^T / sqrt(d_k)) V` |
| "why divide by sqrt(d_k)?" | dot products of `d_k`-dimensional unit-variance vectors have variance `d_k`; unscaled, the softmax saturates (section 3) |
| "why multi-head?" | several smaller attentions in parallel, each free to pick a different pattern; cost stays about that of one full-width head (section 4) |
| "how does the model know word order?" | positional encodings added to the embeddings (section 5) |
| "how do you stop the model seeing the future?" | an additive `-inf` mask before the softmax (section 6) |
| "what is in a Transformer layer?" | attention, feed-forward, a residual and a layer norm around each (section 7) |
| "what does attention cost?" | an `n x n` score matrix per head: quadratic in sequence length |
| "layer norm versus batch norm?" | layer norm normalises across one token's features, so it does not depend on the batch or the sequence length |

---

## 3. Scaled Dot-Product Attention

For `n` queries, `m` keys and values: `softmax(Q K^T / sqrt(d_k)) V`. `Q` and `K` have `d_k` columns; `V` has `d_v`; the score matrix is `n x m`; each row of it is softmaxed.

```python
import math, random

def matmul(A, B):
    cols = list(zip(*B))
    return [[sum(a * b for a, b in zip(row, col)) for col in cols] for row in A]

def transpose(A):
    return [list(r) for r in zip(*A)]

def softmax(row):
    m = max(row)                                   # subtract the max: same answer, no overflow
    e = [math.exp(x - m) for x in row]
    s = sum(e)
    return [x / s for x in e]

def causal_mask(n):
    """Row i may look at columns j <= i; everything else gets -inf before the softmax."""
    return [[0.0 if j <= i else -math.inf for j in range(n)] for i in range(n)]

def attention(Q, K, V, mask=None):
    """softmax(Q K^T / sqrt(d_k)) V  -- returns (output, weights). Each row of weights sums to 1."""
    dk = len(Q[0])
    scores = matmul(Q, transpose(K))
    weights = []
    for i, row in enumerate(scores):
        row = [s / math.sqrt(dk) for s in row]
        if mask:
            row = [s + m for s, m in zip(row, mask[i])]
        weights.append(softmax(row))
    return matmul(weights, V), weights
```

Details that matter:

- **Subtract the row maximum before exponentiating.** The result is identical and large scores cannot overflow. The check feeds a score of 9000 and expects no overflow.
- **The `sqrt(d_k)`.** Vaswani et al. suspect that for large `d_k` the dot products grow in magnitude, pushing the softmax into regions with extremely small gradients, and their footnote gives the reason: if the components of `q` and `k` are independent with mean 0 and variance 1, `q.k` has mean 0 and variance `d_k`. Dividing by `sqrt(d_k)` restores unit variance. The demo below measures both effects.
- **Complexity.** The score matrix has `n x m` entries. For self-attention over `n` tokens the paper's Table 1 lists `O(n^2 * d)` work per layer with `O(1)` sequential operations and `O(1)` path length between any two positions. That quadratic term is why long contexts are expensive.

---

## 4. Multi-Head Attention

Project the input three times (`W_q`, `W_k`, `W_v`, each `d x d`), cut each projection into `h` slices of `d_k = d / h` columns, run attention independently on each slice, glue the `h` outputs side by side, and project once more with `W_o`. The paper uses `h = 8` and `d_k = d_v = d_model / h = 64`, and notes that because each head is smaller the total cost is similar to one full-width head. Their stated reason for it: a single head averages, while several heads can attend to different positions in different representation subspaces.

```python
def split_heads(X, h):
    """n x d  ->  h matrices of n x (d/h): head i owns columns i*dk .. (i+1)*dk."""
    dk = len(X[0]) // h
    return [[row[i * dk:(i + 1) * dk] for row in X] for i in range(h)]

def multi_head(X, Wq, Wk, Wv, Wo, h, mask=None):
    Qs, Ks, Vs = (split_heads(matmul(X, W), h) for W in (Wq, Wk, Wv))
    outs = [attention(q, k, v, mask)[0] for q, k, v in zip(Qs, Ks, Vs)]
    concat = [sum((o[i] for o in outs), []) for i in range(len(X))]     # glue the heads side by side
    return matmul(concat, Wo)

def positional_encoding(n, d):
    """Vaswani et al.: PE(pos, 2i) = sin(pos / 10000^(2i/d)), PE(pos, 2i+1) = cos(same angle)."""
    pe = [[0.0] * d for _ in range(n)]
    for pos in range(n):
        for i in range(0, d, 2):
            angle = pos / 10000 ** (i / d)
            pe[pos][i] = math.sin(angle)
            if i + 1 < d:
                pe[pos][i + 1] = math.cos(angle)
    return pe
```

The check recomputes every case the slow way: slice the weight matrices, run a separate naive attention per head, concatenate, multiply by `W_o`. It must agree to within `1e-9`.

---

## 5. Positions

Self-attention treats the tokens as a set. Take any input, permute the rows, and the output rows are permuted the same way (the demo prints it as `True`). The model cannot tell "dog bites man" from "man bites dog" until something carries position. The original Transformer adds a fixed positional encoding to the embedding: sines and cosines of geometrically spaced wavelengths. The `positional_encoding` function above is the paper's formula, `PE(pos, 2i) = sin(pos / 10000^(2i/d))` and `PE(pos, 2i+1) = cos(same angle)`. The authors chose it because they hypothesised that a fixed offset `k` makes `PE(pos + k)` a linear function of `PE(pos)`; for each sine/cosine pair that linear map is a rotation by an angle that depends on `k` and the pair but not on `pos`, which the check verifies numerically. They also tried learned positional embeddings and report nearly identical results (their Table 3, row E), and picked sinusoids because they might extrapolate to longer sequences than seen in training.

What this lesson does not cover, because the sources read do not: the position schemes used by later large models. Know that others exist and that the choice affects how far a model generalises past its training length; do not state details you have not read.

---

## 6. Masking: Prove It Leaks Nothing

For a language model, position `i` may attend to positions `0..i` only. The mask adds `-inf` to scores above the diagonal; `exp(-inf)` is exactly zero, so those weights are zero and the softmax over the remaining entries still sums to one. The diagonal is always allowed, so no row is fully masked (a fully masked row would be `0/0`).

The test that matters is behavioural, not structural: change one token, run the whole layer, and compare the outputs at *earlier* positions. With the mask they must be identical, bit for bit, because the changed token can influence earlier positions through no path; without the mask they must differ. The check does this for random sequences and positions, through the full layer defined in the next section.

A common bug is to apply the mask after the softmax (zeroing weights but not renormalising, so rows no longer sum to one) or to forget it at inference. Another is a row where every position is masked: `softmax` of all `-inf` is `nan`, so padding masks need a guard. This code masks with `-inf` and a max-subtracted softmax, which makes masked weights exactly zero; if you mask with a large finite negative number instead, check that it is negative enough for the score scale and numeric precision you use, because nothing in the sources read here covers that case.

---

## 7. The Block: Residual, Layer Norm, Feed-Forward

The original encoder layer has two sub-layers, multi-head self-attention and a position-wise feed-forward network, each with a residual connection followed by layer normalisation: the output of each sub-layer is `LayerNorm(x + Sublayer(x))`. The feed-forward network is two linear maps with a ReLU between, applied to each position separately. The base model has `d_model = 512` and inner size `d_ff = 2048`.

- **Residual.** The sub-layer adds a correction to its input instead of replacing it, so information has a direct path through the stack. The check turns both sub-layers off (output projections set to zero) and confirms the block reduces to two layer norms applied in a row to its input.
- **Layer norm.** Ba et al. compute the mean and variance from all the summed inputs of a layer on a single training case, so unlike batch normalisation it does not depend on the mini-batch. Here, for each token, subtract the mean of its `d` features, divide by their standard deviation, then apply a learned gain and bias. The check verifies zero mean, unit variance, invariance to rescaling the token, and that `eps` keeps a constant row finite.
- **Feed-forward.** The same two-layer network on every token. The check confirms that processing a token alone gives the same answer as inside a batch of tokens.
- **Where the parameters are.** Attention has four `d x d` matrices; the feed-forward network has two `d x d_ff` matrices plus biases. At the base size that is `4 * 512 * 512 = 1,048,576` for attention (the paper's formulation has no bias terms on these), `2,099,712` for the feed-forward network, and `2,048` for the two norms' gains and biases, `3,150,336` in all, counted by code below and not copied from a source.

Many later models move the normalisation or change other details of this layer. This lesson implements the original arrangement because it is the one in the paper read; check what a given model does before answering a question about it.

```python
def layer_norm(X, gain, bias, eps=1e-5):
    """Normalise each ROW (one token's d features) to mean 0, variance 1, then scale and shift."""
    out = []
    for x in X:
        mu = sum(x) / len(x)
        var = sum((v - mu) ** 2 for v in x) / len(x)
        out.append([g * (v - mu) / math.sqrt(var + eps) + b for v, g, b in zip(x, gain, bias)])
    return out

def add(A, B):
    return [[a + b for a, b in zip(ra, rb)] for ra, rb in zip(A, B)]

def feed_forward(X, W1, c1, W2, c2):
    hid = [[max(0.0, v + c) for v, c in zip(row, c1)] for row in matmul(X, W1)]    # ReLU
    return [[v + c for v, c in zip(row, c2)] for row in matmul(hid, W2)]

def init_params(d, dff, rnd):
    mat = lambda r, c: [[rnd.gauss(0, 1 / math.sqrt(r)) for _ in range(c)] for _ in range(r)]
    return dict(Wq=mat(d, d), Wk=mat(d, d), Wv=mat(d, d), Wo=mat(d, d),
                W1=mat(d, dff), c1=[0.0] * dff, W2=mat(dff, d), c2=[0.0] * d,
                g1=[1.0] * d, b1=[0.0] * d, g2=[1.0] * d, b2=[0.0] * d)

def block(X, P, h, mask=None):
    """One post-norm Transformer layer, as in the original paper: LayerNorm(x + Sublayer(x)) twice."""
    a = multi_head(X, P["Wq"], P["Wk"], P["Wv"], P["Wo"], h, mask)
    X = layer_norm(add(X, a), P["g1"], P["b1"])
    f = feed_forward(X, P["W1"], P["c1"], P["W2"], P["c2"])
    return layer_norm(add(X, f), P["g2"], P["b2"])
```

---

## 8. What the Experiments Show

```python
def n_params(P):
    return sum(len(r) for v in P.values() if isinstance(v[0], list) for r in v) + \
           sum(len(v) for v in P.values() if not isinstance(v[0], list))

def demo():
    L, rnd = [], random.Random(30)
    # 1. why divide by sqrt(d_k): dot products of unit-variance vectors have variance d_k
    for dk in (4, 64, 512):
        dots = []
        for _ in range(4000):
            q = [rnd.gauss(0, 1) for _ in range(dk)]; k = [rnd.gauss(0, 1) for _ in range(dk)]
            dots.append(sum(a * b for a, b in zip(q, k)))
        var = sum(x * x for x in dots) / len(dots)
        L.append(f"d_k={dk:<4} variance of q.k = {var:7.1f}   (theory: {dk})")
    # ...and what that does to the softmax: average largest weight over 8 random keys
    for dk in (4, 64, 512):
        raw, scaled = [], []
        for _ in range(400):
            q = [rnd.gauss(0, 1) for _ in range(dk)]
            s = [sum(a * rnd.gauss(0, 1) for a in q) for _ in range(8)]
            raw.append(max(softmax(s))); scaled.append(max(softmax([x / math.sqrt(dk) for x in s])))
        L.append(f"d_k={dk:<4} mean largest weight of 8: unscaled {sum(raw) / 400:.3f}, scaled {sum(scaled) / 400:.3f}")
    # 2. attention without positions cannot see order
    d, h, n = 8, 2, 5
    P = init_params(d, 16, rnd)
    X = [[rnd.gauss(0, 1) for _ in range(d)] for _ in range(n)]
    perm = [3, 0, 4, 1, 2]
    run = lambda Z: block(Z, P, h)
    plain = run([X[i] for i in perm]); base = run(X)
    gap = max(abs(a - b) for i, p in enumerate(perm) for a, b in zip(plain[i], base[p]))
    L.append(f"no positions: shuffling the tokens just shuffles the outputs (max gap below 1e-12: {gap < 1e-12})")
    pe = positional_encoding(n, d)
    withpos = lambda order: run(add([X[i] for i in order], pe))
    a, b = withpos(perm), withpos(list(range(n)))
    gap2 = max(abs(x - y) for i, p in enumerate(perm) for x, y in zip(a[i], b[p]))
    L.append(f"with positional encoding the same shuffle changes the outputs (max gap {gap2:.2f})")
    # 3. causal masking: change the LAST token, look at the earlier outputs
    X2 = [r[:] for r in X]; X2[-1] = [rnd.gauss(0, 1) for _ in range(d)]
    for name, mask in (("causal mask", causal_mask(n)), ("no mask", None)):
        o1, o2 = block(X, P, h, mask), block(X2, P, h, mask)
        leak = max(abs(a - b) for r1, r2 in zip(o1[:-1], o2[:-1]) for a, b in zip(r1, r2))
        L.append(f"{name:<11}: largest change in positions 0..{n - 2} when token {n - 1} changes = {leak:.3g}")
    # 4. parameter count of one layer at the base size in the paper (d=512, d_ff=2048, 8 heads)
    attn = 4 * 512 * 512
    ffn = 512 * 2048 + 2048 + 2048 * 512 + 512
    norms = 2 * 2 * 512
    L.append(f"one base layer: attention {attn:,} + feed-forward {ffn:,} + norms {norms:,} = {attn + ffn + norms:,}")
    L.append(f"counted from init_params at d=512, d_ff=2048: {n_params(init_params(512, 2048, random.Random(0))):,}")
    return L

if __name__ == "__main__":
    print("\n".join(demo()))
```

Output (produced by the check script, which fails if this block drifts from the code):

```text
d_k=4    variance of q.k =     4.1   (theory: 4)
d_k=64   variance of q.k =    64.5   (theory: 64)
d_k=512  variance of q.k =   519.1   (theory: 512)
d_k=4    mean largest weight of 8: unscaled 0.508, scaled 0.330
d_k=64   mean largest weight of 8: unscaled 0.874, scaled 0.352
d_k=512  mean largest weight of 8: unscaled 0.959, scaled 0.357
no positions: shuffling the tokens just shuffles the outputs (max gap below 1e-12: True)
with positional encoding the same shuffle changes the outputs (max gap 3.32)
causal mask: largest change in positions 0..3 when token 4 changes = 0
no mask    : largest change in positions 0..3 when token 4 changes = 0.35
one base layer: attention 1,048,576 + feed-forward 2,099,712 + norms 2,048 = 3,150,336
counted from init_params at d=512, d_ff=2048: 3,150,336
```

1. **Variance grows with `d_k`.** Measured variance of `q.k` is `4.1`, `64.5` and `519.1` for `d_k` of 4, 64 and 512, matching the theory of `d_k` within sampling noise.
2. **What that does to the softmax.** Among 8 random keys, the average largest weight is `0.508` unscaled against `0.330` scaled at `d_k = 4`, but at `d_k = 512` it is `0.959` unscaled against `0.357` scaled. Unscaled, attention at large width is almost one-hot at initialisation, which is the "extremely small gradients" the paper warns about; scaled, it stays spread out whatever the width. (The uniform value for 8 keys is `0.125`, so `0.357` is already peaky, but it is stable across widths.)
3. **Positions.** Without them, shuffling tokens only shuffles outputs; with them, the same shuffle changes the outputs (max gap `3.32` in this run).
4. **Masking.** With the causal mask, changing the last token changes nothing at earlier positions (exactly `0`); without it the change reaches them (`0.35`).
5. **Size.** The computed layer size agrees with the formula.

These come from random weights, not trained ones. They show the behaviours that depend on the mathematics (variance, saturation, the leak), not how a trained model attends.

---

## 9. Pitfalls Checklist

1. **Forgetting `1/sqrt(d_k)`.** The model still trains at small width and then gets fragile at large width.
2. **Masking after the softmax.** Rows stop summing to one and the future still leaks through the denominator.
3. **Normalising over the wrong axis.** Layer norm is per token across features. Normalising each feature across tokens makes a token's output depend on other tokens, which also breaks the causal guarantee.
4. **Splitting heads wrongly.** Head `i` must own a contiguous slice of the projected features; reshaping in the wrong order scrambles which features belong together without any error.
5. **No positions.** The model becomes a bag of tokens.
6. **A fully masked row.** `softmax` of all `-inf` is `nan`; padding masks need a guard.
7. **Treating the quadratic cost as free.** The score matrix is `n x n` per head.
8. **Leakage tests that only check the mask matrix.** Test the output of the whole layer, as in section 6.
9. **Quoting details of a real model from memory.** Say which paper you are reading from.

---

## Drills

1. Write attention for one query, one key, one value in a single line, and say what happens if there are two keys with identical scores.
2. Show that the variance of `q.k` is `d_k` when the components are independent with mean 0 and variance 1.
3. Why does a large `d_k` without scaling produce tiny gradients? Name the function and the region it is pushed into.
4. A model with `d = 512` and 8 heads has `d_k = 64`. How many parameters are in its four attention matrices, and why does changing the head count not change that number?
5. You apply the causal mask after the softmax. What property of the weights breaks, and does the future still leak?
6. What does `LayerNorm(x + Sublayer(x))` compute, in order? Name the parts that act on a token alone and the one that mixes tokens.
7. Without positional encoding, what does permuting the input rows do to the output of unmasked self-attention? Does the answer change with a causal mask?
8. At 4,096 tokens, how many entries does one head's score matrix have, and how does that change at 8,192?

---

## Homework

1. Implement `softmax` with a temperature argument and plot, as numbers, the largest weight against temperature for one random query and 8 keys.
2. Add a padding mask (some key positions are padding) and test that padded keys get zero weight and the rest sum to one, including the guard for a fully padded row.
3. Implement learned positional embeddings and compare with the sinusoidal version on the permutation experiment.
4. Stack two layers and extend the leak test to the stack.
5. Change the block to apply layer norm before each sub-layer instead of after, and say which tests of this lesson still pass without modification and why.
6. Count the floating-point multiplications in one attention head as a function of `n` and `d_k`, and check against a counter you add to `matmul`.

---

## Sources

Read on 26 November 2026:

- Vaswani et al., "Attention Is All You Need", arXiv:1706.03762 (NeurIPS 2017), full text (ar5iv rendering). Used for the formula, the scaling argument and its footnote, multi-head attention and its dimensions, the three uses of attention, the masking description, positional encoding (formula, the linear-offset hypothesis, learned versus sinusoidal), the layer structure `LayerNorm(x + Sublayer(x))`, the base dimensions, and Table 1.
- Ba, Kiros and Hinton, "Layer Normalization", arXiv:1607.06450, abstract and introduction (ar5iv rendering). Used only for the statement that the statistics are computed from the summed inputs of a layer on a single training case, so there is no dependence on the mini-batch.

Not consulted, and nothing above relies on them: the original additive-attention paper, papers on later position schemes, pre-norm analyses, any implementation of a production model, FlashAttention and other efficient-attention work, key-value caching (covered in the vLLM lesson).

*Last reviewed: 26 November 2026.*
