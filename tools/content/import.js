#!/usr/bin/env node
// One-off content import: curriculum.json + lesson markdown + lesson HTML pages + labs +
// videos + resources  ->  SQLite. After this runs, the source HTML files are no longer needed
// at runtime and can be archived.
//
// Usage: node tools/content/import.js [--projects <dir>] [--data <dir>] [--reset]
const fs = require('fs');
const path = require('path');
const { openDb } = require('../../db');
const { convertPage } = require('./convert');

const args = process.argv.slice(2);
const opt = (name, def) => { const i = args.indexOf('--' + name); return i >= 0 ? args[i + 1] : def; };
const ROOT = path.join(__dirname, '..', '..');
const DATA_DIR = path.resolve(opt('data', process.env.ALGOARCH_DATA_DIR || path.join(ROOT, 'data')));
const PROJECTS = path.resolve(opt('projects', 'C:\\YASH\\CODES\\YASHVARDHAN_FAANG\\AI-System_design_DSA\\PROJECTS'));

function sanitizeMarkdown(raw) {
  if (!raw) return '';
  return raw
    .replace(/^>\s*\*\*Prereq:\*\*.*$/gim, '').replace(/^>\s*\*\*Visual:\*\*.*$/gim, '')
    .replace(/^>\s*\*\*Repairs:\*\*.*$/gim, '').replace(/^>\s*\*\*Standing companion:\*\*.*$/gim, '')
    .replace(/\[([^\]]+)\]\(\.\.\/visuals\/[^)]+\)/gi, '$1').replace(/\[([^\]]+)\]\(visuals\/[^)]+\)/gi, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\.md\)/gi, '$1').replace(/^>\s*\n/gm, '').replace(/\n{3,}/g, '\n\n').trim();
}

// Recorded panel states from the original pages (see capture-driver.js); optional.
const capIdx = args.indexOf('--capture');
const CAPTURE_DIR = capIdx >= 0 ? path.resolve(args[capIdx + 1]) : path.join(DATA_DIR, 'capture');
const readIf = (p) => (p && fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : null);

// Replace both pathway tables from data/pathways.json. Validates before any write.
function importPathways(db, pathwaysJson, lessonIds) {
  const valid = new Set(lessonIds);
  const pathways = (pathwaysJson && pathwaysJson.pathways) || [];
  for (const p of pathways) {
    for (const l of p.lessons || []) {
      if (!valid.has(l.id)) throw new Error(`pathway ${p.id} references unknown lesson ${l.id}`);
    }
  }
  const insPathway = db.prepare('INSERT INTO pathways (id, title, description, kind, position) VALUES (?,?,?,?,?)');
  const insPL = db.prepare('INSERT INTO pathway_lessons (pathway_id, lesson_id, position, note) VALUES (?,?,?,?)');
  db.transaction(() => {
    db.exec('DELETE FROM pathways; DELETE FROM pathway_lessons;');
    pathways.forEach((p, i) => {
      insPathway.run(p.id, p.title, p.description || null, p.kind, i);
      (p.lessons || []).forEach((l, j) => insPL.run(p.id, l.id, j, l.note || null));
    });
  })();
}

