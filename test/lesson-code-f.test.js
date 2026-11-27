'use strict';
// Wave 3 task 3 (sy60 to sy62): runs the lesson code against reference checks. Skips when python is absent.
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

test('sy60 lesson code: checker, verdict precedence, real subprocess runner, re-measure rule and judge queue', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [check('sy60_check.py'), lesson('sy60-online-judge-sandboxed-execution.md')], { encoding: 'utf8', timeout: 300000 });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /sy60 code checks passed/);
});

const CAPACITY_LESSONS_F = [
  'sy60-online-judge-sandboxed-execution.md',
];

test('sy60 to sy62 capacity estimates are reproduced by script', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    check('capacity_check_f.py'),
    ...CAPACITY_LESSONS_F.map(lesson),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /capacity checks passed/);
  for (const f of CAPACITY_LESSONS_F) assert.match(r.stdout, new RegExp(f.slice(0, 4)));
});
