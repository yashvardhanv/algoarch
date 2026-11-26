'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const core = require('../public/planner-core.js');
const { minutesOf, clampHours, pathwayProgress, buildSchedule, isPathwayLocked } = core;

const lesson = (id, min) => ({ id, title: id, trackId: 't', duration: min + ' min' });
const pathway = (...ls) => ({ id: 'p', title: 'P', description: '', kind: 'x', minutes: 0, lessons: ls });
const ids = (week) => week.lessons.map((l) => l.id);

test('minutesOf reads "45 min", falls back to 45', () => {
  assert.equal(minutesOf('50 min'), 50);
  assert.equal(minutesOf(''), 45);
  assert.equal(minutesOf(undefined), 45);
  assert.equal(minutesOf('0 min'), 45);
});

test('minutesOf agrees with parseMinutes on data/pathways.json', () => {
  const { parseMinutes } = require('../curriculum');
  const raw = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'pathways.json'), 'utf8'));
  const durations = ['25 min', '45 min drill', '90 min'];
  for (const p of raw.pathways) for (const l of p.lessons) if (l.duration) durations.push(l.duration);
  for (const d of durations) {
    if (typeof d === 'string' && d.includes('min')) assert.equal(minutesOf(d), parseMinutes(d), d);
  }
});

test('clampHours', () => {
  assert.equal(clampHours(0), 1);
  assert.equal(clampHours(-5), 1);
  assert.equal(clampHours(''), 10);
  assert.equal(clampHours(NaN), 10);
  assert.equal(clampHours(1000), 40);
  assert.equal(clampHours('12'), 12);
  assert.equal(clampHours(7.6), 8);
});

test('pathwayProgress ignores completed ids outside the pathway', () => {
  const p = pathwayProgress(pathway(lesson('a', 10), lesson('b', 10), lesson('c', 10)), ['a', 'zzz']);
  assert.equal(p.done, 1);
  assert.equal(p.total, 3);
  assert.equal(p.percent, 33);
  assert.equal(p.next.id, 'b');
  assert.equal(p.minutesLeft, 20);
});

test('pathwayProgress on a finished pathway', () => {
  const p = pathwayProgress(pathway(lesson('a', 10), lesson('b', 10)), ['a', 'b']);
  assert.equal(p.next, null);
  assert.equal(p.percent, 100);
  assert.equal(p.minutesLeft, 0);
});

test('pathwayProgress on an empty pathway', () => {
  const p = pathwayProgress(pathway(), []);
  assert.equal(p.percent, 0);
  assert.equal(p.next, null);
});

test('buildSchedule packs in pathway order within the weekly budget', () => {
  const s = buildSchedule(pathway(lesson('a', 60), lesson('b', 60), lesson('c', 60)), [], { hoursPerWeek: 2 });
  assert.deepEqual(s.weeks.map(ids), [['a', 'b'], ['c']]);
  assert.equal(s.weeksNeeded, 2);
  assert.equal(s.weeks[0].n, 1);
  assert.equal(s.weeks[0].minutes, 120);
});

test('buildSchedule skips completed lessons', () => {
  const s = buildSchedule(pathway(lesson('a', 60), lesson('b', 60), lesson('c', 60)), ['a'], { hoursPerWeek: 2 });
  assert.deepEqual(s.weeks.map(ids), [['b', 'c']]);
  assert.equal(s.remainingLessons, 2);
  assert.equal(s.remainingMinutes, 120);
});

test('buildSchedule gives an oversize lesson its own week', () => {
  const s = buildSchedule(pathway(lesson('big', 200)), [], { hoursPerWeek: 1 });
  assert.equal(s.weeks.length, 1);
  assert.deepEqual(ids(s.weeks[0]), ['big']);
  assert.equal(s.weeks[0].minutes, 200);
});

test('buildSchedule reports fit against a target', () => {
  const p = pathway(...Array.from({ length: 10 }, (_, i) => lesson('l' + i, 60)));
  const a = buildSchedule(p, [], { hoursPerWeek: 10, weeks: 2 });
  assert.equal(a.hoursNeeded, 5);
  assert.equal(a.fits, true);
  const b = buildSchedule(p, [], { hoursPerWeek: 2, weeks: 2 });
  assert.equal(b.fits, false);
  const c = buildSchedule(p, [], { hoursPerWeek: 2 });
  assert.equal(c.fits, true);
  assert.equal(c.hoursNeeded, null);
});

test('buildSchedule with nothing left', () => {
  const s = buildSchedule(pathway(lesson('a', 10)), ['a'], { hoursPerWeek: 5, weeks: 3 });
  assert.deepEqual(s.weeks, []);
  assert.equal(s.weeksNeeded, 0);
  assert.equal(s.fits, true);
});

test('isPathwayLocked', () => {
  assert.equal(isPathwayLocked({ id: 'crash' }, false), false);
  assert.equal(isPathwayLocked({ id: 'deep' }, false), true);
  assert.equal(isPathwayLocked({ id: 'deep' }, true), false);
});
