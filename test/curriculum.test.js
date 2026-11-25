'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  parseMinutes,
  findPrereqProblems,
  checkPathways,
  unreachableLessons,
  checkMigrationMap,
  mergeBaseline,
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

// ---- GET /api/pathways (spawns the real server on a temp copy of data/)
const { spawn } = require('node:child_process');
const http = require('node:http');
const { parseMinutes: minutesOf } = require('../curriculum');

const ROOT = path.join(__dirname, '..');
const PORT = 5900 + Math.floor(Math.random() * 300);
const FIXTURE_ID = 'api-fixture';
let child;
let tmpData;
let fixtureLessons = [];

function request(method, urlPath, { body, token } = {}) {
  return new Promise((resolve, reject) => {
    const payload = body ? JSON.stringify(body) : null;
    const h = {};
    if (payload) { h['Content-Type'] = 'application/json'; h['Content-Length'] = Buffer.byteLength(payload); }
    if (token) h['Authorization'] = 'Bearer ' + token;
    const req = http.request({ host: '127.0.0.1', port: PORT, path: urlPath, method, headers: h }, res => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        let json = null;
        try { json = JSON.parse(data); } catch (e) { /* not json */ }
        resolve({ status: res.statusCode, json });
      });
    });
    req.on('error', reject);
    if (payload) req.write(payload);
    req.end();
  });
}

async function startServer() {
  tmpData = fs.mkdtempSync(path.join(os.tmpdir(), 'algoarch-pw-'));
  for (const f of fs.readdirSync(path.join(ROOT, 'data'))) {
    const src = path.join(ROOT, 'data', f);
    if (fs.statSync(src).isFile()) fs.copyFileSync(src, path.join(tmpData, f));
    else fs.cpSync(src, path.join(tmpData, f), { recursive: true });
  }
  const db = openDb(tmpData);
  fixtureLessons = db.prepare('SELECT id, duration FROM lessons ORDER BY position LIMIT 3').all();
  importPathways(db, {
    pathways: [{ id: FIXTURE_ID, title: 'API fixture', description: 'd', kind: 'goal', lessons: fixtureLessons.map(l => ({ id: l.id })) }],
  }, fixtureLessons.map(l => l.id));
  db.close();
  const env = { ...process.env, PORT: String(PORT), ALGOARCH_DATA_DIR: tmpData, AUTH_SECRET: 'test-secret', GEMINI_API_KEY: '' };
  delete env.RAZORPAY_KEY_ID; delete env.RAZORPAY_KEY_SECRET; delete env.ADMIN_KEY; delete env.NODE_ENV;
  for (const k of ['GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GITHUB_CLIENT_ID', 'GITHUB_CLIENT_SECRET', 'PUBLIC_URL']) delete env[k]; // keep the run hermetic
  child = spawn(process.execPath, ['server.js'], { cwd: ROOT, env, stdio: 'ignore' });
  for (let i = 0; i < 50; i++) {
    try { const r = await request('GET', '/api/auth/providers'); if (r.status === 200) break; } catch (e) { /* not up yet */ }
    if (i === 49) throw new Error('server did not start');
    await new Promise(r => setTimeout(r, 100));
  }
  const login = await request('POST', '/api/auth/dev-login', { body: { email: 'pathways@example.com', name: 'T' } });
  assert.equal(login.status, 200);
  return login.json.token;
}

function stopServer() {
  if (child) child.kill();
  if (tmpData) fs.rmSync(tmpData, { recursive: true, force: true });
}

test('GET /api/pathways requires a sign-in and lists pathways with summed minutes', async () => {
  const token = await startServer();
  try {
    const anon = await request('GET', '/api/pathways');
    assert.equal(anon.status, 401);
    const r = await request('GET', '/api/pathways', { token });
    assert.equal(r.status, 200);
    assert.ok(Array.isArray(r.json.pathways));
    const p = r.json.pathways.find(x => x.id === FIXTURE_ID);
    assert.ok(p, 'fixture pathway is listed');
    assert.equal(p.minutes, fixtureLessons.reduce((s, l) => s + minutesOf(l.duration), 0));
    assert.deepEqual(p.lessons.map(l => l.id), fixtureLessons.map(l => l.id));
  } finally {
    stopServer();
  }
});

// ---- generated pathways and real-data checks ----
const { buildPathways } = require('../tools/content/build-pathways');

