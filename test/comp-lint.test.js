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

// Stricter than findCompClaims: also rejects currency symbols and ISO codes next to a number,
// k-suffix amounts, multiples of pay ("2x base") and percentages tied to pay ("15% of base",
// "a bonus of 15%", "25% of the initial grant"), which read as market norms.
const PAY = String.raw`(?:base|salary|pay|CTC|compensation|bonus|equity|grant|RSUs?|options?)`;
const STRICT_COMP_RE = new RegExp([
  String.raw`[$€£₹]\s?\d`, // $40, ₹10
  String.raw`\b(?:USD|EUR|GBP|INR|Rs\.?)\s?\d`, // USD 150k, Rs. 20 lakh, INR 30,00,000
  String.raw`\d[\d,.]*\s?(?:USD|EUR|GBP|INR)\b`, // 150,000 USD
  String.raw`\b\d+(?:\.\d+)?\s?[kK]\b`, // base 180k
  String.raw`\b\d+(?:\.\d+)?\s?[x×]\s*(?:(?:the|your|annual|target)\s+)*${PAY}\b`, // 2x base
  String.raw`\b\d+(?:\.\d+)?\s?(?:[-–]\s?\d+(?:\.\d+)?\s?)?%\s*(?:of\s+)?(?:[\w-]+\s+){0,3}?${PAY}\b`, // 15% of base, 25% of the initial grant
  String.raw`\b${PAY}\s+(?:of|at|is|was|=|:)\s*(?:about\s+|around\s+|~)?\d+(?:\.\d+)?\s?%`, // bonus of 15%
].join('|'), 'gi');

function findStrictCompClaims(text) {
  return String(text || '').match(STRICT_COMP_RE) || [];
}

test('the strict pattern catches currency symbols and pay percentages', () => {
  const bad = 'A sign-on of $40,000, €5k, £3 000 or ₹10 plus a 15% of base bonus and 10-20% of salary in RSUs';
  assert.equal(findStrictCompClaims(bad).length, 6);
  assert.deepEqual(findStrictCompClaims('Vest X/4 shares each year; a cliff of one year; 25 items'), []);
});

test('be08 lesson carries no compensation figures', () => {
  const fs = require('node:fs');
  const path = require('node:path');
  const md = fs.readFileSync(path.join(__dirname, '..', 'data', 'new_lessons', 'be08-ctc-equity-playbook.md'), 'utf8');
  assert.deepEqual(findCompClaims(md), []);
  assert.deepEqual(findStrictCompClaims(md), []);
  assert.match(md.split(/\r?\n/)[0], /^# Lesson 08 — Offer Structure and Equity Playbook$/);
  assert.match(md, /^## Sources$/m);
  assert.match(md, /not tax advice/i);
});

test('the strict pattern catches codes, k-suffixes, multiples and grant percentages', () => {
  const planted = [
    'a bonus of 15%',
    'USD 150k',
    '150,000 USD',
    'Rs. 20 lakh',
    'INR 30,00,000',
    'base 180k',
    'equity worth 2x base',
    '25% of the initial grant',
  ];
  for (const s of planted) assert.notDeepEqual(findStrictCompClaims(s), [], `should flag: ${s}`);
  assert.deepEqual(findStrictCompClaims('Vest G/4 units after a one-year cliff; read your plan'), []);
});
