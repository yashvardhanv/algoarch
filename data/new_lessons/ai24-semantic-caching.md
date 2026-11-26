# Lesson 24 — Semantic Vector Caching & Prompt Routing

> **Priority:** ★★★★★ — the cost-engineering follow-up: "your bill tripled; what do you do before buying more GPUs?"
>
> **Study time:** 60 minutes. **Do this after:** Lesson 02 (Tokens, BPE and Embeddings) and Lesson 16 (Observability, Tracing & Cost Engineering).
>
> **Level:** advanced. Optional for a crash plan; worth doing if your target loops include LLM platform or cost rounds.

Two levers cut the cost of an LLM product without touching the model: answer a query from a cache
when an earlier query meant the same thing, and send each query that does reach a model to the
cheapest model that can answer it. Both are easy to build and easy to get dangerously wrong, because
both are *decisions made by a similarity score or a classifier*, and every wrong decision serves a
worse answer. This lesson is about making those decisions measurable: what goes in the cache key,
how to pick the threshold from labelled data, and how to reason about the cost.

---

## 1. Mental Model

> **A semantic cache hit is a claim: "the answer I stored for that earlier query is correct for this
> one." A router decision is a claim: "the cheap model is good enough here." Treat both as
> classifiers with a precision you measure, not as free speed-ups.**

What follows from it:

- **Exact caches never lie; semantic caches can.** A hash of the full prompt only hits on identical
  input. Embedding similarity hits on paraphrases, and also on near-misses ("cancel my order" and
  "don't cancel my order" can embed close together). The GPTCache README says plainly that a semantic
  cache produces false positives on hits and false negatives on misses.
- **The threshold is a precision-versus-hit-rate dial**, and the right setting depends on the embedding
  model, the traffic and the cost of a wrong answer. RedisVL's guide makes the same point: the threshold
  is not a fixed quantity. So you set it from labelled pairs, per use case.
- **Anything that changes the right answer must be in the key**, not just the user's words.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "the same questions keep coming, worded differently" (FAQ, support, docs search) | semantic cache with a calibrated threshold |
| "identical requests" (retries, the same report regenerated) | exact cache on a hash of the full request |
| "long shared system prompt, different questions" | provider prefix caching (Lesson 09), not a semantic cache |
| "answers depend on the user, their data or time" | scope the key, add a TTL, or do not cache |
| "most queries are easy, a few need the frontier model" | a router with a threshold on predicted strong-model win probability |
| "we can check an answer cheaply (tests, schema, a verifier)" | a cascade: cheap model first, escalate on failure |
| "creative or high-temperature output" | skip the cache; users expect variety |

---

## 3. Exact vs Semantic Caching

| | Exact cache | Semantic cache |
|---|---|---|
| Key | hash of the full request (model, system prompt, messages, parameters) | embedding of the query, plus a scope |
| Hits on | identical requests | paraphrases, and some near-misses |
| Wrong answers served | none (if the key is complete) | the false-positive rate at your threshold |
| Cost per lookup | a hash and a key-value read | an embedding call and a nearest-neighbour search |
| Tuning | none | threshold, TTL, scope, eviction |

Put an exact cache in front of the semantic one: it is cheaper and never wrong.

**What belongs in the scope.** Everything that can change the correct answer: the tenant or user
(RedisVL's guide uses filterable tag fields for exactly this, to keep users' entries apart), the model
and its version, a hash of the system prompt and tool definitions, the version of any retrieved data,
and the language. If two requests differ in any of these, they must never share an entry. Leaking one
user's cached answer to another is a security bug, not a cache miss.

**Temperature.** GPTCache treats temperature as a reason to skip the cache: in its README, a higher
temperature means a higher chance of skipping the cache search, and at the maximum it always calls the
model. The principle generalises: cache deterministic tasks, not creative ones.

---

## 4. A Semantic Cache You Can Reason About

Linear scan, cosine similarity on normalised vectors, a scope per entry, a time-to-live, and
least-recently-used eviction. In production the scan becomes an approximate nearest-neighbour index
(the vector store), but the decisions are the same.

