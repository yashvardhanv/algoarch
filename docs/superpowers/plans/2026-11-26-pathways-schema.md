# Pathways and Curriculum Schema (Phase 2a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lessons can carry optional prerequisites, objectives, level, review date and sources; curriculum "pathways" (ordered lesson lists) are stored in the database and served by an API; a validator proves the prerequisite graph and pathways are sound and no lesson id is ever lost.

**Architecture:** A pure module `curriculum.js` holds the rules (duration parsing, cycle detection, pathway checks, id-loss check). The importer and repo store the new fields and pathways. A new `/api/pathways` endpoint serves them. A generator derives a first set of pathways from existing lesson data by fixed rules, and a validator CLI plus one real-data test keep it honest.

**Tech Stack:** Node 20, CommonJS, `better-sqlite3`, `node:test`. Web types in `web/src/types.ts` (TypeScript, checked with `npm run typecheck`).

**Spec:** `docs/plans/curriculum-overhaul-plan.md` §4 (only on branch `origin/claude/epic-davinci-ugc6xq`); owner decisions in `docs/curriculum/decisions.md`; direction in `docs/curriculum/benchmark-summary.md`.

**Out of scope (later plans):** the planner and overview UI, authoring prerequisites and objectives per lesson (done during the Phase 3 rewrite), `level`-based pathways (they need `level` authored first), and adding new lessons.

## Global Constraints

- All new lesson fields are optional and additive: a lesson with none of them produces exactly the same JSON as today (no new keys, no nulls).
- Lesson ids are never renamed, reused or dropped. `data/migrations/2026-11-26-curriculum-map.json` records the baseline of 106 ids; a test fails if any baseline id disappears from `data/curriculum.json`.
- Every `/api` route except `/api/auth/*` requires a sign-in (existing gate in `server.js`); `/api/pathways` must not bypass it.
- No new dependencies. No network access.
- Database changes are a new migration with `id: 4` appended to `MIGRATIONS` in `db.js` (ids 1 to 3 exist; do not edit them). No foreign keys on the new tables or columns (the importer rebuilds lessons).
- Never commit `data/*.db`, `data/users.json`, `data/.auth_secret`.
- Duration strings look like `"45 min"`, `"45 min drill"`, `"60 min"`; some lessons have none.
- Code style: CommonJS `require`, 2-space indent, single quotes, matching `db.js`.
- The suite is `npm test` (currently 63 passing); each task ends with it green.

## Review Focus

1. A lesson with none of the new fields: `/api/curriculum` output for it is byte-identical to today (no new keys). Owner: Task 2.
2. A pathway that names a lesson id that does not exist: the importer refuses to write pathways and throws an error naming the pathway and id, instead of silently dropping it. Owner: Task 2.
3. Duration strings such as `"45 min drill"` and a missing duration never produce `NaN`; missing is 0 minutes. Owner: Task 1.
4. A diamond (two lessons sharing one prerequisite) is not reported as a cycle; a self-prerequisite is. Owner: Task 1.
5. Importing twice leaves exactly one copy of each pathway and each pathway lesson. Owner: Task 2.

---

## File Structure

| File | Responsibility |
|---|---|
| `curriculum.js` (repo root, beside `lessonText.js`) | Pure rules: `parseMinutes`, `findPrereqProblems`, `checkPathways`, `unreachableLessons`, `checkMigrationMap` |
| `db.js` | Migration 4 (lesson columns + pathway tables); `lessonRow` and `getCurriculum` emit new optional fields; `getPathways()` |
| `tools/content/import.js` | Writes the new lesson fields and `data/pathways.json` |
| `server.js` | `GET /api/pathways` |
| `web/src/types.ts` | `LessonMeta` optional fields; `Pathway` and `PathwayLesson` types |
| `tools/content/build-pathways.js` | Generator: `data/curriculum.json` to `data/pathways.json` by fixed rules |
| `tools/content/validate-curriculum.js` | CLI: validates graph, pathways, id baseline; `--write-baseline` creates the baseline file |
| `data/pathways.json`, `data/migrations/2026-11-26-curriculum-map.json` | Generated data, committed |
| `test/curriculum.test.js` | Pure-function tests, DB and API tests, real-data test |

Data shapes:
- `curriculum.json` lesson, new optional fields: `prereqs: string[]` (lesson ids), `objectives: string[]`, `level: 'mid' | 'senior' | 'staff'`, `reviewedAt: 'YYYY-MM-DD'`, `sources: { title: string, url: string, accessed: 'YYYY-MM-DD' }[]`.
- `data/pathways.json`: `{ "pathways": [ { "id": string, "title": string, "description": string, "kind": "horizon" | "goal" | "level", "lessons": [ { "id": string, "note"?: string } ] } ] }`.
- API `GET /api/pathways`: `{ pathways: [ { id, title, description, kind, minutes: number, lessons: [ { id, title, trackId, duration, note? } ] } ] }`.

