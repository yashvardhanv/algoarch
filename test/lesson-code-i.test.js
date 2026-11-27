'use strict';
// Task 6 (wave 3, letter i): sy70 to sy73 lesson code and capacity checks. Skips when python is absent.
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

function codeTest(id, file, title) {
  test(`${id} lesson code matches ${title}`, { skip: py ? false : 'python not installed' }, () => {
    const r = spawnSync(py, [check(`${id}_check.py`), lesson(file)], { encoding: 'utf8', timeout: 180000 });
    assert.equal(r.status, 0, r.stderr || r.stdout);
    assert.match(r.stdout, new RegExp(`${id} code checks passed`));
  });
}

codeTest('sy70', 'sy70-dating-app-matching.md', 'every swipe interleaving, the Bloom filter and the exposure cap');
codeTest('sy71', 'sy71-fitness-activity-tracking.md', 'distance and climb checks, the polyline format, Douglas-Peucker, a brute-force segment matcher and crash replays');

const CAPACITY_LESSONS_I = [
  'sy70-dating-app-matching.md',
  'sy71-fitness-activity-tracking.md',
];

test('task 6 capacity estimates are reproduced by script', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [check('capacity_check_i.py'), ...CAPACITY_LESSONS_I.map(lesson)], { encoding: 'utf8', timeout: 180000 });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /capacity checks passed/);
  for (const f of CAPACITY_LESSONS_I) assert.match(r.stdout, new RegExp(f.slice(0, 4)));
});
