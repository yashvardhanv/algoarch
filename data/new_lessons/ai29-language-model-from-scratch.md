# Lesson 29 — A Language Model from Scratch, and Training Hygiene

> **Priority:** ★★★★★ — "build a tiny language model" and "your validation loss went up, what now?" are the two most common ways an ML interviewer tests whether you have actually trained something.
>
> **Study time:** 75 minutes. **Do this after:** the autodiff and gradient descent lesson (Lesson 28). You should be comfortable with logarithms and the softmax.
>
> **Level:** core.

A language model assigns a probability to the next token given what came before. Everything a large model does is a scaled-up version of that, so the cleanest way to understand it is to build the smallest honest one, in pure Python, on a corpus small enough to see. This lesson builds a counting model, shows that gradient descent on a softmax model reaches the same answer, and then spends most of its time on the part interviewers actually probe: how to know whether a training run is healthy. Every number below is printed by the code in the lesson.

---

## 1. Mental Model

> **A language model is a table from context to a probability distribution over the next token. Training picks that table to minimise the average negative log-probability of the true next token on the training text. The only number that tells you whether it learned the language, rather than memorised the text, is the same loss on text it never trained on.**

What follows from it:

- **Loss is surprise.** Average `-ln p(true next token)` in nats. A model that knows nothing and guesses uniformly over `V` tokens scores exactly `ln V`; its perplexity (`e^loss`) is `V`. Every real loss is read against that.
- **There is a floor.** Text is partly random, so even the perfect model has a loss above zero. A loss lower than the floor on held-out text means something leaked.
- **More context fits the training set better, always.** Whether it helps on new text depends on how much data you have to estimate that many contexts. That tension is the whole of overfitting.
- **Counting and gradient descent are the same estimator.** For a model whose parameters are the table itself, the loss is minimised exactly at the table of observed frequencies. Gradient descent just gets there iteratively (section 5).

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "build a language model / bigram model" | count pairs, normalise rows, add smoothing; evaluate by held-out loss |
| "train loss falls, validation loss rises" | overfitting: less capacity, more data, more smoothing or regularisation, earlier stop |
| "what loss should I see at step 0?" | `ln V` for a softmax over `V` tokens with zero (or small) initial weights |
| "loss is stuck near its initial value" | learning rate far too small, or a bug that stops gradients (section 6) |
| "loss jumps up or goes to inf/nan" | learning rate too large; check the sweep (section 6) |
| "is the model good?" | compare with the uniform baseline, the simplest model (counts), and, if known, the floor |
| "how do I split the data?" | deduplicate first, then split by document, never by position inside a document |
| "what is perplexity?" | `exp(average negative log-likelihood per token)`: the effective number of equally likely choices |

---

## 3. The Data, and the Split

Real corpora are too big to inspect. This lesson invents a language you can reason about: words are two to four syllables, each a consonant (`p t k m n l`) followed by a vowel, and, the property that makes it interesting, every vowel in a word comes from the same group, either `e i` or `a o u` (a toy version of vowel harmony). The first character gives no hint of the group; later vowels are determined by earlier ones. The `.` character is the start and end marker.

Because the generator is known, the true loss floor can be computed: the language's own probability of each val word (pick a group, pick a length, pick each syllable). That is `generator_nll`. A model with a short context cannot quite reach it: the end-of-word choice depends on how many syllables have been spoken, which three characters do not reveal.

Two data-hygiene rules are built into `split_words`, and both come up in interviews:

- **Deduplicate before splitting.** The generator emits some words several times. If duplicates straddle the split, validation words appear in training and the validation loss lies. (The same failure at web scale is the subject of the pretraining-data lesson.)
- **Split by word.** Splitting by position inside a word would put one half of a word in training and the other half in validation.

