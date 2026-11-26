# Lesson 21 — Bitmask DP & State Compression

> **Priority:** ★★★★☆ — a recognisable hard-problem family; the constraint line gives it away before you read the story.
>
> **Study time:** 50 minutes. **Do this after:** Lesson 15 (2D dynamic programming) and Lesson 17 (bit manipulation).
> **Level:** advanced. Optional for a crash plan; worth doing if your target loops include hard rounds.

Some problems ask you to choose among, order, or partition a small set of items, and the answer
depends on *which* items are already used. The set of used items is the DP state. When there are at
most about 20 items, that set fits in one integer, one bit per item, and `2^n` states is affordable.
This lesson gives you the template, four worked problems, and the one counting argument interviewers
like to hear.

---

## 1. Mental Model

> **A subset of `n` items is an integer from `0` to `2^n - 1`. The DP is over subsets: `dp[mask]`
> is the best answer for "exactly the items in `mask` are done", built from smaller masks.**

Two follow-ups decide everything:

- **What else do you need besides the mask?** Often the *last item chosen* (`dp[mask][last]`, for
  routes) or nothing at all because the mask already implies the position (for assignment, the number
  of set bits is the index of the next person).
- **How do you move?** Add one item (`mask | 1 << k`), or split into a submask and the rest.

Idioms to have in your fingers:

| Operation | Python |
|---|---|
| set bit `k` | `mask \| (1 << k)` |
| clear bit `k` | `mask & ~(1 << k)` |
| test bit `k` | `(mask >> k) & 1` |
| all `n` bits | `(1 << n) - 1` |
| lowest set bit | `mask & -mask` |
| count set bits | `mask.bit_count()` (Python 3.10 and later) or `bin(mask).count('1')` |

---

## 2. Recognition Reflex

| If the prompt says... | Reach for | Cost |
|---|---|---|
| `n <= 20`, "visit every node/city once", route cost | **`dp[mask][last]`** (Held-Karp) | `O(2^n * n^2)` |
| "assign each person one task", `n <= 20`, minimise cost | **`dp[mask]`**, person index = popcount | `O(2^n * n)` |
| "can you split these into `k` groups of equal sum", `n <= 16` | **`dp[mask]` = leftover in the current group** | `O(2^n * n)` |
| "shortest walk visiting all nodes" (unweighted, nodes can repeat) | **BFS over `(node, mask)`** | `O(2^n * n)` states |
| "split a set into groups, group cost given per subset" | **submask enumeration** | `O(3^n)` |
| `n` is 30 or more | not this; look for a different structure | |

Why the cut-off is about 20: `2^20` is 1,048,576 states, and `20!` is about `2.4 * 10^18` permutations.
With an inner loop of `n` per state (about 21 million steps) a Python solution is slow but workable;
with an inner `n^2` (about 420 million steps) it is not. As a rule of thumb, the route DP with a last
node is comfortable in Python to around `n = 15`. Say that at the whiteboard.

---

## 3. Route Cost: Held-Karp

`dp[mask][j]` is the cheapest way to start at node 0, visit exactly the nodes in `mask`, and end at
`j`. Extend by one unvisited node `k`. The answer closes the loop back to 0.

```python
def held_karp(d):
    """Cheapest tour from node 0 that visits every node once and returns to 0.
    d[i][j] is the cost of going i -> j (need not be symmetric)."""
    n = len(d)
    if n == 1:
        return 0
    INF = float('inf')
    FULL = 1 << n
    dp = [[INF] * n for _ in range(FULL)]
    dp[1][0] = 0                                 # only node 0 visited, standing at 0
    for mask in range(1, FULL):
        if not mask & 1:
            continue                             # node 0 is always in the mask
        for j in range(n):
            if not (mask >> j) & 1 or dp[mask][j] == INF:
                continue
            for k in range(n):
                if (mask >> k) & 1:
                    continue                     # already visited
                nm = mask | (1 << k)
                c = dp[mask][j] + d[j][k]
                if c < dp[nm][k]:
                    dp[nm][k] = c
    return min(dp[FULL - 1][j] + d[j][0] for j in range(1, n))
```

