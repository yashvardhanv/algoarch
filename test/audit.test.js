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
