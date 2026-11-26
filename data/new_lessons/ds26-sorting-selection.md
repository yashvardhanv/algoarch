# Lesson — Sorting and Selection: Merge Sort, Quicksort, Quickselect and Linear Sorts

> **Priority:** ★★★★ (proposed; the curriculum data holds the final rating) — you will rarely be asked to *write* a sort, but half of all array problems are a sort plus one idea.
>
> **Study time:** 60 minutes. **Do this after:** Lesson 5 (prefix sums). It is needed before binary search on a sorted array, intervals and the heap problems.
> **Level:** core.

Almost no interviewer asks "implement quicksort" any more. They ask "find the k-th largest", "count pairs that are out of order", "sort these records by two keys", "merge overlapping intervals". Every one of those is a sorting idea used on purpose. This lesson gives you the five ideas, the one working implementation of each, and the point at which each one is the wrong tool.

---

## 1. Mental Model

> **A comparison sort has to ask enough yes/no questions to tell apart every possible ordering of the input. Everything else is bookkeeping about *which* questions to ask and *what you keep* while asking.**

- **Merge sort** splits, sorts halves, merges. It always does `O(n log n)` work, keeps equal items in their original order (stable), and needs `O(n)` extra space.
- **Quicksort** picks a pivot and splits the array into smaller, equal and larger. It does `O(n log n)` work on average, sorts in place, and is *not* stable.
- **Quickselect** is quicksort that only follows the side holding the k-th item. Average `O(n)`.
- **Counting and radix sort** do not compare at all. They use the keys as array positions, so they need small integer keys, and in exchange they beat `n log n`.

Why `n log n` is a floor for comparison sorts: `n` distinct items can be arranged in `n!` orders, each comparison has two outcomes, so you need at least `lg(n!)` comparisons in the worst case, and `lg(n!)` grows like `n log n`. The CPython notes on its sort call `lg(n!)` the information-theoretic limit and report that a random-input run lands within about 1% of it (see Sources).

*Visual (planned): the array as bars, with the merge and partition steps animated and a counter of comparisons against the `lg(n!)` line. Not built yet.*

---

## 2. The Recognition Reflex

| If the prompt says... | Reach for | Time |
|---|---|---|
| "k-th largest/smallest", "median", "top-k without sorting everything" | **Quickselect** (or a size-k heap if the data streams) | average `O(n)` |
| "count pairs `i < j` with `a[i] > a[j]`", "how far from sorted" | **Merge sort counting inversions** | `O(n log n)` |
| "sort by A, break ties by B", "keep the original order of equals" | **A stable sort**, or sort by B first then A | `O(n log n)` |
| "sort 0/1/2", "partition around a value", "dutch flag" | **Three-way partition** | `O(n)` |
| keys are integers in a small range, or fixed-width digits | **Counting sort / radix sort** | `O(n + m)` / `O(d (n + m))` |
| "merge intervals", "meeting rooms", "closest pair of values" | **Sort first, then one sweep** | `O(n log n)` |
| "sort a linked list" | **Merge sort** (no random access, merging needs none) | `O(n log n)` |
| the data does not fit in memory | **External merge sort** (sorted runs, then merge) | `O(n log n)` with sequential I/O |

> **Before you sort, ask what the sort buys.** If you only need the top `k` of `n`, sorting does `n log n` work to answer a question that a heap answers in `n log k`.

---

## 3. Merge Sort, Stability and Counting Inversions