---

### Task 1: Curriculum rules module

**Files:**
- Create: `curriculum.js`
- Test: `test/curriculum.test.js`

**Interfaces:**
- Produces:
  - `parseMinutes(duration: string | null | undefined): number`, the first integer followed by optional space and `min`; otherwise 0.
  - `findPrereqProblems(lessons: { id: string, prereqs?: string[] }[]): { unknown: { lesson: string, prereq: string }[], selfLoops: string[], cycles: string[][] }`. `cycles` lists each distinct cycle once as the ids in order, rotated to start at the smallest id; `selfLoops` are not repeated in `cycles`; output is deterministic.
  - `checkPathways(pathways: { id: string, lessons: { id: string }[] }[], lessons: { id: string, duration?: string, prereqs?: string[] }[]): { errors: string[], warnings: string[], minutes: Record<string, number> }`. Errors: `unknown lesson <id> in <pathwayId>`, `duplicate lesson <id> in <pathwayId>`, `empty pathway <pathwayId>`, `<pathwayId>: <lesson> comes before its prerequisite <prereq>`. Warnings: `<pathwayId>: <lesson> needs <prereq>, which the pathway does not include`.
  - `unreachableLessons(pathways, lessons): string[]`, ids in no pathway, in `lessons` order.
  - `checkMigrationMap(baselineIds: string[], currentIds: string[]): { missing: string[], added: string[] }`, both in sorted order.

- [ ] **Step 1: Write failing tests** in `test/curriculum.test.js`:
  - `parseMinutes('45 min')` is `45`, `parseMinutes('45 min drill')` is `45`, `parseMinutes('1 hr')` is `0`, `parseMinutes(undefined)` and `parseMinutes('')` are `0` (never `NaN`).
  - Diamond: lessons `a`, `b(prereqs a)`, `c(prereqs a)`, `d(prereqs b, c)` gives no cycles and no selfLoops. Cycle: `a(prereqs c)`, `b(prereqs a)`, `c(prereqs b)` gives `cycles` equal to `[['a', 'c', 'b']]`. Self-loop: `x(prereqs x)` gives `selfLoops` equal to `['x']` and `cycles` equal to `[]`. Unknown: `y(prereqs nope)` gives `unknown` equal to `[{ lesson: 'y', prereq: 'nope' }]`.
  - `checkPathways`: a pathway listing `b` before its prerequisite `a` yields the error `p1: b comes before its prerequisite a`; a pathway with `b` but not `a` yields the warning `p1: b needs a, which the pathway does not include`; unknown id, duplicate and empty pathway yield their errors; `minutes` for `[{45 min},{45 min drill},{no duration}]` is `90`.
  - `unreachableLessons` returns only ids that appear in no pathway.
  - `checkMigrationMap(['a','b','c'], ['b','c','d'])` equals `{ missing: ['a'], added: ['d'] }`.
- [ ] **Step 2: Run to verify failure.** Run: `node --test test/curriculum.test.js`. Expected: FAIL, `Cannot find module '../curriculum'`.
- [ ] **Step 3: Implement** `curriculum.js` with the signatures above and `module.exports = { parseMinutes, findPrereqProblems, checkPathways, unreachableLessons, checkMigrationMap }`. Use an iterative or recursive depth-first search with visiting and done sets for cycles.
- [ ] **Step 4: Run to verify pass.** Run: `node --test test/curriculum.test.js`, then `npm test`. Expected: PASS.
- [ ] **Step 5: Commit.**
```bash
git add curriculum.js test/curriculum.test.js
git commit -m "tools: curriculum rules module (prereq graph, pathway checks, id baseline)"
```

---

### Task 2: Store the new fields and pathways

**Files:**
- Modify: `db.js` (append migration `id: 4`; `lessonRow`; `getCurriculum` unchanged shape; add `getPathways`), `tools/content/import.js`
- Test: `test/curriculum.test.js`

