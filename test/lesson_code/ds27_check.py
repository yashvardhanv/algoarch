"""Runs the python blocks from data/new_lessons/ds27-matrix-grid.md against brute-force references."""
import re, sys, random, copy, itertools
src = open(sys.argv[1], encoding='utf-8').read()
ns = {}
for b in re.findall(r"```python\n(.*?)```", src, re.S):
    exec(b, ns)
DIRS4, DIRS8 = ns['DIRS4'], ns['DIRS8']
flood_fill, component_sizes, nearest_zero = ns['flood_fill'], ns['component_sizes'], ns['nearest_zero']
rotate_cw, rotate_ccw, transpose, spiral_order = ns['rotate_cw'], ns['rotate_ccw'], ns['transpose'], ns['spiral_order']
game_of_life, set_zeroes = ns['game_of_life'], ns['set_zeroes']
Prefix2D, search_sorted_matrix = ns['Prefix2D'], ns['search_sorted_matrix']
min_path_sum, paths_with_obstacles, maximal_square = ns['min_path_sum'], ns['paths_with_obstacles'], ns['maximal_square']
random.seed(27)

def rect(lo, hi, maxr=7, maxc=7, minr=1, minc=1):
    R, C = random.randint(minr, maxr), random.randint(minc, maxc)
    return [[random.randint(lo, hi) for _ in range(C)] for _ in range(R)]

assert len(DIRS4) == 4 and len(DIRS8) == 8 and len(set(DIRS8)) == 8 and (0, 0) not in DIRS8
assert set(DIRS4) < set(DIRS8)

# ---- flood fill vs recursive reference; same-colour call must terminate and change nothing
def ref_fill(img, r, c, old, new):
    if not (0 <= r < len(img) and 0 <= c < len(img[0])) or img[r][c] != old:
        return
    img[r][c] = new
    for dr, dc in DIRS4:
        ref_fill(img, r + dr, c + dc, old, new)
for _ in range(400):
    g = rect(0, 2); r, c = random.randrange(len(g)), random.randrange(len(g[0])); new = random.randint(0, 3)
    orig = copy.deepcopy(g)
    want = copy.deepcopy(g)
    if want[r][c] != new:
        ref_fill(want, r, c, want[r][c], new)
    assert flood_fill(g, r, c, new) == want, (orig, r, c, new)
    assert g == orig, "input must not be mutated"

# ---- component sizes vs union-find, 4- and 8-connectivity
def uf_sizes(g, dirs):
    R, C = len(g), len(g[0]); par = {}
    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]; x = par[x]
        return x
    for r in range(R):
        for c in range(C):
            if g[r][c] == 1: par[(r, c)] = (r, c)
    for (r, c) in list(par):
        for dr, dc in dirs:
            if (r + dr, c + dc) in par:
                par[find((r, c))] = find((r + dr, c + dc))
    cnt = {}
    for x in par:
        cnt[find(x)] = cnt.get(find(x), 0) + 1
    return sorted(cnt.values())
for _ in range(400):
    g = rect(0, 1, 8, 8); orig = copy.deepcopy(g)
    assert component_sizes(g) == uf_sizes(g, DIRS4), g
    assert component_sizes(g, dirs=DIRS8) == uf_sizes(g, DIRS8), g
    assert g == orig
assert component_sizes([[1, 0], [0, 1]]) == [1, 1] and component_sizes([[1, 0], [0, 1]], dirs=DIRS8) == [2]

# ---- nearest zero (multi-source BFS) vs min Manhattan distance
for _ in range(400):
    g = rect(0, 1, 7, 7)
    zeros = [(r, c) for r in range(len(g)) for c in range(len(g[0])) if g[r][c] == 0]
    if not zeros:
        try:
            nearest_zero(g); assert False
        except ValueError:
            continue
    want = [[min(abs(r - zr) + abs(c - zc) for zr, zc in zeros) for c in range(len(g[0]))] for r in range(len(g))]
    assert nearest_zero(g) == want, g

# ---- rotate / transpose / spiral
for _ in range(300):
    n = random.randint(1, 6)
    m = [[random.randint(0, 99) for _ in range(n)] for _ in range(n)]
    cw = [[m[n - 1 - j][i] for j in range(n)] for i in range(n)]       # index formula: out[i][j] = in[n-1-j][i]
    assert cw == [list(r) for r in zip(*m[::-1])]
    a = copy.deepcopy(m); rotate_cw(a); assert a == cw, m
    b = copy.deepcopy(m); rotate_ccw(b); assert b == [list(r) for r in zip(*m)][::-1], m
    c = copy.deepcopy(m)
    for _ in range(4): rotate_cw(c)
    assert c == m
    d = copy.deepcopy(m); rotate_cw(d); rotate_ccw(d); assert d == m
