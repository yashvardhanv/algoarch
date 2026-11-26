# Lesson 20 — Segment Trees & Fenwick Trees

> **Priority:** ★★★★☆ — rare in a first-round loop, decisive when a hard round asks for "update and query a range, many times".
>
> **Study time:** 65 minutes. **Do this after:** Lesson 5 (prefix sums) and Lesson 10 (trees and recursion).
> **Level:** advanced. Optional for a crash plan; worth doing if your target loops include hard rounds.

A prefix-sum array answers range queries in `O(1)` but dies the moment a value changes: one update
costs `O(n)`. The problem shape "array changes, and you keep asking about ranges" needs a structure
where both the update and the query cost `O(log n)`. There are two you should be able to write: the
Fenwick tree (short, sums only) and the segment tree (longer, any associative operation, range updates
with lazy tags).

---

## 1. Mental Model

> **Store the answer for a few well-chosen ranges. A query is stitched together from `O(log n)` of
> those ranges; an update repairs the `O(log n)` ranges that contain the changed position.**

- A **segment tree** picks the ranges by halving: the root covers `[0, n-1]`, each node's children
  cover its left and right halves. Any query range splits into at most about `2 log n` nodes.
- A **Fenwick tree** picks them by binary arithmetic: slot `i` (1-based) stores the sum of the
  `lowbit(i) = i & -i` positions ending at `i`. Slot 12 (`1100`) covers 4 positions, slot 8 covers 8.
  Jumping `i -= i & -i` walks down a prefix; `i += i & -i` walks up to every slot that contains `i`.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for | Why |
|---|---|---|
| "point update, range sum", or "count of smaller elements to the right", "inversions" | **Fenwick** | shortest code; sums are invertible |
| "range minimum/maximum/GCD with point updates" | **Segment tree** (iterative is fine) | min has no inverse, so a Fenwick cannot subtract |
| "add `v` to every element in `[l, r]`, then query a range sum" | **Segment tree with lazy tags** (or two Fenwicks) | range update needs deferred work |
| values up to `10^9` but only `n` of them | **Coordinate compression**, then either | the tree is indexed by rank, not value |
| array never changes | **Prefix sums or a sparse table**, no tree | do not pay `log n` for nothing |
| "k-th smallest in a changing multiset of small integers" | **Fenwick `lower_bound`** | binary descent on the tree |

---

## 3. Fenwick Tree

```python
class Fenwick:
    """Point add, prefix/range sum, and lower_bound on non-negative data. 0-based public API."""
    def __init__(self, n):
        self.n = n
        self.t = [0] * (n + 1)              # 1-based internally

    def add(self, i, delta):
        i += 1
        while i <= self.n:
            self.t[i] += delta
            i += i & -i                      # next slot whose range contains i

    def prefix(self, i):
        """Sum of positions 0..i."""
        i += 1
        s = 0
        while i > 0:
            s += self.t[i]
            i -= i & -i                      # drop the lowest set bit
        return s

    def range_sum(self, l, r):
        return self.prefix(r) - (self.prefix(l - 1) if l > 0 else 0)

    def lower_bound(self, target):
        """Smallest index i with prefix(i) >= target (target >= 1). Needs all values >= 0.
        Returns n if the total is below target."""
        pos = 0
        for b in range(self.n.bit_length(), -1, -1):
            nxt = pos + (1 << b)
            if nxt <= self.n and self.t[nxt] < target:
                pos = nxt
                target -= self.t[nxt]
        return pos
```

Why `lower_bound` works: it builds the answer one bit at a time from the top. If the block of size
`2^b` starting after `pos` sums to less than `target`, the answer lies beyond it, so skip it and
subtract. This needs non-negative values, because it relies on prefix sums only growing.

**Inversions and "count smaller after self", with coordinate compression.** Replace each value by its
rank among the distinct values, then sweep left to right: before inserting `x`, the number of earlier
elements strictly greater than `x` is `inserted - prefix(rank(x))`.

