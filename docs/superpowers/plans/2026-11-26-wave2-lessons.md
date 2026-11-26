# Wave 2 New Lessons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write the 20 new "gap" lessons of wave 2 (`ds27`, `ds28`, `ai28`-`ai31`, `sy45`, `sy46`, `sy48`-`sy52`, `sy54`-`sy56`, `be09`-`be12`) to the standard set by the owner-approved sample `ds26`.

**Architecture:** One Markdown file per lesson, `data/new_lessons/<id>-<slug>.md`. Runnable Python in lessons is extracted and checked by `test/lesson_code/<id>_check.py`, wired into `test/lesson-code.test.js`. These ids do not exist in the live database yet, so nothing is loaded live (see Global Constraints).

**Tech Stack:** Markdown, Python 3 (checks only), Node `node:test`.

**Spec:** `docs/curriculum/lesson-standard.md`, `docs/curriculum/outline.md` (each lesson's row gives title, level and what it covers; for `sy` lessons also the case-study shape), `docs/curriculum/decisions.md`. Approved sample for style and depth: `data/new_lessons/ds26-sorting-selection.md` with `test/lesson_code/ds26_check.py`. Wave 1 lessons (`ds19`-`ds25`, `ai23`-`ai26`, `sy37`-`sy44`, `be07`, `be08`) show the voice for their tracks.

## Global Constraints

- Follow `lesson-standard.md` exactly: the shape (title and blockquote, opening, Mental Model, recognition table, substance, pitfalls, 8 drills, homework, Sources, Last reviewed), the truth rule, tested code. Last reviewed is 26 November 2026.
- Edit only: your lesson files, their check scripts, `test/lesson-code.test.js`. Do not touch curriculum data, other lessons, ids, pathways, or `data/algoarch.db`.
- NEVER run `tools/content/import.js` or `tools/content/update-guide.js` and never open the live database: these ids are new and have no live rows. The controller handles registration.
- Sources: cite only pages you actually read, with the access date (26 November 2026). Prefer primary sources (papers, official docs, source code, engineering posts by the system's own authors). State no company internal numbers you did not read. A claim you cannot support is omitted or marked illustrative. List what you did NOT consult.
- No compensation figures anywhere (decision 4). `npm run lint:comp` must list nothing new.
- No invented quotes. No prior-wave copying: do not reuse sentences from other lessons.
- Where a visual would help write "Visual (planned): ...". Do not build one.
- Level text: `core` lessons say `Level: core`; `extended` say `Level: extended`; `advanced` say `Level: advanced` and note they are optional for a crash plan. Use the outline's level.
- Capacity numbers in case studies are computed by a check script, not by memory.
- Every code check is mutation-tested: break the code at least twice and record that the check fails.
- Commit one lesson per commit, message `content: write <id> <short title>`, ending with the line `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Do not push.
- Python code in lessons: standard library only.

## Review Focus

- A claim about a real system, paper or product that is not in the Sources section.
- Code that runs but does not do what the prose says (off-by-one, wrong complexity, wrong invariant) despite a weak check.
- Capacity arithmetic not reproduced by a script.
- A lesson that is longer but not deeper (a survey of names instead of worked reasoning).
- Compensation figures or invented quotes.
- Overlap with an existing lesson: where the outline says "check X overlap", read X first and avoid repeating it.

---

### Task 1: DSA gap lessons ds27, ds28

**Files:** Create `data/new_lessons/ds27-matrix-grid.md`, `ds28-recursion-fundamentals.md`, `test/lesson_code/ds27_check.py`, `ds28_check.py`; modify `test/lesson-code.test.js`.

**Interfaces:** Consumes the `ds26` pattern. `ds27` Matrix and Grid Problems (core): grid BFS/DFS with direction arrays, flood fill, multi-source BFS, rotate/transpose/spiral, in-place tricks, 2D prefix sums, grid DP; all checked against brute force. `ds28` Recursion Fundamentals (core, short): base case, the recursion tree, stack depth and its limit, memoisation as the bridge to DP, converting recursion to an explicit stack, recursion on subsets/permutations as the lead-in to backtracking (`ds13`); checked against iterative references.

- [ ] **Step 1:** Read the outline rows, the existing neighbours (`ds11`, `ds13`, `ds14` files), and write the failing checks.
- [ ] **Step 2:** Write the lessons; run checks; mutate twice each; `npm test`; commit each.

### Task 2: AI foundations ai28 to ai31

**Files:** Create `data/new_lessons/ai28-autodiff-gradient-descent.md`, `ai29-language-model-from-scratch.md`, `ai30-attention-transformer-block.md`, `ai31-pretraining-scaling-laws.md`, matching `ai28_check.py` ... `ai31_check.py`; modify `test/lesson-code.test.js`.

**Interfaces:** AI foundations block (outline rows 2 to 6). `ai28` Autodiff and Gradient Descent with optimizers (core): a scalar reverse-mode autodiff engine, gradient checks against finite differences, SGD/momentum/Adam on a toy loss; flagship lesson (a gradient-descent scene is planned later: write "Visual (planned)"). `ai29` A Language Model from Scratch and Training Hygiene (core): a bigram/count model then a tiny trained model in pure Python, train/validation split, overfitting, learning-rate sanity checks, loss curves described in numbers produced by the script. `ai30` Attention and the Transformer Block (core): scaled dot-product attention, masking, multi-head, positional information, residual and layer norm, in pure Python lists; check against a naive reference and verify causal masking leaks nothing. `ai31` Pretraining Data and Scaling Laws (extended): data pipelines (dedup, filtering), the idea of scaling laws and compute-optimal training with only the claims you read in the primary papers; a small fit-a-power-law script on synthetic data is allowed, labelled synthetic. Read primary sources (the Transformer paper, Adam paper, Chinchilla/Kaplan papers as available) and list exactly what you read.

- [ ] **Step 1:** Read outline rows and `ai23`-`ai26` for voice; write failing checks first.
- [ ] **Step 2:** Write lessons; checks; mutation-test twice each; `npm test`; commit each.

### Task 3: System design foundations sy45, sy46, sy48, sy49

**Files:** Create `data/new_lessons/sy45-caching-consistent-hashing.md`, `sy46-time-clocks-ordering.md`, `sy48-slos-error-budgets.md`, `sy49-overload-load-shedding.md`, checks where there is code (`sy45` consistent-hash ring with virtual nodes and balance/movement measurement; `sy46` Lamport and vector clocks, a linearizability checker for tiny histories; `sy48` error-budget and burn-rate arithmetic; `sy49` a token bucket / load shedder simulation showing a metastable failure), modify `test/lesson-code.test.js`.

**Interfaces:** Outline rows `sy45`, `sy46`, `sy48`, `sy49`. Concept lessons, with worked code and every number script-produced. Read primary sources (the Dynamo paper, the consistent hashing paper if accessible, Lamport's "Time, Clocks", the Google SRE book chapters on SLOs and overload, etc.) and cite only what you read.

- [ ] **Step 1:** Read outline rows and the existing `sy` lessons they overlap; write failing checks.
- [ ] **Step 2:** Write lessons; checks; mutations; `npm test`; commit each.

### Task 4: System design patterns sy50, sy51, sy52

**Files:** Create `data/new_lessons/sy50-incident-response-postmortems.md`, `sy51-scaling-patterns-reads-writes.md`, `sy52-scaling-patterns-blobs-tasks-realtime.md`, checks for code (`sy51`: write sharding/batching/contention simulation or hot-key splitting; `sy52`: resumable chunked upload bookkeeping and a long-running-task state machine); modify `test/lesson-code.test.js`.

**Interfaces:** Outline rows `sy50` (extended), `sy51`, `sy52` (core). Same standard as Task 3. `sy50` is process, not code: a postmortem template worked on an invented incident clearly labelled illustrative; cite the sources actually read.

- [ ] **Step 1:** Read the outline rows and overlap lessons; failing checks first.
- [ ] **Step 2:** Write; checks; mutations; `npm test`; commit each.

### Task 5: Case studies sy54, sy55, sy56

**Files:** Create `data/new_lessons/sy54-web-crawler.md`, `sy55-file-sync-storage.md`, `sy56-top-k-trending.md`, checks and capacity scripts (`capacity_check_c.py` for all capacity numbers in these three; `sy54` politeness/frontier/dedup simulation; `sy55` chunking and content-hash sync with a deduplication check, and read `sy35` first for overlap; `sy56` a count-min sketch with a space-saving or heap top-k checked against an exact count); modify `test/lesson-code.test.js`.

**Interfaces:** Outline rows `sy54`, `sy55`, `sy56` (core). Case-study shape from `outline.md`: requirements, capacity estimates, API and data model, high-level design, two or three worked deep dives, failure modes, what real companies did with dated sources, drills. Statements about real companies cite a source actually read or are omitted.

- [ ] **Step 1:** Read the outline rows, `sy35`, and write failing checks.
- [ ] **Step 2:** Write; checks; mutations; `npm test`; commit each.

### Task 6: Behavioral Staff arc be09 to be12

**Files:** Create `data/new_lessons/be09-staff-scope-archetypes.md`, `be10-engineering-strategy-design-docs.md`, `be11-operating-at-staff.md`, `be12-career-growth.md`; modify `test/comp-lint.test.js` to assert none of the four lessons carries compensation figures (follow the be08 test).

**Interfaces:** Outline rows `be09` to `be12` (advanced). Voice reference `be07`. No code. Each lesson needs worked examples (labelled illustrative), a sourced framework (read primary sources such as published staff-engineer writing and company career-ladder documents you can actually read), 8 drills, and homework. No compensation figures, no invented quotes, no real people's private details.

- [ ] **Step 1:** Write the failing comp-lint test; read sources; read `be07` for voice.
- [ ] **Step 2:** Write the lessons; `npm test`; `npm run lint:comp`; commit each.