for _ in range(300):
    m = rect(0, 99)
    assert transpose(m) == [[m[r][c] for r in range(len(m))] for c in range(len(m[0]))]
    # spiral by simulation with a visited grid
    R, C = len(m), len(m[0]); seen = [[False] * C for _ in range(R)]
    r = c = d = 0; want = []
    for _ in range(R * C):
        want.append(m[r][c]); seen[r][c] = True
        dr, dc = DIRS4[d]
        if not (0 <= r + dr < R and 0 <= c + dc < C and not seen[r + dr][c + dc]):
            d = (d + 1) % 4; dr, dc = DIRS4[d]
        r, c = r + dr, c + dc
    assert spiral_order(m) == want, m
assert spiral_order([[1, 2, 3]]) == [1, 2, 3] and spiral_order([[1], [2], [3]]) == [1, 2, 3]

# ---- game of life (in place, two-bit encoding) vs a fresh-grid step
def life_ref(b):
    R, C = len(b), len(b[0]); out = [[0] * C for _ in range(R)]
    for r in range(R):
        for c in range(C):
            n = sum(b[r + dr][c + dc] for dr, dc in DIRS8 if 0 <= r + dr < R and 0 <= c + dc < C)
            out[r][c] = 1 if (b[r][c] and n in (2, 3)) or (not b[r][c] and n == 3) else 0
    return out
for _ in range(300):
    b = rect(0, 1, 7, 7); want = life_ref(b); game_of_life(b); assert b == want
blinker = [[0, 1, 0], [0, 1, 0], [0, 1, 0]]; game_of_life(blinker); assert blinker == [[0, 0, 0], [1, 1, 1], [0, 0, 0]]

# ---- set matrix zeroes with O(1) extra space vs new-grid reference
for _ in range(500):
    m = rect(0, 3, 6, 6)
    R, C = len(m), len(m[0])
    zr = {r for r in range(R) for c in range(C) if m[r][c] == 0}
    zc = {c for r in range(R) for c in range(C) if m[r][c] == 0}
    want = [[0 if (r in zr or c in zc) else m[r][c] for c in range(C)] for r in range(R)]
    set_zeroes(m); assert m == want

# ---- 2D prefix sums vs direct sum over every rectangle
for _ in range(150):
    m = rect(-5, 9, 6, 6); p = Prefix2D(m); R, C = len(m), len(m[0])
    for r1, r2 in itertools.combinations_with_replacement(range(R), 2):
        for c1, c2 in itertools.combinations_with_replacement(range(C), 2):
            assert p.sum(r1, c1, r2, c2) == sum(m[r][c] for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)), (m, r1, c1, r2, c2)

# ---- staircase search in a matrix sorted by row and by column
for _ in range(400):
    R, C = random.randint(1, 6), random.randint(1, 6)
    base = [[random.randint(0, 6) for _ in range(C)] for _ in range(R)]
    for r in range(R):
        for c in range(C):                      # make rows and columns non-decreasing
            up = base[r - 1][c] if r else 0; left = base[r][c - 1] if c else 0
            base[r][c] = max(base[r][c], up, left)
    t = random.randint(-1, 20)
    assert search_sorted_matrix(base, t) == any(t in row for row in base), (base, t)

# ---- grid DP vs exhaustive path enumeration / all-squares brute force
def all_paths(g, blocked):
    R, C = len(g), len(g[0])
    def go(r, c, cost):
        if not (r < R and c < C) or (blocked and g[r][c] == 1):
            return []
        cost += 0 if blocked else g[r][c]
        if (r, c) == (R - 1, C - 1):
            return [cost]
        return go(r + 1, c, cost) + go(r, c + 1, cost)
    return go(0, 0, 0)
for _ in range(400):
    g = rect(0, 9, 5, 5)
    assert min_path_sum(g) == min(all_paths(g, False)), g
    h = rect(0, 1, 5, 5)
    assert paths_with_obstacles(h) == len(all_paths(h, True)), h
for _ in range(400):
    g = rect(0, 1, 7, 7); R, C = len(g), len(g[0]); best = 0
    for r in range(R):
        for c in range(C):
            for k in range(1, min(R - r, C - c) + 1):
                if all(g[i][j] == 1 for i in range(r, r + k) for j in range(c, c + k)): best = max(best, k * k)
    assert maximal_square(g) == best, g
print("ds27 code checks passed")
