# Pathways and Planner UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the seven pathways (served by `GET /api/pathways`) to signed-in learners, with progress per pathway and a week-by-week plan that replaces the old star-sorted planner modal.

**Architecture:** Two small pure modules (`planner-core.js` for scheduling and progress, `pathways-view.js` for HTML strings) load in the browser and in Node, so `node --test` covers them. A thin `pathways.js` wires them to the DOM, the existing `state` and the existing `openLesson` / `toggleCompleteLesson`. The planner modal and its generator are deleted; its three entry points open the new Pathways view.

**Tech Stack:** Vanilla JS (no bundler, no new dependency), `node:test`, the design tokens in `public/style.css`.

**Spec:** `docs/superpowers/plans/2026-11-26-pathways-schema.md` (what `/api/pathways` returns) and `docs/curriculum/decisions.md` (decision 4: no compensation figures). The overhaul plan lives on branch `claude/epic-davinci-ugc6xq`.

## Global Constraints

- No new npm dependency, no build step for these files. Browser files are plain scripts in `public/`, loaded from `public/index.html`.
- Pure modules use a UMD guard: `if (typeof module !== 'undefined' && module.exports) module.exports = api; else window.PlannerCore = api;` (and `window.PathwaysView`).
- No inline `style=` attributes and no inline `onclick=` in generated HTML. Use classes in `public/pathways.css` and `data-*` attributes with one delegated listener.
- Every string from the API goes through the module's own `esc()` before it enters HTML.
- Use existing tokens (`--paper`, `--well`, `--line`, `--ink`, `--accent`, `--ok`, `--r-outer`, `--s-*`, `--dur-*`). Light and dark themes must both work. Respect `prefers-reduced-motion`. Touch targets at least 44px. No horizontal scroll at 375px width.
- No compensation figures (rupee amounts, LPA, lakh, crore) in any text this plan adds or edits (owner decision 4).
- Never run a server, importer or test against the live `data/` directory. Browser checks use a temp copy of `data/`, provider env vars deleted, as `test/curriculum.test.js` does.
- Plan gating stays client-side as today: `can('plannerFull')` false means only the `crash` pathway is usable; other pathways show a locked card that opens the pricing modal.
- Test ports for new server-spawning tests: not needed (this plan adds no server test).

## Review Focus

- All lessons in a pathway already completed: the view shows a finished state, no empty weeks, no crash.
- `completed` contains ids that are not in the pathway (stale or other course): ignored in every count.
- One lesson longer than the weekly time budget: it gets a week to itself, never dropped or split.
- Hours per week that are `0`, negative, empty, `NaN` or huge: clamped to 1 to 40, default 10.
- Lesson titles or notes containing `<script>` or quotes: escaped in every generated string.
- `/api/pathways` fails or returns no pathways: the view shows an error with a Retry button, not a blank page.
- A free-plan user clicking a locked pathway: pricing modal opens, nothing else changes.

---

### Task 1: Scheduling and progress core

**Files:**
- Create: `public/planner-core.js`
- Test: `test/planner-core.test.js`

**Interfaces:**
- Consumes: pathway objects shaped `{ id, title, description, kind, minutes, lessons: [{ id, title, trackId, duration, note? }] }`; `completed` as an array of lesson ids.
- Produces (all on `PlannerCore`):
  - `minutesOf(duration: string): number`. Reads the first `N min`; falls back to 45 when absent or 0. A test also asserts it equals `parseMinutes` from `curriculum.js` for every non-empty duration in `data/pathways.json`.
  - `clampHours(h: unknown): number`. Integer 1 to 40, default 10.
  - `pathwayProgress(pathway, completed): { done, total, percent, minutesTotal, minutesLeft, next }` where `next` is the first lesson not completed, or `null`. `percent` is a rounded integer 0 to 100; an empty pathway gives 0.
  - `buildSchedule(pathway, completed, { hoursPerWeek, weeks }): { weeks: [{ n, minutes, lessons }], remainingLessons, remainingMinutes, weeksNeeded, fits, hoursNeeded }`.
  - `isPathwayLocked(pathway, fullPlanner: boolean): boolean`. True when `!fullPlanner && pathway.id !== 'crash'`.

