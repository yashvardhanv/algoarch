# Lesson 23 — High-Throughput LLM Serving: vLLM, PagedAttention, KV Cache, FlashAttention, Speculative Decoding

> **Priority:** ★★★★★ — the serving round: "why is my GPU idle while users wait?"
>
> **Study time:** 75 minutes. **Do this after:** Lesson 09 (Model Behaviour & Prefix Caching). You should be able to write attention for one query by hand.
>
> **Level:** advanced. Optional for a crash plan; worth doing if your target loops include inference or platform rounds.

Serving a large model is a memory problem first and a compute problem second. Every request drags
a growing key-value (KV) cache behind it, generation emits one token per forward pass, and the
number of requests you can batch is set by how much KV memory is left after the weights. This lesson
gives you the four mechanisms an interviewer expects you to explain from first principles: the KV
cache and its size, paged KV memory (PagedAttention, vLLM), IO-aware attention (FlashAttention), and
speculative decoding. Each comes with code you can run and the arithmetic to back it.

---

## 1. Mental Model

> **Decoding is limited by moving bytes, not by doing arithmetic. Every technique here either stores
> fewer bytes (paging, sharing), moves fewer bytes (FlashAttention), or gets more tokens out of each
> pass over the weights (batching, speculative decoding).**

What follows from it:

- **Two phases.** The prompt (prefill) phase processes all prompt tokens in parallel and keeps the
  GPU busy. The generation (decode) phase produces one token at a time; the vLLM paper describes it
  as underusing GPU compute and memory-bound. Time to first token (TTFT) is mostly prefill;
  the gap between later tokens (inter-token latency, ITL) is mostly decode.
- **Batch size is the throughput lever in decode**, because one pass over the weights serves every
  sequence in the batch. Batch size is capped by KV memory. So KV memory management *is* throughput.
- **None of the four techniques changes the output.** Paging and FlashAttention compute exact
  attention; speculative sampling provably keeps the target model's distribution. Say this
  unprompted: it is the difference between an optimisation and a quality trade.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "GPU memory is full but utilisation is low", "batch size stuck at a handful" | KV cache sizing, then paged KV blocks |
| "new requests wait for the whole batch to finish" | iteration-level (continuous) batching |
| "many requests share a long system prompt" or "n samples per prompt" | block sharing with reference counts and copy-on-write |
| "out of KV memory mid-generation" | preemption: swap the sequence's blocks to CPU or drop and recompute |
| "attention is slow or OOMs at long context during training or prefill" | FlashAttention (tiling plus online softmax) |
| "single-user latency is too high, the GPU has spare compute" | speculative decoding with a small draft model |
| "the KV cache per token is too big" | fewer KV heads (multi-query or grouped-query attention), lower precision |

---

## 3. The KV Cache, and How Big It Is

At each layer, attention needs the keys and values of every earlier token. Recomputing them per
step would redo the whole prefix, so the server stores them: that store is the KV cache. Per token,
per layer, you keep one key vector and one value vector.

```python
def kv_cache_bytes(n_tokens, n_layers, kv_width, bytes_per_value=2):
    """KV cache size in bytes. kv_width = (number of KV heads) * head_dim; for standard multi-head
    attention that equals the hidden size. bytes_per_value = 2 for FP16/BF16."""
    return 2 * n_layers * kv_width * bytes_per_value * n_tokens   # 2 = one key + one value
```

**Worked number (from the vLLM paper).** For OPT-13B the paper uses hidden size 5120 and 40 layers
in FP16, so one token costs `2 * 40 * 5120 * 2 = 819,200` bytes, which is 800 KiB. A full 2,048-token
sequence is `1,677,721,600` bytes, about 1.6 GB. The check script reproduces both numbers.

**What that means for batch size (illustrative).** Suppose 12 GB of the GPU is left for KV after
the weights. That holds `12e9 // 819,200 = 14,648` tokens, about seven full-length sequences. The
paper reports that on a 40 GB A100 serving a 13B model, about 65% of memory holds the weights and
close to 30% holds request state, so this is the right order of magnitude to reason about.

**Levers on the formula.** Fewer KV heads shrink `kv_width`: multi-query attention keeps a single KV
head, and grouped-query attention keeps a number between one and the number of query heads (the GQA
paper). Lower precision shrinks `bytes_per_value`. Shorter context shrinks `n_tokens`. Nothing else
in the formula moves.

