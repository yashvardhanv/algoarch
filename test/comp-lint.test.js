const { test } = require('node:test');
const assert = require('node:assert/strict');
const { findCompClaims } = require('../tools/content/comp-lint');

test('flags rupee amounts, LPA figures, lakh and crore amounts and salary ranges', () => {
  assert.equal(findCompClaims('an offer of ₹50,00,000 CTC').length, 1);
  assert.equal(findCompClaims('between 25LPA and 50 LPA+').length, 2);
  assert.equal(findCompClaims('they said ₹50 Lakhs and 1.2 Cr').length, 2);
  assert.equal(findCompClaims('base ~20–30 LPA').length, 1);
});

test('does not flag qualitative compensation talk, code or unrelated numbers', () => {
  assert.deepEqual(findCompClaims('Negotiate the base, bonus and RSU vesting schedule.'), []);
  assert.deepEqual(findCompClaims('Cr is a column name; total = 50 items'), []);
  assert.deepEqual(findCompClaims('ratio 3 : 1 and 20% of base'), []);
});

test('returns the matched text so a reviewer can find it', () => {
  assert.deepEqual(findCompClaims('target ₹35L base'), ['₹35L']);
});

test('rubric verdicts carry no compensation figures', () => {
  const fs = require('node:fs');
  const path = require('node:path');
  const lines = fs.readFileSync(path.join(__dirname, '..', 'public', 'app.js'), 'utf8').split(/\r?\n/);
  const start = lines.findIndex((l) => l.includes('const updateRubric'));
  assert.notEqual(start, -1);
  let end = start + 1;
  while (end < lines.length && lines[end] !== '  };') end++;
  const text = lines.slice(start, end).join('\n');
  assert.deepEqual(findCompClaims(text), []);
});
