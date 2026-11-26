// Safely replaces ONE lesson guide in the live database.
//   node tools/content/update-guide.js <lessonId> <markdown file> --was <git rev> [--data <dir>] [--force]
// Refuses when the stored guide differs from the file as it was at <git rev> (someone edited it in the CMS),
// so a CMS edit is never overwritten by accident. Makes a timestamped backup of the database first.
const fs = require('fs');
const path = require('path');

const norm = (s) => String(s == null ? '' : s).replace(/\r/g, '').trim();

function updateGuide(db, lessonId, newMd, expectedOldMd, opts = {}) {
  if (!norm(newMd)) return { ok: false, reason: 'new text is empty' };
  const lesson = db.prepare('SELECT id FROM lessons WHERE id = ?').get(lessonId);
  if (!lesson) return { ok: false, reason: `unknown lesson ${lessonId}` };
  const row = db.prepare('SELECT markdown FROM lesson_guides WHERE lesson_id = ?').get(lessonId);
  if (row && !opts.force && norm(row.markdown) !== norm(expectedOldMd)) {
    return { ok: false, reason: `stored guide differs from the expected old text (edited in the CMS?); not overwriting` };
  }
  db.prepare('INSERT OR REPLACE INTO lesson_guides (lesson_id, markdown, updated_at) VALUES (?,?,?)')
    .run(lessonId, norm(newMd), new Date().toISOString());
  return { ok: true };
}

function main() {
  const args = process.argv.slice(2);
  const opt = (name) => { const i = args.indexOf('--' + name); return i >= 0 ? args[i + 1] : undefined; };
  const [lessonId, file] = args;
  const was = opt('was');
  if (!lessonId || !file || (!was && !args.includes('--force'))) {
    console.error('usage: update-guide.js <lessonId> <markdown file> --was <git rev> [--data <dir>] [--force]');
    process.exit(2);
  }
  const dataDir = path.resolve(opt('data') || path.join(__dirname, '..', '..', 'data'));
  const { openDb } = require('../../db.js');
  let expected = '';
  if (was) {
    const rel = path.relative(path.join(__dirname, '..', '..'), path.resolve(file)).split(path.sep).join('/');
    expected = require('child_process').execFileSync('git', ['show', `${was}:${rel}`], { cwd: path.join(__dirname, '..', '..'), encoding: 'utf8' });
  }
  const dbFile = path.join(dataDir, 'algoarch.db');
  if (fs.existsSync(dbFile)) fs.copyFileSync(dbFile, `${dbFile}.bak-${lessonId}-${Date.now()}`);
  const db = openDb(dataDir);
  const r = updateGuide(db, lessonId, fs.readFileSync(file, 'utf8'), expected, { force: args.includes('--force') });
  db.close();
  console.log(r.ok ? `updated ${lessonId}` : `REFUSED ${lessonId}: ${r.reason}`);
  process.exitCode = r.ok ? 0 : 1;
}

if (require.main === module) main();
module.exports = { updateGuide };