---

## 4. Why Contiguous Allocation Wastes Memory

Before paging, systems reserved one contiguous buffer per request sized for the maximum possible
length, because the final length is unknown. The vLLM paper names three kinds of waste:

1. **Reserved slots** for tokens not yet generated, held for the request's whole lifetime.
2. **Internal fragmentation**: slots reserved for a maximum length the request never reaches.
3. **External fragmentation**: gaps between buffers of different sizes left by the allocator.

The paper measured that existing systems used only 20.4% to 38.2% of KV memory for actual token
states.

```python
def reserved_vs_used(lengths, max_len, block_size):
    """Token slots used, reserved by max-length preallocation, and reserved by paging,
    for sequences that finished at the given lengths."""
    used = sum(lengths)
    contiguous = len(lengths) * max_len
    paged = sum(-(-n // block_size) * block_size for n in lengths)   # round each up to whole blocks
    return used, contiguous, paged
```

Illustrative run: four requests finishing at 120, 900, 300 and 2,048 tokens, a 2,048 maximum and
16-token blocks. Used: 3,368 slots. Contiguous reservation: 8,192 slots (41% used). Paged: 3,392
slots (99% used). Paging wastes at most one partly filled block per sequence.

---

## 5. PagedAttention: The KV Cache as Virtual Memory

> **Split each sequence's KV cache into fixed-size blocks of `B` tokens. A per-sequence block table
> maps logical block `i` to any free physical block. Allocate a block only when the previous one is
> full. Share blocks between sequences with reference counts; copy a shared block only when someone
> writes to it.**

That is paging from operating systems: tokens are bytes, blocks are pages, the block table is the page
table, and copy-on-write is the same trick `fork()` uses. The vLLM default block size is 16 tokens.

Visual (planned): two sequences' logical blocks pointing through block tables to scattered physical
blocks, with a shared prompt block showing reference count 2.

The simulation below stores token ids in place of real key and value tensors, so the check can
confirm that every sequence reads back exactly what it wrote.

```python
class BlockAllocator:
    """A pool of fixed-size physical KV blocks with reference counts."""
    def __init__(self, num_blocks, block_size):
        self.block_size = block_size
        self.free = list(range(num_blocks - 1, -1, -1))   # pop() hands out block 0 first
        self.ref = [0] * num_blocks
        self.data = [[] for _ in range(num_blocks)]       # stands in for the K and V tensors

    def alloc(self):
        if not self.free:
            raise MemoryError("out of KV blocks: preempt a sequence")
        b = self.free.pop()
        self.ref[b] = 1
        self.data[b] = []
        return b

    def release(self, b):
        self.ref[b] -= 1
        if self.ref[b] == 0:
            self.free.append(b)


class Sequence:
    """One sequence's view of the KV cache: a block table plus a length."""
    def __init__(self, alloc):
        self.alloc = alloc
        self.table = []      # logical block i -> physical block id
        self.length = 0      # tokens stored

    def append(self, token):
        a = self.alloc
        if self.length % a.block_size == 0:      # no block yet, or the last one is full
            self.table.append(a.alloc())         # allocate on demand, one block at a time
        last = self.table[-1]
        if a.ref[last] > 1:                      # shared with another sequence: copy on write
            new = a.alloc()
            a.data[new] = list(a.data[last])
            a.release(last)
            self.table[-1] = new
            last = new
        a.data[last].append(token)
        self.length += 1

    def fork(self):
        """A new sequence sharing every block (parallel sampling, beam search, a shared prefix)."""
        child = Sequence(self.alloc)
        child.table = list(self.table)
        child.length = self.length
        for b in self.table:
            self.alloc.ref[b] += 1
        return child

    def tokens(self):
        out = []
        for b in self.table:
            out.extend(self.alloc.data[b])
        return out

    def free(self):
        for b in self.table:
            self.alloc.release(b)
        self.table, self.length = [], 0
```

**Why only the last block needs copy-on-write.** Full blocks are never written again, so sharing
them is free forever. Only the partly filled tail can be written, so only the tail is ever copied.
Two samples from the same 1,000-token prompt share every full prompt block and diverge only from
the tail on.

**What the paper measured from sharing (OPT-13B).** Memory savings of 6.1% to 9.8% for parallel
sampling and 37.6% to 55.2% for beam search on the Alpaca trace; 16.2% to 30.5% and 44.3% to 66.3% on
ShareGPT. The headline end-to-end result is 2 to 4 times the throughput of FasterTransformer and Orca
at the same latency, with larger gains for longer sequences, larger models and more complex decoding.

