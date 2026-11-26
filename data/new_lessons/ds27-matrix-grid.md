# Lesson — Matrix and Grid Problems: Traversal, Transforms, In-Place Tricks and Grid DP

> **Priority:** ★★★★ (proposed; the curriculum data holds the final rating) — grids are the most common "disguised" input in a coding loop: the problem is a picture, and the work is index arithmetic you must not get wrong.
>
> **Study time:** 75 minutes. **Do this after:** Lesson 11 (graphs, BFS and DFS) and Lesson 5 (prefix sums). It is used again by dynamic programming on grids (Lesson 15).
>
> **Level:** core.

Lesson 11 already taught you that a grid is a graph and how to run BFS on it. This lesson is about everything else a grid problem asks: spin it, spiral through it, change it without a second copy, sum a rectangle of it, and run a recurrence over it. Almost none of it needs a clever idea. It needs you to pick one convention for indices, state the invariant, and test three tiny cases: one cell, one row, one column.

---

## 1. Mental Model

> **A grid problem is an index-arithmetic problem with a story on top. Fix a convention (`r` is the row, `c` is the column, `grid[r][c]`), say what each loop variable means in words, and the only way to be wrong is an off-by-one on a boundary.**

Four habits cover nearly every bug:

- **One neighbour table.** Directions live in one constant, and the bounds check happens before any index.
- **Say the shape.** `R = len(grid)` rows, `C = len(grid[0])` columns. A square is the special case `R == C`; many "rotate" solutions silently assume it.
- **Choose the visited marker deliberately.** A separate set costs `O(R·C)` space; painting the cell itself is free but destroys the input, and it only works if the painted value cannot be mistaken for an unvisited one.
- **Test the degenerate shapes first.** `1×1`, `1×n`, `n×1`. Spiral and boundary-shrinking code fails there, not on the 4×4 in the prompt.

Two facts about indices are worth having cold. Cells on the same diagonal share `r - c`; cells on the same anti-diagonal share `r + c`. And a flat index `r * C + c` converts a cell to one integer and back with `divmod(i, C)`, which is how a grid becomes a graph node id or a hashmap key without tuples.

*Visual (planned): a grid with the four-neighbour and eight-neighbour stars, a rotation drawn as transpose-then-reverse, and the four shrinking boundaries of a spiral. Not built yet.*

---

## 2. The Recognition Reflex

| If the prompt says... | Reach for | Time |
|---|---|---|
| "paint/replace the connected region", "count regions", "largest region" | **Flood fill** with an explicit stack | `O(R·C)` |
| "nearest 0/gate/exit for every cell", "how far from..." | **Multi-source BFS** from every source at once | `O(R·C)` |
| "rotate the image 90 degrees", "in place" | **Transpose, then reverse each row** | `O(R·C)`, `O(1)` space |
| "print/return in spiral order" | **Four shrinking boundaries** | `O(R·C)` |
| "update every cell from its neighbours, simultaneously, in place" | **Encode old and new state in one cell** | `O(R·C)`, `O(1)` space |
| "if a cell is 0, zero its row and column", in `O(1)` space | **Use the first row and column as the marker storage** | `O(R·C)` |
| "sum of a sub-rectangle", many queries | **2D prefix sums** | `O(R·C)` build, `O(1)` per query |
| "search a matrix sorted by row and by column" | **Staircase walk from a corner** | `O(R + C)` |
| "minimum cost / number of ways to reach the corner moving right/down" | **Grid DP** | `O(R·C)` |
| "largest square/rectangle of 1s" | **Grid DP on the corner of a square** | `O(R·C)` |

> **Before you reach for BFS, ask whether the answer is a distance.** "How many regions" and "what is the area" do not need BFS ordering; "how many steps" does. Lesson 11 has the full DFS-versus-BFS rule. Here it only decides which of the first two rows you are in.

---

## 3. Directions, Bounds and Flood Fill