const genFixture = {
  tracks: [
    { id: 'ta', name: 'Track A', blocks: [{ k: 'b1', t: 'B1', lessons: [
      { id: 'a1', title: 'A1', stars: 5, duration: '10 min' },
      { id: 'a2', title: 'A2', stars: 3, duration: '10 min' },
    ] }] },
    { id: 'tb', name: 'Track B', blocks: [{ k: 'b2', t: 'B2', lessons: [
      { id: 'b1', title: 'B1', stars: 4, duration: '10 min' },
      { id: 'b2', title: 'B2', stars: 5, duration: '10 min' },
    ] }] },
  ],
};

test('buildPathways applies the fixed rules in curriculum order', () => {
  const { pathways } = buildPathways(genFixture);
  const ids = (id) => pathways.find((p) => p.id === id).lessons.map((l) => l.id);
  assert.deepEqual(ids('crash'), ['a1', 'b2']);
  assert.deepEqual(ids('standard'), ['a1', 'b1', 'b2']);
  assert.deepEqual(ids('deep'), ['a1', 'a2', 'b1', 'b2']);
  assert.deepEqual(ids('ta'), ['a1', 'a2']);
  assert.deepEqual(ids('tb'), ['b1', 'b2']);
  assert.deepEqual(pathways.filter((p) => p.kind === 'goal').map((p) => p.id), ['ta', 'tb']);
  assert.deepEqual(pathways.filter((p) => p.kind === 'horizon').map((p) => p.id), ['crash', 'standard', 'deep']);
  for (const p of pathways) assert.equal(typeof p.description, 'string');
});

test('buildPathways is deterministic', () => {
  assert.equal(JSON.stringify(buildPathways(genFixture)), JSON.stringify(buildPathways(genFixture)));
});

test('real data: pathways, prerequisites and the id baseline are consistent', () => {
  const read = (f) => JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', f), 'utf8'));
  const curriculum = read('curriculum.json');
  const pathways = read('pathways.json').pathways;
  const baseline = read('migrations/2026-11-26-curriculum-map.json');
  const lessons = curriculum.tracks.flatMap((t) => t.blocks.flatMap((b) => b.lessons));
  assert.deepEqual(checkPathways(pathways, lessons).errors, []);
  assert.deepEqual(unreachableLessons(pathways, lessons), []);
  assert.deepEqual(findPrereqProblems(lessons), { unknown: [], selfLoops: [], cycles: [] });
  assert.deepEqual(checkMigrationMap(baseline.ids, lessons.map((l) => l.id)).missing, []);
  assert.ok(baseline.ids.length >= 106);
});

// ---- baseline can only grow (I-1)
test('mergeBaseline reports a rename as missing and keeps both ids', () => {
  assert.deepEqual(mergeBaseline(['a', 'b'], ['a', 'c']), { ids: ['a', 'b', 'c'], missing: ['b'] });
});

test('mergeBaseline on pure growth has nothing missing', () => {
  assert.deepEqual(mergeBaseline(['a', 'b'], ['a', 'b', 'c', 'd']), { ids: ['a', 'b', 'c', 'd'], missing: [] });
});

test('mergeBaseline sorts and de-duplicates', () => {
  assert.deepEqual(mergeBaseline(['z', 'b', 'b', 'a'], ['c', 'a', 'c', 'y']), { ids: ['a', 'b', 'c', 'y', 'z'], missing: ['b', 'z'] });
});

function copyDataFiles(dest, files) {
  for (const f of files) {
    const src = path.join(ROOT, 'data', f);
    fs.mkdirSync(path.dirname(path.join(dest, f)), { recursive: true });
    fs.copyFileSync(src, path.join(dest, f));
  }
}

function runNode(args) {
  return require('node:child_process').spawnSync(process.execPath, args, { cwd: ROOT, encoding: 'utf8' });
}

test('validate-curriculum --write-baseline refuses to rewrite when a lesson id was lost', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'algoarch-bl-'));
  try {
    const BASE = 'migrations/2026-11-26-curriculum-map.json';
    copyDataFiles(tmp, ['curriculum.json', 'pathways.json', BASE]);
    const cur = JSON.parse(fs.readFileSync(path.join(tmp, 'curriculum.json'), 'utf8'));
    const removed = cur.tracks[0].blocks[0].lessons.shift().id;
    fs.writeFileSync(path.join(tmp, 'curriculum.json'), JSON.stringify(cur));
    const before = fs.readFileSync(path.join(tmp, BASE));
    const r = runNode(['tools/content/validate-curriculum.js', '--data', tmp, '--write-baseline']);
    assert.equal(r.status, 1);
    assert.ok(r.stdout.includes('lost lesson ids: ' + removed), r.stdout);
    assert.ok(Buffer.from(fs.readFileSync(path.join(tmp, BASE))).equals(before), 'baseline unchanged');
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  }
});
