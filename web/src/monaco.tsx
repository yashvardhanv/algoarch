import { useEffect, useRef, useState } from 'react';

const BASE = 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min';
let monacoPromise: Promise<any> | null = null;

// Monaco is loaded on demand from the CDN, only when a code block scrolls near the viewport.
export function loadMonaco(): Promise<any> {
  const w = window as any;
  if (w.monaco) return Promise.resolve(w.monaco);
  if (monacoPromise) return monacoPromise;
  monacoPromise = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = `${BASE}/vs/loader.min.js`;
    s.onload = () => {
      w.MonacoEnvironment = {
        getWorkerUrl: () => URL.createObjectURL(new Blob(
          [`self.MonacoEnvironment={baseUrl:'${BASE}/'};importScripts('${BASE}/vs/base/worker/workerMain.js');`],
          { type: 'text/javascript' }
        ))
      };
      w.require.config({ paths: { vs: `${BASE}/vs` } });
      w.require(['vs/editor/editor.main'], () => resolve(w.monaco), reject);
    };
    s.onerror = () => reject(new Error('Monaco failed to load'));
    document.head.appendChild(s);
  });
  monacoPromise.catch(() => { monacoPromise = null; });
  return monacoPromise;
}

// Resolve a CSS design token (OKLCH) to #rrggbb, which is what Monaco themes require.
function tokenToHex(name: string): string {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const c = document.createElement('canvas');
  c.width = c.height = 1;
  const ctx = c.getContext('2d', { willReadFrequently: true })!;
  ctx.fillStyle = '#000';
  ctx.fillStyle = raw;
  ctx.fillRect(0, 0, 1, 1);
  const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data;
  return '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('');
}

function applyTheme(monaco: any) {
  const dark = document.documentElement.dataset.theme === 'dark';
  monaco.editor.defineTheme('algoarch', {
    base: dark ? 'vs-dark' : 'vs',
    inherit: true,
    rules: [],
    colors: {
      'editor.background': tokenToHex('--well'),
      'editor.foreground': tokenToHex('--ink'),
      'editor.lineHighlightBackground': tokenToHex('--well-2'),
      'editor.lineHighlightBorder': tokenToHex('--well-2'),
      'editorLineNumber.foreground': tokenToHex('--ink-3'),
      'editorLineNumber.activeForeground': tokenToHex('--ink-2'),
      'editorGutter.background': tokenToHex('--well'),
      'editorWidget.background': tokenToHex('--paper'),
      'scrollbarSlider.background': tokenToHex('--line-strong') + '66'
    }
  });
  monaco.editor.setTheme('algoarch');
}

export function guessLanguage(text: string): string {
  if (/^\s*(def |class |import |from \w+ import |for .+ in .+:|print\()/m.test(text)) return 'python';
  if (/^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|WITH|EXPLAIN|ALTER)\b/im.test(text)) return 'sql';
  if (/^\s*(func |package |type \w+ struct)/m.test(text)) return 'go';
  if (/^\s*[{[]/.test(text) && /"\w+"\s*:/.test(text)) return 'json';
  if (/^\s*(const |let |function |=>)/m.test(text)) return 'javascript';
  return 'plaintext';
}

interface Props {
  value: string;
  language?: string;
  readOnly?: boolean;
  onChange?: (v: string) => void;
  minHeight?: number;
  maxHeight?: number;
  lineNumbers?: boolean;
}

export function MonacoEditor({ value, language = 'plaintext', readOnly = false, onChange, minHeight = 56, maxHeight = 520, lineNumbers }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const editorRef = useRef<any>(null);
  const [near, setNear] = useState(false);
  const [failed, setFailed] = useState(false);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  // mount only when near the viewport
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    if (!('IntersectionObserver' in window)) { setNear(true); return; }
    const io = new IntersectionObserver(entries => { if (entries.some(e => e.isIntersecting)) { setNear(true); io.disconnect(); } }, { rootMargin: '600px' });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!near || !host.current) return;
    let disposed = false;
    let themeObserver: MutationObserver | null = null;
    loadMonaco().then(monaco => {
      if (disposed || !host.current) return;
      applyTheme(monaco);
      const editor = monaco.editor.create(host.current, {
        value, language, readOnly,
        theme: 'algoarch',
        automaticLayout: true,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        fontSize: 13,
        lineHeight: 21,
        fontFamily: "'JetBrains Mono', ui-monospace, Consolas, monospace",
        tabSize: 4,
        padding: { top: 12, bottom: 12 },
        lineNumbers: (lineNumbers ?? !readOnly) ? 'on' : 'off',
        glyphMargin: false,
        folding: false,
        lineDecorationsWidth: readOnly ? 12 : 8,
        renderLineHighlight: readOnly ? 'none' : 'line',
        overviewRulerLanes: 0,
        hideCursorInOverviewRuler: true,
        scrollbar: { alwaysConsumeMouseWheel: false, vertical: 'auto', horizontal: 'auto', useShadows: false },
        domReadOnly: readOnly,
        contextmenu: !readOnly,
        wordWrap: 'off'
      });
      editorRef.current = editor;
      const fit = () => {
        const h = Math.min(maxHeight, Math.max(minHeight, editor.getContentHeight()));
        host.current!.style.height = h + 'px';
        editor.layout();
      };
      editor.onDidContentSizeChange(fit);
      fit();
      editor.onDidChangeModelContent(() => onChangeRef.current?.(editor.getValue()));
      themeObserver = new MutationObserver(() => applyTheme(monaco));
      themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    }).catch(() => !disposed && setFailed(true));
    return () => {
      disposed = true;
      themeObserver?.disconnect();
      editorRef.current?.dispose();
      editorRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [near, language, readOnly]);

  // external value changes (for example Reset)
  useEffect(() => {
    const ed = editorRef.current;
    if (ed && ed.getValue() !== value) ed.setValue(value);
  }, [value]);

  if (failed) {
    return readOnly
      ? <pre className="rd-fallback"><code>{value}</code></pre>
      : <textarea className="rd-fallback-edit" spellCheck={false} value={value} onChange={e => onChange?.(e.target.value)} />;
  }
  return <div ref={host} className="rd-monaco" style={{ height: minHeight }} />;
}