```python
def count_inversions(a):
    """Number of pairs i < j with a[i] > a[j]. Values may be huge; they are compressed to ranks."""
    ranks = {v: r for r, v in enumerate(sorted(set(a)))}
    f = Fenwick(len(ranks))
    inv = 0
    for seen, x in enumerate(a):
        r = ranks[x]
        inv += seen - f.prefix(r)            # earlier elements with rank <= r are not greater
        f.add(r, 1)
    return inv
```

Equal values are not inversions, which is why the prefix includes `rank(x)` itself.

---

## 4. Segment Tree for a Non-Invertible Operation (Iterative, Min)

The bottom-up layout stores the array in the second half of a `2n` array: leaf `i` lives at
`n + i`, and node `k` has children `2k` and `2k+1`. No recursion, no `4n` memory, and it works for any
`n`, not only powers of two, as long as the operation is commutative (min, max, sum, GCD).

```python
class MinSegTree:
    """Point set, range min over inclusive [l, r]."""
    def __init__(self, arr):
        self.n = len(arr)
        self.t = [float('inf')] * self.n + list(arr)
        for k in range(self.n - 1, 0, -1):
            self.t[k] = min(self.t[2 * k], self.t[2 * k + 1])

    def set(self, i, v):
        k = i + self.n
        self.t[k] = v
        while k > 1:
            k >>= 1
            self.t[k] = min(self.t[2 * k], self.t[2 * k + 1])

    def query(self, l, r):
        res = float('inf')
        l += self.n
        r += self.n + 1                      # half-open [l, r)
        while l < r:
            if l & 1:                        # l is a right child: take it, move right
                res = min(res, self.t[l]); l += 1
            if r & 1:                        # r is exclusive: its left sibling is inside
                r -= 1; res = min(res, self.t[r])
            l >>= 1; r >>= 1
        return res
```

If the operation is **not commutative** (string concatenation, matrix product), keep separate left
and right accumulators and combine them in order at the end; the loop above would mix the order.

---

## 5. Lazy Propagation: Range Add, Range Sum

When a whole range is changed at once you cannot touch every leaf. Instead, mark the fully covered
node with a **tag** ("every element below me gets `+v`"), fix its own sum immediately, and push the
tag to the children only when a later operation has to descend through that node.

```python
class LazySegTree:
    """Range add, range sum, inclusive [l, r]. Recursion depth is log n, so recursion is safe here."""
    def __init__(self, arr):
        self.n = len(arr)
        self.sum = [0] * (4 * self.n)
        self.tag = [0] * (4 * self.n)
        if self.n:
            self._build(arr, 1, 0, self.n - 1)

    def _build(self, arr, node, lo, hi):
        if lo == hi:
            self.sum[node] = arr[lo]
            return
        mid = (lo + hi) // 2
        self._build(arr, 2 * node, lo, mid)
        self._build(arr, 2 * node + 1, mid + 1, hi)
        self.sum[node] = self.sum[2 * node] + self.sum[2 * node + 1]

    def _apply(self, node, lo, hi, v):
        self.sum[node] += v * (hi - lo + 1)  # the node's own answer is correct immediately
        self.tag[node] += v                  # its children are stale until pushed

    def _push(self, node, lo, hi):
        if self.tag[node]:
            mid = (lo + hi) // 2
            self._apply(2 * node, lo, mid, self.tag[node])
            self._apply(2 * node + 1, mid + 1, hi, self.tag[node])
            self.tag[node] = 0

    def range_add(self, l, r, v, node=1, lo=0, hi=None):
        if hi is None:
            hi = self.n - 1
        if r < lo or hi < l:
            return
        if l <= lo and hi <= r:
            self._apply(node, lo, hi, v)
            return
        self._push(node, lo, hi)
        mid = (lo + hi) // 2
        self.range_add(l, r, v, 2 * node, lo, mid)
        self.range_add(l, r, v, 2 * node + 1, mid + 1, hi)
        self.sum[node] = self.sum[2 * node] + self.sum[2 * node + 1]

    def range_sum(self, l, r, node=1, lo=0, hi=None):
        if hi is None:
            hi = self.n - 1
        if r < lo or hi < l:
            return 0
        if l <= lo and hi <= r:
            return self.sum[node]
        self._push(node, lo, hi)             # never read children without pushing first
        mid = (lo + hi) // 2
        return (self.range_sum(l, r, 2 * node, lo, mid)
                + self.range_sum(l, r, 2 * node + 1, mid + 1, hi))
```