```python
import math
from collections import OrderedDict

def normalize(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]

def cosine(a, b):
    """Cosine similarity of two already-normalised vectors."""
    return sum(x * y for x, y in zip(a, b))

class SemanticCache:
    def __init__(self, threshold, capacity, ttl):
        self.threshold, self.capacity, self.ttl = threshold, capacity, ttl
        self.entries = OrderedDict()   # key -> (scope, unit vector, answer, stored_at); least recently used first
        self.next_key = 0

    def _purge(self, now):
        for key in [k for k, e in self.entries.items() if now - e[3] >= self.ttl]:
            del self.entries[key]

    def get(self, scope, emb, now):
        """The answer of the most similar live entry in this scope, if it clears the threshold."""
        self._purge(now)
        q = normalize(emb)
        best_key, best_sim = None, -2.0
        for key, (s, vec, _, _) in self.entries.items():
            if s != scope:
                continue                       # never match across tenants, models or prompt versions
            sim = cosine(q, vec)
            if sim > best_sim:
                best_key, best_sim = key, sim
        if best_key is None or best_sim < self.threshold:
            return None                        # miss: call the model, then put()
        self.entries.move_to_end(best_key)     # a hit makes the entry most recently used
        return self.entries[best_key][2]

    def put(self, scope, emb, answer, now):
        self._purge(now)
        if len(self.entries) >= self.capacity:
            self.entries.popitem(last=False)   # evict the least recently used live entry
        self.entries[self.next_key] = (scope, normalize(emb), answer, now)
        self.next_key += 1
```

Three choices to defend in an interview:

1. **Best match, then threshold.** Taking the *first* entry above the threshold returns a worse
   match than one that exists.
2. **Expire before you match.** A stale answer above the threshold is still stale.
3. **Evict by recency, and count what you evict.** The GPTCache README warns that counting entries
   rather than bytes can misjudge memory; if answers vary a lot in size, budget by bytes.

---

## 5. Choosing the Threshold From Data

Collect query pairs from real traffic (an incoming query and its nearest cached query), have a person
or a strong judge label whether the cached answer is acceptable, and record each pair's similarity. Then
choose the lowest threshold whose served hits still meet your precision target.

```python
def calibrate_threshold(labelled, min_precision):
    """labelled: (similarity, cached_answer_ok) pairs. Returns (threshold, precision, served_fraction)
    for the LOWEST threshold whose served pairs reach min_precision, or None if none does."""
    best = None
    for t in sorted({s for s, _ in labelled}, reverse=True):
        served = [ok for s, ok in labelled if s >= t]
        precision = sum(served) / len(served)
        if precision >= min_precision:
            best = (t, precision, len(served) / len(labelled))
    return best
```

Precision is **not** monotone in the threshold, which is why the loop checks every candidate instead
of stopping at the first failure.

**Worked example (illustrative, ten labelled pairs, produced by the check).** Similarities
`0.97 ok, 0.95 ok, 0.93 wrong, 0.92 ok, 0.90 ok, 0.88 wrong, 0.86 ok, 0.84 wrong, 0.80 wrong, 0.75 wrong`.

- Target precision 0.9: threshold 0.95, precision 1.0, serving 20% of these queries.
- Target precision 0.75: threshold 0.90, precision 0.8, serving 50%. Note that 0.93 alone would fail
  (precision 0.67) while the lower 0.90 passes: that is the non-monotonicity.

Ten pairs is far too few to trust; the example only shows the procedure. Recalibrate whenever you change
the embedding model, because similarity scores from different models are not comparable.

---

## 6. Routing Between a Strong and a Weak Model

RouteLLM frames routing as a binary decision. A router estimates `P(strong wins | q)`, the chance the
strong model's answer is better than the weak model's for query `q`, and a threshold `α` decides: strong
if the estimate is at least `α`, weak otherwise. The paper states that `α` controls the trade-off between
quality and cost. Its routers are trained on human preference data (with augmentation), and include a
similarity-weighted Bradley-Terry ranker, matrix factorisation, a BERT classifier and an LLM classifier.

```python
def route(p_strong_wins, alpha):
    return 'strong' if p_strong_wins >= alpha else 'weak'

def alpha_for_budget(scores, strong_fraction):
    """Smallest threshold that would have sent at most strong_fraction of these historical queries
    to the strong model. scores: the router's P(strong wins) for each query."""
    limit = math.floor(strong_fraction * len(scores))
    for a in sorted(set(scores)) + [float('inf')]:
        if sum(s >= a for s in scores) <= limit:
            return a
```

**How RouteLLM measures a router.** *Call percentage* is the share of queries sent to the strong model.
*Performance gap recovered* is `(quality of the routed system - weak quality) / (strong quality - weak
quality)`. `CPT(x%)` is the smallest call percentage that recovers `x%` of the gap. On MT Bench, with
routers trained on Arena data plus judge-labelled data, the matrix-factorisation router reached half the gap
with 13.4% of calls to GPT-4 against 49.0% for random routing; the paper reports this as a cost saving of
about 3.66 times at 95% of GPT-4's MT Bench score. The same paper gives a caveat and a positive result:
on MMLU and GSM8K, routers trained only on Arena data were close to random until in-domain labelled data was
added; and the routers did transfer to other model pairs without retraining.

**Cascades** are the other shape. FrugalGPT names three strategies for cutting LLM cost (prompt
adaptation, LLM approximation and the LLM cascade) and studies the cascade: query models in order of cost
and stop when an answer is judged good enough. A cascade pays the cheap model on every query, so it wins
only when a reliable, cheap acceptance check exists.

