'use strict';

function wordCount(text) {
  if (!text) return 0;
  return String(text).split(/\s+/).filter((t) => /[\p{L}\p{N}]/u.test(t)).length;
}

function guideStats(markdown) {
  const out = { words: 0, headings: 0, codeBlocks: 0 };
  if (!markdown) return out;
  let inFence = false;
  const prose = [];
  for (const line of String(markdown).split(/\r?\n/)) {
    if (line.startsWith('```')) {
      if (!inFence) out.codeBlocks += 1;
      inFence = !inFence;
      continue;
    }
    if (!inFence && /^#{2,4}\s/.test(line)) out.headings += 1;
    prose.push(line);
  }
  out.words = wordCount(prose.join('\n'));
  return out;
}

function inlineText(nodes) {
  if (nodes == null) return '';
  if (typeof nodes === 'string') return nodes;
  if (Array.isArray(nodes)) return nodes.map(inlineText).join('');
  if (typeof nodes === 'object') {
    if (nodes.t === 'br') return ' ';
    return Array.isArray(nodes.c) ? inlineText(nodes.c) : '';
  }
  return '';
}

function listText(list, parts) {
  for (const item of list.items || []) {
    parts.push(inlineText(item.content));
    for (const child of item.children || []) listText(child, parts);
  }
}

function documentStats(doc) {
  const s = {
    words: 0, headings: 0, codeBlocks: 0, codeCells: 0, cellsWithTests: 0,
    widgets: 0, widgetsPorted: 0, quizzes: 0, checklists: 0, visuals: 0, text: '',
  };
  if (!doc) return s;
  const parts = [];

  function walk(block) {
    if (!block || typeof block !== 'object') return;
    switch (block.type) {
      case 'paragraph':
      case 'quote':
      case 'say':
        parts.push(inlineText(block.content));
        break;
      case 'heading':
        s.headings += 1;
        parts.push(inlineText(block.content));
        break;
      case 'list':
        listText(block, parts);
        break;
      case 'table':
        for (const cell of block.head || []) parts.push(inlineText(cell));
        for (const row of block.rows || []) for (const cell of row) parts.push(inlineText(cell));
        break;
      case 'code':
        s.codeBlocks += 1;
        parts.push(block.text || '');
        break;
      case 'code_cell':
        s.codeCells += 1;
        if (block.tests && String(block.tests).trim()) s.cellsWithTests += 1;
        break;
      case 'diagram':
      case 'scene':
        s.visuals += 1;
        break;
      case 'qa':
        parts.push(inlineText(block.summary));
        break;
      case 'widget':
        s.widgets += 1;
        if (block.ported) s.widgetsPorted += 1;
        if (block.kind === 'quiz') s.quizzes += 1;
        if (block.kind === 'checklist' || block.kind === 'scorecard') s.checklists += 1;
        if (block.kind === 'frames' || block.kind === 'trace') s.visuals += 1;
        break;
      default:
        break;
    }
    if (Array.isArray(block.blocks)) block.blocks.forEach(walk);
  }

  for (const section of doc.sections || []) (section.blocks || []).forEach(walk);
  s.text = parts.join('\n');
  s.words = wordCount(s.text);
  return s;
}

module.exports = { wordCount, guideStats, documentStats };
