'use strict';
(function () {
  const DEFAULT_MINUTES = 45;

  function minutesOf(duration) {
    const m = typeof duration === 'string' ? duration.match(/(\d+)\s*min/) : null;
    const n = m ? parseInt(m[1], 10) : 0;
    return n > 0 ? n : DEFAULT_MINUTES;
  }

  function clampHours(h) {
    const n = typeof h === 'string' && h.trim() === '' ? NaN : Number(h);
    if (!Number.isFinite(n)) return 10;
    return Math.min(40, Math.max(1, Math.round(n)));
  }

  function lessonsOf(pathway) {
    return pathway && Array.isArray(pathway.lessons) ? pathway.lessons : [];
  }

  function pathwayProgress(pathway, completed) {
    const doneSet = new Set(completed || []);
    const lessons = lessonsOf(pathway);
    let done = 0;
    let minutesTotal = 0;
    let minutesLeft = 0;
    let next = null;
    for (const l of lessons) {
      const m = minutesOf(l.duration);
      minutesTotal += m;
      if (doneSet.has(l.id)) done++;
      else {
        minutesLeft += m;
        if (!next) next = l;
      }
    }
    const total = lessons.length;
    return { done, total, percent: total ? Math.round((done / total) * 100) : 0, minutesTotal, minutesLeft, next };
  }

  function buildSchedule(pathway, completed, opts) {
    const o = opts || {};
    const budget = clampHours(o.hoursPerWeek) * 60;
    const doneSet = new Set(completed || []);
    const remaining = lessonsOf(pathway).filter((l) => !doneSet.has(l.id));
    const weeks = [];
    let cur = null;
    let remainingMinutes = 0;
    for (const l of remaining) {
      const m = minutesOf(l.duration);
      remainingMinutes += m;
      if (!cur || (cur.lessons.length > 0 && cur.minutes + m > budget)) {
        cur = { n: weeks.length + 1, minutes: 0, lessons: [] };
        weeks.push(cur);
      }
      cur.lessons.push(l);
      cur.minutes += m;
    }
    const target = typeof o.weeks === 'number' && o.weeks > 0 ? o.weeks : null;
    return {
      weeks,
      remainingLessons: remaining.length,
      remainingMinutes,
      weeksNeeded: weeks.length,
      fits: target === null ? true : weeks.length <= target,
      hoursNeeded: target === null ? null : Math.ceil(remainingMinutes / 60 / target),
    };
  }

  function isPathwayLocked(pathway, fullPlanner) {
    return !fullPlanner && !(pathway && pathway.id === 'crash');
  }

  const api = { minutesOf, clampHours, pathwayProgress, buildSchedule, isPathwayLocked };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else window.PlannerCore = api;
})();
