# Phase 1 summary: benchmarks for all four courses (DRAFT 1)

Date: 2026-11-26. Detail and sources are in the four benchmark files; owner decisions are in `decisions.md`.
All numbers are hypotheses from lesson titles and audit flags, not from reading lesson bodies.

## Size after the proposed changes

| Course | Today | Proposed | Main reason |
|---|---:|---:|---|
| AI Engineering | 28 | about 33 to 34 | add a foundations arc (owner: core lessons), pretraining and scaling laws, reasoning models, possibly dataset engineering |
| DSA | 26 | about 29 to 31 | add sorting, matrix and grid problems, recursion fundamentals, balanced trees, a recognition index |
| System Design | 44 | about 47 to 50 (47 after merges) | add web crawler, file sync, reliability lessons, caching and consistent hashing, time and ordering, scaling patterns; merge three overlapping pairs |
| Behavioral | 8 | about 11 to 12 | add the Staff-scope arc (what Staff engineers do, engineering strategy, operating at Staff), possibly the Big Three |
| **Total** | **106** | **about 120 to 127** | within the owner's range of 110 to 140 |

## Findings that hold across courses

1. **Our applied core agrees with the public benchmarks.** DSA matches NeetCode's categories one for one; system design case studies cover almost every item both the Primer and Hello Interview list.
2. **The gaps are in foundations and the conceptual layer**, not in case studies: ML foundations, sorting and grids in DSA, reliability engineering and consistent hashing in system design, and Staff-level scope in behavioral.
3. **Thin lessons concentrate in the "advanced FAANG bar" blocks** (`ai23` to `ai27`, `ds19` to `ds25`, `sy37` to `sy44`, `be07` and `be08`). They need deepening before more lessons are added.
4. **Lessons with no visual are the norm** (84 of 106 in the baseline audit, about 71 once recorded widget frames are counted). The animated-scene work in the overhaul plan targets this, but per owner decision only for flagship lessons.

## Gaps in this benchmark itself

- Practitioner and book sources not yet read: Raschka, Lilian Weng, Anthropic and OpenAI agent guides (AI); Blind 75, Grind 75, CTCI, EPI, CLRS (DSA); DDIA, Alex Xu, key papers, a Kubernetes source (system design); levels and compensation sources, company values pages, *The Staff Engineer's Path* (behavioral).
- Stanford CS161 could not be read (Canvas login).
- Our coverage is judged from titles. The review that matters is Phase 3, lesson by lesson.

## What the owner is asked to approve (gate before Phase 2)

1. The proposed outline direction per course (the tables in each benchmark file).
2. The open questions at the end of each file:
   - AI: multimodality in scope?
   - DSA: sorting and matrix as separate lessons, and are the advanced lessons optional?
   - System design: is reliability engineering in scope, and skip low-frequency case studies?
   - Behavioral: is career growth in scope, and 8 stories or 3 to 5?
3. Then Phase 2 (pathways and schema) starts.