```python
def merge_sort(a, key=lambda x: x):
    """Stable bottom-up merge sort. Returns a new list; does not change a."""
    a = list(a)
    n = len(a)
    buf = a[:]
    width = 1
    while width < n:
        for lo in range(0, n, 2 * width):
            mid, hi = min(lo + width, n), min(lo + 2 * width, n)
            i, j, k = lo, mid, lo
            while i < mid and j < hi:
                if key(a[j]) < key(a[i]):      # take the right item only if STRICTLY smaller
                    buf[k] = a[j]; j += 1
                else:                          # on a tie the left item goes first: that is stability
                    buf[k] = a[i]; i += 1
                k += 1
            while i < mid:
                buf[k] = a[i]; i += 1; k += 1
            while j < hi:
                buf[k] = a[j]; j += 1; k += 1
        a, buf = buf, a
        width *= 2
    return a


def count_inversions(a):
    """Number of pairs i < j with a[i] > a[j]."""
    a = list(a)
    n = len(a)
    buf = a[:]
    total = 0
    width = 1
    while width < n:
        for lo in range(0, n, 2 * width):
            mid, hi = min(lo + width, n), min(lo + 2 * width, n)
            i, j, k = lo, mid, lo
            while i < mid and j < hi:
                if a[j] < a[i]:
                    total += mid - i           # a[j] jumps over every remaining left item: each is an inversion
                    buf[k] = a[j]; j += 1
                else:
                    buf[k] = a[i]; i += 1
                k += 1
            while i < mid:
                buf[k] = a[i]; i += 1; k += 1
            while j < hi:
                buf[k] = a[j]; j += 1; k += 1
        a, buf = buf, a
        width *= 2
    return total
```

**Stability, concretely.** Sort `[(2,'a'), (1,'b'), (2,'c')]` by the number only. A stable sort must return `(1,'b'), (2,'a'), (2,'c')`: the two 2s keep the order they came in. The single strict `<` in the merge is the whole mechanism. Change it to `<=` and equal items from the right half jump ahead, and the sort is no longer stable. Python's `sorted` and `list.sort` are guaranteed stable, and its documentation uses that to sort by two keys in two passes: sort by the *secondary* key first, then by the primary key (see Sources).

**Counting inversions, worked.** For `[2, 4, 1, 3, 5]` the inversions are `(2,1)`, `(4,1)`, `(4,3)`: three. In the merge of `[2, 4]` with `[1, 3, 5]`, the `1` is smaller than the first left item, so it jumps over both remaining left items (`mid - i = 2`). Later `3` jumps over the one left item still waiting (`4`): one more. Total 3. The trick is that merging already compares across the halves, so the count costs nothing extra.

**Why bottom-up.** A recursive merge sort is fine in Python at any realistic size, because its depth is only `log n`. The reason to write it iteratively is that it avoids function-call overhead and gives you the loop to explain on a whiteboard in six lines. The cost is `O(n)` extra space for `buf`. On a linked list the extra space disappears, because merging relinks nodes instead of copying.

---

## 4. Quicksort, Done So It Cannot Blow Up

```python
import random

def quicksort(a):
    """Randomised three-way quicksort. Returns a new list. Stack depth is O(log n)."""
    a = list(a)
    stack = [(0, len(a) - 1)]
    while stack:
        lo, hi = stack.pop()
        while lo < hi:
            p = a[random.randint(lo, hi)]
            lt, i, gt = lo, lo, hi
            while i <= gt:                       # invariant: [lo,lt) < p, [lt,i) == p, (gt,hi] > p
                if a[i] < p:
                    a[lt], a[i] = a[i], a[lt]; lt += 1; i += 1
                elif a[i] > p:
                    a[i], a[gt] = a[gt], a[i]; gt -= 1
                else:
                    i += 1
            # the block [lt, gt] equals p and is already in its final place
            if lt - lo < hi - gt:
                stack.append((gt + 1, hi)); hi = lt - 1   # defer the larger side, loop on the smaller
            else:
                stack.append((lo, lt - 1)); lo = gt + 1
    return a
```

Three decisions in this code, each answering a real failure:

1. **Random pivot.** A fixed pivot (first or last element) turns a sorted or reverse-sorted input into the worst case: every partition peels off one item and the total is quadratic. Picking the pivot at random makes that outcome depend on your dice, not on the input.
2. **Three-way partition.** A two-way partition on an array of all-equal values puts everything on one side every time: quadratic again. Grouping the items equal to the pivot and *not touching them again* makes all-equal input a single pass. This is also exactly the "sort colors" problem.
3. **Recurse on the smaller side, loop on the larger.** The pending stack then never holds more than about `lg n` entries, so there is no recursion-depth failure on large inputs.

