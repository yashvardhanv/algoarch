# Wave 1 Lesson Rewrites Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deepen the 19 remaining thin "advanced bar" lessons (`ds20`-`ds25`, `ai23`-`ai26`, `sy37`-`sy44`, `be08`) to the standard set by the approved samples `be07` and `ds19`.

**Architecture:** One Markdown file per lesson in `data/new_lessons/`, rewritten in place (ids and file names do not change). Code in lessons is extracted and checked by Python or JS scripts under `test/lesson_code/`, run from `test/lesson-code.test.js`. After each lesson is committed, its guide is loaded into the live database with `tools/content/update-guide.js`.

**Tech Stack:** Markdown, Python 3 (checks only), Node `node:test`.

**Spec:** `docs/curriculum/lesson-standard.md` (the lesson shape and rules), `docs/curriculum/outline.md` (what each lesson should cover and its level), `docs/curriculum/decisions.md`. Approved samples: `data/new_lessons/be07-leveling-matrix.md`, `data/new_lessons/ds19-advanced-graphs.md`.

## Global Constraints

- Follow `docs/curriculum/lesson-standard.md` exactly: the shape, the truth rule, the no-figures rule, tested code, the live-database loader.
- Edit only the lesson files named in your task, the check scripts for them, and `test/lesson-code.test.js`. Do not touch curriculum data, titles, ids, pathways or any other lesson.
- Never run `tools/content/import.js` and never open the live `data/` database with anything but `tools/content/update-guide.js`. Run it with `--was <the commit you started from>` so a CMS edit is never overwritten; if it prints REFUSED, stop and report it, do not use `--force`.
- Sources: cite only pages you actually read, with the access date. Prefer primary sources (papers, official docs, source code). A claim you cannot support is omitted or marked as illustrative. Never state a company's internal numbers or rubric.
- No compensation figures. `npm run lint:comp` must list nothing new.
- Marks: advanced lessons say `Level: advanced`; extended case studies say `Level: extended`; follow `outline.md`.
- Commit one lesson per commit, message `content: rewrite <id> <short title>`; do not push (the controller pushes).

## Review Focus

- A lesson claims a fact, number or behaviour about a real system or paper that was not read: the reviewer checks every such claim against the Sources section.
- Code blocks that run but do not do what the prose says (off-by-one, wrong complexity, wrong loop order) despite passing a weak check.
- Arithmetic in capacity estimates that is not reproduced by a script.
- A lesson that is longer but not deeper (survey of names instead of worked reasoning).
- Compensation figures or invented quotes anywhere.
- The live guide overwritten although it differed from the committed text.

---

### Task 1: DSA advanced lessons ds20 to ds25

**Files:**
- Rewrite: `data/new_lessons/ds20-segment-trees.md`, `ds21-bitmask-dp.md`, `ds22-math-sampling.md`, `ds23-string-algorithms.md`, `ds24.md`, `ds25.md`
- Create: `test/lesson_code/ds20_check.py` ... `ds25_check.py` (one per lesson)
- Modify: `test/lesson-code.test.js` (one test per lesson)

