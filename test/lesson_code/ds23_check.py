"""Runs the python code blocks from data/new_lessons/ds23-string-algorithms.md against brute-force checks."""
import re, sys, random
src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
ns = {}
for b in blocks:
    exec(b, ns)
prefix_function, kmp_search, repeated, shortest_pal, rabin_karp, manacher = (
    ns['prefix_function'], ns['kmp_search'], ns['repeated_substring_pattern'],
    ns['shortest_palindrome'], ns['rabin_karp'], ns['longest_palindromic_substring'])
random.seed(23)

def rand_str(n, alpha):
    return ''.join(random.choice(alpha) for _ in range(n))

def brute_find_all(text, pat):
    return [i for i in range(len(text) - len(pat) + 1) if text[i:i + len(pat)] == pat] if pat else []

# prefix function vs its definition
for _ in range(500):
    p = rand_str(random.randint(1, 12), 'ab' if random.random() < 0.7 else 'abc')
    exp = [max([k for k in range(0, i + 1) if p[:k] == p[i + 1 - k:i + 1]]) for i in range(len(p))]
    assert prefix_function(p) == exp, (p, prefix_function(p), exp)

# KMP and Rabin-Karp vs naive search (overlapping matches included); tiny alphabet forces many repeats
for _ in range(800):
    alpha = 'ab' if random.random() < 0.7 else 'abc'
    text = rand_str(random.randint(0, 25), alpha); pat = rand_str(random.randint(0, 6), alpha)
    exp = brute_find_all(text, pat)
    assert kmp_search(text, pat) == exp, (text, pat)
    assert rabin_karp(text, pat) == exp, (text, pat)
    # tiny modulus makes almost every window collide: the verification step must save correctness
    assert rabin_karp(text, pat, base=3, mod=5) == exp, ('collide', text, pat)
assert kmp_search("AAAAAAAAAB", "AAAB") == [6]
assert kmp_search("aaaa", "aa") == [0, 1, 2]

# Repeated substring pattern
for _ in range(500):
    s = rand_str(random.randint(0, 10), 'ab')
    exp = any(len(s) % k == 0 and s[:k] * (len(s) // k) == s for k in range(1, len(s)))
    assert repeated(s) == exp, s
assert repeated("abab") and not repeated("aba") and not repeated("a") and not repeated("")

# Shortest palindrome by prepending
def brute_shortest_pal(s):
    for k in range(len(s) + 1):
        cand = s[::-1][:k] + s if k else s
        if cand == cand[::-1]:
            return cand
for _ in range(500):
    s = rand_str(random.randint(0, 9), 'abc' if random.random() < 0.5 else 'ab')
    assert shortest_pal(s) == brute_shortest_pal(s), s
assert shortest_pal("aacecaaa") == "aaacecaaa" and shortest_pal("abcd") == "dcbabcd"

# Manacher: the returned substring is a palindrome inside s, and no longer palindrome exists
for _ in range(800):
    s = rand_str(random.randint(0, 14), 'ab' if random.random() < 0.7 else 'abc')
    best = max((j - i for i in range(len(s)) for j in range(i + 1, len(s) + 1) if s[i:j] == s[i:j][::-1]), default=0)
    got = manacher(s)
    assert got == got[::-1] and got in s and len(got) == best, (s, got, best)
print("ds23 code checks passed")
