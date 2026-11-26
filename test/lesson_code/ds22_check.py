"""Runs the python code blocks from data/new_lessons/ds22-math-sampling.md against brute-force checks."""
import re, sys, random, math, itertools
from collections import Counter
src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
ns = {}
for b in blocks:
    exec(b, ns)
fast_pow, mod_inv, mod_inv_any, make_ncr, sieve = ns['fast_pow'], ns['mod_inv'], ns['mod_inv_any'], ns['make_ncr'], ns['sieve']
catalan, reservoir_sample, fisher_yates, shuffle_biased = ns['catalan'], ns['reservoir_sample'], ns['fisher_yates'], ns['shuffle_biased']
MOD = 10**9 + 7
random.seed(22)

# fast_pow vs builtin, including exponent 0 and modulus 1
for _ in range(500):
    b = random.randint(0, 10**12); e = random.randint(0, 200); m = random.choice([1, 2, 7, 1000, MOD])
    assert fast_pow(b, e, m) == pow(b, e, m), (b, e, m)

# mod_inv with prime modulus vs search; division trap
for p in (2, 3, 7, 13, 101):
    for b in range(1, p):
        inv = mod_inv(b, p)
        assert (b * inv) % p == 1 and 0 <= inv < p, (b, p)
for _ in range(300):
    b = random.randint(1, 10**6); q = random.randint(0, 10**6); a = b * q
    assert (a * mod_inv(b, MOD)) % MOD == (a // b) % MOD, (a, b)

# general modular inverse (modulus need not be prime)
for m in range(2, 40):
    for b in range(1, 3 * m):
        if math.gcd(b, m) == 1:
            inv = mod_inv_any(b, m)
            assert (b * inv) % m == 1 and 0 <= inv < m, (b, m)
        else:
            try:
                mod_inv_any(b, m); raise SystemExit("no error for non-coprime %d %d" % (b, m))
            except ValueError:
                pass

# nCr table vs math.comb, out-of-range arguments
ncr = make_ncr(200, MOD)
for _ in range(500):
    n = random.randint(0, 200); r = random.randint(-2, n + 2)
    exp = math.comb(n, r) % MOD if 0 <= r <= n else 0
    assert ncr(n, r) == exp, (n, r)

# sieve vs trial division
def is_prime(x):
    return x >= 2 and all(x % d for d in range(2, int(x ** 0.5) + 1))
for n in (0, 1, 2, 3, 10, 97, 100, 541):
    assert sieve(n) == [x for x in range(n + 1) if is_prime(x)], n

# Catalan: formula == recurrence == brute-force count of balanced strings
def balanced(n):
    c = 0
    for s in itertools.product('()', repeat=2 * n):
        d = 0; ok = True
        for ch in s:
            d += 1 if ch == '(' else -1
            if d < 0: ok = False; break
        if ok and d == 0: c += 1
    return c
cat = [1]
for n in range(1, 12):
    cat.append(sum(cat[i] * cat[n - 1 - i] for i in range(n)))
for n in range(0, 12):
    assert catalan(n) == cat[n], n
for n in range(0, 6):
    assert catalan(n) == balanced(n), n

# Exact distribution checks: enumerate every possible sequence of random draws
def run_all(ranges, fn):
    """Call fn(randrange) once for every combination of draws; randrange(m) must be asked in the given order."""
    results = []
    for choices in itertools.product(*[range(r) for r in ranges]):
        it = iter(choices); idx = [0]
        def rr(m):
            assert m == ranges[idx[0]], (m, ranges, idx[0])
            idx[0] += 1
            return next(it)
        results.append(fn(rr))
        assert idx[0] == len(ranges), "unused draws"
    return results

# Reservoir sampling: every k-subset equally likely, every item included with probability k/N
for N, k in [(5, 1), (6, 2), (6, 3), (7, 2), (4, 4), (3, 5)]:
    stream = list(range(N))
    ranges = [c for c in range(k + 1, N + 1)]
    res = run_all(ranges, lambda rr: reservoir_sample(stream, k, rr))
    total = len(res)
    assert all(len(r) == min(k, N) for r in res)
    subsets = Counter(frozenset(r) for r in res)
    if N > k:
        assert len(subsets) == math.comb(N, k) and len(set(subsets.values())) == 1, (N, k, subsets)
        incl = Counter(x for r in res for x in r)
        assert all(incl[x] * N == total * k for x in stream), (N, k, incl)
    else:
        assert set(map(frozenset, res)) == {frozenset(stream)}

# Fisher-Yates: all n! permutations equally likely; the biased "swap with any index" shuffle is not
for n in range(1, 6):
    perms = Counter(tuple(p) for p in run_all(list(range(n, 1, -1)), lambda rr: fisher_yates(list(range(n)), rr)))
    assert len(perms) == math.factorial(n) and len(set(perms.values())) == 1, n
n = 4
biased = Counter(tuple(p) for p in run_all([n] * n, lambda rr: shuffle_biased(list(range(n)), rr)))
assert len(set(biased.values())) > 1, "biased shuffle unexpectedly uniform"
assert n ** n % math.factorial(n) != 0   # 256 outcomes cannot split evenly over 24 permutations
print("ds22 code checks passed")
