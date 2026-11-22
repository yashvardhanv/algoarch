# Lesson 22 — Math, Number Theory & Reservoir Sampling

> **Priority:** ★★★★☆ (Google, Bloomberg, Databricks standard rounds)  
> **Estimated Study Time:** 45 minutes  
> **Key Skills:** Fast Modular Exponentiation, Modular Inverse via Fermat's Little Theorem, Sieve of Eratosthenes, Reservoir Sampling on infinite streams, Catalan numbers.

---

## 1. Modular Arithmetic for Interviews

Whenever a problem ends with: *"Return answer modulo 10^9 + 7"*:
- Addition: `(a + b) % M = ((a % M) + (b % M)) % M`
- Multiplication: `(a * b) % M = ((a % M) * (b % M)) % M`
- **Division Trap:** `(a / b) % M` is NOT `((a % M) / (b % M)) % M`. Division by `b` is multiplication by the modular multiplicative inverse `b^(M - 2) % M` (by Fermat's Little Theorem, where `M` is prime).

```python
MOD = 10**9 + 7

def mod_inv(b: int) -> int:
    return pow(b, MOD - 2, MOD)

def nCr(n: int, r: int) -> int:
    if r < 0 or r > n: return 0
    num = denom = 1
    for i in range(r):
        num = (num * (n - i)) % MOD
        denom = (denom * (i + 1)) % MOD
    return (num * mod_inv(denom)) % MOD
```

---

## 2. Reservoir Sampling (Streaming Algorithm)

**Problem:** Select `k` random elements uniformly from a data stream of unknown, massive length `N` (too large to fit in memory) using `O(k)` space in a single pass.

```python
import random

class ReservoirSampler:
    def __init__(self, k: int):
        self.k = k
        self.reservoir = []
        self.count = 0

    def feed(self, item):
        self.count += 1
        if len(self.reservoir) < self.k:
            self.reservoir.append(item)
        else:
            # Replace item with probability k / count
            idx = random.randint(0, self.count - 1)
            if idx < self.k:
                self.reservoir[idx] = item

    def get_sample(self):
        return self.reservoir
```

**Proof of Uniform Probability:**
At step `N`, probability item `i` is in reservoir is exactly `k / N`.
Induction step: At step `N + 1`, item `i` remains in reservoir if new element does not displace it:
`P(stays) = (k / N) * [1 - (k / (N + 1)) * (1 / k)] = (k / N) * [N / (N + 1)] = k / (N + 1)`. Proof complete.
