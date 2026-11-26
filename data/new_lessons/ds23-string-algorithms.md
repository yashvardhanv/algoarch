# Lesson 23 — String Algorithms: KMP, Rabin-Karp & Rolling Hash

> **Priority:** ★★★★☆ — string-matching and palindrome questions have standard linear-time answers; knowing them separates "I can code it" from "I can code it in `O(n + m)`".
>
> **Study time:** 50 minutes. **Do this after:** Lesson 3 (two pointers) and Lesson 4 (sliding window).
> **Level:** advanced. Optional for a crash plan; worth doing if your target loops include hard rounds.

Finding a pattern of length `m` inside a text of length `n` by trying every start position costs
`O(n * m)` in the worst case. For `n = 10^5` and `m = 10^4` that is roughly `9 * 10^8` character
comparisons. This lesson gives you two ways to do it in linear time (KMP, which never re-reads text,
and Rabin-Karp, which compares fingerprints), and then shows that the machinery behind KMP also
solves several "prefix is also a suffix" problems, and that palindromes have their own linear-time
algorithm (Manacher).

---

## 1. Mental Model

> **When a match attempt fails after matching some characters, you already know what the text
> looked like. Reuse that knowledge instead of starting over.**

- **KMP** remembers it as a number: the *prefix function* `pi[i]` is the length of the longest
  proper prefix of the pattern that is also a suffix of `pattern[0..i]`. After a mismatch following `k`
  matched characters, the text still ends with the first `pi[k-1]` pattern characters, so resume there.
  The text pointer never moves back.
- **Rabin-Karp** remembers it as a *fingerprint*: the hash of the current window, updated in `O(1)`
  as the window slides. Equal hash means "maybe equal"; you confirm with a direct comparison.
- **Manacher** remembers palindromes already found: inside a big palindrome, the left half's
  palindromes mirror into the right half.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "find all occurrences of a pattern in a text", worst case matters | **KMP** |
| "does any window of length `m` equal / duplicate another" (many patterns, or many windows) | **Rolling hash** |
| "is the string a repetition of a smaller block" | **Prefix function**: `n - pi[n-1]` is the candidate block length |
| "shortest palindrome you can make by adding characters in front" | **Prefix function on `s + '#' + reverse(s)`** |
| "longest palindromic substring" in linear time | **Manacher** (expand-around-centre is `O(n^2)` and is usually accepted first) |
| "longest repeated substring" | **Binary search on length + rolling hash** |
| short pattern, one-off search in a real program | the library's search; say so, then show you know how it works |

---

## 3. KMP: the Prefix Function

```python
def prefix_function(p):
    """pi[i] = length of the longest proper prefix of p that is also a suffix of p[:i+1]."""
    pi = [0] * len(p)
    k = 0
    for i in range(1, len(p)):
        while k and p[i] != p[k]:
            k = pi[k - 1]                 # fall back to the next shorter border
        if p[i] == p[k]:
            k += 1
        pi[i] = k
    return pi

def kmp_search(text, pat):
    """Start indices of every occurrence of pat in text, overlaps included. Empty pattern: no matches."""
    m = len(pat)
    if m == 0:
        return []
    pi = prefix_function(pat)
    out = []
    k = 0                                 # characters of pat currently matched
    for i, ch in enumerate(text):
        while k and ch != pat[k]:
            k = pi[k - 1]
        if ch == pat[k]:
            k += 1
        if k == m:
            out.append(i - m + 1)
            k = pi[k - 1]                 # continue, allowing overlapping matches
    return out
```

**Why it is linear.** `k` increases by at most 1 per text character and the `while` loop only
decreases it, so the total number of decreases is at most the total number of increases, `O(n)`. The
same argument for `prefix_function` gives `O(m)`.

**Hand trace of `prefix_function("aabaaab")`**: `[0, 1, 0, 1, 2, 2, 3]`. At index 5, `k = 2` and
`p[5] = 'a'` does not equal `p[2] = 'b'`, so fall back to `pi[1] = 1`; `p[1] = 'a'` matches, `k`
becomes 2. At index 6, `p[6] = 'b'` equals `p[2] = 'b'`, so `k = 3`.

Visual (planned): the pattern drawn twice, with arrows showing the fall-back from a mismatch to the
border given by `pi[k-1]`.

### What else the prefix function gives you

```python
def repeated_substring_pattern(s):
    """True if s is some block repeated two or more times."""
    n = len(s)
    border = prefix_function(s)[-1]       # longest proper prefix that is also a suffix
    block = n - border                    # the only candidate period
    return border > 0 and n % block == 0

def shortest_palindrome(s):
    """Shortest palindrome formed by adding characters only in front of s. Assumes '#' is not in s."""
    if not s:
        return s
    pi = prefix_function(s + '#' + s[::-1])
    longest_pal_prefix = pi[-1]           # the separator stops a border from running past s
    return s[::-1][:len(s) - longest_pal_prefix] + s
```

For the repeated block, if `s` is a block `B` repeated `r >= 2` times, then `s[B:]` equals `s[:-B]`,
so `n - |B|` is a border; the longest border corresponds to the smallest period, and that smallest
period divides `n` exactly when `s` is a repetition.

For the palindrome, a border of `s + '#' + reverse(s)` is a prefix of `s` that equals a suffix of
`reverse(s)`, which is the reverse of a prefix of `s`; so it is a prefix that equals its own reverse,
a palindrome. The longest such prefix tells you how much of `s` is already fine; reverse the rest and
put it in front.

---

## 4. Rabin-Karp: Rolling Hash

