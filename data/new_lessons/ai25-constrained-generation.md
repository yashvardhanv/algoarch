# Lesson 25 — Constrained Generation & Logits Guardrails

> **Priority:** ★★★★★ — "the downstream parser keeps crashing on model output; fix it properly."
>
> **Study time:** 60 minutes. **Do this after:** Lesson 07 (Context Engineering & Structured Output). You should know what a regular expression and a finite automaton are.
>
> **Level:** advanced. Optional for a crash plan; worth doing if your target loops include LLM platform or agent-tooling rounds.

Asking a model for "only valid JSON" is a request, not a guarantee. Constrained generation turns it
into a guarantee by changing the sampler, not the prompt: at every step, tokens that would break the
format get probability zero. This lesson builds that from scratch (a grammar as an automaton, an index
from automaton states to allowed tokens, and the masked sampling loop) and then covers what the
guarantee does *not* cover, which is where interviews go next.

---

## 1. Mental Model

> **The grammar is an automaton. Its current state decides which tokens are legal next. Set every other
> token's logit to minus infinity and renormalise. Every finished output is then in the language, by
> construction.**

What follows from it:

- **The work is in the index, not the mask.** Checking every vocabulary token against the grammar at every
  step costs `O(N)` per step for a vocabulary of `N`. Willard and Louf (the paper behind the Outlines library)
  precompute, for every automaton state, the set of tokens it accepts, so each step is a lookup.
- **Tokens are not characters.** One token can span several grammar symbols (`":"` or `","n":`), so the index
  walks each token's characters through the automaton.
- **"Valid" means syntactically valid.** A constraint guarantees shape, not truth. The value inside a valid
  field can still be wrong, and a run cut off by the token budget is a valid *prefix*, not a valid document.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "a hosted API, the output must match our JSON Schema" | the provider's strict structured-output mode, within its schema subset |
| "one of a fixed set of labels" | an enum constraint (the cheapest grammar there is) |
| "a regex-shaped field" (dates, ids, phone numbers) | a regex constraint compiled to an automaton |
| "nested or recursive structure" (JSON, SQL, a DSL) | a context-free grammar (a pushdown automaton or a parser) |
| "self-hosted model, we own the sampler" | a grammar-constrained decoding library in the serving stack |
| "accuracy dropped after we forced JSON" | measure free-form versus constrained; give reasoning room before the answer fields |
| "we must never emit a forbidden word or tool" | a logit mask from a deny-list, alongside output checks |

---

## 3. Masking, Precisely

Sampling picks token `t` with probability `softmax(logits)[t]`. Masking sets `logits[t] = -inf` for every
disallowed `t`, so `exp(-inf) = 0` and the rest renormalise. Relative odds among the allowed tokens do not
change.

```python
import math

def masked_softmax(logits, allowed):
    """Probabilities after setting every logit outside `allowed` to -inf. logits: {token: score}."""
    m = max(logits[t] for t in allowed)
    w = {t: math.exp(logits[t] - m) for t in allowed}
    z = sum(w.values())
    return {t: (w[t] / z if t in w else 0.0) for t in logits}
```

Masking is not the same as rejecting a bad sample and retrying, and the difference runs the opposite way
to what people expect. **Retry-until-valid is exact but can be slow:** it samples whole outputs from the
model and keeps the valid ones, so what you get is exactly `p(y | y is valid)`, at the cost of an expected
`1 / P(valid)` attempts. **Masking is fast but not exact at the sequence level:** it renormalises each step
separately, so a prefix keeps its full probability even when most of its continuations are invalid. Mass
moves towards prefixes that have few valid continuations.

**Worked example (illustrative, computed exactly by the check).** Two tokens, `a` and `b`, two steps, and
the grammar forbids `aa`. The model gives `p(a) = p(b) = 0.5` at step one, then `p(a | a) = 0.9`,
`p(b | a) = 0.1` and `p(a | b) = p(b | b) = 0.5`.

