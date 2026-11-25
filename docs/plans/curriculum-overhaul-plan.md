# AlgoArch curriculum overhaul: execution plan

**Audience:** a Claude session with full access (web, the complete lesson sources, the repo).
**Written by:** a session that had *no* web access and only 22 of 106 lesson bodies, so every
"verify" step below is mandatory, not optional. Treat the candidate topics as hypotheses.

---

## 0. The ask, in one paragraph

1. Benchmark each of the 4 courses against the best public curricula; add what is essential and
   missing; fix ordering; redefine the **courses and pathways**.
2. Then go course by course, lesson by lesson: verify the content, deepen thin lessons, and make
   every topic *intuitive and visual* with animated, interactive explainers in the spirit of
   https://studiotvai.com/gradient-descent (a ball descending a loss surface, a learning-rate
   slider that visibly oscillates or diverges, optimizer variants side by side, a live loss curve).
3. Build the visuals on one reusable system so that **any lesson can also be rendered as a YouTube
   video later with little effort** (the repo already has Hyperframes video tooling).

### Open questions to confirm with the owner (do not guess silently)
| # | Question | Default if unanswered |
|---|---|---|
| Q1 | The owner wrote **"backlit js"**. Almost certainly **Three.js** (3D) is meant; could be Babylon.js. | Use Three.js, only where 3D adds value (loss surfaces, embeddings). |
| Q2 | Where are the original lesson files? `tools/content/import.js` defaults `--projects` to `C:\YASH\CODES\YASHVARDHAN_FAANG\AI-System_design_DSA\PROJECTS`. Only 22 bodies are in git (`data/new_lessons/`). | Import everything available; mark lessons with no source as **NEW (author from scratch)**. |
| Q3 | Voice-over for YouTube versions? Language? | English, captions only; narration scripts written but not recorded. |
| Q4 | Target size of each course after the redesign. | Keep total roughly 110–140 lessons (see §3.4 budget rule). |
| Q5 | Compensation figures (₹50 LPA / ₹1.2 Cr claims, CTC tables) are marketing-sensitive. | Re-verify with dated sources (e.g. levels.fyi) or soften wording. Never ship invented numbers. |

---

## 1. Repository facts the executor needs (verified)

**Stack:** Node `http` server (`server.js`), SQLite via `better-sqlite3` (`db.js`), vanilla JS shell
(`public/app.js`, `public/index.html`, `public/style.css`) plus a **React reader** built with Vite
(`web/src/**`) into `public/reader/` (git-ignored; run `npm run build`). Scripts: `npm start`,
`npm test` (`node --test test/`), `npm run build`, `npm run typecheck`, `npm run db:import`.

**Content model (SQLite, imported by `tools/content/import.js`):**
- `data/curriculum.json` → `tracks[] → blocks[] → lessons[]`, lesson fields:
  `n, id, title, stars, desc, duration, isNew, tags[], companies[], lab`.
  Track ids: `dsa` (26 lessons), `system-design` (44), `ai-engineering` (28), `behavioral` (8) = **106**.
- Tables: `tracks, course_blocks, lessons, lesson_guides` (markdown body), `lesson_documents`
  (structured JSON, **schema v1**, see `web/src/types.ts`), `lesson_labs, videos` (202 YouTube
  entries), `track_resources`, `admin_emails`.
- Lesson **Document** blocks: `paragraph, heading, list, code, table, callout, say, quote, card, qa,
  code_cell, widget`. A `code_cell` has `starter` + `tests` (each top-level statement of `tests` is
  one test) and runs real Python in-browser via Pyodide (Pro plan; Free is read-only).
  A `widget` has `kind, ported, data, archetype, inputs`.
- Lesson **ids are referenced by user progress** (`progress.json`, `users.json`, bookmarks, notes,
  video `lessonLink`). **Never reuse or silently rename an id.**