```python
DIRS4 = ((0, 1), (1, 0), (0, -1), (-1, 0))                      # right, down, left, up
DIRS8 = DIRS4 + ((1, 1), (1, -1), (-1, -1), (-1, 1))            # plus the four diagonals


def flood_fill(img, sr, sc, color):
    """Return a copy of img with the 4-connected region of (sr, sc) recoloured. Iterative."""
    img = [row[:] for row in img]
    old = img[sr][sc]
    if old == color:                      # without this the loop never terminates (see pitfall 2)
        return img
    R, C = len(img), len(img[0])
    img[sr][sc] = color                   # painting a cell IS the visited mark; paint on push
    stack = [(sr, sc)]
    while stack:
        r, c = stack.pop()
        for dr, dc in DIRS4:
            nr, nc = r + dr, c + dc
            if 0 <= nr < R and 0 <= nc < C and img[nr][nc] == old:
                img[nr][nc] = color
                stack.append((nr, nc))
    return img


def component_sizes(grid, target=1, dirs=DIRS4):
    """Sizes of the connected regions made of `target` cells, sorted. Does not change grid."""
    R, C = len(grid), len(grid[0])
    seen = [[False] * C for _ in range(R)]
    sizes = []
    for r0 in range(R):
        for c0 in range(C):
            if grid[r0][c0] != target or seen[r0][c0]:
                continue
            seen[r0][c0] = True
            stack, size = [(r0, c0)], 0
            while stack:
                r, c = stack.pop()
                size += 1
                for dr, dc in dirs:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < R and 0 <= nc < C and grid[nr][nc] == target and not seen[nr][nc]:
                        seen[nr][nc] = True
                        stack.append((nr, nc))
            sizes.append(size)
    return sorted(sizes)
```

**Why an explicit stack.** A recursive flood fill on a grid whose region is one long snake recurses once per cell. CPython caps recursion depth; the `sys` documentation says the limit exists to prevent a C stack overflow, that the highest limit you may set depends on the platform, and that setting it too high can crash the interpreter (see Sources). The code above uses a list as the stack, so depth is a non-issue.

**Mark on push, not on pop.** This is the same rule as BFS in Lesson 11, and it is the one line that decides whether a cell is pushed once or many times. Painting `img[nr][nc] = color` at push time is both the visited mark and the answer.

**Four directions or eight.** Switching `dirs=DIRS4` to `DIRS8` is the entire difference between "islands" and "islands, where diagonal touching counts". The matrix `[[1, 0], [0, 1]]` has two regions with `DIRS4` and one with `DIRS8`; the check script asserts exactly that.

**Distance to the nearest source.** When every cell wants the distance to its nearest special cell, run one BFS seeded with all of them, as in Lesson 11, instead of one BFS per cell:

```python
from collections import deque

def nearest_zero(m):
    """Distance (in 4-neighbour steps) from each cell to the nearest 0. m must contain a 0."""
    R, C = len(m), len(m[0])
    dist = [[None] * C for _ in range(R)]
    q = deque()
    for r in range(R):
        for c in range(C):
            if m[r][c] == 0:
                dist[r][c] = 0
                q.append((r, c))          # every source is queued before the first pop
    if not q:
        raise ValueError("no zero in the matrix")
    while q:
        r, c = q.popleft()
        for dr, dc in DIRS4:
            nr, nc = r + dr, c + dc
            if 0 <= nr < R and 0 <= nc < C and dist[nr][nc] is None:
                dist[nr][nc] = dist[r][c] + 1
                q.append((nr, nc))
    return dist
```

`dist[nr][nc] is None` doubles as the visited test. Cost is `O(R·C)`: each cell enters the queue once. A BFS per cell would be `O((R·C)²)`. Because this grid has no walls, the check script compares against the formula "smallest `|r - zr| + |c - zc|` over all zeros"; with walls that formula no longer holds and only BFS is correct.

---

