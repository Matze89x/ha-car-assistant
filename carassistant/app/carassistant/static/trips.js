/* Trips page: tap a trip to open its card (distance, duration, speeds, route on the map / drawn); the data comes from track.json when first opened. */
(function () {
  function colour(kmh) {
    if (!kmh) { return "#4f86ff"; }  /* blue (slow) -> green -> yellow -> red (130+ km/h) */
    var t = Math.max(0, Math.min(1, kmh / 130)), hue = 220 - t * 220;
    return "hsl(" + Math.round(hue) + ",85%,55%)";
  }
  var MAPKEY = "caMapMode";
  function mapMode() {  /* like the location map: its own choice if there is one, otherwise the design decides (light design = light map) */
    try { var saved = localStorage.getItem(MAPKEY); if (saved === "light" || saved === "dark") { return saved; } } catch (e) { /* no storage */ }
    var cs = ""; try { cs = getComputedStyle(document.documentElement).colorScheme || ""; } catch (e) { cs = ""; }
    return cs.trim() === "light" ? "light" : "dark";
  }
  function legend(card) {  /* what the colours mean: the scale of the speed in the units of the app, and the start / end marks */
    var lg = card.querySelector(".tp-legend"); if (!lg) { return; }
    var f = parseFloat(card.getAttribute("data-factor")) || 1, u = card.getAttribute("data-unit") || "km/h", top = Math.round(130 * f);
    lg.querySelector('[data-k="l0"]').textContent = "0";
    lg.querySelector('[data-k="l1"]').textContent = Math.round(top / 2);
    lg.querySelector('[data-k="l2"]').textContent = top + "+ " + u;
    lg.querySelector('[data-k="start-word"]').textContent = card.getAttribute("data-start-word") || "";
    lg.querySelector('[data-k="end-word"]').textContent = card.getAttribute("data-end-word") || "";
    lg.querySelector(".tl-text").textContent = (card.getAttribute("data-legend") || "").replace("{v}", top + " " + u);
    lg.hidden = false;
  }
  function fmtMin(m) { var h = Math.floor(m / 60), r = Math.round(m % 60); return h ? h + ":" + (r < 10 ? "0" : "") + r + " h" : Math.round(m) + " min"; }
  function num(v, d) { return (Math.round(v * Math.pow(10, d)) / Math.pow(10, d)).toString().replace(".", ","); }
  function setText(card, key, text, show) { var el = card.querySelector('[data-k="' + key + '"]'); if (!el) { return; } var tgt = el.querySelector("b, span") || el; if (text !== null && text !== undefined) { if (el.tagName === "EM" || !el.querySelector("b, span")) { el.textContent = text; } else { tgt.textContent = text; } } if (show !== false) { el.hidden = false; } }
  function setStat(card, key, text) { var el = card.querySelector('.tp-st[data-k="' + key + '"]'); if (el && text) { el.hidden = false; el.querySelector("b").textContent = text; } }
  function mins(t) { var m = /^(\d+):(\d+)/.exec(t || ""); return m ? parseInt(m[1], 10) * 60 + parseInt(m[2], 10) : null; }

  function draw(card, data) {
    var box = card.querySelector(".tp-map"), pts = data.points || [];
    if (!box || pts.length < 2) { return; }
    box.hidden = false; var note = card.querySelector(".tp-note"); if (note) { note.hidden = false; }
    legend(card);
    if (!document.documentElement.getAttribute("data-map")) { document.documentElement.setAttribute("data-map", mapMode()); }
    if (typeof L !== "undefined" && card.getAttribute("data-maps") === "1") {
      box.classList.add("pos-map");  /* the same dark / light look as the location map */
      var map = L.map(box, { zoomControl: true, attributionControl: true });
      L.tileLayer(card.getAttribute("data-tiles") + "/{z}/{x}/{y}.png", { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors' }).addTo(map);
      var bounds = [];
      for (var i = 1; i < pts.length; i++) {
        L.polyline([[pts[i - 1][0], pts[i - 1][1]], [pts[i][0], pts[i][1]]], { color: colour(pts[i][2]), weight: 5, opacity: .95 }).addTo(map);
        bounds.push([pts[i][0], pts[i][1]]);
      }
      L.circleMarker([pts[0][0], pts[0][1]], { radius: 7, color: "#fff", weight: 2, fillColor: "#2fbf6a", fillOpacity: 1 }).addTo(map);
      L.circleMarker([pts[pts.length - 1][0], pts[pts.length - 1][1]], { radius: 7, color: "#fff", weight: 2, fillColor: "#ef4452", fillOpacity: 1 }).addTo(map);
      map.invalidateSize(); map.fitBounds(bounds, { padding: [28, 28] });  /* the route fills the 16:9 map and sits in its middle */
      return;
    }
    /* no map tiles allowed: the route as a drawing */
    var lats = pts.map(function (p) { return p[0]; }), lons = pts.map(function (p) { return p[1]; });
    var minLat = Math.min.apply(null, lats), maxLat = Math.max.apply(null, lats), minLon = Math.min.apply(null, lons), maxLon = Math.max.apply(null, lons);
    var k = Math.max(Math.cos(((minLat + maxLat) / 2) * Math.PI / 180), 0.01), W = 640, H = 360, pad = 28;
    var wd = Math.max((maxLon - minLon) * k, 1e-6), hd = Math.max(maxLat - minLat, 1e-6), sc = Math.min((W - 2 * pad) / wd, (H - 2 * pad) / hd);
    var ox = (W - wd * sc) / 2, oy = (H - hd * sc) / 2;
    function xy(p) { return [ox + (p[1] - minLon) * k * sc, oy + (maxLat - p[0]) * sc]; }
    var svg = '<svg viewBox="0 0 ' + W + " " + H + '" xmlns="http://www.w3.org/2000/svg" class="tp-svg">';
    for (var j = 1; j < pts.length; j++) { var a = xy(pts[j - 1]), b = xy(pts[j]); svg += '<line x1="' + a[0].toFixed(1) + '" y1="' + a[1].toFixed(1) + '" x2="' + b[0].toFixed(1) + '" y2="' + b[1].toFixed(1) + '" stroke="' + colour(pts[j][2]) + '" stroke-width="4" stroke-linecap="round"/>'; }
    var s = xy(pts[0]), e = xy(pts[pts.length - 1]);
    svg += '<circle cx="' + s[0].toFixed(1) + '" cy="' + s[1].toFixed(1) + '" r="7" class="p-start"/><circle cx="' + e[0].toFixed(1) + '" cy="' + e[1].toFixed(1) + '" r="7" class="p-end"/></svg>';
    box.innerHTML = svg; box.classList.add("flat");
  }

  document.addEventListener("toggle", function (ev) {
    var d = ev.target;
    if (!d || !d.classList || !d.classList.contains("trip")) { return; }
    var card = d.querySelector(".tp-card");
    if (!card) { return; }
    card.hidden = !d.open;  /* opened: the whole trip (map, speeds, driving style) is shown; closed: only the essentials */
    if (d.open) { load(card); }
  }, true);

  function load(card) {
    if (card.getAttribute("data-loaded")) { return; }
    card.setAttribute("data-loaded", "1");
    var f = parseFloat(card.getAttribute("data-factor")) || 1, u = card.getAttribute("data-unit") || "km/h";
    /* without positions: the duration and the average from the entered times */
    var km = parseFloat(card.getAttribute("data-km")), a = mins(card.getAttribute("data-start")), b = mins(card.getAttribute("data-end"));
    if (a !== null && b !== null && b > a) { setStat(card, "min", fmtMin(b - a)); if (km) { setStat(card, "avg", Math.round(km / ((b - a) / 60) * f) + " " + u); } }
    if (card.getAttribute("data-has") !== "1") { return; }
    fetch(card.getAttribute("data-track"), { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (d) {
      if (d.minutes) { setStat(card, "min", fmtMin(d.minutes)); }
      if (d.avg_kmh) { setStat(card, "avg", Math.round(d.avg_kmh * f) + " " + u); }
      if (d.max_kmh) { setStat(card, "max", Math.round(d.max_kmh * f) + " " + u); }
      var e = d.estimate || {};
      if (e.per100) {
        var chips = card.querySelector(".tp-chips"); chips.hidden = false;
        chips.querySelector('[data-k="per100"] span').textContent = e.per100 + " " + e.per100_unit;
        chips.querySelector('[data-k="amount"] span').textContent = "\u2248 " + e.amount + " " + e.amount_unit;
        var c = chips.querySelector('[data-k="cost"]'); if (e.cost) { c.querySelector("span").textContent = "\u2248 " + e.cost + " " + e.cur; } else { c.hidden = true; }
        card.querySelector('[data-k="fine"]').hidden = false;
      }
      if (d.acc !== null && d.acc !== undefined) {
        card.querySelector('[data-k="style-h"]').hidden = false; card.querySelector(".tp-tiles").hidden = false;
        var L = card.getAttribute("data-l") || "";
        setText(card, "acc", num(d.acc, 1) + " m/s\u00b2", false); setText(card, "dec", num(Math.abs(d.dec), 1) + " m/s\u00b2", false);
        setText(card, "hard", (card.getAttribute("data-hard") || "{n}").replace("{n}", d.hard_brakes || 0), false);
        if (d.moving_kmh) { setText(card, "moving", Math.round(d.moving_kmh * f) + " " + u, false); setText(card, "peak", (card.getAttribute("data-peak") || "{v}").replace("{v}", Math.round(d.max_kmh * f) + " " + u), false); }
        if (d.idle_pct !== null) { setText(card, "idle", d.idle_pct + " %", false); setText(card, "movmin", (card.getAttribute("data-inmotion") || "{n}").replace("{n}", d.moving_min), false); }
      }
      var note = card.querySelector(".tp-note");
      if (note && d.n) { note.textContent = (card.getAttribute("data-note") || "").replace("{n}", d.n).replace("{a}", d.start || "").replace("{b}", d.end || "").replace("{v}", d.max_kmh ? Math.round(d.max_kmh * f) + " " + u : "-"); }
      draw(card, d);
    }).catch(function () { /* the card stays with what it has */ });
  }
})();
