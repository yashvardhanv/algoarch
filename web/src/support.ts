// Small helpers: API client, markdown rendering with sanitising, and the JS sandbox runner.
import type { LessonPayload } from './types';

export async function fetchLesson(id: string): Promise<LessonPayload> {
  const headers: Record<string, string> = {};
  try {
    const token = localStorage.getItem('algoarch_token');
    if (token) headers.Authorization = `Bearer ${token}`;
  } catch { /* storage unavailable */ }
  const res = await fetch(`/api/lessons/${encodeURIComponent(id)}`, { headers });
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'section';

export interface Heading { id: string; title: string; level: 2 | 3 }

// Renders markdown (via the host's global `marked`), strips anything executable, assigns heading ids.
export function renderMarkdown(md: string): { html: string; headings: Heading[] } {
  const marked = (window as any).marked;
  const raw: string = marked && md ? marked.parse(md) : '';
  const doc = new DOMParser().parseFromString(raw, 'text/html');
  doc.querySelectorAll('script, style, iframe, object, embed, link, meta, form').forEach(n => n.remove());
  doc.body.querySelectorAll('*').forEach(el => {
    for (const attr of Array.from(el.attributes)) {
      const name = attr.name.toLowerCase();
      if (name.startsWith('on') || name === 'style' || (['href', 'src', 'xlink:href'].includes(name) && /^\s*javascript:/i.test(attr.value))) el.removeAttribute(attr.name);
    }
    if (el.tagName === 'A' && /^https?:/i.test(el.getAttribute('href') || '')) { el.setAttribute('target', '_blank'); el.setAttribute('rel', 'noopener noreferrer'); }
  });
  // The reader renders the lesson title itself; drop a leading duplicate H1 from the guide.
  const firstEl = doc.body.firstElementChild;
  if (firstEl && firstEl.tagName === 'H1') firstEl.remove();
  const headings: Heading[] = [];
  const seen = new Set<string>();
  doc.body.querySelectorAll('h2, h3').forEach(h => {
    const title = (h.textContent || '').split('$').join('').trim();
    if (!title || title.toLowerCase() === 'table of contents') return;
    let id = `g-${slug(title)}`;
    for (let i = 2; seen.has(id); i++) id = `g-${slug(title)}-${i}`;
    seen.add(id);
    h.id = id;
    headings.push({ id, title, level: h.tagName === 'H2' ? 2 : 3 });
  });
  return { html: doc.body.innerHTML, headings };
}

export function typesetMath(el: HTMLElement | null) {
  const render = (window as any).renderMathInElement;
  if (!el || !render) return;
  try {
    render(el, { delimiters: [{ left: '$$', right: '$$', display: true }, { left: '$', right: '$', display: false }], throwOnError: false });
  } catch { /* math is progressive enhancement */ }
}

export function runJs(code: string, timeoutMs: number): Promise<{ logs: string[]; error: string | null }> {
  return new Promise(resolve => {
    const src =
      'const logs=[];const fmt=a=>a.map(x=>typeof x==="string"?x:(()=>{try{return JSON.stringify(x)}catch(e){return String(x)}})()).join(" ");' +
      'console.log=(...a)=>logs.push(fmt(a));console.error=console.warn=console.info=console.log;' +
      'self.onmessage=e=>{let error=null;try{(0,eval)(e.data)}catch(err){error=String(err&&err.stack||err)}self.postMessage({logs,error})};';
    const url = URL.createObjectURL(new Blob([src], { type: 'text/javascript' }));
    const worker = new Worker(url);
    const finish = (r: { logs: string[]; error: string | null }) => { clearTimeout(timer); worker.terminate(); URL.revokeObjectURL(url); resolve(r); };
    const timer = setTimeout(() => finish({ logs: [], error: `Time limit exceeded (${timeoutMs} ms)` }), timeoutMs);
    worker.onmessage = e => finish(e.data);
    worker.onerror = e => finish({ logs: [], error: e.message || 'Runtime error' });
    worker.postMessage(code);
  });
}
