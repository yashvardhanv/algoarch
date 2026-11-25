# Curriculum Audit (Phase 0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A deterministic, read-only script that measures every lesson in the AlgoArch database and writes `docs/curriculum/audit/audit.csv` plus `audit-summary.md`, so the owner can approve the counts before any course is redesigned.

**Architecture:** Pure metric and flag functions in `tools/content/audit/` (unit-tested with no database), a loader that reads the SQLite file read-only, and a thin CLI that writes the two output files. The audit never changes lessons, ids or the database.

**Tech Stack:** Node 20, CommonJS, `better-sqlite3` (already a dependency), `node:test` (the repo's test runner: `npm test` runs `node --test test/`).

**Spec:** `docs/plans/curriculum-overhaul-plan.md` §2 "Phase 0". It lives on branch `origin/claude/epic-davinci-ugc6xq` (commit `0569e0a`), not on `main`. Read it with `git show origin/claude/epic-davinci-ugc6xq:docs/plans/curriculum-overhaul-plan.md`.

## Global Constraints

- No new dependencies. No network access at any point.
- Open the database with `{ readonly: true }`. The audit must never write to `data/algoarch.db`.
- Never commit `data/*.db`, `data/users.json` or `data/.auth_secret` (already git-ignored; keep it that way).
- Output order is deterministic: tracks by `tracks.position`, then lessons by block position, then lesson position. No timestamps inside `audit.csv`.
- Lesson ids are never renamed, reused or dropped; the audit only reads them.
- Thin-lesson rule (spec §5.1): **fewer than 600 words and no code cell and no widget**.
- Quality flags are exactly: `thin`, `no-visual`, `no-practice`, `no-pitfalls`, `bad-document`.
- `outdated-claim?` and `inconsistent-notation` from the spec are manual review flags; the script does not compute them (it emits an empty `manual_flags` column for the reviewer).
- Code style: CommonJS `require`, 2-space indent, single quotes, matching `db.js`.

## Review Focus

Inputs and conditions the spec implies but does not spell out. Each has a test in the task that owns the code.

1. A lesson with no guide row **and** no document row (e.g. `ai00`): the audit still emits a row (zero counts, `has_source=false`) instead of crashing. Owner: Task 4.
2. A `lesson_documents.document` value that is not valid JSON or lacks `sections`: the row is flagged `bad-document` and counted as zero words. The audit continues. Owner: Task 4.
3. Titles containing commas, quotes, newlines or non-ASCII (`·`, `₹`): `audit.csv` stays valid CSV and round-trips. Owner: Task 4.
4. A video whose `lesson_id` is NULL or empty is not an orphan; only a non-empty id that matches no lesson is. Owner: Task 3.
5. Sequels ("Postgres I: Indexes" vs "Postgres II: MVCC") must not be reported as duplicate topics; only near-identical titles are. Owner: Task 3.

---

## File Structure

| File | Responsibility |
|---|---|
| `tools/content/audit/metrics.js` | Pure functions: `wordCount`, `documentStats`, `guideStats` |
| `tools/content/audit/flags.js` | Pure function: `flagLesson` |
| `tools/content/audit/crosscheck.js` | Pure functions: `findOrphanVideos`, `findDuplicateTitles`, `findBrokenRefs` |
| `tools/content/audit/build.js` | `loadAuditInput`, `buildAudit`, `toCsv`, `renderSummary` |
| `tools/content/audit.js` | CLI: `node tools/content/audit.js [--data <dir>] [--out <dir>]` |
| `test/audit.test.js` | All tests (pure-function tests plus one integration test on a temp database) |
| `docs/curriculum/audit/audit.csv`, `audit-summary.md` | Generated deliverables, committed in Task 5 |
| `package.json` | Add script `"audit": "node tools/content/audit.js"` |

Database facts the loader relies on (from `db.js`): `lessons(id, track_id, block_id, position, num, title, stars, description, duration, is_new, tags, companies, lab_file)`; `course_blocks(id, track_id, key, title, position)`; `tracks(id, name, position)`; `lesson_guides(lesson_id, markdown, updated_at)`; `lesson_documents(lesson_id, schema_version, document, updated_at)`; `lesson_labs(lesson_id, file_name, code)`; `videos(pk, id, youtube_id, track_id, lesson_id, title, ...)`. `document` is JSON `{ schemaVersion, title, lede, sections: [{ blocks: [...] }] }`. Block types that matter: `heading`, `code`, `code_cell` (`starter`, `tests`), `widget` (`kind`, `ported`), `callout`/`card`/`qa` (nested `blocks`), and `diagram` or `scene` if present (visual blocks).

---

### Task 1: Text and document metrics

**Files:**
- Create: `tools/content/audit/metrics.js`
- Test: `test/audit.test.js`

**Interfaces:**
- Produces:
  - `wordCount(text: string): number`, whitespace-separated tokens containing at least one letter or digit.
  - `guideStats(markdown: string | null): { words: number, headings: number, codeBlocks: number }`, headings are lines matching `^#{2,4}\s`; `codeBlocks` counts fenced pairs (a line starting with three backticks opens, the next closes).
  - `documentStats(doc: object | null): { words, headings, codeBlocks, codeCells, cellsWithTests, widgets, widgetsPorted, quizzes, checklists, visuals, text }`. It walks `doc.sections[].blocks[]` recursively through any block's `blocks` array and through `qa` bodies. `words` counts inline text from `paragraph`, `heading`, `list`, `quote`, `say`, table cells and `code` blocks; `quizzes` = widgets with `kind === 'quiz'`; `checklists` = widgets with `kind` `checklist` or `scorecard`; `visuals` = `diagram` or `scene` blocks plus widgets with `kind === 'frames'` or `kind === 'trace'`; `text` is the concatenated plain text (used later for the pitfalls check).
  - Inline nodes are either strings or objects with a child array `c` (see `web/src/types.ts` `Inline`); flatten both.

- [ ] **Step 1: Write the failing tests** in `test/audit.test.js` using `node:test` and `node:assert/strict`:
  - `wordCount('Two  pointers: O(n) -- fast')` equals `4` (the lone `--` is not a word).
  - `guideStats('## A\ntext words here\n```py\nx=1\n```\n### B')` equals `{ words: 6, headings: 2, codeBlocks: 1 }`. The pinned choice: the fence marker lines (the lines starting with three backticks) are not words, but the code between them is.
  - `documentStats(null)` returns all zeros and `text === ''`.
  - A document with one section containing a paragraph `['Hello ', { c: ['big'] }, ' world']`, a `code_cell` with non-empty `tests`, a `widget` `{ kind: 'frames', ported: true }`, a `widget` `{ kind: 'quiz', ported: false }`, and a `callout` whose nested `blocks` hold one more paragraph of 2 words gives `words >= 5`, `codeCells === 1`, `cellsWithTests === 1`, `widgets === 2`, `widgetsPorted === 1`, `quizzes === 1`, `visuals === 1`.

- [ ] **Step 2: Run to verify failure.** Run: `node --test test/audit.test.js`. Expected: FAIL, `Cannot find module '../tools/content/audit/metrics'`.

- [ ] **Step 3: Implement** the three functions in `tools/content/audit/metrics.js` with the signatures above and `module.exports = { wordCount, guideStats, documentStats }`. Walk blocks with one recursive function; treat unknown block types as having no text rather than throwing.

- [ ] **Step 4: Run to verify pass.** Run: `node --test test/audit.test.js`. Expected: all Task 1 tests PASS.

- [ ] **Step 5: Commit.**
```bash
git add tools/content/audit/metrics.js test/audit.test.js
git commit -m "tools: audit text and document metrics"
```

---

### Task 2: Quality flags

**Files:**
- Create: `tools/content/audit/flags.js`
- Modify: `test/audit.test.js`

**Interfaces:**
- Consumes: the shapes returned by Task 1.
- Produces: `flagLesson(row: { guide: ReturnType<guideStats>, doc: ReturnType<documentStats>, drills: number, badDocument: boolean }): string[]`. Returns a sorted array drawn only from `thin`, `no-visual`, `no-practice`, `no-pitfalls`, `bad-document`. Rules:
  - `thin`: `guide.words + doc.words < 600` and `doc.codeCells + doc.widgets === 0`.
  - `no-visual`: `doc.visuals === 0` and `doc.widgetsPorted === 0`.
  - `no-practice`: `doc.codeCells + doc.quizzes + doc.checklists + drills === 0`.
  - `no-pitfalls`: neither the guide nor `doc.text` matches `/pitfall|mistake|gotcha|failure mode|common error|anti-?pattern/i`. `flagLesson` receives `guidePitfall: boolean` and `docPitfall: boolean` computed by the caller (add both to the `row` argument) so this function stays regex-free of large inputs.
  - `bad-document`: `row.badDocument`.
- Also produces: `countDrills(markdown: string | null): number`, the number of list items under a heading matching `/^#{2,3}\s+(Drills|Homework|Mock Drills|Practice Exercises)/im`, up to the next heading (mirrors `extractDrills` in `server.js`, which returns at most 10).

- [ ] **Step 1: Write failing tests:** a 599-word lesson with no cell or widget gets `thin`; the same lesson with one `codeCell` does not; 600 words exactly is not thin; a lesson with a ported widget and nothing else has no `no-visual` and no `no-practice` only if it also has a quiz/cell/drill (assert both outcomes); `badDocument: true` yields `bad-document`; `countDrills('## Drills\n1. a\n2. b\n## Next\n1. c')` equals `2`.
- [ ] **Step 2: Run to verify failure.** Run: `node --test test/audit.test.js`. Expected: FAIL on missing module `flags`.
- [ ] **Step 3: Implement** `flagLesson` and `countDrills` per the rules above; export both.
- [ ] **Step 4: Run to verify pass.** Run: `node --test test/audit.test.js`. Expected: PASS.
- [ ] **Step 5: Commit.**
```bash
git add tools/content/audit/flags.js test/audit.test.js
git commit -m "tools: audit quality flags"
```

---

### Task 3: Cross-lesson checks

**Files:**
- Create: `tools/content/audit/crosscheck.js`
- Modify: `test/audit.test.js`

**Interfaces:**
- Produces:
  - `findOrphanVideos(videos: { id: string, lessonId: string | null }[], lessonIds: Set<string>): string[]`, video ids whose non-empty `lessonId` is not in `lessonIds`. NULL, `''` and whitespace are never orphans (Review Focus 4).
  - `findDuplicateTitles(lessons: { id: string, title: string }[], threshold?: number): [string, string][]`, id pairs whose normalized titles have token-set Jaccard similarity `>= threshold` (default `0.85`). Normalize: lowercase, strip punctuation, drop standalone digits and roman numerals `i ii iii iv v vi vii viii ix x`, drop the words `part`, `the`, `a`, `and`.
  - `findBrokenRefs(guides: { id: string, markdown: string }[], lessonIds: Set<string>): { from: string, to: string }[]`, references written as `#open-lesson-<id>` or as markdown links to `lesson:<id>` that name an id not in `lessonIds`.

- [ ] **Step 1: Write failing tests:**
  - `findOrphanVideos([{id:'v1',lessonId:'ds01'},{id:'v2',lessonId:null},{id:'v3',lessonId:' '},{id:'v4',lessonId:'zz99'}], new Set(['ds01']))` equals `['v4']`.
  - `findDuplicateTitles([{id:'a',title:'Two Pointers'},{id:'b',title:'Two Pointers: Part II'},{id:'c',title:'Postgres I: Indexes & Scans'},{id:'d',title:'Postgres II: MVCC & Locking'}])` equals `[['a','b']]`.
  - `findBrokenRefs([{id:'ds02',markdown:'see [x](#open-lesson-ds01) and [y](#open-lesson-nope)'}], new Set(['ds01','ds02']))` equals `[{from:'ds02',to:'nope'}]`.
- [ ] **Step 2: Run to verify failure.** Run: `node --test test/audit.test.js`. Expected: FAIL on missing module `crosscheck`.
- [ ] **Step 3: Implement** the three functions; return pairs and refs in input order so output is deterministic.
- [ ] **Step 4: Run to verify pass.** Run: `node --test test/audit.test.js`. Expected: PASS.
- [ ] **Step 5: Commit.**
```bash
git add tools/content/audit/crosscheck.js test/audit.test.js
git commit -m "tools: audit cross-lesson checks"
```

---

### Task 4: Database loader, CSV and summary

**Files:**
- Create: `tools/content/audit/build.js`, `tools/content/audit.js`
- Modify: `test/audit.test.js`, `package.json` (add the `audit` script)

**Interfaces:**
- Consumes: everything from Tasks 1 to 3.
- Produces in `build.js`:
  - `loadAuditInput(dataDir: string): AuditInput`, opens `path.join(dataDir, 'algoarch.db')` read-only and returns `{ lessons: LessonRecord[], videos, guides }`. A `LessonRecord` carries `id, track, trackName, block, title, stars, duration, isNew, hasGuide, hasDocument, hasLab, markdown, document` (parsed JSON or `null`), and `badDocument` (true if the JSON is invalid or has no `sections` array).
  - `buildAudit(input: AuditInput): { rows: AuditRow[], summary: object }`. Each `AuditRow` has exactly these CSV columns, in this order: `id, track, block, title, stars, declared_duration, words, headings, code_blocks, code_cells, cells_with_tests, widgets, widgets_ported, quizzes, checklists, visuals, drills, videos_linked, has_source, is_new, flags, manual_flags`. `has_source` = the lesson has a guide row or a document row. `videos_linked` = videos whose `lessonId` equals the lesson id. `flags` is `;`-joined (empty string when none). `manual_flags` is always empty.
  - `summary` has `{ totals, byTrack, byFlag, sourceSplit, orphanVideos, duplicateTitles, brokenRefs }` where `byFlag` is counts per flag per track.
  - `toCsv(rows: AuditRow[]): string`, RFC 4180: quote any field containing `,`, `"`, `\n` or `\r`, double embedded quotes, `\n` line endings, header first, trailing newline.
  - `renderSummary(summary: object): string`, Markdown with the headings `# Curriculum audit`, `## Totals`, `## Flags by course`, `## Source coverage`, `## Orphan videos`, `## Duplicate topics`, `## Broken cross-references`, and a final `## Owner gate` section that lists the three decisions needed (see Task 5).
- CLI `tools/content/audit.js`: flags `--data <dir>` (default `data`) and `--out <dir>` (default `docs/curriculum/audit`); creates the output directory; writes `audit.csv` and `audit-summary.md`; prints one line with the row count and per-flag totals.

- [ ] **Step 1: Write failing integration tests** that create a temp data directory with `openDb(tmp)` from `db.js`, insert one track, one block and five lessons with raw SQL, then call `buildAudit(loadAuditInput(tmp))`:
  - Lesson `L1`: guide of 700 words and a valid document with a ported `frames` widget, a `code_cell` with tests and a quiz. Expect `flags === ''` for `thin`, `no-visual` and `no-practice`, and `has_source === 'true'`.
  - Lesson `L2` (Review Focus 1): no guide row and no document row. Expect zero counts, `has_source === 'false'`, and flags to include `thin`.
  - Lesson `L3` (Review Focus 2): `document` is the string `not json`. Expect `flags` to contain `bad-document` and `words` to equal the guide's count only.
  - Lesson `L4` (Review Focus 3): title `Cache, "Aside" · ₹50\nLPA`. Expect `toCsv` output to parse back (write a minimal CSV parser in the test) to the identical title.
  - Empty database (no lessons): `buildAudit` returns `rows: []` and `renderSummary` still renders every required heading.
  - Determinism: two consecutive `toCsv(buildAudit(...).rows)` calls return identical strings.
- [ ] **Step 2: Run to verify failure.** Run: `node --test test/audit.test.js`. Expected: FAIL on missing module `build`.
- [ ] **Step 3: Implement** `build.js` per the interfaces; query lessons joined to tracks and blocks ordered `tracks.position, course_blocks.position, lessons.position`; wrap each document `JSON.parse` in try/catch.
- [ ] **Step 4: Implement the CLI** in `tools/content/audit.js` and add `"audit": "node tools/content/audit.js"` to `package.json` scripts.
- [ ] **Step 5: Run to verify pass.** Run: `node --test test/audit.test.js` then `npm test`. Expected: both PASS (existing 30 tests plus the new ones).
- [ ] **Step 6: Commit.**
```bash
git add tools/content/audit/build.js tools/content/audit.js test/audit.test.js package.json
git commit -m "tools: curriculum audit CLI, CSV and summary"
```

---

### Task 5: Run on real data and prepare the owner gate

**Files:**
- Create: `docs/curriculum/audit/audit.csv`, `docs/curriculum/audit/audit-summary.md` (generated)
- Modify: none

**Interfaces:**
- Consumes: the CLI from Task 4 and a freshly imported local database.

- [ ] **Step 1: Import the real lessons into a scratch directory.** Copy `data/curriculum.json`, `data/videos.json`, `data/resources.json` and `data/new_lessons/` to a temp dir, then run `node tools/content/import.js --data <tmp> --reset --projects "C:\YASH\CODES\YASHVARDHAN_FAANG\AI-System_design_DSA\PROJECTS"`. Expected: JSON report with `lessons: 106`, `documents: 83`, and `missingGuides` listing `ds00` and `ai00`. (Do not point the audit at the live `data/` directory while the server runs.)
- [ ] **Step 2: Run the audit.** Run: `node tools/content/audit.js --data <tmp> --out docs/curriculum/audit`. Expected: prints `106 lessons`; both files exist; `audit.csv` has 107 lines (header plus 106 rows).
- [ ] **Step 3: Sanity-check the output.** Confirm by reading `audit-summary.md`: the four track totals are `dsa 26`, `system-design 44`, `ai-engineering 28`, `behavioral 8`; `ds00` and `ai00` appear with their real flags; every orphan or duplicate listed is a genuine finding (open the two lessons and check, do not trust the script blindly). If a rule produces obvious false positives, fix the rule and its test in the owning task before continuing.
- [ ] **Step 4: Commit.**
```bash
git add docs/curriculum/audit
git commit -m "docs: curriculum audit results (Phase 0)"
```
- [ ] **Step 5: Owner gate.** Stop here. Share `audit-summary.md` and ask the owner to decide, before any further plan is written: (a) is the source split acceptable, i.e. which lessons have no original body; (b) the intended size of each course after the redesign (spec Q4); (c) Three.js or Babylon.js for the 3D scenes (spec Q1). Do not start Phase 1 until all three are answered.

---

## Follow-on plans (write each after its gate; not part of this plan)

1. **Benchmark plans, one per course (Phase 1).** Research-heavy and web-dependent: AI Engineering first, then DSA, System Design, Behavioral. Output is `docs/curriculum/<course>-benchmark.md` with a coverage matrix and add/merge/split/retire decisions. Gate: owner approves the four outlines.
2. **Pathways and schema (Phase 2).** Optional lesson fields (`prereqs`, `objectives`, `level`, `pathways`, `reviewedAt`, `sources`), a pathways table, the id migration map, a prerequisite-DAG validator and planner UI changes. Gate: owner approves pathways.
3. **Motion Kit and gradient-descent pilot (Phase 4).** A `scene` block type, primitive library, one flagship scene, and the `npm run lesson:video` renderer. Gate: owner approves the look. Decide first whether `scene` replaces or complements the recorded-frames widgets (`FrameWidget`) so the two systems are not built twice.
4. **Per-course lesson rewrites (Phase 3), one plan and one PR per course**, in the order AI Engineering, DSA, System Design, Behavioral.
5. **QA hardening (Phase 5).** Content lint, code-cell harness, visual regression, accessibility and bundle-size budgets.

## Self-Review Notes

- **Spec coverage:** Phase 0 requirements (per-lesson record fields, orphan videos, duplicate topics, broken cross-references, the 22 vs 84 source split, computed quality flags, summary for the owner gate) map to Tasks 1 to 5. Two spec fields are intentionally not computed: "last-modified" (the schema stores `updated_at` only on guides and documents, which the importer overwrites on every import, so it carries no signal) and "#videos" beyond linked count; both are listed here so the omission is a decision, not an accident.
- **Type consistency:** `guideStats`/`documentStats` shapes feed `flagLesson`; `AuditRow` column order is fixed in Task 4 and reused by `toCsv`.
- **Proportion:** the plan is shorter than the spec section it implements plus its follow-on list; code appears only as test values and signatures.
