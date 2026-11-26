'use strict';
// Runs the python code blocks in rewritten lessons against brute-force checks. Skips when python is absent.
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

test('ds19 lesson code matches brute-force checks', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'ds19_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'ds19-advanced-graphs.md'),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /ds19 code checks passed/);
});
