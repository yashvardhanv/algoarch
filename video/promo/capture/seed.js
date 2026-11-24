// Seeds the SCRATCH data dir only (never the repo's data/): one runnable lesson cell + progress.
const Database = require('../../../node_modules/better-sqlite3');
const fs = require('fs');
const path = require('path');
const dir = process.argv[2];
const db = new Database(path.join(dir, 'algoarch.db'));

const doc = {
  schemaVersion: 1,
  title: 'Hashmap as an Index',
  lede: ['The single highest-yield idea in interview DSA: trade memory for a lookup. For every value, the thing you need is already one dictionary hit away.'],
  sections: [{
    anchor: 'complement', number: '1', title: 'The complement trick', subtitle: null,
    blocks: [
      { type: 'paragraph', content: ['For each number ', { t: 'code', c: ['x'] }, ', the partner you need is ', { t: 'code', c: ['target - x'] }, '. Remember what you have already seen in a map from value to index, and the pair announces itself in a single pass: O(n) time, O(n) space.'] },
      { type: 'code_cell', title: 'Two Sum: complement map', badge: 'Editable, runs in your browser', language: 'python',
        starter: 'def two_sum(nums, target):\n    """Return the indices of the two numbers that add up to target."""\n    pass\n',
        tests: 'assert two_sum([2, 7, 11, 15], 9) == [0, 1]\nassert two_sum([3, 2, 4], 6) == [1, 2]\nassert two_sum([3, 3], 6) == [0, 1]\nassert two_sum([1, 2, 3], 7) == []\n' },
      { type: 'callout', tone: 'info', label: 'Recognition cue', blocks: [{ type: 'paragraph', content: ['"Find a pair that sums to a target" or "have I seen this before?" almost always means a hash map beats nested loops.'] }] }
    ]
  }]
};
db.prepare('DELETE FROM lesson_documents WHERE lesson_id = ?').run('ds02');
db.prepare('INSERT INTO lesson_documents (lesson_id, schema_version, document, updated_at) VALUES (?,?,?,?)').run('ds02', 1, JSON.stringify(doc), new Date().toISOString());
fs.writeFileSync(path.join(dir, 'progress.json'), JSON.stringify({ completed: ['ds00', 'ds01', 'sy01', 'sy02', 'ai01'], bookmarked: ['sy22'], notes: {} }, null, 2));
console.log('seeded', db.prepare('SELECT lesson_id, length(document) n FROM lesson_documents').all());
