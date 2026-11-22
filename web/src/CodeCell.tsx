import { useState } from 'react';
import { MonacoEditor } from './monaco';
import { runPython, countTests, type PyResult } from './python';
import { useHost } from './context';

interface Cell { title: string; badge?: string | null; language: string; starter: string; tests?: string }

export function CodeCell({ cell }: { cell: Cell }) {
  const host = useHost();
  const allowed = host ? host.can('monacoRun') : true;
  const [code, setCode] = useState(cell.starter);
  const [result, setResult] = useState<(PyResult & { withTests: boolean }) | null>(null);
  const [status, setStatus] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const nTests = cell.tests ? countTests(cell.tests) : 0;

  const run = async (withTests: boolean) => {
    if (!allowed) { host?.openPricing(); return; }
    setBusy(true); setError(null); setResult(null);
    try {
      const r = await runPython(code, withTests ? cell.tests || '' : '', { onStatus: setStatus });
      setResult({ ...r, withTests });
      setStatus('');
    } catch (e: any) {
      setError(e.message || String(e));
      setStatus('');
    } finally { setBusy(false); }
  };

  const reset = () => { setCode(cell.starter); setResult(null); setError(null); setStatus(''); };
  const passed = result ? result.tests.filter(t => t.ok).length : 0;

  return (
    <div className="rd-cell">
      <div className="rd-cell-bar">
        <span className="rd-cell-title">{cell.title}</span>
        <span className="rd-cell-badge">{allowed ? (cell.badge || 'Editable, runs in your browser') : 'Read-only on the Free plan'}</span>
      </div>
      <MonacoEditor value={code} language="python" readOnly={!allowed} onChange={setCode} minHeight={72} maxHeight={420} />
      <div className="rd-cell-actions">
        <button type="button" className="btn-pg-primary" disabled={busy} onClick={() => run(false)}>Run</button>
        {nTests > 0 && <button type="button" className="btn-pg-ghost" disabled={busy} onClick={() => run(true)}>Run {nTests} test{nTests === 1 ? '' : 's'}</button>}
        <button type="button" className="btn-pg-ghost" disabled={busy} onClick={reset}>Reset</button>
        <span className="rd-cell-status" aria-live="polite">
          {status}
          {result && !status && (result.error ? <span className="rd-fail">Raised an error</span>
            : result.withTests && result.tests.length
              ? <span className={passed === result.tests.length ? 'rd-pass' : 'rd-fail'}>{passed}/{result.tests.length} passed</span>
              : <span className="rd-pass">Ran in {Math.round(result.wallMs)} ms</span>)}
        </span>
      </div>
      {(result || error) && (
        <pre className="rd-cell-out">
          {error && <span className="rd-fail">{error}</span>}
          {result && result.stdout && <>{result.stdout.replace(/\n+$/, '')}{'\n'}</>}
          {result && result.error && <span className="rd-fail">{result.error.trim()}</span>}
          {result && result.withTests && result.tests.map((t, i) => (
            <span key={i} className="rd-test">
              {t.ok ? <span className="rd-pass">  ✓ </span> : <span className="rd-fail">  ✗ </span>}
              <span className={t.ok ? 'rd-dim' : 'rd-fail'}>{t.label}</span>
              {!t.ok && <span className="rd-fail">{'\n      ' + t.err}</span>}
              {'\n'}
            </span>
          ))}
          {result && !result.error && !result.stdout && !result.withTests && <span className="rd-dim">(no output: this cell defines things, so run the tests)</span>}
        </pre>
      )}
    </div>
  );
}
