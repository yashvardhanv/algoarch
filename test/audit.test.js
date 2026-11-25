'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { wordCount, guideStats, documentStats } = require('../tools/content/audit/metrics');

test('wordCount ignores tokens without letters or digits', () => {
  assert.equal(wordCount('Two  pointers: O(n) -- fast'), 4);
});

test('guideStats counts words, headings and fenced code blocks', () => {
  assert.deepEqual(
    guideStats('## A\ntext words here\n```py\nx=1\n```\n### B'),
    { words: 6, headings: 2, codeBlocks: 1 }
  );
});

test('documentStats(null) is all zeros', () => {
  assert.deepEqual(documentStats(null), {
    words: 0, headings: 0, codeBlocks: 0, codeCells: 0, cellsWithTests: 0,
    widgets: 0, widgetsPorted: 0, quizzes: 0, checklists: 0, visuals: 0, text: '',
  });
});

test('documentStats walks nested blocks and counts widgets', () => {
  const doc = {
    sections: [{
      blocks: [
        { type: 'paragraph', content: ['Hello ', { c: ['big'] }, ' world'] },
        { type: 'code_cell', title: 't', language: 'py', starter: '', tests: 'assert 1' },
        { type: 'widget', kind: 'frames', ported: true, blocks: [] },
        { type: 'widget', kind: 'quiz', ported: false, blocks: [] },
        { type: 'callout', tone: 'info', label: null, blocks: [
          { type: 'paragraph', content: ['two words'] },
        ] },
      ],
    }],
  };
  const s = documentStats(doc);
  assert.ok(s.words >= 5);
  assert.equal(s.codeCells, 1);
  assert.equal(s.cellsWithTests, 1);
  assert.equal(s.widgets, 2);
  assert.equal(s.widgetsPorted, 1);
  assert.equal(s.quizzes, 1);
  assert.equal(s.visuals, 1);
});

const { flagLesson, countDrills, hasPitfall } = require('../tools/content/audit/flags');

function row(over = {}) {
  const doc = Object.assign({
    words: 0, codeCells: 0, widgets: 0, widgetsPorted: 0, quizzes: 0, checklists: 0, visuals: 0,
  }, over.doc);
  return Object.assign({
    guide: { words: 0, headings: 0, codeBlocks: 0 },
    drills: 0, badDocument: false, guidePitfall: true, docPitfall: false,
  }, over, { doc });
}

test('flagLesson marks 599 words without cell or widget as thin', () => {
  assert.ok(flagLesson(row({ guide: { words: 599 } })).includes('thin'));
});

test('flagLesson: one code cell removes thin', () => {
  assert.ok(!flagLesson(row({ guide: { words: 599 }, doc: { codeCells: 1 } })).includes('thin'));
});

test('flagLesson: exactly 600 words is not thin', () => {
  assert.ok(!flagLesson(row({ guide: { words: 300 }, doc: { words: 300 } })).includes('thin'));
});

test('flagLesson: lone ported widget avoids no-visual but has no-practice', () => {
  const flags = flagLesson(row({ doc: { widgets: 1, widgetsPorted: 1 } }));
  assert.ok(!flags.includes('no-visual'));
  assert.ok(flags.includes('no-practice'));
});

test('flagLesson: ported widget plus a quiz has neither no-visual nor no-practice', () => {
  const flags = flagLesson(row({ doc: { widgets: 1, widgetsPorted: 1, quizzes: 1 } }));
  assert.ok(!flags.includes('no-visual'));
  assert.ok(!flags.includes('no-practice'));
});

test('flagLesson: no-pitfalls only when neither source mentions one', () => {
  assert.ok(flagLesson(row({ guidePitfall: false, docPitfall: false })).includes('no-pitfalls'));
  assert.ok(!flagLesson(row({ guidePitfall: false, docPitfall: true })).includes('no-pitfalls'));
});

test('flagLesson: badDocument yields bad-document, result is sorted', () => {
  const flags = flagLesson(row({ badDocument: true, guidePitfall: false }));
  assert.ok(flags.includes('bad-document'));
  assert.deepEqual(flags, [...flags].sort());
});

test('countDrills counts list items up to the next heading', () => {
  assert.equal(countDrills('## Drills\n1. a\n2. b\n## Next\n1. c'), 2);
  assert.equal(countDrills(null), 0);
  assert.equal(countDrills('## Other\n- a'), 0);
});

test('hasPitfall matches pitfall vocabulary only', () => {
  assert.equal(hasPitfall('a common mistake'), true);
  assert.equal(hasPitfall('all good'), false);
  assert.equal(hasPitfall(''), false);
});

const { findOrphanVideos, findDuplicateTitles, findBrokenRefs } = require('../tools/content/audit/crosscheck');

test('findOrphanVideos ignores null and blank lessonIds', () => {
  assert.deepEqual(
    findOrphanVideos(
      [{ id: 'v1', lessonId: 'ds01' }, { id: 'v2', lessonId: null }, { id: 'v3', lessonId: ' ' }, { id: 'v4', lessonId: 'zz99' }],
      new Set(['ds01'])
    ),
    ['v4']
  );
});

