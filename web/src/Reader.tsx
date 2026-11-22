import { useEffect, useMemo, useRef, useState } from 'react';
import { Blocks, Inlines } from './blocks';
import { HostContext } from './context';
import { MonacoEditor } from './monaco';
import { ReadingRail } from './ReadingRail';
import type { LessonPayload, ReaderHost, Section } from './types';
import { fetchLesson, renderMarkdown, runJs, typesetMath } from './support';

type Tab = 'lesson' | 'videos' | 'drills' | 'playground' | 'articles' | 'repos';

interface TocItem { id: string; title: string; level: 2 | 3 }

export function Reader({ host }: { host: ReaderHost }) {
  const [data, setData] = useState<LessonPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('lesson');
  const [, force] = useState(0);
  const [activeToc, setActiveToc] = useState<string>('');
  const articleRef = useRef<HTMLElement>(null);

  useEffect(() => {
    let alive = true;
    setData(null); setError(null); setTab('lesson');
    fetchLesson(host.lessonId)
      .then(d => { if (alive) { setData(d); window.scrollTo({ top: 0 }); } })
      .catch(e => alive && setError(String(e.message || e)));
    return () => { alive = false; };
  }, [host.lessonId]);

  const guide = useMemo(() => (data ? renderMarkdown(data.guide) : { html: '', headings: [] as TocItem[] }), [data]);
  const toc: TocItem[] = useMemo(() => {
    if (!data) return [];
    const fromDoc = (data.document?.sections || []).map((s: Section) => ({ id: s.anchor, title: s.title, level: 2 as const }));
    return [...fromDoc, ...guide.headings];
  }, [data, guide]);

  const railSections = useMemo(() => {
    if (data?.document?.sections?.length) return data.document.sections.map((s: Section) => ({ id: s.anchor, title: s.title }));
    return toc.filter(t => t.level === 2);
  }, [data, toc]);

  useEffect(() => {
    if (tab !== 'lesson' || toc.length === 0) return;
    const onScroll = () => {
      let cur = toc[0].id;
      for (const t of toc) {
        const el = document.getElementById(t.id);
        if (el && el.getBoundingClientRect().top <= 120) cur = t.id;
      }
      setActiveToc(cur);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [toc, tab]);

  useEffect(() => { if (tab === 'lesson') typesetMath(articleRef.current); }, [data, tab]);

  if (error) return <div className="rd-state">Could not load this lesson. {error}</div>;
  if (!data) return <div className="rd-state">Loading lesson</div>;

  const { lesson, track } = data;
  const refresh = () => force(n => n + 1);
  const done = host.isCompleted();
  const marked = host.isBookmarked();
  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: 'lesson', label: 'Lesson' },
    { id: 'videos', label: 'Lectures', count: data.videos.length },
    { id: 'drills', label: 'Drills', count: data.drills.length },
    { id: 'playground', label: 'Playground' },
    { id: 'articles', label: 'Articles', count: data.articles.length },
    { id: 'repos', label: 'Repos', count: data.repos.length }
  ];

  return (
    <HostContext.Provider value={host}>
    <div className="rd-root">
      <div className="reader-header">
        <button className="btn-back" type="button" onClick={host.onBack}>Back to overview</button>
        <div className="reader-meta-bar">
          {track && <span>{track.name}</span>}
          <span>{'★'.repeat(lesson.stars)}{'☆'.repeat(5 - lesson.stars)}</span>
          <span>{lesson.duration}</span>
          {lesson.isNew && <span className="rd-new">Advanced</span>}
        </div>
        <div className="reader-controls">
          <button type="button" className={`btn-action-icon${marked ? ' bookmarked' : ''}`} onClick={() => { host.onToggleBookmark(lesson.id); refresh(); }}>
            {marked ? 'Bookmarked' : 'Bookmark'}
          </button>
          <button type="button" className="btn-action-ai" onClick={host.onAskMentor}>Ask mentor</button>
          <button type="button" className="btn-action-primary" onClick={() => { host.onToggleComplete(lesson.id); refresh(); }}>
            {done ? 'Completed' : 'Mark completed'}
          </button>
        </div>
      </div>

      <div className="reader-tabs-nav" role="tablist">
        {tabs.map(t => (
          <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} className={`reader-tab${tab === t.id ? ' active' : ''}`} onClick={() => setTab(t.id)}>
            {t.label}{t.count ? ` (${t.count})` : ''}
          </button>
        ))}
      </div>

      {tab === 'lesson' && <ReadingRail key={host.lessonId} sections={railSections} />}

      {tab === 'lesson' && (
        <div className="reader-layout">
          <aside className="reader-toc-rail">
            <div className="toc-rail-title">On this page</div>
            <nav className="reader-toc-list">
              {toc.length === 0 && <span className="rd-muted">Single section</span>}
              {toc.map(t => (
                <a key={t.id} href={`#${t.id}`} className={`toc-link${t.level === 3 ? ' is-h3' : ''}${activeToc === t.id ? ' active' : ''}`}
                  onClick={e => { e.preventDefault(); document.getElementById(t.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }}>
                  {t.title}
                </a>
              ))}
            </nav>
          </aside>
          <div className="reader-main-column">
            {data.document ? (
              <div className="rd-doc">
                <h1>{data.document.title || lesson.title}</h1>
                {data.document.lede.length > 0 && <p className="rd-lede"><Inlines nodes={data.document.lede} /></p>}
                {data.document.sections.map(s => (
                  <section key={s.anchor} id={s.anchor} className="rd-section reveal">
                    <header className="rd-section-head">
                      {s.number && <span className="rd-section-num">{s.number}</span>}
                      <div>
                        <h2>{s.title}</h2>
                        {s.subtitle && <p className="rd-sub">{s.subtitle}</p>}
                      </div>
                    </header>
                    <Blocks blocks={s.blocks} />
                  </section>
                ))}
                {guide.html && <h2 className="rd-guide-title">Written guide</h2>}
              </div>
            ) : (
              <h1 className="rd-title">{lesson.title}</h1>
            )}
            <article ref={articleRef} className="markdown-content" dangerouslySetInnerHTML={{ __html: guide.html }} />
          </div>
        </div>
      )}

      {tab === 'videos' && <Videos data={data} />}
      {tab === 'drills' && <Drills data={data} lessonId={lesson.id} />}
      {tab === 'playground' && <Playground data={data} host={host} />}
      {tab === 'articles' && <Links kind="articles" data={data} />}
      {tab === 'repos' && <Links kind="repos" data={data} />}

      <div className="reader-footer">
        {data.prev ? <button type="button" className="btn-nav-lesson" onClick={() => host.onNavigate(data.prev!.id, data.prev!.trackId)}>Previous: {data.prev.title}</button> : <span />}
        {data.next ? <button type="button" className="btn-nav-lesson" onClick={() => host.onNavigate(data.next!.id, data.next!.trackId)}>Next: {data.next.title}</button> : <span />}
      </div>
    </div>
    </HostContext.Provider>
  );
}

