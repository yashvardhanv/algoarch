# Lesson 23 — String Algorithms: KMP, Rabin-Karp & Rolling Hash

> **Priority:** ★★★★☆ (Common string matching & palindrome bar)  
> **Estimated Study Time:** 50 minutes  
> **Key Skills:** Knuth-Morris-Pratt (KMP) Longest Prefix Suffix (LPS), Rabin-Karp polynomial rolling hash, Manacher's algorithm for palindromes in O(N).

---

## 1. The Naive Matching Trap

Searching for pattern of length `M` in text of length `N`:
- Naive nested comparison: `O(N * M)` worst case (e.g. text `"AAAAAAAAAB"`, pattern `"AAAB"`).
- At `N = 10^5` and `M = 10^4`, naive does `10^9` operations and gets Time Limit Exceeded (TLE).
- **KMP and Rabin-Karp achieve guaranteed `O(N + M)` time.**

---

## 2. KMP: Longest Prefix Suffix (LPS) Table

The genius of KMP is never moving the text pointer backward. When a mismatch occurs at `pattern[j]`, the LPS table tells us the longest proper prefix that is also a suffix up to index `j - 1`, skipping redundant comparisons.

```python
def build_lps(pattern: str) -> list[int]:
    m = len(pattern)
    lps = [0] * m
    length = 0
    i = 1

    while i < m:
        if pattern[i] == pattern[length]:
            length += 1
            lps[i] = length
            i += 1
        else:
            if length != 0:
                length = lps[length - 1]
            else:
                lps[i] = 0
                i += 1
    return lps

def kmp_search(text: str, pattern: str) -> list[int]:
    n, m = len(text), len(pattern)
    if m == 0: return []
    lps = build_lps(pattern)
    matches = []
    i = j = 0

    while i < n:
        if text[i] == pattern[j]:
            i += 1
            j += 1
            if j == m:
                matches.append(i - j)
                j = lps[j - 1]
        else:
            if j != 0:
                j = lps[j - 1]
            else:
                i += 1
    return matches
```

---

## 3. Rabin-Karp: Polynomial Rolling Hash

Computes hash of sliding window in `O(1)` time per character shift:
`hash = (hash - old_char * base^(M-1)) * base + new_char (mod MOD)`
Use a large prime modulus (e.g., `10^9 + 7` or double-hash with two distinct primes) to eliminate malicious hash collisions.