- Reader: `web/src/Reader.tsx`, `blocks.tsx`, `CodeCell.tsx`, `FrameWidget.tsx`, `Trace.tsx`,
  `Quiz.tsx`, `Checklist.tsx`, `Scorecard.tsx`. Styling uses design tokens in `public/style.css`
  (OKLCH, light/dark; fonts Schibsted Grotesk + JetBrains Mono; accent is a warm orange).
- **Existing widget system:** `docs/SIMULATIONS.md` and `tools/content/*` (capture-driver,
  frames, report-widgets). 293 widgets across 69 lessons, 61 ported (groups: parameter-model 131,
  simulation 66, static-reference 61, trace 16, checklist 12, measured-data 6, quiz 1). **Reuse and
  migrate; do not build a parallel system without reading these.**
- Only **22 lesson bodies** live in git (`data/new_lessons/*.md`: ds19–25, sy37–44, ai23–27,
  be07–08). Everything else must come from the owner's originals (Q2).

**Running the app locally (what the video work used):**
```bash
npm ci && npm run build
D=$(mktemp -d); cp data/{curriculum,videos,resources}.json $D; cp -r data/new_lessons $D
node tools/content/import.js --data $D --reset          # add --projects <dir> when you have originals
ALGOARCH_DATA_DIR=$D PORT=5050 AUTH_SECRET=dev node server.js
# local sign-in: POST /api/auth/dev-login {"email":"you@example.com"} (loopback only; no OAuth creds set)
# Pro features (code runner): set "plan":"pro" for the user in $D/users.json
# AI mentor needs GEMINI_API_KEY (or GEMINI_BASE_URL pointing to a stub); see video/promo/capture/mock-gemini.js
```
Always use a **scratch data dir**; never commit `data/*.db`, `users.json`, or `.auth_secret`.
CDN note: Monaco (cdnjs) and Pyodide (jsDelivr) are loaded from CDNs; in restricted networks
serve them locally as `video/promo/capture/routes.js` does.

**Video tooling already in the repo (`video/`):** Hyperframes projects (`intro/`, `promo/`),
HTML+GSAP compositions rendered to MP4 (Node ≥ 22, ffmpeg). `promo/capture/` records the real UI;
`promo/tools/score.py` synthesizes music. Hyperframes rules: timelines are **paused, seekable
GSAP**; **no `Math.random()`, `Date.now()`, or network fetches** at render time; vendor GSAP/fonts.
Catalog: `npx hyperframes catalog`, install with `npx hyperframes add <name>`
(useful: `code-highlight`, `code-morph`, `code-typing`, `flowchart`, `data-chart`, `bar-chart-race`,
`exploded-stack`, `hw-pipeline`, transitions).

---

## 2. Phase 0: audit the current state (read-only, produce data first)

Deliverable: `docs/curriculum/audit/audit.csv` + `audit-summary.md`, generated by a script
`tools/content/audit.js` (commit the script).

Per lesson record: id, track, block, title, stars, declared duration, **word count** (guide +
document text), #headings, #code blocks, #code_cells (+ whether tests exist and pass), #widgets
(ported / not), #quiz/checklist, #drills, #videos linked, last-modified, **has_source** (true/false).
Plus: orphan videos (`lessonLink` to missing id), duplicate topics across lessons, broken
cross-references, and the 22 vs 84 source split.