function Videos({ data }: { data: LessonPayload }) {
  const [playing, setPlaying] = useState<string | null>(null);
  if (data.videos.length === 0) return <div className="rd-state">No lectures are linked to this lesson yet.</div>;
  return (
    <div className="tab-pane">
      {playing && (
        <div className="featured-video-player">
          <div className="video-embed-container">
            <iframe title="Lecture" src={`https://www.youtube.com/embed/${playing}?autoplay=1`} allow="autoplay; encrypted-media; picture-in-picture" allowFullScreen />
          </div>
        </div>
      )}
      <div className="lesson-videos-grid">
        {data.videos.map(v => (
          <div key={v.id} className="video-card" onClick={() => setPlaying(v.youtubeId)}>
            <div className="video-thumb-wrapper">
              <img className="v-thumb" loading="lazy" alt="" src={v.thumbnail || `https://img.youtube.com/vi/${v.youtubeId}/hqdefault.jpg`} />
              <span className="v-duration">{v.duration}</span>
            </div>
            <div className="video-meta">
              <span className="v-channel">{v.channel}</span>
              <h4 className="v-title">{v.title}</h4>
              <p className="v-desc">{v.description}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Drills({ data, lessonId }: { data: LessonPayload; lessonId: string }) {
  const key = `algoarch-drills-${lessonId}`;
  const [checked, setChecked] = useState<number[]>(() => { try { return JSON.parse(localStorage.getItem(key) || '[]'); } catch { return []; } });
  const toggle = (i: number) => {
    const next = checked.includes(i) ? checked.filter(x => x !== i) : [...checked, i];
    setChecked(next);
    try { localStorage.setItem(key, JSON.stringify(next)); } catch { /* storage unavailable */ }
  };
  if (data.drills.length === 0) return <div className="rd-state">This lesson has no drills.</div>;
  const pct = Math.round((checked.length / data.drills.length) * 100);
  return (
    <div className="tab-pane">
      <div className="drills-progress-card">
        <div className="drills-header-row"><span>Practiced</span><span className="drills-counter">{checked.length} / {data.drills.length}</span></div>
        <div className="drills-progress-track"><div className="drills-progress-fill" style={{ width: `${pct}%` }} /></div>
      </div>
      <div className="homework-drills-list">
        {data.drills.map((d, i) => (
          <label key={i} className={`drill-card${checked.includes(i) ? ' practiced' : ''}`}>
            <div className="drill-top-row">
              <input type="checkbox" className="drill-check-input" checked={checked.includes(i)} onChange={() => toggle(i)} />
              <div className="drill-content">
                <div className="drill-title">{d.title}</div>
                {d.notes && <div className="drill-notes">{d.notes}</div>}
              </div>
            </div>
          </label>
        ))}
      </div>
    </div>
  );
}

function Playground({ data, host }: { data: LessonPayload; host: ReaderHost }) {
  const starter = data.lab?.code || '// Write JavaScript here and run it in the browser.\nconsole.log("hello");';
  const [lang, setLang] = useState(data.lab ? 'python' : 'javascript');
  const [code, setCode] = useState(starter);
  const [out, setOut] = useState('');
  const allowed = host.can('monacoRun');

  const run = async () => {
    if (!allowed) { host.openPricing(); return; }
    if (lang !== 'javascript') { setOut(`${lang} cannot run in the browser. Download the lab and run it locally.`); return; }
    setOut('Running');
    const r = await runJs(code, 5000);
    setOut((r.logs.join('\n') || '(no output)') + (r.error ? `\n\nError: ${r.error}` : ''));
  };

  return (
    <div className="tab-pane">
      <div className="playground-card">
        <div className="playground-topbar">
          <div className="pg-file-meta">
            <span className="pg-filename">{data.lab?.fileName || 'scratch.js'}</span>
            <select className="pg-lang-picker" value={lang} onChange={e => setLang(e.target.value)}>
              <option value="python">Python</option>
              <option value="javascript">JavaScript</option>
            </select>
            {!allowed && <span className="pg-monaco-badge">Read-only on the Free plan</span>}
          </div>
          <div className="pg-btn-group">
            <button type="button" className="btn-pg-ghost" onClick={() => navigator.clipboard.writeText(code)}>Copy</button>
            <button type="button" className="btn-pg-ghost" onClick={() => setCode(starter)}>Reset</button>
            <button type="button" className="btn-pg-primary" onClick={run}>Run</button>
          </div>
        </div>
        <MonacoEditor value={code} language={lang} readOnly={!allowed} onChange={setCode} minHeight={320} maxHeight={520} />
        <div className="playground-console">
          <div className="console-header"><span>Output</span></div>
          <pre className="console-output">{out || 'Press Run to execute JavaScript.'}</pre>
        </div>
      </div>
    </div>
  );
}

function Links({ kind, data }: { kind: 'articles' | 'repos'; data: LessonPayload }) {
  const items = kind === 'articles' ? data.articles : data.repos;
  if (items.length === 0) return <div className="rd-state">Nothing listed yet.</div>;
  return (
    <div className="tab-pane">
      <div className={kind === 'articles' ? 'articles-grid' : 'repos-grid'}>
        {items.map((it: any, i: number) => (
          <a key={i} className={kind === 'articles' ? 'article-card' : 'repo-card'} href={it.url || it.link || '#'} target="_blank" rel="noopener noreferrer">
            <div className="article-header"><span>{it.org || it.language || ''}</span><span>{it.readTime || it.stars || ''}</span></div>
            <div className="article-title">{it.title || it.name}</div>
            {(it.description || it.desc) && <p className="article-desc">{it.description || it.desc}</p>}
          </a>
        ))}
      </div>
    </div>
  );
}
