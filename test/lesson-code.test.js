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

test('sy43 lesson code matches brute-force nearest-k, including poles and the antimeridian', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'sy43_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'sy43.md'),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /sy43 code checks passed/);
});

test('sy44 lesson code matches a naive price-time matcher and replays deterministically', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'sy44_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'sy44.md'),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /sy44 code checks passed/);
});

const CAPACITY_LESSONS_B = [
  'sy42.md',
  'sy43.md',
  'sy44.md',
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

test('ds26 lesson code matches reference checks', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'ds26_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'ds26-sorting-selection.md'),
  ], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /ds26 code checks passed/);
});

test('ds27 lesson code matches reference checks', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'ds27_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'ds27-matrix-grid.md'),
  ], { encoding: 'utf8', timeout: 120000 });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /ds27 code checks passed/);
});

test('ds28 lesson code matches reference checks', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'ds28_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'ds28-recursion-fundamentals.md'),
  ], { encoding: 'utf8', timeout: 120000 });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /ds28 code checks passed/);
});

test('ai28 lesson code matches finite differences and reference optimizers', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'ai28_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'ai28-autodiff-gradient-descent.md'),
  ], { encoding: 'utf8', timeout: 120000 });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /ai28 code checks passed/);
});

test('ai29 lesson code matches reference counts, finite-difference gradients and the printed loss numbers', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'ai29_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'ai29-language-model-from-scratch.md'),
  ], { encoding: 'utf8', timeout: 180000 });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /ai29 code checks passed/);
});

test('ai30 lesson code matches a naive attention reference and leaks nothing through the causal mask', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'ai30_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'ai30-attention-transformer-block.md'),
  ], { encoding: 'utf8', timeout: 180000 });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /ai30 code checks passed/);
});

test('ai31 lesson code matches brute-force dedup, contamination and compute-optimal references', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'ai31_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'ai31-pretraining-scaling-laws.md'),
  ], { encoding: 'utf8', timeout: 180000 });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /ai31 code checks passed/);
});

test('sy45 lesson code matches brute-force ring lookups, exhaustive cache-aside interleavings and the printed figures', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'sy45_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'sy45-caching-consistent-hashing.md'),
  ], { encoding: 'utf8', timeout: 180000 });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /sy45 code checks passed/);
});

test('sy46 lesson code matches an independent happened-before, the published Dynamo example and brute-force linearizability', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'sy46_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'sy46-time-clocks-ordering.md'),
  ], { encoding: 'utf8', timeout: 180000 });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /sy46 code checks passed/);
});

test('sy48 lesson code reproduces the SRE Workbook burn-rate figures and a brute-force alert-window reference', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'sy48_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'sy48-slos-error-budgets.md'),
  ], { encoding: 'utf8', timeout: 180000 });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /sy48 code checks passed/);
});

test('sy49 lesson code matches an independent retry-loop simulator and the metastable-failure arithmetic', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'sy49_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'sy49-overload-load-shedding.md'),
  ], { encoding: 'utf8', timeout: 180000 });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /sy49 code checks passed/);
});

test('sy51 lesson code matches a per-read replica brute force, a batching event simulation and full enumeration of contention', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [
    path.join(__dirname, 'lesson_code', 'sy51_check.py'),
    path.join(__dirname, '..', 'data', 'new_lessons', 'sy51-scaling-patterns-reads-writes.md'),
  ], { encoding: 'utf8', timeout: 180000 });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /sy51 code checks passed/);
});