```python
import math, random

CONS, FRONT, BACK = "ptkmnl", "ei", "aou"
START = "."                                   # doubles as the end-of-word marker
VOCAB = sorted(CONS + FRONT + BACK) + [START]
IDX = {ch: i for i, ch in enumerate(VOCAB)}
V = len(VOCAB)

def make_words(n, seed):
    """Invented 'language': 2-4 consonant+vowel syllables, every vowel in a word from ONE group."""
    rnd = random.Random(seed)
    words = []
    for _ in range(n):
        vowels = rnd.choice([FRONT, BACK])
        words.append("".join(rnd.choice(CONS) + rnd.choice(vowels) for _ in range(rnd.randint(2, 4))))
    return words

def split_words(words, val_frac=0.2, seed=0):
    """Deduplicate FIRST, then split by word, so no word is in both sets."""
    uniq = sorted(set(words))
    random.Random(seed).shuffle(uniq)
    cut = int(len(uniq) * (1 - val_frac))
    return uniq[:cut], uniq[cut:]

def pairs(words, ctx):
    """(context string, next char) for every position, padding the start with the marker."""
    for w in words:
        s = START * ctx + w + START
        for i in range(ctx, len(s)):
            yield s[i - ctx:i], s[i]

def fit_counts(words, ctx):
    counts = {}
    for c, ch in pairs(words, ctx):
        row = counts.setdefault(c, {})
        row[ch] = row.get(ch, 0) + 1
    return counts

def count_prob(counts, c, ch, alpha):
    """Add-alpha smoothing: (count + alpha) / (total + alpha * V)."""
    row = counts.get(c, {})
    den = sum(row.values()) + alpha * V
    return (row.get(ch, 0) + alpha) / den if den else 0.0

def mean_nll(prob_fn, words, ctx):
    """Average negative log-likelihood per predicted character, in nats; inf if any p is 0."""
    total = n = 0
    for c, ch in pairs(words, ctx):
        p = prob_fn(c, ch)
        if p <= 0.0:
            return math.inf
        total -= math.log(p); n += 1
    return total / n

def sample_word(prob_fn, ctx, rnd, max_len=12):
    out, c = "", START * ctx
    while len(out) < max_len:
        r, acc, nxt = rnd.random(), 0.0, VOCAB[-1]
        for ch in VOCAB:
            acc += prob_fn(c, ch)
            if r < acc:
                nxt = ch; break
        if nxt == START:
            break
        out += nxt
        c = (c + nxt)[-ctx:] if ctx else ""
    return out
```

---

## 4. The Counting Model, Smoothing, and Honest Evaluation

A model with context length `ctx` keeps counts of how often each character followed each `ctx`-character context. The maximum-likelihood estimate is `count / total`. It fails on anything unseen: probability zero means infinite loss, and one unseen context in the validation set ruins the average. The fix used since the early days is additive smoothing: `(count + alpha) / (total + alpha * V)`. Chen and Goodman's 1996 smoothing study describes it as the simplest smoothing in practice and compares it against more elaborate schemes by the cross-entropy of test data, which is also how this lesson scores models.

`ctx = 0` is a unigram model, `ctx = 1` a bigram, `ctx = 2` a trigram, and so on.

---

## 5. The Same Model by Gradient Descent

Give each context position a table of learned scores (logits) and add them up: the logits for the next character are the sum, over the `ctx` previous characters, of one row each. A softmax turns logits into probabilities. For one training pair the gradient of `-ln p(target)` with respect to the logits is `p - onehot(target)`, the model's probabilities minus 1 at the true character. That one line is the entire backward pass here, so this model needs no autodiff engine; the check script compares it with finite differences exactly as in Lesson 28.

Two facts worth stating, both verified by the check script:

1. At zero weights every probability is `1/V`, so the starting loss is exactly `ln V`. If your first loss is far from that, the model or the loss is wrong before training even starts.
2. For `ctx = 1`, put the logarithms of the count-based probabilities in the table and the gradient is zero. Counting is the minimiser; the trained model can at best match it.

