
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
