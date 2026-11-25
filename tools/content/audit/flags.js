'use strict';

const PITFALL_RE = /pitfall|mistake|gotcha|failure mode|common error|anti-?pattern/i;
const DRILL_HEADING_RE = /^#{2,3}\s+(Drills|Homework|Mock Drills|Practice Exercises)/i;
const MAX_DRILLS = 10;

function hasPitfall(text) {
  return PITFALL_RE.test(text || '');
}

function countDrills(markdown) {
  if (!markdown) return 0;
  let inSection = false;
  let count = 0;
  for (const line of String(markdown).split(/\r?\n/)) {
    if (/^#{1,6}\s/.test(line)) {
      inSection = DRILL_HEADING_RE.test(line);
      continue;
    }
    if (inSection && /^\s*(?:[-*+]|\d+[.)])\s+\S/.test(line)) count++;
  }
  return Math.min(count, MAX_DRILLS);
}

function flagLesson(row) {
  const { guide, doc } = row;
  const flags = [];
  if (guide.words + doc.words < 600 && doc.codeCells + doc.widgets === 0) flags.push('thin');
  if (doc.visuals === 0 && doc.widgetsPorted === 0) flags.push('no-visual');
  if (doc.codeCells + doc.quizzes + doc.checklists + row.drills === 0) flags.push('no-practice');
  if (!row.guidePitfall && !row.docPitfall) flags.push('no-pitfalls');
  if (row.badDocument) flags.push('bad-document');
  return flags.sort();
}

module.exports = { flagLesson, countDrills, hasPitfall };
