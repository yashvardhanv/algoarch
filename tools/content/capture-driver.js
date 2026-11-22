// Runs INSIDE an original lesson page (same-origin iframe) and records every interactive panel
// as data: the controls it exposes and the rendered result for each reachable control state.
// Dev-only; nothing here ships to users. Output is turned into lesson data by convert.js.
(function () {
  const WS = /\s+/g;
  const ATTRS = new Set(['class', 'style', 'viewBox', 'x', 'y', 'cx', 'cy', 'r', 'rx', 'ry', 'width', 'height', 'd', 'points', 'fill', 'stroke',
    'stroke-width', 'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin', 'transform', 'x1', 'y1', 'x2', 'y2', 'text-anchor', 'dominant-baseline',
    'font-size', 'font-weight', 'font-family', 'opacity', 'fill-opacity', 'stroke-opacity', 'offset', 'colspan', 'rowspan', 'title', 'marker-end',
    'marker-start', 'preserveAspectRatio', 'stop-color', 'stop-opacity', 'rotate', 'dx', 'dy']);
  const SKIP = new Set(['SCRIPT', 'STYLE', 'INPUT', 'SELECT', 'TEXTAREA', 'NOSCRIPT', 'IFRAME', 'OBJECT', 'LINK', 'META']);
  // Pages can contain handlers that never return; report what is about to run so a hang can be located.
  const note = (msg) => { try { fetch('/save?name=_progress', { method: 'POST', body: msg, keepalive: true }); } catch (e) { /* ignore */ } };
  const sleep = (w, ms) => new Promise(r => w.setTimeout(r, ms));
  const norm = (s) => String(s == null ? '' : s).replace(WS, ' ').trim();

  function actElements(body) {
    const out = [];
    const w = body.ownerDocument.defaultView;
    const all = body.querySelectorAll('*');
    for (const el of all) {
      if (SKIP.has(el.tagName) || el.tagName === 'CANVAS') continue;
      const isBtn = el.tagName === 'BUTTON';
      let pointer = false;
      if (!isBtn) {
        const cs = w.getComputedStyle(el);
        pointer = cs.cursor === 'pointer' && cs.display !== 'none';
        if (pointer && el.closest('button')) pointer = false;
        // keep only the innermost pointer element of a nest
        if (pointer && [...el.querySelectorAll('*')].some(c => c !== el && w.getComputedStyle(c).cursor === 'pointer')) pointer = false;
      }
      if (isBtn || pointer) out.push(el);
    }
    return out;
  }

  function serialize(w, root, acts) {
    const ser = (el) => {
      if (el.nodeType !== 1) return null;
      if (SKIP.has(el.tagName)) return null;
      const cs = w.getComputedStyle(el);
      if (cs.display === 'none') return null;
      const tag = el.tagName.toLowerCase();
      if (tag === 'canvas') {
        try {
          const src = el.toDataURL('image/png');
          return src.length < 300000 ? { t: 'img', a: { src, width: String(el.width), height: String(el.height) } } : null;
        } catch (e) { return null; }
      }
      const node = { t: tag };
      const a = {};
      for (const at of el.attributes) {
        if (ATTRS.has(at.name) && at.value.length < 600) a[at.name] = at.value;
      }
      const ai = acts.indexOf(el);
      if (ai >= 0) a.act = String(ai);
      if (Object.keys(a).length) node.a = a;
      const kids = [];
      const nodes = el.childNodes;
      let prevInline = false;
      for (let i = 0; i < nodes.length; i++) {
        const n = nodes[i];
        if (n.nodeType === 3) {
          const s = n.nodeValue.replace(WS, ' ');
          if (!s.trim()) { if (kids.length && prevInline && i < nodes.length - 1) kids.push(' '); continue; }
          kids.push(s); prevInline = true;
        } else if (n.nodeType === 1) {
          const k = ser(n);
          if (k) { kids.push(k); prevInline = /^inline/.test(w.getComputedStyle(n).display); }
        }
      }
      if (kids.length) node.k = kids;
      return node;
    };
    return ser(root);
  }

  function snapshot(w, panel) {
    const body = panel.querySelector('.panel-body');
    const bar = panel.querySelector('.panel-bar');
    const spans = bar ? bar.querySelectorAll('span') : [];
    const status = spans.length > 1 ? norm(spans[spans.length - 1].textContent) : '';
    const acts = body ? actElements(body) : [];
    return { s: status, b: body ? serialize(w, body, acts) : null, acts: acts.length };
  }

  function sampleRange(min, max, step, def) {
    const n = Math.round((max - min) / step);
    let vals = [];
    if (n <= 8) { for (let i = 0; i <= n; i++) vals.push(min + i * step); }
    else {
      for (let i = 0; i < 9; i++) vals.push(Math.round((min + (i * (max - min)) / 8) / step) * step);
    }
    vals.push(def);
    vals = [...new Set(vals.map(v => +(+v).toFixed(6)))].sort((x, y) => x - y);
    return vals;
  }

  function setValue(w, el, v) {
    if (el.type === 'checkbox') el.checked = !!v; else el.value = String(v);
    el.dispatchEvent(new w.Event('input', { bubbles: true }));
    el.dispatchEvent(new w.Event('change', { bubbles: true }));
  }

  const labelOf = (el) => {
    const l = el.closest('label');
    if (l) {
      const c = l.cloneNode(true);
      c.querySelectorAll('input,select,output,.val,[id$="-v"],b').forEach(x => x.remove());
      const t = norm(c.textContent);
      if (t) return t;
    }
    let p = el.previousSibling;
    while (p) { const t = norm(p.textContent); if (t) return t; p = p.previousSibling; }
    return el.id || 'value';
  };

  async function capturePanel(w, panel, index, page) {
    const bar = panel.querySelector('.panel-bar');
    const titleSpan = bar && bar.querySelector('span');
    const out = {
      i: index, page,
      title: bar ? norm(bar.textContent) : '',
      label: titleSpan ? norm(titleSpan.textContent) : '',
      controls: [], buttons: [], frames: [], grid: null, seq: null, acts: [], bodyActs: [], base: 0, warnings: []
    };
    const ctlRoot = panel.querySelector('.controls');
    const seen = new Map();
    const frameIdx = (snap) => {
      const key = JSON.stringify([snap.s, snap.b]);
      if (!seen.has(key)) { seen.set(key, out.frames.length); out.frames.push({ s: snap.s, b: snap.b }); }
      return seen.get(key);
    };

    // controls
    const inputs = []; // one setter per control, parallel to out.controls
    const buttons = [];
    const radios = new Map();
    if (ctlRoot) {
      for (const el of ctlRoot.querySelectorAll('input,select,button')) {
        if (el.tagName === 'BUTTON') { buttons.push(el); continue; }
        if (el.tagName === 'SELECT') {
          const o = [...el.options].map(op => ({ v: op.value, t: norm(op.textContent) }));
          out.controls.push({ k: 'select', label: labelOf(el), options: o, def: el.value });
          inputs.push((v) => setValue(w, el, v));
        } else if (el.type === 'range') {
          const min = +el.min || 0, max = el.max === '' ? 100 : +el.max, step = +el.step || 1, def = +el.value;
          out.controls.push({ k: 'range', label: labelOf(el), min, max, step, def, samples: sampleRange(min, max, step, def) });
          inputs.push((v) => setValue(w, el, v));
        } else if (el.type === 'checkbox') {
          out.controls.push({ k: 'check', label: labelOf(el), def: el.checked });
          inputs.push((v) => setValue(w, el, v));
        } else if (el.type === 'radio') {
          let g = radios.get(el.name);
          if (!g) {
            g = { control: { k: 'select', label: el.name || 'option', options: [], def: '' }, els: new Map() };
            radios.set(el.name, g);
            out.controls.push(g.control);
            inputs.push((v) => { const r = g.els.get(String(v)); if (r) { r.checked = true; r.dispatchEvent(new w.Event('input', { bubbles: true })); r.dispatchEvent(new w.Event('change', { bubbles: true })); r.click(); } });
          }
          const lab = el.closest('label');
          const t = norm(lab ? lab.textContent : (el.nextSibling ? el.nextSibling.textContent : el.value)) || el.value;
          g.control.options.push({ v: el.value, t });
          g.els.set(String(el.value), el);
          if (el.checked) g.control.def = el.value;
        } else { out.warnings.push('unsupported input ' + el.type); }
      }
    }
    out.base = frameIdx(snapshot(w, panel));

    // grid over ranges / selects / checkboxes (cap total combinations)
    if (inputs.length) {
      const domains = out.controls.map(c => c.k === 'range' ? c.samples : c.k === 'select' ? c.options.map(o => o.v) : [false, true]);
      let total = domains.reduce((n, d) => n * d.length, 1);
      let guard = 0;
      while (total > 160 && guard++ < 40) {
        const ci = domains.map((d, i) => [d.length, i]).sort((a, b) => b[0] - a[0])[0][1];
        const c = out.controls[ci];
        if (c.k === 'range' && c.samples.length > 3) {
          const keep = c.samples.length > 5 ? 5 : 3;
          const picks = new Set([0, c.samples.length - 1]);
          for (let j = 1; j < keep - 1; j++) picks.add(Math.round((j * (c.samples.length - 1)) / (keep - 1)));
          const defIdx = c.samples.indexOf(c.def); if (defIdx >= 0 && picks.size < c.samples.length - 1) picks.add(defIdx);
          c.samples = [...picks].sort((a, b) => a - b).map(i => c.samples[i]);
          domains[ci] = c.samples;
        } else break;
        total = domains.reduce((n, d) => n * d.length, 1);
      }
      if (total > 400) { out.warnings.push('grid too large: ' + total); }
      else {
        const grid = [];
        const idx = new Array(domains.length).fill(0);
        for (let n = 0; n < total; n++) {
          const cellKey = (out.page || '') + '|' + index + '|grid' + idx.join(',');
          if (window.__skip && window.__skip.has(cellKey)) { grid.push(out.base); for (let i = domains.length - 1; i >= 0; i--) { if (++idx[i] < domains[i].length) break; idx[i] = 0; } continue; }
          note('cell ' + cellKey + ' = ' + domains.map((d, i) => d[idx[i]]).join(','));
          domains.forEach((d, i) => inputs[i](d[idx[i]]));
          await sleep(w, 12);
          grid.push(frameIdx(snapshot(w, panel)));
          for (let i = domains.length - 1; i >= 0; i--) { if (++idx[i] < domains[i].length) break; idx[i] = 0; }
        }
        out.grid = grid;
        out.controls.forEach((c, i) => inputs[i](c.def));
        await sleep(w, 20);
      }
    }

    // buttons in the controls row: reset / step / actions
    const live = () => buttons.filter(b => !b.disabled);
    const role = (b) => { const t = norm(b.textContent); return /reset|clear|start over|restart|again|new$/i.test(t) ? 'reset' : /step|next|advance|tick|›|→|»|forward|\+1/i.test(t) ? 'step' : 'action'; };
    buttons.forEach(b => out.buttons.push({ label: norm(b.textContent), role: role(b) }));
    const resetBtn = buttons.find(b => role(b) === 'reset');
    const stepBtn = buttons.find(b => role(b) === 'step');
    const click = async (b, ms) => {
      const key = (out.page || '') + '|' + index + '|' + norm(b.textContent);
      if (window.__skip && window.__skip.has(key)) return;
      note('click ' + key);
      b.click(); await sleep(w, ms || 60);
    };
    if (resetBtn) { await click(resetBtn, 60); out.base = frameIdx(snapshot(w, panel)); }
    if (stepBtn) {
      const seq = [out.base];
      for (let n = 0; n < 60; n++) {
        if (stepBtn.disabled) break;
        await click(stepBtn, 70);
        const f = frameIdx(snapshot(w, panel));
        if (f === seq[seq.length - 1]) break;
        seq.push(f);
      }
      out.seq = seq;
      if (resetBtn) await click(resetBtn, 60);
    }
    for (let bi = 0; bi < buttons.length; bi++) {
      const b = buttons[bi];
      if (b === resetBtn || b === stepBtn || b.disabled) continue;
      if (resetBtn) await click(resetBtn, 40);
      await click(b, 350);
      out.acts.push({ label: norm(b.textContent), frame: frameIdx(snapshot(w, panel)) });
    }
    if (resetBtn) await click(resetBtn, 60);

    // clickable elements inside the body: click each from the base state
    const body = panel.querySelector('.panel-body');
    if (body) {
      const count = Math.min(actElements(body).length, 40);
      for (let i = 0; i < count; i++) {
        if (resetBtn) await click(resetBtn, 40);
        const list = actElements(body);
        if (!list[i]) break;
        note('act ' + (out.page || '') + '|' + index + '|' + i);
        if (window.__skip && window.__skip.has((out.page || '') + '|' + index + '|act' + i)) continue;
        list[i].click();
        await sleep(w, 120);
        out.bodyActs.push({ i, frame: frameIdx(snapshot(w, panel)) });
      }
      if (resetBtn) await click(resetBtn, 60);
    }
    return out;
  }

  window.__captureDoc = async function (w, page) {
    w.alert = () => {}; w.confirm = () => true; w.prompt = () => '';
    const panels = [...w.document.querySelectorAll('.panel')];
    const out = [];
    for (let i = 0; i < panels.length; i++) {
      // traces, rubrics and the drill already ship as dedicated components
      const t = norm((panels[i].querySelector('.panel-bar') || {}).textContent);
      if (panels[i].querySelector('.tr-cells, .drill') || /follows the trace|rubric|click what you|checklist/i.test(t)) { out.push({ i, title: t, skipped: true }); continue; }
      if (window.__skip && window.__skip.has(page + '|' + i + '|panel')) { out.push({ i, title: t, skipped: true, error: 'skipped: page handler hangs' }); continue; }
      note('panel ' + page + '|' + i);
      try { const r = await capturePanel(w, panels[i], i, page); out.push(r); }
      catch (e) { out.push({ i, title: norm((panels[i].querySelector('.panel-bar') || {}).textContent), error: String(e && e.message || e) }); }
    }
    return out;
  };
})();
