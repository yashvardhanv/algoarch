#!/usr/bin/env node
'use strict';

// Usage: node tools/content/validate-curriculum.js [--write-baseline]
const fs = require('fs');
const path = require('path');
const {
  findPrereqProblems,
  checkPathways,
  unreachableLessons,
  checkMigrationMap,
} = require('../../curriculum');

const DATA_DIR = path.join(__dirname, '..', '..', 'data');
const BASELINE = path.join(DATA_DIR, 'migrations', '2026-11-26-curriculum-map.json');
const read = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));

const curriculum = read(path.join(DATA_DIR, 'curriculum.json'));
const lessons = curriculum.tracks.flatMap((t) => t.blocks.flatMap((b) => b.lessons));
const currentIds = lessons.map((l) => l.id);

if (process.argv.includes('--write-baseline')) {
  fs.mkdirSync(path.dirname(BASELINE), { recursive: true });
  const body = { version: 1, date: '2026-11-26', ids: currentIds.slice().sort() };
  fs.writeFileSync(BASELINE, JSON.stringify(body, null, 2) + '\n');
  console.log(`wrote baseline with ${body.ids.length} ids`);
}

const pathways = read(path.join(DATA_DIR, 'pathways.json')).pathways;
const errors = [];
const warnings = [];

const prereq = findPrereqProblems(lessons);
for (const u of prereq.unknown) errors.push(`unknown prerequisite ${u.prereq} on ${u.lesson}`);
for (const id of prereq.selfLoops) errors.push(`self-referencing prerequisite on ${id}`);
for (const c of prereq.cycles) errors.push(`prerequisite cycle: ${c.join(' -> ')}`);

const pw = checkPathways(pathways, lessons);
errors.push(...pw.errors);
warnings.push(...pw.warnings);

const unreachable = unreachableLessons(pathways, lessons);
for (const id of unreachable) errors.push(`lesson ${id} is in no pathway`);

if (fs.existsSync(BASELINE)) {
  const map = checkMigrationMap(read(BASELINE).ids, currentIds);
  for (const id of map.missing) errors.push(`baseline lesson id ${id} is missing from the curriculum`);
  if (map.added.length) console.log(`added since baseline: ${map.added.join(', ')}`);
} else {
  warnings.push('no id baseline found (run with --write-baseline)');
}

console.log('minutes per pathway:');
for (const [id, m] of Object.entries(pw.minutes)) console.log(`  ${id}: ${m}`);
console.log(`unreachable lessons: ${unreachable.length ? unreachable.join(', ') : 'none'}`);
console.log(`warnings: ${warnings.length}`);
for (const w of warnings) console.log(`  ${w}`);
console.log(`errors: ${errors.length}`);
for (const e of errors) console.log(`  ${e}`);
process.exit(errors.length ? 1 : 0);
