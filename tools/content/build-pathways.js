#!/usr/bin/env node
'use strict';

// Generates data/pathways.json from data/curriculum.json by fixed rules.
// Usage: node tools/content/build-pathways.js [--write]
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', '..', 'data');

function flatten(curriculum) {
  const out = [];
  for (const t of curriculum.tracks) {
    for (const b of t.blocks) {
      for (const l of b.lessons) out.push({ track: t.id, lesson: l });
    }
  }
  return out;
}

function buildPathways(curriculum) {
  const all = flatten(curriculum);
  const refs = (rows) => rows.map((r) => ({ id: r.lesson.id }));
  const pathways = [
    {
      id: 'crash',
      title: 'Crash',
      description: 'Every lesson rated 5 stars, in course order.',
      kind: 'horizon',
      lessons: refs(all.filter((r) => r.lesson.stars === 5)),
    },
    {
      id: 'standard',
      title: 'Standard',
      description: 'Every lesson rated 4 stars or more, in course order.',
      kind: 'horizon',
      lessons: refs(all.filter((r) => r.lesson.stars >= 4)),
    },
    {
      id: 'deep',
      title: 'Deep',
      description: 'Every lesson in the course, in course order.',
      kind: 'horizon',
      lessons: refs(all),
    },
  ];
  for (const t of curriculum.tracks) {
    pathways.push({
      id: t.id,
      title: t.name,
      description: `Every lesson in the ${t.name} track, in course order.`,
      kind: 'goal',
      lessons: refs(all.filter((r) => r.track === t.id)),
    });
  }
  return { pathways };
}

module.exports = { buildPathways };

if (require.main === module) {
  const curriculum = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'curriculum.json'), 'utf8'));
  const text = JSON.stringify(buildPathways(curriculum), null, 2) + '\n';
  if (process.argv.includes('--write')) {
    fs.writeFileSync(path.join(DATA_DIR, 'pathways.json'), text);
    console.log('wrote data/pathways.json');
  } else {
    process.stdout.write(text);
  }
}