| Output | Model probability | `p(y \| valid)` (rejection sampling) | Per-step masking |
|---|---|---|---|
| `ab` | 0.05 | 0.091 | 0.5 |
| `ba` | 0.25 | 0.455 | 0.25 |
| `bb` | 0.25 | 0.455 | 0.25 |

Rejection sampling accepts 55% of tries, so it needs about 1.82 tries on average. Masking needs one pass,
but it makes `ab` (an output the model barely wanted) the most likely result. Masking guarantees the
format; it does not guarantee that you sample what the model would have said if it had stayed valid on
its own.

---

## 4. A Grammar as an Automaton

The running example is a tiny schema: objects like `{"label":"pos","n":12}`, with a label from an enum and
a non-negative integer without leading zeros. As a regular expression:
`\{"label":"(pos|neg)","n":(0|[1-9][0-9]*)\}`.

```python
class SegmentDFA:
    """A character-level DFA for a sequence of segments:
    ('lit', text)          exactly this text
    ('alt', [a, b, ...])   one of these strings (no option may be a prefix of another)
    ('int',)               0, or a non-zero digit followed by digits
    A state is (segment index, progress); (len(segments), None) means everything matched."""
    def __init__(self, segments):
        self.segs = segments
        self.start = self._enter(0)

    def _enter(self, i):
        if i == len(self.segs):
            return (i, None)
        kind = self.segs[i][0]
        return (i, 0) if kind == 'lit' else (i, '') if kind == 'alt' else (i, 'start')

    def step(self, state, ch):
        """Next state after reading ch, or None if ch is not allowed here."""
        i, prog = state
        if i == len(self.segs):
            return None
        seg = self.segs[i]
        if seg[0] == 'lit':
            if seg[1][prog] != ch:
                return None
            return self._enter(i + 1) if prog + 1 == len(seg[1]) else (i, prog + 1)
        if seg[0] == 'alt':
            p = prog + ch
            if p in seg[1]:
                return self._enter(i + 1)
            return (i, p) if any(o.startswith(p) for o in seg[1]) else None
        if prog == 'start':                              # 'int'
            return (i, 'zero') if ch == '0' else (i, 'digits') if ch in '123456789' else None
        if prog == 'digits' and ch in '0123456789':     # not str.isdigit(), which accepts '²' and '٣'
            return (i, 'digits')
        return self.step(self._enter(i + 1), ch)        # the number ended; ch must start the next segment

    def accepting(self, state):
        i, prog = state
        return i == len(self.segs) or (
            i == len(self.segs) - 1 and self.segs[i][0] == 'int' and prog in ('zero', 'digits'))

LABEL_SCHEMA = [('lit', '{"label":"'), ('alt', ['pos', 'neg']), ('lit', '","n":'), ('int',), ('lit', '}')]
```

Real libraries compile a regular expression or a JSON Schema into the same kind of automaton; this hand-built
one keeps the mechanism visible. Notice the `int` segment: after `0` the number is over (no leading zeros), and
after other digits a non-digit must start the next segment. That "the number ends when the next thing starts"
logic is exactly what a hand-written prompt cannot enforce.

---

## 5. From Characters to Tokens: the Index

```python
def walk(dfa, state, text):
    """Run a whole token's characters through the DFA; None if any character is rejected."""
    for ch in text:
        state = dfa.step(state, ch)
        if state is None:
            return None
    return state

def build_index(dfa, vocab):
    """index[state] = {token_id: next_state} for every reachable state, keeping only tokens after which the
    output can still be finished with this vocabulary. vocab: {token_id: text}, no empty texts."""
    index, frontier = {}, [dfa.start]
    while frontier:
        s = frontier.pop()
        if s in index:
            continue
        index[s] = {}
        for tok, text in vocab.items():
            t = walk(dfa, s, text)
            if t is not None:
                index[s][tok] = t
                frontier.append(t)
    live = {s for s in index if dfa.accepting(s)}        # states from which we can still finish
    changed = True
    while changed:
        changed = False
        for s, moves in index.items():
            if s not in live and any(t in live for t in moves.values()):
                live.add(s)
                changed = True
    return {s: {tok: t for tok, t in moves.items() if t in live} for s, moves in index.items() if s in live}
```

