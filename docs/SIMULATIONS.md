# Interactive widgets

Total: 293 across 69 lessons. Ported: 26.

| Group | Count | Share |
|---|---:|---:|
| parameter-model | 131 | 45% |
| simulation | 66 | 23% |
| static-reference | 61 | 21% |
| trace | 16 | 5% |
| checklist | 12 | 4% |
| measured-data | 6 | 2% |
| quiz | 1 | 0% |

## By track

- **ai-engineering**: parameter-model 33, static-reference 8, measured-data 6, simulation 3
- **dsa**: trace 16, simulation 7, parameter-model 5, quiz 1, checklist 1
- **system-design**: parameter-model 93, simulation 56, static-reference 53, checklist 11

## Examples

- **parameter-model**: ai01: bench · chunkerlive · drag the sliders; ai01: bench · rag tax calculatorlive; ai02: bench · tokenizer explorerreal tiktoken output; ai02: bench · head to head, same 7-doc corpusreal scores; ai02: bench · truncation curve — your roadmap indexreal recall; ai03: bench · chunkerlive · drag the sliders
- **simulation**: ai01: bench · cosine vs dot vs euclideanlive · drag the arrow heads; ai12: bench · step through the handshakereal capture; ai16: bench · cost stackmeasured inputs; ds11: Rotting Oranges · multi-source BFSlive · step it; ds12: the same unions, two implementationslive · step it; ds13: choose · explore · un-chooselive · step it
- **static-reference**: ai02: bench · cosine vs word-overlapreal encoder output; ai03: bench · chunk size vs encoder truncationreal measurements; ai05: bench · judge calibration, two tiersreal, ground truth by construction; ai07: measuredreal; ai07: bench · position vs accuracyreal; ai07: measuredreal
- **trace**: ds02: two_sum([3,2,4,1,8], 9) · complement map; ds03: two_sum_sorted([1,3,4,6,8,11], 12) · one element eliminated per step; ds03: max_area([1,8,6,2,5,4,8,3,7]) · move the shorter wall; ds04: longest_unique("abcabcbb") · left never moves backwards; ds04: min_len_subarray([2,3,1,2,4,3], 7) · the while fires more than once; ds05: range sum via two prefixeslive
- **checklist**: ds18: rubric · 7 axes × 4live · saved in this browser; sy21: Rubric · click what you covered0 / 20; sy22: Rubric · click what you covered0 / 20; sy23: Rubric · click what you covered0 / 20; sy24: Rubric · click what you covered0 / 20; sy25: Rubric · click what you covered0 / 20
- **measured-data**: ai01: bench · your actual embedding spacelive · real vectors; ai01: bench · score inspector — all 40 chunkslive · real scores; ai03: bench · does the winner change with the budget?real measurements; ai06: measured · 12 generated answersreal; ai09: bench · temperature, top-k, top-plive · real distribution; ai18: bench · filter by what you're deciding17 measured defaults
- **quiz**: ds00: Timed drill

## Lessons with the most widgets

- sy02 Postgres I: Indexes & Scans: 12
- sy03 Postgres II: MVCC & Locking: 10
- sy04 Postgres III: Query Planner & Pooling: 10
- sy01 Redis Internals & Eviction: 9
- sy05 NoSQL, LSM Trees & Cassandra: 9
- sy06 Latency Numbers & Capacity Estimation: 8
- sy07 Replication & Sharding: 8
- sy08 CAP Theorem to PACELC: 8
- sy13 Docker & Container Internals: 8
- sy15 Kubernetes II: Networking & Rollouts: 8

## Status

Ported so far: the timed-drill quiz, 13 step-through traces, 11 rubric checklists and the
mock-round scorecard (26 widgets). Everything else is still a placeholder.
Three trace "companion" panels (the live stack and heap views beside two traces) are not
ported yet: their per-step state lives in script variables next to the trace data.

## Why the rest are placeholders

Each widget is a small program in the original lesson page, not content. The importer stores
the written content as data and tags every widget with the group above, so the work can be
tracked and ported group by group. Groups are inferred from the controls a panel exposes, so
they are approximate: a few panels may land in a neighbouring group.

## How each remaining group can be ported

| Group | Port approach | Effort |
|---|---|---|
| trace companions (3) | Capture the per-step state arrays and show them beside the trace. | Small |
| measured-data (6) | One chart/table component. The numbers are precomputed and embedded in the page script. | Medium |
| static-reference (61) | Needs a look at what draws each one. Most render tables or readouts from constants in the script, which can be captured as table data. | Medium |
| parameter-model (131) | A declarative model spec (inputs with min, max and default; named expressions; outputs as text, bars or a verdict) plus a small safe expression evaluator, with no eval. The formulas must be written per widget, in batches by lesson. | Large |
| simulation (66) | Step-by-step state machines. Some will fit a generic frame-sequence player; the rest need their own components. | Large |

## Suggested order

1. trace companions, then measured-data and static-reference.
2. parameter-model, built as the generic model component, then authored lesson by lesson
   starting with the lessons that have the most widgets (sy02, sy03, sy04, sy01, sy05).
3. simulation, last, one at a time.

Regenerate this file with: npm run docs:widgets