- [ ] **Step 1: Write the failing tests** in `test/planner-core.test.js`, all with the names below:
  - `minutesOf reads "45 min", falls back to 45`: `minutesOf('50 min') === 50`, `minutesOf('') === 45`, `minutesOf(undefined) === 45`, `minutesOf('0 min') === 45`.
  - `minutesOf agrees with parseMinutes on data/pathways.json`: for every lesson with a duration containing `min`, equal to `require('../curriculum').parseMinutes`.
  - `clampHours`: `clampHours(0)===1`, `(-5)===1`, `('')===10`, `(NaN)===10`, `(1000)===40`, `('12')===12`, `(7.6)===8`.
  - `pathwayProgress ignores completed ids outside the pathway`: pathway of a, b, c; completed `['a','zzz']` gives `done 1, total 3, percent 33, next.id 'b'`.
  - `pathwayProgress on a finished pathway`: `next === null`, `percent === 100`, `minutesLeft === 0`.
  - `pathwayProgress on an empty pathway`: `percent === 0`, `next === null`.
  - `buildSchedule packs in pathway order within the weekly budget`: lessons of 60, 60, 60 minutes at 2 h/week gives weeks `[a,b]`, `[c]`, `weeksNeeded 2`.
  - `buildSchedule skips completed lessons`.
  - `buildSchedule gives an oversize lesson its own week`: one 200-minute lesson at 1 h/week yields a week containing exactly that lesson, `minutes 200`.
  - `buildSchedule reports fit against a target`: remaining 600 minutes, `weeks: 2` gives `hoursNeeded 5`; at 10 h/week `fits true`; at 2 h/week `fits false`. With `weeks` omitted: `fits true`, `hoursNeeded null`.
  - `buildSchedule with nothing left`: `weeks []`, `weeksNeeded 0`, `fits true`.
  - `isPathwayLocked`: `crash` never locked; `deep` locked unless `fullPlanner`.
- [ ] **Step 2: Run to confirm failure**
  Run: `node --test test/planner-core.test.js`
  Expected: FAIL, cannot find module `../public/planner-core.js`.
- [ ] **Step 3: Implement the five functions in `public/planner-core.js`** with the UMD guard from Global Constraints. `buildSchedule` is greedy and sequential: close the current week when adding the next lesson would pass `hoursPerWeek * 60` and the week is not empty. `weeksNeeded` is `weeks.length`. `hoursNeeded` is `Math.ceil(remainingMinutes / 60 / weeks)` only when `weeks` is a positive number.
- [ ] **Step 4: Run to confirm pass**
  Run: `node --test test/planner-core.test.js`
  Expected: PASS, all tests above.
- [ ] **Step 5: Commit**
  `git add public/planner-core.js test/planner-core.test.js && git commit -m "feat: pure pathway scheduling and progress core"`

---

### Task 2: HTML builders and styles

**Files:**
- Create: `public/pathways-view.js`, `public/pathways.css`
- Test: `test/pathways-view.test.js`

**Interfaces:**
- Consumes: Task 1 outputs (`pathwayProgress` result, `buildSchedule` result).
- Produces (all on `PathwaysView`, each returns an HTML string):
  - `cardHtml(pathway, progress, { locked: boolean, selected: boolean }): string`. A `<button class="pw-card" data-pathway="ID">`; adds class `is-selected` and `aria-pressed="true"` when selected, class `is-locked` and a visible "Pro" label when locked; shows title, description, lesson count, whole hours, and a progress bar with `role="progressbar"` and `aria-valuenow`.
  - `scheduleHtml(schedule, { completed: string[], target: number | null }): string`. One `<section class="pw-week">` per week with heading "Week N" and its minutes as hours; each lesson is an `<li class="pw-lesson">` containing a button `data-action="open" data-lesson="ID" data-track="TRACK"` and a check button `data-action="toggle" data-lesson="ID"`. A summary line above says how many lessons are left, about how many hours, and how many weeks at the chosen pace. When `target` is set and the plan does not fit, the summary says how many hours a week would finish it in `target` weeks (use `schedule.hoursNeeded`). When `schedule.weeks` is empty it renders a single "Pathway complete" block instead.
  - `errorHtml(message: string): string`: message plus a `<button data-action="retry">Retry</button>`.
  - `esc(s: unknown): string`: escapes `& < > " '`.

