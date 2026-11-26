# Lesson 22 — Math, Number Theory & Reservoir Sampling

> **Priority:** ★★★★☆ — small toolkit, repeated constantly: "answer modulo 10^9 + 7", "pick uniformly at random", "count primes".
>
> **Study time:** 45 minutes. **Do this after:** Lesson 14 (1D dynamic programming).
> **Level:** advanced. Optional for a crash plan; worth doing if your target loops include hard rounds.

Three families of problem turn up again and again and are not solved by a data structure. Counting
problems that ask for the answer modulo a prime (you must divide without dividing). Number problems
that need a sieve or fast exponentiation. And randomness problems where "random" has a precise
meaning: uniform over a stream you cannot store, or uniform over all orderings. In each, the easy
version is subtly wrong, and the check is a short argument you can say out loud.

---

## 1. Mental Model

> **Do arithmetic in a ring where results stay small, and when you need uniform randomness, count
> the equally likely outcomes and show each result gets the same number of them.**

- Modular arithmetic: `+`, `-`, `*` commute with taking the remainder. Division does not; it is
  multiplication by an inverse, which exists only when the divisor shares no factor with the modulus.
- Randomness: an algorithm is uniform if every outcome is produced by the same number of random-draw
  sequences. That is how you prove it, and also how the checks for this lesson test it, by enumerating
  every draw sequence for tiny inputs.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "return the answer modulo `10^9 + 7`" | reduce after every `+`, `*`; never reduce a division, multiply by an inverse |
| `n` and `r` up to `10^5` or `10^6`, many `nCr` queries | factorial and inverse-factorial tables |
| "`x^e mod m`", `e` is huge | fast exponentiation, `O(log e)` |
| "count primes below `n`", `n` up to a few million | sieve of Eratosthenes |
| "pick `k` items uniformly from a stream of unknown length" or "do not store the stream" | reservoir sampling |
| "shuffle an array so every ordering is equally likely" | Fisher-Yates |
| "number of valid bracket strings", "ways to triangulate", "binary trees with `n` nodes" | Catalan number |

---

## 3. Modular Arithmetic

```python
def fast_pow(base, exp, mod):
    """base ** exp % mod in O(log exp), by squaring. exp >= 0."""
    result = 1 % mod
    base %= mod
    while exp:
        if exp & 1:
            result = result * base % mod
        base = base * base % mod
        exp >>= 1
    return result

def mod_inv(b, p):
    """Inverse of b modulo a PRIME p (Fermat: b^(p-1) = 1, so b^(p-2) is the inverse). b not a multiple of p."""
    return fast_pow(b, p - 2, p)

def mod_inv_any(b, m):
    """Inverse of b modulo any m, by the extended Euclidean algorithm. Raises ValueError if gcd(b, m) != 1."""
    old_r, r = b % m, m
    old_s, s = 1, 0
    while r:
        q = old_r // r
        old_r, r = r, old_r - q * r
        old_s, s = s, old_s - q * s
    if old_r != 1:
        raise ValueError("not invertible")
    return old_s % m
```

**The division trap.** `(a / b) % M` is not `((a % M) / (b % M)) % M`. When `b` divides `a`, the
correct value is `a * mod_inv(b, M) % M`, with `M` prime and `b` not a multiple of `M`. Fermat's
trick needs a **prime** modulus; with a composite modulus use `mod_inv_any`. (Python 3.8 and later
also has `pow(b, -1, m)`.)

**Combinations, many queries.** Build `fact[i]` and `inv_fact[i]` once; each `nCr` is then three
multiplications. Computing one inverse and walking down avoids `n` modular exponentiations.

```python
def make_ncr(n_max, mod):
    """Returns ncr(n, r) mod a prime `mod`, valid for n <= n_max. Out of range r gives 0."""
    fact = [1] * (n_max + 1)
    for i in range(1, n_max + 1):
        fact[i] = fact[i - 1] * i % mod
    inv_fact = [1] * (n_max + 1)
    inv_fact[n_max] = pow(fact[n_max], mod - 2, mod)
    for i in range(n_max, 0, -1):
        inv_fact[i - 1] = inv_fact[i] * i % mod      # 1/(i-1)! = i / i!
    def ncr(n, r):
        if r < 0 or r > n:
            return 0
        return fact[n] * inv_fact[r] % mod * inv_fact[n - r] % mod
    return ncr
```

The old habit of computing `nCr` with a loop of `r` multiplications plus one inverse is fine for a
single query, and wrong in cost for `10^5` queries.

**Catalan numbers.** `C(n) = (2n choose n) / (n + 1)`, and `C(0) = 1`, `C(1) = 1`, `C(2) = 2`,
`C(3) = 5`, `C(4) = 14`. The same sequence counts balanced bracket strings of `n` pairs, binary trees
with `n` nodes, and triangulations of an `(n + 2)`-gon. Modulo a prime use
`ncr(2n, n) * mod_inv(n + 1, p)`.

```python
import math

def catalan(n):
    """Exact Catalan number."""
    return math.comb(2 * n, n) // (n + 1)
```

---

## 4. Sieve of Eratosthenes

Start with every number marked prime; for each prime `p`, cross out its multiples starting at
`p * p`, because a smaller multiple `p * q` with `q < p` has already been crossed out by `q`'s prime
factors. `O(n log log n)` time, `O(n)` memory.

