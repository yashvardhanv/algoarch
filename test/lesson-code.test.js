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

test('ds20 lesson code matches brute-force checks', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'ds20_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'ds20-segment-trees.md'),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /ds20 code checks passed/);
});

test('ds21 lesson code matches brute-force checks', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'ds21_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'ds21-bitmask-dp.md'),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /ds21 code checks passed/);
});

test('ds22 lesson code matches brute-force checks', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'ds22_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'ds22-math-sampling.md'),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /ds22 code checks passed/);
});

test('ds23 lesson code matches brute-force checks', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'ds23_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'ds23-string-algorithms.md'),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /ds23 code checks passed/);
});

test('ds24 lesson code matches brute-force checks', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'ds24_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'ds24.md'),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /ds24 code checks passed/);
});

test('ds25 lesson code matches brute-force checks', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'ds25_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'ds25.md'),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /ds25 code checks passed/);
});

test('ai23 lesson code matches reference checks', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'ai23_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'ai23-vllm-serving.md'),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /ai23 code checks passed/);
});

test('ai24 lesson code matches reference checks', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'ai24_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'ai24-semantic-caching.md'),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /ai24 code checks passed/);
});

test('ai25 lesson code matches reference checks', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'ai25_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'ai25-constrained-generation.md'),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /ai25 code checks passed/);
});

test('ai26 lesson code matches reference checks', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'ai26_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'ai26-dpo-alignment.md'),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /ai26 code checks passed/);
});

test('sy37 lesson code matches brute-force checks', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'sy37_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'sy37-distributed-search.md'),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /sy37 code checks passed/);
});

test('sy38 lesson code matches reference checks', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'sy38_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'sy38-collaborative-docs-crdt.md'),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /sy38 code checks passed/);
});

test('sy39 lesson code matches brute-force checks', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'sy39_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'sy39-realtime-leaderboard.md'),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /sy39 code checks passed/);
});

const CAPACITY_LESSONS = [
  'sy37-distributed-search.md',
  'sy38-collaborative-docs-crdt.md',
  'sy39-realtime-leaderboard.md',
  'sy40-spanner-truetime-dr.md',
];

test('sy40 lesson code matches reference checks', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'sy40_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'sy40-spanner-truetime-dr.md'),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /sy40 code checks passed/);
});

test('sy41 lesson code matches reference models and threaded checks', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'sy41_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'sy41-machine-coding-lld.md'),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /sy41 code checks passed/);
});

test('sy42 lesson code matches reference models under random and threaded interleavings', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'sy42_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'sy42.md'),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /sy42 code checks passed/);
});

const CAPACITY_LESSONS_B = [
  'sy42.md',
];

test('sy42-sy44 capacity estimates are reproduced by script', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'capacity_check_b.py'),
    ...CAPACITY_LESSONS_B.map((f) => path.join(__dirname, '..', 'data', 'new_lessons', f)),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /capacity checks passed/);
  for (const f of CAPACITY_LESSONS_B) assert.match(r.stdout, new RegExp(f.slice(0, 4)));
});

test('sy37-sy40 capacity estimates are reproduced by script', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'capacity_check.py'),
    ...CAPACITY_LESSONS.map((f) => path.join(__dirname, '..', 'data', 'new_lessons', f)),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /capacity checks passed/);
  for (const f of CAPACITY_LESSONS) assert.match(r.stdout, new RegExp(f.slice(0, 4)));
});
