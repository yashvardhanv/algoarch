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
