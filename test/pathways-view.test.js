'use strict';
const test = require('node:test');
const assert = require('node:assert');
const V = require('../public/pathways-view.js');
const { findCompClaims } = require('../tools/content/comp-lint.js');

const pw = { id: 'crash', title: 'Crash', description: 'Fast path', lessons: [{ id: 'a' }, { id: 'b' }, { id: 'c' }] };
const prog = { done: 1, total: 3, percent: 33, minutesTotal: 180, minutesLeft: 120, next: { id: 'b' } };
const sched = {
  weeks: [
    { n: 1, minutes: 90, lessons: [{ id: 'a', title: 'A <b>', trackId: 't1', duration: '45 min' }, { id: 'b', title: 'B', trackId: 't1', duration: '45 min' }] },
    { n: 2, minutes: 45, lessons: [{ id: 'c', title: 'C', trackId: 't2', duration: '45 min' }] },
  ],
  remainingLessons: 3, remainingMinutes: 135, weeksNeeded: 2, fits: true, hoursNeeded: null,
};

test('esc escapes the five characters and tolerates null', () => {
  assert.strictEqual(V.esc(`&<>"'`), '&amp;&lt;&gt;&quot;&#39;');
  assert.strictEqual(V.esc(null), '');
  assert.strictEqual(V.esc(undefined), '');
});

test('cardHtml escapes the title and description', () => {
  const h = V.cardHtml({ ...pw, title: '<img src=x onerror=1>', description: '<script>' }, prog, {});
  assert.ok(h.includes('&lt;img'));
  assert.ok(!h.includes('<img'));
  assert.ok(!h.includes('<script>'));
});

test('cardHtml marks selected and locked states', () => {
  const s = V.cardHtml(pw, prog, { selected: true });
  assert.ok(s.includes('is-selected') && s.includes('aria-pressed="true"'));
  const l = V.cardHtml(pw, prog, { locked: true });
  assert.ok(l.includes('is-locked') && l.includes('Pro'));
  const n = V.cardHtml(pw, prog, {});
  assert.ok(!n.includes('is-selected') && !n.includes('is-locked'));
});

test('cardHtml shows progress', () => {
  const h = V.cardHtml(pw, prog, {});
  assert.ok(h.includes('role="progressbar"') && h.includes('aria-valuenow="33"'));
  assert.ok(h.includes('data-pathway="crash"'));
});

test('scheduleHtml renders one section per week with open and toggle buttons per lesson', () => {
  const h = V.scheduleHtml(sched, { completed: [], target: null });
  assert.strictEqual((h.match(/<section class="pw-week"/g) || []).length, 2);
  assert.strictEqual((h.match(/data-action="open"/g) || []).length, 3);
  assert.strictEqual((h.match(/data-action="toggle"/g) || []).length, 3);
  assert.ok(h.includes('Week 1') && h.includes('data-track="t2"'));
  assert.ok(h.includes('A &lt;b&gt;'));
});

test('scheduleHtml has no inline handlers or styles', () => {
  const h = V.scheduleHtml(sched, { completed: ['a'], target: 4 }) + V.cardHtml(pw, prog, { locked: true }) + V.errorHtml('x');
  assert.ok(!/\sonclick=/i.test(h));
  assert.ok(!/\sstyle=/i.test(h));
});

test('scheduleHtml says when the plan does not fit', () => {
  const h = V.scheduleHtml({ ...sched, fits: false, hoursNeeded: 5 }, { completed: [], target: 2 });
  assert.ok(h.includes('5 hours a week'));
});

test('scheduleHtml renders a finished state when no weeks remain', () => {
  const h = V.scheduleHtml({ weeks: [], remainingLessons: 0, remainingMinutes: 0, weeksNeeded: 0, fits: true, hoursNeeded: null }, { completed: [], target: null });
  assert.ok(h.includes('Pathway complete'));
  assert.ok(!h.includes('pw-week'));
});

test('errorHtml has a retry button and escapes the message', () => {
  const h = V.errorHtml('<b>bad</b>');
  assert.ok(h.includes('data-action="retry"') && h.includes('Retry'));
  assert.ok(h.includes('&lt;b&gt;') && !h.includes('<b>bad'));
});

test('no output contains compensation figures', () => {
  const outs = [V.cardHtml(pw, prog, { locked: true, selected: true }), V.scheduleHtml(sched, { completed: ['a'], target: 1 }),
    V.scheduleHtml({ ...sched, fits: false, hoursNeeded: 9 }, { completed: [], target: 1 }), V.errorHtml('Could not load')];
  for (const o of outs) assert.deepStrictEqual(findCompClaims(o), []);
});

test('cardHtml bar never shows 98% as full or 1% as empty', () => {
  const at = (percent) => V.cardHtml(pw, { ...prog, percent }, {});
  assert.ok(at(98).includes('pw-w-95') && at(98).includes('aria-valuenow="98"'));
  assert.ok(at(1).includes('pw-w-5') && at(1).includes('aria-valuenow="1"'));
  assert.ok(at(100).includes('pw-w-100'));
  assert.ok(at(0).includes('pw-w-0"'));
  assert.ok(at(NaN).includes('aria-valuenow="0"'));
  assert.ok(at(33.4).includes('aria-valuenow="33"'));
});

test('statusHtml escapes the title and offers undo only when asked', () => {
  const h = V.statusHtml('<b>x</b>', 'l"1', true);
  assert.ok(h.includes('Marked done: &lt;b&gt;x&lt;/b&gt;.'));
  assert.ok(h.includes('data-action="undo"') && h.includes('data-lesson="l&quot;1"'));
  assert.ok(!h.includes('<b>') && !/\bon\w+=/.test(h) && !h.includes('style='));
  const u = V.statusHtml('T', 'l1', false);
  assert.ok(u.includes('Marked not done: T.') && !u.includes('data-action'));
});
