'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  parseMinutes,
  findPrereqProblems,
  checkPathways,
  unreachableLessons,
  checkMigrationMap,
} = require('../curriculum');

test('parseMinutes reads the first integer before min', () => {
  assert.equal(parseMinutes('45 min'), 45);
  assert.equal(parseMinutes('45 min drill'), 45);
  assert.equal(parseMinutes('1 hr'), 0);
  assert.equal(parseMinutes(undefined), 0);
  assert.equal(parseMinutes(null), 0);
  assert.equal(parseMinutes(''), 0);
});

test('findPrereqProblems accepts a diamond', () => {
  const r = findPrereqProblems([
    { id: 'a' },
    { id: 'b', prereqs: ['a'] },
    { id: 'c', prereqs: ['a'] },
    { id: 'd', prereqs: ['b', 'c'] },
  ]);
  assert.deepEqual(r, { unknown: [], selfLoops: [], cycles: [] });
});

test('findPrereqProblems finds a cycle once, rotated to smallest id', () => {
  const r = findPrereqProblems([
    { id: 'a', prereqs: ['c'] },
    { id: 'b', prereqs: ['a'] },
    { id: 'c', prereqs: ['b'] },
  ]);
  assert.deepEqual(r.cycles, [['a', 'c', 'b']]);
  assert.deepEqual(r.selfLoops, []);
});

test('findPrereqProblems reports self-loops separately', () => {
  const r = findPrereqProblems([{ id: 'x', prereqs: ['x'] }]);
  assert.deepEqual(r.selfLoops, ['x']);
  assert.deepEqual(r.cycles, []);
});

test('findPrereqProblems reports unknown prereqs', () => {
  const r = findPrereqProblems([{ id: 'y', prereqs: ['nope'] }]);
  assert.deepEqual(r.unknown, [{ lesson: 'y', prereq: 'nope' }]);
});

const lessons = [
  { id: 'a', duration: '45 min' },
  { id: 'b', duration: '45 min drill', prereqs: ['a'] },
  { id: 'c' },
];

test('checkPathways errors when a lesson precedes its prerequisite', () => {
  const r = checkPathways([{ id: 'p1', lessons: [{ id: 'b' }, { id: 'a' }] }], lessons);
  assert.deepEqual(r.errors, ['p1: b comes before its prerequisite a']);
});

test('checkPathways warns when a prerequisite is not in the pathway', () => {
  const r = checkPathways([{ id: 'p1', lessons: [{ id: 'b' }] }], lessons);
  assert.deepEqual(r.errors, []);
  assert.deepEqual(r.warnings, ['p1: b needs a, which the pathway does not include']);
});

test('checkPathways reports unknown, duplicate and empty', () => {
  const r = checkPathways(
    [
      { id: 'p1', lessons: [{ id: 'zzz' }, { id: 'a' }, { id: 'a' }] },
      { id: 'p2', lessons: [] },
    ],
    lessons
  );
  assert.ok(r.errors.includes('unknown lesson zzz in p1'));
  assert.ok(r.errors.includes('duplicate lesson a in p1'));
  assert.ok(r.errors.includes('empty pathway p2'));
});

test('checkPathways sums minutes per pathway', () => {
  const r = checkPathways(
    [{ id: 'p1', lessons: [{ id: 'a' }, { id: 'b' }, { id: 'c' }] }],
    lessons
  );
  assert.equal(r.minutes.p1, 90);
});

test('unreachableLessons returns ids in no pathway', () => {
  const r = unreachableLessons([{ id: 'p1', lessons: [{ id: 'b' }] }], lessons);
  assert.deepEqual(r, ['a', 'c']);
});

test('checkMigrationMap reports missing and added ids sorted', () => {
  assert.deepEqual(checkMigrationMap(['a', 'b', 'c'], ['b', 'c', 'd']), {
    missing: ['a'],
    added: ['d'],
  });
});
