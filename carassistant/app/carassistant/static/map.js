/* Location map: Leaflet (local copy) with OpenStreetMap tiles. Reads lat/lon from the #posmap data attributes. */
(function () {
  var box = document.getElementById('posmap');
  if (!box || typeof L === 'undefined') return;
  var lat = parseFloat(box.getAttribute('data-lat')), lon = parseFloat(box.getAttribute('data-lon'));
  if (!isFinite(lat) || !isFinite(lon)) return;

  /* light / dark map: without a choice of its own the map follows the design (light designs get a light map, dark ones a dark map);
     the sun/moon button overrides it and is remembered in the browser */
  var KEY = 'caMapMode';
  function themeIsLight() {
    var cs = ''; try { cs = getComputedStyle(document.documentElement).colorScheme || ''; } catch (e) { cs = ''; }
    return cs.trim() === 'light';
  }
  function mode() {
    try { var saved = localStorage.getItem(KEY); if (saved === 'light' || saved === 'dark') { return saved; } } catch (e) { /* no storage */ }
    return themeIsLight() ? 'light' : 'dark';
  }
  function apply(m) { document.documentElement.setAttribute('data-map', m); }
  apply(mode());

  var map = L.map(box).setView([lat, lon], 18);
  L.tileLayer((box.getAttribute('data-tiles') || '/tiles') + '/{z}/{x}/{y}.png', {  /* through this app, see tiles.py */
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>'
  }).addTo(map);
  L.marker([lat, lon], {
    title: box.getAttribute('data-pin') || '',
    zIndexOffset: 1000,
    icon: L.divIcon({ className: 'pos-pin', html: '<span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5,11L6.5,6.5H17.5L19,11M17.5,16A1.5,1.5 0 0,1 16,14.5A1.5,1.5 0 0,1 17.5,13A1.5,1.5 0 0,1 19,14.5A1.5,1.5 0 0,1 17.5,16M6.5,16A1.5,1.5 0 0,1 5,14.5A1.5,1.5 0 0,1 6.5,13A1.5,1.5 0 0,1 8,14.5A1.5,1.5 0 0,1 6.5,16M18.92,6C18.7,5.39 18.12,5 17.5,5H6.5C5.88,5 5.3,5.39 5.08,6L3,12V20A1,1 0 0,0 4,21H5A1,1 0 0,0 6,20V19H18V20A1,1 0 0,0 19,21H20A1,1 0 0,0 21,20V12L18.92,6Z"/></svg></span>', iconSize: [36, 36], iconAnchor: [18, 18] })
  }).addTo(map);

  var light = box.getAttribute('data-light') || 'Light', dark = box.getAttribute('data-dark') || 'Dark';
  var Toggle = L.Control.extend({
    options: { position: 'topright' },
    onAdd: function () {
      var bar = L.DomUtil.create('div', 'leaflet-bar leaflet-control pc-maptoggle'), a = L.DomUtil.create('a', '', bar);
      a.href = '#'; a.setAttribute('role', 'button');
      function paint() { var isLight = mode() === 'light'; a.textContent = isLight ? '\u263E' : '\u2600'; a.title = isLight ? dark : light; a.setAttribute('aria-label', a.title); }
      paint();
      L.DomEvent.disableClickPropagation(bar);
      L.DomEvent.on(a, 'click', function (e) {
        L.DomEvent.preventDefault(e);
        var next = mode() === 'light' ? 'dark' : 'light';
        try { localStorage.setItem(KEY, next); } catch (x) { }
        apply(next);
        paint();
      });
      return bar;
    }
  });
  new Toggle().addTo(map);
})();