- [ ] **Step 1: Write the failing tests** in `test/pathways-view.test.js`:
  - `esc escapes the five characters and tolerates null`.
  - `cardHtml escapes the title and description`: title `<img src=x onerror=1>` appears only as `&lt;img ...`.
  - `cardHtml marks selected and locked states`: selected has `is-selected` and `aria-pressed="true"`; locked has `is-locked` and the text `Pro`.
  - `cardHtml shows progress`: `aria-valuenow="33"` for a pathway 1 of 3 done.
  - `scheduleHtml renders one section per week with open and toggle buttons per lesson`: counts of `pw-week`, `data-action="open"`, `data-action="toggle"` match.
  - `scheduleHtml has no inline handlers or styles`: output matches neither `/\sonclick=/i` nor `/\sstyle=/i`.
  - `scheduleHtml says when the plan does not fit`: with `fits:false, hoursNeeded:5` and `target:2` the output contains `5 hours a week`.
  - `scheduleHtml renders a finished state when no weeks remain`: contains `Pathway complete`, no `pw-week`.
  - `errorHtml has a retry button and escapes the message`.
  - `no output contains compensation figures`: run `findCompClaims` from `tools/content/comp-lint.js` over every builder's output for a fixture; expect `[]`.
- [ ] **Step 2: Run to confirm failure**
  Run: `node --test test/pathways-view.test.js`
  Expected: FAIL, cannot find module.
- [ ] **Step 3: Implement the builders in `public/pathways-view.js`** (UMD guard). Not a Node `require` of the DOM; strings only.
- [ ] **Step 4: Write `public/pathways.css`.** Load the project's `impeccable` skill first and follow it with the tokens in Global Constraints. Classes needed: `.pw-grid`, `.pw-card` (+ `.is-selected`, `.is-locked`), `.pw-bar`, `.pw-controls`, `.pw-week`, `.pw-lesson`, `.pw-empty`, `.pw-error`. Cards in one column at 375px, two or three columns on wide screens. Hover and focus-visible states; transitions use `--dur-short` and are disabled under `prefers-reduced-motion`.
- [ ] **Step 5: Run to confirm pass**
  Run: `node --test test/pathways-view.test.js`
  Expected: PASS.
- [ ] **Step 6: Commit**
  `git add public/pathways-view.js public/pathways.css test/pathways-view.test.js && git commit -m "feat: pathway card and weekly plan HTML builders"`

---

### Task 3: Wire the Pathways view and retire the old planner

**Files:**
- Create: `public/pathways.js`
- Modify: `public/index.html` (nav item, `#view-pathways` section, script and stylesheet tags, delete `#planner-modal` block, update `app.js?v=3.5` to `?v=3.6`), `public/app.js` (delete the planner half of `setupPlannerAndRubric`, keep the rubric half; point `hero-plan` at the new view)
- Test: browser check (no automated DOM test; the logic is covered by Tasks 1 and 2)

**Interfaces:**
- Consumes: `PlannerCore`, `PathwaysView`; globals `state` (`state.progress.completed`), `switchView(name)`, `openLesson(id, trackId)`, `toggleCompleteLesson(id)`, `can('plannerFull')`, `window.openPricingModal`; `GET /api/pathways` returning `{ pathways: [...] }` (confirm the exact wrapper in `server.js` and `test/curriculum.test.js` before coding).
- Produces: a `Pathways` nav button (`data-view="pathways"`) between Overview and Curriculum; section `#view-pathways` containing the card grid, a controls row (hours per week select with 5, 10, 15, 20; optional target weeks select with "No target", 2, 4, 8, 12, 16), and the schedule area.

- [ ] **Step 1: Add markup to `public/index.html`.** The nav button, the `#view-pathways` section (heading, short description, `#pw-grid`, `#pw-controls`, `#pw-schedule`), the stylesheet link `pathways.css`, and script tags `planner-core.js`, `pathways-view.js` before `app.js`, and `pathways.js` after `home.js`. Delete the `#planner-modal` block. Do not touch the rubric modal.
- [ ] **Step 2: Implement `public/pathways.js`.**
  - On first show of the view (wrap `switchView` the way `home.js` does, or listen on the nav button), fetch `/api/pathways` once and cache it; on failure render `errorHtml`; `Retry` refetches.
  - Render cards with `pathwayProgress`; select a pathway by clicking its card (locked cards call `window.openPricingModal()` instead). Default selection: the saved one, else `crash`, else the first.
  - Controls re-render the schedule using `buildSchedule(pathway, state.progress.completed, { hoursPerWeek: clampHours(...), weeks })`. Save pathway id, hours and weeks in `localStorage` inside try/catch; the view must work with storage blocked.
  - One delegated click listener on `#view-pathways` handles `data-pathway`, `data-action="open"` (calls `openLesson`), `data-action="toggle"` (calls `toggleCompleteLesson`, then re-renders cards and schedule from the updated state), and `retry`.
  - Re-render when the view is shown again, so progress made in the reader shows up.