function main() {
  if (args.includes('--reset')) {
    for (const f of ['algoarch.db', 'algoarch.db-wal', 'algoarch.db-shm']) fs.rmSync(path.join(DATA_DIR, f), { force: true });
  }
  const db = openDb(DATA_DIR);
  const curriculum = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'curriculum.json'), 'utf8'));
  const videos = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'videos.json'), 'utf8'));
  const resources = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'resources.json'), 'utf8'));
  const now = new Date().toISOString();
  const report = { tracks: 0, lessons: 0, guides: 0, documents: 0, labs: 0, videos: 0, resources: 0, missingGuides: [], missingPages: [], widgets: {}, dropped: {} };

  const insTrack = db.prepare('INSERT OR REPLACE INTO tracks (id, name, short_name, badge, description, color, position) VALUES (?,?,?,?,?,?,?)');
  const insBlock = db.prepare('INSERT INTO course_blocks (track_id, key, title, position) VALUES (?,?,?,?)');
  const insLesson = db.prepare(`INSERT OR REPLACE INTO lessons (id, track_id, block_id, position, num, title, stars, description, duration, is_new, tags, companies, lab_file, prereqs, objectives, sources, level, reviewed_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`);
  const insGuide = db.prepare('INSERT OR REPLACE INTO lesson_guides (lesson_id, markdown, updated_at) VALUES (?,?,?)');
  const insDoc = db.prepare('INSERT OR REPLACE INTO lesson_documents (lesson_id, schema_version, document, updated_at) VALUES (?,?,?,?)');
  const insLab = db.prepare('INSERT OR REPLACE INTO lesson_labs (lesson_id, file_name, code) VALUES (?,?,?)');
  const insVideo = db.prepare('INSERT OR REPLACE INTO videos (id, youtube_id, track_id, lesson_id, title, channel, duration, category, description, thumbnail, position) VALUES (?,?,?,?,?,?,?,?,?,?,?)');
  const insRes = db.prepare('INSERT OR REPLACE INTO track_resources (track_id, kind, position, data) VALUES (?,?,?,?)');

  db.transaction(() => {
    db.exec('DELETE FROM course_blocks; DELETE FROM tracks; DELETE FROM videos; DELETE FROM track_resources;');
    curriculum.tracks.forEach((t, ti) => {
      insTrack.run(t.id, t.name, t.shortName || null, t.badge || null, t.description || null, t.color || null, ti);
      report.tracks++;
      t.blocks.forEach((b, bi) => {
        const blockId = insBlock.run(t.id, b.k, b.t, bi).lastInsertRowid;
        b.lessons.forEach((l, li) => {
          insLesson.run(l.id, t.id, blockId, li, l.n || null, l.title, l.stars ?? 5, l.desc || null, l.duration || null, l.isNew ? 1 : 0,
            JSON.stringify(l.tags || []), JSON.stringify(l.companies || []), l.lab || null,
            JSON.stringify(l.prereqs || []), JSON.stringify(l.objectives || []), JSON.stringify(l.sources || []), l.level || null, l.reviewedAt || null);
          report.lessons++;

          const mdPath = l.isNew && l.newPath ? path.join(DATA_DIR, l.newPath) : l.existingPath ? path.join(PROJECTS, l.existingPath) : null;
          const md = readIf(mdPath);
          if (md != null) { insGuide.run(l.id, sanitizeMarkdown(md), now); report.guides++; } else report.missingGuides.push(l.id);

          if (l.visualPath) {
            const html = readIf(path.join(PROJECTS, l.visualPath));
            if (html == null) report.missingPages.push(l.id);
            else {
              const capName = l.visualPath.replace(/\\/g, '/').replace(/\//g, '__').replace(/\.html$/, '');
              const capRaw = readIf(path.join(CAPTURE_DIR, capName + '.json'));
              const doc = convertPage(html, capRaw ? JSON.parse(capRaw) : null);
              const { stats, ...payload } = doc;
              insDoc.run(l.id, doc.schemaVersion, JSON.stringify(payload), now);
              report.documents++;
              for (const [k, v] of Object.entries(stats.widgets)) report.widgets[k] = (report.widgets[k] || 0) + v;
              for (const [k, v] of Object.entries(stats.dropped)) report.dropped[k] = (report.dropped[k] || 0) + v;
            }
          }
          if (l.lab) {
            const code = readIf(path.join(PROJECTS, 'ai-master-prep', 'labs', l.lab));
            if (code != null) { insLab.run(l.id, l.lab, code); report.labs++; }
          }
        });
      });
    });
    videos.forEach((v, i) => {
      insVideo.run(String(v.id), v.youtubeId, v.track || null, v.lessonLink || null, v.title, v.channel || null, v.duration || null, v.category || null, v.description || null, v.thumbnail || null, i);
      report.videos++;
    });
    for (const [trackId, r] of Object.entries(resources)) {
      (r.defaultArticles || []).forEach((a, i) => { insRes.run(trackId, 'article', i, JSON.stringify(a)); report.resources++; });
      (r.defaultRepos || []).forEach((a, i) => { insRes.run(trackId, 'repo', i, JSON.stringify(a)); report.resources++; });
    }
    const pathwaysFile = path.join(DATA_DIR, 'pathways.json');
    if (fs.existsSync(pathwaysFile)) {
      const lessonIds = curriculum.tracks.flatMap(t => t.blocks.flatMap(b => b.lessons.map(l => l.id)));
      importPathways(db, JSON.parse(fs.readFileSync(pathwaysFile, 'utf8')), lessonIds);
    }
  })();

  console.log(JSON.stringify(report, null, 2));
  console.log(`\nImported into ${path.join(DATA_DIR, 'algoarch.db')}`);
}

if (require.main === module) main();

module.exports = { importPathways };
