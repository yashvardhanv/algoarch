'use strict';
// Wave 3 task 4 (sy63 to sy65): runs the python code blocks of the lessons against reference checks. Skips when python is absent.
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

test('sy63 lesson code matches the retry rules, a lost-reply simulation, full-state mailbox replicas under random operations and brute-force DMARC alignment', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [check('sy63_check.py'), lesson('sy63-email-service.md')], { encoding: 'utf8', timeout: 300000 });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /sy63 code checks passed/);
});

const CAPACITY_LESSONS_G = [
  'sy63-email-service.md',
];

test('sy63 capacity estimates are reproduced by script', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [check('capacity_check_g.py'), ...CAPACITY_LESSONS_G.map(lesson)], { encoding: 'utf8', timeout: 300000 });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /capacity checks passed/);
  for (const f of CAPACITY_LESSONS_G) assert.match(r.stdout, new RegExp(f.slice(0, 4)));
});