```python
def expected_cost(hit_rate, strong_fraction, cost_strong, cost_weak, cost_lookup):
    """Mean cost per query, in your own units: every query pays the cache lookup, misses pay a model."""
    miss = 1 - hit_rate
    return cost_lookup + miss * (strong_fraction * cost_strong + (1 - strong_fraction) * cost_weak)

def cascade_cost(accept_rate, cost_weak, cost_strong):
    """Weak model on every query; escalate the ones its answer fails the check on."""
    return cost_weak + (1 - accept_rate) * cost_strong
```

**Worked numbers (illustrative units, from the check).** Strong call 100, weak call 5, lookup 0.5.
Everything to the strong model: 100 per query. A 20% cache hit rate and 30% of misses to the strong model:
`0.5 + 0.8 * (30 + 3.5) = 27.3`. A cascade whose check accepts 70% of weak answers: `5 + 0.3 * 100 = 35`.
Work these numbers in the interview with the candidate's own estimates of hit rate and routing share, and
then say how you would measure each one.

---

## 7. Pitfalls Checklist

1. **A threshold copied from a blog post** or a default, instead of calibrated on your labelled pairs with
   your embedding model.
2. **No scope in the key**: one tenant's answer served to another, or answers that outlive a system-prompt
   or model change.
3. **Caching personalised or time-sensitive answers** without a TTL ("my order status", "today's rate").
4. **Taking the first entry above the threshold** instead of the best one.
5. **Measuring hit rate and not precision.** A cache with a great hit rate and 5% wrong answers is a
   quality incident.
6. **Ignoring negation and entity swaps**: "flights to Delhi" and "flights from Delhi" can sit close in
   embedding space. Add them to your labelled set on purpose.
7. **A router trained on general chat data used for a specialised domain** without in-domain labels.
8. **Cascades without a reliable acceptance check**, which pay for both models and keep the weak answer.

---

## Drills

1. Why put an exact cache in front of a semantic one?
2. List five things that belong in a semantic cache's scope, and the failure each one prevents.
3. In `SemanticCache.get`, why purge expired entries before the similarity search?
4. Using the ten labelled pairs in §5, what threshold and served fraction does a target precision of 0.8 give?
5. Why is precision not monotone in the threshold? Construct a three-pair example.
6. Define call percentage, performance gap recovered and `CPT(50%)`.
7. With a 40% hit rate, 25% of misses to the strong model and the costs in §6, what is the mean cost per query?
8. When does a cascade cost more than always calling the strong model?

---

## Homework

1. Build an exact-plus-semantic cache in front of any model you can call. Log the similarity of every
   nearest neighbour for a week of your own queries (or a public question dataset), label 200 pairs, and
   run `calibrate_threshold` at precision targets 0.95 and 0.99.
2. Write twenty adversarial pairs (negations, swapped entities, different numbers) and measure how many your
   threshold serves.
3. Add byte-based eviction to `SemanticCache`: a budget in bytes of answer text instead of an entry count.
4. Read the RouteLLM paper's evaluation section and reproduce the definition of APGR from it in your own words.
5. Design question, aloud, in five minutes: "A support assistant costs too much. Walk me through cache,
   router and cascade, what you would measure first, and what could go wrong."

---

## Sources

All read 2026-11-26.

- Ong et al., *RouteLLM: Learning to Route LLMs with Preference Data* (2024), arxiv.org/abs/2406.18665 and the
  full text at arxiv.org/html/2406.18665. Source for the routing formulation, router types, call percentage, PGR,
  CPT, the MT Bench results, the MMLU/GSM8K caveat and transfer to other model pairs.
- Chen, Zaharia, Zou, *FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance*
  (2023), arxiv.org/abs/2305.05176 (abstract). Source for the three strategies and the cascade.
- GPTCache README, github.com/zilliztech/GPTCache. Source for the module list (embedding generator, cache
  storage, vector store, cache manager, similarity evaluator), the false-positive statement, entry-count eviction
  and the temperature behaviour.
- RedisVL user guide, *Semantic caching for LLMs*, docs.redisvl.com/en/latest/user_guide/03_llmcache.html. Source
  for cosine-distance thresholds, the "not a fixed quantity" guidance, TTL and per-user filter fields.
- Fu Bang, *GPTCache: An Open-Source Semantic Cache for LLM Applications* (NLP-OSS 2023),
  aclanthology.org/2023.nlposs-1.24 (abstract page only; the PDF could not be read).

## Further reading (not consulted)

The full GPTCache paper; vendor documentation for managed semantic caches; the literature on learned
cascades and model selection beyond FrugalGPT's abstract. None were read for this revision.

*Last reviewed: 2026-11-26.*
