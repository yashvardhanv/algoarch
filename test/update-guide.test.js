'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { openDb } = require('../db.js');
const { updateGuide } = require('../tools/content/update-guide.js');

function fresh() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ug-'));
  const db = openDb(dir);
  db.prepare("INSERT INTO tracks (id, name, position) VALUES ('t','T',0)").run();
  db.prepare("INSERT INTO course_blocks (id, track_id, key, title, position) VALUES (1,'t','k','B',0)").run();
  return { dir, db };
}
function addLesson(db, id, md) {
  db.prepare("INSERT INTO lessons (id, track_id, block_id, title, position) VALUES (?, 't', 1, 'L', 0)").run(id);
  if (md != null) db.prepare("INSERT INTO lesson_guides (lesson_id, markdown, updated_at) VALUES (?,?,?)").run(id, md, 'x');
}

test('updateGuide replaces a guide that still equals the expected old text', () => {
  const { db } = fresh();
  addLesson(db, 'a', 'old text');
  const r = updateGuide(db, 'a', 'new text', 'old text');
  assert.equal(r.ok, true);
  assert.equal(db.prepare("SELECT markdown FROM lesson_guides WHERE lesson_id='a'").get().markdown, 'new text');
  db.close();
});

test('updateGuide ignores line-ending and outer whitespace differences when comparing', () => {
  const { db } = fresh();
  addLesson(db, 'a', 'one\ntwo');
  assert.equal(updateGuide(db, 'a', 'new', 'one\r\ntwo\r\n').ok, true);
  db.close();
});

test('updateGuide refuses when the live guide was edited, and leaves it unchanged', () => {
  const { db } = fresh();
  addLesson(db, 'a', 'edited in the CMS');
  const r = updateGuide(db, 'a', 'new text', 'old text');
  assert.equal(r.ok, false);
  assert.match(r.reason, /differs/);
  assert.equal(db.prepare("SELECT markdown FROM lesson_guides WHERE lesson_id='a'").get().markdown, 'edited in the CMS');
  db.close();
});

test('updateGuide with force overwrites an edited guide', () => {
  const { db } = fresh();
  addLesson(db, 'a', 'edited');
  assert.equal(updateGuide(db, 'a', 'new', 'old', { force: true }).ok, true);
  db.close();
});

test('updateGuide refuses an unknown lesson and creates a missing guide only for a known lesson', () => {
  const { db } = fresh();
  assert.equal(updateGuide(db, 'nope', 'x', '').ok, false);
  addLesson(db, 'b', null);
  assert.equal(updateGuide(db, 'b', 'brand new', '').ok, true);
  assert.equal(db.prepare("SELECT markdown FROM lesson_guides WHERE lesson_id='b'").get().markdown, 'brand new');
  db.close();
});

test('updateGuide refuses empty new text', () => {
  const { db } = fresh();
  addLesson(db, 'a', 'old');
  assert.equal(updateGuide(db, 'a', '   ', 'old').ok, false);
  db.close();
});
