import { useEffect, useMemo, useRef, useState } from 'react';
import { Inlines } from './inline';
import type { Inline } from './types';

export interface QuizData {
  patterns: string[];
  core: string[];
  bank: { statement: Inline[]; constraint: string; answer: string; why: Inline[] }[];
}
interface Rep { p: string; ok: boolean; ms: number }

const KEY = 'dsa-drill-v1';
const load = (): Rep[] => { try { return JSON.parse(localStorage.getItem(KEY) || '[]'); } catch { return []; } };

export function Quiz({ data, title }: { data: QuizData; title?: string | null }) {
  const [mode, setMode] = useState<'core' | 'all'>('core');
  const [hist, setHist] = useState<Rep[]>(load);
  const [cur, setCur] = useState<number | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const t0 = useRef(0);
  const tick = useRef<number | null>(null);

  const pool = useMemo(() => data.bank.map((q, i) => ({ q, i })).filter(({ q }) => mode === 'all' || data.core.includes(q.answer)), [data, mode]);
  const options = mode === 'core' ? data.core : data.patterns;
  const q = cur !== null ? data.bank[cur] : null;
  const answered = chosen !== null;

  const stop = () => { if (tick.current) { clearInterval(tick.current); tick.current = null; } };
  useEffect(() => stop, []);

  const next = () => {
    let pick = pool[Math.floor(Math.random() * pool.length)];
    while (pool.length > 1 && pick.i === cur) pick = pool[Math.floor(Math.random() * pool.length)];
    setCur(pick.i); setChosen(null); setElapsed(0);
    t0.current = performance.now();
    stop();
    tick.current = window.setInterval(() => setElapsed(performance.now() - t0.current), 100);
  };

  const answer = (p: string) => {
    if (!q || answered) return;
    stop();
    const ms = performance.now() - t0.current;
    setElapsed(ms); setChosen(p);
    const h = [...hist, { p: q.answer, ok: p === q.answer, ms }];
    setHist(h);
    try { localStorage.setItem(KEY, JSON.stringify(h.slice(-500))); } catch { /* storage unavailable */ }
  };

  const reset = () => { setHist([]); try { localStorage.setItem(KEY, '[]'); } catch { /* storage unavailable */ } };

  const stats = useMemo(() => {
    if (!hist.length) return null;
    const ok = hist.filter(h => h.ok).length;
    const times = hist.map(h => h.ms).sort((a, b) => a - b);
    const last = hist.slice(-10);
    const by: Record<string, number[]> = {};
    hist.forEach(h => { (by[h.p] ||= []).push(h.ms + (h.ok ? 0 : 20000)); });
    let worst: string | null = null, worstV = -1;
    for (const p of Object.keys(by)) {
      if (by[p].length < 2) continue;
      const m = by[p].reduce((a, b) => a + b, 0) / by[p].length;
      if (m > worstV) { worstV = m; worst = p; }
    }
    return { reps: hist.length, acc: Math.round((100 * ok) / hist.length), med: times[Math.floor(times.length / 2)] / 1000, last: `${last.filter(h => h.ok).length}/${last.length}`, slow: worst };
  }, [hist]);

  return (
    <div className="rd-quiz">
      <div className="rd-quiz-bar">
        <span className="rd-quiz-title">{title || 'Timed drill'}</span>
        <label className="rd-quiz-mode">
          Patterns
          <select value={mode} onChange={e => { setMode(e.target.value as 'core' | 'all'); setCur(null); setChosen(null); stop(); setElapsed(0); }}>
            <option value="core">Core {data.core.length}</option>
            <option value="all">All {data.patterns.length}</option>
          </select>
        </label>
        <span className="rd-quiz-clock" aria-live="off">{(elapsed / 1000).toFixed(1)} s</span>
      </div>
      <div className="rd-quiz-body">
        {!q && <p className="rd-quiz-intro">A problem statement appears and the clock starts. Name the pattern as fast as you can.</p>}
        {q && (
          <>
            <p className="rd-quiz-stmt"><Inlines nodes={q.statement} /></p>
            {q.constraint && <p className="rd-quiz-con">Constraints: {q.constraint}</p>}
            <div className="rd-quiz-opts" role="group" aria-label="Pick the pattern">
              {options.map(p => (
                <button key={p} type="button" disabled={answered}
                  className={answered ? (p === q.answer ? 'right' : p === chosen ? 'wrong' : '') : ''}
                  onClick={() => answer(p)}>{p}</button>
              ))}
            </div>
            {answered && (
              <div className="rd-quiz-why">
                <strong>{chosen === q.answer ? 'Correct' : 'Answer'}: {q.answer}</strong> in {(elapsed / 1000).toFixed(1)} s
                <p><Inlines nodes={q.why} /></p>
              </div>
            )}
          </>
        )}
        <div className="rd-quiz-actions">
          {!q && <button type="button" className="btn-pg-primary" onClick={next}>Start</button>}
          {q && <button type="button" className="btn-pg-primary" disabled={!answered} onClick={next}>Next</button>}
          <button type="button" className="btn-pg-ghost" onClick={reset}>Reset history</button>
        </div>
      </div>
      <dl className="rd-quiz-stats">
        <div><dt>Reps</dt><dd>{stats ? stats.reps : 0}</dd></div>
        <div><dt>Accuracy</dt><dd>{stats ? stats.acc + '%' : '-'}</dd></div>
        <div><dt>Median time</dt><dd>{stats ? stats.med.toFixed(1) + ' s' : '-'}</dd></div>
        <div><dt>Last 10</dt><dd>{stats ? stats.last : '-'}</dd></div>
        <div><dt>Slowest pattern</dt><dd>{stats && stats.slow ? stats.slow : '-'}</dd></div>
      </dl>
    </div>
  );
}