Masks are processed in increasing numeric order. That is a valid topological order because every
transition goes to a numerically larger mask (it only adds a bit). That sentence is the whole
correctness argument for "iterate masks upward".

---

## 4. Assignment: the Mask Implies the Position

Give person `0` a task, then person `1`, and so on. After `p` people are assigned, exactly `p` bits
are set, so the mask alone tells you which person is next. No extra dimension.

```python
def min_cost_assignment(c):
    """c[i][t] = cost of giving task t to person i (n people, n tasks). Minimum total cost."""
    n = len(c)
    INF = float('inf')
    dp = [INF] * (1 << n)
    dp[0] = 0
    for mask in range(1 << n):
        if dp[mask] == INF:
            continue
        person = bin(mask).count('1')
        if person == n:
            continue
        for t in range(n):
            if not (mask >> t) & 1:
                nm = mask | (1 << t)
                if dp[mask] + c[person][t] < dp[nm]:
                    dp[nm] = dp[mask] + c[person][t]
    return dp[(1 << n) - 1]
```

For large `n` the Hungarian algorithm is the right tool; the bitmask DP is what you write when the
constraint says `n <= 20` or when a task has extra side conditions that break the Hungarian model.

---

## 5. Equal-Sum Partition: Compress the Remainder

"Split `nums` into `k` subsets with equal sum." Let `t = sum / k`. Fill one bucket at a time, in
order. `fill[mask]` is how full the *current* bucket is after using exactly the items in `mask`
(`-1` if `mask` cannot be reached without overflowing a bucket). Reaching a full bucket resets it to 0
via `% t`.

```python
def can_partition_k_subsets(nums, k):
    total = sum(nums)
    if total % k:
        return False
    t = total // k
    if max(nums) > t:
        return False
    n = len(nums)
    fill = [-1] * (1 << n)
    fill[0] = 0
    for mask in range(1 << n):
        if fill[mask] < 0:
            continue
        for i in range(n):
            if (mask >> i) & 1 or fill[mask] + nums[i] > t:
                continue
            fill[mask | (1 << i)] = (fill[mask] + nums[i]) % t
    return fill[(1 << n) - 1] == 0
```

This replaces a backtracking search that can revisit the same set of used items many times with a
DP that visits each set once. The state is the set of items used, because *which* items fill the
earlier buckets does not matter, only how full the current one is.

---

## 6. Shortest Walk Visiting All Nodes: BFS on `(node, mask)`

Nodes may repeat, edges have length 1, so the state is `(where I am, which nodes I have seen)` and the
search is a plain BFS. Start from every node at once.

```python
from collections import deque

def shortest_path_visiting_all(graph):
    """graph[u] lists the neighbours of u (undirected, connected). Length of the shortest walk
    that visits every node; it may start anywhere and reuse nodes."""
    n = len(graph)
    if n == 1:
        return 0
    full = (1 << n) - 1
    seen = {(i, 1 << i) for i in range(n)}
    q = deque((i, 1 << i, 0) for i in range(n))
    while q:
        u, mask, dist = q.popleft()
        for v in graph[u]:
            nm = mask | (1 << v)
            if nm == full:
                return dist + 1
            if (v, nm) not in seen:
                seen.add((v, nm))
                q.append((v, nm, dist + 1))
    return -1                                    # only reachable for a disconnected graph
```

Do not use Held-Karp here: it forbids revisiting a node, but a star graph needs to pass through the
centre several times (`[[1,2,3],[0],[0],[0]]` has answer 4, not 3).

---

## 7. Submask Enumeration and the `3^n` Argument

To split a set into groups you need to loop over the subsets of a mask:

```python
def submasks(mask):
    """Every non-empty submask of mask, from mask itself down to the smallest."""
    sub = mask
    while sub:
        yield sub
        sub = (sub - 1) & mask                   # next smaller submask
```

`sub - 1` flips the lowest set bit and sets every bit below it; `& mask` throws away the bits that
are not in `mask`, which lands exactly on the next smaller submask.