Two details matter:

1. **Walking whole tokens.** A token like `","n":` crosses three grammar symbols and two segments; it is legal
   only if every character is. The Willard and Louf paper does the same: it runs each vocabulary token through
   the automaton from each state and records where it lands.
2. **Pruning dead ends.** A token can be legal character-by-character and still lead to a state from which *this
   vocabulary* can never finish. With a vocabulary that has `po` but no `s`, `po` is a legal prefix of `pos`, yet
   choosing it strands the model. The second loop keeps only states that can still reach acceptance.

The index is built once per (grammar, tokenizer) pair, then reused for every request. This is consistent with
what OpenAI's structured-outputs guide says: the first request with a new schema has extra latency while the
schema is processed, and later requests with the same schema do not.

---

## 6. The Decoding Loop

```python
def allowed_tokens(index, dfa, state, eos):
    """Legal next tokens and their next states; end-of-sequence only where the grammar may stop."""
    moves = dict(index[state])
    if dfa.accepting(state):
        moves[eos] = None
    return moves

def constrained_decode(logits_fn, index, dfa, eos, max_tokens):
    """Greedy decoding under the grammar. logits_fn(prefix) -> {token: score} over the whole vocabulary.
    Returns (token ids, finished)."""
    if dfa.start not in index:
        raise ValueError("this tokenizer cannot produce any string of this grammar")
    state, out = dfa.start, []
    for _ in range(max_tokens):
        moves = allowed_tokens(index, dfa, state, eos)
        probs = masked_softmax(logits_fn(out), moves)
        tok = max(moves, key=lambda t: probs[t])
        if tok == eos:
            return out, True
        out.append(tok)
        state = moves[tok]
    return out, False        # the budget ran out: a valid prefix, not a valid document
```

The check runs this with random "models" (random logits at every step) over random vocabularies that include
multi-symbol tokens, and confirms that every finished output matches the regular expression above, that every
prefix is extendable, and that the masked probabilities equal the original ones renormalised over the legal set.

**Illustrative numbers from the check.** With the 27-token toy vocabulary in the check script, the index has 19
live states, and the largest number of legal tokens in any state is 7: at most states most of the vocabulary is
masked. Real vocabularies have tens of thousands of tokens, which is why precomputing the index matters.

---

## 7. Beyond Regular Languages

A finite automaton cannot count brackets, so it cannot describe arbitrary nesting. For JSON with nested objects,
SQL or a programming language you need a context-free grammar, and a stack:

- Willard and Louf extend the index idea to LALR(1) parsers (pushdown automata); because the legal next tokens
  depend on the stack, the index becomes more complex than a state-to-set map.
- XGrammar (Dong et al.) splits the vocabulary into *context-independent* tokens, whose legality can be checked
  ahead of time, and *context-dependent* tokens, checked at runtime against the stack, and overlaps grammar work
  with GPU execution. Its authors report up to 100 times speed-up over existing solutions.

You do not need to implement either in an interview. You need to say: regular constraints compile to an automaton
and a precomputed token index; recursive constraints need a stack, and the engineering problem is keeping the
per-step check off the critical path.

---

## 8. What a Hosted API Gives You

OpenAI's structured-outputs guide is a representative example of a hosted constrained mode. In it:

- Strict structured outputs keep completed, non-refusal output within your JSON Schema; plain JSON mode only
  guarantees valid JSON, not schema adherence.
- The schema must be a supported subset: every field listed as `required`, `additionalProperties: false` on every
  object, the root an object (not `anyOf`), and limits on total properties (5,000), nesting depth (10) and enum
  sizes. Composition keywords such as `allOf`, `not` and `if`/`then`/`else` are not supported. Optional fields are
  emulated with a union with `null`.
- A **refusal** comes back in a separate field and need not match your schema.
- An output cut off by the token limit is **incomplete**, and the guide's examples treat it as an error.
- Business rules the schema cannot express still need validation in your code.