## 4. Rotate, Transpose and Spiral

```python
def transpose(m):
    """New matrix with rows and columns swapped. Works for any R x C."""
    return [[m[r][c] for r in range(len(m))] for c in range(len(m[0]))]


def rotate_cw(m):
    """Rotate a SQUARE matrix 90 degrees clockwise, in place."""
    n = len(m)
    for i in range(n):
        for j in range(i + 1, n):                 # strictly above the diagonal: each pair swaps once
            m[i][j], m[j][i] = m[j][i], m[i][j]
    for row in m:
        row.reverse()                              # then mirror each row left to right


def rotate_ccw(m):
    """Rotate a SQUARE matrix 90 degrees counter-clockwise, in place."""
    n = len(m)
    for i in range(n):
        for j in range(i + 1, n):
            m[i][j], m[j][i] = m[j][i], m[i][j]
    m.reverse()                                    # transpose, then flip the ROW ORDER instead


def spiral_order(m):
    """All cells in clockwise spiral order, for any R x C."""
    out = []
    top, bottom, left, right = 0, len(m) - 1, 0, len(m[0]) - 1
    while top <= bottom and left <= right:
        out.extend(m[top][c] for c in range(left, right + 1))          # top row, left to right
        top += 1
        out.extend(m[r][right] for r in range(top, bottom + 1))        # right column, downward
        right -= 1
        if top <= bottom:                                              # a row may remain...
            out.extend(m[bottom][c] for c in range(right, left - 1, -1))
            bottom -= 1
        if left <= right:                                              # ...and so may a column
            out.extend(m[r][left] for r in range(bottom, top - 1, -1))
            left += 1
    return out
```

**Rotation as two reflections.** A clockwise quarter-turn sends the cell at `(i, j)` to `(j, n - 1 - i)`. Equivalently the new matrix has `out[i][j] = in[n - 1 - j][i]`. Transposing sends `(i, j)` to `(j, i)`; reversing each row then sends `(j, i)` to `(j, n - 1 - i)`. Two reflections compose to a rotation, and each one is a trivial in-place loop, so you never need to remember the four-way cycle swap. Reverse the *order of the rows* after the transpose instead, and you get the counter-clockwise turn. The check script confirms both against `zip(*m[::-1])`, and that four clockwise turns return the original. `zip(*rows)` transposes because it pairs up the i-th item of every row; by default it stops at the shortest iterable, and `strict=True` (Python 3.10+) makes unequal row lengths an error rather than a silent truncation (see Sources).

**Why the square matters.** In-place rotation needs `R == C`. For a rectangle the result has different dimensions, so it cannot overwrite the input; build a new matrix with `transpose` and reverse. `transpose` above is correct for rectangles; `rotate_cw` is not, and the lesson says so rather than letting a `3×2` input corrupt silently.

**Spiral: shrinking boundaries.** Walk the outer ring, then shrink `top`, `right`, `bottom`, `left` by one and repeat. The two `if` guards are the whole difficulty. After the top row and right column are consumed, a single-row or single-column remainder would be walked twice (once forward, once back) without them. Trace `[[1, 2, 3]]` and `[[1], [2], [3]]` by hand: both must give `[1, 2, 3]`, and they are the inputs that expose a missing guard. The check also compares every random rectangle against a different method, a simulation that walks and turns right whenever the next cell is out of bounds or already visited.

---

## 5. In-Place Tricks: Change the Grid Without a Copy

When every cell's new value depends on its neighbours' *old* values, overwriting as you go corrupts later reads. The cheap fix is a copy. The in-place fix is to store both the old and the new value in each cell.