**Worked use: partition into groups of minimum total cost**, where `cost[s]` is the price of making
`s` a group. Fix the group that contains the lowest set bit of `mask`, so each partition is built
once, not once per ordering of its groups.

```python
def min_partition_cost(n, cost):
    """cost[s] for every non-empty subset s of range(n). Minimum total cost to split all n items into groups."""
    FULL = 1 << n
    dp = [0] + [float('inf')] * (FULL - 1)
    for mask in range(1, FULL):
        low = mask & -mask
        for sub in submasks(mask):
            if sub & low:                        # the group that holds the lowest item
                dp[mask] = min(dp[mask], cost[sub] + dp[mask ^ sub])
    return dp[FULL - 1]
```

**Why the total is `O(3^n)`, not `O(4^n)`.** Count pairs `(mask, sub)` with `sub` a submask of `mask`.
Each of the `n` items is in one of three situations: in neither, in `mask` only, or in both. That is
`3` choices per item, so `3^n` pairs. The same count from the other side:
`sum over k of C(n, k) * 2^k = (1 + 2)^n = 3^n`. For `n = 15` that is 14,348,907 pairs, workable; for
`n = 20` it is about `3.5 * 10^9`, not.

---

## 8. Pitfalls Checklist

1. **Using the mask DP when `n` is not small.** Read the constraint first.
2. **Forgetting the "last node" dimension** in route problems, so two different endpoints share one state.
3. **Using Held-Karp when nodes may repeat.** That is the BFS formulation of Section 6.
4. **Operator precedence.** In Python `x - 1 << k` is `(x - 1) << k`. Parenthesise every shift and every bit test.
5. **Not marking unreachable states** (`INF` or `-1`) and then extending from them.
6. **Iterating masks in the wrong order.** Transitions that add bits go upward; transitions that remove bits go downward.
7. **Submask loop that stops at `sub > 0` but you needed the empty set** (or the reverse). Decide whether `0` belongs.
8. **Counting each partition once per ordering** by not fixing the lowest bit; it is correct for a minimum, but multiplies the work and breaks "count the ways".

---

## 9. Drills

1. What are `mask | 1 << 3`, `mask & ~(1 << 3)` and `(mask >> 3) & 1` for `mask = 0b1010`?
2. In Held-Karp, why is `dp[mask][j]` defined only when bit `j` of `mask` is set?
3. Why does `min_cost_assignment` need no "which person" dimension?
4. What does `fill[mask]` mean in the equal-sum partition, and why does `% t` reset it?
5. Why does Held-Karp give the wrong answer on a star graph for "shortest walk visiting all nodes"?
6. List the non-empty submasks of `0b1011` in the order `submasks` produces them.
7. Show that the total number of `(mask, submask)` pairs over `n` items is `3^n`.
8. A problem has `n = 25` cities and asks for the cheapest tour. Which part of the constraint line made you hesitate, and what would you say to the interviewer?

---

## 10. Homework

Solve these in order. Names are common problem titles; numbers are LeetCode's.

1. **Shortest Path Visiting All Nodes** (847) — Section 6.
2. **Partition to K Equal Sum Subsets** (698) — Section 5, then compare with backtracking.
3. **Minimum Number of Work Sessions to Finish the Tasks** (1986) — a bucket-filling DP, with sessions in place of equal sums.
4. **Number of Ways to Wear Different Hats to Each Other** (1434) — here the mask is over people, not items; work out why.
5. **Find the Shortest Superstring** (943) — Held-Karp on overlap costs.
6. **Maximum Students Taking Exam** (1349) — a row-by-row mask.

Then: write `held_karp` from a blank page, and explain in one minute why iterating masks in increasing
order is valid.

---

## Further reading

The standard names to search for are Held-Karp for the tour DP and SOS (sum over subsets) DP for
the next step after submask enumeration. They were not consulted while writing this revision: the
code here was written from the technique itself and checked against brute-force versions
(permutations, set partitions, recursive bucket assignment) on random small inputs before publishing.

*Last reviewed: 2026-11-26.*