The invariant to say out loud: **a node's `sum` is always correct for its own range; a node's `tag`
is work its children still owe.** Every operation that descends pushes first, so children are never
read while stale.

Different lazy operations need different tags. "Range assign" cannot be an additive tag: you need a
"has a pending assignment" flag, and an assignment must overwrite an older pending add. Decide what
composing two tags means before writing code.

Visual (planned): a segment tree over 8 leaves with a query `[2, 6]` highlighting the 4 nodes it
decomposes into, and a Fenwick tree with the slots visited by `prefix(6)` and `add(2)`.

---

## 6. Complexity

| Structure | Build | Update | Query | Memory |
|---|---|---|---|---|
| Fenwick | `O(n)` with care, `O(n log n)` by repeated `add` | `O(log n)` | `O(log n)` | `n + 1` |
| Iterative segment tree | `O(n)` | `O(log n)` | `O(log n)` | `2n` |
| Recursive lazy segment tree | `O(n)` | `O(log n)` (range) | `O(log n)` (range) | `4n` array |

---

## 7. Pitfalls Checklist

1. **Index 0 in a Fenwick tree.** `i += i & -i` from `i = 0` never moves. Shift to 1-based inside, as above.
2. **Using a Fenwick for min/max.** Prefix min cannot be undone by subtraction, and a value that increases breaks it.
3. **Forgetting to push before descending** in a lazy tree, or pushing after reading the children.
4. **Tree size `2n` in the recursive layout.** Use `4n` (or round `n` up to a power of two).
5. **Off-by-one on range ends**: decide inclusive or half-open once. The iterative tree above is half-open internally and inclusive at the API.
6. **Compressing values and then comparing the wrong way**: for "strictly greater" use `seen - prefix(rank)`, not `seen - prefix(rank - 1)`.
7. **Using a tree when the array is static.** Prefix sums or a sparse table are simpler and faster.
8. **Applying the `if l & 1 / if r & 1` iterative loop to a non-commutative operation** without ordered left and right accumulators.

---

## 8. Drills

1. Which slots does `prefix(10)` (0-based, so 1-based 11, binary `1011`) read in a Fenwick tree?
2. Which slots does `add(2)` (1-based 3) update when `n = 8`?
3. Why can a Fenwick tree do range sum but not range min with point updates?
4. In the lazy tree, what is true about `sum[node]` and `tag[node]` right after `_apply`?
5. Why is the recursion safe in `LazySegTree` when it would not be safe in a DFS over a path graph of a million nodes?
6. What changes if the operation is "range assign" instead of "range add"?
7. Count inversions in `[3, 1, 2, 2]` by hand using the rank sweep.
8. A problem gives `n = 10^5` values up to `10^9` and asks "how many earlier elements are smaller". What do you do first?

---

## 9. Homework

Solve these, in this order. Names are the common problem titles; numbers are LeetCode's.

1. **Range Sum Query - Mutable** (307) — Fenwick, then again with the iterative segment tree.
2. **Count of Smaller Numbers After Self** (315) — Fenwick with compression.
3. **Reverse Pairs** (493) — compression plus a twist: the compared value is `2 * a[j]`, so compress both.
4. **Range Sum Query 2D - Mutable** (308) — a 2D Fenwick.
5. **The Skyline Problem** (218) or **Falling Squares** (699) — range-max with range assign; this is where tag composition bites.

Then write the Fenwick tree from a blank page in under five minutes and explain `i & -i` aloud.

---

## Further reading

The standard references are CLRS (augmenting data structures) and the CP-Algorithms pages on
Fenwick and segment trees. They were not consulted while writing this revision: the code here was
written from the structures themselves and checked against brute-force versions on random inputs
before publishing.

*Last reviewed: 2026-11-26.*
