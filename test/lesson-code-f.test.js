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

test('sy61 lesson code: ICE priorities, SFU sequence rewriting, NACK packing and layer allocation', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [check('sy61_check.py'), lesson('sy61-video-conferencing-webrtc.md')], { encoding: 'utf8', timeout: 400000 });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /sy61 code checks passed/);
});

test('sy62 lesson code: prefetch and source rules, chunk scheduler, tracker, LRU cache, seek index and fractional playlist keys', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [check('sy62_check.py'), lesson('sy62-music-streaming.md')], { encoding: 'utf8', timeout: 300000 });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /sy62 code checks passed/);
});

const CAPACITY_LESSONS_F = [
  'sy60-online-judge-sandboxed-execution.md',
  'sy61-video-conferencing-webrtc.md',
  'sy62-music-streaming.md',
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