**Block size is a trade.** Small blocks waste less at the tail but mean more, smaller transfers and
more table entries. The paper found 16 to 128 performed best on ShareGPT, while on Alpaca's short
sequences 16 and 32 were good and larger blocks hurt.

**When blocks run out: preemption.** vLLM evicts whole sequences (all or none of a sequence's
blocks), latest arrivals first, and either **swaps** the blocks to CPU memory or **drops and
recomputes** them later by running the prompt plus the generated tokens as one prefill. In the paper's
microbenchmark, recomputation's overhead never exceeded 20% of swapping's latency, and swapping
suffers at small block sizes because of many small transfers.

---

## 6. Iteration-Level (Continuous) Batching

Request-level batching runs a batch until its longest member finishes, so a new arrival waits for the
slowest request, and finished slots sit idle. Iteration-level scheduling (introduced by Orca, used by
vLLM) re-forms the batch after every decode step: finished sequences leave, waiting ones join, and a
new request waits at most one iteration, if there is memory for it (otherwise it queues, and §5's
preemption decides who gives way). Paged KV memory is what makes this cheap, because a joining sequence
needs only the blocks its prompt fills, not a contiguous max-length buffer.

---

## 7. FlashAttention: Exact Attention With Less Memory Traffic

Standard attention writes the `N x N` score matrix to GPU high-bandwidth memory (HBM), reads it back for
softmax, writes the probabilities, and reads them again to multiply by `V`. FlashAttention keeps tiles of
`Q`, `K` and `V` in fast on-chip SRAM, fuses the steps into one kernel, and never writes the full matrix.
The paper's stated goal is to avoid reading and writing the attention matrix to and from HBM.

The obstacle is softmax: its denominator needs every score in the row. The fix is the **online
softmax**: keep a running maximum `m`, a running denominator `l` and an unnormalised output, and rescale
them whenever a new tile raises the maximum.

```python
import math

def attention_naive(q, keys, values):
    """softmax(q . k) weighted sum of values, for one query. (The 1/sqrt(d) scale is folded into q.)"""
    scores = [sum(a * b for a, b in zip(q, k)) for k in keys]
    m = max(scores)
    w = [math.exp(s - m) for s in scores]
    total = sum(w)
    return [sum(wi * v[j] for wi, v in zip(w, values)) / total for j in range(len(values[0]))]

def attention_tiled(q, keys, values, tile):
    """Same result, one tile of keys at a time, holding only m, l and an unnormalised output."""
    m, l = float('-inf'), 0.0
    acc = [0.0] * len(values[0])
    for start in range(0, len(keys), tile):
        ks, vs = keys[start:start + tile], values[start:start + tile]
        scores = [sum(a * b for a, b in zip(q, k)) for k in ks]
        m_new = max(m, max(scores))
        scale = math.exp(m - m_new)           # old terms were exp(s - m); make them exp(s - m_new)
        l *= scale
        acc = [x * scale for x in acc]
        for s, v in zip(scores, vs):
            w = math.exp(s - m_new)
            l += w
            acc = [x + w * vj for x, vj in zip(acc, v)]
        m = m_new
    return [x / l for x in acc]
```

What the paper establishes, in the terms you should repeat:

- **Exact, not approximate.** Its Theorem 1 states the algorithm returns `softmax(QK^T)V` with `O(N)`
  extra memory. (Its block-sparse variant is the approximate one.)
- **Fewer HBM accesses.** Standard attention needs `Θ(Nd + N²)` HBM accesses; FlashAttention needs
  `Θ(N²d²/M)` for SRAM size `M`, and the paper proves no exact algorithm does asymptotically better
  across that range of `M`.
- **Backward pass recomputes.** It stores only the output and the `(m, l)` statistics, and recomputes
  attention tiles in SRAM during backward: more FLOPs, fewer bytes moved, faster overall.
