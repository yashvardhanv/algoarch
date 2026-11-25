# Owner decisions (curriculum overhaul)

Recorded 2026-11-26 from the owner's answers. These bind the Phase 1 benchmarks and later plans.

| # | Question | Decision |
|---|---|---|
| 1 | Foundations arc for AI Engineering (backprop, gradient descent, attention and the transformer, pretraining) | **Core lessons** at the start of the course, before RAG |
| 2 | Size of the whole curriculum after the redesign (106 today) | **110 to 140 lessons**; additions come mostly with merges and deepening |
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