```python
def game_of_life(board):
    """One generation of Conway's rules on a 0/1 board, in place. Bit 0 = now, bit 1 = next."""
    R, C = len(board), len(board[0])
    for r in range(R):
        for c in range(C):
            live = 0
            for dr, dc in DIRS8:
                nr, nc = r + dr, c + dc
                if 0 <= nr < R and 0 <= nc < C:
                    live += board[nr][nc] & 1          # read only the OLD bit of a neighbour
            if live == 3 or (board[r][c] == 1 and live == 2):
                board[r][c] |= 2                       # remember the NEW state in bit 1
    for r in range(R):
        for c in range(C):
            board[r][c] >>= 1                          # promote new state to current


def set_zeroes(m):
    """If a cell is 0, set its whole row and column to 0. O(1) extra space, in place."""
    R, C = len(m), len(m[0])
    first_row_zero = any(m[0][c] == 0 for c in range(C))
    first_col_zero = any(m[r][0] == 0 for r in range(R))
    for r in range(1, R):
        for c in range(1, C):
            if m[r][c] == 0:
                m[r][0] = 0                            # the first column holds "zero this row"
                m[0][c] = 0                            # the first row holds "zero this column"
    for r in range(1, R):
        for c in range(1, C):
            if m[r][0] == 0 or m[0][c] == 0:
                m[r][c] = 0
    if first_row_zero:
        for c in range(C):
            m[0][c] = 0
    if first_col_zero:
        for r in range(R):
            m[r][0] = 0
```

**The two-bit encoding.** `board[r][c] & 1` is always the old state, because the code only ever sets bit 1 and never touches bit 0 until the final pass. Neighbours not yet visited and neighbours already visited look identical through `& 1`, which is the whole point. The check script compares against a version that builds a fresh board, and a blinker (`[[0,1,0],[0,1,0],[0,1,0]]`) must become the horizontal bar. This encoding assumes values fit in spare bits; with arbitrary integers you would encode a pair some other way, or accept the copy.

**The marker trick.** The first row and first column are borrowed as storage for "this column/row must become zero". Borrowing destroys their own information, so you save it first in `first_row_zero` and `first_col_zero` and apply it last. Zero the first row and first column *before* the interior pass and the markers read as real zeros, so whole rows and columns are wiped that should survive: this ordering is the usual bug.

**Say the trade-off.** Both tricks save a copy at the cost of readability and of a precondition. In an interview, write the copy version first if you are unsure, state that an `O(1)`-space version exists, and then do it if asked.

---

## 6. 2D Prefix Sums and the Staircase Search

```python
class Prefix2D:
    """Sum of any sub-rectangle in O(1) after an O(R*C) build."""
    def __init__(self, m):
        R, C = len(m), len(m[0])
        self.p = [[0] * (C + 1) for _ in range(R + 1)]       # one row and one column of zeros as padding
        for r in range(R):
            for c in range(C):
                self.p[r + 1][c + 1] = m[r][c] + self.p[r][c + 1] + self.p[r + 1][c] - self.p[r][c]

    def sum(self, r1, c1, r2, c2):
        """Inclusive corners (r1, c1) top-left and (r2, c2) bottom-right."""
        p = self.p
        return p[r2 + 1][c2 + 1] - p[r1][c2 + 1] - p[r2 + 1][c1] + p[r1][c1]


def search_sorted_matrix(m, target):
    """m is non-decreasing along every row and down every column. True if target is present."""
    r, c = 0, len(m[0]) - 1                  # start at the top-right corner
    while r < len(m) and c >= 0:
        if m[r][c] == target:
            return True
        if m[r][c] > target:
            c -= 1                           # everything below in this column is even larger
        else:
            r += 1                           # everything to the left in this row is even smaller
    return False
```

**Inclusion and exclusion.** `p[r+1][c+1]` is the sum of the rectangle from the origin to `(r, c)`. Adding the cell, the rectangle above it and the rectangle to its left counts the overlap twice, so one `p[r][c]` is subtracted. A query does the same in reverse: take the big corner, remove the strip above and the strip to the left, and add back the corner removed twice. The padding row and column of zeros means queries touching row 0 or column 0 need no special case. The check script tests *every* rectangle of many random matrices, including negative values, against a direct sum. Lesson 5 introduced this; the new point here is the padding, because the usual error is forgetting the `+ 1` shift between the matrix index and the prefix index.

