# Lesson — Recursion Fundamentals: Base Cases, the Recursion Tree, Stack Depth and the Explicit Stack

> **Priority:** ★★★★ (proposed; the curriculum data holds the final rating) — trees, backtracking and dynamic programming are all recursion with a rule added. If recursion is shaky, all three are.
>
> **Study time:** 40 minutes. **Do this after:** Lesson 10 (trees and DFS), before Lesson 13 (backtracking).
>
> **Level:** core.

Most recursion bugs are not about recursion. They are a missing base case, a wrong claim about what the recursive call returns, or a depth the interpreter will not allow. This lesson fixes those three, then shows the two moves everything later is built on: caching the recursion (which becomes DP) and enumerating with it (which becomes backtracking).

---

## 1. Mental Model

> **Write a recursive function by stating, in one sentence, what it returns for an input, and then *assuming that sentence is true* for every smaller input. You only have to make it true for the base case and to combine the smaller answers correctly.**

That is induction, written as code. It gives a three-question checklist to ask before you type anything:

1. **What does `f(x)` return?** Say it in words, including the edge input. "`f(n)` is the sum of `1..n`, and `0` when `n = 0`."
2. **What are the base cases?** The smallest inputs you answer directly, without a recursive call.
3. **Does every recursive call move strictly toward a base case?** `f(n - 1)` does; `f(n)` or `f(n + 1)` does not.