**Average cost, and what "average" means.** With a random pivot, the expected number of comparisons is `O(n log n)` on *every* input; the randomness is in your choices, not in the data. The CPython notes quantify the constant for random-pivot quicksort against the information-theoretic limit: about 39% more comparisons, and about 19% more with a median-of-three pivot (see Sources). Mergesort-style algorithms come much closer to the limit, which is one reason a library sort is a merge-based one.

**Not stable.** The swaps move equal items past each other. If a problem says "keep the original order of equals", quicksort is the wrong tool; use merge sort or the library sort.

---

## 5. Quickselect: The k-th Item Without Sorting

```python
def quickselect(a, k):
    """The k-th smallest item (k is 0-based). Average O(n). Does not change a."""
    if not 0 <= k < len(a):
        raise IndexError(k)
    a = list(a)
    lo, hi = 0, len(a) - 1
    while True:
        p = a[random.randint(lo, hi)]
        lt, i, gt = lo, lo, hi
        while i <= gt:
            if a[i] < p:
                a[lt], a[i] = a[i], a[lt]; lt += 1; i += 1
            elif a[i] > p:
                a[i], a[gt] = a[gt], a[i]; gt -= 1
            else:
                i += 1
        if k < lt:
            hi = lt - 1                          # the answer is among the smaller items
        elif k > gt:
            lo = gt + 1                          # the answer is among the larger items
        else:
            return p                             # k falls inside the block equal to the pivot
```

Same partition as quicksort, but after each pass it keeps only the one side that contains index `k`. Each pass is expected to leave a constant fraction of the work, so the total is a geometric sum: average `O(n)`. The worst case is still `O(n²)` with unlucky pivots; for a *guaranteed* linear bound there is a median-of-medians variant, which is rarely worth writing in an interview. Say that it exists and why you did not use it.

**k-th largest** is the `(n - k)`-th smallest in 0-based terms. Off-by-one here is the most common bug in the whole topic, so write `k_small = len(a) - k` and test it on `[3, 1, 2]` with `k = 1` (answer 3).

**Quickselect or a heap?** Quickselect needs all the data in memory and answers once. A min-heap of size `k` handles a stream and costs `O(n log k)`. If the prompt says "stream", "online" or "data too large to hold", it is the heap.

---

## 6. Counting Sort and Radix Sort: Beating `n log n` by Not Comparing

```python
def counting_sort_by(items, key, m):
    """Stable sort of items by an integer key in range(m). O(n + m)."""
    count = [0] * (m + 1)
    for x in items:
        count[key(x) + 1] += 1
    for d in range(m):
        count[d + 1] += count[d]          # count[d] is now the first output position for key d
    out = [None] * len(items)
    for x in items:                        # left to right keeps equal keys in their original order
        out[count[key(x)]] = x
        count[key(x)] += 1
    return out


def radix_sort(a, base=10):
    """Sort non-negative integers digit by digit, least significant first."""
    a = list(a)
    if not a:
        return a
    biggest = max(a)
    exp = 1
    while biggest // exp > 0:
        a = counting_sort_by(a, lambda x: (x // exp) % base, base)
        exp *= base
    return a
```

**Why radix sort works at all.** Sorting by the least significant digit first and the most significant digit last only gives a correct result because each pass is *stable*: a later, more significant pass cannot undo the order the earlier passes built among equal digits. This is the same fact as the two-pass multi-key sort in section 3, used on purpose. Replace the stable pass with an unstable one and radix sort is wrong.

**The cost is `O(d · (n + base))`** for `d` digits. That beats `n log n` only when `d` is small. Sorting `10^6` integers below `10^9` in base 10 takes 9 passes; in base `2^16` it takes 2. When the range is huge (a 64-bit hash) or the keys are floats, counting sort is the wrong tool. Negative numbers need an offset or a separate pass, which is why the code above asks for non-negative input.

**Counting sort alone** is the right answer to "sort ages", "sort characters", "sort exam scores 0–100": a key range far smaller than `n`.

---

## 7. Pitfalls