**Interfaces:**
- Consumes: `parseMinutes` from Task 1; `openDb(dataDir)` and `createRepo(db)` from `db.js`.
- Produces:
  - Migration 4 SQL: `ALTER TABLE lessons ADD COLUMN prereqs TEXT NOT NULL DEFAULT '[]'`; the same for `objectives` and `sources` (default `'[]'`); `ADD COLUMN level TEXT`; `ADD COLUMN reviewed_at TEXT`; `CREATE TABLE pathways (id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT, kind TEXT NOT NULL, position INTEGER NOT NULL)`; `CREATE TABLE pathway_lessons (pathway_id TEXT NOT NULL, lesson_id TEXT NOT NULL, position INTEGER NOT NULL, note TEXT, PRIMARY KEY (pathway_id, lesson_id))`.
  - `lessonRow` adds `prereqs`, `objectives`, `sources` (only when the parsed array is non-empty) and `level`, `reviewedAt` (only when set). A lesson with none of them is unchanged.
  - `repo.getPathways(): { id, title, description, kind, minutes, lessons: { id, title, trackId, duration, note? }[] }[]` in pathway `position` order, lessons in `position` order; `note` omitted when null; a pathway lesson whose id no longer exists in `lessons` is omitted from the list.
  - Importer: reads the optional new fields from each lesson in `curriculum.json` into the INSERT (`JSON.stringify` for arrays); if `data/pathways.json` exists, replaces the pathway tables inside the same transaction (`DELETE FROM pathways; DELETE FROM pathway_lessons;` then inserts). Before writing, if any pathway lesson id is missing from `curriculum.json`, throw `Error('pathway <id> references unknown lesson <lessonId>')` before any write.

- [ ] **Step 1: Write failing tests** (fixture database via `openDb(tmp)` and raw SQL, the same approach as `test/audit.test.js`):
  - Review Focus 1: a lesson inserted without the new columns returns a `lessonRow` object with none of `prereqs`, `objectives`, `sources`, `level`, `reviewedAt` keys; a lesson with `prereqs: '["a"]'`, `level: 'senior'`, `reviewed_at: '2026-11-26'` returns those as `prereqs: ['a']`, `level: 'senior'`, `reviewedAt: '2026-11-26'`.
  - `getPathways()` returns lessons in position order with `minutes` equal to the sum of `parseMinutes`, omits a removed lesson, and omits `note` when null.
  - Review Focus 2: run the importer's pathway step with a pathway naming an unknown id and assert the thrown message and that no pathway rows were written. To make this testable, put the pathway load in an exported function `importPathways(db, pathwaysJson, lessonIds)` in `tools/content/import.js` (guard the existing `main()` call with `if (require.main === module)`), called by `main`.
  - Review Focus 5: calling `importPathways` twice with the same data leaves `COUNT(*)` of `pathways` and `pathway_lessons` unchanged.
- [ ] **Step 2: Run to verify failure.** Run: `node --test test/curriculum.test.js`. Expected: FAIL on the new tests (missing columns, `importPathways` not exported).
- [ ] **Step 3: Implement** migration 4, the `lessonRow` and `getPathways` changes in `db.js`, and the importer changes. Keep `main()` behavior identical when run as a script.
- [ ] **Step 4: Run to verify pass.** Run: `node --test test/curriculum.test.js`, then `npm test`. Expected: PASS, including all existing tests.
- [ ] **Step 5: Commit.**
```bash
git add db.js tools/content/import.js test/curriculum.test.js
git commit -m "schema: optional lesson fields and pathway tables (migration 4)"
```

---

### Task 3: Pathways API and web types

**Files:**
- Modify: `server.js`, `web/src/types.ts`
- Test: `test/curriculum.test.js` (a server-spawning section in the style of `test/security.test.js`: temp copy of `data/`, `AUTH_SECRET`, dev sign-in, with the OAuth environment variables deleted so the run is hermetic)

**Interfaces:**
- Consumes: `repo.getPathways()` from Task 2.
- Produces: `GET /api/pathways` returning `{ pathways: Pathway[] }` (shape in File Structure); `web/src/types.ts` gains `export interface PathwayLesson { id: string; title: string; trackId: string; duration: string; note?: string }`, `export interface Pathway { id: string; title: string; description: string; kind: 'horizon' | 'goal' | 'level'; minutes: number; lessons: PathwayLesson[] }` and the optional fields `prereqs?: string[]; objectives?: string[]; level?: 'mid' | 'senior' | 'staff'; reviewedAt?: string; sources?: { title: string; url: string; accessed: string }[]` on `LessonMeta`.

- [ ] **Step 1: Write failing tests:** an unauthenticated `GET /api/pathways` returns 401; an authenticated call returns 200 with a `pathways` array; with a fixture pathway inserted in the temp database (via `importPathways` or SQL before the server starts), the response lists it with the right `minutes`.
- [ ] **Step 2: Run to verify failure.** Run: `node --test test/curriculum.test.js`. Expected: FAIL (404 or missing route).
- [ ] **Step 3: Implement** the route (`sendJson(res, 200, { pathways: repo.getPathways() })`) before the generic handlers, and the type additions.
- [ ] **Step 4: Run to verify pass.** Run: `node --test test/curriculum.test.js`, `npm run typecheck`, then `npm test`. Expected: all PASS.
- [ ] **Step 5: Commit.**
```bash
git add server.js web/src/types.ts test/curriculum.test.js
git commit -m "api: GET /api/pathways and pathway types"
```

---

### Task 4: Generated pathways, validator CLI and id baseline

