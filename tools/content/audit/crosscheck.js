'use strict';

const STOP = new Set(['part', 'the', 'a', 'and', 'i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x']);

function findOrphanVideos(videos, lessonIds) {
  const out = [];
  for (const v of videos) {
    const lid = typeof v.lessonId === 'string' ? v.lessonId.trim() : '';
    if (lid && !lessonIds.has(v.lessonId) && !lessonIds.has(lid)) out.push(v.id);
  }
  return out;
}

function tokens(title) {
  const words = String(title || '').toLowerCase().replace(/[^a-z0-9\s]/g, ' ').split(/\s+/);
  return new Set(words.filter((w) => w && !/^\d+$/.test(w) && !STOP.has(w)));
}

function jaccard(a, b) {
  if (!a.size || !b.size) return 0;
  let inter = 0;
  for (const t of a) if (b.has(t)) inter++;
  return inter / (a.size + b.size - inter);
}

function findDuplicateTitles(lessons, threshold = 0.85) {
  const sets = lessons.map((l) => tokens(l.title));
  const pairs = [];
  for (let i = 0; i < lessons.length; i++) {
    for (let j = i + 1; j < lessons.length; j++) {
      if (jaccard(sets[i], sets[j]) >= threshold) pairs.push([lessons[i].id, lessons[j].id]);
    }
  }
  return pairs;
}

const REF_RE = /#open-lesson-([A-Za-z0-9_-]+)|\]\(\s*lesson:([A-Za-z0-9_-]+)/g;

function countRefs(guides) {
  let n = 0;
  for (const g of guides) {
    for (const m of String(g.markdown || '').matchAll(REF_RE)) {
      if ((m[1] || m[2]).replace(/[-_]+$/, '')) n++;
    }
  }
  return n;
}

function findBrokenRefs(guides, lessonIds) {
  const out = [];
  const re = REF_RE;
  for (const g of guides) {
    const seen = new Set();
    for (const m of String(g.markdown || '').matchAll(re)) {
      const to = (m[1] || m[2]).replace(/[-_]+$/, '');
      if (!to || lessonIds.has(to) || seen.has(to)) continue;
      seen.add(to);
      out.push({ from: g.id, to });
    }
  }
  return out;
}

module.exports = { findOrphanVideos, findDuplicateTitles, findBrokenRefs, countRefs };
