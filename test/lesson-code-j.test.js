'use strict';
// Task 7 (wave 3, letter j): sy74 to sy77 lesson code and capacity checks. Skips when python is absent.
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

codeTest('sy74', 'sy74-news-aggregator.md', 'shingle and Jaccard definitions, MinHash bias, the banding curve, exact pairwise components and entry revisions');
codeTest('sy75', 'sy75-feature-flags-config.md', 'a nested-ramp, independence and ordering suite, a never-throw client and a propagation simulation');
codeTest('sy76', 'sy76-social-graph-pymk.md', 'the two-hop definition, the hub guard, the ranking rules and the shard fan-out formula');
codeTest('sy77', 'sy77-dns-at-scale.md', 'a packet parser, resolver boundary cases, coalescing and a Poisson simulation');

test('sy74 to sy77 capacity estimates are reproduced by script', { skip: py ? false : 'python not installed' }, () => {
  const r = spawnSync(py, [check('capacity_check_j.py'), lesson('sy77-dns-at-scale.md'), lesson('sy75-feature-flags-config.md'), lesson('sy76-social-graph-pymk.md'), lesson('sy74-news-aggregator.md')], { encoding: 'utf8', timeout: 180000 });
  assert.equal(r.status, 0, r.stderr || r.stdout);
  assert.match(r.stdout, /capacity_check_j \(sy77\) passed/);
  assert.match(r.stdout, /capacity_check_j \(sy75\) passed/);
  assert.match(r.stdout, /capacity_check_j \(sy76\) passed/);
  assert.match(r.stdout, /capacity_check_j \(sy74\) passed/);
});