1. **Using `<=` in a merge that must be stable.** One character changes stability. Equal items from the right half now jump ahead.
2. **Fixed pivot on sorted input, or two-way partition on duplicates.** Both give quadratic time. The fix is the random pivot and the three-way partition above.
3. **Sorting when a selection is enough.** `sorted(a)[k]` costs `n log n`; quickselect or a size-`k` heap is cheaper.
4. **Comparator that is not a strict ordering.** A comparison that says "a before b" and also "b before a", or fails to be transitive, makes any sort behave unpredictably. In Python prefer a `key` function; `functools.cmp_to_key` exists for the cases where you must express the order as a comparison (see Sources). "Largest number" (concatenate to get the biggest number) is the standard case, and its comparison is `a+b` against `b+a` as strings.
5. **Sorting by a key you recompute inside the comparison.** A `key` function is evaluated once per item; a comparator is called `O(n log n)` times. Expensive derived keys belong in `key`.
6. **Mutating the caller's list.** Interview prompts often say "do not modify the input". Every function above copies first.
7. **Forgetting that a library sort is already stable and fast.** In an interview, call `sorted` for the sorting step of a problem and spend your time on the idea. Write a sort out only when the sort *is* the question.
8. **Counting sort on a huge key range.** `m` of `10^9` allocates a `10^9`-slot array. The check is `m` against `n`.

---

## 8. Drills

1. Sort `[(2,'a'), (1,'b'), (2,'c'), (1,'d')]` by number only, by hand, with a stable sort. Then say what an unstable sort could return that a stable one cannot.
2. Count the inversions in `[5, 3, 4, 1, 2]` by hand, then by tracing the merge.
3. Change one character in `merge_sort` to break stability, and write the input that exposes it.
4. Run `quicksort` on 5,000 equal values with the three-way partition replaced by a two-way one. What happens to the running time, and why?
5. Find the 2nd largest of `[3, 1, 2]` with quickselect. What `k` do you pass?
6. State when you would choose a size-`k` heap over quickselect, in one sentence.
7. Radix-sort `[170, 45, 75, 90, 802, 24, 2, 66]` by hand, writing the list after each digit pass.
8. For each of these, say the sort you would use and why: 50 million log lines by timestamp on one machine with 8 GB of memory; one million exam scores from 0 to 100; a linked list of 200,000 nodes.

---

## 9. Homework

Do these in order, and for each one write the one-line reason a sort or selection is the right tool:

1. **Sort an Array** (LeetCode 912). Write it with your own `quicksort`, then with `merge_sort`, and compare the running time on already-sorted input.
2. **Kth Largest Element in an Array** (215). Solve with quickselect, then with a heap.
3. **Sort Colors** (75). One pass, in place, using the three-way partition.
4. **Largest Number** (179). The comparator problem.
5. **Merge Intervals** (56). Sort, then sweep.
6. **Count of Smaller Numbers After Self** (315) and **Reverse Pairs** (493). Both are the inversion-counting merge with a changed condition.
7. **Maximum Gap** (164). The one where the expected answer is a radix or bucket sort.
8. **Sort List** (148). Merge sort on a linked list, in `O(1)` extra space.

---

## Sources and further reading

Read and used for this lesson (accessed 26 November 2026):

- Python HOWTO, "Sorting Techniques", docs.python.org/3/howto/sorting.html. Read in full. Used for: sorts are guaranteed stable; the two-pass multi-key sort by sorting on the secondary key first; `key` functions are applied once per record; `cmp_to_key` for comparison-style orders.
- CPython source notes on its sort, `Objects/listsort.txt` in github.com/python/cpython (main branch). Read in full. Used for: `lg(n!)` as the information-theoretic limit; the figure of about 1% above it on random data; random-pivot quicksort about 39% and median-of-three about 19% above that limit; the sort described as a stable natural merge sort.

Not consulted: any textbook or paper for the quicksort, quickselect or radix-sort complexity claims. They are stated here as the standard results and are backed by the tests in `test/lesson_code/ds26_check.py` for correctness, not for running time. The median-of-medians variant is named but not shown. The expected-`O(n)` argument for quickselect is a sketch, not a proof. The LeetCode problem numbers are from memory of the problem list and should be checked against the site before you rely on them.

**Last reviewed:** 26 November 2026.
