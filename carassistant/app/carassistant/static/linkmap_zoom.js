/* The zoomable connection map (Plugins -> Connections): plugins on the left, every channel of the Plugin API in the middle (also the open ones that nobody
   uses yet), on the right the place where it lands. The mouse wheel zooms at the pointer, a drag moves, two fingers pinch; a click on a plugin, a channel,
   a place or a line opens everything about it below: the explanation, the connections, the data with its raw value and the small history with dates.
   Everything that comes from a plugin (names, values) is put in with textContent, never as HTML. No timers except one refresh every 20 seconds. */
(function () {
  var root = document.getElementById('lmz');
  if (!root) return;
  var model;
  try { model = JSON.parse(root.getAttribute('data-model') || '{}'); } catch (e) { return; }
  var base = root.getAttribute('data-base'), canRaw = root.getAttribute('data-raw') === '1';
  var stage = root.querySelector('.lmz-stage'), svg = root.querySelector('.lmz-svg'), detail = document.getElementById('lmz-detail');
  if (!stage || !svg || !model.groups) return;
  var NS = 'http://www.w3.org/2000/svg';
  function T(k) { return root.getAttribute('data-t-' + k) || ''; }
  function fmt(s, o) { return s.replace(/\{(\w+)\}/g, function (m, k) { return o[k] !== undefined ? o[k] : m; }); }
  function el(name, attrs, text) {
    var n = document.createElementNS(NS, name);
    for (var k in attrs) { n.setAttribute(k, attrs[k]); }
    if (text !== undefined) { n.textContent = text; }
    return n;
  }
  function cut(s, n) { s = String(s || ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; }
  function wrap(text, max, lines) {
    var words = String(text || '').split(/\s+/), out = [], cur = '';
    words.forEach(function (w) {
      if ((cur + ' ' + w).trim().length > max && cur) { out.push(cur); cur = w; } else { cur = (cur + ' ' + w).trim(); }
    });
    if (cur) { out.push(cur); }
    if (out.length > lines) { out = out.slice(0, lines); out[lines - 1] = cut(out[lines - 1] + '…', max); }
    return out;
  }
  var icons = model.icons || {};
  function icon(name, x, y, size, cls) {
    var g = el('g', { transform: 'translate(' + x + ' ' + y + ') scale(' + (size / 24) + ')', 'class': cls || 'lmz-ico' });
    g.appendChild(el('path', { d: icons[name] || icons.puzzle || '' }));
    return g;
  }

  /* ------------------------------------------------------------------ layout: plugins | channels in groups | places */
  var PW = 232, PH = 66, PGAP = 16, GX = PW + 200, GW = 340, DX = GX + GW + 110, DW = 272, ROW = 27, HEAD = 44, GPAD = 10, GGAP = 30, DH = 92;
  var pos = { plug: {}, ch: {}, grp: {}, place: {} }, cy = 0;
  /* what is connected comes first (the places with traffic on top, inside a place the used channels first); the open ones follow below */
  var groups = model.groups.map(function (g, i) {
    var used = g.channels.filter(function (c) { return c.state !== 'open'; }), open = g.channels.filter(function (c) { return c.state === 'open'; });
    return { g: g, i: i, view: Object.assign({}, g, { channels: used.concat(open) }) };
  }).sort(function (a, b) { return (b.g.n_used > 0) - (a.g.n_used > 0) || a.i - b.i; }).map(function (x) { return x.view; });
  groups.forEach(function (g) {
    var h = Math.max(DH, HEAD + g.channels.length * ROW + GPAD);
    pos.grp[g.area] = { x: GX, y: cy, w: GW, h: h };
    g.channels.forEach(function (c, i) { pos.ch[c.key] = { x: GX, y: cy + HEAD + i * ROW, w: GW, h: ROW, cy: cy + HEAD + i * ROW + ROW / 2 }; });
    pos.place[g.area] = { x: DX, y: cy + h / 2 - DH / 2, w: DW, h: DH };
    cy += h + GGAP;
  });
  var worldH = cy - GGAP;
  var want = {};
  model.plugins.forEach(function (p) {
    var ys = model.edges.filter(function (e) { return e.plugin === p.id && pos.ch[e.channel]; }).map(function (e) { return pos.ch[e.channel].cy; });
    want[p.id] = ys.length ? Math.min.apply(null, ys) : null;  /* at the top of its first channel: the lines run down from there */
  });
  var order = model.plugins.filter(function (p) { return want[p.id] !== null; }).sort(function (a, b) { return want[a.id] - want[b.id]; })
    .concat(model.plugins.filter(function (p) { return want[p.id] === null; }));
  var py = 0;
  order.forEach(function (p) {
    var y = want[p.id] === null ? py : Math.max(py, want[p.id] - PH / 2);
    pos.plug[p.id] = { x: 0, y: y, w: PW, h: PH };
    py = y + PH + PGAP;
  });
  worldH = Math.max(worldH, py - PGAP);
  var worldW = DX + DW;

  /* ------------------------------------------------------------------ drawing */
  var defs = el('defs', {});
  for (var i = 1; i <= 7; i++) {
    var m = el('marker', { id: 'lmz-m' + i, viewBox: '0 0 10 10', refX: '8', refY: '5', markerWidth: '6', markerHeight: '6', orient: 'auto-start-reverse' });
    m.appendChild(el('path', { d: 'M1 1L9 5L1 9z', fill: 'var(--chip-' + i + ')' }));
    defs.appendChild(m);
  }
  var mo = el('marker', { id: 'lmz-mo', viewBox: '0 0 10 10', refX: '8', refY: '5', markerWidth: '6', markerHeight: '6', orient: 'auto' });
  mo.appendChild(el('path', { d: 'M1 1L9 5L1 9z', fill: 'var(--dim)' }));
  defs.appendChild(mo);
  svg.appendChild(defs);
  var world = el('g', { 'class': 'lmz-world' });
  svg.appendChild(world);
  var layerOut = el('g', {}), layerWires = el('g', {}), layerNodes = el('g', {});
  world.appendChild(layerOut); world.appendChild(layerWires); world.appendChild(layerNodes);

  function heading(x, text) { layerNodes.appendChild(el('text', { x: x, y: -16, 'class': 'lmz-col-h', 'font-size': 13 }, text)); }
  heading(0, T('plugins')); heading(GX, T('channels')); heading(DX, T('places'));

  var tintOf = {}, els = { plug: {}, ch: {}, grp: {}, place: {}, wires: [], outs: {} };
  model.plugins.forEach(function (p) { tintOf[p.id] = p.tint; });

  function node(kind, id, x, y, w, h, label) {
    var g = el('g', { 'class': 'lmz-node', 'data-kind': kind, 'data-id': id, tabindex: '0', role: 'button', 'aria-label': label });
    return g;
  }

  /* the groups with their channels */
  groups.forEach(function (g) {
    var b = pos.grp[g.area], gr = node('g', g.area, b.x, b.y, b.w, b.h, g.name);
    gr.classList.add('lmz-group', g.state);
    gr.appendChild(el('rect', { x: b.x, y: b.y, width: b.w, height: b.h, rx: 16, 'class': 'lmz-box' }));
    gr.appendChild(icon(g.icon, b.x + 14, b.y + 12, 20, 'lmz-ico ' + g.chip));
    gr.appendChild(el('text', { x: b.x + 44, y: b.y + 27, 'class': 'lmz-title', 'font-size': 16 }, cut(g.name, 30)));
    gr.appendChild(el('text', { x: b.x + b.w - 14, y: b.y + 27, 'class': 'lmz-meta', 'font-size': 12, 'text-anchor': 'end' }, fmt(T('counts_short'), { used: g.n_used, open: g.n_open })));
    layerNodes.appendChild(gr);
    els.grp[g.area] = gr;
    g.channels.forEach(function (c) {
      var r = pos.ch[c.key], row = node('c', c.key, r.x, r.y, r.w, r.h, c.label);
      row.classList.add('lmz-ch', c.state);
      row.appendChild(el('title', {}, c.label + ' - ' + c.explain));
      row.appendChild(el('rect', { x: r.x + 6, y: r.y + 1, width: r.w - 12, height: r.h - 2, rx: 8, 'class': 'lmz-row' }));
      row.appendChild(el('circle', { cx: r.x + 20, cy: r.cy, r: 5, 'class': 'lmz-dot' }));
      row.appendChild(el('text', { x: r.x + 34, y: r.cy + 4.5, 'class': 'lmz-label', 'font-size': 13 }, cut(c.label, 34)));
      var gx = r.x + r.w - 20;
      if (c.ago) { row.appendChild(el('text', { x: gx, y: r.cy + 4, 'class': 'lmz-ago', 'font-size': 11, 'text-anchor': 'end' }, c.ago)); }
      var dx = r.x + r.w - (c.ago ? 100 : 22);
      c.dirs.slice().sort().forEach(function (d, k) {  /* a triangle to the right = the plugin sends, to the left = the plugin reads */
        var tx = dx - k * 14, p = d === 'set' ? 'M' + (tx - 4) + ' ' + (r.cy - 4) + 'L' + (tx + 4) + ' ' + r.cy + 'L' + (tx - 4) + ' ' + (r.cy + 4) + 'z' : 'M' + (tx + 4) + ' ' + (r.cy - 4) + 'L' + (tx - 4) + ' ' + r.cy + 'L' + (tx + 4) + ' ' + (r.cy + 4) + 'z';
        row.appendChild(el('path', { d: p, 'class': 'lmz-dir ' + d }));
      });
      layerNodes.appendChild(row);
      els.ch[c.key] = row;
    });
    /* the place where it lands */
    var pl = pos.place[g.area], pn = node('d', g.area, pl.x, pl.y, pl.w, pl.h, g.name);
    pn.classList.add('lmz-place', g.state);
    pn.appendChild(el('rect', { x: pl.x, y: pl.y, width: pl.w, height: pl.h, rx: 16, 'class': 'lmz-box' }));
    pn.appendChild(icon(g.icon, pl.x + 14, pl.y + 14, 22, 'lmz-ico ' + g.chip));
    pn.appendChild(el('text', { x: pl.x + 46, y: pl.y + 31, 'class': 'lmz-title', 'font-size': 15 }, cut(g.name, 27)));
    wrap(g.explain, 34, 3).forEach(function (line, k) { pn.appendChild(el('text', { x: pl.x + 14, y: pl.y + 52 + k * 15, 'class': 'lmz-meta', 'font-size': 11.5 }, line)); });
    if (g.ha) { pn.appendChild(el('text', { x: pl.x + pl.w - 12, y: pl.y + 29, 'class': 'lmz-ha', 'font-size': 11, 'text-anchor': 'end' }, 'HA')); }
    layerNodes.appendChild(pn);
    els.place[g.area] = pn;
    var out = el('path', { d: 'M' + (b.x + b.w) + ' ' + (b.y + b.h / 2) + 'L' + (pl.x - 4) + ' ' + (pl.y + pl.h / 2), 'class': 'lmz-out ' + g.state, 'marker-end': 'url(#lmz-mo)' });
    layerOut.appendChild(out);
    els.outs[g.area] = out;
  });

  /* the plugins */
  model.plugins.forEach(function (p) {
    var b = pos.plug[p.id], pn = node('p', p.id, b.x, b.y, b.w, b.h, p.name);
    pn.classList.add('lmz-plugin', 't' + p.tint, p.state);
    if (!p.active) { pn.classList.add('off'); }
    pn.appendChild(el('rect', { x: b.x, y: b.y, width: b.w, height: b.h, rx: 16, 'class': 'lmz-box' }));
    pn.appendChild(el('rect', { x: b.x, y: b.y + 10, width: 4, height: b.h - 20, rx: 2, 'class': 'lmz-tintbar' }));
    pn.appendChild(icon(p.icon, b.x + 16, b.y + 14, 22, 'lmz-ico'));
    pn.appendChild(el('text', { x: b.x + 48, y: b.y + 28, 'class': 'lmz-title', 'font-size': 15 }, cut(p.name, 20)));
    var meta = el('text', { x: b.x + 16, y: b.y + 52, 'class': 'lmz-meta', 'font-size': 11.5 }, cut(p.meta, 36));
    meta.setAttribute('data-meta', '1');
    pn.appendChild(meta);
    pn.appendChild(el('circle', { cx: b.x + b.w - 16, cy: b.y + 22, r: 5, 'class': 'lmz-dot' }));
    layerNodes.appendChild(pn);
    els.plug[p.id] = pn;
  });

  /* the lines: one per plugin, channel and direction */
  model.edges.forEach(function (e, idx) {
    var a = pos.plug[e.plugin], c = pos.ch[e.channel];
    if (!a || !c) return;
    var off = e.dir === 'get' ? 4 : -4, x1 = a.x + a.w, y1 = a.y + a.h / 2 + off, x2 = c.x + 2, y2 = c.cy, dx = Math.max(60, (x2 - x1) * 0.55);
    var d = 'M' + x1 + ' ' + y1 + ' C' + (x1 + dx) + ' ' + y1 + ' ' + (x2 - dx) + ' ' + y2 + ' ' + x2 + ' ' + y2;
    var t = tintOf[e.plugin] || 1;
    var path = el('path', { d: d, 'class': 'lmz-w t' + t + ' ' + e.state + ' ' + e.dir, 'data-plugin': e.plugin, 'data-channel': e.channel });
    path.setAttribute(e.dir === 'get' ? 'marker-start' : 'marker-end', 'url(#lmz-m' + t + ')');
    var hit = el('path', { d: d, 'class': 'lmz-hit', 'data-kind': 'w', 'data-plugin': e.plugin, 'data-channel': e.channel });
    layerWires.appendChild(path); layerWires.appendChild(hit);
    els.wires.push({ el: path, edge: e, idx: idx });
  });

  /* ------------------------------------------------------------------ zoom and move */
  var view = { k: 1, x: 0, y: 0 }, KMIN = 0.18, KMAX = 4;
  function apply() { world.setAttribute('transform', 'translate(' + view.x + ' ' + view.y + ') scale(' + view.k + ')'); stage.setAttribute('data-zoom', view.k < 0.5 ? 'far' : view.k < 1 ? 'mid' : 'near'); }
  function size() { var r = stage.getBoundingClientRect(); return { w: r.width, h: r.height, l: r.left, t: r.top }; }
  function zoomAt(px, py, factor) {
    var k = Math.min(KMAX, Math.max(KMIN, view.k * factor)), f = k / view.k;
    view.x = px - (px - view.x) * f; view.y = py - (py - view.y) * f; view.k = k; apply();
  }
  function fitWidth() { var s = size(), k = Math.min(1, Math.max(KMIN, (s.w - 32) / worldW)); view = { k: k, x: (s.w - worldW * k) / 2, y: 56 * k }; apply(); }
  function fitAll() { var s = size(), k = Math.min(1, Math.max(KMIN, Math.min((s.w - 32) / worldW, (s.h - 32) / (worldH + 56)))); view = { k: k, x: (s.w - worldW * k) / 2, y: (s.h - (worldH + 56) * k) / 2 + 40 * k }; apply(); }
  stage.addEventListener('wheel', function (e) {
    e.preventDefault();
    var s = size();
    zoomAt(e.clientX - s.l, e.clientY - s.t, Math.exp(-e.deltaY * (e.ctrlKey ? 0.012 : (e.deltaMode === 1 ? 0.05 : 0.0016))));
  }, { passive: false });
  var ptrs = {}, drag = null, pinch = null, moved = false;
  function count() { return Object.keys(ptrs).length; }
  svg.addEventListener('pointerdown', function (e) {
    ptrs[e.pointerId] = { x: e.clientX, y: e.clientY };
    if (count() === 1) { drag = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }; moved = false; }
    else if (count() === 2) { var a = Object.keys(ptrs).map(function (k) { return ptrs[k]; }); pinch = { d: Math.hypot(a[0].x - a[1].x, a[0].y - a[1].y), k: view.k }; moved = true; }
  });
  svg.addEventListener('pointermove', function (e) {
    if (!ptrs[e.pointerId]) return;
    ptrs[e.pointerId] = { x: e.clientX, y: e.clientY };
    if (pinch && count() === 2) {
      var a = Object.keys(ptrs).map(function (k) { return ptrs[k]; }), d = Math.hypot(a[0].x - a[1].x, a[0].y - a[1].y), s = size();
      zoomAt((a[0].x + a[1].x) / 2 - s.l, (a[0].y + a[1].y) / 2 - s.t, (pinch.k * d / Math.max(1, pinch.d)) / view.k);
      return;
    }
    if (drag && count() === 1) {
      var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (!moved && Math.hypot(dx, dy) > 5) { moved = true; try { svg.setPointerCapture(e.pointerId); } catch (x) { } stage.classList.add('moving'); }
      if (moved) { view.x = drag.vx + dx; view.y = drag.vy + dy; apply(); }
    }
  });
  function up(e) {
    delete ptrs[e.pointerId];
    if (count() < 2) { pinch = null; }
    if (count() === 0) { drag = null; stage.classList.remove('moving'); window.setTimeout(function () { moved = false; }, 0); }
  }
  svg.addEventListener('pointerup', up); svg.addEventListener('pointercancel', up);
  svg.addEventListener('dblclick', function (e) { if (e.target.closest && e.target.closest('[data-kind]')) return; var s = size(); zoomAt(e.clientX - s.l, e.clientY - s.t, 1.7); });
  Array.prototype.forEach.call(root.querySelectorAll('[data-lmz-zoom]'), function (b) {
    b.addEventListener('click', function () {
      var w = b.getAttribute('data-lmz-zoom'), s = size();
      if (w === 'in') { zoomAt(s.w / 2, s.h / 2, 1.4); } else if (w === 'out') { zoomAt(s.w / 2, s.h / 2, 1 / 1.4); } else if (w === 'wide') { wide(!root.classList.contains('lmz-full')); } else { fitAll(); }
    });
  });
  function wide(on) {  /* the whole window for the map (the details stay below it); Escape leaves */
    root.classList.toggle('lmz-full', on);
    document.documentElement.classList.toggle('lmz-lock', on);
    window.requestAnimationFrame(function () { fitWidth(); });
  }
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && root.classList.contains('lmz-full')) { wide(false); } });
  stage.addEventListener('keydown', function (e) {
    var s = size(), step = 60;
    if (e.key === '+' || e.key === '=') { zoomAt(s.w / 2, s.h / 2, 1.25); }
    else if (e.key === '-' || e.key === '_') { zoomAt(s.w / 2, s.h / 2, 0.8); }
    else if (e.key === '0') { fitAll(); }
    else if (e.key === 'ArrowLeft') { view.x += step; apply(); } else if (e.key === 'ArrowRight') { view.x -= step; apply(); }
    else if (e.key === 'ArrowUp') { view.y += step; apply(); } else if (e.key === 'ArrowDown') { view.y -= step; apply(); }
    else if (e.key === 'Escape') { select(null); } else { return; }
    if (e.target === stage || e.target === svg) { e.preventDefault(); }
  });

  /* ------------------------------------------------------------------ the selection */
  var sel = null;
  function related() {
    var rp = {}, rc = {}, rg = {}, rw = {};
    function chOf(area) { var g = model.groups.filter(function (x) { return x.area === area; })[0]; return g ? g.channels.map(function (c) { return c.key; }) : []; }
    function areaOf(key) { for (var i = 0; i < model.groups.length; i++) { for (var j = 0; j < model.groups[i].channels.length; j++) { if (model.groups[i].channels[j].key === key) return model.groups[i].area; } } return ''; }
    if (!sel) return null;
    model.edges.forEach(function (e, idx) {
      var area = areaOf(e.channel), on = false;
      if (sel.kind === 'p') { on = e.plugin === sel.id && (!sel.sub || e.channel === sel.sub); }
      else if (sel.kind === 'c') { on = e.channel === sel.id && (!sel.sub || e.plugin === sel.sub); }
      else if (sel.kind === 'g' || sel.kind === 'd') { on = area === sel.id; }
      if (on) { rp[e.plugin] = 1; rc[e.channel] = 1; rg[area] = 1; rw[idx] = 1; }
    });
    if (sel.kind === 'c') { rc[sel.id] = 1; rg[areaOf(sel.id)] = 1; }
    if (sel.kind === 'p') { rp[sel.id] = 1; }
    if (sel.kind === 'g' || sel.kind === 'd') { rg[sel.id] = 1; chOf(sel.id).forEach(function (k) { rc[k] = 1; }); }
    return { p: rp, c: rc, g: rg, w: rw };
  }
  function paint() {
    var r = related();
    world.classList.toggle('has-sel', !!r);
    function mark(map, set, key) { for (var id in map) { map[id].classList.toggle('sel', !!(r && set[key ? key(id) : id])); } }
    mark(els.plug, r ? r.p : {}); mark(els.ch, r ? r.c : {}); mark(els.grp, r ? r.g : {}); mark(els.place, r ? r.g : {});
    for (var a in els.outs) { els.outs[a].classList.toggle('sel', !!(r && r.g[a])); }
    els.wires.forEach(function (w) { w.el.classList.toggle('sel', !!(r && r.w[w.idx])); });
  }
  function select(next) {
    if (next && sel && sel.kind === next.kind && sel.id === next.id && (sel.sub || '') === (next.sub || '')) { next = null; }
    sel = next; paint();
    if (!sel) { detail.hidden = true; token++; return; }
    openDetail();
  }
  svg.addEventListener('click', function (e) {
    if (moved) return;
    var n = e.target.closest ? e.target.closest('[data-kind]') : null;
    if (!n) { return; }
    var kind = n.getAttribute('data-kind');
    if (kind === 'w') { select({ kind: 'p', id: n.getAttribute('data-plugin'), sub: n.getAttribute('data-channel') }); return; }
    select({ kind: kind === 'd' ? 'g' : kind, id: n.getAttribute('data-id') });
  });
  svg.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    var n = e.target.closest ? e.target.closest('[data-kind]') : null;
    if (!n || n.getAttribute('data-kind') === 'w') return;
    e.preventDefault(); n.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });

  /* ------------------------------------------------------------------ the details below the map */
  var token = 0, $ = function (id) { return document.getElementById(id); };
  function empty(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }
  function add(parent, tag, cls, text) { var n = document.createElement(tag); if (cls) { n.className = cls; } if (text !== undefined) { n.textContent = text; } parent.appendChild(n); return n; }
  function pretty(v) { try { return JSON.stringify(JSON.parse(v), null, 2); } catch (e) { return String(v); } }
  function dirBadge(parent, dir) { return add(parent, 'span', 'lm-dir ' + dir, T(dir)); }
  function openDetail() {
    var mine = ++token, kind = sel.kind === 'g' ? 'group' : sel.kind === 'p' ? 'plugin' : 'channel';
    detail.hidden = false;
    $('lmz-dtitle').textContent = '…'; $('lmz-dex').textContent = ''; empty($('lmz-dextra')); empty($('lmz-conn')); empty($('lmz-data'));
    fetch(base + '/detail.json?kind=' + kind + '&id=' + encodeURIComponent(sel.id) + '&sub=' + encodeURIComponent(sel.sub || ''), { credentials: 'same-origin', cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (mine === token && d) { renderDetail(d); detail.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } })
      .catch(function () { });
  }
  function renderDetail(d) {
    $('lmz-dtitle').textContent = d.title;
    $('lmz-dex').textContent = d.explain;
    var extra = $('lmz-dextra'); empty(extra);
    (d.extra || []).forEach(function (x) { add(extra, 'li', 'lmz-chip', x); });
    var conn = $('lmz-conn'); empty(conn);
    if (!d.connections.length) { add(conn, 'li', 'hint', T('no_connections')); }
    d.connections.forEach(function (c) {
      var li = add(conn, 'li', 'lmz-conn-row t' + (tintOf[c.plugin] || 1));
      dirBadge(li, c.dir);
      add(li, 'b', '', c.plugin_name); add(li, 'span', 'lmz-arrow', '→'); add(li, 'span', '', c.channel_label);
      add(li, 'span', 'lmz-calls', fmt(T('hits'), { n: c.hits }));
      var tm = add(li, 'time', '', c.when || c.ago); tm.title = c.ago;
      add(li, 'i', 'lm-dot ' + c.state);
    });
    var data = $('lmz-data'); empty(data);
    if (!d.signals.length) { add(data, 'p', 'hint', T('no_data')); }
    d.signals.forEach(function (s, i) {
      var det = add(data, 'details', 'lmz-sig t' + (tintOf[s.plugin] || 1)), sm = add(det, 'summary', '');
      if (i < 4) { det.open = true; }
      dirBadge(sm, s.dir); add(sm, 'b', '', s.name); add(sm, 'small', '', s.plugin_name); var tm = add(sm, 'time', '', s.when || s.ago); tm.title = s.ago;
      var body = add(det, 'div', 'lmz-sig-body'), meta = add(body, 'p', 'hint');
      meta.textContent = T('last_seen') + ': ' + (s.when || '-') + ' (' + s.ago + ') · ' + T('calls') + ': ' + s.hits + ' · ' + s.area;
      add(body, 'h3', '', T('raw'));
      if (!d.raw) { add(body, 'p', 'hint', T('masked')); }
      else if (s.value === null) { add(body, 'p', 'hint', T('novalue')); }
      else { add(body, 'pre', '', pretty(s.value)); }
      if (s.history && s.history.length) {
        add(body, 'h3', '', T('history'));
        var ol = add(body, 'ol', 'lm-hist');
        s.history.forEach(function (h) {
          var li = add(ol, 'li', ''), t2 = add(li, 'time', '', h.when || h.ago); t2.title = h.ago;
          add(li, 'code', '', h.value === null ? '' : (h.value.length > 160 ? h.value.slice(0, 159) + '…' : h.value));
        });
      }
    });
    if (d.more) { add(data, 'p', 'hint', fmt(T('more_signals'), { n: d.more })); }
  }
  $('lmz-dclose').addEventListener('click', function () { select(null); });

  /* ------------------------------------------------------------------ a refresh every 20 seconds: only states and times; a new plugin or channel reloads the page */
  function refresh() {
    if (document.hidden || !root.offsetParent) return;
    fetch(base + '/zoom.json', { credentials: 'same-origin', cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
      if (!d) return;
      if (d.version !== model.version) { window.location.reload(); return; }
      var states = ['live', 'recent', 'idle', 'none', 'open'];
      function setState(node, st) { states.forEach(function (s) { node.classList.remove(s); }); node.classList.add(st); }
      d.plugins.forEach(function (p) {
        var n = els.plug[p.id]; if (!n) return;
        setState(n, p.state); var mt = n.querySelector('[data-meta]'); if (mt) { mt.textContent = cut(p.meta, 36); }
      });
      d.channels.forEach(function (c) {
        var n = els.ch[c.key]; if (!n) return;
        setState(n, c.state); var ago = n.querySelector('.lmz-ago'); if (ago) { ago.textContent = c.ago; }
      });
      d.edges.forEach(function (e) {
        els.wires.forEach(function (w) { if (w.edge.plugin === e.plugin && w.edge.channel === e.channel && w.edge.dir === e.dir) { setState(w.el, e.state); w.el.classList.add('lmz-w', 't' + (tintOf[e.plugin] || 1), e.dir); } });
      });
    }).catch(function () { });
  }
  window.setInterval(refresh, 20000);

  fitWidth();
  window.addEventListener('resize', function () { if (!root.offsetParent) return; });
  root.classList.add('ready');
})();