test('findDuplicateTitles pairs near-identical normalized titles', () => {
  assert.deepEqual(
    findDuplicateTitles([
      { id: 'a', title: 'Two Pointers' },
      { id: 'b', title: 'Two Pointers: Part II' },
      { id: 'c', title: 'Postgres I: Indexes & Scans' },
      { id: 'd', title: 'Postgres II: MVCC & Locking' },
    ]),
    [['a', 'b']]
  );
});

test('findBrokenRefs reports unknown lesson ids once per pair', () => {
  assert.deepEqual(
    findBrokenRefs(
      [{ id: 'ds02', markdown: 'see [x](#open-lesson-ds01) and [y](#open-lesson-nope) [z](lesson:nope), [w](lesson:gone).' }],
      new Set(['ds01', 'ds02'])
    ),
    [{ from: 'ds02', to: 'nope' }, { from: 'ds02', to: 'gone' }]
  );
});

// ---------------------------------------------------------------- build (integration)
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { openDb } = require('../db');
const { loadAuditInput, buildAudit, toCsv, renderSummary } = require('../tools/content/audit/build');

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = '';
  let q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; } else if (c === '"') q = false; else field += c;
    } else if (c === '"') q = true;
    else if (c === ',') { row.push(field); field = ''; }
    else if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
    else field += c;
  }
  return rows;
}

function makeFixture() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'audit-'));
  const db = openDb(tmp);
  db.prepare("INSERT INTO tracks (id, name, position) VALUES ('t1', 'Track One', 1)").run();
  db.prepare("INSERT INTO course_blocks (id, track_id, key, title, position) VALUES (1, 't1', 'b1', 'Block One', 1)").run();
  const ins = db.prepare('INSERT INTO lessons (id, track_id, block_id, position, title, stars, duration, is_new) VALUES (?, \'t1\', 1, ?, ?, 4, \'30 min\', ?)');
  ins.run('L1', 1, 'Alpha', 0);
  ins.run('L2', 2, 'Review Focus 1', 1);
  ins.run('L3', 3, 'Review Focus 2', 0);
  ins.run('L4', 4, 'Cache, "Aside" \u00b7 \u20b950\nLPA', 0);
  ins.run('L5', 5, 'Zeta', 0);
  const words = (n) => Array.from({ length: n }, (_, i) => 'word' + i).join(' ');
  const guide = db.prepare("INSERT INTO lesson_guides (lesson_id, markdown, updated_at) VALUES (?, ?, 'x')");
  guide.run('L1', '## Intro\n' + words(700));
  guide.run('L3', '## Intro\n' + words(10));
  const doc = db.prepare("INSERT INTO lesson_documents (lesson_id, schema_version, document, updated_at) VALUES (?, 1, ?, 'x')");
  doc.run('L1', JSON.stringify({ sections: [{ blocks: [
    { type: 'widget', kind: 'frames', ported: true, blocks: [] },
    { type: 'code_cell', title: 't', language: 'py', starter: '', tests: 'assert 1' },
    { type: 'widget', kind: 'quiz', ported: false, blocks: [] },
  ] }] }));
  doc.run('L3', 'not json');
  db.prepare("INSERT INTO videos (id, youtube_id, track_id, lesson_id, title, position) VALUES ('v1', 'y1', 't1', 'L1', 'V', 1)").run();
  db.prepare("INSERT INTO videos (id, youtube_id, track_id, lesson_id, title, position) VALUES ('v2', 'y2', 't1', 'GONE', 'V', 2)").run();
  db.close();
  return tmp;
}

test('buildAudit computes rows and flags from the database', () => {
  const tmp = makeFixture();
  const { rows, summary } = buildAudit(loadAuditInput(tmp));
  const by = Object.fromEntries(rows.map((r) => [r.id, r]));
  assert.equal(rows.length, 5);
  assert.equal(by.L1.has_source, 'true');
  assert.equal(by.L1.videos_linked, 1);
  for (const f of ['thin', 'no-visual', 'no-practice']) assert.ok(!by.L1.flags.split(';').includes(f), f);
  assert.equal(by.L2.has_source, 'false');
  assert.equal(by.L2.words, 0);
  assert.ok(by.L2.flags.split(';').includes('thin'));
  assert.ok(by.L3.flags.split(';').includes('bad-document'));
  assert.equal(by.L3.words, 11); // guide only: heading word plus ten words
  assert.equal(by.L1.manual_flags, '');
  assert.deepEqual(summary.orphanVideos, ['v2']);
  assert.equal(summary.sourceSplit.withSource, 2);
  assert.equal(summary.sourceSplit.withoutSource, 3);
});

test('toCsv round-trips awkward titles and has the exact header', () => {
  const { rows } = buildAudit(loadAuditInput(makeFixture()));
  const parsed = parseCsv(toCsv(rows));
  assert.equal(parsed[0].join(','), 'id,track,block,title,stars,declared_duration,words,headings,code_blocks,code_cells,cells_with_tests,widgets,widgets_ported,quizzes,checklists,visuals,drills,videos_linked,has_source,is_new,flags,manual_flags');
  const l4 = parsed.find((r) => r[0] === 'L4');
  assert.equal(l4[3], 'Cache, "Aside" \u00b7 \u20b950\nLPA');
});

