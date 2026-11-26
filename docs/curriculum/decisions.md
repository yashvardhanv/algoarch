# Owner decisions (curriculum overhaul)

Recorded 2026-11-26 from the owner's answers. These bind the Phase 1 benchmarks and later plans.

| # | Question | Decision |
|---|---|---|
| 1 | Foundations arc for AI Engineering (backprop, gradient descent, attention and the transformer, pretraining) | **Core lessons** at the start of the course, before RAG |
| 2 | Size of the whole curriculum after the redesign (106 today) | ~~110 to 140 lessons~~ **Raised to about 155 lessons (2026-11-26)** so detailed real-life System Design case studies are never cut for count; see `outline.md` |
| 3 | Animated scenes versus the recorded interactive widgets | **Scenes only for flagship lessons** (e.g. gradient descent); the recorded widgets stay for existing panels |
| 4 | Compensation figures in lessons | **Remove specific figures** (rupee amounts, LPA, lakh, crore); keep qualitative guidance |

Defaults used for questions not asked (change any by saying so):

- 3D library: Three.js, only where 3D adds value.
- Multimodality: deferred, decide after the practitioner sources.
- Video: captions only, no voice-over; narration scripts written but not recorded.
- Finishing the recorded-widget capture (about 27 of 83 pages done): paused.

## Compensation-figure cleanup (decision 4)

Done in the repo: `be07` and `be08` lesson text and the curriculum titles and descriptions that carried figures. Check with `npm run lint:comp` (lists any imported lesson that still contains a figure).
Remaining: the original source for `be05` (recruiter and offers) lives outside the repo and still has about 17 figures (9 in its guide, 8 in its page). It needs editing in place.
Marketing copy (home-page hero, README) still says "₹50 LPA"; that is the product's name and promise, not lesson content, so it was left alone.

## Benchmark gate answers (owner, 2026-11-26)

| Course | Question | Decision |
|---|---|---|
| AI Engineering | Multimodality in scope? | **Ignore for now** (stays deferred) |
| DSA | Sorting and matrix/grid as separate lessons? Advanced lessons optional? | **Yes, separate lessons**; the advanced lessons stay separate from the core path (read as: marked advanced, outside the crash pathway) |
| System Design | Reliability engineering in scope? Skip low-frequency case studies? | **In scope.** Do not skip case studies: include as many real-life case studies, in detail, as we can |
| Behavioral | Career growth in scope? 8 stories or 3 to 5? | **Delegated to the assistant** (rulings below) |

Rulings on the delegated question (change either by saying so):

- Career growth is in scope as a single lesson inside the Staff-scope arc (promotion packets, sponsors, visibility); no separate career track.
- Keep the 8-story inventory in be02 and mark 3 to 5 as the core set, as the Tech Interview Handbook recommends.

Consequences to resolve before the outline is final:

- Decision 2 caps the curriculum at 110 to 140 lessons. "As many case studies as we can" pushes System Design well past the benchmark's 47 to 50, so the cap or the case-study count needs a decision once the real list is drawn up.
- The "advanced, outside crash" reading of the DSA answer is an interpretation; confirm it when the DSA outline is written.

## Cap raised (owner, 2026-11-26)

Decision 2 is amended: the curriculum may grow to about 155 lessons (the outline is 156 with its conditional lessons). Pathways keep Crash near 60 lessons regardless of library size. Still open, defaults apply until changed: advanced = optional and outside Crash and Standard; all three case-study tiers kept; AI foundations in Standard and Deep, and in Crash only if rated 5 stars.
