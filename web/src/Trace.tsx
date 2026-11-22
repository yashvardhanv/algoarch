import { useEffect, useRef, useState } from 'react';
import { Inlines } from './inline';
import type { Inline } from './types';

export interface TraceData {
  values: string[];
  frames: { ptrs: Record<string, number>; win: [number, number] | null; marks: Record<string, string>; note: string; stat: Inline[] }[];
}

export function Trace({ data, title }: { data: TraceData; title?: string | null }) {
  const { values, frames } = data;
  const [i, setI] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(520);
  const logRef = useRef<HTMLOListElement>(null);
  const last = frames.length - 1;

  useEffect(() => {
    if (!playing) return;
    const t = window.setInterval(() => {
      setI(cur => {
        if (cur >= last) { setPlaying(false); return cur; }
        return cur + 1;
      });
    }, speed);
    return () => window.clearInterval(t);
  }, [playing, speed, last]);

  // keep the current log line visible without moving the page
  useEffect(() => {
    const el = logRef.current?.children[i] as HTMLElement | undefined;
    const box = logRef.current;
    if (el && box) {
      const top = el.offsetTop - box.offsetTop;
      if (top < box.scrollTop) box.scrollTop = top;
      else if (top + el.offsetHeight > box.scrollTop + box.clientHeight) box.scrollTop = top + el.offsetHeight - box.clientHeight;
    }
  }, [i]);

  const go = (n: number) => { setPlaying(false); setI(Math.max(0, Math.min(last, n))); };
  const f = frames[i];

  return (
    <div className="rd-trace">
      <div className="rd-trace-bar">
        <span className="rd-trace-title">{title || 'Trace'}</span>
        <span className="rd-trace-step" aria-live="polite">Step {i + 1} of {frames.length}</span>
      </div>
      <div className="rd-trace-body">
        <div className="rd-trace-cells" role="img" aria-label={f.note || `Step ${i + 1}`}>
          {values.map((v, k) => {
            const names = Object.keys(f.ptrs).filter(p => f.ptrs[p] === k);
            const cls = ['rd-trace-cell'];
            if (f.win && k >= f.win[0] && k <= f.win[1]) cls.push('win');
            if (f.marks[k]) cls.push(f.marks[k]);
            if (names.length) cls.push(names[0].toLowerCase() === 'l' ? 'l' : 'r');
            return (
              <div key={k} className={cls.join(' ')}>
                {names.length > 0 && <span className="rd-trace-pin">{names.join('/')}</span>}
                {v}
                <span className="rd-trace-ix">{k}</span>
              </div>
            );
          })}
        </div>
        {f.stat.length > 0 && <p className="rd-trace-stat"><Inlines nodes={f.stat} /></p>}
        <ol className="rd-trace-log" ref={logRef}>
          {frames.map((fr, ix) => (
            <li key={ix} className={ix === i ? 'now' : ''}>
              <button type="button" onClick={() => go(ix)}>
                <span className="k">{String(ix).padStart(2, '0')}</span> {fr.note}
              </button>
            </li>
          ))}
        </ol>
      </div>
      <div className="rd-trace-controls">
        <button type="button" className="btn-pg-ghost" onClick={() => go(i - 1)} disabled={i === 0}>Previous</button>
        <button type="button" className="btn-pg-primary" onClick={() => { if (i >= last) setI(0); setPlaying(p => !p); }}>{playing ? 'Pause' : 'Play'}</button>
        <button type="button" className="btn-pg-ghost" onClick={() => go(i + 1)} disabled={i === last}>Next</button>
        <button type="button" className="btn-pg-ghost" onClick={() => go(0)}>Reset</button>
        <label className="rd-trace-speed">
          Speed
          <input type="range" min={60} max={1200} step={20} value={1260 - speed} onChange={e => setSpeed(1260 - Number(e.target.value))} />
        </label>
      </div>
    </div>
  );
}
