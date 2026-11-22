# Lesson 20 — Segment Trees & Fenwick Trees (Binary Indexed Trees)

> **Priority:** ★★★★★ (The algorithmic bar at Google, Uber, Citadel, Atlassian)  
> **Estimated Study Time:** 65 minutes  
> **Key Skills:** Point updates, Range sum/min/max in O(log n), Lazy Propagation, Coordinate Compression, Fenwick tree vs Segment tree selection.

---

## 1. Mental Model & First Principles

When given an array of size `N`:
- Static range queries? Use **Prefix Sum** (Query in `O(1)`, but updates are `O(N)`).
- Frequent point updates AND frequent range queries? A standard array requires `O(N)` for one of the operations.
- **The Segment Tree & Fenwick Tree** balance both operations to **`O(log N)`** by storing aggregated partial ranges in a balanced tree or bitwise hierarchical structure.

### Segment Tree vs Fenwick Tree: The Decision Matrix

| Dimension | Fenwick Tree (BIT) | Segment Tree |
|---|---|---|
| **Code Length** | ~15 lines (ultra-fast to write in 45 min) | ~60 lines |
| **Space** | `O(N)` exact array size | `O(4N)` array representation |
| **Supported Operations** | Invertible associative operations (Sum, XOR) | Any associative operation (Min, Max, GCD, Sum, Custom Objects) |
| **Range Updates + Range Queries** | Complex (difference BITs) | Standard with **Lazy Propagation** |

---

## 2. Production Python Implementation: Segment Tree with Lazy Propagation

```python
class SegmentTree:
    """
    Segment tree supporting Range Add updates and Range Sum queries in O(log N).
    Uses Lazy Propagation to defer range updates to children.
    """
    def __init__(self, arr: list[int]):
        self.n = len(arr)
        self.tree = [0] * (4 * self.n)
        self.lazy = [0] * (4 * self.n)
        self._build(arr, 0, 0, self.n - 1)

    def _build(self, arr: list[int], node: int, start: int, end: int):
        if start == end:
            self.tree[node] = arr[start]
            return
        mid = (start + end) // 2
        left = 2 * node + 1
        right = 2 * node + 2
        self._build(arr, left, start, mid)
        self._build(arr, right, mid + 1, end)
        self.tree[node] = self.tree[left] + self.tree[right]

    def _push(self, node: int, start: int, end: int):
        if self.lazy[node] != 0:
            val = self.lazy[node]
            mid = (start + end) // 2
            left = 2 * node + 1
            right = 2 * node + 2
            
            # Apply to left child
            self.tree[left] += val * (mid - start + 1)
            self.lazy[left] += val
            
            # Apply to right child
            self.tree[right] += val * (end - mid)
            self.lazy[right] += val
            
            self.lazy[node] = 0

    def update_range(self, l: int, r: int, val: int, node: int = 0, start: int = 0, end: int = -1):
        if end == -1: end = self.n - 1
        if r < start or end < l:
            return  # Completely out of bounds
        if l <= start and end <= r:
            # Completely inside query range
            self.tree[node] += val * (end - start + 1)
            self.lazy[node] += val
            return

        self._push(node, start, end)
        mid = (start + end) // 2
        left, right = 2 * node + 1, 2 * node + 2
        self.update_range(l, r, val, left, start, mid)
        self.update_range(l, r, val, right, mid + 1, end)
        self.tree[node] = self.tree[left] + self.tree[right]

    def query_range(self, l: int, r: int, node: int = 0, start: int = 0, end: int = -1) -> int:
        if end == -1: end = self.n - 1
        if r < start or end < l:
            return 0
        if l <= start and end <= r:
            return self.tree[node]

        self._push(node, start, end)
        mid = (start + end) // 2
        left, right = 2 * node + 1, 2 * node + 2
        return (self.query_range(l, r, left, start, mid) +
                self.query_range(l, r, right, mid + 1, end))
```

---

## 3. The 45-Second Fenwick Tree (When Speed Matters in Interviews)

If you only have Point Update and Prefix Sum:
```python
class FenwickTree:
    def __init__(self, n: int):
        self.tree = [0] * (n + 1)

    def add(self, i: int, delta: int):
        i += 1  # 1-based indexing
        while i < len(self.tree):
            self.tree[i] += delta
            i += i & (-i)  # isolate lowest set bit

    def query(self, i: int) -> int:
        i += 1
        s = 0
        while i > 0:
            s += self.tree[i]
            i -= i & (-i)
        return s
```

---

## 4. Staff L5 Interview Rubric

- **Candidate Trap:** Using Segment Trees when coordinates are sparse (`10^9`) without **Coordinate Compression**. If coordinates range up to `10^9`, compressing distinct values to `0..K` (where `K <= 2 * 10^5`) saves `O(N)` memory and prevents Memory Limit Exceeded.
- **Strong Hire:** Writes Fenwick Tree effortlessly in 5 minutes for inversion count or dynamic 2D updates; explains the `i & (-i)` lowest-set-bit mechanism; chooses Segment Tree only when non-invertible range queries (e.g. Range Minimum Query) or Lazy range updates are strictly necessary.
