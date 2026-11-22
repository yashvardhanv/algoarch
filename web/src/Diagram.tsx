import { useId, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

// A lesson diagram. The data is a plain scene (shapes, text, arrows with semantic tones and an
// optional step number); this component owns how it looks: a hand-drawn line style that follows
// the app theme, and an optional step-by-step walk-through.
type Tone = 'neutral' | 'accent' | 'ok' | 'bad' | 'cool' | 'warn' | 'violet';
export interface DiagramElement {
  id: string;
  k: 'box' | 'ellipse' | 'diamond' | 'text' | 'arrow' | 'line';
  x?: number; y?: number; w?: number; h?: number;
  pts?: [number, number][];
  label?: string;
  tone?: Tone;
  fill?: boolean;
  dashed?: boolean;
  faint?: boolean;
  size?: 'sm' | 'md' | 'lg';
  head?: 'end' | 'start' | 'both' | 'none';
  step?: number;
}
export interface DiagramScene { v: 1; width: number; height: number; elements: DiagramElement[]; steps?: string[] }

// deterministic jitter so a diagram looks the same on every render
function rng(seed: string) {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) { h ^= seed.charCodeAt(i); h = Math.imul(h, 16777619); }
  return () => {
    h += 0x6d2b79f5;
    let t = h;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const f = (n: number) => Math.round(n * 10) / 10;

// a slightly bowed, slightly overshooting line
function sketchLine(x1: number, y1: number, x2: number, y2: number, r: () => number, over = 2): string {
  const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy) || 1;
  const ux = dx / len, uy = dy / len, nx = -uy, ny = ux;
  const bow = Math.min(3, len * 0.012) * (r() - 0.5) * 2 + (r() - 0.5);
  const sx = x1 - ux * over * r(), sy = y1 - uy * over * r();
  const ex = x2 + ux * over * r(), ey = y2 + uy * over * r();
  const c1x = sx + (ex - sx) * 0.3 + nx * bow, c1y = sy + (ey - sy) * 0.3 + ny * bow;
  const c2x = sx + (ex - sx) * 0.7 + nx * bow, c2y = sy + (ey - sy) * 0.7 + ny * bow;
  return `M${f(sx)} ${f(sy)}C${f(c1x)} ${f(c1y)} ${f(c2x)} ${f(c2y)} ${f(ex)} ${f(ey)}`;
}
function roundedRect(x: number, y: number, w: number, h: number, rad: number): string {
  const r = Math.min(rad, w / 2, h / 2);
  return `M${x + r} ${y}H${x + w - r}Q${x + w} ${y} ${x + w} ${y + r}V${y + h - r}Q${x + w} ${y + h} ${x + w - r} ${y + h}H${x + r}Q${x} ${y + h} ${x} ${y + h - r}V${y + r}Q${x} ${y} ${x + r} ${y}Z`;
}
function sketchOutline(e: DiagramElement, r: () => number): string[] {
  const x = e.x ?? 0, y = e.y ?? 0, w = e.w ?? 0, h = e.h ?? 0;
  if (e.k === 'ellipse') {
    const out: string[] = [];
    for (let pass = 0; pass < 2; pass++) {
      const n = 28, pts: string[] = [];
      for (let i = 0; i <= n + 2; i++) {
        const a = ((i / n) * Math.PI * 2) + pass * 0.15;
        const j = 1 + (r() - 0.5) * 0.02;
        pts.push(`${f(x + w / 2 + (w / 2) * Math.cos(a) * j)} ${f(y + h / 2 + (h / 2) * Math.sin(a) * j)}`);
      }
      out.push('M' + pts[0] + pts.slice(1).map(p => 'L' + p).join(''));
    }
    return out;
  }
  const corners: [number, number][] = e.k === 'diamond'
    ? [[x + w / 2, y], [x + w, y + h / 2], [x + w / 2, y + h], [x, y + h / 2]]
    : [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
  const out: string[] = [];
  for (let pass = 0; pass < 2; pass++) {
    let d = '';
    for (let i = 0; i < 4; i++) { const a = corners[i], b = corners[(i + 1) % 4]; d += sketchLine(a[0], a[1], b[0], b[1], r, e.k === 'box' ? 3 : 1); }
    out.push(d);
  }
  return out;
}
function arrowHead(p: [number, number], from: [number, number], r: () => number): string {
  const ang = Math.atan2(p[1] - from[1], p[0] - from[0]);
  const len = 13;
  const a1 = ang + Math.PI - 0.45, a2 = ang + Math.PI + 0.45;
  return `M${f(p[0] + Math.cos(a1) * len)} ${f(p[1] + Math.sin(a1) * len)}L${f(p[0])} ${f(p[1])}L${f(p[0] + Math.cos(a2) * len)} ${f(p[1] + Math.sin(a2) * len)}` + (r() < 0 ? '' : '');
}

const PX = { sm: 16, md: 19, lg: 25 };

function Lines({ text, x, y, size, anchor, middle }: { text: string; x: number; y: number; size: number; anchor: 'start' | 'middle'; middle: boolean }) {
  const lines = text.split('\n');
  const lh = size * 1.28;
  const y0 = middle ? y - ((lines.length - 1) * lh) / 2 : y + size;
  return (
    <>
      {lines.map((ln, i) => (
        <text key={i} x={x} y={f(y0 + i * lh)} textAnchor={anchor} dominantBaseline={middle ? 'central' : 'auto'} fontSize={size}>{ln}</text>
      ))}
    </>
  );
}

function Shape({ e }: { e: DiagramElement }): ReactNode {
  const r = rng(e.id);
  const tone = e.tone || 'neutral';
  const size = PX[e.size || 'md'];
  if (e.k === 'text') {
    return <g className={`dg-text dg-${tone}`}><Lines text={e.label || ''} x={e.x ?? 0} y={e.y ?? 0} size={size} anchor="start" middle={false} /></g>;
  }
  if (e.k === 'arrow' || e.k === 'line') {
    const pts = e.pts || [];
    let d = '';
    for (let i = 0; i < pts.length - 1; i++) d += sketchLine(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], r, 0.5);
    const last = pts[pts.length - 1], prev = pts[pts.length - 2];
    const first = pts[0], second = pts[1];
    const heads: string[] = [];
    if (e.k === 'arrow' && last && prev) {
      if (e.head !== 'none' && e.head !== 'start') heads.push(arrowHead(last, prev, r));
      if (e.head === 'start' || e.head === 'both') heads.push(arrowHead(first, second, r));
    }
    // label sits on the longest segment
    let lab: ReactNode = null;
    if (e.label && pts.length >= 2) {
      let best = 0, bi = 0;
      for (let i = 0; i < pts.length - 1; i++) { const l = Math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]); if (l > best) { best = l; bi = i; } }
      const mx = (pts[bi][0] + pts[bi + 1][0]) / 2, my = (pts[bi][1] + pts[bi + 1][1]) / 2;
      lab = <g className="dg-arrow-label"><Lines text={e.label} x={mx} y={my - 14} size={16} anchor="middle" middle /></g>;
    }
    return (
      <g className={`dg-line dg-${tone}${e.dashed ? ' dashed' : ''}`}>
        <path d={d} fill="none" />
        {heads.map((h, i) => <path key={i} d={h} fill="none" />)}
        {lab}
      </g>
    );
  }
  // shapes
  const x = e.x ?? 0, y = e.y ?? 0, w = e.w ?? 0, h = e.h ?? 0;
  const outline = sketchOutline(e, r);
  const fillD = e.k === 'box' ? roundedRect(x, y, w, h, 10)
    : e.k === 'ellipse' ? `M${x} ${y + h / 2}a${w / 2} ${h / 2} 0 1 0 ${w} 0a${w / 2} ${h / 2} 0 1 0 ${-w} 0Z`
      : `M${x + w / 2} ${y}L${x + w} ${y + h / 2}L${x + w / 2} ${y + h}L${x} ${y + h / 2}Z`;
  return (
    <g className={`dg-shape dg-${tone}${e.dashed ? ' dashed' : ''}${e.faint ? ' faint' : ''}`}>
      {e.fill ? <path className="dg-fill" d={fillD} stroke="none" /> : null}
      {outline.map((d, i) => <path key={i} d={d} fill="none" />)}
      {e.label ? <g className="dg-label"><Lines text={e.label} x={x + w / 2} y={y + h / 2} size={size} anchor="middle" middle /></g> : null}
    </g>
  );
}

