// Runs Python (CPython compiled to WASM via Pyodide) inside a Web Worker, so a runaway loop
// can be terminated without freezing the page. Pyodide is downloaded on the first run only.
import { PY_HARNESS } from './pyHarness';

const PYODIDE_BASE = 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/';

export interface PyTest { ok: boolean; label: string; ms: number; err: string }
export interface PyResult { stdout: string; error: string | null; tests: PyTest[]; wallMs: number }

const WORKER_SRC = `
let py = null;
self.onmessage = async (e) => {
  const m = e.data;
  try {
    if (m.type === 'init') {
      importScripts('${PYODIDE_BASE}pyodide.js');
      py = await loadPyodide({ indexURL: '${PYODIDE_BASE}' });
      py.runPython(m.harness);
      self.postMessage({ type: 'ready' });
    } else if (m.type === 'run') {
      py.globals.set('__user_src', m.src);
      py.globals.set('__test_src', m.tests || '');
      const raw = py.runPython('_bench_run(__user_src, __test_src)');
      self.postMessage({ type: 'result', id: m.id, payload: JSON.parse(raw) });
    }
  } catch (err) {
    self.postMessage({ type: 'fail', id: m.id, message: String((err && err.message) || err) });
  }
};`;

let worker: Worker | null = null;
let ready: Promise<void> | null = null;
let seq = 0;

function boot(): Promise<void> {
  if (ready) return ready;
  const url = URL.createObjectURL(new Blob([WORKER_SRC], { type: 'text/javascript' }));
  const w = new Worker(url);
  worker = w;
  ready = new Promise<void>((resolve, reject) => {
    const onMsg = (e: MessageEvent) => {
      if (e.data.type === 'ready') { w.removeEventListener('message', onMsg); resolve(); }
      else if (e.data.type === 'fail') { w.removeEventListener('message', onMsg); reject(new Error(e.data.message)); }
    };
    w.addEventListener('message', onMsg);
    w.addEventListener('error', ev => reject(new Error(ev.message || 'Python worker failed')), { once: true });
    w.postMessage({ type: 'init', harness: PY_HARNESS });
  });
  ready.catch(() => reset());
  return ready;
}

function reset() {
  worker?.terminate();
  worker = null;
  ready = null;
}

export async function runPython(src: string, tests: string, opts: { timeoutMs?: number; onStatus?: (s: string) => void } = {}): Promise<PyResult> {
  const timeoutMs = opts.timeoutMs ?? 20000;
  const started = performance.now();
  if (!ready) opts.onStatus?.('Loading Python (about 10 MB, cached after the first run)');
  await boot();
  opts.onStatus?.('Running');
  const w = worker!;
  const id = ++seq;
  return new Promise<PyResult>((resolve, reject) => {
    const timer = setTimeout(() => { reset(); reject(new Error(`Time limit exceeded (${Math.round(timeoutMs / 1000)} s). The Python runtime was restarted.`)); }, timeoutMs);
    const onMsg = (e: MessageEvent) => {
      if (e.data.id !== id) return;
      w.removeEventListener('message', onMsg);
      clearTimeout(timer);
      if (e.data.type === 'result') resolve({ ...e.data.payload, wallMs: performance.now() - started });
      else reject(new Error(e.data.message));
    };
    w.addEventListener('message', onMsg);
    w.postMessage({ type: 'run', id, src, tests });
  });
}

// Number of top-level statements in a test block (for the button label).
export function countTests(tests: string): number {
  return tests.split('\n').filter(l => l.length && !' )]}'.includes(l[0]) && l.trim()[0] !== '#').length;
}
