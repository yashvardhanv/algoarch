// Home-page and shell interactions: view transitions, floating header, topics menu,
// topic ticker, new-lessons deck, hero tile motion. Loaded after app.js; wraps its globals.
(function () {
  'use strict';
  const reduceMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const $ = (id) => document.getElementById(id);
  const esc = (s) => (typeof escapeHtml === 'function' ? escapeHtml(String(s ?? '')) : String(s ?? ''));

  // ------------------------------------------------------------ view transitions
  const originalSwitchView = window.switchView;
  window.switchView = function (name) {
    if (!document.startViewTransition || reduceMotion()) return originalSwitchView(name);
    document.startViewTransition(() => originalSwitchView(name));
  };

  // -------------------------------------------------------------- floating header
  const nav = document.querySelector('.navbar');
  if (nav) {
    const onScroll = () => nav.classList.toggle('is-floating', window.scrollY > 24);
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  // ------------------------------------------------------------------ topics menu
  const topicsBtn = $('btn-topics');
  const topicsMenu = $('topics-menu');

  function setTopicsOpen(open) {
    if (!topicsBtn || !topicsMenu) return;
    topicsMenu.classList.toggle('open', open);
    topicsBtn.setAttribute('aria-expanded', String(open));
  }

  window.openTrackBlock = function (trackId, blockKey) {
    state.activeTrackId = trackId;
    document.querySelectorAll('.track-pill').forEach(p => p.classList.toggle('active', p.dataset.track === trackId));
    renderCurriculumLibrary();
    switchView('library');
    if (blockKey) {
      setTimeout(() => {
        const el = document.querySelector('.block-divider[data-block="' + CSS.escape(blockKey) + '"]');
        if (el) el.scrollIntoView({ block: 'start' });
      }, 260);
    }
  };

  function renderTopicsMenu() {
    if (!topicsMenu || !state.tracks.length) return;
    topicsMenu.innerHTML = state.tracks.map(t => {
      const total = t.blocks.reduce((n, b) => n + b.lessons.length, 0);
      return '<div class="topics-col">' +
        '<button type="button" class="topics-track" data-track="' + esc(t.id) + '">' + esc(t.name) + '<small>' + total + ' lessons</small></button>' +
        '<ul>' + t.blocks.map(b =>
          '<li><button type="button" data-track="' + esc(t.id) + '" data-block="' + esc(b.k) + '">' + esc(b.t) + '<small>' + b.lessons.length + '</small></button></li>'
        ).join('') + '</ul></div>';
    }).join('');
  }

  if (topicsBtn && topicsMenu) {
    topicsBtn.addEventListener('click', (e) => { e.stopPropagation(); setTopicsOpen(!topicsMenu.classList.contains('open')); });
    topicsMenu.addEventListener('click', (e) => {
      const b = e.target.closest('button[data-track]');
      if (!b) return;
      setTopicsOpen(false);
      window.openTrackBlock(b.dataset.track, b.dataset.block || null);
    });
    document.addEventListener('click', (e) => { if (!topicsMenu.contains(e.target)) setTopicsOpen(false); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') setTopicsOpen(false); });
  }

  // ----------------------------------------------------------------- topic ticker
  function renderTicker() {
    const el = $('topic-marquee');
    if (!el || !state.allLessons.length) return;
    const seen = new Set();
    const topics = [];
    for (const l of state.allLessons.filter(x => x.stars === 5)) {
      for (const tag of l.tags || []) {
        const k = tag.toLowerCase();
        if (!seen.has(k) && tag.length <= 28) { seen.add(k); topics.push(tag); }
        if (topics.length >= 30) break;
      }
      if (topics.length >= 30) break;
    }
    if (topics.length < 6) { el.hidden = true; return; }
    const list = topics.map(t => '<li>' + esc(t) + '</li>').join('');
    el.innerHTML = '<ul class="topic-track" aria-label="Topics covered">' + list + '</ul>' +
      '<ul class="topic-track" aria-hidden="true">' + list + '</ul>';
  }

  // ------------------------------------------------------------ new-lessons deck
  let deckIdx = 0;
  const deckItems = () => {
    const fresh = state.allLessons.filter(l => l.isNew);
    return fresh.length >= 3 ? fresh : state.allLessons.filter(l => l.stars === 5).slice(0, 6);
  };

  function positionDeck() {
    const cards = document.querySelectorAll('#deck .deck-card');
    const n = cards.length;
    cards.forEach((c, i) => {
      const o = (i - deckIdx + n) % n;
      c.style.setProperty('--o', Math.min(o, 3));
      c.classList.toggle('is-top', o === 0);
      c.setAttribute('aria-hidden', String(o !== 0));
      if ('inert' in c) c.inert = o !== 0;
    });
    const count = $('deck-count');
    if (count) count.textContent = (deckIdx + 1) + ' of ' + n;
    restartRing();
  }

  function restartRing() {
    const ring = $('deck-ring');
    if (!ring) return;
    ring.classList.remove('run');
    void ring.getBoundingClientRect(); // restart the CSS animation
    if (!reduceMotion()) ring.classList.add('run');
  }

  function stepDeck(d) {
    const n = document.querySelectorAll('#deck .deck-card').length;
    if (!n) return;
    deckIdx = (deckIdx + d + n) % n;
    positionDeck();
  }

  function renderDeck() {
    const section = $('deck-section');
    const el = $('deck');
    if (!section || !el) return;
    const items = deckItems();
    if (!items.length) { section.hidden = true; return; }
    section.hidden = false;
    deckIdx = 0;
    el.innerHTML = items.map(l => {
      const track = state.tracks.find(t => t.id === l.trackId);
      return '<article class="deck-card">' +
        '<p class="deck-track">' + esc(track ? track.name : '') + '</p>' +
        '<h3>' + esc(l.title) + '</h3>' +
        '<p class="deck-desc">' + esc(l.desc || '') + '</p>' +
        '<div class="deck-tags">' + (l.tags || []).slice(0, 3).map(t => '<span>' + esc(t) + '</span>').join('') + '</div>' +
        '<button type="button" class="btn-action-primary" data-open="' + esc(l.id) + '" data-track="' + esc(l.trackId) + '">Open lesson</button>' +
        '</article>';
    }).join('');
    el.onclick = (e) => {
      const b = e.target.closest('button[data-open]');
      if (b) window.openLesson(b.dataset.open, b.dataset.track);
    };
    positionDeck();
  }

  const prev = $('deck-prev'), next = $('deck-next'), ring = $('deck-ring'), deckBox = $('deck-section');
  if (prev) prev.addEventListener('click', () => stepDeck(-1));
  if (next) next.addEventListener('click', () => stepDeck(1));
  if (ring) ring.addEventListener('animationend', () => stepDeck(1));
  if (deckBox) {
    const pause = (on) => deckBox.classList.toggle('is-paused', on);
    deckBox.addEventListener('mouseenter', () => pause(true));
    deckBox.addEventListener('mouseleave', () => pause(false));
    deckBox.addEventListener('focusin', () => pause(true));
    deckBox.addEventListener('focusout', () => pause(false));
  }

  // ------------------------------------------- pause looping motion when off-screen
  const loops = [document.querySelector('.hero-stage'), $('topic-marquee'), deckBox].filter(Boolean);
  if ('IntersectionObserver' in window) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach(en => en.target.classList.toggle('is-offscreen', !en.isIntersecting));
    });
    loops.forEach(el => io.observe(el));
  }
  document.addEventListener('visibilitychange', () => document.documentElement.classList.toggle('tab-hidden', document.hidden));

  // ------------------------------------------------- hook into app data rendering
  const originalPillars = window.renderPillarsRoadmap;
  window.renderPillarsRoadmap = function () {
    originalPillars();
    renderTopicsMenu();
    renderTicker();
    if (!document.querySelector('#deck .deck-card')) renderDeck();
  };

  const originalComplete = window.toggleCompleteLesson;
  window.toggleCompleteLesson = async function (id) {
    const r = await originalComplete(id);
    originalPillars();
    return r;
  };
})();
