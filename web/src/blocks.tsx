import { useState } from 'react';
import type { Block, ListBlock } from './types';
import { Inlines } from './inline';
import { MonacoEditor, guessLanguage } from './monaco';
import { CodeCell } from './CodeCell';
import { Quiz } from './Quiz';
import { Trace } from './Trace';
import { Checklist } from './Checklist';
import { Scorecard } from './Scorecard';

export { Inlines };

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className="rd-copy"
      onClick={() => navigator.clipboard.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1400); })}
    >
      {done ? 'Copied' : 'Copy'}
    </button>
  );
}

function ListView({ block }: { block: ListBlock }) {
  const Tag = block.ordered ? 'ol' : 'ul';
  return (
    <Tag>
      {block.items.map((it, i) => (
        <li key={i}>
          <Inlines nodes={it.content} />
          {it.children.map((c, j) => <ListView key={j} block={c} />)}
        </li>
      ))}
    </Tag>
  );
}

export function Blocks({ blocks }: { blocks: Block[] }) {
  return <>{blocks.map((b, i) => <BlockView key={i} block={b} />)}</>;
}

function BlockView({ block }: { block: Block }) {
  switch (block.type) {
    case 'paragraph': return <p><Inlines nodes={block.content} /></p>;
    case 'heading': return block.level === 3 ? <h3><Inlines nodes={block.content} /></h3> : <h4><Inlines nodes={block.content} /></h4>;
    case 'list': return <ListView block={block} />;
    case 'quote': return <blockquote><Inlines nodes={block.content} /></blockquote>;
    case 'code':
      if (block.diagram) {
        return <div className="rd-code diagram"><pre><code>{block.text}</code></pre></div>;
      }
      return (
        <div className={`rd-code${block.tone ? ' ' + block.tone : ''}`}>
          <CopyButton text={block.text} />
          <MonacoEditor value={block.text} language={guessLanguage(block.text)} readOnly lineNumbers={false} minHeight={40} maxHeight={480} />
        </div>
      );
    case 'table':
      return (
        <div className="rd-table">
          <table>
            {block.head && <thead><tr>{block.head.map((c, i) => <th key={i}><Inlines nodes={c} /></th>)}</tr></thead>}
            <tbody>{block.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}><Inlines nodes={c} /></td>)}</tr>)}</tbody>
          </table>
        </div>
      );
    case 'callout':
      return (
        <aside className={`rd-callout ${block.tone}`}>
          {block.label && <div className="rd-callout-label">{block.label}</div>}
          <Blocks blocks={block.blocks} />
        </aside>
      );
    case 'say':
      return (
        <figure className="rd-say">
          {block.label && <figcaption>{block.label}</figcaption>}
          <p><Inlines nodes={block.content} /></p>
        </figure>
      );
    case 'card':
      return (
        <section className={`rd-card ${block.tone}`}>
          {block.title && <h4>{block.title}</h4>}
          <Blocks blocks={block.blocks} />
        </section>
      );
    case 'qa':
      return (
        <details className="rd-qa">
          <summary><Inlines nodes={block.summary} /></summary>
          <div className="rd-qa-body"><Blocks blocks={block.blocks} /></div>
        </details>
      );
    case 'code_cell':
      return <CodeCell cell={block} />;
    case 'widget':
      if (block.data) {
        if (block.kind === 'quiz') return <Quiz data={block.data} title={block.title} />;
        if (block.kind === 'trace') return <Trace data={block.data} title={block.title} />;
        if (block.kind === 'checklist') return <Checklist data={block.data} title={block.title} />;
        if (block.kind === 'scorecard') return <Scorecard data={block.data} title={block.title} />;
      }
      return (
        <div className="rd-widget">
          <div className="rd-widget-title">{block.title || 'Interactive exercise'}</div>
          {block.description && <p>{block.description}</p>}
          <Blocks blocks={block.blocks} />
          {!block.ported && <p className="rd-widget-note">The interactive version of this exercise is not available yet.</p>}
        </div>
      );
    default:
      return null;
  }
}
