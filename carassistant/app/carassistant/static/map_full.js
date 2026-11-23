/* The Map page: the car, the own position (only when the person allows it in the browser, never sent anywhere), a search and the way to send a
   destination on - to the plugin of the car or to a navigation service (a link the phone opens). */
(function () {
  var stage = document.getElementById('mapstage');
  if (!stage || typeof L === 'undefined') return;
  function a(n) { return stage.getAttribute('data-' + n) || ''; }
  var providers = [];
  try { providers = JSON.parse(a('providers')) || []; } catch (e) { providers = []; }

  /* light / dark map: follows the design, the sun/moon button overrides it (the same remembered choice as the small location map) */
  var KEY = 'caMapMode';
  function mode() {
    try { var s = localStorage.getItem(KEY); if (s === 'light' || s === 'dark') return s; } catch (e) { /* no storage */ }
    var cs = ''; try { cs = getComputedStyle(document.documentElement).colorScheme || ''; } catch (e) { cs = ''; }
    return cs.trim() === 'light' ? 'light' : 'dark';
  }
  var themeBtn = document.querySelector('[data-map-act="theme"]');
  function applyMode(m) {
    document.documentElement.setAttribute('data-map', m);
    if (themeBtn) { var t = m === 'light' ? a('dark') : a('light'); themeBtn.title = t; themeBtn.setAttribute('aria-label', t); }
  }
  applyMode(mode());

  var carLat = parseFloat(a('lat')), carLon = parseFloat(a('lon')), hasCar = isFinite(carLat) && isFinite(carLon);
  var map = L.map('fullmap', { zoomControl: false }).setView(hasCar ? [carLat, carLon] : [51.1, 10.4], hasCar ? 16 : 6);
  L.control.zoom({ position: 'bottomright' }).addTo(map);
  L.tileLayer((a('tiles') || '/tiles') + '/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>'
  }).addTo(map);

  function pin(cls, svg) { return L.divIcon({ className: cls, html: '<span>' + svg + '</span>', iconSize: [36, 36], iconAnchor: [18, 18] }); }
  var CAR = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5,11L6.5,6.5H17.5L19,11M17.5,16A1.5,1.5 0 0,1 16,14.5A1.5,1.5 0 0,1 17.5,13A1.5,1.5 0 0,1 19,14.5A1.5,1.5 0 0,1 17.5,16M6.5,16A1.5,1.5 0 0,1 5,14.5A1.5,1.5 0 0,1 6.5,13A1.5,1.5 0 0,1 8,14.5A1.5,1.5 0 0,1 6.5,16M18.92,6C18.7,5.39 18.12,5 17.5,5H6.5C5.88,5 5.3,5.39 5.08,6L3,12V20A1,1 0 0,0 4,21H5A1,1 0 0,0 6,20V19H18V20A1,1 0 0,0 19,21H20A1,1 0 0,0 21,20V12L18.92,6Z"/></svg>';
  var DEST = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12,2C8.13,2 5,5.13 5,9C5,14.25 12,22 12,22C12,22 19,14.25 19,9C19,5.13 15.87,2 12,2M12,11.5A2.5,2.5 0 0,1 9.5,9A2.5,2.5 0 0,1 12,6.5A2.5,2.5 0 0,1 14.5,9A2.5,2.5 0 0,1 12,11.5Z"/></svg>';

  var carMarker = null;
  function placeCar(lat, lon) {
    carLat = lat; carLon = lon; hasCar = true;
    if (!carMarker) {
      carMarker = L.marker([lat, lon], { icon: pin('pos-pin', CAR), zIndexOffset: 900, title: a('t-car') }).addTo(map);
      carMarker.on('click', function () { choose({ name: a('t-car'), address: a('car-title'), lat: carLat, lon: carLon }); });
    } else { carMarker.setLatLng([lat, lon]); }
  }
  if (hasCar) placeCar(carLat, carLon);
  setInterval(function () { /* the car moves: ask again every 20 seconds while the page is in front */
    if (document.hidden || !a('car')) return;
    fetch(a('car'), { credentials: 'same-origin', cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d && d.lat !== null && isFinite(d.lat)) placeCar(d.lat, d.lon); }).catch(function () { });
  }, 20000);

  /* ---- messages */
  var note = stage.querySelector('.map-note'), noteTimer = 0;
  function say(text, ms) {
    clearTimeout(noteTimer);
    note.textContent = text || ''; note.hidden = !text;
    if (text && ms) noteTimer = setTimeout(function () { note.hidden = true; }, ms);
  }

  /* ---- own position: asked from the browser, drawn here, never sent to the server */
  var meBtn = document.querySelector('[data-map-act="me"]'), watch = null, meDot = null, meRing = null, firstFix = true;
  function stopMe() {
    if (watch !== null) navigator.geolocation.clearWatch(watch);
    watch = null; firstFix = true;
    if (meDot) { map.removeLayer(meDot); meDot = null; }
    if (meRing) { map.removeLayer(meRing); meRing = null; }
    meBtn.setAttribute('aria-pressed', 'false'); meBtn.classList.remove('on');
  }
  function startMe() {
    if (!navigator.geolocation) { say(a('t-nogeo'), 6000); return; }
    meBtn.setAttribute('aria-pressed', 'true'); meBtn.classList.add('on');
    watch = navigator.geolocation.watchPosition(function (p) {
      var ll = [p.coords.latitude, p.coords.longitude];
      if (!meDot) {
        meRing = L.circle(ll, { radius: p.coords.accuracy || 30, className: 'me-ring', interactive: false }).addTo(map);
        meDot = L.marker(ll, { icon: L.divIcon({ className: 'me-pin', html: '<span></span>', iconSize: [20, 20], iconAnchor: [10, 10] }), interactive: false, zIndexOffset: 800 }).addTo(map);
      } else { meDot.setLatLng(ll); meRing.setLatLng(ll); meRing.setRadius(p.coords.accuracy || 30); }
      if (firstFix) { firstFix = false; map.flyTo(ll, Math.max(map.getZoom(), 15)); }
    }, function (err) { stopMe(); say(err && err.code === 1 ? a('t-denied') : a('t-nogeo'), 7000); }, { enableHighAccuracy: true, maximumAge: 10000, timeout: 20000 });
  }

  /* ---- a destination: the sheet at the bottom */
  var sheet = stage.querySelector('.map-sheet'), select = sheet.querySelector('.ms-select'), dest = null, destMarker = null;
  select.innerHTML = '';
  providers.forEach(function (p) { var o = document.createElement('option'); o.value = p.key; o.textContent = p.name; select.appendChild(o); });
  select.value = a('first');
  function choose(d) {
    dest = d;
    if (destMarker) map.removeLayer(destMarker);
    if (!(Math.abs(d.lat - carLat) < 1e-6 && Math.abs(d.lon - carLon) < 1e-6)) destMarker = L.marker([d.lat, d.lon], { icon: pin('dest-pin', DEST), zIndexOffset: 700 }).addTo(map);
    sheet.querySelector('.ms-t').textContent = d.name;
    sheet.querySelector('.ms-a').textContent = d.address || '';
    sheet.hidden = false;
    results.hidden = true;
  }
  function closeSheet() { sheet.hidden = true; dest = null; if (destMarker) { map.removeLayer(destMarker); destMarker = null; } }
  function fill(tpl, d) { return tpl.replace(/\{lat\}/g, d.lat.toFixed(6)).replace(/\{lon\}/g, d.lon.toFixed(6)).replace(/\{name\}/g, encodeURIComponent(d.name || a('t-pin'))); }
  function open(url) {
    if (/^https?:/.test(url)) window.open(url, '_blank', 'noopener'); else window.location.href = url;
  }
  function go() {
    if (!dest) return;
    var p = providers.filter(function (x) { return x.key === select.value; })[0];
    if (!p) return;
    if (p.plugin) {
      var btn = sheet.querySelector('[data-map-act="go"]'); btn.disabled = true;
      fetch(a('send'), { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key: p.key, lat: dest.lat, lon: dest.lon, name: dest.name, address: dest.address || '' }) })
        .then(function (r) { return r.json(); })
        .then(function (d) { say(d && d.ok ? (d.message || a('t-sent')) : (d && d.message ? d.message : a('t-send-err')), 6000); })
        .catch(function () { say(a('t-send-err'), 6000); })
        .then(function () { btn.disabled = false; });
    } else { open(fill(p.url, dest)); }
  }

  /* ---- search (only when sent: the public service does not allow search while typing) */
  var results = stage.querySelector('.map-results'), form = stage.querySelector('.map-search'), input = form.querySelector('input');
  function searchAt(q) { /* the same words, handed to the chosen provider: it finds the place itself */
    var p = providers.filter(function (x) { return x.key === select.value && x.search; })[0] || providers.filter(function (x) { return x.search; })[0];
    return p ? { p: p, url: p.search.replace(/\{q\}/g, encodeURIComponent(q)) } : null;
  }
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var q = input.value.trim();
    if (q.length < 3) return;
    var b = map.getBounds();
    say(a('t-searching'));
    fetch(a('search') + '?q=' + encodeURIComponent(q) + '&bbox=' + [b.getSouth(), b.getWest(), b.getNorth(), b.getEast()].join(','), { credentials: 'same-origin' })
      .then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
      .then(function (d) {
        say('');
        results.innerHTML = '';
        (d.results || []).forEach(function (r) {
          var li = document.createElement('li'), btn = document.createElement('button'), s = document.createElement('small');
          btn.type = 'button'; btn.textContent = r.name; s.textContent = r.address;
          btn.appendChild(s);
          btn.addEventListener('click', function () { choose(r); map.flyTo([r.lat, r.lon], Math.max(map.getZoom(), 15)); });
          li.appendChild(btn); results.appendChild(li);
        });
        if (!(d.results || []).length) { say(a('t-none'), 5000); }
        var alt = searchAt(q);
        if (alt) {
          var li2 = document.createElement('li'), l = document.createElement('a');
          l.href = alt.url; l.target = '_blank'; l.rel = 'noopener noreferrer'; l.textContent = a('t-search-at').replace('{name}', alt.p.name);
          li2.className = 'alt'; li2.appendChild(l); results.appendChild(li2);
        }
        results.hidden = !results.children.length;
      })
      .catch(function () {
        results.innerHTML = '';
        var alt = searchAt(q);
        say(a('t-err'), 6000);
        if (alt) {
          var li = document.createElement('li'), l = document.createElement('a');
          l.href = alt.url; l.target = '_blank'; l.rel = 'noopener noreferrer'; l.textContent = a('t-search-at').replace('{name}', alt.p.name);
          li.className = 'alt'; li.appendChild(l); results.appendChild(li); results.hidden = false;
        }
      });
  });
  var told = false;
  input.addEventListener('focus', function () { if (!told) { told = true; say(a('t-hint'), 7000); } }); /* once: what a search sends */
  map.on('click', function () { results.hidden = true; });
  map.on('contextmenu', function (e) { choose({ name: a('t-pin'), address: e.latlng.lat.toFixed(5) + ', ' + e.latlng.lng.toFixed(5), lat: e.latlng.lat, lon: e.latlng.lng }); }); /* a long press drops a point */

  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-map-act]');
    if (!b) return;
    var act = b.getAttribute('data-map-act');
    if (act === 'close') closeSheet();
    else if (act === 'go') go();
    else if (act === 'me') { if (watch === null) startMe(); else stopMe(); }
    else if (act === 'car') { if (hasCar) map.flyTo([carLat, carLon], Math.max(map.getZoom(), 16)); }
    else if (act === 'theme') { var next = mode() === 'light' ? 'dark' : 'light'; try { localStorage.setItem(KEY, next); } catch (x) { /* no storage */ } applyMode(next); }
  });
  /* the map takes the rest of the window below the header; on a phone it runs down to the edge, behind the floating bar */
  function fit() {
    var narrow = window.matchMedia('(max-width: 999px)').matches;
    var top = stage.getBoundingClientRect().top + (window.pageYOffset || 0);
    stage.style.height = Math.max(340, Math.round(window.innerHeight - top - (narrow ? 0 : 14))) + 'px';
    map.invalidateSize();
  }
  fit();
  window.addEventListener('resize', fit);
  window.addEventListener('orientationchange', function () { setTimeout(fit, 250); });
  window.addEventListener('load', fit);
  setTimeout(fit, 300);
})();
