# Wave 3 Case-Study Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write the 21 remaining case-study lessons `sy57` to `sy77` (all `Level: extended`) to the standard set by the wave 2 case studies, beginning with ONE sample lesson (`sy68`) that the owner reviews before the rest.

**Architecture:** One Markdown file per lesson, `data/new_lessons/<id>-<slug>.md`; runnable Python checked by `test/lesson_code/<id>_check.py`, wired into `test/lesson-code.test.js`; capacity numbers computed in a `capacity_check_<letter>.py` script. These ids do not exist in the live database, so nothing is loaded live.

**Tech Stack:** Markdown, Python 3 standard library (checks only), Node `node:test`.

**Spec:** `docs/curriculum/lesson-standard.md`, `docs/curriculum/outline.md` (rows `sy57` to `sy77` and the case-study shape: requirements, capacity estimates, API and data model, high-level design, two or three worked deep dives, failure modes, what real companies did with dated sources, drills), `docs/curriculum/decisions.md`. Style and depth: `data/new_lessons/sy54-*.md`, `sy55-*.md`, `sy56-*.md` and their fix-round lessons in `.superpowers/sdd/wave2/` reports (what reviewers caught).

## Global Constraints

- Follow `lesson-standard.md` exactly (shape, truth rule, tested code, 8 drills, homework, Sources, Last reviewed 27 November 2026). Level line: `Level: extended`. Priority line: `(proposed; the curriculum data holds the final rating)`.
- Edit only your lesson files, their check scripts, a `capacity_check_*.py` and `test/lesson-code.test.js`. Never touch curriculum data, other lessons, `data/algoarch.db`, or run `tools/content/import.js` / `update-guide.js`.
- Sources: cite only what you actually read, with the access date; prefer the system's own papers and engineering posts; state in Sources when a page was read in part, blocked or paywalled; do not use paywalled pages. Never attribute your own design (data model, protocol, simulation) to a company. State no company internal numbers you did not read. List what you did NOT consult.
- Capacity numbers come from a script, with assumptions labelled as assumptions. Simulation figures are labelled illustrative. Every number in prose is asserted by a check or labelled illustrative; stale-wording regressions are locked with negative checks.
- Honest limits: when a design has a known hole (a farm, a race, a case a mitigation does not cover), say so and measure it rather than hide it.
- No compensation figures, no invented quotes, no copying of long passages.
- Length: depth, not length. Aim for 25 to 35 KB. Do not repeat material from existing lessons: link to them by their titles.
- Every code check is mutation-tested (two or more breaks per lesson, recorded). Failing check first.
- One commit per lesson, message `content: write <id> <short title>`, trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Do not push. Python standard library only.

## Review Focus

- A claim about a real system or paper not in Sources, or attributed beyond what was read.
- Capacity or sizing arithmetic that charges for impossible quantities (the wave 2 `sy56` mistake): sanity-check every estimate against what can physically be present.
- Prose that contradicts the lesson's own tables or simulation.
- Checks that miss plausible bugs (reviewers find survivors).
- A design example that fails the lesson's own stated tests.

---

### Task 1 (SAMPLE): sy68 Distributed Lock Service (Chubby / ZooKeeper)

**Files:** Create `data/new_lessons/sy68-distributed-lock-service.md`, `test/lesson_code/sy68_check.py`, `test/lesson_code/capacity_check_d.py` (if the lesson has capacity numbers); modify `test/lesson-code.test.js`.

**Interfaces:** Consumes the wave 2 case-study pattern and `sy46` (clocks and ordering), `sy49` (overload) and `sy45` for overlap. Covers: why a lock service exists (coarse-grained locks, leader election, config), leases and session timeouts, fencing tokens (and the exact failure without them), consensus underneath at the level of what the service needs from it (do not re-teach consensus beyond what the existing lessons cover), client caching and KeepAlive, the ZooKeeper-style recipe (ephemeral sequential nodes, watches) with a tested in-memory model of locks, leases, expiry and fencing checked against a naive reference and against a simulated pause-then-resume client; failure modes (clock pause, split brain, thundering herd on lock release). Primary sources to read: the Chubby paper (Burrows, OSDI 2006), the ZooKeeper paper (Hunt et al., USENIX ATC 2010) and ZooKeeper's official recipes docs; read the real text (curl then grep).

- [ ] **Step 1:** Read the outline row, the sources and the neighbouring lessons; write the failing checks first.
- [ ] **Step 2:** Write the lesson, run checks, mutation-test (two or more breaks), `npm test`, `npm run lint:comp`, commit.
- [ ] **Step 3:** Write the report to the path given in the dispatch.

---

## Tasks 2 to 7 (approved by the owner after the sy68 sample)

Each task writes its lessons as `data/new_lessons/<id>-<slug>.md` with `test/lesson_code/<id>_check.py` per lesson that has code (every lesson should have at least a small tested model), one shared `capacity_check_<letter>.py` for the task's capacity numbers, and a wrapper in `test/lesson-code.test.js`. Use the sy68 lesson and its Fix round (`.superpowers/sdd/wave3/task1-report.md`, `task1-review.md`) as the style and as a list of mistakes to avoid. Outline rows give each lesson's title and scope. Statements about real companies cite a source actually read or are omitted; where no engineering source for a product can be read, say so and teach the general design, labelled as such.

- **Task 2** (capacity letter `e`): `sy57` Maps Routing and ETA (Google Maps), `sy58` Hotel and Flight Booking, `sy59` Online Auction.
- **Task 3** (letter `f`): `sy60` Online Judge with sandboxed execution, `sy61` Video Conferencing (WebRTC), `sy62` Music Streaming.
- **Task 4** (letter `g`): `sy63` Email Service, `sy64` Food Delivery Dispatch, `sy65` Live Streaming with Live Comments.
- **Task 5** (letter `h`): `sy66` Log Aggregation and Search, `sy67` Content Delivery Network, `sy69` Dynamo-style Key-Value Store (read `sy45`/`sy46` first: do not repeat consistent hashing and vector clocks; link them).
- **Task 6** (letter `i`): `sy70` Dating App Matching and Swipe Feed, `sy71` Fitness Activity Tracking, `sy72` Multiplayer Game Backend and Matchmaking, `sy73` Price Tracker and Alerts.
- **Task 7** (letter `j`): `sy74` News Aggregator, `sy75` Feature Flags and Config Service, `sy76` Social Graph and People You May Know, `sy77` DNS at Scale.

- [ ] **Step 1:** Read the outline rows, neighbouring lessons for overlap, and the primary sources; write the failing checks first.
- [ ] **Step 2:** Write the lessons; run checks; mutation-test twice or more each; `npm test`; `npm run lint:comp`; one commit per lesson.
- [ ] **Step 3:** Write the report to the path given in the dispatch.