**Staircase.** From the top-right corner, a value larger than the target rules out the whole column below it; a smaller one rules out the whole row to its left. Each step removes a row or a column, so at most `R + C` steps. Starting at the top-left would not work: both neighbours are larger, so you could not decide which way to go. A binary search in every row costs `O(R log C)`; the staircase costs `O(R + C)` and needs no per-row search, so it is the standard answer.

---

## 7. Grid DP

```python
def min_path_sum(grid):
    """Cheapest top-left to bottom-right path moving only right or down. O(C) extra space."""
    R, C = len(grid), len(grid[0])
    row = [0] * C
    for r in range(R):
        for c in range(C):
            if r == 0 and c == 0:
                row[c] = grid[0][0]
            elif r == 0:
                row[c] = row[c - 1] + grid[r][c]              # only reachable from the left
            elif c == 0:
                row[c] = row[c] + grid[r][c]                  # only reachable from above (old row[c])
            else:
                row[c] = min(row[c], row[c - 1]) + grid[r][c]  # above is old row[c], left is new row[c-1]
    return row[-1]


def paths_with_obstacles(grid):
    """Number of right/down paths from top-left to bottom-right; cells equal to 1 are blocked."""
    R, C = len(grid), len(grid[0])
    row = [0] * C
    for r in range(R):
        for c in range(C):
            if grid[r][c] == 1:
                row[c] = 0                                     # a blocked cell has no paths through it
            elif r == 0 and c == 0:
                row[c] = 1
            elif c > 0:
                row[c] += row[c - 1]                           # paths from above (old row[c]) + from the left
    return row[-1]


def maximal_square(g):
    """Area of the largest all-1 square in a 0/1 grid."""
    R, C = len(g), len(g[0])
    dp = [[0] * (C + 1) for _ in range(R + 1)]                 # dp[r+1][c+1] = side of the largest square ending at (r, c)
    best = 0
    for r in range(R):
        for c in range(C):
            if g[r][c] == 1:
                dp[r + 1][c + 1] = 1 + min(dp[r][c], dp[r][c + 1], dp[r + 1][c])
                best = max(best, dp[r + 1][c + 1])
    return best * best
```

Lesson 15 develops the 2D table. Three points belong here because they are about the *grid*.

**One row is enough when each cell reads only above and left.** In `min_path_sum`, `row[c]` before it is overwritten still holds the value from the row above; `row[c - 1]` has already been overwritten with the current row. The comments mark which is which, and mixing them up is the bug. The check compares against exhaustive enumeration of every path on grids up to `5×5`.

**Obstacles reset, they do not subtract.** When a cell is blocked its count is `0`, not "skip". Forgetting to write the zero lets the previous row's count leak down through a blocked cell. Check start and end cells being blocked: if the start is blocked there is no path, and the code returns `0` because `row[0]` is zeroed and never set.

**Largest square: the corner trick.** A square of side `k` ending at `(r, c)` exists only if squares of side `k - 1` end at the cell above, the cell on the left and the cell diagonally up-left. That gives `1 + min(three neighbours)`. The padding row and column again remove edge cases. The answer is the *area*, the square of the best side; returning the side is the most common slip. The check tries every square explicitly on 400 random grids.

---

## 8. Pitfalls

