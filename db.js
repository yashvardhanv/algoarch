// SQLite persistence layer. Content (curriculum, lesson guides, lesson documents, videos,
// resources, labs) lives here as data; the frontend owns all presentation.
const fs = require('fs');
const path = require('path');
const Database = require('better-sqlite3');
const { lessonToText } = require('./lessonText');
const { parseMinutes } = require('./curriculum');

const MIGRATIONS = [
  {
    id: 1,
    sql: `
      CREATE TABLE tracks (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, short_name TEXT, badge TEXT,
        description TEXT, color TEXT, position INTEGER NOT NULL
      );
      CREATE TABLE course_blocks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        track_id TEXT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
        key TEXT NOT NULL, title TEXT NOT NULL, position INTEGER NOT NULL
      );
      CREATE TABLE lessons (
        id TEXT PRIMARY KEY,
        track_id TEXT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
        block_id INTEGER NOT NULL REFERENCES course_blocks(id) ON DELETE CASCADE,
        position INTEGER NOT NULL, num TEXT, title TEXT NOT NULL, stars INTEGER DEFAULT 5,
        description TEXT, duration TEXT, is_new INTEGER DEFAULT 0,
        tags TEXT NOT NULL DEFAULT '[]', companies TEXT NOT NULL DEFAULT '[]',
        lab_file TEXT
      );
      CREATE INDEX idx_lessons_track ON lessons(track_id, position);
      CREATE TABLE lesson_guides (
        lesson_id TEXT PRIMARY KEY REFERENCES lessons(id) ON DELETE CASCADE,
        markdown TEXT NOT NULL, updated_at TEXT NOT NULL
      );
      CREATE TABLE lesson_documents (
        lesson_id TEXT PRIMARY KEY REFERENCES lessons(id) ON DELETE CASCADE,
        schema_version INTEGER NOT NULL, document TEXT NOT NULL, updated_at TEXT NOT NULL
      );
      CREATE TABLE lesson_labs (
        lesson_id TEXT PRIMARY KEY REFERENCES lessons(id) ON DELETE CASCADE,
        file_name TEXT NOT NULL, code TEXT NOT NULL
      );
      CREATE TABLE videos (
        pk INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL, youtube_id TEXT NOT NULL, track_id TEXT, lesson_id TEXT,
        title TEXT NOT NULL, channel TEXT, duration TEXT, category TEXT,
        description TEXT, thumbnail TEXT, position INTEGER NOT NULL
      );
      CREATE INDEX idx_videos_lesson ON videos(lesson_id);
      CREATE TABLE track_resources (
        track_id TEXT NOT NULL, kind TEXT NOT NULL CHECK (kind IN ('article','repo')),
        position INTEGER NOT NULL, data TEXT NOT NULL,
        PRIMARY KEY (track_id, kind, position)
      );
    `
  },
  {
    id: 2,
    sql: `
      CREATE TABLE admin_emails (
        email TEXT PRIMARY KEY COLLATE NOCASE,
        added_by TEXT,
        created_at TEXT NOT NULL
      );
      INSERT INTO admin_emails (email, added_by, created_at)
        VALUES ('yashji2117@gmail.com', 'seed', datetime('now'));
    `
  },
  {
    // Diagrams are authored separately from lesson documents so re-importing a lesson never drops them.
    // No foreign key on purpose: the importer rebuilds tracks and lessons.
    id: 3,
    sql: `
      CREATE TABLE lesson_diagrams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE,
        lesson_id TEXT NOT NULL,
        section_anchor TEXT NOT NULL,
        after_block INTEGER,
        position INTEGER NOT NULL DEFAULT 0,
        title TEXT,
        caption TEXT,
        scene TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
      CREATE INDEX idx_diagrams_lesson ON lesson_diagrams(lesson_id);
    `
  },
  {
    // Optional lesson metadata and curated pathways. Pathway tables carry no foreign keys:
    // the importer rebuilds lessons, and getPathways skips lessons that no longer exist.
    id: 4,
    sql: `
      ALTER TABLE lessons ADD COLUMN prereqs TEXT NOT NULL DEFAULT '[]';
      ALTER TABLE lessons ADD COLUMN objectives TEXT NOT NULL DEFAULT '[]';
      ALTER TABLE lessons ADD COLUMN sources TEXT NOT NULL DEFAULT '[]';
      ALTER TABLE lessons ADD COLUMN level TEXT;
      ALTER TABLE lessons ADD COLUMN reviewed_at TEXT;
      CREATE TABLE pathways (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT, kind TEXT NOT NULL, position INTEGER NOT NULL
      );
      CREATE TABLE pathway_lessons (
        pathway_id TEXT NOT NULL, lesson_id TEXT NOT NULL, position INTEGER NOT NULL, note TEXT,
        PRIMARY KEY (pathway_id, lesson_id)
      );
    `
  }
];

