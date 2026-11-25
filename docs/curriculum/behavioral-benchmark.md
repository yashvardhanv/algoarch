# Behavioral, leadership and compensation: benchmark (DRAFT 1)

Status: first pass, 2026-11-26. Phase 1 of `docs/plans/curriculum-overhaul-plan.md`; binding owner decisions are in `docs/curriculum/decisions.md` (including: no specific compensation figures in lessons).
Not yet owner-reviewed. Every "Ours" cell is judged from **lesson titles, descriptions and audit flags only**, not from the lesson bodies.

## Sources read (access date 2026-11-26)

| Code | Source | What was read | Limit |
|---|---|---|---|
| TIH | Tech Interview Handbook, behavioral interview page and questions page (updated Aug 7, 2026) | what the round assesses; seven preparation steps; STAR with an added Reflection step; organizing 3 to 5 key stories; the "Big Three" questions (tell me about yourself, most impactful project, a conflict you resolved); company values; a 29-question list plus company lists from Glassdoor | the pages for questions to ask, evaluation rubrics and compensation exist but were **not read** |
| AMZ | Amazon Leadership Principles (via the redirect on atoz.amazon) | 16 principle names, ending with "Success and Scale Bring Broad Responsibility" | names only |
| STF | staffeng.com guides index (Will Larson) | the index titles and section headings: Overview (archetypes, what Staff engineers do), Operating at Staff (work on what matters, writing engineering strategy, managing technical quality, staying aligned with authority, creating space for others, networking, presenting to executives), Getting the title (promotion packets, sponsors, visibility), Switching companies (interviewing for Staff-plus roles, negotiating), Resources (ladders, managing Staff-plus engineers) | guide bodies not read; the site says the guide set is still being filled in |

**Not read yet:** levels and compensation sources (needed before any compensation guidance is dated and sourced), Google, Meta, Microsoft, Netflix and Uber published values and rubrics, *The Staff Engineer's Path*, *Crucial Conversations*, *Never Split the Difference*, India-specific CTC and ESOP tax guidance, and the TIH pages for rubrics, final questions and compensation.

## Coverage matrix

`D` = dedicated section or guide, `P` = part of one, `-` = not named, `?` = judged from title or description only.

| Topic | TIH | AMZ | STF | Ours (lesson ids) |
|---|---|---|---|---|
| What the round assesses, scoring signals | D | - | - | `D` be01 |
| Story framework (STAR, plus a Reflection step) | D | - | - | `D` be01 (STAR-L, "L" = learning) |
| Building a story bank | D (3 to 5 stories) | - | - | `D` be02 (8 stories) |
| "Tell me about yourself", most impactful project, a conflict | D (the Big Three) | - | - | `P` be03 ? (failure, leaving, manager-to-IC); the Big Three are not named |
| Hard questions (failure, why leaving) | P (question list) | - | - | `D` be03 |
| Company values and culture fit | D | D (16 principles) | - | `D` be04 (Amazon, Google, Meta) |
| Mock interviews and self-scoring | P | - | - | `D` be06 |
| Questions to ask the interviewer | page exists, unread | - | - | `-` |
| Evaluation rubrics | page exists, unread | - | - | `P` be01, be06 (7-axis rubric) |
| Compensation and negotiation | page exists, unread | - | D (negotiating your offer) | `D` be05, be08 |
| What Staff engineers do; archetypes | - | - | D | `-` |
| Writing engineering strategy and design documents | - | - | D | `P` be07 (RFCs) |
| Managing technical quality | - | - | D | `P` be07 ? |
| Influence without authority; staying aligned with authority | - | - | D | `P` be07 |
| Mentoring and creating space for others | - | - | D | `P` be07 ? |
| Presenting to executives | - | - | D | `-` |
| Promotion packets, sponsors, visibility | - | - | D | `-` |
| Staff-plus interview processes | - | - | D | `-` |
| Level expectations, L4 versus L5 | - | - | D (career ladders) | `D` be07 (thin) |

Reading the matrix: the interview-skills half of our course (be01 to be06) matches the Tech Interview Handbook closely, and be04's "16 Leadership Principles" agrees with the current Amazon list. Differences worth a decision: TIH recommends **3 to 5 high-impact stories** while be02 builds 8; and the "Big Three" opening questions are not named in any lesson title. The Staff-level half is the real gap: staffeng.com has about 25 guides on operating at Staff, and our course has one thin lesson (be07) plus a compensation lesson.

## Hypotheses for the outline (to confirm, not decided)

| # | Proposed change | Action | Why | What gives |
|---|---|---|---|---|
| 1 | Staff scope: what Staff engineers do and the archetypes | add 1 lesson | STF overview; the plan's own hypothesis list asks for Staff-scope material | none |
| 2 | Writing engineering strategy and design documents | add 1 lesson (or deepen be07) | STF guide; RFC work is the Staff-level behavioral signal be07 only names | none |
| 3 | Operating at Staff: technical quality, aligning with authority, presenting to executives | add 1 lesson | STF section of 10 guides; maps to "influence without authority" | none |
| 4 | The Big Three opening questions | check be02 and be03 first; add 1 lesson if absent | TIH treats them as the core of the round | none if covered |
| 5 | Questions to ask the interviewer and closing | fold into be06 after reading the TIH page | page exists in the nav but was not read | none |
| 6 | Story-bank size | owner decision: keep 8 as an inventory but mark 3 to 5 as the core set | TIH says 3 to 5; be02 says 8 | none |
| 7 | Company loops beyond Amazon, Google, Meta | add only after reading Microsoft, Netflix, Uber, Stripe sources | no source read for these, so nothing is justified yet | none |
| 8 | Promotion packets, sponsors, visibility | optional; ask the owner | career growth rather than interview content | none |
| 9 | be05 and be08 (compensation) | rewrite around structure; add dated sources; no figures | owner decision 4; be08 already rewritten, be05's original still has about 17 figures | none |
| 10 | be07 and be08 | deepen | both flagged thin, with no practice | none |

Net effect if rows 1 to 3 and 4 or 5 are accepted: Behavioral grows from 8 to about 11 to 12 lessons.

## Open questions

1. Is career growth (promotion packets, sponsors, visibility) in scope, or only interview content?
2. Keep 8 core stories in be02, or move to the 3 to 5 that TIH recommends?

## Next steps

1. Read the unread TIH pages (rubrics, questions to ask, compensation) and the company sources for Microsoft, Netflix, Uber and Stripe.
2. Re-judge each "Ours" cell against the lesson body.
3. Pull the four benchmarks into one outline for the owner gate (see `benchmark-summary.md`).
