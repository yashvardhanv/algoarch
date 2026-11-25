'use strict';

const fs = require('node:fs');
const path = require('node:path');
const Database = require('better-sqlite3');
const { guideStats, documentStats } = require('./metrics');
const { flagLesson, countDrills, hasPitfall } = require('./flags');
const { findOrphanVideos, findDuplicateTitles, findBrokenRefs } = require('./crosscheck');

const COLUMNS = [
  'id', 'track', 'block', 'title', 'stars', 'declared_duration', 'words', 'headings', 'code_blocks',
  'code_cells', 'cells_with_tests', 'widgets', 'widgets_ported', 'quizzes', 'checklists', 'visuals',
  'drills', 'videos_linked', 'has_source', 'is_new', 'flags', 'manual_flags',
];

const OWNER_DECISIONS = [
  'Is the source split (lessons with versus without a guide or document) acceptable?',
  'What are the course sizes after the redesign?',
  'Three.js or Babylon.js for 3D scenes?',
];

function loadAuditInput(dataDir) {
  const file = path.join(dataDir, 'algoarch.db');
  if (!fs.existsSync(file)) throw new Error('Database not found: ' + file);
  const db = new Database(file, { readonly: true });
  try {
    const lessons = db.prepare(`
      SELECT l.id, l.title, l.stars, l.duration, l.is_new,
             t.id AS track, t.name AS track_name, b.title AS block,
             g.markdown AS markdown, d.document AS document,
             g.lesson_id IS NOT NULL AS has_guide, d.lesson_id IS NOT NULL AS has_document,
             EXISTS(SELECT 1 FROM lesson_labs x WHERE x.lesson_id = l.id) AS has_lab
      FROM lessons l
      JOIN tracks t ON t.id = l.track_id
      JOIN course_blocks b ON b.id = l.block_id
      LEFT JOIN lesson_guides g ON g.lesson_id = l.id
      LEFT JOIN lesson_documents d ON d.lesson_id = l.id
      ORDER BY t.position, b.position, l.position`).all().map((r) => {
      let document = null;
      let badDocument = false;
      if (r.has_document) {
        try {
          document = JSON.parse(r.document);
        } catch (e) {
          document = null;
        }
        if (!document || !Array.isArray(document.sections)) {
          document = null;
          badDocument = true;
        }
      }
      return {
        id: r.id, track: r.track, trackName: r.track_name, block: r.block, title: r.title,
        stars: r.stars, duration: r.duration, isNew: !!r.is_new,
        hasGuide: !!r.has_guide, hasDocument: !!r.has_document, hasLab: !!r.has_lab,
        markdown: r.has_guide ? r.markdown : null, document, badDocument,
      };
    });
    const videos = db.prepare('SELECT id, lesson_id FROM videos ORDER BY position, pk').all()
      .map((v) => ({ id: v.id, lessonId: v.lesson_id }));
    const guides = lessons.filter((l) => l.hasGuide).map((l) => ({ id: l.id, markdown: l.markdown }));
    return { lessons, videos, guides };
  } finally {
    db.close();
  }
}