// Scenes are plain data (see web/src/Diagram.tsx for how they are drawn). Validate before storing.
const TONES = new Set(['neutral', 'accent', 'ok', 'bad', 'cool', 'warn', 'violet']);
const KINDS = new Set(['box', 'ellipse', 'diamond', 'text', 'arrow', 'line']);
function validateScene(scene) {
  if (!scene || scene.v !== 1 || !Array.isArray(scene.elements)) throw new Error('Scene must be {v:1, elements:[...]}');
  if (!(scene.width > 0 && scene.height > 0 && scene.width < 5000 && scene.height < 5000)) throw new Error('Scene needs a width and height');
  if (scene.elements.length > 300) throw new Error('Scene has too many elements');
  for (const e of scene.elements) {
    if (!KINDS.has(e.k)) throw new Error('Unknown element kind: ' + e.k);
    if (e.tone && !TONES.has(e.tone)) throw new Error('Unknown tone: ' + e.tone);
    if ((e.k === 'arrow' || e.k === 'line') ? !Array.isArray(e.pts) || e.pts.length < 2 : !Number.isFinite(e.x) || !Number.isFinite(e.y)) throw new Error('Element ' + (e.id || e.k) + ' has bad geometry');
  }
  return true;
}

function migrate(db) {
  db.exec('CREATE TABLE IF NOT EXISTS schema_migrations (id INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)');
  const applied = new Set(db.prepare('SELECT id FROM schema_migrations').all().map(r => r.id));
  for (const m of MIGRATIONS) {
    if (applied.has(m.id)) continue;
    db.transaction(() => {
      db.exec(m.sql);
      db.prepare('INSERT INTO schema_migrations (id, applied_at) VALUES (?, ?)').run(m.id, new Date().toISOString());
    })();
  }
}

function openDb(dataDir) {
  fs.mkdirSync(dataDir, { recursive: true });
  const db = new Database(path.join(dataDir, 'algoarch.db'));
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');
  migrate(db);
  return db;
}

// ------------------------------------------------------------------ queries
const parseJson = (s, fallback) => { try { return JSON.parse(s); } catch (e) { return fallback; } };

function lessonRow(r) {
  const row = {
    n: r.num, id: r.id, title: r.title, stars: r.stars, desc: r.description, duration: r.duration,
    tags: parseJson(r.tags, []), companies: parseJson(r.companies, []), isNew: !!r.is_new,
    lab: r.lab_file || undefined, hasDocument: !!r.has_document
  };
  for (const k of ['prereqs', 'objectives', 'sources']) {
    const arr = parseJson(r[k], []);
    if (Array.isArray(arr) && arr.length) row[k] = arr;
  }
  if (r.level) row.level = r.level;
  if (r.reviewed_at) row.reviewedAt = r.reviewed_at;
  return row;
}

