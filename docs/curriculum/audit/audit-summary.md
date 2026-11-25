# Curriculum audit

## Totals

- Lessons: 106
- Total words: 420733

| Course | Lessons | Words |
| --- | ---: | ---: |
| Data Structures & Algorithms | 26 | 79638 |
| System Design (HLD & LLD) | 44 | 239379 |
| AI Engineering & LLM Systems | 28 | 83144 |
| Behavioral, Leadership & Compensation | 8 | 18572 |

## Flags by course

| Flag | dsa | system-design | ai-engineering | behavioral | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| no-pitfalls | 7 | 14 | 11 | 3 | 35 |
| no-practice | 7 | 8 | 7 | 2 | 24 |
| no-visual | 15 | 33 | 28 | 8 | 84 |
| thin | 6 | 8 | 6 | 2 | 22 |

## Source coverage

- With source: 105
- Without source: 1
- New lessons: 22
- No source: ai00
- Document only (no guide): ds00
- Guide only (no document): ds19, ds20, ds21, ds22, ds23, ds24, ds25, sy37, sy38, sy39, sy40, sy41, sy42, sy43, sy44, ai23, ai24, ai25, ai26, ai27, be07, be08

## Orphan videos

None

## Duplicate topics

Title-only check (word-set similarity 0.85 or higher): none
Topic overlap between differently titled lessons needs manual review in Phase 1.

## Broken cross-references

None found. Checked 0 lesson references in 104 guides. The importer strips .md cross-links from guides, so links in the original sources are not checked.

## Method and limits

- The audit reads the database as imported. Recorded interactive-widget frames are only included if they were imported, so `no-visual` and `no-practice` can be overstated for lessons whose widgets were not imported or not yet ported.
- Unported widgets and dropped SVG figures are not counted as visuals. ASCII diagrams (code blocks marked diagram) are not counted as visuals either; whether they should be is the owner's call.
- Word counts are guide words plus document words, and code text counts as words.
- `drills` is capped at 10 per lesson to mirror the server.

## Owner gate

- Is the source split (lessons with versus without a guide or document) acceptable?
- What are the course sizes after the redesign?
- Three.js or Babylon.js for 3D scenes?