Quality flags (compute, don't eyeball): `thin` (< 600 words and no cell/widget), `no-visual`,
`no-practice`, `no-pitfalls`, `outdated-claim?` (manual), `inconsistent-notation`.

**Gate:** owner reviews the summary (counts per flag per course) before Phase 1 starts.

---

## 3. Phase 1: benchmark research, one course at a time

### 3.1 Method (identical for each course)
1. Collect **8–15 reference sources** (list below; add better ones you find). For each, fetch the
   *current* table of contents/syllabus and record URL + access date. Paraphrase; never copy text.
2. Build a **coverage matrix**: rows = atomic topics (normalize synonyms), columns = sources + ours.
   Cell values: `deep / covered / mention / absent`.
3. For each topic compute: how many reputable sources cover it, interview weight (FAANG L4–L6
   bar), prerequisite depth, and our current coverage. Classify the gap:
   **missing, shallow, misordered, redundant, outdated**.
4. Decide per topic: **add** (new lesson) / **merge into** an existing lesson / **split** / **move** /
   **retire** (keep the id, hide from paths, never delete progress data).
5. Write `docs/curriculum/<course>-benchmark.md`: matrix (CSV alongside), decisions with a
   one-line rationale each, and the proposed new outline.

### 3.2 Reference source candidates (verify each still exists and what it covers)
- **DSA:** NeetCode roadmap/150, Blind 75, Grind 75, Tech Interview Handbook, LeetCode Explore cards,
  *Cracking the Coding Interview*, *Elements of Programming Interviews*, CLRS, Skiena's *Algorithm
  Design Manual*, Sedgewick/Wayne, MIT 6.006 / 6.046, Stanford CS161, CP-Algorithms, USACO Guide,
  AlgoMonster patterns.
- **System design:** *Designing Data-Intensive Applications* (Kleppmann), Alex Xu vols 1–2 /
  ByteByteGo, System Design Primer (donnemartin), Hello Interview, MIT 6.5840 (6.824), Google SRE
  book + Workbook, AWS Well-Architected, Jepsen analyses, Martin Fowler, key papers (Dynamo, Bigtable,
  Spanner, Raft, Paxos Made Simple, Kafka, MapReduce, Chubby, Borg).
- **AI engineering / ML:** Karpathy *Zero to Hero* + nanoGPT, 3Blue1Brown neural networks &
  transformers, Stanford CS229 / CS224N / CS231n / CS336, fast.ai, Hugging Face courses, Chip Huyen
  (*AI Engineering*, *Designing ML Systems*), Sebastian Raschka (*LLMs from scratch*), Lilian Weng,
  Eugene Yan, Full Stack Deep Learning, DeepLearning.AI short courses, Anthropic/OpenAI cookbooks
  and prompting/agent guides, MLOps Zoomcamp, papers (Attention Is All You Need, PagedAttention,
  FlashAttention, LoRA, RAG, ReAct, DPO).
- **Behavioral / leadership / compensation:** Amazon Leadership Principles, Google/Meta/Microsoft
  published rubrics, Tech Interview Handbook behavioral section, Levels.fyi (levels + comp),
  *Staff Engineer* (Will Larson), *The Staff Engineer's Path* (Tanya Reilly), *Never Split the
  Difference*, *Crucial Conversations*, Holloway/other negotiation guides, India-specific CTC/ESOP
  tax and notice-period guidance (verify with a current, reputable source).

### 3.3 Hypotheses: likely gaps (from our 106 titles; confirm or reject with the matrix)

**AI Engineering (largest gap; today it is strong on RAG/agents/serving, weak on fundamentals):**
- ML/DL foundations: loss functions, **gradient descent & optimizers (SGD, momentum, Adam)**,
  backprop, regularization, overfitting/bias-variance, evaluation metrics, cross-validation.
- **Neural nets → transformers:** embeddings (deeper than ai02), self-attention, multi-head,
  positional encodings, the full transformer block, tokenization (BPE), decoding (greedy/top-k/
  top-p/temperature), context length limits.
- LLM lifecycle: pretraining data & scaling laws, SFT, **LoRA/QLoRA**, RLHF/DPO (exists in ai26),
  distillation, quantization, KV cache, FlashAttention, speculative decoding, batching.
- Retrieval internals: vector indexes (HNSW/IVF/PQ), ANN trade-offs, reranker training.
- Evaluation: LLM-as-judge pitfalls, offline vs online, A/B testing, dataset construction.
- Classical ML system design: feature stores, training/serving skew, ranking funnels beyond
  two-tower (ai27), drift monitoring, retraining pipelines, model registry, cost/latency budgets.
- Agents: memory, planning, tool-calling reliability, agent evals; multimodal basics.
- Probability/statistics primer needed for the above.

**DSA:** recursion fundamentals; sorting (merge/quick/quickselect, stability); stacks/queues basics;
BST/balanced trees concepts; **design-a-data-structure** (LRU/LFU, min-stack, iterators);
grid/matrix problems; DP extensions (knapsack family, LIS, tree DP, digit DP, interval DP);
binary lifting/LCA; sqrt/offline queries; randomized algorithms; amortized analysis depth;
concurrency basics for LLD; a **pattern-recognition index** tying problems to techniques.

**System design:** foundational lessons currently implied but not standalone: **caching patterns &
CDN, load-balancing algorithms, consistent hashing, choosing a database**; event-driven
architecture (CQRS, event sourcing); batch vs stream processing (Spark/Flink, lambda/kappa);
**time & ordering in distributed systems** (Lamport/vector clocks, hybrid logical clocks), gossip,
leader election, distributed locks; SLO/SLI/error budgets, chaos engineering; multi-tenancy; security
(OAuth/OIDC/JWT, encryption at rest/in transit, secrets); API pagination/webhooks/versioning;
microservices vs monolith & service mesh; cost engineering; **LLD**: SOLID, GoF patterns, concurrency
primitives, more OOD case studies (elevator, rate limiter classes, chess, library).

**Behavioral (8 lessons is thin for "Staff-level"):** story-bank craft (STAR/SOAR), conflict,
failure/learning, ambiguity, influence without authority, mentoring, tech-decision narratives,
project deep-dives, "tell me about yourself", questions to ask, **Staff-scope** material (strategy,
org influence, incident leadership, design docs/RFCs, cross-team delivery), company-specific values
beyond Amazon/Google (Meta, Microsoft, Uber, Netflix, Stripe), negotiation (competing offers,
ESOPs/RSUs, vesting, taxation in India, notice-period buyouts, counter-offers), referrals/resume,
interview schedule and stress management, how hiring committees calibrate.

### 3.4 Budget rule
Adding without removing bloats the course. Keep each course navigable: prefer **merge/split** over
net-new when a topic fits; every addition needs an owner-visible rationale and a "what did we cut or
shorten to make room" line.

---

## 4. Phase 2: redefine courses and pathways

### 4.1 Course redesign (per course)
- New `curriculum.json` with **stable ids** (keep existing; new ids continue each track's sequence
  or use a documented new scheme), updated blocks, ordering, durations, tags, companies, stars.
- Mark additions `isNew: true`; keep `data/migrations/<date>-curriculum-map.json` mapping
  old→new (id, title, block, action) so progress/bookmarks/video links survive.
- Every course gets: **learning objectives**, **prerequisites**, **target level**, **estimated hours**.

### 4.2 Pathways (new concept; today there are only 4 flat tracks + a weeks/focus study planner)
Define pathways as ordered lists of lesson ids with rationale:
- **By horizon:** Crash (2–4 weeks), Standard (8 weeks), Deep (12–16 weeks).
- **By level:** Mid (L4) → Senior (L5) → Staff (L6) emphasis.
- **By goal:** DSA-heavy loop, System-design-heavy loop, AI-engineer loop, Behavioral/negotiation only.
- **By company flavour:** use the existing `companies[]` tags; do not invent company facts.
- **Prerequisite graph** (DAG, validate acyclic with a script) so the planner and "next lesson"
  respect order. Cross-course dependencies are allowed (e.g. AI → probability primer).
Schema changes (backward compatible, optional fields, bump `schema_version`, write a migration):
`lesson.prereqs[]`, `lesson.objectives[]`, `lesson.level`, `lesson.pathways[]`, `lesson.sceneIds[]`,
`lesson.reviewedAt`, `lesson.sources[]`. New table/JSON for pathways. Update the study planner
(`public/app.js`, planner code) and overview UI to show pathways. Add tests.

**Gate:** owner approves the four new outlines + pathways before Phase 3 starts.

---

## 5. Phase 3: per-lesson review and rewrite (course by course)

Order: **AI Engineering → DSA → System Design → Behavioral** (AI first because it is the most
visual and the biggest gap; reuse what the kit teaches before scaling). One PR per course.

### 5.1 Per-lesson protocol (apply to every lesson, record in a changelog row)
1. **Verify facts:** every claim, number, complexity, API name, version, paper result. Fix or cite.
   Date-stamp anything perishable (model names, pricing, limits, comp bands).
2. **Verify code:** every snippet and `code_cell` runs; tests pass in Pyodide *and* CPython;
   no hidden state; deterministic; add edge-case tests. Non-Python snippets: lint/compile-check.
3. **Depth check** against the matrix: add missing sub-topics; remove padding; keep one idea per
   section. Thin lesson rule: if < 600 words and no cell/widget, it fails.
4. **Intuition first structure** (use as the default section order):
   *Hook/why it matters → Mental model (picture first) → Formalization → Worked example (animated)
   → Code (runnable) → Failure modes & pitfalls → Interview framing (what a strong answer sounds
   like) → Drills/quiz → Further reading (3–5 vetted links).*
5. **Visuals:** every lesson gets ≥ 1 animated explainer; heavy topics get a 3–6 step "scrollytelling"
   sequence. Choose the visual from the primitive library (§6.3); don't decorate, *explain*.
6. **Practice:** ≥ 1 runnable cell or interactive widget, a short quiz (3–5 items with explanations),
   and 2–3 drills (link existing `drills`).
7. **Cross-links:** prerequisites, related lessons, and the pathways it belongs to.
8. **Accessibility & tone:** plain language, define jargon on first use, consistent notation,
   alt text/captions for every animation, `prefers-reduced-motion` fallback.
9. **Changelog row:** id, what changed, sources consulted, verification done, remaining doubts.

### 5.2 Lessons without a source body (the ~84)
If the owner supplies originals: review as above. If not: **author new** following §5.1 and mark
`isNew` + `reviewedAt`. Never present an authored lesson as a "verified original".

### 5.3 Course-specific notes
- **AI Engineering:** add the foundations arc first (gradient descent → backprop → transformer),
  because later lessons (RAG, serving, alignment) assume it. Flagship visual = gradient descent.
- **DSA:** each pattern lesson gets a **step-through trace visual** (array/pointers/stack/heap
  states) driven by the *same code* the cell runs. Add a recognition-index lesson.
- **System design:** each case study gets an **animated architecture + request-flow diagram** and a
  capacity-estimation calculator widget; foundation lessons get failure-injection visuals
  (partition, node loss, replication lag) where the learner toggles the fault.
- **Behavioral:** interactive **story builder** (STAR/SOAR scaffolding), scoring rubric visuals,
  negotiation calculator (verify all comp math and tax assumptions with sources).

---

## 6. Phase 4: the Lesson Motion Kit (build this before mass-producing visuals)

### 6.1 Principle
**One scene spec, two renderers.** Author a scene once as data; render it (a) interactively in the
reader and (b) as a deterministic Hyperframes composition for YouTube.

```
scene spec (TS/JSON)  ──►  <LessonScene/> React renderer   (anime.js; play/pause/scrub/params)
        │
        └──────────────►  sceneToGsap() adapter → Hyperframes comp → MP4 (paused, seekable GSAP)
```
Package location suggestion: `web/src/motion/` (primitives, renderer, tokens) and
`video/lessons/<lesson-id>/` (generated Hyperframes projects). Keep scenes in
`content/scenes/<lesson-id>/*.scene.ts`.

### 6.2 Library choices (decide with a 1-day spike; justify in `docs/motion/decision.md`)
- **anime.js (v4)**: in-app timelines, SVG path/morph, scroll/draggable. Lightweight; lazy-load.
- **Theatre.js** (`@theatre/core` + Studio): visual keyframe authoring for flagship sequences and
  for video-grade polish; export static state JSON so renders stay deterministic and offline.
- **Three.js** (Q1): only for true 3D (loss surfaces, embedding clouds, attention cubes).
- **GSAP**: already required by Hyperframes; the adapter targets it for video. Verify the license
  terms for your use before depending on it in the app bundle.
- **D3** utilities (scales, geometry, contours) for data-driven drawing. No heavy chart suites.
Constraint: **no randomness at render time** (seeded PRNG only); **no network** at render time.

### 6.3 Primitive library (build once, reuse everywhere)
`Plot2D` (axes, curves, points), `ContourMap` / `Surface3D` (loss landscape), `ParamSlider` /
`Toggle` / `Stepper`, `Matrix/Tensor grid` (with highlight & flow), `ArrayBoxes` + `Pointer`,
`StackQueueHeap`, `Tree`, `Graph` (nodes, edges, weights, BFS/DFS frontier), `Timeline/Sequence
diagram` (messages between nodes; fault injection), `Packets/Network`, `TokenStream`,
`AttentionHeatmap`, `EmbeddingScatter`, `TrainingCurve`, `CodeStepper` (line highlight tied to state),
`MemoryLayout`, `Callout/Caption`, `Legend`. Each exposes: props schema, a11y label, reduced-motion
variant, theme tokens (light/dark from `public/style.css`), and a Storybook-like demo page.

### 6.4 Interaction & quality requirements
Play / pause / scrub / step-by-step; reset; keyboard operable; touch friendly; 60 fps on a mid
laptop; each widget lazy-loaded (reader bundle budget: set a number now and fail CI above it);
works offline except what the lesson explicitly fetches; no layout shift; screenshots in CI.
Motion principles: ease-out entrances, 200–600 ms, one focal change at a time, color = meaning
(accent = focus, green = correct, red = failure), never animate for decoration.

### 6.5 Document schema integration
Add a block type `scene` to schema (bump `schemaVersion`; keep `widget` working):
`{type:'scene', sceneId, params, steps?, caption, alt}`. Migrate `parameter-model` / `simulation`
widgets opportunistically (prioritize those in high-traffic lessons); do not break the 61 ported ones.
Update `web/src/types.ts`, `blocks.tsx`, importer validation, and tests.

### 6.6 Flagship scene (acceptance test for the kit): **Gradient descent**
Reproduce these behaviors (original implementation, not a copy of the reference site):
1. A 2-D contour map and an optional 3-D surface of a non-trivial loss (bowl, saddle, ravine,
   local minima); a ball/point descends along the negative gradient, drawing its path.
2. **Learning-rate slider**: too small crawls, good converges, too large oscillates then diverges.
3. **Optimizer comparison** side by side: SGD vs momentum vs RMSProp vs Adam on the same start point.
4. Live **loss-vs-step curve** and a table of (step, x, y, loss, gradient).
5. Click to place a start point; presets for pathological surfaces; step/auto-play/scrub.
6. Narration steps ("Compute the slope → take a step downhill → repeat") that can be exported as
   video chapters. Deterministic given (start, lr, optimizer, steps).

### 6.7 YouTube pipeline (`video/lessons/`)
Generate from each scene spec: Hyperframes project (1080p30 default; 4K via `--resolution
landscape-4k`), chapter list, caption file (SRT/VTT), narration script (`script.md`), thumbnail
frame, and a metadata JSON (title, description, tags, chapters). A single command, e.g.
`npm run lesson:video -- <lesson-id> [--4k]`. Reuse the intro/promo design language (dark ground,
orange accent, Schibsted Grotesk/JetBrains Mono). Vendor GSAP and fonts for offline renders.
Efficiency note from the film: a 60 s 1080p30 render took ~4.5 min; plan 4K at ~4× that.

---

## 7. Phase 5: QA gates (automate; fail the PR if red)
- `npm test`, `npm run typecheck`, `npm run build`, schema validation of every document.
- **Content lint script:** thin-lesson rule, missing objectives/prereqs, broken internal links,
  dead external links (allow-list), unresolved TODOs, notation drift.
- **Code-cell harness:** run every `code_cell` + tests headlessly (Pyodide in Playwright, or CPython
  with the same harness `web/src/pyHarness.ts`); all must pass.
- **Visual regression:** Playwright screenshots of each scene at defined steps (light + dark,
  desktop + mobile), diff against baselines.
- **A11y:** axe checks on reader pages, reduced-motion path, focus order, contrast.
- **Perf:** bundle-size budget for `public/reader/reader.js` and per-scene chunks; interaction
  frame-time probe.
- **Pathway validation:** DAG acyclic, every lesson reachable, every pathway has a realistic
  total duration, no lesson id lost versus `curriculum-map.json`.
- **Security/privacy:** no secrets or user data committed; outbound links `rel=noopener`.

---

## 8. Sequencing, sizing, and git workflow

| Step | Output | Owner gate |
|---|---|---|
| 0 | Audit CSV + summary | Review counts |
| 1 | 4 benchmark docs + proposed outlines | Approve outlines |
| 2 | New curriculum + pathways + schema migration + planner UI | Approve pathways |
| 3a | Motion Kit + flagship gradient-descent scene + `npm run lesson:video` | **Approve the look** |
| 3b | AI Engineering course rewrite (PR 1) | Review |
| 3c | DSA (PR 2) → System Design (PR 3) → Behavioral (PR 4) | Review each |
| 4 | QA hardening, docs for adding a new scene/lesson/video | Done |

Rules: work on the designated branch; small, reviewable commits (conventions: `content(<course>):`,
`motion:`, `schema:`, `tools:`); one PR per course; never rewrite others' history; no force-push;
do **not** commit large binaries (rendered videos go to a git-ignored `out/` or releases); keep
progress-compatible ids; update `docs/` as you go.

## 9. Working efficiently (the owner is token-sensitive)
- Generate audits/matrices with **scripts and files**, not by pasting long tables into chat.
- Delegate per course (or per 8–10 lessons) to sub-agents with a self-contained brief
  (this document + that course's audit rows); require them to return a short changelog, not prose.
- Read each lesson once; write results to files; don't re-open unchanged files.
- Batch verification (run all code cells in one harness run); look at **contact sheets**, not
  individual screenshots.
- Prefer deterministic generators (scene → video) over hand-built per-lesson compositions.

## 10. Definition of done
**Per lesson:** facts and code verified; follows the §5.1 structure; ≥ 1 animated explainer + ≥ 1
interactive/runnable element + quiz + drills; cross-linked; accessible; changelog row written;
scene exportable to video.
**Per course:** benchmark doc, final outline, pathways, all lessons done, QA green, owner sign-off.
**Overall:** Motion Kit documented with "add a scene in 30 minutes" and "make the YouTube video in
one command" guides; progress data intact for existing users; no invented statistics anywhere.

## 11. Risks
| Risk | Mitigation |
|---|---|
| Hallucinated facts in rewritten lessons | Source every claim; verification column in the changelog; owner spot-checks |
| Scope explosion (106+ lessons × visuals) | Kit first; scene reuse; pilot gate; budget rule §3.4 |
| Lost user progress | Stable ids, migration map, validation test |
| Heavy animations hurt performance/accessibility | Lazy load, budgets, reduced-motion path, CI checks |
| License issues (copying external text/visuals, GSAP terms) | Paraphrase, cite, original art; verify licenses before shipping |
| Inconsistent look across lessons | One token set, one primitive library, design review at gate 3a |
| Stale compensation/model/pricing data | Date-stamp and re-verify; avoid absolute claims |
