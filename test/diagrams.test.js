// Lesson diagrams: Excalidraw conversion, validation, storage that survives re-imports,
// and splicing into the lesson document at the right place.
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { openDb, createRepo } = require('../db');
const { fromExcalidraw } = require('../tools/content/excalidraw');

let dir, db, repo;
before(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'algoarch-dg-'));
  db = openDb(dir);
  repo = createRepo(db);
  db.prepare("INSERT INTO tracks (id, name, position) VALUES ('t', 'T', 0)").run();
  const bid = db.prepare("INSERT INTO course_blocks (track_id, key, title, position) VALUES ('t', 'k', 'B', 0)").run().lastInsertRowid;
  db.prepare("INSERT INTO lessons (id, track_id, block_id, position, title) VALUES ('l1', 't', ?, 0, 'Lesson one')").run(bid);
  const doc = { title: 'Lesson one', lede: [], sections: [{ anchor: 's1', number: '01', title: 'Sec', subtitle: null, blocks: [
    { type: 'paragraph', content: ['zero'] }, { type: 'paragraph', content: ['one'] }, { type: 'paragraph', content: ['two'] }] }] };
  db.prepare("INSERT INTO lesson_documents (lesson_id, schema_version, document, updated_at) VALUES ('l1', 1, ?, 'now')").run(JSON.stringify(doc));
});
after(() => { db.close(); fs.rmSync(dir, { recursive: true, force: true }); });

const SAMPLE = [
  { type: 'cameraUpdate', width: 800, height: 600, x: 0, y: 0 },
  { type: 'rectangle', id: 'a', x: 100, y: 100, width: 160, height: 70, backgroundColor: '#a5d8ff', strokeColor: '#4a9eed', label: { text: 'Index\n(key, ctid)', fontSize: 20 }, step: 1 },
  { type: 'rectangle', id: 'b', x: 400, y: 100, width: 160, height: 70, backgroundColor: '#ffd8a8', label: { text: 'Heap' }, strokeStyle: 'dashed', step: 2 },
  { type: 'arrow', id: 'c', x: 260, y: 135, width: 140, height: 0, points: [[0, 0], [140, 0]], endArrowhead: 'arrow', label: { text: 'ctid' } },
  { type: 'text', id: 'd', x: 100, y: 200, text: 'one hop', fontSize: 16 },
  { type: 'rectangle', id: 'gone', x: 0, y: 0, width: 10, height: 10 },
  { type: 'delete', ids: 'gone' }
];

test('Excalidraw elements convert to a theme-neutral scene', () => {
  const s = fromExcalidraw(SAMPLE);
  assert.equal(s.v, 1);
  assert.equal(s.elements.length, 4, 'camera and deleted elements are dropped');
  const a = s.elements.find(e => e.id === 'a');
  assert.deepEqual([a.k, a.tone, a.fill, a.label, a.step], ['box', 'cool', true, 'Index\n(key, ctid)', 1]);
  assert.equal(s.elements.find(e => e.id === 'b').tone, 'warn');
  assert.equal(s.elements.find(e => e.id === 'b').dashed, true);
  const arrow = s.elements.find(e => e.k === 'arrow');
  assert.equal(arrow.pts.length, 2);
  assert.equal(arrow.label, 'ctid');
  assert.ok(!JSON.stringify(s).includes('#'), 'no raw colours leak into stored data');
  assert.ok(s.elements.every(e => (e.x ?? e.pts[0][0]) >= 0), 'translated into positive space');
});

test('scenes are validated before they are stored', () => {
  const scene = fromExcalidraw(SAMPLE);
  assert.throws(() => repo.saveDiagram({ lessonId: 'nope', sectionAnchor: 's1', scene }), /Unknown lesson/);
  assert.throws(() => repo.saveDiagram({ lessonId: 'l1', sectionAnchor: 's1', scene: { v: 1, width: 10, height: 10, elements: [{ id: 'x', k: 'script', x: 0, y: 0 }] } }), /Unknown element kind/);
  assert.throws(() => repo.saveDiagram({ lessonId: 'l1', sectionAnchor: 's1', scene: { v: 1, width: 10, height: 10, elements: [{ id: 'x', k: 'box', tone: 'red', x: 0, y: 0 }] } }), /Unknown tone/);
  assert.throws(() => repo.saveDiagram({ lessonId: 'l1', sectionAnchor: 's1', scene: { v: 2, elements: [] } }), /Scene must be/);
});

test('a stored diagram appears in the lesson at its insertion point, and slugs upsert', () => {
  const scene = fromExcalidraw(SAMPLE);
  const { id } = repo.saveDiagram({ slug: 'one', lessonId: 'l1', sectionAnchor: 's1', afterBlock: 0, title: 'T', caption: 'C', scene });
  const again = repo.saveDiagram({ slug: 'one', lessonId: 'l1', sectionAnchor: 's1', afterBlock: 0, title: 'T2', caption: 'C', scene });
  assert.equal(again.id, id, 'same slug updates in place');
  const blocks = repo.getLesson('l1').document.sections[0].blocks;
  assert.deepEqual(blocks.map(b => b.type), ['paragraph', 'diagram', 'paragraph', 'paragraph']);
  assert.equal(blocks[1].title, 'T2');
  assert.equal(blocks[1].scene.elements.length, 4);
});

test('diagrams survive a lesson re-import and feed the mentor text', () => {
  // the importer wipes tracks (cascading to lessons) and rebuilds them; diagrams live outside that
  db.exec('DELETE FROM course_blocks; DELETE FROM tracks;');
  assert.equal(repo.listDiagrams('l1').length, 1);
  assert.ok(repo.getDiagramsText('l1')[0].includes('Index'), 'labels are available to ground the mentor');
  assert.equal(repo.deleteDiagram(repo.listDiagrams('l1')[0].id), true);
  assert.equal(repo.listDiagrams('l1').length, 0);
});
