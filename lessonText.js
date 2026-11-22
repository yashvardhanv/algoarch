// Flattens a lesson (typed-block document + markdown guide) into plain text for the AI mentor.
// Section titles are kept so the model can point the learner to where the answer lives.

function inlineText(nodes) {
  if (!Array.isArray(nodes)) return '';
  return nodes.map(n => {
    if (typeof n === 'string') return n;
    if (n && n.t === 'br') return '\n';
    return n && n.c ? inlineText(n.c) : '';
  }).join('');
}

function listText(block, depth = 0) {
  const pad = '  '.repeat(depth);
  return block.items.map((it, i) => {
    const bullet = block.ordered ? `${i + 1}.` : '-';
    const nested = (it.children || []).map(c => listText(c, depth + 1)).join('\n');
    return `${pad}${bullet} ${inlineText(it.content)}${nested ? '\n' + nested : ''}`;
  }).join('\n');
}

function blockText(b) {
  switch (b.type) {
    case 'paragraph': return inlineText(b.content);
    case 'heading': return `${'#'.repeat(b.level)} ${inlineText(b.content)}`;
    case 'list': return listText(b);
    case 'quote': return `> ${inlineText(b.content)}`;
    case 'code': return '```\n' + b.text + '\n```';
    case 'table': {
      const rows = [];
      if (b.head) rows.push(b.head.map(inlineText).join(' | '));
      for (const r of b.rows) rows.push(r.map(inlineText).join(' | '));
      return rows.join('\n');
    }
    case 'callout': return [b.label ? `${b.label}:` : '', blocksText(b.blocks)].filter(Boolean).join('\n');
    case 'say': return `${b.label ? b.label + ': ' : ''}${inlineText(b.content)}`;
    case 'card': return [b.title || '', blocksText(b.blocks)].filter(Boolean).join('\n');
    case 'qa': return `Q: ${inlineText(b.summary)}\nA: ${blocksText(b.blocks)}`;
    case 'code_cell': return `${b.title}:\n\`\`\`${b.language || ''}\n${b.starter}\n\`\`\``;
    case 'widget': return [b.title, b.description, blocksText(b.blocks)].filter(Boolean).join('\n');
    default: return '';
  }
}

function blocksText(blocks) {
  return (blocks || []).map(blockText).filter(Boolean).join('\n\n');
}

function documentToText(doc) {
  if (!doc) return '';
  const parts = [];
  if (doc.title) parts.push(`# ${doc.title}`);
  if (doc.lede && doc.lede.length) parts.push(inlineText(doc.lede));
  (doc.sections || []).forEach((s, i) => {
    parts.push(`## Section ${s.number || i + 1}: ${s.title}${s.subtitle ? ' (' + s.subtitle + ')' : ''}\n${blocksText(s.blocks)}`);
  });
  return parts.join('\n\n');
}

const MAX_CHARS = 150000;

function lessonToText({ title, document, guide }) {
  const parts = [];
  if (document) parts.push(documentToText(document));
  if (guide) parts.push(`## Written guide\n${guide}`);
  const text = parts.join('\n\n');
  return text.length > MAX_CHARS ? text.slice(0, MAX_CHARS) + '\n[truncated]' : text;
}

module.exports = { lessonToText, documentToText };
