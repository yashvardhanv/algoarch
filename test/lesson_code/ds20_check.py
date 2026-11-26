"""Runs the python code blocks from data/new_lessons/ds20-segment-trees.md against brute-force checks."""
import re, sys, random
src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
ns = {}
for b in blocks:
    exec(b, ns)
Fenwick, MinSegTree, LazySegTree, count_inversions = ns['Fenwick'], ns['MinSegTree'], ns['LazySegTree'], ns['count_inversions']
INF = float('inf')
random.seed(20)

# Fenwick: random point adds, prefix and range sums, and lower_bound on non-negative data
for _ in range(300):
    n = random.randint(1, 20)
    arr = [0] * n
    f = Fenwick(n)
    for _op in range(40):
        i = random.randrange(n); d = random.randint(0, 5)
        arr[i] += d; f.add(i, d)
        l = random.randrange(n); r = random.randrange(l, n)
        assert f.prefix(r) == sum(arr[:r + 1]), (arr, r)
        assert f.range_sum(l, r) == sum(arr[l:r + 1]), (arr, l, r)
        total = sum(arr)
        t = random.randint(1, max(1, total + 2))
        run, exp = 0, n
        for j, v in enumerate(arr):
            run += v
            if run >= t:
                exp = j; break
        assert f.lower_bound(t) == exp, (arr, t, f.lower_bound(t), exp)
# negative deltas are fine for sums
f = Fenwick(5)
for i, d in enumerate([5, -2, 7, 0, -1]): f.add(i, d)
assert f.range_sum(0, 4) == 9 and f.range_sum(1, 2) == 5

# MinSegTree: non power of two sizes, point sets, range min
for _ in range(300):
    n = random.randint(1, 20)
    arr = [random.randint(-9, 9) for _ in range(n)]
    st = MinSegTree(arr)
    for _op in range(40):
        if random.random() < 0.4:
            i = random.randrange(n); v = random.randint(-9, 9)
            arr[i] = v; st.set(i, v)
        l = random.randrange(n); r = random.randrange(l, n)
        assert st.query(l, r) == min(arr[l:r + 1]), (arr, l, r)

# LazySegTree: range add + range sum vs plain list
for _ in range(300):
    n = random.randint(1, 20)
    arr = [random.randint(-5, 5) for _ in range(n)]
    st = LazySegTree(arr)
    for _op in range(40):
        l = random.randrange(n); r = random.randrange(l, n)
        if random.random() < 0.5:
            v = random.randint(-4, 4)
            for j in range(l, r + 1): arr[j] += v
            st.range_add(l, r, v)
        else:
            assert st.range_sum(l, r) == sum(arr[l:r + 1]), (arr, l, r)

# Inversions (with duplicates and huge values) vs O(n^2)
for _ in range(300):
    n = random.randint(0, 15)
    a = [random.choice([random.randint(-3, 3), random.randint(-10**9, 10**9)]) for _ in range(n)]
    assert count_inversions(a) == sum(1 for i in range(n) for j in range(i + 1, n) if a[i] > a[j]), a
assert count_inversions([3, 1, 2]) == 2 and count_inversions([2, 2, 2]) == 0

# Larger sizes run fast and agree (guards accidental O(n) per operation is not tested; correctness only)
n = 5000; arr = [random.randint(0, 100) for _ in range(n)]
st = LazySegTree(arr); st.range_add(0, n - 1, 1)
assert st.range_sum(0, n - 1) == sum(arr) + n
print("ds20 code checks passed")