```python
def softmax(z):
    m = max(z); e = [math.exp(x - m) for x in z]; s = sum(e)
    return [x / s for x in e]

class LogLinear:
    """logits for the next char = sum over the ctx previous chars of a learned row W[j][char]."""
    def __init__(self, ctx):
        self.ctx = ctx
        self.W = [[[0.0] * V for _ in range(V)] for _ in range(ctx)]
    def logits(self, c):
        return [sum(self.W[j][IDX[c[j]]][v] for j in range(self.ctx)) for v in range(V)]
    def prob(self, c, ch):
        return softmax(self.logits(c))[IDX[ch]]

def loss_and_grad(model, batch):
    """Mean NLL on a list of (context, next char) and its gradient; d loss / d logit_v = p_v - [v is target]."""
    grad = [[[0.0] * V for _ in range(V)] for _ in range(model.ctx)]
    total = 0.0
    for c, ch in batch:
        p = softmax(model.logits(c)); t = IDX[ch]
        total -= math.log(p[t])
        for v in range(V):
            d = (p[v] - (1.0 if v == t else 0.0)) / len(batch)
            for j in range(model.ctx):
                grad[j][IDX[c[j]]][v] += d
    return total / len(batch), grad

def train(model, train_pairs, val_pairs, lr, steps, batch_size=64, seed=0, every=100):
    rnd, history = random.Random(seed), []
    for step in range(steps + 1):
        if step % every == 0:
            history.append((step, loss_and_grad(model, train_pairs)[0], loss_and_grad(model, val_pairs)[0]))
        if step == steps:
            break
        _, g = loss_and_grad(model, [rnd.choice(train_pairs) for _ in range(batch_size)])
        for j in range(model.ctx):
            for r in range(V):
                for v in range(V):
                    model.W[j][r][v] -= lr * g[j][r][v]
    return history
```

---

## 6. Training Hygiene, in Numbers

```python
def generator_nll(words):
    """What the invented language itself scores on these words: the best any model could hope for."""
    total = n = 0
    for w in words:
        k, group = len(w) // 2, len(FRONT) if w[1] in FRONT else len(BACK)
        total -= math.log(0.5 * (1 / 3) * (1 / (6 * group)) ** k)   # pick group, pick length, then k syllables
        n += len(w) + 1
    return total / n

def mixes_groups(w):
    return any(ch in FRONT for ch in w) and any(ch in BACK for ch in w)

RESULTS = {}

def demo():
    L = []
    train_w, val_w = split_words(make_words(900, 1))
    L.append(f"words: {len(train_w)} train, {len(val_w)} val; vocabulary {V}")
    L.append(f"uniform guess: loss {math.log(V):.3f} nats, perplexity {math.exp(math.log(V)):.2f}")
    RESULTS["floor"] = generator_nll(val_w)
    L.append(f"the language's own loss on val words: {RESULTS['floor']:.3f}")

    for name, ws in (("632 train words", train_w), ("40 train words", train_w[:40])):
        L.append(f"count models, add-0.1 smoothing, trained on {name}")
        for ctx in range(4):
            c = fit_counts(ws, ctx)
            f = lambda a, b: count_prob(c, a, b, 0.1)
            tr, va = mean_nll(f, ws, ctx), mean_nll(f, val_w, ctx)
            RESULTS[(len(ws), ctx)] = (tr, va)
            L.append(f"  context {ctx}: train {tr:.3f}  val {va:.3f}")

    tp, vp = list(pairs(train_w, 2)), list(pairs(val_w, 2))
    m = LogLinear(2); hist = train(m, tp, vp, 1.0, 600, every=100)
    RESULTS["curve"] = hist
    L.append("log-linear model, context 2, lr 1.0 (step: train / val)")
    L.append("  " + "  ".join(f"{s}: {a:.3f}/{b:.3f}" for s, a, b in hist))

    L.append("learning-rate sweep, context 2, val loss after 300 steps")
    sweep = {}
    for lr in (0.01, 0.1, 1.0, 10.0, 100.0):
        sweep[lr] = train(LogLinear(2), tp, vp, lr, 300, every=300)[-1][2]
    RESULTS["sweep"] = sweep
    L.append("  " + "  ".join(f"lr {lr:g}: {v:.3f}" for lr, v in sweep.items()))

    tp1, vp1 = list(pairs(train_w, 1)), list(pairs(val_w, 1))
    m1 = LogLinear(1); h1 = train(m1, tp1, vp1, 3.0, 1500, every=1500)
    c1 = fit_counts(train_w, 1)
    cv = mean_nll(lambda a, b: count_prob(c1, a, b, 0.0), val_w, 1)
    RESULTS["bigram"] = (h1[-1][2], cv)
    L.append(f"bigram: trained log-linear val {h1[-1][2]:.3f} vs counting val {cv:.3f}")

    rnd = random.Random(5)
    for ctx in (1, 2):
        c = fit_counts(train_w, ctx)
        ws = [sample_word(lambda a, b: count_prob(c, a, b, 0.1), ctx, rnd) for _ in range(2000)]
        RESULTS[("mix", ctx)] = sum(mixes_groups(w) for w in ws) / len(ws)
        L.append(f"context {ctx} samples mixing vowel groups: {100 * RESULTS[('mix', ctx)]:.1f}% (the language: 0%)")
    return L

if __name__ == "__main__":
    print("\n".join(demo()))
```