// Splice stored diagrams into the lesson document as ordinary blocks.
function withDiagrams(document, rows) {
  if (!rows.length || !document.sections) return document;
  const sections = document.sections.map(s => ({ ...s, blocks: [...s.blocks] }));
  // insert from the back so earlier insertion points keep their meaning
  for (const d of [...rows].reverse()) {
    const s = sections.find(x => x.anchor === d.section_anchor);
    if (!s) continue;
    const block = { type: 'diagram', id: d.id, title: d.title || null, caption: d.caption || null, scene: parseJson(d.scene, null) };
    if (!block.scene) continue;
    const at = d.after_block == null ? s.blocks.length : Math.min(s.blocks.length, d.after_block + 1);
    s.blocks.splice(at, 0, block);
  }
  return { ...document, sections };
}

function createRepo(db) {
  const q = {
    tracks: db.prepare('SELECT * FROM tracks ORDER BY position'),
    blocks: db.prepare('SELECT * FROM course_blocks WHERE track_id = ? ORDER BY position'),
    lessonsByBlock: db.prepare(`
      SELECT l.*, EXISTS(SELECT 1 FROM lesson_documents d WHERE d.lesson_id = l.id) AS has_document
      FROM lessons l WHERE l.block_id = ? ORDER BY l.position`),
    lesson: db.prepare(`
      SELECT l.*, EXISTS(SELECT 1 FROM lesson_documents d WHERE d.lesson_id = l.id) AS has_document
      FROM lessons l WHERE l.id = ?`),
    guide: db.prepare('SELECT markdown FROM lesson_guides WHERE lesson_id = ?'),
    document: db.prepare('SELECT schema_version, document FROM lesson_documents WHERE lesson_id = ?'),
    lab: db.prepare('SELECT file_name, code FROM lesson_labs WHERE lesson_id = ?'),
    videosByLesson: db.prepare('SELECT * FROM videos WHERE lesson_id = ? ORDER BY position'),
    allVideos: db.prepare('SELECT * FROM videos ORDER BY position'),
    resources: db.prepare('SELECT data FROM track_resources WHERE track_id = ? AND kind = ? ORDER BY position'),
    neighbours: db.prepare(`
      SELECT l.id, l.title, l.track_id FROM lessons l
      JOIN course_blocks b ON b.id = l.block_id JOIN tracks t ON t.id = l.track_id
      ORDER BY t.position, b.position, l.position`)
  };

  const videoRow = (v) => ({ id: v.id, track: v.track_id, title: v.title, channel: v.channel, youtubeId: v.youtube_id, duration: v.duration, category: v.category, lessonLink: v.lesson_id, description: v.description, thumbnail: v.thumbnail });

  return {
    // Same shape the existing frontend consumed from curriculum.json.
    getCurriculum() {
      const tracks = q.tracks.all().map(t => {
        const blocks = q.blocks.all(t.id).map(b => ({ k: b.key, t: b.title, lessons: q.lessonsByBlock.all(b.id).map(lessonRow) }));
        return { id: t.id, name: t.name, shortName: t.short_name, badge: t.badge, description: t.description, color: t.color, totalLessons: blocks.reduce((n, b) => n + b.lessons.length, 0), blocks };
      });
      return { tracks };
    },
    getLesson(id) {
      const r = q.lesson.get(id);
      if (!r) return null;
      const track = db.prepare('SELECT id, name, color FROM tracks WHERE id = ?').get(r.track_id);
      const guide = q.guide.get(id);
      const doc = q.document.get(id);
      const lab = q.lab.get(id);
      const order = q.neighbours.all();
      const i = order.findIndex(x => x.id === id);
      let document = doc ? { schemaVersion: doc.schema_version, ...parseJson(doc.document, {}) } : null;
      if (document) document = withDiagrams(document, db.prepare('SELECT * FROM lesson_diagrams WHERE lesson_id = ? ORDER BY position, id').all(id));
      return {
        lesson: lessonRow(r),
        track,
        guide: guide ? guide.markdown : '',
        document,
        lab: lab ? { fileName: lab.file_name, code: lab.code } : null,
        videos: q.videosByLesson.all(id).map(videoRow),
        articles: q.resources.all(r.track_id, 'article').map(x => parseJson(x.data, {})),
        repos: q.resources.all(r.track_id, 'repo').map(x => parseJson(x.data, {})),
        prev: i > 0 ? { id: order[i - 1].id, title: order[i - 1].title, trackId: order[i - 1].track_id } : null,
        next: i >= 0 && i < order.length - 1 ? { id: order[i + 1].id, title: order[i + 1].title, trackId: order[i + 1].track_id } : null
      };
    },
    getPathways() {
      const lessons = db.prepare(`SELECT pl.pathway_id, pl.note, l.id, l.title, l.track_id, l.duration
        FROM pathway_lessons pl JOIN lessons l ON l.id = pl.lesson_id ORDER BY pl.pathway_id, pl.position`).all();
      return db.prepare('SELECT * FROM pathways ORDER BY position').all().map(p => {
        const ls = lessons.filter(x => x.pathway_id === p.id).map(x => {
          const o = { id: x.id, title: x.title, trackId: x.track_id, duration: x.duration };
          if (x.note != null) o.note = x.note;
          return o;
        });
        return { id: p.id, title: p.title, description: p.description, kind: p.kind, minutes: ls.reduce((n, x) => n + parseMinutes(x.duration), 0), lessons: ls };
      });
    },
    getVideos() { return q.allVideos.all().map(videoRow); },
    // Plain text of a lesson (document + guide) used to ground the AI mentor.
    getLessonText(id) {
      const r = q.lesson.get(id);
      if (!r) return null;
      const guide = q.guide.get(id);
      const doc = q.document.get(id);
      let text = lessonToText({ title: r.title, document: doc ? parseJson(doc.document, null) : null, guide: guide ? guide.markdown : '' });
      const dg = this.getDiagramsText(id);
      if (dg.length) text += '\n\n' + dg.join('\n');
      return { title: r.title, trackId: r.track_id, text };
    },
    getAdminLesson(id) {
      const r = q.lesson.get(id);
      if (!r) return null;
      const track = db.prepare('SELECT id, name FROM tracks WHERE id = ?').get(r.track_id);
      const guide = q.guide.get(id);
      return { ...lessonRow(r), trackId: track.id, trackName: track.name, markdown: guide ? guide.markdown : '' };
    },
    saveLesson(body) {
      const { id, title, trackId, duration, stars, desc, tags, markdown } = body;
      if (!id) throw new Error('Missing lesson ID');
      const tagList = Array.isArray(tags) ? tags : String(tags || '').split(',').map(t => t.trim()).filter(Boolean);
      db.transaction(() => {
        const existing = q.lesson.get(id);
        if (existing) {
          db.prepare('UPDATE lessons SET title = ?, duration = ?, stars = ?, description = ?, tags = ?, is_new = 1 WHERE id = ?')
            .run(title || existing.title, duration || existing.duration, parseInt(stars) || existing.stars || 5, desc || existing.description, JSON.stringify(tagList), id);
        } else {
          const track = db.prepare('SELECT id FROM tracks WHERE id = ?').get(trackId) || db.prepare('SELECT id FROM tracks ORDER BY position LIMIT 1').get();
          if (!track) throw new Error('No track available for new lesson');
          const block = db.prepare('SELECT id FROM course_blocks WHERE track_id = ? ORDER BY position LIMIT 1').get(track.id);
          if (!block) throw new Error('Track has no blocks');
          const pos = db.prepare('SELECT COALESCE(MAX(position), -1) + 1 AS p FROM lessons WHERE block_id = ?').get(block.id).p;
          db.prepare(`INSERT INTO lessons (id, track_id, block_id, position, num, title, stars, description, duration, is_new, tags, companies)
            VALUES (?,?,?,?,?,?,?,?,?,1,?,'[]')`)
            .run(id, track.id, block.id, pos, String(pos + 1), title || 'New Lesson', parseInt(stars) || 5, desc || '', duration || '45 min', JSON.stringify(tagList));
        }
        db.prepare(`INSERT INTO lesson_guides (lesson_id, markdown, updated_at) VALUES (?, ?, ?)
          ON CONFLICT(lesson_id) DO UPDATE SET markdown = excluded.markdown, updated_at = excluded.updated_at`)
          .run(id, markdown || '', new Date().toISOString());
      })();
      return { success: true, id, message: `Lesson ${id} published successfully.` };
    },

    // ---- diagrams
    listDiagrams(lessonId) {
      return db.prepare('SELECT id, slug, lesson_id AS lessonId, section_anchor AS sectionAnchor, after_block AS afterBlock, position, title, caption, updated_at AS updatedAt FROM lesson_diagrams WHERE lesson_id = ? ORDER BY position, id').all(lessonId);
    },
    saveDiagram({ id, slug = null, lessonId, sectionAnchor, afterBlock = null, position = 0, title = null, caption = null, scene }) {
      if (!id && slug) { const ex = db.prepare('SELECT id FROM lesson_diagrams WHERE slug = ?').get(slug); if (ex) id = ex.id; }
      if (!db.prepare('SELECT 1 FROM lessons WHERE id = ?').get(lessonId)) throw new Error('Unknown lesson: ' + lessonId);
      if (!sectionAnchor) throw new Error('sectionAnchor is required');
      validateScene(scene);
      const now = new Date().toISOString();
      if (id) {
        const r = db.prepare('UPDATE lesson_diagrams SET slug=COALESCE(?, slug), lesson_id=?, section_anchor=?, after_block=?, position=?, title=?, caption=?, scene=?, updated_at=? WHERE id=?')
          .run(slug, lessonId, sectionAnchor, afterBlock, position, title, caption, JSON.stringify(scene), now, id);
        if (!r.changes) throw new Error('Diagram not found');
        return { id };
      }
      const r = db.prepare('INSERT INTO lesson_diagrams (slug, lesson_id, section_anchor, after_block, position, title, caption, scene, updated_at) VALUES (?,?,?,?,?,?,?,?,?)')
        .run(slug, lessonId, sectionAnchor, afterBlock, position, title, caption, JSON.stringify(scene), now);
      return { id: Number(r.lastInsertRowid) };
    },
    deleteDiagram(id) { return db.prepare('DELETE FROM lesson_diagrams WHERE id = ?').run(id).changes > 0; },
    getDiagramsText(lessonId) {
      return db.prepare('SELECT title, caption, scene FROM lesson_diagrams WHERE lesson_id = ?').all(lessonId).map(d => {
        const sc = parseJson(d.scene, null) || { elements: [] };
        const labels = sc.elements.map(e => e.label || (e.k === 'text' ? e.text : '')).filter(Boolean).join('; ');
        return `Diagram: ${d.title || ''}. ${d.caption || ''} Labels: ${labels}`.trim();
      });
    },

    // ---- admin emails: only a verified sign-in with one of these addresses is an admin
    isAdminEmail(email) {
      if (!email) return false;
      return !!db.prepare('SELECT 1 FROM admin_emails WHERE email = ?').get(String(email).trim());
    },
    listAdmins() {
      return db.prepare('SELECT email, added_by AS addedBy, created_at AS createdAt FROM admin_emails ORDER BY created_at, email').all();
    },
    addAdmin(email, addedBy) {
      const e = String(email || '').trim().toLowerCase();
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e)) throw new Error('Enter a valid email address');
      db.prepare('INSERT OR IGNORE INTO admin_emails (email, added_by, created_at) VALUES (?, ?, ?)')
        .run(e, addedBy || null, new Date().toISOString());
      return this.listAdmins();
    },
    removeAdmin(email) {
      const e = String(email || '').trim();
      const total = db.prepare('SELECT COUNT(*) AS n FROM admin_emails').get().n;
      if (total <= 1) throw new Error('Cannot remove the last admin');
      db.prepare('DELETE FROM admin_emails WHERE email = ?').run(e);
      return this.listAdmins();
    }
  };
}

module.exports = { openDb, createRepo, MIGRATIONS, validateScene };