**Files:**
- Create: `tools/content/build-pathways.js`, `tools/content/validate-curriculum.js`, `data/pathways.json` (generated), `data/migrations/2026-11-26-curriculum-map.json` (generated)
- Modify: `package.json` (scripts `pathways` and `validate:curriculum`)
- Test: `test/curriculum.test.js`

**Interfaces:**
- Consumes: Task 1 functions; `data/curriculum.json`.
- Produces:
  - `buildPathways(curriculum: object): { pathways: Pathway[] }` exported from `build-pathways.js` (shape: `data/pathways.json`), deterministic, by these fixed rules, with lessons in curriculum order (track order, then block, then lesson):
    - `crash` (kind `horizon`): lessons with `stars === 5`.
    - `standard` (kind `horizon`): lessons with `stars >= 4`.
    - `deep` (kind `horizon`): every lesson.
    - `dsa`, `system-design`, `ai-engineering`, `behavioral` (kind `goal`): every lesson of that track.
    - Each has a title and a one-sentence description stating its rule (for example "Every lesson rated 5 stars, in course order"). No invented claims about weeks or hours.
  - `validate-curriculum.js` CLI: `node tools/content/validate-curriculum.js [--write-baseline]` loads `data/curriculum.json` and `data/pathways.json`, runs the Task 1 checks, prints errors, warnings, `minutes` per pathway and unreachable lessons, and exits 1 on any error. `--write-baseline` writes `data/migrations/2026-11-26-curriculum-map.json` as `{ "version": 1, "date": "2026-11-26", "ids": [<all current lesson ids, sorted>] }`.
  - The baseline file contains the 106 current ids.

- [ ] **Step 1: Write failing tests:**
  - `buildPathways` on a small fixture curriculum (two tracks, stars 5/4/3) gives `crash` equal to the stars-5 ids in order, `standard` the stars >= 4 ids, `deep` all, one `goal` pathway per track; running it twice gives identical output.
  - Real-data test: load the repo's `data/curriculum.json`, `data/pathways.json` and the baseline file; assert `checkPathways` returns no errors; `unreachableLessons` is empty; `findPrereqProblems` reports no unknown, self-loops or cycles; and `checkMigrationMap(baseline.ids, currentIds).missing` is empty and `baseline.ids.length === 106`. This test is what protects progress data from a lost id.
- [ ] **Step 2: Run to verify failure.** Run: `node --test test/curriculum.test.js`. Expected: FAIL (missing module and data files).
- [ ] **Step 3: Implement** the generator and the validator, then generate the data: `node tools/content/validate-curriculum.js --write-baseline`, then write `data/pathways.json` from `buildPathways` (add a `--write` flag to `build-pathways.js` that writes the file; the `pathways` npm script runs it that way).
- [ ] **Step 4: Run to verify pass.** Run: `node tools/content/validate-curriculum.js` (exit 0), `node --test test/curriculum.test.js`, then `npm test`. Expected: all PASS.
- [ ] **Step 5: Import check.** Import into a scratch directory (copy `curriculum.json`, `videos.json`, `resources.json`, `pathways.json`, `new_lessons/`; run `node tools/content/import.js --data <tmp> --reset --projects "C:\YASH\CODES\YASHVARDHAN_FAANG\AI-System_design_DSA\PROJECTS"`) and confirm the report has `lessons: 106`, then query the scratch database for 7 rows in `pathways` and `deep` holding 106 rows in `pathway_lessons`. Do not touch the live `data/algoarch.db`.
- [ ] **Step 6: Commit.**
```bash
git add tools/content/build-pathways.js tools/content/validate-curriculum.js data/pathways.json data/migrations/2026-11-26-curriculum-map.json package.json test/curriculum.test.js
git commit -m "content: generated pathways, curriculum validator and id baseline"
```

---

## Follow-on plans

1. **Planner and overview UI** for pathways (public/app.js planner, home overview).
2. **Authoring prerequisites, objectives, level and reviewedAt** lesson by lesson during the Phase 3 rewrite; then `level` pathways (mid, senior, staff).
3. **Adding the new lessons** the benchmarks propose, each with stable new ids that continue the track sequence.

## Self-Review Notes

- **Spec coverage (§4):** optional schema fields (Task 2), pathways stored and served (Tasks 2 to 3), prerequisite DAG validation and "every lesson reachable" (Tasks 1 and 4), id migration map (Task 4), tests (all). `sceneIds` is deferred to the motion-kit plan; `lesson.pathways[]` is served by `/api/pathways` rather than stored per lesson, to avoid two sources of truth; planner UI and level pathways are explicit follow-ons.
- **Types:** `Pathway` is the same shape in the data file, the repo and the API, except that the API adds `minutes` and expands lesson titles.
- **Proportion:** the plan is shorter than the spec section it implements plus the surrounding detail; code appears only as signatures, test names and values.