Output (produced by the check script, which fails if this block drifts from the code):

```text
words: 632 train, 158 val; vocabulary 12
uniform guess: loss 2.485 nats, perplexity 12.00
the language's own loss on val words: 1.404
count models, add-0.1 smoothing, trained on 632 train words
  context 0: train 2.460  val 2.457
  context 1: train 1.728  val 1.740
  context 2: train 1.517  val 1.573
  context 3: train 1.405  val 1.698
count models, add-0.1 smoothing, trained on 40 train words
  context 0: train 2.436  val 2.477
  context 1: train 1.604  val 1.960
  context 2: train 1.237  val 2.256
  context 3: train 1.036  val 2.377
log-linear model, context 2, lr 1.0 (step: train / val)
  0: 2.485/2.485  100: 1.778/1.782  200: 1.661/1.670  300: 1.616/1.635  400: 1.594/1.615  500: 1.580/1.593  600: 1.571/1.590
learning-rate sweep, context 2, val loss after 300 steps
  lr 0.01: 2.430  lr 0.1: 2.085  lr 1: 1.635  lr 10: 1.603  lr 100: 5.283
bigram: trained log-linear val 1.761 vs counting val 1.738
context 1 samples mixing vowel groups: 51.4% (the language: 0%)
context 2 samples mixing vowel groups: 3.0% (the language: 0%)
```

Read it in this order, which is also the order to read a real run:

1. **Baseline.** Uniform guessing scores `2.485`; the language's own loss on these val words is `1.404`. Every honest model lives between those two numbers.
2. **Context helps, then hurts.** With 632 training words, validation loss improves from context 0 to 1 to 2 (`2.457`, `1.740`, `1.573`) and then gets worse at context 3 (`1.698`) while training loss keeps falling (`1.405`, a figure close to the floor, reached by memorising contexts rather than by learning the rule). Context 3 has seen too few examples of each context. Selecting by validation loss picks context 2, and context 2 is also what the language needs: the previous vowel two characters back decides the next vowel's group.
3. **Overfitting in plain sight.** With only 40 training words the same sequence is dramatic: training loss falls to `1.036` at context 3 while validation loss climbs to `2.377`, a gap over one nat. A training loss alone would have said the opposite.
4. **The loss curve.** The log-linear model with context 2 and `lr = 1.0` starts at `2.485` (equal on train and val, as predicted) and falls every hundred steps; train and val stay close because this model is small relative to the data. A curve whose training line falls while the validation line flattens or rises is the picture of the previous point.
5. **The learning-rate sweep.** After 300 steps, `lr = 0.01` has barely moved (`2.430`), `0.1` is slow (`2.085`), `1` and `10` are good (`1.635`, `1.603`), and `100` is worse than guessing (`5.283`). Too small looks like a healthy loss that does not go anywhere; too large looks like a loss that jumps up. Sweep by factors of ten before you tune anything else.
6. **Counting versus training.** The trained bigram reaches `1.761` validation loss against `1.738` for the closed-form counts, close but not equal: SGD with 64-example batches and a fixed learning rate keeps jittering around the minimum. The trained context-2 model (`1.590`) lands near the context-2 counts (`1.573`) but cannot beat them; it is additive across positions, a restriction counts do not have.
7. **Loss is not the whole story.** Sample 2000 words and count how many mix the two vowel groups, which the real language never does. The bigram model, whose loss looks only 0.17 nats worse than context 2, mixes them `51.4%` of the time; context 2 does it `3.0%` of the time. Reading samples catches what an average hides, and a loss gap of a fraction of a nat can be the difference between a model that has learned a rule and one that has not.