- [ ] **Step 3: Retire the old planner in `public/app.js`.** Remove the `generateBtn` block and the open/close handlers for `#planner-modal`; make `#btn-open-planner`, `#btn-trigger-planner` and `#hero-plan` call `switchView('pathways')`. Keep rubric code intact. Search `index.html` and `app.js` for any remaining reference to `planner-modal`, `planner-select-` or `btn-generate-schedule` and remove them.
- [ ] **Step 4: Browser verification** with the built-in browser, on a temp copy of `data/` (see Global Constraints), signed in through dev login. Confirm and record in the report:
  - The Pathways nav item shows 7 cards with sensible counts and hours; selecting each updates the plan.
  - Marking a lesson complete from the plan updates the card's bar and the weeks without a reload.
  - Changing hours per week changes the week count; setting a target the plan cannot meet shows the hours-a-week hint.
  - `hero-plan` and the account-menu "Study planner" both open the view.
  - Free-plan behavior: with `can('plannerFull')` false, non-`crash` cards show Pro and open pricing.
  - Mobile preset (375px) has no horizontal scroll; dark theme is readable; no console errors.
  - With the server stopped mid-session (or the fetch blocked), the error state and Retry work.
- [ ] **Step 5: Run the full suite**
  Run: `npm test`
  Expected: all tests pass (94 existing plus the new ones), twice in a row.
- [ ] **Step 6: Commit**
  `git add public/index.html public/app.js public/pathways.js && git commit -m "feat: pathways view replaces the star-sorted planner modal"`

---

### Task 4: Remove compensation figures from the rubric verdict

**Files:**
- Modify: `public/app.js` (the `updateRubric` verdict strings)
- Test: `test/pathways-view.test.js` (add one test) or `test/comp-lint.test.js`

**Interfaces:**
- Consumes: `findCompClaims` from `tools/content/comp-lint.js`.
- Produces: verdict strings that name the level and hiring signal only, e.g. `STRONG HIRE (L6 Staff SWE)`, `STRONG HIRE (L5 Senior SWE)`, `LEAN HIRE (L4 Mid-Level SWE)`, `NO HIRE (needs deeper invariant and constraint proofs)`.

- [ ] **Step 1: Write the failing test** `rubric verdicts carry no compensation figures` in `test/comp-lint.test.js`: read `public/app.js`, take the text from `const updateRubric` up to the next line that is exactly `  };`, and assert `findCompClaims(thatText)` is `[]`.
- [ ] **Step 2: Run to confirm failure**
  Run: `node --test test/comp-lint.test.js`
  Expected: FAIL, the three `₹..LPA` strings are found.
- [ ] **Step 3: Edit the four verdict strings** as listed under Produces.
- [ ] **Step 4: Run the full suite**
  Run: `npm test`
  Expected: all pass.
- [ ] **Step 5: Commit**
  `git add public/app.js test/comp-lint.test.js && git commit -m "fix: rubric verdict no longer states salary figures"`

---

## Notes for the executor and owner

- **Rulings already made in this plan:** the planner modal is replaced, not kept beside the new view (two planners would disagree); a duration that cannot be read counts as 45 minutes; free-plan gating stays client-side and limited to the `crash` pathway; the calculator view and the home-page "₹50 LPA" copy are left alone (product name, not lesson content).
- **Left out on purpose:** prerequisites in the schedule (no lesson has any authored yet), level-based and company pathways, dates and calendar export, server-side gating, and any change to `/api/pathways`.
- **Known size caveat:** the Crash pathway is 60 lessons (about 52 hours), so a "2 to 4 weeks" target needs 13 to 26 hours a week. The plan surfaces that honestly through `hoursNeeded`; resizing the pathways is the owner's call at the Phase 2 gate.
