"""Runs the python code blocks from data/new_lessons/ds24.md against brute-force checks."""
import re, sys, random
src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
ns = {}
for b in blocks:
    exec(b, ns)
fmp, missing_number, disappeared, dups, dup_swap, dup_floyd, dups_sign, mismatch = (
    ns['first_missing_positive'], ns['missing_number'], ns['find_disappeared_numbers'],
    ns['find_duplicates'], ns['find_duplicate_swap'], ns['find_duplicate_floyd'],
    ns['find_duplicates_sign'], ns['set_mismatch'])
random.seed(24)

# First missing positive vs set scan; values include negatives, zero and large numbers
for _ in range(1000):
    n = random.randint(1, 10)
    a = [random.choice([random.randint(-3, n + 3), random.randint(1, n)]) for _ in range(n)]
    s = set(a); exp = 1
    while exp in s: exp += 1
    assert fmp(list(a)) == exp, a
assert fmp([3, 4, -1, 1]) == 2 and fmp([1, 2, 0]) == 3 and fmp([7, 8, 9, 11, 12]) == 1 and fmp([2, 2]) == 1

# Missing number in [0..n] (n values, all distinct)
for _ in range(500):
    n = random.randint(1, 10)
    full = list(range(n + 1)); miss = random.choice(full)
    a = [x for x in full if x != miss]; random.shuffle(a)
    assert missing_number(list(a)) == miss, (a, miss)

# All disappeared numbers: arbitrary multiplicities in 1..n
for _ in range(1000):
    n = random.randint(1, 10)
    a = [random.randint(1, n) for _ in range(n)]
    exp = [v for v in range(1, n + 1) if v not in set(a)]
    assert sorted(disappeared(list(a))) == exp, a

# Duplicates: each value appears at most twice, length n, values 1..n
for _ in range(1000):
    n = random.randint(1, 10)
    pool = list(range(1, n + 1)) * 2
    a = random.sample(pool, n)
    exp = sorted(v for v in set(a) if a.count(v) == 2)
    assert sorted(dups(list(a))) == exp, a
    b = list(a)
    assert sorted(dups_sign(b)) == exp, a
    assert b == a, "sign method must restore the array"

# The single repeated value in n + 1 numbers drawn from 1..n (it may repeat more than twice)
for _ in range(1000):
    n = random.randint(1, 9)
    d = random.randint(1, n); c = random.randint(2, n + 1)
    others = random.sample([v for v in range(1, n + 1) if v != d], n + 1 - c)
    a = [d] * c + others; random.shuffle(a)
    assert dup_swap(list(a)) == d, a
    b = list(a)
    assert dup_floyd(b) == d, a
    assert b == a, "Floyd version must not modify the input"

# Set mismatch: a permutation of 1..n with one value overwritten by another
for _ in range(500):
    n = random.randint(2, 10)
    a = list(range(1, n + 1)); random.shuffle(a)
    i, j = random.sample(range(n), 2)
    missing_val = a[i]; a[i] = a[j]
    assert mismatch(list(a)) == [a[j], missing_val], (a,)
print("ds24 code checks passed")
