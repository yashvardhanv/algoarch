import { useMemo, useState } from 'react';

export interface ScorecardData {
  axes: { name: string; levels: string[] }[];
  target: number | null;
  max: number;
  criticalAxes: number[];
  criticalNote: string | null;
  storageKey: string;
}
interface Entry { total: number; scores: number[] }

export function Scorecard({ data, title }: { data: ScorecardData; title?: string | null }) {
  const n = data.axes.length;
  const [scores, setScores] = useState<number[]>(() => new Array(n).fill(0));
  const [hist, setHist] = useState<Entry[]>(() => { try { return JSON.parse(localStorage.getItem(data.storageKey) || '[]'); } catch { return []; } });
  const [note, setNote] = useState('');

  const s = useMemo(() => {
    const filled = scores.filter(Boolean).length;
    const total = scores.reduce((a, b) => a + b, 0);
    let worst = -1, worstV = 5;
    scores.forEach((v, i) => { if (v && v < worstV) { worstV = v; worst = i; } });
    const avg = hist.length ? hist.reduce((a, h) => a + h.total, 0) / hist.length : null;
    let status = '';
    if (filled < n) status = `${n - filled} axes unscored`;
    else if (data.criticalAxes.some(i => scores[i] < 3) && data.criticalNote) status = data.criticalNote;
    else if (data.target !== null && total >= data.target) status = 'At target';
    else if (data.target !== null) status = `Below the ${data.target}/${data.max} target`;
    return { filled, total, worst, worstV, avg, status };
  }, [scores, hist, n, data]);

  const persist = (h: Entry[]) => { try { localStorage.setItem(data.storageKey, JSON.stringify(h.slice(-60))); } catch { /* storage unavailable */ } };
  const save = () => {
    if (s.filled < n) { setNote('Score every axis before saving'); return; }
    const h = [...hist, { total: s.total, scores: [...scores] }];
    setHist(h); persist(h);
    setScores(new Array(n).fill(0));
    setNote(`Saved. ${h.length} mock${h.length === 1 ? '' : 's'} logged`);
  };
  const clear = () => { setHist([]); try { localStorage.removeItem(data.storageKey); } catch { /* storage unavailable */ } setNote(''); };

  return (
    <div className="rd-score">
      <div className="rd-check-bar"><span className="rd-check-title">{title || 'Scorecard'}</span></div>
      <table className="rd-score-table">
        <thead><tr><th>Axis</th><th>Score</th><th>What that level means</th></tr></thead>
        <tbody>
          {data.axes.map((a, i) => (
            <tr key={a.name}>
              <td>{a.name}</td>
              <td>
                <div className="rd-score-opts" role="group" aria-label={`${a.name} score`}>
                  {[1, 2, 3, 4].map(v => (
                    <button key={v} type="button" aria-pressed={scores[i] === v} className={scores[i] === v ? 'sel' : ''}
                      onClick={() => setScores(sc => sc.map((x, j) => (j === i ? v : x)))}>{v}</button>
                  ))}
                </div>
              </td>
              <td className="rd-score-desc">{scores[i] ? a.levels[scores[i] - 1] : '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <dl className="rd-check-readout">
        <div><dt>Total</dt><dd className={s.filled === n ? (data.target !== null && s.total >= data.target ? 'good' : 'bad') : ''}>{s.total}{s.filled < n ? '*' : ''}</dd></div>
        <div><dt>Target</dt><dd>{data.target ?? '-'} / {data.max}</dd></div>
        <div><dt>Weakest axis</dt><dd className={s.worstV < 3 && s.worst >= 0 ? 'bad' : ''}>{s.worst >= 0 ? `${data.axes[s.worst].name} (${s.worstV})` : '-'}</dd></div>
        <div><dt>Mocks logged</dt><dd>{hist.length}</dd></div>
        <div><dt>Average</dt><dd>{s.avg !== null ? s.avg.toFixed(1) : '-'}</dd></div>
      </dl>
      <div className="rd-check-foot">
        <button type="button" className="btn-pg-primary" onClick={save}>Save this mock</button>
        <button type="button" className="btn-pg-ghost" onClick={clear}>Clear all history</button>
        <span className="rd-score-note" aria-live="polite">{note || s.status}</span>
      </div>
    </div>
  );
}
