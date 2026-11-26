// Pathways view: loads /api/pathways, renders cards and a weekly plan. Loaded after home.js.
(function () {
  'use strict';
  const Core = window.PlannerCore;
  const View = window.PathwaysView;
  const root = document.getElementById('view-pathways');
  if (!root || !Core || !View) return;

  const $ = (id) => document.getElementById(id);
  const grid = $('pw-grid');
  const controls = $('pw-controls');
  const schedule = $('pw-schedule');
  const status = $('pw-status');
  const hoursSel = $('pw-hours');
  const weeksSel = $('pw-weeks');
  const KEY = 'algoarch.pathways';

  let pathways = null;
  let loading = false;
  let selectedId = null;

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; }
  }
  function save() {
    try {
      localStorage.setItem(KEY, JSON.stringify({ id: selectedId, hours: hoursSel.value, weeks: weeksSel.value }));
    } catch (e) { /* storage blocked: the view works without it */ }
  }

  const fullPlanner = () => can('plannerFull');
  const completed = () => (state.progress && state.progress.completed) || [];
  const lessonTitle = (id) => {
    for (const p of pathways || []) {
      const l = (p.lessons || []).find((x) => x.id === id);
      if (l) return l.title;
    }
    return id;
  };
  const current = () => pathways.find((p) => p.id === selectedId) || pathways[0];

  function renderCards() {
    const done = completed();
    const full = fullPlanner();
    grid.innerHTML = pathways.map((p) => View.cardHtml(p, Core.pathwayProgress(p, done), {
      selected: p.id === selectedId,
      locked: Core.isPathwayLocked(p, full),
    })).join('');
  }

  function renderSchedule() {
    const p = current();
    const weeks = parseInt(weeksSel.value, 10);
    const s = Core.buildSchedule(p, completed(), {
      hoursPerWeek: Core.clampHours(hoursSel.value),
      weeks: weeks > 0 ? weeks : undefined,
    });
    schedule.innerHTML = View.scheduleHtml(s, {
      completed: completed(),
      target: weeks > 0 ? weeks : null,
      totalLessons: (p.lessons || []).length,
    });
  }

  function setStatus(html) {
    status.innerHTML = html;
    status.hidden = !html;
  }

  function render() {
    if (!pathways) return;
    renderCards();
    renderSchedule();
  }

  async function fetchPathways() {
    if (loading) return;
    loading = true;
    setStatus('');
    controls.hidden = true;
    schedule.innerHTML = '';
    let list;
    try {
      const res = await fetch('/api/pathways');
      if (!res.ok) throw new Error('status ' + res.status);
      const data = await res.json();
      list = data && Array.isArray(data.pathways) ? data.pathways : null;
      if (!list) throw new Error('bad response');
    } catch (e) {
      pathways = null;
      grid.innerHTML = '';
      schedule.innerHTML = View.errorHtml('Could not load pathways. Check your connection and try again.');
      loading = false;
      return;
    }
    try {
      if (!list.length) {
        pathways = null;
        grid.innerHTML = '';
        schedule.innerHTML = View.emptyHtml('No pathways available yet.');
        return;
      }
      pathways = list;
      const saved = load();
      const hasOption = (sel, v) => v != null && [...sel.options].some((o) => o.value === String(v));
      if (saved.hours && hasOption(hoursSel, saved.hours)) hoursSel.value = String(saved.hours);
      if (hasOption(weeksSel, saved.weeks)) weeksSel.value = String(saved.weeks);
      const usable = (id) => pathways.some((p) => p.id === id) &&
        !Core.isPathwayLocked(pathways.find((p) => p.id === id), fullPlanner());
      selectedId = [saved.id, 'crash', pathways[0].id].find((id) => id && usable(id)) || pathways[0].id;
      controls.hidden = false;
      render();
    } finally {
      loading = false;
    }
  }

  function onShow() {
    setStatus('');
    if (pathways) render();
    else fetchPathways();
  }

  root.addEventListener('click', async (e) => {
    const card = e.target.closest('[data-pathway]');
    if (card) {
      const p = pathways && pathways.find((x) => x.id === card.dataset.pathway);
      if (!p) return;
      if (Core.isPathwayLocked(p, fullPlanner())) {
        if (window.openPricingModal) window.openPricingModal();
        return;
      }
      selectedId = p.id;
      setStatus('');
      save();
      render();
      const again = [...grid.querySelectorAll('[data-pathway]')].find((c) => c.dataset.pathway === p.id);
      if (again) again.focus();
      return;
    }
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const action = btn.dataset.action;
    if (action === 'retry') fetchPathways();
    else if (action === 'open') window.openLesson(btn.dataset.lesson, btn.dataset.track);
    else if (action === 'toggle') {
      btn.disabled = true;
      const id = btn.dataset.lesson;
      const wasDone = completed().includes(id);
      try { await window.toggleCompleteLesson(id); } catch (err) { console.error(err); }
      setStatus('');
      render();
      const nowDone = completed().includes(id);
      if (nowDone === wasDone) return;
      setStatus(View.statusHtml(lessonTitle(id), id, nowDone));
      status.focus();
    } else if (action === 'undo') {
      const id = btn.dataset.lesson;
      const wasDone = completed().includes(id);
      btn.disabled = true;
      try { await window.toggleCompleteLesson(id); } catch (err) { console.error(err); }
      setStatus('');
      render();
      const nowDone = completed().includes(id);
      if (nowDone === wasDone) return;
      setStatus(View.statusHtml(lessonTitle(id), id, nowDone));
      status.focus();
    }
  });

  [hoursSel, weeksSel].forEach((sel) => sel.addEventListener('change', () => { setStatus(''); save(); render(); }));

  const previous = window.switchView;
  window.switchView = function (name) {
    const r = previous(name);
    if (name === 'pathways') onShow();
    return r;
  };
})();