None of these numbers belongs to a real language, and the toy is far smaller than any real corpus. What carries over are the procedures: start-of-training loss against `ln V`, compare to simple baselines, read validation not training, sweep the learning rate, look at samples.

---

## 7. Pitfalls Checklist

1. **Reporting training loss.** It decreases with capacity by construction (section 6, point 2).
2. **Splitting after duplicates are in.** Leakage makes validation loss optimistic and hides overfitting.
3. **Unsmoothed counts evaluated on new text.** One unseen context gives infinite loss. Smooth, and choose `alpha` on validation data.
4. **Tuning on the validation set and reporting it as the final score.** Once you have chosen `alpha`, context length and learning rate with it, hold out a third set that you look at once.
5. **A first loss that is not near `ln V`.** Check shapes, label alignment (is the target the next token?) and the loss before anything else.
6. **Never trying to overfit a tiny batch.** A model that cannot drive the loss to near zero on eight examples has a bug that more data will not fix.
7. **Comparing losses across different vocabularies or tokenisers.** Nats per token are not comparable if the tokens differ.
8. **Judging by loss alone.** Read samples; compute task-specific checks (here, the harmony rule).
9. **Changing several things at once.** One change per run, or you will not know which one mattered.

---

## Drills

1. A model over 50,000 tokens starts at loss `10.82`. Is that plausible? What would you check if it were `14`?
2. State `perplexity` in words, and compute it from an average loss of `1.573` nats.
3. With 40 training words, validation loss rises as context grows from 1 to 3 while training loss falls. Explain each trend in one sentence.
4. Why does the unsmoothed trigram have infinite validation loss, and what does `alpha` trade away?
5. Derive the gradient of `-ln softmax(z)[t]` with respect to `z` and explain why the training loop needs only `p - onehot`.
6. A learning-rate sweep gives `1.635` at `1` and `5.283` at `100`. What would you try next, and what would you expect at `0.001`?
7. Your validation set contains a word that also appears in training. By how much can that bias the result, and how do you find such overlaps in a large corpus?
8. Two models have similar validation loss but one mixes the vowel groups far more often. Which would you ship, and what does that say about the loss?

---

## Homework

1. Add a second model type: a context-3 log-linear model with one extra interaction feature (the pair of the two previous characters as a single row). Does it close the gap to the counts?
2. Choose `alpha` for each context length on the validation set and report the table again; show how the best `alpha` changes between 40 and 632 training words.
3. Add a held-out test set and report all final numbers there once.
4. Replace SGD with the Adam optimizer from Lesson 28 and rerun the learning-rate sweep. Does the good range of `lr` move?
5. Build an early-stopping rule that keeps the weights with the lowest validation loss, and show it on the 40-word run with a model you train long enough to overfit.
6. Generate 20 words from the context-2 model and from the context-1 model and classify them by hand as valid or invalid in the invented language. Compare with the mixing rates above.

---

## Sources

Read on 26 November 2026:

- Chen and Goodman, "An Empirical Study of Smoothing Techniques for Language Modeling", arXiv:cmp-lg/9606011 (ACL 1996), full text from the arXiv PDF. Used for the definition of additive smoothing, the use of test-set cross-entropy as the measure, and the statement that the relative performance of techniques depends on training-set size and n-gram order. The invented language, the numbers and every other claim are this lesson's own and are produced by its script.

Not consulted, and nothing above relies on them: Bengio et al.'s neural probabilistic language model paper, textbook treatments of perplexity, any real-corpus measurement. Statements about "real" language models in this lesson are limited to the general structure (next-token prediction with a cross-entropy loss), which section 6 shows on a toy and does not measure at scale.

*Last reviewed: 26 November 2026.*
