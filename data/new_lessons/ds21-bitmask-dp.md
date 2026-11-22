# Lesson 21 — Bitmask Dynamic Programming & State Compression

> **Priority:** ★★★★☆ (Signature Google Hard & Meta E5 Algorithmic Problem)  
> **Estimated Study Time:** 50 minutes  
> **Key Skills:** State compression into 32-bit integers, Traveling Salesperson Problem (TSP), Submask iteration in O(3^n), Assignment problem.

---

## 1. Mental Model & Constraint Recognition

When the constraint on an interview problem states **`N <= 20`**, this is an unambiguous signal:
- `O(2^N)` is `~1,048,576` operations (completely feasible inside 10^7 Python ops budget).
- `O(N!)` (brute force permutations) is `2.4 * 10^18` (instantly times out).
- **Bitmask DP** allows you to represent whether each element in an `N`-element set has been visited as a single integer where the `k`-th bit is `1` (visited) or `0` (unvisited).

### Essential Bitwise Idioms
```python
mask | (1 << k)    # Turn on k-th bit (mark visited)
mask & ~(1 << k)   # Turn off k-th bit
(mask >> k) & 1    # Check if k-th bit is set
bin(mask).count('1') # Count number of set bits (popcount)
mask = (1 << n) - 1 # Full mask (all N items selected)
```

---

## 2. Classic Problem: Shortest Path Visiting All Nodes (TSP)

```python
from functools import lru_cache

def shortestPathLength(graph: list[list[int]]) -> int:
    """
    Finds the shortest path that visits every node in an unweighted graph.
    Uses BFS with state: (current_node, visited_bitmask).
    """
    from collections import deque
    n = len(graph)
    target_mask = (1 << n) - 1
    
    # queue contains: (node, mask, distance)
    queue = deque((i, 1 << i, 0) for i in range(n))
    visited = {(i, 1 << i) for i in range(n)}
    
    while queue:
        u, mask, dist = queue.popleft()
        if mask == target_mask:
            return dist
        
        for v in graph[u]:
            next_mask = mask | (1 << v)
            if (v, next_mask) not in visited:
                visited.add((v, next_mask))
                queue.append((v, next_mask, dist + 1))
                
    return 0
```

---

## 3. Submask Iteration in `O(3^N)`

When dividing a set into subsets, iterating through all submasks of a mask efficiently:
```python
submask = mask
while submask > 0:
    # Process submask
    submask = (submask - 1) & mask  # Magic line: jumps to next lower submask
```
Iterating over all submasks of all masks runs in `O(3^N)`, NOT `O(4^N)`. Proving this using the Binomial Theorem (`sum of C(n, k) * 2^k = (1 + 2)^n = 3^n`) is an instant L5 strong hire marker.
