# DSA: benchmark (DRAFT 1)

Status: first pass, 2026-11-26. Phase 1 of `docs/plans/curriculum-overhaul-plan.md`; binding owner decisions are in `docs/curriculum/decisions.md`.
Not yet owner-reviewed. Every "Ours" cell is judged from **lesson titles and the audit flags only**, not from reading the lesson bodies. Treat each as a hypothesis for the Phase 3 per-lesson review.

## Sources read (access date 2026-11-26)

| Code | Source | What was read | Limit |
|---|---|---|---|
| NC | NeetCode roadmap (neetcode.io/roadmap), read in a browser because the page is script-rendered | the 18 category names, in page order: Arrays & Hashing, Two Pointers, Binary Search, Stack, Sliding Window, Linked List, Trees, Tries, Heap / Priority Queue, Backtracking, Graphs, 1-D Dynamic Programming, Intervals, Greedy, Advanced Graphs, Math & Geometry, 2-D Dynamic Programming, Bit Manipulation | names only; no per-category problem counts or prerequisite arrows were visible in the text |
| TIH | Tech Interview Handbook, algorithms study cheatsheet (page dated Aug 7, 2026) | the three importance tiers: High = Array, String, Sorting and searching, Matrix, Tree, Graph; Mid = Hash Table, Recursion, Linked List, Queue, Stack, Heap, Trie, Interval; Low = Dynamic programming, Binary, Math, Geometry | tiers only, no order inside a tier; the Grind 75 question count was not read |
| MIT | MIT 6.006 Introduction to Algorithms, Spring 2020 (OCW calendar) | 21 lectures: intro, data structures, sorting, hashing, linear sorting, binary trees (2, with AVL), binary heaps, BFS, DFS, weighted shortest paths, Bellman-Ford, Dijkstra, Johnson, dynamic programming (4 parts), complexity, review, next steps | Spring 2020 is the newest term found; its separate syllabus page was not read |

**Not retrieved:** Stanford CS161 (the public page is a summer-2026 FAQ with no schedule; the schedule is on a login-gated Canvas page). Still to read: Blind 75 and Grind 75 lists, *Cracking the Coding Interview*, *Elements of Programming Interviews*, CLRS, Skiena, CP-Algorithms, USACO Guide, AlgoMonster patterns, LeetCode Explore.

## Coverage matrix

`D` = dedicated category or lecture, `P` = part of one, `-` = not named, `?` = judged from title only.

| Topic | NC | TIH | MIT | Ours (lesson ids) |
|---|---|---|---|---|
| Complexity analysis, recognition habit | - | - | D (intro) | `D` ds00, ds01 |
| Arrays and hash tables | D | D (Hash Table Mid, Array High) | D (hashing) | `D` ds02 |
| Two pointers | D | - | - | `D` ds03 |
| Sliding window | D | - | - | `D` ds04 |
| Prefix sums and difference arrays | - | - | - | `D` ds05 |
| Binary search and search on answer | D | D (searching High) | - | `D` ds06 |
| Stack, monotonic stack and deque | D | D (Stack, Queue Mid) | - | `D` ds07 |
| Heaps and top-K | D | D (Heap Mid) | D (binary heaps) | `D` ds08 |
| Linked lists | D | D (Mid) | - | `D` ds09 |
| Trees and traversals | D | D (High) | D (binary trees, AVL) | `D` ds10 ? |
| Balanced BSTs (AVL, rotations) | - | - | D | `-` |
| Graph traversal (BFS, DFS) | D | D (Graph High) | D (BFS, DFS) | `D` ds11 |
| Union-find | - | - | - | `D` ds12 |
| Backtracking and recursion | D | D (Recursion Mid) | P | `D` ds13 ? |
| Dynamic programming, 1-D and 2-D | D | D (Low) | D (4 lectures) | `D` ds14, ds15, ds21 |
| Greedy and intervals | D | D (Interval Mid) | - | `D` ds16 |
| Tries | D | D (Mid) | - | `D` ds17 |
| Bit manipulation | D | D (Binary Low) | - | `D` ds17 |
| Shortest paths, MST, strongly connected components | D (Advanced Graphs) | - | D (weighted paths, Bellman-Ford, Dijkstra, Johnson) | `D` ds19 (thin) |
| Math and geometry | D | D (Math, Geometry Low) | - | `P` ds22 ? |
| Sorting (comparison and linear) | - | D (High) | D (3 lectures) | `-` |
| Matrix and grid problems | - | D (High) | - | `-` (may be inside ds11) |
| Complexity classes, pseudopolynomial time | - | - | D | `-` |
| Segment and Fenwick trees, string algorithms, topological sort, cyclic sort | - | - | - | `D` ds20, ds23, ds25, ds24 |
| Interview protocol and mock rounds | - | - | - | `D` ds18 |

Reading the matrix: our core 17 lessons match NeetCode's category list one for one, which is expected since it was the model. The sources point to four things we do not teach as lessons of their own: **sorting**, **matrix/grid problems**, **balanced BSTs**, and **recursion fundamentals before backtracking**. Our extras (segment trees, string algorithms, topological sort, cyclic sort) are not named by these three sources; whether they belong is a judgment about the "advanced FAANG bar", not something this benchmark can confirm.

## Hypotheses for the outline (to confirm, not decided)

| # | Proposed change | Action | Why | What gives |
|---|---|---|---|---|
| 1 | Sorting and selection (merge sort, quicksort, quickselect, stability, linear sorts) | add 1 lesson before `ds06` | TIH rates it High and MIT gives it 3 lectures; we have no lesson on it | none |
| 2 | Matrix and grid problems | add 1 lesson, or fold into `ds11` after review | TIH rates Matrix High; grid traversal is a common loop topic | decide after reading `ds11` |
| 3 | Recursion fundamentals | fold into `ds13`, or add a short lesson before it | TIH lists Recursion as Mid; backtracking assumes it | none |
| 4 | Balanced and binary search trees | fold into `ds10` | MIT spends 2 lectures; interview weight is moderate | shorten traversal repetition |
| 5 | Design-a-data-structure (LRU, LFU, min-stack, iterators) | check first | in the overhaul plan's own hypothesis list, **not yet supported by a source I read**; verify against Blind 75 / EPI before adding | none |
| 6 | Thin advanced lessons `ds19` to `ds25` | deepen | all flagged thin by the audit; five also lack practice | none |
| 7 | Pattern-recognition index | add 1 lesson at the end of the core | ties problems to techniques; `ds00` already does part of this, so check overlap | none |

Net effect if all accepted: DSA grows from 26 to about 29 to 31 lessons.

## Open questions

1. Should sorting and matrix problems be separate lessons, or woven into existing ones to keep the course at its current length?
2. Are the "advanced FAANG bar" lessons (`ds19` to `ds25`) meant for every learner, or an optional advanced track?

## Next steps

1. Read the remaining sources (Blind 75, Grind 75, CTCI, EPI, CLRS, CP-Algorithms) and add their columns.
2. Re-judge each "Ours" cell against the lesson body.
3. Move on to the System Design and Behavioral benchmarks.