```python
def sieve(n):
    """All primes <= n."""
    if n < 2:
        return []
    is_p = bytearray([1]) * (n + 1)
    is_p[0] = is_p[1] = 0
    p = 2
    while p * p <= n:
        if is_p[p]:
            is_p[p * p::p] = bytearray(len(range(p * p, n + 1, p)))
        p += 1
    return [i for i in range(n + 1) if is_p[i]]
```

---

## 5. Reservoir Sampling

**Problem:** keep `k` items, chosen uniformly, from a stream of unknown length in one pass and
`O(k)` memory. The random source is a parameter here so the check can enumerate its choices.

```python
import random

def reservoir_sample(stream, k, randrange=random.randrange):
    """k items chosen uniformly from the stream (all of it, if it has fewer than k)."""
    reservoir = []
    for count, item in enumerate(stream, 1):         # count = items seen so far, including this one
        if count <= k:
            reservoir.append(item)
        else:
            j = randrange(count)                      # uniform in [0, count)
            if j < k:                                 # happens with probability k / count
                reservoir[j] = item                   # and then j is a uniform slot to evict
    return reservoir
```

**Why it is uniform.** Claim: after `N >= k` items, each item is in the reservoir with probability
`k / N`. For `N = k` that is 1. Step from `N` to `N + 1`:

- the new item enters with probability `k / (N + 1)`, by construction;
- an old item is in the reservoir with probability `k / N`; it is evicted only if the new item enters
  (`k / (N + 1)`) *and* picks that slot (`1 / k`), so it is evicted with probability `1 / (N + 1)`
  and survives with probability `N / (N + 1)`;
- so an old item is present with probability `(k / N) * (N / (N + 1)) = k / (N + 1)`.

The check enumerates every possible sequence of draws for small streams and confirms every `k`-subset
comes out equally often.

**Shuffle.** Fisher-Yates walks from the end, swapping each position with a random position at or
before it. The tempting variant swaps with *any* position.

```python
def fisher_yates(a, randrange=random.randrange):
    """In-place uniform shuffle: all len(a)! orderings are equally likely."""
    for i in range(len(a) - 1, 0, -1):
        j = randrange(i + 1)                          # 0..i inclusive
        a[i], a[j] = a[j], a[i]
    return a

def shuffle_biased(a, randrange=random.randrange):
    """WRONG: swap each position with any position. Not uniform."""
    n = len(a)
    for i in range(n):
        j = randrange(n)
        a[i], a[j] = a[j], a[i]
    return a
```

Fisher-Yates makes `n * (n-1) * ... * 2 = n!` equally likely draw sequences, and each gives a distinct
ordering. The biased version makes `n^n` draw sequences. For `n >= 3`, `n^n` is not divisible by
`n!` (`n - 1` shares no prime factor with `n`, so it cannot divide a power of `n`), so the
orderings cannot all be equally likely. The check confirms this for `n = 4`: 256 outcomes over 24 orderings.

---

## 6. Pitfalls Checklist

1. **Dividing under a modulus** without an inverse.
2. **Fermat inverse with a composite modulus**, or when the value is a multiple of the modulus.
3. **Forgetting a final `% M`** after subtraction: `(a - b) % M` is fine in Python but negative in languages with truncating remainder.
4. **Overflow in other languages**: the product of two values below `10^9 + 7` needs 64 bits. Python does not overflow, but say it.
5. **Sieve starting inner loop at `2 * p`** instead of `p * p`: correct but needlessly slower.
6. **Reservoir off-by-one**: drawing in `[0, count - 1)` or comparing `j <= k` skews the probabilities. Draw in `[0, count)` and test `j < k`.
7. **Biased shuffle**: swapping with any index, or choosing `j` from `[0, i)` (which can never leave an element in place and is not uniform either).
8. **Calling a random-number function with modulo bias** when the range does not divide evenly: say that you would use a library routine that handles it.

---

## 7. Drills

1. Why is `(a / b) % M` not `((a % M) / (b % M)) % M`? Give the correct computation when `b` divides `a`.
2. For which moduli does the Fermat inverse work, and what do you use otherwise?
3. What is `fast_pow(3, 13, 1000)` by hand, using the binary form of 13?
4. Why does the sieve start crossing out at `p * p`?
5. In reservoir sampling, why is the new item admitted with probability `k / count` and not `1 / count`?
6. Prove that after step `N + 1` an old item stays with probability `N / (N + 1)`.
7. Why is `shuffle_biased` not uniform for `n = 3`? (Count draw sequences and orderings.)
8. List the five balanced bracket strings with three pairs and match them to `C(3) = 5`.

---

## 8. Homework

Solve these in order. Names are common problem titles; numbers are LeetCode's.

1. **Pow(x, n)** (50) — fast exponentiation, including negative `n`.
2. **Count Primes** (204) — the sieve.
3. **Unique Paths** (62) — solve with DP, then again as `nCr` with the table above.
4. **Generate Parentheses** (22) — then count the results and compare with `C(n)`.
5. **Linked List Random Node** (382) — reservoir sampling with `k = 1`.
6. **Shuffle an Array** (384) — Fisher-Yates.
7. **Count Good Numbers** (1922) — fast exponentiation under a modulus.

Then write the reservoir proof on paper without looking, in four lines.

---

## Further reading

The standard references are CLRS (number-theoretic algorithms; the randomised algorithms chapter) and
Knuth's *The Art of Computer Programming*, volume 2, for sampling and shuffling. They were not
consulted while writing this revision: the code here was written from the algorithms themselves, and
the checks compare it with Python's built-in `pow` and `math.comb`, with trial division, with direct counting of
bracket strings, and with exhaustive enumeration of every random-draw sequence for small cases.

*Last reviewed: 2026-11-26.*