- **Measured results** include about 15% faster BERT-large training than the MLPerf 1.1 record
  implementation, GPT-2 small trained in 2.7 days against 9.5 days for the HuggingFace implementation
  (the paper's Table 2), and an average 2.4 times speed-up on Long Range Arena.

> **Interview framing.** FlashAttention does not reduce FLOPs; it reduces memory traffic, which is the
> bottleneck. If someone says "it approximates attention", correct them.

---

## 8. Speculative Decoding

> **A small draft model guesses `γ` tokens; the large target model scores all of them in one parallel
> pass; a rejection rule keeps a prefix of the guesses and fixes the first miss, so the output has
> exactly the target model's distribution.**

The rule for each draft token `x`, where `p` is the target's distribution and `q` the draft's
(Leviathan et al.; Chen et al. give the same scheme as speculative sampling):

1. Accept `x` with probability `min(1, p(x) / q(x))`.
2. On rejection, sample a replacement from `norm(max(0, p - q))` and stop.
3. If all `γ` are accepted, sample one more token from the target's next distribution, which the
   parallel pass computed anyway.

```python
import random

def sample(dist, rand):
    """Draw a token from {token: prob} with one uniform number from rand()."""
    u, cum = rand(), 0.0
    for tok, pr in dist.items():
        cum += pr
        if u < cum:
            return tok
    return tok                                # floating-point leftover goes to the last token

def residual(p, q):
    """norm(max(0, p - q)): the mass the target wants that the draft under-proposed."""
    r = {t: max(0.0, p.get(t, 0.0) - q.get(t, 0.0)) for t in p}
    z = sum(r.values())
    return {t: v / z for t, v in r.items()}

def speculative_step(p_rows, q_rows, drafts, rand=random.random):
    """p_rows: gamma + 1 target distributions; q_rows: gamma draft distributions; drafts: the gamma
    draft tokens. Returns the tokens emitted by this step (between 1 and gamma + 1)."""
    out = []
    for i, x in enumerate(drafts):
        p, q = p_rows[i], q_rows[i]
        if rand() < min(1.0, p.get(x, 0.0) / q[x]):
            out.append(x)
        else:
            out.append(sample(residual(p, q), rand))
            return out
    out.append(sample(p_rows[len(drafts)], rand))
    return out

def acceptance_rate(p, q):
    """alpha = sum over tokens of min(p, q)."""
    return sum(min(p.get(t, 0.0), q.get(t, 0.0)) for t in set(p) | set(q))

def expected_tokens(alpha, gamma):
    """Expected tokens per target pass, if each draft is accepted independently with rate alpha."""
    return (1 - alpha ** (gamma + 1)) / (1 - alpha)

def walltime_factor(alpha, gamma, c):
    """Expected speed-up when one draft pass costs c target passes (Leviathan et al.)."""
    return expected_tokens(alpha, gamma) / (gamma * c + 1)
```

**Why the distribution is exact.** A token `y` comes out either as an accepted draft, with probability
`q(y) * min(1, p(y)/q(y)) = min(p(y), q(y))`, or as a replacement, with probability
`(1 - α) * residual(y) = p(y) - min(p(y), q(y))`. The two add to `p(y)`. The check confirms this exactly
for random distributions and by simulation for the full multi-token step.

**Worked numbers (illustrative, produced by the check).** Target `p = {the: 0.5, a: 0.3, cat: 0.2}`,
draft `q = {the: 0.7, a: 0.1, cat: 0.2}`. Then `α = 0.5 + 0.1 + 0.2 = 0.8`. With `γ = 4`, the expected
tokens per target pass is `(1 - 0.8^5) / 0.2 ≈ 3.36`; if a draft pass costs `c = 0.05` of a target pass,
the expected speed-up is `3.36 / 1.2 ≈ 2.80`. With `γ = 8` it is about `4.33` tokens and `3.09`
times. Raising `γ` has diminishing returns, and the paper notes a gain is only guaranteed when
`α > c`.

**Reported results:** Leviathan et al. report 2 to 3 times faster than a standard T5X implementation
on T5-XXL with identical outputs; Chen et al. report a 2 to 2.5 times decoding speed-up on the 70B
Chinchilla model in a distributed setup.

**When it does not help.** Leviathan et al.'s analysis assumes spare compute for the parallel
target pass. At large batch sizes the GPU is no longer idle in decode, so the "free"
parallel verification is no longer free. It is a latency tool for lightly loaded or latency-critical
serving, not a throughput tool for a saturated cluster. That follows from the mental model; treat any
specific crossover batch size as something you would measure.

---

## 9. Pitfalls Checklist

1. **Forgetting the factor of 2** (keys *and* values) or the layer count in the KV formula.
2. **Using the hidden size as `kv_width` for a grouped-query model**: with fewer KV heads the cache is
   proportionally smaller.
3. **Calling paging a compression trick.** It stores the same bytes; it stops reserving bytes nobody
   uses.
4. **Copy-on-write on every block**, instead of only the shared, partly filled tail.
5. **Saying FlashAttention is approximate**, or that it saves FLOPs. It is exact and saves memory
   traffic.
6. **Online softmax without rescaling** the running sum and output when the maximum rises.
7. **Speculative decoding as "accept if the tokens match"** (that is only the greedy special case),
   or resampling from `p` instead of `norm(max(0, p - q))` after a rejection, which biases the output.
8. **Claiming a speed-up number without the conditions**: acceptance rate, draft cost, batch size.

---

## Drills

1. Compute the KV cache for one token of a model with 32 layers, 8 KV heads, head dimension 128, in FP16.
2. Why is the decode phase memory-bound while prefill is not?
3. Name the three kinds of KV memory waste in contiguous allocation. Which one does paging leave, and how big can it get?
4. Two beams share a 40-token prefix with block size 16. How many physical blocks do they share, and what happens when one writes token 41?
5. What does iteration-level batching change for a request that arrives while a long request is generating?
6. In the tiled attention, what must happen to `l` and `acc` when a tile has a score larger than the running maximum, and why?
7. Prove in two lines that speculative sampling emits token `y` with probability `p(y)`.
8. With `α = 0.6`, `γ = 3` and `c = 0.1`, what is the expected speed-up? Is a larger `γ` better?

---

## Homework

1. Extend the `BlockAllocator` with all-or-nothing preemption: when `alloc` fails, evict the most
   recently arrived sequence group, record its tokens, and re-admit it later by recomputation. Test that
   every sequence still reads back its tokens.
2. Add a prefix cache: map a hash of each full block's token ids (and its prefix) to a physical block, so
   a new request with the same system prompt reuses blocks. Count the blocks saved for 100 requests
   sharing a 500-token prompt.
3. Run `attention_tiled` with tile sizes 1, 7 and `N`, and show the output matches `attention_naive`
   to `1e-9`. Then remove the rescale and watch it fail.
4. Simulate speculative decoding with a toy bigram target and a smoothed draft. Measure tokens per target
   pass against `expected_tokens`, then vary how close the draft is to the target.
5. Read sections 3 and 4 of the vLLM paper and section 3 of the FlashAttention paper, then explain each
   mechanism aloud in under two minutes.

---

## Sources

All read 2026-11-26.

- Kwon et al., *Efficient Memory Management for Large Language Model Serving with PagedAttention*
  (SOSP 2023), arxiv.org/abs/2309.06180 and the full text at arxiv.org/html/2309.06180. Source for the
  OPT-13B KV size, the 20.4% to 38.2% utilisation, the waste types, blocks and block tables,
  copy-on-write, sharing savings, the 2 to 4 times throughput result, block-size findings, preemption,
  the memory split on an A100 40GB, the prefill/decode characterisation and iteration-level scheduling.
- Dao et al., *FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness* (2022),
  arxiv.org/html/2205.14135 (first part of the full text). Source for tiling, online softmax statistics,
  recomputation, Theorems 1 and 2, the lower bound and the reported speed-ups.
- Leviathan, Kalman, Matias, *Fast Inference from Transformers via Speculative Decoding* (ICML 2023),
  arxiv.org/abs/2211.17192 and arxiv.org/html/2211.17192. Source for the acceptance rule, the residual
  distribution, `α`, the expected-tokens and walltime formulas, and the T5-XXL result.
- Chen et al., *Accelerating Large Language Model Decoding with Speculative Sampling* (2023),
  arxiv.org/abs/2302.01318 (abstract). Source for the Chinchilla result.
- Ainslie et al., *GQA: Training Generalized Multi-Query Transformer Models from Multi-Head Checkpoints*
  (2023), arxiv.org/abs/2305.13245 (abstract). Source for multi-query and grouped-query KV heads.

## Further reading (not consulted)

FlashAttention-2 and FlashAttention-3 (later kernels with better work partitioning); the Orca paper
(OSDI 2022), which introduced iteration-level scheduling; the vLLM documentation; Medusa and EAGLE
(draft heads instead of a separate draft model). None were read for this revision, and no claim above
relies on them.

*Last reviewed: 2026-11-26.*