Each of those is a failure mode the "it's guaranteed" answer misses. Name them.

**Does forcing a format cost accuracy?** Tam et al. (*Let Me Speak Freely?*, 2024) report a significant decline in
reasoning ability under format restrictions, with stricter formats generally hurting more. The practical answer is
to measure your own task both ways, and when reasoning matters, give the model room before the answer: a reasoning
field placed before the answer fields, or a free-form step followed by a constrained formatting step. Treat both as
designs to test, not as settled fixes.

---

## 9. Pitfalls Checklist

1. **"Guaranteed valid" with no mention of truncation**: a budget cut-off yields a valid prefix that does not parse.
2. **Confusing JSON mode with schema adherence.** Valid JSON with the wrong keys still breaks the consumer.
3. **Masking characters instead of tokens**, or checking only a token's first character.
4. **Not pruning dead ends**, so the model can pick a legal prefix it can never finish.
5. **Allowing end-of-sequence in a non-accepting state**, or forbidding it in an accepting one.
6. **Rebuilding the index per request** instead of caching it per grammar and tokenizer.
7. **Treating shape as truth**: a constrained `"n": 7` is a well-formed lie if the right value was 9. Validate semantics.
8. **Forcing a rigid format on a reasoning task without measuring** the accuracy cost.

---

## Drills

1. Why does masking with minus infinity keep the relative odds of the allowed tokens unchanged?
2. In `SegmentDFA`, trace the states for the text `{"label":"neg","n":40}`. Where does the `int` segment end?
3. Why must the index walk every character of a multi-character token, not just its first?
4. With a vocabulary containing `po` and `pos` but no `s`, which one does `build_index` keep at the state after `{"label":"`, and why?
5. Where may `allowed_tokens` include end-of-sequence in the toy grammar?
6. What does `constrained_decode` return when `max_tokens` is too small, and what should the caller do with it?
7. Name four ways a hosted "structured output" call can still give your code something it cannot use.
8. Why does nesting need a stack, and what does XGrammar precompute to keep that cheap?

---

## Homework

1. Add an `('enum_int', lo, hi)` segment that accepts only integers in a range, and extend the check with a
   brute-force reference over all strings up to the range's length.
2. Extend `SegmentDFA` with an optional whitespace segment and show which multi-character tokens become legal.
3. Write a JSON Schema for a support-ticket triage result that fits the hosted subset in §8, including an optional
   field emulated with `null`.
4. Take ten reasoning questions you can grade. Answer them free-form and with a strict JSON answer field, with and
   without a preceding reasoning field. Report all three accuracies.
5. Read section 3 of the Willard and Louf paper (including 3.2, the comparison with current methods) and explain, aloud, how their index differs from per-step masking.

---

## Sources

All read 2026-11-26.

- Willard and Louf, *Efficient Guided Generation for Large Language Models* (2023), arxiv.org/html/2307.09702.
  Source for the `O(N)` per-step cost of naive masking, the regex-to-automaton framing, the precomputed
  state-to-token index, walking multi-character tokens, and the extension to LALR(1) parsers.
- Dong et al., *XGrammar: Flexible and Efficient Structured Generation Engine for Large Language Models* (2024),
  arxiv.org/abs/2411.15100 (abstract). Source for context-independent and context-dependent tokens, overlapping
  grammar work with GPU execution, and the reported speed-up.
- OpenAI, *Structured Outputs* guide, developers.openai.com/api/docs/guides/structured-outputs. Source for strict mode
  versus JSON mode, the schema subset and limits, refusals, incomplete outputs and first-request latency.
- Tam et al., *Let Me Speak Freely? A Study on the Impact of Format Restrictions on Performance of Large Language
  Models* (2024), arxiv.org/abs/2408.02442 (abstract). Source for the reported reasoning decline under format restrictions.

## Further reading (not consulted)

The Outlines, Guidance, llama.cpp grammar (GBNF) and XGrammar documentation; the full XGrammar and *Let Me Speak
Freely?* papers. None were read for this revision.

*Last reviewed: 2026-11-26.*
