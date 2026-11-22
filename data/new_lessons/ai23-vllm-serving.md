# Lesson 23 — High-Throughput LLM Serving: vLLM & PagedAttention

> **Priority:** ★★★★★ (OpenAI, Anthropic, Databricks, Meta GenAI, AI Unicorns)  
> **Estimated Study Time:** 60 minutes  
> **Key Skills:** Continuous (dynamic) batching vs static batching, PagedAttention memory fragmentation fix, KV Cache allocation math, Speculative Decoding with draft models, TTFT vs ITL metrics.

---

## 1. The GPU Memory Wall in LLM Inference

In transformer inference (autoregressive generation), generating each new token requires attending to all prior tokens' Key and Value vectors.
- **The KV Cache Memory Equation:**
  `KV_Cache_Size = 2 * n_layers * n_heads * head_dim * context_length * precision_bytes`
  For LLaMA-3-70B with 4k context in FP16: A single request requires **~2.6 GB** of GPU VRAM purely for its KV cache!
- **The Fragmentation Problem:** Traditional serving frameworks allocate contiguous VRAM buffers for the *maximum possible* sequence length (e.g. 4096 tokens). If a request only generates 120 tokens, **97% of the reserved VRAM is wasted**, choking GPU concurrency down to batch size 4!

---

## 2. PagedAttention Architecture (vLLM Innovation)

Inspired by OS virtual memory and page tables:
- KV Cache is partitioned into non-contiguous fixed-size blocks (e.g., 16 tokens per block).
- A **Block Table** maps logical token sequences to physical GPU memory pages.
- Memory waste is reduced to the tail fraction of the final block (< 4%), increasing GPU throughput by **3.5x to 4x** on identical hardware!

```
Logical KV Cache:   [Block 0 (0-15)] ───► [Block 1 (16-31)] ───► [Block 2 (32-47)]
                          │                     │                     │
Block Table Mapping:      │ (Page #7)           │ (Page #2)           │ (Page #9)
                          ▼                     ▼                     ▼
Physical GPU VRAM:   [Page #2: B1] ... [Page #7: B0] ... [Page #9: B2]
```

---

## 3. Serving Metrics: TTFT vs ITL

When designing and benching LLM platforms, never talk about "average latency". Senior AI engineers monitor two distinct metrics:
1. **Time to First Token (TTFT):** The time from request arrival until the first token streams out. Dominated by the **Prefill Phase** (compute-bound, processing all prompt tokens simultaneously in parallel).
2. **Inter-Token Latency (ITL):** The time between successive generated tokens. Dominated by the **Decode Phase** (memory-bandwidth bound, sequentially loading 70B weights for every single token).

---

## 4. Speculative Decoding (Draft + Target Models)

How to accelerate the memory-bound Decode phase:
1. A tiny, ultra-fast draft model (e.g. LLaMA-3-8B) speculatively generates `K = 5` tokens quickly.
2. The large target model (LLaMA-3-70B) evaluates all `K` tokens in a **single forward prefill pass** in parallel.
3. If the first 3 tokens match the target model's probability distribution, all 3 are accepted simultaneously!
4. **Result:** 2x - 3x latency reduction with zero loss in output quality (mathematically identical distribution).