function buildAudit(input) {
  const { lessons, videos, guides } = input;
  const linked = new Map();
  for (const v of videos) linked.set(v.lessonId, (linked.get(v.lessonId) || 0) + 1);

  const byTrack = {};
  const byFlag = {};
  const sourceSplit = { withSource: 0, withoutSource: 0, newLessons: 0 };
  let totalWords = 0;

  const rows = lessons.map((l) => {
    const g = guideStats(l.markdown);
    const d = documentStats(l.badDocument ? null : l.document);
    const drills = countDrills(l.markdown);
    const flags = flagLesson({
      guide: g, doc: d, drills, badDocument: l.badDocument,
      guidePitfall: hasPitfall(l.markdown), docPitfall: hasPitfall(d.text),
    });
    const hasSource = l.hasGuide || l.hasDocument;
    const words = g.words + d.words;
    const row = {
      id: l.id, track: l.track, block: l.block, title: l.title, stars: l.stars,
      declared_duration: l.duration || '', words, headings: g.headings + d.headings,
      code_blocks: g.codeBlocks + d.codeBlocks, code_cells: d.codeCells,
      cells_with_tests: d.cellsWithTests, widgets: d.widgets, widgets_ported: d.widgetsPorted,
      quizzes: d.quizzes, checklists: d.checklists, visuals: d.visuals,
      drills, videos_linked: linked.get(l.id) || 0,
      has_source: String(hasSource), is_new: String(l.isNew),
      flags: flags.join(';'), manual_flags: '',
    };
    const t = byTrack[l.track] || (byTrack[l.track] = { name: l.trackName, lessons: 0, words: 0 });
    t.lessons += 1;
    t.words += words;
    for (const f of flags) {
      const bf = byFlag[f] || (byFlag[f] = {});
      bf[l.track] = (bf[l.track] || 0) + 1;
    }
    if (hasSource) sourceSplit.withSource += 1; else sourceSplit.withoutSource += 1;
    if (l.isNew) sourceSplit.newLessons += 1;
    totalWords += words;
    return row;
  });

  const ids = new Set(lessons.map((l) => l.id));
  const summary = {
    totals: { lessons: lessons.length, words: totalWords },
    byTrack,
    byFlag,
    sourceSplit,
    orphanVideos: findOrphanVideos(videos, ids),
    duplicateTitles: findDuplicateTitles(lessons.map((l) => ({ id: l.id, title: l.title }))),
    brokenRefs: findBrokenRefs(guides, ids),
  };
  return { rows, summary };
}

function csvField(v) {
  const s = String(v == null ? '' : v);
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

function toCsv(rows) {
  const lines = [COLUMNS.join(',')];
  for (const r of rows) lines.push(COLUMNS.map((c) => csvField(r[c])).join(','));
  return lines.join('\n') + '\n';
}

function renderSummary(summary) {
  const out = ['# Curriculum audit', ''];
  const none = (arr) => (arr.length ? arr : ['None']);

  out.push('## Totals', '', `- Lessons: ${summary.totals.lessons}`, `- Total words: ${summary.totals.words}`, '');
  const tracks = Object.keys(summary.byTrack);
  if (tracks.length) {
    out.push('| Course | Lessons | Words |', '| --- | ---: | ---: |');
    for (const id of tracks) {
      const t = summary.byTrack[id];
      out.push(`| ${t.name || id} | ${t.lessons} | ${t.words} |`);
    }
    out.push('');
  }

  out.push('## Flags by course', '');
  const flags = Object.keys(summary.byFlag).sort();
  if (flags.length) {
    out.push(`| Flag | ${tracks.join(' | ')} | Total |`, `| --- | ${tracks.map(() => '---:').join(' | ')} | ---: |`);
    for (const f of flags) {
      const counts = tracks.map((t) => summary.byFlag[f][t] || 0);
      out.push(`| ${f} | ${counts.join(' | ')} | ${counts.reduce((a, b) => a + b, 0)} |`);
    }
  } else out.push('None');
  out.push('');

  const s = summary.sourceSplit;
  out.push('## Source coverage', '', `- With source: ${s.withSource}`, `- Without source: ${s.withoutSource}`, `- New lessons: ${s.newLessons}`, '');

  out.push('## Orphan videos', '', ...none(summary.orphanVideos.map((id) => `- ${id}`)), '');
  out.push('## Duplicate topics', '', ...none(summary.duplicateTitles.map((p) => `- ${p[0]} and ${p[1]}`)), '');
  out.push('## Broken cross-references', '', ...none(summary.brokenRefs.map((r) => `- ${r.from} links to missing ${r.to}`)), '');
  out.push('## Owner gate', '', ...OWNER_DECISIONS.map((d) => `- ${d}`), '');
  return out.join('\n');
}

module.exports = { loadAuditInput, buildAudit, toCsv, renderSummary, COLUMNS };
