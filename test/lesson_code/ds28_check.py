"""Runs the python blocks from data/new_lessons/ds28-recursion-fundamentals.md against iterative references."""
import re, sys, random, math, itertools
src = open(sys.argv[1], encoding='utf-8').read()
ns = {}
for b in re.findall(r"```python\n(.*?)```", src, re.S):
    exec(b, ns)
random.seed(28)

def fib_ref(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a

# ---- fib: value, and the call counts the lesson quotes (measured, then stated as formulas)
for n in range(0, 21):
    calls = [0]
    assert ns['fib_naive'](n, calls) == fib_ref(n)
    assert calls[0] == 2 * fib_ref(n + 1) - 1, (n, calls)         # naive call count
    calls = [0]
    memo = {}
    assert ns['fib_memo'](n, memo, calls) == fib_ref(n)
    assert len(memo) == max(0, n - 1)
    assert calls[0] == max(1, 2 * n - 1), (n, calls)              # memoised call count
c = [0]; ns['fib_naive'](25, c); assert c[0] == 242785           # the number printed in the lesson

# ---- towers of hanoi: legal moves, solved, 2^n - 1 moves
for n in range(0, 11):
    moves = []
    ns['hanoi'](n, 'A', 'C', 'B', moves)
    assert len(moves) == 2 ** n - 1
    pegs = {'A': list(range(n, 0, -1)), 'B': [], 'C': []}
    for s, d in moves:
        disc = pegs[s].pop()
        assert not pegs[d] or pegs[d][-1] > disc, "illegal move"
        pegs[d].append(disc)
    assert pegs == {'A': [], 'B': [], 'C': list(range(n, 0, -1))}

# ---- fast power: equals ** and survives a depth that linear recursion cannot
for _ in range(300):
    x, n = random.randint(-5, 5), random.randint(0, 60)
    assert ns['power'](x, n) == x ** n, (x, n)
assert ns['power'](3, 10 ** 5) == 3 ** (10 ** 5)

# ---- depth: linear recursion hits the limit, the loop and log-depth recursion do not
limit = sys.getrecursionlimit()
assert ns['sum_to'](50) == 1275 and ns['sum_to_loop'](50) == 1275
try:
    ns['sum_to'](limit * 50); assert False, "expected RecursionError"
except RecursionError:
    pass
assert ns['sum_to_loop'](10 ** 6) == 10 ** 6 * (10 ** 6 + 1) // 2
assert ns['sum_to_loop'](0) == 0 and ns['sum_to'](0) == 0

# ---- recursion -> explicit stack on expression trees
import operator
def rand_expr(d):
    if d == 0 or random.random() < 0.25:
        return random.randint(-4, 9)
    return (random.choice('+-*'), rand_expr(d - 1), rand_expr(d - 1))
for _ in range(400):
    e = rand_expr(6)
    assert ns['eval_iter'](e) == ns['eval_rec'](e), e
assert ns['eval_iter'](('-', 10, ('-', 4, 1))) == 7               # operand ORDER matters: 10 - (4 - 1)
e = 0
for i in range(100000):                                           # a left-leaning chain 100,000 deep
    e = ('+', e, 1)
assert ns['eval_iter'](e) == 100000
try:
    ns['eval_rec'](e); assert False, "expected RecursionError"
except RecursionError:
    pass

# ---- nested sum: recursive and explicit-stack agree
def rand_nested(d):
    return [rand_nested(d - 1) if d and random.random() < 0.4 else random.randint(-3, 9) for _ in range(random.randint(0, 4))]
for _ in range(300):
    x = rand_nested(4)
    flat = []
    def f(y):
        for z in y:
            f(z) if isinstance(z, list) else flat.append(z)
    f(x)
    assert ns['nested_sum'](x) == sum(flat) == ns['nested_sum_stack'](x), x

# ---- subsets and permutations by recursion vs itertools, with the tree sizes the lesson quotes
for n in range(0, 8):
    items = list(range(n))
    subs = ns['subsets_rec'](items)
    assert len(subs) == 2 ** n
    assert {tuple(s) for s in subs} == {c for k in range(n + 1) for c in itertools.combinations(items, k)}
    perms = ns['permutations_rec'](items)
    assert [tuple(p) for p in perms] == list(itertools.permutations(items))   # same order as itertools
    assert len(perms) == math.factorial(n)
assert ns['subsets_rec']([1, 1]) and sorted(map(tuple, ns['subsets_rec']([1, 1]))) == [(), (1,), (1,), (1, 1)]  # duplicates are NOT merged

# ---- grid paths: naive call count is 2*C(r+c, r) - 1; memo does one computation per state
for r in range(0, 9):
    for c in range(0, 9):
        calls = [0]
        assert ns['paths_naive'](r, c, calls) == math.comb(r + c, r)
        assert calls[0] == 2 * math.comb(r + c, r) - 1, (r, c, calls)
        memo = {}; calls = [0]
        assert ns['paths_memo'](r, c, memo, calls) == math.comb(r + c, r)
        assert len(memo) == ((r + 1) * (c + 1) - 1 if r and c else 1), (r, c, len(memo))   # (0, 0) is never reached
c = [0]; ns['paths_naive'](10, 10, c); assert c[0] == 369511     # numbers printed in the lesson
print("ds28 code checks passed")