**Interfaces:**
- Consumes: the extraction pattern in `test/lesson_code/ds19_check.py` (python fenced blocks exec'd, functions then compared with brute force) and the ds19 test wrapper.
- Produces: six rewritten lessons; each with brute-force-checked code and a mutation check recorded in the report. `ds25` (topological sort) is core, not advanced; `ds24` is advanced; the outline says which level each is.

- [ ] **Step 1:** For each lesson read its current file, its audit row (`docs/curriculum/audit/audit.csv`) and the outline row. Write the failing check first (it fails because the lesson lacks the functions).
- [ ] **Step 2:** Rewrite the lesson to the standard: recognition table, full worked code (iterative where recursion depth is a trap), pitfalls, drills, homework with named real problems.
- [ ] **Step 3:** Run its check; then break the code in two ways and confirm the check fails; record which mutations were caught.
- [ ] **Step 4:** Run `npm test`; commit the lesson; run `node tools/content/update-guide.js <id> <file> --was <start commit>`.
- [ ] **Step 5:** Repeat for the next lesson; write the report to the path given in the dispatch.

---

### Task 2: AI engineering advanced lessons ai23 to ai26

**Files:**
- Rewrite: `data/new_lessons/ai23-vllm-serving.md`, `ai24-semantic-caching.md`, `ai25-constrained-generation.md`, `ai26-dpo-alignment.md`
- Create: `test/lesson_code/ai23_check.py` ... `ai26_check.py` where the lesson has runnable code
- Modify: `test/lesson-code.test.js`

**Interfaces:**
- Consumes: the same check pattern as Task 1.
- Produces: four rewritten lessons. Per the outline, `ai23` also covers KV cache, FlashAttention and speculative decoding; `ai26` covers SFT, RLHF, DPO and verifiable-reward RL. Runnable code is pure Python with no third-party packages (for example a paged KV-cache block allocator simulation, a cosine-similarity cache with a threshold, a token-mask for constrained decoding, the DPO loss on toy log-probabilities), each checked against a reference computation.

- [ ] **Step 1:** Read each current file, its audit row and outline row. Read primary sources (the vLLM/PagedAttention paper, FlashAttention paper, speculative decoding papers, the DPO paper, official docs) and keep a list of exactly what was read.
- [ ] **Step 2:** Write the failing check, then the lesson. Explain mechanisms with worked numbers produced by the check script, not by memory.
- [ ] **Step 3:** Run the check, mutate the code twice, confirm failures; run `npm test`.
- [ ] **Step 4:** Commit each lesson separately and load each with `update-guide.js --was <start commit>`.
- [ ] **Step 5:** Report the sources read per lesson and any claim you could not verify.

---

### Task 3: System design advanced case studies sy37 to sy40

**Files:**
- Rewrite: `data/new_lessons/sy37-distributed-search.md`, `sy38-collaborative-docs-crdt.md`, `sy39-realtime-leaderboard.md`, `sy40-spanner-truetime-dr.md`
- Create: `test/lesson_code/sy37_check.py` ... where the lesson has code (for example a CRDT merge, a sorted-set leaderboard, an inverted-index scorer) and `capacity_check.py` reproducing every capacity number in these four lessons
- Modify: `test/lesson-code.test.js`

**Interfaces:**
- Consumes: Task 1's pattern; the case-study shape in `outline.md` ("requirements, capacity estimates, API and data model, high-level design, two or three worked deep dives, failure modes, what real companies did with dated sources, drills").
- Produces: four case-study lessons. Capacity numbers are computed in `capacity_check.py`; statements about real companies (Elasticsearch, Google Docs, Spanner) cite a source actually read or are omitted.

- [ ] **Step 1:** Read each current file, audit row, outline row. Read primary sources (the Spanner paper, official Elasticsearch docs, CRDT papers or well-known write-ups) and record what was read.
- [ ] **Step 2:** Write failing checks for code and capacity numbers; then the lessons.
- [ ] **Step 3:** Run checks, mutate twice, run `npm test`.
- [ ] **Step 4:** Commit each lesson separately; load each with `update-guide.js --was <start commit>`.
- [ ] **Step 5:** Report sources read and unverifiable claims.

---

### Task 4: System design advanced case studies sy41 to sy44

**Files:**
- Rewrite: `data/new_lessons/sy41-machine-coding-lld.md`, `sy42.md`, `sy43.md`, `sy44.md`
- Create: `test/lesson_code/sy41_check.py`, and checks for any other lesson with code; extend `capacity_check.py` or add `capacity_check_b.py` for the numbers in `sy42` to `sy44`
- Modify: `test/lesson-code.test.js`

**Interfaces:**
- Consumes: Tasks 1 and 3 patterns. `sy41` is machine coding (parking lot, Splitwise, in-memory DB): its code must be complete, runnable and tested with unit assertions for behaviour and concurrency rules stated. `sy42` flash sale and ticketing, `sy43` proximity service (geohash or quadtree, with working code checked against brute force), `sy44` order matching engine (price-time priority, with a working matching engine checked against a naive reference).
- Produces: four lessons to the standard.

- [ ] **Step 1:** Read each current file, audit row and outline row; read primary sources as in Task 3 and record them.
- [ ] **Step 2:** Failing checks first; then the lessons.
- [ ] **Step 3:** Run checks, mutate twice, run `npm test`.
- [ ] **Step 4:** Commit each lesson separately; load with `update-guide.js --was <start commit>`.
- [ ] **Step 5:** Report sources read and unverifiable claims.

---

### Task 5: Behavioral be08 (offer structure and equity)

**Files:**
- Rewrite: `data/new_lessons/be08-ctc-equity-playbook.md`
- Test: `npm run lint:comp` and `test/comp-lint.test.js` (add a test that reads this file and asserts `findCompClaims` finds nothing)

**Interfaces:**
- Consumes: the be07 sample as the Behavioral voice reference; `decisions.md` decision 4 (no figures).
- Produces: a lesson on offer structure, equity mechanics (grants, vesting, cliffs, refreshers, strike and exercise, tax timing as concepts), negotiation structure and trade-offs, with dated sources read for each general claim. It states no amounts. Title in the outline is "Offer Structure and Equity Playbook"; the heading in the file uses it, the curriculum title is not changed here.

- [ ] **Step 1:** Write the failing test (`be08 lesson carries no compensation figures`) and run it; read the current file and the audit row; read at least two reputable public explainers of equity compensation and record exactly what was read (access date, URL).
- [ ] **Step 2:** Rewrite to the standard; say plainly that tax and vesting rules vary by country and company and the lesson is not tax advice; include drills and homework (a worksheet for comparing two offers by structure).
- [ ] **Step 3:** Run the test and `npm test`.
- [ ] **Step 4:** Commit; load with `update-guide.js --was <start commit>`.
- [ ] **Step 5:** Report the sources read.
