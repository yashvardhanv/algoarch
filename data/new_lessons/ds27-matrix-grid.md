# Lesson — Matrix and Grid Problems: Traversal, Transforms, In-Place Tricks and Grid DP

> **Priority:** ★★★★ (proposed; the curriculum data holds the final rating) — grids are the most common "disguised" input in a coding loop: the problem is a picture, and the work is index arithmetic you must not get wrong.
>
> **Study time:** 60 minutes. **Do this after:** Lesson 11 (graphs, BFS and DFS) and Lesson 5 (prefix sums). It is used again by dynamic programming on grids (Lesson 15).
>
> **Level:** core.

Lesson 11 already taught you that a grid is a graph and how to run BFS on it. This lesson is about what a grid problem asks beyond traversal: spin it, spiral through it, change it without a second copy, sum a rectangle of it, search it by its sort order. Grid traversal and grid DP are taught in Lessons 11 and 15, and the 2D prefix table in Lesson 5; here they get a pointer and only the parts those lessons do not cover. Almost none of it needs a clever idea. It needs you to pick one convention for indices, state the invariant, and test three tiny cases: one cell, one row, one column.

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
| "search a matrix sorted by row and by column" | **Staircase walk from the top-right (or bottom-left) corner**; binary search along the shorter side if one side is tiny | `O(R + C)`, or `O(min(R, C) · log max(R, C))` |
| "minimum cost / number of ways to reach the corner", "largest square of 1s" | **Grid DP** (Lesson 15 teaches it; section 7 here adds one grid-specific point) | `O(R·C)` |

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

**What is new here compared with Lesson 11.** Lesson 11 explains why you mark on push, why the bounds test comes before indexing, and why a long snake-shaped region defeats recursion; the code above follows all three (the `sys` documentation says the recursion limit exists so that infinite recursion does not overflow the C stack, see Sources). Two points are specific to flood fill. Painting the cell is the visited mark and the answer at once, so no `seen` structure is needed. And the early return for an unchanged colour is mandatory, because the painting trick relies on the new colour differing from the old one.

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

**Rotation as two reflections.** A clockwise quarter-turn sends the cell at `(i, j)` to `(j, n - 1 - i)`. Equivalently the new matrix has `out[i][j] = in[n - 1 - j][i]`. Transposing sends `(i, j)` to `(j, i)`; reversing each row then sends `(j, i)` to `(j, n - 1 - i)`. Two reflections compose to a rotation, and each one is a trivial in-place loop, so you never need to remember the four-way cycle swap. Reverse the *order of the rows* after the transpose instead, and you get the counter-clockwise turn. The check script confirms the clockwise turn against `zip(*m[::-1])` and the counter-clockwise turn against `zip(*m)` with the rows reversed, and that four clockwise turns return the original. `zip(*rows)` transposes because it pairs up the i-th item of every row; by default it stops at the shortest iterable, and `strict=True` (Python 3.10+) makes unequal row lengths an error rather than a silent truncation (see Sources).

**Why the square matters.** In-place rotation needs `R == C`. For a rectangle the result has different dimensions, so it cannot overwrite the input; build a new matrix with `transpose` and reverse. `transpose` above is correct for rectangles; `rotate_cw` is not. On a `3×2` input it raises `IndexError`, but on a `2×3` input such as `[[0, 1, 2], [10, 11, 12]]` it returns `[[2, 10, 0], [12, 11, 1]]` with no error at all: a wrong answer that looks plausible. Check `R == C` first.

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

**Inclusion and exclusion.** Lesson 5 derives this. The point to keep from it here is the padding: the table has one extra row and column of zeros, so the matrix cell `(r, c)` lives at `p[r + 1][c + 1]` and a query touching row 0 or column 0 needs no special case. Forgetting the `+ 1` shift between matrix index and prefix index is the usual error. The check script tests *every* rectangle of many random matrices, including negative values, against a direct sum.

**Staircase.** From the top-right corner, a value larger than the target rules out the whole column below it; a smaller one rules out the whole row to its left. Each step removes a row or a column, so at most `R + C` steps. The bottom-left corner works for the same reason (up is smaller, right is larger). The top-left and bottom-right corners do not: both neighbours are larger (or both smaller), so you cannot decide which way to go.

**When the staircase loses.** `O(R + C)` is good when `R` and `C` are comparable. For a `1 × 1,000,000` matrix it can take up to a million steps, while a binary search along the single row takes about 20. The general bound is to loop over the *shorter* dimension and binary-search the other, `O(min(R, C) · log max(R, C))`. Say both in an interview and pick by shape.

---

## 7. Grid DP: the One Grid-Specific Point

