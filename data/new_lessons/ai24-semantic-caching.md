# Lesson 24 — Semantic Vector Caching & Prompt Routing

> **Priority:** ★★★★★ (Critical for AI Cost Engineering & Latency at Scale)  
> **Estimated Study Time:** 50 minutes  
> **Key Skills:** Exact vs Semantic Vector Caching, Cosine Similarity Thresholds, Embedding Drift, Dynamic Model Tiering (Small SLM vs Large Frontier LLM), Pareto Frontier.

---

## 1. Why Standard Exact Matching Fails for GenAI

In traditional web apps, caching uses exact string or hash keys (`Redis.get("query_string")`).
- User 1: *"How do I reverse a linked list in Python?"*
- User 2: *"Python code to reverse singly linked list"*
- Both have identical intent and need the same output, but exact string hashing yields a **cache miss**, triggering another costly \$0.03 frontier model generation.
- **Semantic Vector Caching** embeds the query with a fast embedding model (e.g. `bge-small-en-v1.5`), searches a local vector index (Redis Vector Store / Qdrant), and returns the cached completion if cosine similarity > threshold (e.g., 0.94).

---

## 2. Production Python Architecture: Semantic Cache Pipeline

```python
import numpy as np
from typing import Optional

class SemanticCache:
    def __init__(self, similarity_threshold: float = 0.94):
        self.threshold = similarity_threshold
        # In production: Redis Vector Search or Milvus
        self.cache_entries = [] # List of tuples: (query_embedding, completion)

    def get(self, query_emb: np.ndarray) -> Optional[str]:
        if not self.cache_entries:
            return None
        
        # Vectorized cosine similarity
        best_sim = -1.0
        best_completion = None
        
        for cached_emb, completion in self.cache_entries:
            # Assume embeddings are L2 normalized
            sim = float(np.dot(query_emb, cached_emb))
            if sim > best_sim:
                best_sim = sim
                best_completion = completion
                
        if best_sim >= self.threshold:
            return best_completion  # Cache HIT: 5ms response, $0 cost
        return None  # Cache MISS: Forward to LLM

    def put(self, query_emb: np.ndarray, completion: str):
        self.cache_entries.append((query_emb, completion))
```

---

## 3. Dynamic Model Tiering (Cost vs Accuracy Routing)

Not all user queries need an expensive \$20/1M token Frontier model:
1. **Tier 1 (Classifier / SLM 8B):** Classifies incoming prompt complexity into `Simple Query`, `Factual Lookup`, or `Complex Reasoning / Code`.
2. **Simple / Conversational:** Answered by fast 8B model or cached entry (cost: \$0.05 / 1M tokens, latency: 150ms).
3. **Complex Reasoning / Multi-Step Code:** Routed to Frontier model (e.g. Claude 3.5 Sonnet / GPT-4o).
- **Impact:** 70% reduction in monthly API spend while maintaining identical user satisfaction benchmarks.
