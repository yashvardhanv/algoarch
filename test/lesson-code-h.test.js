'use strict';
// Wave 3 task 5 (sy66, sy67, sy69): runs the python blocks of each lesson against independent references.
// Kept apart from lesson-code.test.js so parallel branches do not conflict. Skips when python is absent.
const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const path = require('node:path');

function findPython() {
  for (const cmd of ['python', 'python3']) {
    const r = spawnSync(cmd, ['--version']);
    if (r.status === 0) return cmd;
  }
  return null;
}

const py = findPython();
const lesson = (f) => path.join(__dirname, '..', 'data', 'new_lessons', f);
const check = (f) => path.join(__dirname, 'lesson_code', f);

// wave3 task5 sy66 begin
test('sy66 lesson code matches scan references, retention bounds, merge closed forms and a lossy at-least-once channel', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [check('sy66_check.py'), lesson('sy66-log-aggregation-search.md')], { encoding: 'utf8', timeout: 300000 });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /sy66 code checks passed/);
});
// wave3 task5 sy66 end

const CAPACITY_LESSONS_H = [
  // wave3 task5 capacity begin
  'sy66-log-aggregation-search.md',
  // wave3 task5 capacity end
];

test('sy66, sy67 and sy69 capacity estimates are reproduced by script', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [check('capacity_check_h.py'), ...CAPACITY_LESSONS_H.map(lesson)], { encoding: 'utf8', timeout: 300000 });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /capacity checks passed/);
  for (const f of CAPACITY_LESSONS_H) assert.match(r.stdout, new RegExp(f.slice(0, 4)));
});
