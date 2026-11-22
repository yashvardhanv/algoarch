import { createRoot, type Root } from 'react-dom/client';
import { Reader } from './Reader';
import type { ReaderHost } from './types';
import './reader.css';

declare global {
  interface Window { AlgoArchReader: { mount(el: HTMLElement, host: ReaderHost): void; unmount(): void } }
}

let root: Root | null = null;
let mountedEl: HTMLElement | null = null;

window.AlgoArchReader = {
  mount(el, host) {
    if (!root || mountedEl !== el) {
      root?.unmount();
      root = createRoot(el);
      mountedEl = el;
    }
    root.render(<Reader host={host} />);
  },
  unmount() {
    root?.unmount();
    root = null;
    mountedEl = null;
  }
};