export function Diagram({ scene, title, caption }: { scene: DiagramScene; title?: string | null; caption?: string | null }) {
  const uid = useId();
  const steps = scene.steps || [];
  const maxStep = useMemo(() => scene.elements.reduce((m, e) => Math.max(m, e.step || 0), 0), [scene]);
  const walkable = maxStep > 1;
  // null = the complete diagram; a number = walking through, showing steps up to that one
  const [step, setStep] = useState<number | null>(null);

  const desc = useMemo(() => scene.elements.map(e => e.label).filter(Boolean).join(', '), [scene]);
  const visible = (e: DiagramElement) => step === null || !e.step || e.step <= step;
  const dim = (e: DiagramElement) => step !== null && !!e.step && e.step < step;

  return (
    <figure className="rd-dg">
      <svg viewBox={`0 0 ${scene.width} ${scene.height}`} role="img" aria-labelledby={`${uid}-t ${uid}-d`}>
        <title id={`${uid}-t`}>{title || 'Diagram'}</title>
        <desc id={`${uid}-d`}>{desc}</desc>
        {scene.elements.map(e => (
          <g key={e.id} className={`dg-el${visible(e) ? '' : ' hidden'}${dim(e) ? ' dim' : ''}${step !== null && e.step === step ? ' now' : ''}`} aria-hidden={!visible(e)}>
            <Shape e={e} />
          </g>
        ))}
      </svg>
      <figcaption>
        <div className="rd-dg-cap">
          {title ? <strong>{title}</strong> : null}
          {caption ? <span>{caption}</span> : null}
        </div>
        {walkable && (
          <div className="rd-dg-steps">
            {step === null ? (
              <button type="button" className="btn-pg-ghost" onClick={() => setStep(1)}>Walk through</button>
            ) : (
              <>
                <button type="button" className="btn-pg-ghost" disabled={step <= 1} onClick={() => setStep(s => Math.max(1, (s ?? 1) - 1))}>Back</button>
                <span className="rd-dg-count">{step} / {maxStep}</span>
                <button type="button" className="btn-pg-primary" disabled={step >= maxStep} onClick={() => setStep(s => Math.min(maxStep, (s ?? 0) + 1))}>Next</button>
                <button type="button" className="btn-pg-ghost" onClick={() => setStep(null)}>Show all</button>
              </>
            )}
          </div>
        )}
        {step !== null && steps[step - 1] ? <p className="rd-dg-step" aria-live="polite">{steps[step - 1]}</p> : null}
      </figcaption>
    </figure>
  );
}
