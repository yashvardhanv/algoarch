import { useEffect, useRef, useState } from 'react';

interface Tick { id: string; title: string; at: number }

// A thin vertical rail on the left edge: fills and carries a marker as you read, with a tick per section.
export function ReadingRail({ sections }: { sections: { id: string; title: string }[] }) {
  const rail = useRef<HTMLDivElement>(null);
  const [ticks, setTicks] = useState<Tick[]>([]);

  useEffect(() => {
    const column = document.querySelector('.reader-main-column') as HTMLElement | null;
    if (!column || sections.length < 2) return;
    let raf = 0;

    const progress = () => {
      const top = column.getBoundingClientRect().top + window.scrollY;
      const span = Math.max(1, column.offsetHeight - window.innerHeight * 0.55);
      const p = Math.min(1, Math.max(0, (window.scrollY + 120 - top) / span));
      rail.current?.style.setProperty('--p', String(p));
    };
    const measure = () => {
      const top = column.getBoundingClientRect().top + window.scrollY;
      const h = Math.max(1, column.offsetHeight);
      setTicks(sections.map(s => {
        const el = document.getElementById(s.id);
        const y = el ? el.getBoundingClientRect().top + window.scrollY - top : 0;
        return { id: s.id, title: s.title, at: Math.min(1, Math.max(0, y / h)) };
      }));
      progress();
    };
    const onScroll = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(progress); };

    measure();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', measure);
    // code editors and widgets change the page height as they load
    const ro = 'ResizeObserver' in window ? new ResizeObserver(measure) : null;
    ro?.observe(column);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', measure);
      ro?.disconnect();
    };
  }, [sections]);

  if (sections.length < 2) return null;
  return (
    <div className="rd-rail" ref={rail} role="navigation" aria-label="Reading progress">
      <div className="rd-rail-fill" />
      <div className="rd-rail-dot" aria-hidden="true" />
      {ticks.map(t => (
        <button key={t.id} type="button" className="rd-rail-tick" style={{ top: `${t.at * 100}%` }} title={t.title} aria-label={`Jump to ${t.title}`}
          onClick={() => document.getElementById(t.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })} />
      ))}
    </div>
  );
}
