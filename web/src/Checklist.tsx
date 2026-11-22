import { useMemo, useState } from 'react';
import { Inlines } from './inline';
import type { Inline } from './types';

export interface ChecklistData {
  items: { text: string; points: number }[];
  deductions: { label: string; points: number }[];
  max: number;
  bands: { min: number; label: string }[];
  verdicts: { min: number; tone: string; content: Inline[] }[];
}

// Replace {score}, {gap}, {ded} placeholders inside an inline tree.
function fill(nodes: Inline[], vars: Record<string, string>): Inline[] {
  return nodes.map(n => {
    if (typeof n === 'string') return n.replace(/\{(score|gap|ded|raw)\}/g, (_m, k) => vars[k] ?? '');
    if ('c' in n) return { ...n, c: fill(n.c, vars) } as Inline;
    return n;
  });
}

const firstAtLeast = <T extends { min: number }>(list: T[], v: number): T | undefined => list.find(x => v >= x.min) ?? list[list.length - 1];

export function Checklist({ data, title }: { data: ChecklistData; title?: string | null }) {
  const [got, setGot] = useState<boolean[]>(() => data.items.map(() => false));
  const [ded, setDed] = useState<boolean[]>(() => data.deductions.map(() => false));

  const r = useMemo(() => {
    const raw = data.items.reduce((n, it, i) => n + (got[i] ? it.points : 0), 0);
    const deducted = data.deductions.reduce((n, d, i) => n + (ded[i] ? d.points : 0), 0);
    const fin = Math.max(0, raw - deducted);
    const missed = data.items.map((it, i) => ({ it, i })).filter(x => !got[x.i]).sort((a, b) => b.it.points - a.it.points)[0];
    const band = firstAtLeast([...data.bands].sort((a, b) => b.min - a.min), fin);
    const verdict = firstAtLeast([...data.verdicts].sort((a, b) => b.min - a.min), fin);
    return { raw, deducted, fin, missed, band, verdict };
  }, [data, got, ded]);

  const reset = () => { setGot(data.items.map(() => false)); setDed(data.deductions.map(() => false)); };
  const tone = r.fin >= (data.bands[0]?.min ?? Infinity) ? 'good' : r.band && r.band.min >= (data.bands[1]?.min ?? 0) ? 'warn' : 'bad';

  return (
    <div className="rd-check">
      <div className="rd-check-bar">
        <span className="rd-check-title">{title || 'Rubric'}</span>
        <span className="rd-check-score">{r.fin} / {data.max}</span>
      </div>
      <div className="rd-check-body">
        <ul className="rd-check-list">
          {data.items.map((it, i) => (
            <li key={i}>
              <label className={got[i] ? 'got' : ''}>
                <input type="checkbox" checked={got[i]} onChange={() => setGot(g => g.map((v, j) => (j === i ? !v : v)))} />
                <span className="rd-check-text">{it.text}</span>
                <span className="rd-check-pts">{it.points}</span>
              </label>
            </li>
          ))}
        </ul>
        <dl className="rd-check-readout">
          <div><dt>Score</dt><dd className={tone}>{r.fin} / {data.max}</dd></div>
          <div><dt>Band</dt><dd>{r.band ? r.band.label : '-'}</dd></div>
          <div><dt>Biggest gap</dt><dd className={r.missed ? 'bad' : 'good'}>{r.missed ? r.missed.it.text : 'none'}</dd></div>
          <div><dt>Deductions</dt><dd className={r.deducted ? 'bad' : 'good'}>{r.deducted ? `-${r.deducted}` : 'none'}</dd></div>
        </dl>
        {r.verdict && (
          <div className={`rd-check-verdict ${r.verdict.tone}`} aria-live="polite">
            <Inlines nodes={fill(r.verdict.content, { score: String(r.fin), gap: r.missed ? r.missed.it.text : 'nothing', ded: String(r.deducted), raw: String(r.raw) })} />
          </div>
        )}
      </div>
      <div className="rd-check-foot">
        {data.deductions.map((d, i) => (
          <label key={i}>
            <input type="checkbox" checked={ded[i]} onChange={() => setDed(x => x.map((v, j) => (j === i ? !v : v)))} />
            {d.label} (-{d.points})
          </label>
        ))}
        <button type="button" className="btn-pg-ghost" onClick={reset}>Reset</button>
      </div>
    </div>
  );
}