Treat a window as a number in base `b`: `h = s[i] * b^(m-1) + s[i+1] * b^(m-2) + ... + s[i+m-1]`,
reduced modulo a large prime. Sliding one step removes the leading term and appends a new one:
`h = (h - s[i] * b^(m-1)) * b + s[i+m]`.

```python
def rabin_karp(text, pat, base=131, mod=(1 << 61) - 1):
    """Start indices of pat in text. Hash equality is only a candidate: confirm by comparing."""
    n, m = len(text), len(pat)
    if m == 0 or m > n:
        return []
    high = pow(base, m - 1, mod)                   # weight of the leading character
    hp = ht = 0
    for i in range(m):
        hp = (hp * base + ord(pat[i])) % mod
        ht = (ht * base + ord(text[i])) % mod
    out = []
    for i in range(n - m + 1):
        if hp == ht and text[i:i + m] == pat:      # verification makes it always correct
            out.append(i)
        if i + m < n:
            ht = ((ht - ord(text[i]) * high) * base + ord(text[i + m])) % mod
    return out
```

Two different strings can share a hash (a collision). With the verification line, a collision only
costs time, never correctness. Without it, the algorithm is right *with high probability* and wrong
otherwise. The check runs this with a modulus of 5, where nearly every window collides, to prove the
verification is what keeps it correct.

**Cost.** Expected `O(n + m)` with a good modulus. Worst case `O(n * m)`: a text and pattern like
`"aaaa..."` match at every position and each match is verified in `O(m)`, and an adversary who knows
your fixed base and modulus can force collisions. Mitigate by choosing the base at random when the
program starts, and by using a large modulus. Rolling hash is the right tool when you compare *many*
windows (duplicate-substring problems), where it beats re-slicing.

---

## 5. Manacher: Longest Palindromic Substring in `O(n)`

Insert a separator between characters so every palindrome has a centre and odd and even lengths are
handled alike: `"abba"` becomes `^#a#b#b#a#$` (the `^` and `$` sentinels stop the expansion at the
ends). `p[i]` is the radius of the palindrome centred at `i`, which equals the palindrome's length in
the original string. Keep the rightmost palindrome found so far, `(center, right)`; a new centre
`i` inside it starts with the mirrored radius `p[2*center - i]`, capped at `right - i`.

```python
def longest_palindromic_substring(s):
    t = '^#' + '#'.join(s) + '#$'
    p = [0] * len(t)
    center = right = 0
    for i in range(1, len(t) - 1):
        if i < right:
            p[i] = min(right - i, p[2 * center - i])   # reuse the mirror image
        while t[i + p[i] + 1] == t[i - p[i] - 1]:      # expand; sentinels end this loop
            p[i] += 1
        if i + p[i] > right:
            center, right = i, i + p[i]
    best = max(range(len(t)), key=p.__getitem__)
    start = (best - p[best]) // 2
    return s[start:start + p[best]]
```

It is linear because `right` only moves rightward and each expansion step extends it. Most
interviews accept expand-around-centre in `O(n^2)`; mention Manacher, and write it only if asked.

---

## 6. Pitfalls Checklist

1. **Rabin-Karp without a verification step**, or a modulus so small that collisions are routine.
2. **Fixed, guessable base and modulus** when the input might be hostile.
3. **Negative intermediate hash** in languages with truncating remainder; add the modulus before reducing.
4. **KMP: forgetting to reset `k` after a full match**, which reads past the end of the pattern or loses overlapping matches.
5. **Prefix function: using `if` where a `while` is needed** for the fall-back.
6. **Treating the empty pattern inconsistently.** Decide (here: no matches) and say it.
7. **Prefix-function tricks without a separator**, so a border runs across the join of the two strings.
8. **Reaching for KMP when a library call is expected**, or the other way round. Read the prompt.

---

## 7. Drills

1. Compute `prefix_function("abcabcab")` by hand.
2. Why does the text pointer in KMP never move backwards?
3. Why is KMP `O(n + m)` even though it has a nested `while`?
4. What does `n - pi[n-1]` tell you about a string, and when is it a real period?
5. For `s = "aacecaaa"`, what is `shortest_palindrome(s)` and which prefix did it keep?
6. In Rabin-Karp, what exactly is verified on a hash match, and what could go wrong if you skip it?
7. Give an input on which Rabin-Karp (with verification) takes `O(n * m)`.
8. Why does Manacher insert `#` between characters?

---

## 8. Homework

Solve these in order. Names are common problem titles; numbers are LeetCode's.

1. **Find the Index of the First Occurrence in a String** (28) — write KMP, do not call `find`.
2. **Repeated Substring Pattern** (459) — the prefix-function observation.
3. **Shortest Palindrome** (214) — the separator trick.
4. **Repeated DNA Sequences** (187) — fixed-width windows; a hash set of windows, then a rolling hash.
5. **Longest Palindromic Substring** (5) — expand around centre first, then Manacher.
6. **Longest Duplicate Substring** (1044) — binary search on the length with a rolling hash.

Then explain, aloud and without notes, why KMP falls back to `pi[k-1]` and not to 0.

---

## Further reading

The standard references are CLRS (the string-matching chapter), and for Manacher and the prefix
function the CP-Algorithms string pages. They were not consulted while writing this revision: the
code here was written from the algorithms themselves and checked against naive search, against the
definition of the prefix function, and against brute-force palindrome search on random strings over
tiny alphabets, including a hash modulus small enough to force collisions.

*Last reviewed: 2026-11-26.*
