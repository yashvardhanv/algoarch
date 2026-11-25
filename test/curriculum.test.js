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

// ---- storage (migration 4, lessonRow, getPathways, importPathways)
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { openDb, createRepo } = require('../db');
const { importPathways } = require('../tools/content/import');

function fixtureDb() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'algoarch-curr-'));
  const db = openDb(dir);
  db.prepare("INSERT INTO tracks (id, name, position) VALUES ('t1', 'Track', 0)").run();
  db.prepare("INSERT INTO course_blocks (id, track_id, key, title, position) VALUES (1, 't1', 'k', 'Block', 0)").run();
  return db;
}
function addLesson(db, id, pos, duration, extra = {}) {
  db.prepare("INSERT INTO lessons (id, track_id, block_id, position, num, title, duration) VALUES (?, 't1', 1, ?, ?, ?, ?)")
    .run(id, pos, String(pos + 1), 'Title ' + id, duration);
  for (const [col, val] of Object.entries(extra)) db.prepare(`UPDATE lessons SET ${col} = ? WHERE id = ?`).run(val, id);
}
const lessonsOf = (db) => createRepo(db).getCurriculum().tracks[0].blocks[0].lessons;

test('lessonRow omits new optional fields when unset', () => {
  const db = fixtureDb();
  addLesson(db, 'a', 0, '10 min');
  const row = lessonsOf(db)[0];
  for (const k of ['prereqs', 'objectives', 'sources', 'level', 'reviewedAt']) assert.equal(k in row, false, k);
});

test('lessonRow exposes new optional fields when set', () => {
  const db = fixtureDb();
  addLesson(db, 'a', 0, '10 min', { prereqs: '["a"]', level: 'senior', reviewed_at: '2026-11-26' });
  const row = lessonsOf(db)[0];
  assert.deepEqual(row.prereqs, ['a']);
  assert.equal(row.level, 'senior');
  assert.equal(row.reviewedAt, '2026-11-26');
  assert.equal('objectives' in row, false);
  assert.equal('sources' in row, false);
});

test('getPathways orders lessons, sums minutes, omits removed lessons and null notes', () => {
  const db = fixtureDb();
  addLesson(db, 'a', 0, '10 min');
  addLesson(db, 'b', 1, '25 min');
  db.prepare("INSERT INTO pathways (id, title, description, kind, position) VALUES ('p2', 'Second', NULL, 'role', 1), ('p1', 'First', 'd', 'role', 0)").run();
  db.prepare("INSERT INTO pathway_lessons (pathway_id, lesson_id, position, note) VALUES ('p1', 'b', 1, 'why'), ('p1', 'a', 0, NULL), ('p1', 'gone', 2, NULL)").run();
  const ps = createRepo(db).getPathways();
  assert.deepEqual(ps.map(p => p.id), ['p1', 'p2']);
  assert.deepEqual(ps[0].lessons, [
    { id: 'a', title: 'Title a', trackId: 't1', duration: '10 min' },
    { id: 'b', title: 'Title b', trackId: 't1', duration: '25 min', note: 'why' },
  ]);
  assert.equal(ps[0].minutes, 35);
  assert.equal(ps[1].minutes, 0);
  assert.deepEqual(ps[1].lessons, []);
});

const PW = { pathways: [{ id: 'p1', title: 'P', description: 'd', kind: 'role', lessons: [{ id: 'a' }, { id: 'b', note: 'n' }] }] };

test('importPathways rejects an unknown lesson before writing', () => {
  const db = fixtureDb();
  const bad = { pathways: [PW.pathways[0], { id: 'p2', title: 'Q', kind: 'role', lessons: [{ id: 'zzz' }] }] };
  assert.throws(() => importPathways(db, bad, new Set(['a', 'b'])), { message: 'pathway p2 references unknown lesson zzz' });
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM pathways').get().n, 0);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM pathway_lessons').get().n, 0);
});

test('importPathways is idempotent', () => {
  const db = fixtureDb();
  const count = () => [db.prepare('SELECT COUNT(*) AS n FROM pathways').get().n, db.prepare('SELECT COUNT(*) AS n FROM pathway_lessons').get().n];
  importPathways(db, PW, ['a', 'b']);
  const first = count();
  importPathways(db, PW, ['a', 'b']);
  assert.deepEqual(count(), first);
  assert.deepEqual(first, [1, 2]);
});
