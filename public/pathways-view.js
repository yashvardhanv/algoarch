'use strict';
(function () {
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function hoursText(minutes) {
    const h = Math.round((minutes || 0) / 60);
    return h + (h === 1 ? ' hour' : ' hours');
  }

  function plural(n, one, many) { return n + ' ' + (n === 1 ? one : many); }

  function cardHtml(pathway, progress, opts) {
    const o = opts || {};
    const p = progress || { done: 0, total: 0, percent: 0, minutesTotal: 0 };
    const total = p.total || 0;
    const cls = 'pw-card' + (o.selected ? ' is-selected' : '') + (o.locked ? ' is-locked' : '');
    const pressed = o.selected ? ' aria-pressed="true"' : ' aria-pressed="false"';
    const pro = o.locked ? '<span class="pw-pro">Pro</span>' : '';
    const pct = Math.max(0, Math.min(100, p.percent || 0));
    return '<button type="button" class="' + cls + '" data-pathway="' + esc(pathway && pathway.id) + '"' + pressed + '>' +
      '<span class="pw-card-head"><span class="pw-card-title">' + esc(pathway && pathway.title) + '</span>' + pro + '</span>' +
      '<span class="pw-card-desc">' + esc(pathway && pathway.description) + '</span>' +
      '<span class="pw-card-meta">' + plural(total, 'lesson', 'lessons') + ' · ' + hoursText(p.minutesTotal) + '</span>' +
      '<span class="pw-bar" role="progressbar" aria-label="Progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + pct + '">' +
      '<span class="pw-bar-fill pw-w-' + (Math.round(pct / 5) * 5) + '"></span></span>' +
      '<span class="pw-card-progress">' + p.done + ' of ' + total + ' done</span>' +
      '</button>';
  }

  function lessonHtml(l, doneSet) {
    const done = doneSet.has(l.id);
    const id = esc(l.id);
    const mins = typeof l.duration === 'string' && l.duration ? '<span class="pw-lesson-dur">' + esc(l.duration) + '</span>' : '';
    return '<li class="pw-lesson' + (done ? ' is-done' : '') + '">' +
      '<button type="button" class="pw-check" data-action="toggle" data-lesson="' + id + '" aria-pressed="' + (done ? 'true' : 'false') +
      '" aria-label="' + (done ? 'Mark not done: ' : 'Mark done: ') + esc(l.title) + '"></button>' +
      '<button type="button" class="pw-open" data-action="open" data-lesson="' + id + '" data-track="' + esc(l.trackId) + '">' +
      '<span class="pw-lesson-title">' + esc(l.title) + '</span>' + mins + '</button></li>';
  }

  function scheduleHtml(schedule, opts) {
    const o = opts || {};
    const s = schedule || { weeks: [] };
    if (!s.weeks || s.weeks.length === 0) {
      return '<div class="pw-empty"><strong>Pathway complete</strong><p>Every lesson in this pathway is marked done.</p></div>';
    }
    const doneSet = new Set(o.completed || []);
    let summary = plural(s.remainingLessons, 'lesson', 'lessons') + ' left, about ' + hoursText(s.remainingMinutes) +
      ', ' + plural(s.weeksNeeded, 'week', 'weeks') + ' at this pace.';
    if (o.target && s.fits === false && s.hoursNeeded) {
      summary += ' To finish in ' + plural(o.target, 'week', 'weeks') + ', plan ' + s.hoursNeeded + ' hours a week.';
    }
    const weeks = s.weeks.map((w) =>
      '<section class="pw-week"><h3 class="pw-week-title">Week ' + esc(w.n) + '<span class="pw-week-hours">' + hoursText(w.minutes) + '</span></h3>' +
      '<ul class="pw-lessons">' + w.lessons.map((l) => lessonHtml(l, doneSet)).join('') + '</ul></section>'
    ).join('');
    return '<p class="pw-summary">' + esc(summary) + '</p>' + weeks;
  }

  function errorHtml(message) {
    return '<div class="pw-error" role="alert"><p>' + esc(message) + '</p><button type="button" class="pw-retry" data-action="retry">Retry</button></div>';
  }

  const api = { esc, cardHtml, scheduleHtml, errorHtml };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else window.PathwaysView = api;
})();