1. **`[[0] * C] * R`.** This builds `R` references to one row, so writing one cell changes every row. The Python FAQ shows exactly this and gives the fix: `[[0] * C for _ in range(R)]` (see Sources).
2. **Flood fill with the same colour.** If the new colour equals the old one, every painted cell still looks unvisited and the loop never ends. Return early.
3. **Marking visited on pop.** Cells get pushed many times. Mark when you push.
4. **Bounds after indexing.** Python accepts negative indices, so `grid[-1][c]` reads the last row instead of failing. Check `0 <= nr < R` first. Lesson 11 shows why this is worse in Python than in other languages.
5. **Mixing up `R` and `C`.** On a non-square grid, `len(grid)` is the rows. Use `R, C = len(grid), len(grid[0])` once, and use those names.
6. **In-place rotation on a non-square matrix.** It cannot be done in place; the output has swapped dimensions.
7. **Spiral on one row or one column.** Without the two guards the single remaining row or column is traversed twice.
8. **Overwriting before reading.** Any "update from neighbours" problem breaks if you write a cell the next cell still needs. Use a copy, a two-bit encoding, or a deliberate traversal order.
9. **Off-by-one in prefix indices.** The prefix table is shifted by one relative to the matrix. Write the query as `p[r2+1][c2+1] - p[r1][c2+1] - p[r2+1][c1] + p[r1][c1]` once and reuse it.
10. **Returning the side instead of the area**, or the area instead of the side. Read the question's last line.

---

## 9. Drills

1. Rotate `[[1, 2], [3, 4]]` clockwise by hand using transpose-then-reverse; write the matrix after each step.
2. Give the smallest grid where `DIRS4` and `DIRS8` give a different number of regions.
3. State why `flood_fill` returns early when the new colour equals the old one, and what happens without it.
4. Trace `spiral_order` on a `1×3` and on a `3×1` matrix with the two `if` guards removed. What is returned?
5. In `game_of_life`, why is it safe to read a neighbour with `& 1` even after that neighbour has been updated?
6. Where in `set_zeroes` does the order of the three passes matter, and what goes wrong if the first row and column are zeroed before the interior pass?
7. From which corner does the staircase search start, and why can it not start at the top-left?
8. Compute `Prefix2D` for `[[1, 2], [3, 4]]` on paper, then the sum of the whole matrix and of the bottom row.

---

## 10. Homework

Do these in order; for each, name the section above it belongs to.

1. **Flood Fill** (LeetCode 733). The template of section 3.
2. **Number of Islands** (200) and **Max Area of Island** (695). `component_sizes` with `len` and `max`.
3. **01 Matrix** (542). `nearest_zero` exactly.
4. **Rotate Image** (48) and **Spiral Matrix** (54). Section 4.
5. **Set Matrix Zeroes** (73), then **Game of Life** (289). Section 5; write the copy version first.
6. **Range Sum Query 2D, Immutable** (304). `Prefix2D`.
7. **Search a 2D Matrix II** (240). The staircase.
8. **Minimum Path Sum** (64), **Unique Paths II** (63), **Maximal Square** (221). Section 7.

---

## Sources and further reading

Read and used for this lesson (accessed 26 November 2026):

- Python documentation, `sys` module, docs.python.org/3/library/sys.html. Read the recursion-limit entries. Used for: the recursion limit exists to prevent a C stack overflow; the highest allowed limit is platform dependent; too high a limit can crash the interpreter.
- Python documentation, built-in functions (`zip`), docs.python.org/3/library/functions.html. Used for: `zip(*rows)` as the unzip/transpose idiom; `zip` stops at the shortest iterable by default; `strict=True` from Python 3.10 raises on unequal lengths.
- Python Programming FAQ, "How do I create a multidimensional list?", docs.python.org/3/faq/programming.html. Used for: `[[None] * w] * h` creates references to one row; the list-comprehension fix.

Not consulted: any textbook or paper for the staircase search, the two-reflections rotation or the maximal-square recurrence; they are stated as standard techniques and verified only for correctness by `test/lesson_code/ds27_check.py` against brute force, not for running time. The rules of Conway's Game of Life are used as stated in the problem statement from memory and were not read from a source for this lesson. The LeetCode problem numbers are from memory and should be checked against the site before you rely on them. The default recursion limit value of the interpreter is deliberately not quoted.

*Last reviewed: 26 November 2026.*
