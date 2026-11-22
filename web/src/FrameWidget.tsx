import { createElement, useMemo, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import './frames.css';

// Interactive panels recorded from the original lessons. The data holds the controls and every
// rendered result as a sanitized element tree; this component owns all presentation and behaviour.
interface FNode { t: string; a?: Record<string, string>; k?: (number | string)[] }
type Ctl =
  | { k: 'range'; label: string; values: number[]; def: number }
  | { k: 'select'; label: string; options: { v: string; t: string }[]; def: number }
  | { k: 'check'; label: string; def: number };
export interface FramesData {
  v: 1;
  scope?: string;
  nodes: FNode[];
  frames: { s: string; r: number | null }[];
  base: number;
  controls: Ctl[];
  grid: number[] | null;
  seq: number[] | null;
  buttons: { label: string; role: 'reset' | 'step' | 'action' }[];
  acts: { label: string; frame: number }[];
  bodyActs: { i: number; frame: number }[];
  partial?: boolean;
}

const VOID = new Set(['br', 'hr', 'img', 'col']);
const RENAME: Record<string, string> = { class: 'className', colspan: 'colSpan', rowspan: 'rowSpan', viewBox: 'viewBox', preserveAspectRatio: 'preserveAspectRatio' };
const camel = (s: string) => s.replace(/-([a-z])/g, (_m, c) => c.toUpperCase());

function parseStyle(s: string): CSSProperties {
  const out: Record<string, string> = {};
  for (const decl of s.split(';')) {
    const i = decl.indexOf(':');
    if (i > 0) out[camel(decl.slice(0, i).trim())] = decl.slice(i + 1).trim();
  }
  return out as CSSProperties;
}

function build(nodes: FNode[], id: number, onAct: (i: number) => void, key: string | number): ReactNode {
  const n = nodes[id];
  if (!n) return null;
  const props: Record<string, unknown> = { key };
  let act: number | null = null;
  for (const [k, v] of Object.entries(n.a || {})) {
    if (k === 'act') act = Number(v);
    else if (k === 'style') props.style = parseStyle(v);
    else props[RENAME[k] ?? camel(k)] = v;
  }
  if (act !== null) {
    props.onClick = () => onAct(act as number);
    if (n.t !== 'button') {
      props.role = 'button'; props.tabIndex = 0;
      props.onKeyDown = (e: React.KeyboardEvent) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onAct(act as number); } };
    } else props.type = 'button';
  }
  const tag = n.t === 'a' ? 'span' : n.t;
  if (VOID.has(tag)) return createElement(tag, props);
  const kids = (n.k || []).map((c, i) => (typeof c === 'string' ? c : build(nodes, c, onAct, i)));
  return createElement(tag, props, ...kids);
}

export function FrameWidget({ data, title }: { data: FramesData; title?: string | null }) {
  const defaults = useMemo(() => data.controls.map(c => c.def), [data]);
  const [idx, setIdx] = useState<number[]>(defaults);
  const [branch, setBranch] = useState<{ frame: number; pos?: number } | null>(null);

  const gridFrame = useMemo(() => {
    if (!data.grid || !data.controls.length) return data.base;
    let i = 0;
    data.controls.forEach((c, ci) => {
      const len = c.k === 'range' ? c.values.length : c.k === 'select' ? c.options.length : 2;
      i = i * len + (idx[ci] ?? 0);
    });
    return data.grid[i] ?? data.base;
  }, [data, idx]);

  const frameNo = branch ? branch.frame : gridFrame;
  const frame = data.frames[frameNo] || data.frames[data.base];
  const reset = () => { setIdx(defaults); setBranch(null); };
  const setControl = (ci: number, v: number) => { setIdx(a => a.map((x, j) => (j === ci ? v : x))); setBranch(null); };

  const stepSeq = () => {
    if (!data.seq) return;
    const pos = branch && branch.pos !== undefined ? Math.min(branch.pos + 1, data.seq.length - 1) : 1;
    setBranch({ frame: data.seq[pos], pos });
  };
  const atEnd = !!data.seq && branch?.pos !== undefined && branch.pos >= data.seq.length - 1;
  const onAct = (i: number) => {
    const hit = data.bodyActs.find(a => a.i === i);
    if (hit) setBranch({ frame: hit.frame });
  };

  const body = useMemo(
    () => (frame && frame.r !== null ? build(data.nodes, frame.r, onAct, 'root') : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data, frame],
  );

  const hasControls = data.controls.length > 0 || data.buttons.length > 0;
  const usedActs = new Set<number>();
  return (
    <div className="rd-fwbox">
      <div className="rd-check-bar">
        <span className="rd-check-title">{title || 'Interactive'}</span>
        {frame && frame.s ? <span className="rd-check-score" aria-live="polite">{frame.s}</span> : null}
      </div>
      <div className={'rd-fw' + (data.scope ? ' fw-pg-' + data.scope : '')}>{body}</div>
      {hasControls && (
        <div className="rd-fw-controls">
          {data.controls.map((c, ci) => (
            <label key={ci} className="rd-fw-ctl">
              <span>{c.label}</span>
              {c.k === 'range' && (
                <>
                  <input type="range" min={0} max={c.values.length - 1} step={1} value={idx[ci] ?? 0} onChange={e => setControl(ci, Number(e.target.value))} />
                  <output>{c.values[idx[ci] ?? 0]}</output>
                </>
              )}
              {c.k === 'select' && (
                <select value={idx[ci] ?? 0} onChange={e => setControl(ci, Number(e.target.value))}>
                  {c.options.map((o, oi) => <option key={oi} value={oi}>{o.t}</option>)}
                </select>
              )}
              {c.k === 'check' && <input type="checkbox" checked={!!idx[ci]} onChange={e => setControl(ci, e.target.checked ? 1 : 0)} />}
            </label>
          ))}
          {data.buttons.map((b, bi) => {
            if (b.role === 'reset') return <button key={bi} type="button" className="btn-pg-ghost" onClick={reset}>{b.label}</button>;
            if (b.role === 'step' && data.seq) return <button key={bi} type="button" className="btn-pg-primary" disabled={atEnd} onClick={stepSeq}>{b.label}</button>;
            const ai = data.acts.findIndex((a, i) => a.label === b.label && !usedActs.has(i));
            if (ai < 0) return null;
            usedActs.add(ai);
            return <button key={bi} type="button" className="btn-pg-ghost" onClick={() => setBranch({ frame: data.acts[ai].frame })}>{b.label}</button>;
          })}
        </div>
      )}
    </div>
  );
}
