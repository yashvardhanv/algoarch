// SQLite persistence layer. Content (curriculum, lesson guides, lesson documents, videos,
// resources, labs) lives here as data; the frontend owns all presentation.
const fs = require('fs');
const path = require('path');
const Database = require('better-sqlite3');
const { lessonToText } = require('./lessonText');

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
  }
];

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
  return {
    n: r.num, id: r.id, title: r.title, stars: r.stars, desc: r.description, duration: r.duration,
    tags: parseJson(r.tags, []), companies: parseJson(r.companies, []), isNew: !!r.is_new,
    lab: r.lab_file || undefined, hasDocument: !!r.has_document
  };
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
      return {
        lesson: lessonRow(r),
        track,
        guide: guide ? guide.markdown : '',
        document: doc ? { schemaVersion: doc.schema_version, ...parseJson(doc.document, {}) } : null,
        lab: lab ? { fileName: lab.file_name, code: lab.code } : null,
        videos: q.videosByLesson.all(id).map(videoRow),
        articles: q.resources.all(r.track_id, 'article').map(x => parseJson(x.data, {})),
        repos: q.resources.all(r.track_id, 'repo').map(x => parseJson(x.data, {})),
        prev: i > 0 ? { id: order[i - 1].id, title: order[i - 1].title, trackId: order[i - 1].track_id } : null,
        next: i >= 0 && i < order.length - 1 ? { id: order[i + 1].id, title: order[i + 1].title, trackId: order[i + 1].track_id } : null
      };
    },
    getVideos() { return q.allVideos.all().map(videoRow); },
    // Plain text of a lesson (document + guide) used to ground the AI mentor.
    getLessonText(id) {
      const r = q.lesson.get(id);
      if (!r) return null;
      const guide = q.guide.get(id);
      const doc = q.document.get(id);
      const text = lessonToText({ title: r.title, document: doc ? parseJson(doc.document, null) : null, guide: guide ? guide.markdown : '' });
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

module.exports = { openDb, createRepo, MIGRATIONS };
