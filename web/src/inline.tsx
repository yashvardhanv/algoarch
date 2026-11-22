import { Fragment } from 'react';
import type { Inline } from './types';

export function Inlines({ nodes }: { nodes: Inline[] }) {
  return (
    <>
      {nodes.map((n, i) => {
        if (typeof n === 'string') return <Fragment key={i}>{n}</Fragment>;
        switch (n.t) {
          case 'br': return <br key={i} />;
          case 'link': return <a key={i} href={n.href} target="_blank" rel="noopener noreferrer"><Inlines nodes={n.c} /></a>;
          case 'strong': return <strong key={i}><Inlines nodes={n.c} /></strong>;
          case 'em': return <em key={i}><Inlines nodes={n.c} /></em>;
          case 'code': return <code key={i}><Inlines nodes={n.c} /></code>;
          case 'kbd': return <kbd key={i}><Inlines nodes={n.c} /></kbd>;
          case 'sub': return <sub key={i}><Inlines nodes={n.c} /></sub>;
          case 'sup': return <sup key={i}><Inlines nodes={n.c} /></sup>;
          case 'phrase': return <code key={i} className="phrase"><Inlines nodes={n.c} /></code>;
          case 'quote': return <q key={i}><Inlines nodes={n.c} /></q>;
          default: return null;
        }
      })}
    </>
  );
}
