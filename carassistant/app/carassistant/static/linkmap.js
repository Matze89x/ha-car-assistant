/* The connection map (Plugins -> Connections): the plugins on the left, the Plugin API in the middle, the integrations on the right, one line per
   plugin and area. Signals are loaded only when somebody opens one. Everything that comes from a plugin (names, values) is put in with textContent,
   never as HTML. Light on purpose: no timers except one refresh every 20 seconds while the page is in front, no animation loop. */
(function () {
  var root = document.getElementById('lm');
  if (!root) return;
  var board = document.getElementById('lm-board'), svg = document.getElementById('lm-wires'), detail = document.getElementById('lm-detail');
  var rowsBox = document.getElementById('lm-rows'), filterBox = document.getElementById('lm-filter'), moreBtn = document.getElementById('lm-more');
  var base = root.getAttribute('data-base'), canRaw = root.getAttribute('data-raw') === '1', edges = [];
  try { edges = JSON.parse(root.getAttribute('data-edges') || '[]'); } catch (e) { edges = []; }
  function t(k) { return root.getAttribute('data-t-' + k) || ''; }
  function fmt(s, o) { return s.replace(/\{(\w+)\}/g, function (m, k) { return o[k] !== undefined ? o[k] : m; }); }
  var tint = {}, NS = 'http://www.w3.org/2000/svg';
  Array.prototype.forEach.call(root.querySelectorAll('.lm-plugin'), function (n) { tint[n.getAttribute('data-id')] = n.getAttribute('data-tint'); });
  var sel = { plugin: '', area: '' };

  /* ---- the lines: one per plugin, area and direction, drawn from the middle of a card to the middle of the other */
  function narrow() { return window.matchMedia && window.matchMedia('(max-width: 860px)').matches; }
  function el(name, attrs) { var n = document.createElementNS(NS, name); for (var k in attrs) { n.setAttribute(k, attrs[k]); } return n; }
  function draw() {
    while (svg.firstChild) { svg.removeChild(svg.firstChild); }
    if (narrow()) { return; }
    var b = board.getBoundingClientRect(), pos = {};
    Array.prototype.forEach.call(board.querySelectorAll('.lm-node'), function (n) { /* read everything first, write after */
      var r = n.getBoundingClientRect();
      pos[n.getAttribute('data-kind') + ':' + n.getAttribute('data-id')] = { l: r.left - b.left, r: r.right - b.left, y: r.top - b.top + r.height / 2 };
    });
    svg.setAttribute('width', b.width); svg.setAttribute('height', b.height); svg.setAttribute('viewBox', '0 0 ' + b.width + ' ' + b.height);
    var defs = el('defs', {});
    for (var i = 1; i <= 7; i++) {
      var m = el('marker', { id: 'lm-m' + i, viewBox: '0 0 10 10', refX: '8', refY: '5', markerWidth: '7', markerHeight: '7', orient: 'auto-start-reverse' });
      m.appendChild(el('path', { d: 'M1 1L9 5L1 9z', fill: 'var(--chip-' + i + ')' })); defs.appendChild(m);
    }
    svg.appendChild(defs);
    edges.forEach(function (e, idx) {
      var p = pos['p:' + e.plugin], a = pos['a:' + e.area];
      if (!p || !a) return;
      var off = e.dir === 'get' ? 6 : -6, x1 = p.r, y1 = p.y + off, x2 = a.l, y2 = a.y + off, dx = Math.max(50, (x2 - x1) * 0.5);
      var d = 'M' + x1 + ' ' + y1 + ' C' + (x1 + dx) + ' ' + y1 + ' ' + (x2 - dx) + ' ' + y2 + ' ' + x2 + ' ' + y2;
      var cls = 'w t' + (tint[e.plugin] || 1) + ' ' + e.state + ' ' + e.dir;
      var path = el('path', { d: d, 'class': cls, 'data-plugin': e.plugin, 'data-area': e.area, 'data-i': idx });
      path.setAttribute(e.dir === 'get' ? 'marker-start' : 'marker-end', 'url(#lm-m' + (tint[e.plugin] || 1) + ')');
      var hit = el('path', { d: d, 'class': 'hit', 'data-plugin': e.plugin, 'data-area': e.area });
      svg.appendChild(path); svg.appendChild(hit);
    });
    paintSelection();
  }

  /* ---- what is related to the selection */
  function related() {
    var rp = {}, ra = {};
    edges.forEach(function (e) {
      if ((sel.plugin && e.plugin === sel.plugin && (!sel.area || e.area === sel.area)) || (sel.area && e.area === sel.area && (!sel.plugin || e.plugin === sel.plugin))) {
        rp[e.plugin] = 1; ra[e.area] = 1;
      }
    });
    return { p: rp, a: ra };
  }
  function paintSelection() {
    var any = !!(sel.plugin || sel.area), r = related();
    board.classList.toggle('has-sel', any);
    Array.prototype.forEach.call(board.querySelectorAll('.lm-node'), function (n) {
      var k = n.getAttribute('data-kind'), id = n.getAttribute('data-id');
      var on = any && ((k === 'p' && (id === sel.plugin || r.p[id])) || (k === 'a' && (id === sel.area || r.a[id])));
      n.classList.toggle('sel', on); n.setAttribute('aria-pressed', (k === 'p' && id === sel.plugin) || (k === 'a' && id === sel.area) ? 'true' : 'false');
    });
    Array.prototype.forEach.call(svg.querySelectorAll('path.w'), function (w) {
      var pl = w.getAttribute('data-plugin'), ar = w.getAttribute('data-area');
      var on = any && ((!sel.plugin || pl === sel.plugin) && (!sel.area || ar === sel.area));
      w.classList.toggle('sel', on);
    });
  }

  /* ---- the signals of the selection */
  var loaded = [], shown = 0, PAGE = 60, token = 0;
  function nameOf(kind, id) { var n = board.querySelector('.lm-node[data-kind="' + kind + '"][data-id="' + id + '"] b'); return n ? n.textContent : id; }
  function open(plugin, area) {
    sel = { plugin: plugin || '', area: area || '' };
    paintSelection();
    var title = plugin && area ? fmt(t('dlink'), { plugin: nameOf('p', plugin), area: nameOf('a', area) }) : plugin ? fmt(t('dplugin'), { name: nameOf('p', plugin) }) : fmt(t('darea'), { name: nameOf('a', area) });
    document.getElementById('lm-dtitle').textContent = title;
    var ex = area ? board.querySelector('.lm-node[data-kind="a"][data-id="' + area + '"] .lm-ex') : null;
    document.getElementById('lm-dex').textContent = ex ? ex.textContent : (canRaw ? '' : t('masked'));
    detail.hidden = false; filterBox.value = ''; rowsBox.textContent = ''; moreBtn.hidden = true;
    var mine = ++token;
    fetch(base + '/signals.json?plugin=' + encodeURIComponent(plugin || '') + '&area=' + encodeURIComponent(area || ''), { credentials: 'same-origin', cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : { signals: [] }; })
      .then(function (d) { if (mine !== token) return; loaded = d.signals || []; shown = 0; render(); })
      .catch(function () { if (mine === token) { loaded = []; render(); } });
    if (window.matchMedia && window.matchMedia('(max-width: 860px)').matches) { detail.scrollIntoView({ block: 'start', behavior: 'smooth' }); }
  }
  function close() { sel = { plugin: '', area: '' }; paintSelection(); detail.hidden = true; token++; }

  function matches(s, q) { return !q || (s.name + ' ' + s.plugin_name).toLowerCase().indexOf(q) !== -1; }
  function render() {
    var q = filterBox.value.trim().toLowerCase(), list = loaded.filter(function (s) { return matches(s, q); });
    rowsBox.textContent = '';
    if (!list.length) { var li = document.createElement('li'); li.className = 'hint'; li.textContent = t('empty'); rowsBox.appendChild(li); moreBtn.hidden = true; return; }
    var upto = Math.min(list.length, Math.max(shown, PAGE)); shown = upto;
    for (var i = 0; i < upto; i++) { rowsBox.appendChild(row(list[i])); }
    moreBtn.hidden = list.length <= upto;
    if (list.length > upto) { moreBtn.textContent = fmt(t('more'), { n: list.length - upto }); }
  }
  function row(s) {
    var li = document.createElement('li'), btn = document.createElement('button'), dir = document.createElement('span'), nm = document.createElement('b'), val = document.createElement('span'), tm = document.createElement('time');
    li.className = 'lm-row t' + (tint[s.plugin] || 1);
    btn.type = 'button'; btn.className = 'lm-rowbtn'; btn.setAttribute('aria-expanded', 'false');
    dir.className = 'lm-dir ' + s.dir; dir.textContent = t(s.dir);
    nm.textContent = s.name; val.className = 'lm-val'; val.textContent = s.value === null ? '' : s.value;
    tm.textContent = s.ago; tm.setAttribute('datetime', s.ts || '');
    var nmw = document.createElement('span'); nmw.className = 'lm-nm'; nmw.appendChild(nm);
    if (!sel.plugin) { var pn = document.createElement('small'); pn.textContent = s.plugin_name; nmw.appendChild(pn); }
    btn.appendChild(dir); btn.appendChild(nmw); btn.appendChild(val); btn.appendChild(tm); li.appendChild(btn);
    var more = document.createElement('div'); more.className = 'lm-raw'; more.hidden = true; li.appendChild(more);
    btn.addEventListener('click', function () {
      var openNow = more.hidden; more.hidden = !openNow; btn.setAttribute('aria-expanded', openNow ? 'true' : 'false');
      if (openNow && !more.getAttribute('data-done')) { more.setAttribute('data-done', '1'); history(s, more); }
    });
    return li;
  }
  function pretty(v) { try { return JSON.stringify(JSON.parse(v), null, 2); } catch (e) { return String(v); } }
  function history(s, box) {
    fetch(base + '/history.json?plugin=' + encodeURIComponent(s.plugin) + '&name=' + encodeURIComponent(s.name) + '&dir=' + s.dir, { credentials: 'same-origin', cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) return;
        if (!d.raw) { var m = document.createElement('p'); m.className = 'hint'; m.textContent = t('masked'); box.appendChild(m); }
        else if (d.value === null) { var nv = document.createElement('p'); nv.className = 'hint'; nv.textContent = t('novalue'); box.appendChild(nv); }
        else { var h = document.createElement('h3'); h.textContent = t('raw'); var pre = document.createElement('pre'); pre.textContent = pretty(d.value); box.appendChild(h); box.appendChild(pre); }
        if (d.history && d.history.length) {
          var h2 = document.createElement('h3'), ol = document.createElement('ol'); h2.textContent = t('history'); ol.className = 'lm-hist';
          d.history.forEach(function (x) {
            var li = document.createElement('li'), tm = document.createElement('time'), c = document.createElement('code');
            tm.textContent = x.ago; tm.title = x.ts || ''; c.textContent = x.value === null ? '' : (x.value.length > 140 ? x.value.slice(0, 139) + '…' : x.value);
            li.appendChild(tm); li.appendChild(c); ol.appendChild(li);
          });
          box.appendChild(h2); box.appendChild(ol);
        }
      }).catch(function () { });
  }
  filterBox.addEventListener('input', function () { shown = 0; render(); });
  moreBtn.addEventListener('click', function () { shown += PAGE; render(); });
  document.getElementById('lm-dclose').addEventListener('click', close);

  /* ---- clicks: a plugin, an integration, a chip (phone) or a line */
  board.addEventListener('click', function (e) {
    var n = e.target.closest ? e.target.closest('.lm-node, .lm-chip') : null, p = e.target.closest ? e.target.closest('path.hit') : null;
    if (p) { open(p.getAttribute('data-plugin'), p.getAttribute('data-area')); return; }
    if (!n) { return; }
    var kind = n.getAttribute('data-kind');
    if (kind === 'l') { open(n.getAttribute('data-plugin'), n.getAttribute('data-area')); return; }
    var id = n.getAttribute('data-id');
    if (kind === 'p') { if (sel.plugin === id && !sel.area) { close(); } else { open(id, ''); } }
    else if (kind === 'a') { if (sel.area === id && !sel.plugin) { close(); } else { open('', id); } }
  });

  /* ---- the lines follow the layout (a changed window, loaded fonts) */
  var pending = 0;
  function later() { if (pending) return; pending = window.requestAnimationFrame(function () { pending = 0; draw(); }); }
  window.addEventListener('resize', later);
  if (document.fonts && document.fonts.ready) { document.fonts.ready.then(later); }
  window.addEventListener('load', later);
  draw();

  /* ---- a refresh every 20 seconds while the page is in front: only the texts and states; a new plugin or area reloads the page */
  function refresh() {
    if (document.hidden) return;
    fetch(base + '/graph.json', { credentials: 'same-origin', cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
      if (!d) return;
      if (d.version !== root.getAttribute('data-version')) { window.location.reload(); return; }
      d.plugins.forEach(function (p) {
        var n = board.querySelector('.lm-plugin[data-id="' + p.id + '"]'); if (!n) return;
        n.querySelector('.lm-meta').textContent = p.meta; ['live', 'recent', 'idle', 'none'].forEach(function (c) { n.classList.remove(c); n.querySelector('.lm-dot').classList.remove(c); }); n.classList.add(p.state); n.querySelector('.lm-dot').classList.add(p.state);
      });
      d.areas.forEach(function (a) {
        var n = board.querySelector('.lm-area[data-id="' + a.key + '"]'); if (!n) return;
        n.querySelector('.lm-meta').textContent = a.meta; ['live', 'recent', 'idle', 'none'].forEach(function (c) { n.classList.remove(c); n.querySelector('.lm-dot').classList.remove(c); }); n.classList.add(a.state); n.querySelector('.lm-dot').classList.add(a.state);
      });
      d.edges.forEach(function (e, i) { edges[i] && (edges[i].state = e.state); });
      Array.prototype.forEach.call(svg.querySelectorAll('path.w'), function (w) { var e = edges[parseInt(w.getAttribute('data-i'), 10)]; if (e) { w.setAttribute('class', 'w t' + (tint[e.plugin] || 1) + ' ' + e.state + ' ' + e.dir + (w.classList.contains('sel') ? ' sel' : '')); } });
    }).catch(function () { });
  }
  window.setInterval(refresh, 20000);
})();