Then there is the picture. Every call is a node, and every call it makes is a child: the **recursion tree**. Its *size* is the running time (work per node times nodes), and its *height* is the stack depth (memory, and the interpreter's limit). Almost every recursion question reduces to "how big is this tree and how tall?".

*Visual (planned): a recursion tree for `fib(5)` with repeated subtrees shaded, then the same tree with cache hits collapsing them. Not built yet.*

---

## 2. The Recognition Reflex

| If the prompt says... | Reach for | Watch for |
|---|---|---|
| a tree, a nested structure, "for each child..." | **Plain recursion** over the structure | depth equals the height of the structure |
| "split in half, solve each half, combine" | **Divide and conquer** | the combine step is where the cost is |
| "count/min/max over choices" and the same sub-input appears twice | **Recursion plus a cache** (memoisation), then DP | state must be hashable; depth |
| "return every subset / ordering / arrangement" | **Recursion that enumerates** (lead-in to backtracking) | output size is exponential by nature |
| a single chain of calls that could be a loop (`f(n)` calls `f(n - 1)`) | **A loop** | recursion buys nothing and costs depth |
| depth could reach thousands (a long list, a deep tree, a snake grid) | **An explicit stack** | `RecursionError` |

> **Recursion is the right tool when the data is a tree or the choices form a tree. It is the wrong tool when the call graph is a line.** A line should be a loop.

---

## 3. Base Cases and Trusting the Call

Two small examples show the whole habit.

```python
def power(x, n):
    """x ** n for a non-negative integer n, with recursion depth about log2(n)."""
    if n == 0:
        return 1                                 # base case: the empty product
    half = power(x, n // 2)                      # TRUST: this is x ** (n // 2)
    return half * half if n % 2 == 0 else half * half * x


def hanoi(n, src, dst, via, moves):
    """Append to `moves` the (from, to) steps that carry n discs from src to dst."""
    if n == 0:
        return                                   # base case: nothing to move
    hanoi(n - 1, src, via, dst, moves)           # TRUST: n-1 discs are now parked on via
    moves.append((src, dst))                     # the one big disc goes straight across
    hanoi(n - 1, via, dst, src, moves)           # TRUST: bring the n-1 discs onto it
```

**`power`.** The sentence is "`power(x, n)` is `x ** n`". For even `n`, `x ** n = (x ** (n/2)) ** 2`; for odd `n`, one more factor of `x`. The call halves `n`, so it recurses about `log2 n` deep instead of `n` deep. The check script compares against `**` on hundreds of random inputs and calls `power(3, 100000)`, which a one-step-at-a-time recursion could not survive (section 5).

**`hanoi`.** You never plan the whole sequence. You assume the function can move `n - 1` discs between any two pegs, and write only the three lines that use that assumption. The check script plays the moves on three stacks, rejects any placement of a larger disc on a smaller one, and confirms the count is `2^n - 1` for `n` up to 10. Each level makes two calls and does one move, which is exactly the recursion tree of height `n` that has `2^n - 1` nodes.

**Where the base case goes wrong.** A missing base case recurses forever (until the depth limit, see section 5). A base case that is too narrow fails on an input you did not think of: `power` with only `if n == 1` fails on `n = 0`. A base case that returns the wrong value is quieter: `power(x, 0)` must be `1`, not `0`. Test the smallest input first.

---

## 4. The Recursion Tree, Its Cost, and the Cache

```python
def fib_naive(n, calls):
    calls[0] += 1                                  # count every call: that is the tree size
    if n < 2:
        return n
    return fib_naive(n - 1, calls) + fib_naive(n - 2, calls)


def fib_memo(n, memo, calls):
    calls[0] += 1
    if n < 2:
        return n
    if n not in memo:                              # compute each distinct input once
        memo[n] = fib_memo(n - 1, memo, calls) + fib_memo(n - 2, memo, calls)
    return memo[n]


def paths_naive(r, c, calls):
    """Ways to walk r steps down and c steps right, one step at a time."""
    calls[0] += 1
    if r == 0 or c == 0:
        return 1
    return paths_naive(r - 1, c, calls) + paths_naive(r, c - 1, calls)


def paths_memo(r, c, memo, calls):
    calls[0] += 1
    if (r, c) not in memo:
        if r == 0 or c == 0:
            memo[(r, c)] = 1
        else:
            memo[(r, c)] = paths_memo(r - 1, c, memo, calls) + paths_memo(r, c - 1, memo, calls)
    return memo[(r, c)]
```

**Measured, not remembered.** The check script counts calls and verifies these exact relations for every small input:

- `fib_naive(n)` makes `2 * F(n + 1) - 1` calls, where `F` is the Fibonacci sequence with `F(1) = F(2) = 1`. For `n = 25` that is **242,785 calls** to compute one number below 100,000.
- `fib_memo(n)` makes `2n - 1` calls for `n >= 1`, and the cache holds one entry per distinct `n >= 2`.
- `paths_naive(r, c)` makes `2 * C(r + c, r) - 1` calls, where `C` is the binomial coefficient. For `r = c = 10` that is **369,511 calls** to return `184,756`.
- `paths_memo(r, c)` stores exactly `(r + 1) * (c + 1) - 1` entries when `r` and `c` are both at least 1: one per cell of the grid of sub-inputs, except `(0, 0)`, which no call ever reaches (it is only a neighbour of base cases). For `10 × 10` that is 120 entries against 369,511 naive calls.

**What changed between the naive and cached versions.** Nothing about the recurrence. One dictionary check was added, and the tree collapsed from exponential size to the number of *distinct inputs*. That is dynamic programming in one sentence: recursion where each distinct sub-input is computed once. Lessons 14 and 15 start from here; their tables are the same cache filled in bottom-up order.

**Python gives you the cache.** `functools.cache` is `lru_cache(maxsize=None)` (Python 3.9+): a wrapper around a dictionary lookup. Its arguments must be hashable, because they are the dictionary key, so you pass indices or tuples, never a list. The documentation's Fibonacci example reports `hits=28, misses=16` for 16 values, which is the same picture: one miss per distinct input, every other call a hit (see Sources). Writing the dictionary by hand, as above, is worth doing once so the mechanism is not magic.

**When a cache does nothing.** It only helps when the same input appears twice. A recursion over a tree visits each node once, so adding `cache` costs memory and buys nothing. Count distinct inputs against calls before you reach for it.

---

## 5. Stack Depth and the Explicit Stack

```python
def sum_to(n):
    """1 + 2 + ... + n, one call per step."""
    return 0 if n == 0 else n + sum_to(n - 1)


def sum_to_loop(n):
    total = 0
    for i in range(1, n + 1):
        total += i
    return total
```

`sum_to(n)` makes a chain of `n` nested calls, so its stack is `n` frames tall. CPython enforces a limit on that depth. On the interpreter used to test this lesson (CPython 3.13 on Windows) `sys.getrecursionlimit()` returned 1000; the documentation page I read does not state a default, so print the value on yours. What the documentation does say is that the limit exists to prevent a C stack overflow, that the maximum you may raise it to depends on the platform, and that setting it too high can crash the interpreter (see Sources). The check script asserts that `sum_to(limit * 50)` raises `RecursionError` while `sum_to_loop(10**6)` returns the exact value.

Python 3.11 changed how calls are made: most Python-to-Python calls no longer use the C stack. The release notes say this lets recursive functions go significantly deeper, but only if you raise the limit with `sys.setrecursionlimit`; the limit itself was not changed (see Sources). Do not rely on that in an interview: you do not know the interviewer's interpreter, and "I raised the limit" reads as a workaround. Say instead where the depth comes from and how you would remove it.

**Recognise depth from the input.** The stack is as deep as the longest chain of calls: `n` for a list walked one element at a time, the tree's height for a tree (up to `n` for a degenerate one), `log n` for halving as in `power`. For a tree of 100,000 nodes that is a straight line, recursion fails; a balanced tree of the same size needs about 17 levels.

### Converting recursion to an explicit stack

A call frame is three things: the arguments, the local variables, and *where to resume* after a child returns. A loop with a list as the stack reproduces all three. The one decision is where "resume" lives. For work done *before* the children it needs nothing; for work done *after* the children, push the node back marked "ready to combine".

```python
import operator

OPS = {'+': operator.add, '-': operator.sub, '*': operator.mul}


def eval_rec(e):
    """e is an int, or (op, left, right). Recursive reference."""
    if isinstance(e, int):
        return e
    op, left, right = e
    return OPS[op](eval_rec(left), eval_rec(right))


def eval_iter(e):
    """The same function with the call stack made explicit. Depth is limited only by memory."""
    work = [(e, False)]                            # (node, children_already_expanded)
    vals = []                                      # results of finished subtrees
    while work:
        node, ready = work.pop()
        if isinstance(node, int):
            vals.append(node)
        elif ready:                                # both children have finished: combine
            b = vals.pop()
            a = vals.pop()                         # pushed left first, so the left value is deeper
            vals.append(OPS[node[0]](a, b))
        else:
            work.append((node, True))              # come back to this node after its children
            work.append((node[2], False))          # right pushed first ...
            work.append((node[1], False))          # ... so the left child is popped first
    return vals[0]


def nested_sum(x):
    """Sum of all ints in arbitrarily nested lists."""
    return sum(nested_sum(y) if isinstance(y, list) else y for y in x)


def nested_sum_stack(x):
    total, stack = 0, [x]
    while stack:
        for y in stack.pop():
            if isinstance(y, list):
                stack.append(y)                    # no "resume" needed: addition does not care about order
            else:
                total += y
    return total
```

The two examples differ on purpose. `nested_sum` needs no resume point, because addition does not care in what order the pieces arrive, so the stack holds only "lists still to open". `eval_iter` does need one: subtraction cares about order, and the operator must wait for both children. The two-phase `(node, ready)` entry is the general trick, and it is what you write when "convert this recursion to iterative" appears on a whiteboard. The check script runs random expression trees through both versions, tests `10 - (4 - 1) = 7` to catch an operand-order bug, then builds a left-leaning chain 100,000 deep: `eval_iter` returns 100,000 while `eval_rec` raises `RecursionError`.

**When to stop converting.** An explicit stack is longer and easier to get wrong. Use it when the depth is a real risk or the interviewer asks. Otherwise write the recursion, state the depth, and say you would convert it if the input could be deep.

---

## 6. Enumeration: the Lead-In to Backtracking

```python
def subsets_rec(items):
    """Every subset of items. Builds new lists; nothing is mutated, so nothing needs undoing."""
    if not items:
        return [[]]                                # base case: the empty set has one subset, the empty one
    rest = subsets_rec(items[1:])                  # TRUST: all subsets of the tail
    return rest + [[items[0]] + s for s in rest]   # without items[0], then with it


def permutations_rec(items):
    """Every ordering of items, in the same order itertools.permutations produces."""
    if not items:
        return [[]]
    out = []
    for i, x in enumerate(items):                  # choose which item goes first
        for p in permutations_rec(items[:i] + items[i + 1:]):
            out.append([x] + p)
    return out
```

Each is a recursion tree whose leaves are the answers. At every node of `subsets_rec` there is a binary choice, include the first item or not, giving `2^n` leaves. In `permutations_rec` the first position has `n` choices, the next `n - 1`, and so on: `n!` leaves. The check script verifies both against `itertools` for `n` up to 7, and counts: 128 subsets and 5,040 permutations at `n = 7`. The `itertools` documentation notes that these tools treat elements as unique by *position*, not by value, so repeated values produce repeated results; the recursive versions behave the same way, and the check asserts that `subsets_rec([1, 1])` returns four subsets, two of them identical (see Sources).

**What Lesson 13 changes.** These versions return a fresh list at every level, which costs time and memory proportional to the output at *every* node. Backtracking instead keeps one mutable `path`, appends before the recursive call, and pops after it, so each node costs `O(1)` plus the copy at a leaf. It also adds *pruning*: abandoning a branch the moment it cannot lead to an answer. Nothing else changes. If you can write `subsets_rec` and say why it has `2^n` leaves, backtracking is a mechanical step.

**Size sets the ceiling.** The output itself has `2^n` or `n!` entries, so enumeration is only possible for small `n`. "Return all" with `n` in the tens of thousands means you have misread the problem; "count" with large `n` is the cache of section 4.

---

## 7. Pitfalls

1. **No base case, or one that misses the smallest input.** Test `n = 0` and the empty list first.
2. **A call that does not move toward the base case.** `f(n)` calling `f(n)`, or `f(n + 1)` with a base at `n = 0`.
3. **Trusting a sentence you did not write.** If you cannot say what `f(x)` returns in words, the recursion is a guess. Write the sentence first.
4. **Exponential recursion with repeated inputs.** `fib_naive(25)` makes 242,785 calls. Count distinct inputs against calls; add a cache when they differ.
5. **A cache on unhashable arguments.** `functools.cache` stores arguments as dictionary keys, so they must be hashable. Pass an index or a tuple, not a list.
6. **A line of calls written as recursion.** `sum_to(n)` should be a loop; it needs `n` frames for no benefit.
7. **Ignoring depth.** A long list, a degenerate tree or a snake-shaped grid needs `RecursionError`-proof code. State the depth, and have the explicit-stack version ready.
8. **Raising the recursion limit as the fix.** The documentation warns that too high a limit can crash the interpreter. Remove the depth instead.
9. **Mutating shared state and forgetting to undo it.** Fine in backtracking, where the undo is the technique, and a bug everywhere else.
10. **Wrong operand order in an iterative conversion.** For a non-commutative operator, check `a - b` against the recursive version on one hand-built input.

---

## 8. Drills

1. Say, in one sentence each, what `power(x, n)` and `hanoi(n, src, dst, via, moves)` return or produce. What are their base cases?
2. Draw the recursion tree of `fib_naive(5)`. How many nodes? Which subtrees repeat?
3. Why does `fib_memo(n)` make `2n - 1` calls rather than `n`?
4. `power(2, 10)` recurses through which values of `n`? How deep does it go?
5. Why does `sum_to(n)` need `n` frames and `power(x, n)` only about `log2 n`?
6. In `eval_iter`, why are the right child and the left child pushed in that order, and what breaks if you swap them on `10 - (4 - 1)`?
7. Why does `nested_sum_stack` need no "ready" flag while `eval_iter` does?
8. How many leaves does the recursion tree of `permutations_rec` have for 4 items, and of `subsets_rec`?

---

## 9. Homework

In order; for each, write the sentence "`f(x)` returns ..." before the code.

1. **Fibonacci Number** (LeetCode 509) and **Climbing Stairs** (70). Write the naive recursion, count its calls, then add the cache.
2. **Pow(x, n)** (50). The halving recursion; handle a negative `n` separately.
3. **Maximum Depth of Binary Tree** (104) and **Invert Binary Tree** (226). Plain recursion over a structure; then write the max-depth one with an explicit stack.
4. **Flatten Nested List Iterator** (341), or any "flatten arbitrarily nested lists" exercise. Recursive, then iterative.
5. **Subsets** (78) and **Permutations** (46). `subsets_rec` and `permutations_rec` first, then re-do them with a single mutable path as Lesson 13 will show.
6. **Unique Paths** (62). `paths_naive`, `paths_memo`, then a bottom-up table.
7. **Basic Calculator** style problems with parentheses: write the recursive evaluator, then the explicit-stack one.
8. **Tower of Hanoi** (any exercise set): print the moves for `n = 3` and confirm there are 7.

---

## Sources and further reading

Read and used for this lesson (accessed 26 November 2026):

- Python documentation, `functools`, docs.python.org/3/library/functools.html. Used for: `cache` is `lru_cache(maxsize=None)` and a thin dictionary wrapper (3.9+); arguments must be hashable; the Fibonacci example and its `hits=28, misses=16` result for 16 values.
- Python documentation, `sys`, docs.python.org/3/library/sys.html (recursion-limit entries). Used for: the limit exists to prevent a C stack overflow; the maximum allowed value is platform dependent; too high a limit can crash the interpreter.
- Python documentation, What's New in Python 3.11, "Inlined Python function calls", docs.python.org/3/whatsnew/3.11.html (read the first part of the page, which contains that section). Used for: most Python-to-Python calls no longer consume C stack space; deeper recursion is possible only if the limit is raised.
- Python documentation, `itertools`, docs.python.org/3/library/itertools.html. Used for: `permutations` and `combinations` treat elements as unique by position, not value; lexicographic output order; `n! / (n - r)!` and binomial counts.

Not consulted: any textbook or paper for induction-based reasoning about recursion, the Tower of Hanoi move count, or the cost of divide and conquer. These are stated as standard results and the lesson's code checks verify only the specific counts quoted (call counts, `2^n - 1` moves, `2^n` subsets, `n!` permutations) for the input sizes tested in `test/lesson_code/ds28_check.py`. The default recursion limit is not quoted from any documentation; the value 1000 is what the tested interpreter reported. The LeetCode problem numbers are from memory and should be checked against the site before you rely on them.

*Last reviewed: 26 November 2026.*
