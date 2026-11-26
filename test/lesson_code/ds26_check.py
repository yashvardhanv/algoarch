"""Runs the python blocks from data/new_lessons/ds26-sorting-selection.md against reference checks."""
import re, sys, random, collections
src = open(sys.argv[1], encoding='utf-8').read()
ns = {}
for b in re.findall(r"```python\n(.*?)```", src, re.S):
    exec(b, ns)
merge_sort, count_inversions = ns['merge_sort'], ns['count_inversions']
quicksort, quickselect = ns['quicksort'], ns['quickselect']
counting_sort_by, radix_sort = ns['counting_sort_by'], ns['radix_sort']
random.seed(11)

def arr(lo=-6, hi=6, mx=25):
    return [random.randint(lo, hi) for _ in range(random.randint(0, mx))]

# sorts equal the reference, including heavy duplicates
for _ in range(500):
    a = arr(); orig = a[:]
    assert merge_sort(a) == sorted(a), a
    assert quicksort(a) == sorted(a), a
    assert a == orig, "input must not be mutated"
assert quicksort([5] * 5000) == [5] * 5000            # all equal must not degrade or recurse deeply
assert quicksort(list(range(5000))) == list(range(5000))
assert quicksort(list(range(5000, 0, -1))) == list(range(1, 5001))

# merge sort is stable: sort (key, tag) pairs by key only
for _ in range(300):
    recs = [(random.randint(0, 3), i) for i in range(random.randint(0, 20))]
    assert merge_sort(recs, key=lambda r: r[0]) == sorted(recs, key=lambda r: r[0]), recs

# inversion count vs O(n^2)
for _ in range(400):
    a = arr(); naive = sum(1 for i in range(len(a)) for j in range(i + 1, len(a)) if a[i] > a[j])
    assert count_inversions(a) == naive, a

# quickselect (k is 0-based) vs sorted, duplicates included
for _ in range(600):
    a = arr();
    if not a: continue
    k = random.randrange(len(a)); orig = a[:]
    assert quickselect(a, k) == sorted(a)[k], (a, k)
    assert a == orig
try:
    quickselect([1, 2], 2); assert False
except IndexError:
    pass

# counting sort by digit is stable; radix sort vs sorted on non-negative ints
for _ in range(300):
    recs = [(random.randint(0, 9), i) for i in range(random.randint(0, 25))]
    assert counting_sort_by(recs, lambda r: r[0], 10) == sorted(recs, key=lambda r: r[0]), recs
for _ in range(300):
    a = [random.randint(0, 10**random.randint(0, 6)) for _ in range(random.randint(0, 30))]
    assert radix_sort(a) == sorted(a), a
print("ds26 code checks passed")