Lesson 15 develops grid DP: minimum path sum, unique paths with and without obstacles, and the maximal square. This lesson does not repeat them. It keeps one point that is about the grid rather than about DP, and one function that shows it.

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
```

**One row is enough when each cell reads only above and left.** Before `row[c]` is overwritten it still holds the value from the row above; `row[c - 1]` has already been overwritten with the current row. The comments mark which is which, and mixing them up is the bug. If a recurrence also reads the up-left diagonal, one row is not enough unless you save the old `row[c - 1]` in a temporary first. The check compares `min_path_sum` against exhaustive enumeration of every path on grids up to `5×5`.

The padding idea of section 6 (an extra row and column of zeros) applies to any recurrence that reads up, left or diagonal neighbours, and removes the first-row and first-column cases.

---

## 8. Pitfalls

1. **`[[0] * C] * R`.** This builds `R` references to one row, so writing one cell changes every row. The Python FAQ shows exactly this and gives the fix: `[[0] * C for _ in range(R)]` (see Sources).
2. **Flood fill with the same colour.** If the new colour equals the old one, every painted cell still looks unvisited and the loop never ends. Return early.
3. **Traversal pitfalls from Lesson 11.** Mark on push, check bounds before indexing, avoid deep recursion on a snake region. They apply to everything in section 3 and are not repeated here.
4. **Mixing up `R` and `C`.** On a non-square grid, `len(grid)` is the rows. Use `R, C = len(grid), len(grid[0])` once, and use those names.
5. **In-place rotation on a non-square matrix.** It cannot be done in place, and the code may return a wrong answer without raising (section 4).
6. **Spiral on one row or one column.** Without the two guards the single remaining row or column is traversed twice.
7. **Overwriting before reading.** Any "update from neighbours" problem breaks if you write a cell the next cell still needs. Use a copy, a two-bit encoding, or a deliberate traversal order.
8. **Off-by-one in prefix indices.** The prefix table is shifted by one relative to the matrix. Write the query as `p[r2+1][c2+1] - p[r1][c2+1] - p[r2+1][c1] + p[r1][c1]` once and reuse it.
9. **Using the staircase on a lopsided matrix.** For `1 × n` it is `O(n)` where binary search is `O(log n)`.

---

## 9. Drills

1. Rotate `[[1, 2], [3, 4]]` clockwise by hand using transpose-then-reverse; write the matrix after each step.
2. Give the smallest grid where `DIRS4` and `DIRS8` give a different number of regions.
3. State why `flood_fill` returns early when the new colour equals the old one, and what happens without it.
4. Trace `spiral_order` on a `1×3` and on a `3×1` matrix with the two `if` guards removed. What is returned?
5. In `game_of_life`, why is it safe to read a neighbour with `& 1` even after that neighbour has been updated?
6. Where in `set_zeroes` does the order of the three passes matter, and what goes wrong if the first row and column are zeroed before the interior pass?
7. Which two corners work for the staircase search, and why do the other two not?
8. Compute `Prefix2D` for `[[1, 2], [3, 4]]` on paper, then the sum of the whole matrix and of the bottom row.

---

## 10. Homework

Do these in order; for each, name the section above it belongs to. Flood fill, islands, 01 Matrix and Rotting Oranges are in Lesson 11's problem set, 2D range sums in Lesson 5's, and the grid-DP problems in Lesson 15's; do those there and do not repeat them here.

1. **Transpose Matrix** (LeetCode 867) and **Rotate Image** (48). Section 4; write the rectangular case with `transpose` and the square case in place.
2. **Spiral Matrix** (54), then **Spiral Matrix II** (59), which fills a square in spiral order with the same four boundaries.
3. **Set Matrix Zeroes** (73), then **Game of Life** (289). Section 5; write the copy version first.
4. **Diagonal Traverse** (498) and **Toeplitz Matrix** (766). Use `r + c` and `r - c` from section 1.
5. **Matrix Block Sum** (1314). `Prefix2D` with clamped corners.
6. **Search a 2D Matrix II** (240). The staircase; then write the binary-search-on-the-shorter-side version and compare on a `1 × n` input.
7. **Number of Enclaves** (1020). `component_sizes` plus a border test.
8. **Shortest Bridge** (934). A flood fill to find one island, then multi-source BFS from it.

---

## Sources and further reading

Read and used for this lesson (accessed 26 November 2026):

- Python documentation, `sys` module, docs.python.org/3/library/sys.html, re-read as page text (HTML fetched and tags stripped) in the fix round. Used for: `getrecursionlimit` and `setrecursionlimit` say the limit prevents infinite recursion from overflowing the C stack and crashing Python; the highest possible limit is platform dependent; a too-high limit can lead to a crash. The What's New in Python 3.12 page, read the same way, says the limit now applies only to Python code and that built-in functions are protected by a different mechanism; the lesson does not depend on that.
- Python documentation, built-in functions (`zip`), docs.python.org/3/library/functions.html. Used for: `zip(*rows)` as the unzip/transpose idiom; `zip` stops at the shortest iterable by default; `strict=True` from Python 3.10 raises on unequal lengths.
- Python Programming FAQ, "How do I create a multidimensional list?", docs.python.org/3/faq/programming.html. Used for: `[[None] * w] * h` creates references to one row; the list-comprehension fix.

Not consulted: any textbook or paper for the staircase search and its `O(min(R, C) · log max(R, C))` alternative, or for the two-reflections rotation. They are standard techniques with no source behind them here, and are verified only for correctness by `test/lesson_code/ds27_check.py` against brute force, not for running time. The rules of Conway's Game of Life are used as stated in the problem statement from memory and were not read from a source for this lesson. The LeetCode problem numbers are from memory and should be checked against the site before you rely on them. The default recursion limit value of the interpreter is deliberately not quoted.

*Last reviewed: 26 November 2026.*