test('empty database yields no rows and a full summary', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'audit-empty-'));
  openDb(tmp).close();
  const { rows, summary } = buildAudit(loadAuditInput(tmp));
  assert.deepEqual(rows, []);
  const md = renderSummary(summary);
  for (const h of ['# Curriculum audit', '## Totals', '## Flags by course', '## Source coverage', '## Orphan videos', '## Duplicate topics', '## Broken cross-references', '## Owner gate']) {
    assert.ok(md.includes(h), h);
  }
});

test('output is deterministic and loadAuditInput rejects a missing database', () => {
  const tmp = makeFixture();
  const a = toCsv(buildAudit(loadAuditInput(tmp)).rows);
  const b = toCsv(buildAudit(loadAuditInput(tmp)).rows);
  assert.equal(a, b);
  assert.throws(() => loadAuditInput(path.join(tmp, 'nope')), /not found/i);
});

test('countDrills accepts numbered section headings', () => {
  assert.equal(countDrills('## 8. Drills\n1. a\n2. b\n## 9. Next\n1. c'), 2);
  assert.equal(countDrills('### 3. Homework\n- x\n- y\n- z'), 3);
  assert.equal(countDrills('## Drills\n1. a\n2. b\n## Next\n1. c'), 2);
});

const { countRefs } = require('../tools/content/audit/crosscheck');

test('countRefs counts every lesson reference in both forms', () => {
  assert.equal(
    countRefs([
      { id: 'a', markdown: 'see [x](#open-lesson-ds01) and [y](#open-lesson-ds01) [z](lesson:nope).' },
      { id: 'b', markdown: 'no links here' },
      { id: 'c', markdown: null },
    ]),
    3
  );
});

test('summary renders method and limits section before the owner gate', () => {
  const md = renderSummary(buildAudit(loadAuditInput(makeFixture())).summary);
  const i = md.indexOf('## Method and limits');
  assert.ok(i > 0 && i < md.indexOf('## Owner gate'));
  for (const s of [
    'as imported',
    'no-visual',
    'no-practice',
    'overstated',
    'not counted as visuals',
    'ASCII diagrams',
    "owner's call",
    'guide words plus document words',
    'code text counts as words',
    'capped at 10 per lesson',
  ]) assert.ok(md.includes(s), s);
});

test('empty results state what was checked', () => {
  const { summary } = buildAudit(loadAuditInput(makeFixture()));
  assert.equal(summary.guidesScanned, 2);
  assert.equal(summary.refsChecked, 0);
  const md = renderSummary(summary);
  assert.ok(md.includes('None found. Checked 0 lesson references in 2 guides. The importer strips .md cross-links from guides, so links in the original sources are not checked.'));
  assert.ok(md.includes('Title-only check (word-set similarity 0.85 or higher): L2 and L3'));
  assert.ok(md.includes('Topic overlap between differently titled lessons needs manual review in Phase 1.'));
  assert.ok(md.includes('## Orphan videos'));
});

test('source coverage names lessons without source', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'audit-src-'));
  const db = openDb(tmp);
  db.prepare("INSERT INTO tracks (id, name, position) VALUES ('t1', 'T', 1)").run();
  db.prepare("INSERT INTO course_blocks (id, track_id, key, title, position) VALUES (1, 't1', 'b1', 'B', 1)").run();
  const ins = db.prepare("INSERT INTO lessons (id, track_id, block_id, position, title, stars, duration, is_new) VALUES (?, 't1', 1, ?, ?, 3, '10 min', 0)");
  ['both', 'none', 'doc', 'guide'].forEach((id, i) => ins.run(id, i + 1, 'Title ' + id));
  const g = db.prepare("INSERT INTO lesson_guides (lesson_id, markdown, updated_at) VALUES (?, 'hello', 'x')");
  g.run('both'); g.run('guide');
  const d = db.prepare("INSERT INTO lesson_documents (lesson_id, schema_version, document, updated_at) VALUES (?, 1, '{\"sections\":[]}', 'x')");
  d.run('both'); d.run('doc');
  db.close();
  const { summary } = buildAudit(loadAuditInput(tmp));
  assert.deepEqual(summary.sourceSplit.noSource, ['none']);
  assert.deepEqual(summary.sourceSplit.documentOnly, ['doc']);
  assert.deepEqual(summary.sourceSplit.guideOnly, ['guide']);
  const md = renderSummary(summary);
  assert.ok(md.includes('- No source: none'));
  assert.ok(md.includes('- Document only (no guide): doc'));
  assert.ok(md.includes('- Guide only (no document): guide'));
  const empty = renderSummary(buildAudit(loadAuditInput(makeFixtureEmptyLists())).summary);
  assert.ok(empty.includes('similarity 0.85 or higher): none'));
  assert.ok(empty.includes('- Document only (no guide): none'));
});

function makeFixtureEmptyLists() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'audit-e2-'));
  openDb(tmp).close();
  return tmp;
}
