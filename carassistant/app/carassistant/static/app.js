// Confirmation dialog for destructive forms (inline handlers are blocked by the CSP): an in-app dialog, the browser's confirm() as fallback.
(function () {
  var pending = null;
  document.addEventListener("submit", function (event) {
    var form = event.target, sub = event.submitter, message = (sub && sub.getAttribute && sub.getAttribute("data-confirm")) || (form && form.getAttribute && form.getAttribute("data-confirm"));
    if (!message) { return; }
    if (form.__confirmed) { form.__confirmed = false; return; }
    event.preventDefault();
    var dlg = document.getElementById("cdlg");
    if (!dlg || !dlg.showModal) {
      if (window.confirm(message)) { form.__confirmed = true; form.submit(); }
      return;
    }
    var ok = document.getElementById("cdlg-ok"), danger = form.getAttribute("data-confirm-ok");
    document.getElementById("cdlg-m").textContent = message;
    ok.textContent = danger || ok.getAttribute("data-default");
    ok.classList.toggle("danger", !!danger);
    pending = { form: form, submitter: event.submitter || null };
    dlg.showModal();
    ok.focus();
  });
  document.addEventListener("click", function (event) {
    var dlg = document.getElementById("cdlg");
    if (!dlg || !event.target) { return; }
    if (event.target === dlg || (event.target.closest && event.target.closest("#cdlg [data-cancel]"))) { dlg.close(); pending = null; return; }
    if (event.target.id === "cdlg-ok" && pending) {
      var p = pending; pending = null; dlg.close(); p.form.__confirmed = true;
      if (p.form.requestSubmit) { p.form.requestSubmit(p.submitter); } else { p.form.submit(); }
    }
  });
})();

// Switches (modules): submit the surrounding form as soon as the checkbox changes (inline handlers are blocked by the CSP).
document.addEventListener("change", function (event) {
  var form = event.target && event.target.closest && event.target.closest("form[data-autosubmit]");
  if (form) {
    var hidden = form.querySelector("input[name=enabled]");
    if (hidden) { hidden.value = event.target.checked ? "1" : "0"; }
    form.submit();
  }
});

// Gliding marker of the navigation: start at the previously active entry, then slide to the current one.
(function () {
  var bar = document.getElementById("tabbar");
  if (!bar) { return; }
  var cur = parseInt(bar.getAttribute("data-i"), 10) || 0, prev = null;
  try { prev = sessionStorage.getItem("ca.nav"); sessionStorage.setItem("ca.nav", String(cur)); sessionStorage.setItem("ca.navd", bar.getAttribute("data-d") || String(cur)); } catch (e) { prev = null; }
  if (bar.hasAttribute("data-kept")) { return; }  // the bar stayed in the page: it glides by itself (softnav.js)
  if (prev === null || parseInt(prev, 10) === cur) { return; }
  var ind = bar.querySelector(".tab-ind");
  var pd = prev; try { pd = sessionStorage.getItem("ca.navd") || prev; } catch (e) { pd = prev; }
  ind.style.transition = "none"; bar.style.setProperty("--i", prev); bar.style.setProperty("--id", pd);
  void ind.offsetWidth;
  ind.style.transition = ""; bar.style.setProperty("--i", cur); bar.style.setProperty("--id", bar.getAttribute("data-d") || cur);
})();

// Settings: sortable navigation. Drag the handle (or use the arrow keys); the first four rows are the bar, the rest moves to More.
(function () {
  var list = document.getElementById("navlist");
  if (!list) { return; }
  var LIMIT = 4;
  var label = list.getAttribute("data-more") || "";
  function rows() { return Array.prototype.slice.call(list.querySelectorAll(".navrow:not(.fixed)")); }  /* the vehicle passport row is fixed: not sortable */
  function refresh() {
    var div = list.querySelector(".navdiv");
    if (!div) {
      div = document.createElement("li"); div.className = "navdiv"; div.textContent = label;
    }
    rows().forEach(function (r, n) { r.classList.toggle("inmore", n >= LIMIT); });
    var all = rows();
    if (all.length > LIMIT) { list.insertBefore(div, all[LIMIT]); } else if (div.parentNode) { div.parentNode.removeChild(div); }
    var pass = list.querySelector(".navpass");  /* the vehicle passport is always the FIRST entry of More, fixed */
    if (pass) { if (div.parentNode) { div.parentNode.insertBefore(pass, div.nextSibling); } else { list.appendChild(pass); } }
  }
  list.addEventListener("sortchange", refresh);  // the handle (SORTING above) moved a row: the first four are the bar, the rest is More
  // the icon choices are cloned from one shared template when a picker is opened (11 rows x 40 icons were a heavy page)
  list.addEventListener("toggle", function (e) {
    var d = e.target, g = d.querySelector && d.querySelector(".pickgrid"), tpl = document.getElementById("pk-tpl");
    if (!d.open || !g || g.firstChild || !tpl) { return; }
    g.appendChild(tpl.content.cloneNode(true));
    Array.prototype.forEach.call(g.querySelectorAll("input"), function (i) {
      i.name = "pick-" + g.getAttribute("data-key");
      if (i.value === g.getAttribute("data-cur")) { i.checked = true; }
    });
  }, true);
  list.addEventListener("change", function (e) {
    var r = e.target.closest && e.target.closest(".navrow");
    if (r && e.target.type === "radio") {
      r.querySelector("input[name=i]").value = e.target.value;
      var ic = e.target.nextElementSibling.cloneNode(true);
      var chip = r.querySelector("summary .mi-ic");
      chip.innerHTML = ""; chip.appendChild(ic.firstElementChild || ic);
      var d = r.querySelector("details"); if (d) { d.open = false; }
    }
  });
  refresh();
})();

// Vehicle switcher: a dark overlay (<dialog>) with all cars; closes with the x, a click outside or Escape.
document.addEventListener("click", function (event) {
  var opener = event.target.closest && event.target.closest("[data-open]");
  if (opener) {
    event.preventDefault();  // the sidebar switch sits inside the logo link
    var dlg = document.getElementById(opener.getAttribute("data-open"));
    if (dlg && dlg.showModal) { dlg.showModal(); }
    return;
  }
  var dialog = event.target.closest && event.target.closest("dialog.vsw");
  if ((event.target.closest && event.target.closest("[data-close]")) || (dialog && event.target === dialog)) {
    (dialog || document.querySelector("dialog.vsw[open]")).close();
  }
});

// First-start language page: choosing a language reloads the page in that language (inline handlers are blocked by the CSP).
document.addEventListener("change", function (event) {
  var sel = event.target && event.target.getAttribute && event.target.getAttribute("data-lang-switch");
  if (sel) { window.location.href = sel + "?lang=" + encodeURIComponent(event.target.value); }
});

// Pressing and holding a link (navigation, widget, list row) must never open the system's link preview or menu - in the Home Assistant
// app that preview loads the page outside the signed-in session ("401 Unauthorized"). Touch only: a mouse keeps its right-click menu.
(function () {
  document.addEventListener("contextmenu", function (e) {
    var touch = window.matchMedia && window.matchMedia("(pointer: coarse)").matches;
    if (touch && e.target.closest && e.target.closest("a, .tabbar, .side, .wd, .mgroup")) { e.preventDefault(); }
  });
})();

// Live saving without a reload (the page keeps its scroll position): the navigation editor of a vehicle and the on/off switches of its fixed integrations.
(function () {
  var timer = null;
  function post(url, data) { return fetch(url, { method: "POST", body: data, credentials: "same-origin" }); }
  var navset = document.getElementById("navset");
  // after a change the real navigation (bar / sidebar and the More list) is rebuilt right away from the server's answer
  function refreshBar(withList, withNav) {
    fetch(location.pathname, { credentials: "same-origin", cache: "no-store" }).then(function (r) { return r.text(); }).then(function (html) {
      var doc = new DOMParser().parseFromString(html, "text/html");
      var bar = document.getElementById("tabbar"), fresh = doc.getElementById("tabbar");
      if (bar && fresh) { bar.outerHTML = fresh.outerHTML; }
      var pane = document.querySelector(".more-pane"), freshPane = doc.querySelector(".more-pane");
      if (pane && freshPane) { pane.innerHTML = freshPane.innerHTML; }
      // the list of fixed integrations below follows the same order
      var fl = document.querySelector(".fn-list"), freshFl = doc.querySelector(".fn-list");
      if (withList === true && fl && freshFl) { fl.innerHTML = freshFl.innerHTML; }
      // switching a fixed integration on or off adds or removes its page in the navigation editor above
      var nl = document.getElementById("navlist"), freshNl = doc.getElementById("navlist");
      if (withNav === true && nl && freshNl) { nl.innerHTML = freshNl.innerHTML; }
    });
  }
  if (navset && navset.getAttribute("data-live") && window.fetch) {
    var save = function () {
      clearTimeout(timer);
      timer = setTimeout(function () {
        var fd = new FormData(navset); fd.append("ajax", "1");
        post(navset.getAttribute("action"), fd).then(function () { refreshBar(true); });
      }, 300);
    };
    navset.addEventListener("sortchange", function () { setTimeout(save, 0); });
    navset.addEventListener("change", function () { setTimeout(save, 0); });
    var lastKeys = "";
    setInterval(function () {
      var keys = Array.prototype.map.call(navset.querySelectorAll(".navrow[data-key] input[name=m]"), function (i) { return i.value; }).join(",");
      if (lastKeys && keys !== lastKeys) { save(); }
      lastKeys = keys;
    }, 600);
  }
  // switches (delegated, so rows rebuilt after a reorder keep working)
  document.addEventListener("change", function (e) {
    var sw = e.target;
    if (sw && sw.getAttribute && sw.getAttribute("data-fn") && window.fetch) {  // a switch inside the navigation editor
      var data = new FormData(); data.set("enabled", sw.checked ? "1" : "0"); data.set("ajax", "1");
      var line = sw.closest(".navrow"); if (line) { line.classList.toggle("off-row", !sw.checked); }
      post(sw.getAttribute("data-fn"), data).then(function () {
        if (sw.getAttribute("data-stay")) { refreshBar(false, true); } else { window.location.reload(); }
      });
      return;
    }
    var box = e.target, form = box && box.closest && box.closest("form[data-ajax]");
    if (!form || !window.fetch || box.type !== "checkbox") { return; }
    var fd = new FormData(form); fd.set("enabled", box.checked ? "1" : "0"); fd.set("ajax", "1");
    var row = form.closest(".fn-row");
    if (row) { row.classList.toggle("off", !box.checked); }
    post(form.getAttribute("action"), fd).then(function () { refreshBar(false, true); });
  });
})();

// Settings that apply at once (no Save button): the design (switches live with a soft fade), and every form marked data-live (saved in the background;
// data-reload reloads afterwards, for example when the language changes).
document.addEventListener("focusin", function (e) { var t = e.target; if (t && t.matches && t.matches("input[readonly][data-select]")) { t.select(); } });  // a value to copy: one tap selects it all
(function () {  // a "Copy" button copies what its data-copy holds (the access key page)
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-copy]"); if (!b) { return; }
    var text = b.getAttribute("data-copy"), label = b.querySelector("span");
    function done() { if (label) { var old = label.textContent; label.textContent = b.getAttribute("data-done") || old; setTimeout(function () { label.textContent = old; }, 1500); } }
    if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(text).then(done, function () { /* the field stays selectable */ }); }
  });
})();
(function () {
  function post(form) { return fetch(form.getAttribute("action"), { method: "POST", body: new FormData(form), credentials: "same-origin" }); }

  // The colour of the designs "dark / light + your colour": the server works out the whole family from one colour (one place for the maths); the
  // wheel only shows it live (fetch of the CSS) and saves it a moment after the last move.
  var accentTag = function () { return document.getElementById("accent-custom"); };
  var accentBox = document.getElementById("accent-pick");
  function accentFetch(hex, scheme) {
    var url = accentBox.getAttribute("data-preview") + "?c=" + encodeURIComponent(hex) + "&s=" + scheme;
    return fetch(url, { credentials: "same-origin" }).then(function (r) { return r.ok ? r.text() : ""; });
  }
  function currentScheme() {
    var radio = document.querySelector("form[data-theme-live] input[name=theme]:checked");
    var s = radio ? radio.getAttribute("data-scheme") : "dark";
    return s === "light" || s === "auto" ? s : "dark";
  }
  function setAccent(scheme) {
    var tag = accentTag(); if (!tag) { return; }
    if (!scheme || !accentBox) { tag.textContent = ""; return; }
    var hex = accentBox.querySelector(".ac-hex").value;
    accentFetch(hex, scheme).then(function (css) { tag.textContent = css; });
  }
  if (accentBox && window.fetch) {
    var cv = accentBox.querySelector(".ac-wheel"), c2 = cv.getContext("2d"), dot = accentBox.querySelector(".ac-dot");
    var hexIn = accentBox.querySelector(".ac-hex"), size = cv.width, half = size / 2, timer = null, saveTimer = null;
    var valIn = accentBox.querySelector(".ac-val"), bright = 1;  // the brightness of the colour (the wheel itself only chooses hue and strength)
    function hsv(h, s, v) {
      var i = Math.floor(h * 6), f = h * 6 - i, p = v * (1 - s), q = v * (1 - f * s), t2 = v * (1 - (1 - f) * s), m = i % 6;
      var r = [v, q, p, p, t2, v][m], g = [t2, v, v, q, p, p][m], b = [p, p, t2, v, v, q][m];
      return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
    }
    function toHex(rgb) { return "#" + rgb.map(function (n) { return ("0" + n.toString(16)).slice(-2); }).join(""); }
    function fromHex(hex) {
      var n = parseInt(hex.slice(1), 16), r = (n >> 16) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
      var max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min, h = 0;
      if (d) { h = max === r ? ((g - b) / d + 6) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4; h /= 6; }
      return { h: h, s: max ? d / max : 0, v: max };
    }
    (function drawWheel() {
      var img = c2.createImageData(size, size);
      for (var y = 0; y < size; y++) { for (var x = 0; x < size; x++) {
        var dx = x - half + 0.5, dy = y - half + 0.5, dist = Math.sqrt(dx * dx + dy * dy), k = (y * size + x) * 4;
        if (dist > half) { img.data[k + 3] = 0; continue; }
        var rgb = hsv((Math.atan2(dy, dx) / (2 * Math.PI) + 1) % 1, dist / half, 1);
        img.data[k] = rgb[0]; img.data[k + 1] = rgb[1]; img.data[k + 2] = rgb[2]; img.data[k + 3] = 255;
      } }
      c2.putImageData(img, 0, 0);
    })();
    function place(hex) {
      var c = fromHex(hex), ang = c.h * 2 * Math.PI, rad = c.s * 100;  // percent of the box
      dot.style.left = (50 + Math.cos(ang) * rad / 2) + "%"; dot.style.top = (50 + Math.sin(ang) * rad / 2) + "%";
    }
    function track(hex) {  // the slider's track runs from dark to the chosen colour at full brightness
      var c = fromHex(hex); accentBox.style.setProperty("--ac-c", toHex(hsv(c.h, c.s, 1)));
    }
    function apply(hex, save) {
      hexIn.value = hex; place(hex); track(hex);
      var v = fromHex(hex).v; bright = v; if (valIn) { valIn.value = Math.round(v * 100); }
      clearTimeout(timer);
      timer = setTimeout(function () { var tag = accentTag(); accentFetch(hex, currentScheme()).then(function (css) { if (tag) { tag.textContent = css; } }); }, 40);
      if (save) {
        clearTimeout(saveTimer);
        saveTimer = setTimeout(function () {
          var body = new FormData(); body.append("accent", hex); body.append("ajax", "1");
          fetch(accentBox.getAttribute("data-save"), { method: "POST", body: body, credentials: "same-origin" });
        }, 250);
      }
    }
    function pick(e, save) {
      var r = cv.getBoundingClientRect(), dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2), rad = r.width / 2;
      var dist = Math.min(Math.sqrt(dx * dx + dy * dy), rad);
      apply(toHex(hsv((Math.atan2(dy, dx) / (2 * Math.PI) + 1) % 1, dist / rad, bright)), save);
    }
    if (valIn) {
      var vStop = function (save) { var c = fromHex(hexIn.value); apply(toHex(hsv(c.h, c.s, valIn.value / 100)), save); };
      valIn.addEventListener("input", function () { vStop(false); });
      valIn.addEventListener("change", function () { vStop(true); });
    }
    var down = false;
    cv.addEventListener("pointerdown", function (e) { down = true; cv.setPointerCapture(e.pointerId); pick(e, false); });
    cv.addEventListener("pointermove", function (e) { if (down) { pick(e, false); } });
    cv.addEventListener("pointerup", function (e) { if (down) { down = false; pick(e, true); } });
    hexIn.addEventListener("input", function () { var v = hexIn.value.trim().toLowerCase(); if (v[0] !== "#") { v = "#" + v; } if (/^#[0-9a-f]{6}$/.test(v)) { apply(v, true); } });
    Array.prototype.forEach.call(accentBox.querySelectorAll(".ac-sw"), function (b) { b.style.background = b.getAttribute("data-hex"); b.addEventListener("click", function () { apply(b.getAttribute("data-hex"), true); }); });
    place(hexIn.value); track(hexIn.value); bright = fromHex(hexIn.value).v; if (valIn) { valIn.value = Math.round(bright * 100); }
  }

  var themeForm = document.querySelector("form[data-theme-live]");
  if (themeForm && window.fetch) {
    var base = (document.querySelector("link[href*='/static/app.css']") || {}).href || "";
    var root = document.documentElement;
    var dir = base.replace(/app\.css.*$/, "themes/");
    var version = (base.match(/\?v=([^&]*)/) || [])[1] || "";
    function paint(name, scheme, bg, attr, custom) {
      var light = scheme === "light";
      var css = ":root{color-scheme:" + (scheme === "auto" ? "light dark" : scheme) + "}html,body{background:" + bg + ";color:" + (light ? "#151922" : "#e8eaf0") + "}";
      if (scheme === "auto") { css += "@media (prefers-color-scheme: light){html,body{background:#eef0f4;color:#151922}}"; }
      var tag = document.getElementById("theme-live");
      if (!tag) { tag = document.createElement("style"); tag.id = "theme-live"; document.head.appendChild(tag); }
      tag.textContent = css;
      Array.prototype.forEach.call(document.querySelectorAll("meta[name=color-scheme]"), function (m) { m.setAttribute("content", scheme === "auto" ? "light dark" : scheme); });
      Array.prototype.forEach.call(document.querySelectorAll("meta[name=theme-color]"), function (m) { m.setAttribute("content", bg); m.removeAttribute("media"); });
      if (!attr) { root.removeAttribute("data-theme"); } else { root.setAttribute("data-theme", attr); }
      setAccent(custom ? scheme : "");
    }
    themeForm.addEventListener("change", function (e) {
      var radio = e.target; if (!radio || radio.name !== "theme") { return; }
      var name = radio.getAttribute("data-name") || radio.value, olds = Array.prototype.slice.call(document.querySelectorAll("link[href*='/static/themes/']"));  // "like the system" (a car) shows the system's design
      var custom = radio.value.indexOf("custom-") === 0, file = radio.getAttribute("data-file") || "";
      var pick = document.getElementById("accent-pick"); if (pick) { pick.hidden = !custom; }
      function apply() {
        root.classList.add("theme-fade");
        paint(name, radio.getAttribute("data-scheme") || "dark", radio.getAttribute("data-bg") || "#0d1016", radio.getAttribute("data-attr") || "", custom);
        olds.forEach(function (l) { if (l !== fresh && l.parentNode) { l.parentNode.removeChild(l); } });
        setTimeout(function () { root.classList.remove("theme-fade"); }, 700);
      }
      var fresh = null;
      if (name !== "default" && (file || !custom)) {
        fresh = document.createElement("link"); fresh.rel = "stylesheet";
        var auto = radio.getAttribute("data-attr") === "auto";
        fresh.href = dir + (auto ? "light" : (custom ? file : name)) + ".css?v=" + version;
        if (auto) { fresh.media = "(prefers-color-scheme: light)"; }
        fresh.onload = apply; fresh.onerror = apply;
        document.head.appendChild(fresh);
      } else { apply(); }
      post(themeForm);
    });
  }

  Array.prototype.forEach.call(document.querySelectorAll("form[data-live]:not(#navset)"), function (form) {
    form.addEventListener("change", function () {
      if (!window.fetch) { form.submit(); return; }
      post(form).then(function () { if (form.hasAttribute("data-reload")) { location.reload(); } });
    });
  });

  // Soft tap on iPhone: a real, invisible system switch lies over the tab, so the finger itself toggles it (iOS gives the haptic click only for
  // real touches on such a switch; clicking it from script no longer works on the newest iOS). The tap then opens the page as usual.
  var ios = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  if (ios && document.body.getAttribute("data-haptics") === "1") {
    Array.prototype.forEach.call(document.querySelectorAll("#tabbar .tab, [data-haptic-test]"), function (host) {
      if (host.classList.contains("hx-host")) { return; }
      var sw = document.createElement("input");
      sw.type = "checkbox"; sw.setAttribute("switch", ""); sw.className = "hx"; sw.tabIndex = -1; sw.setAttribute("aria-hidden", "true");
      host.classList.add("hx-host"); host.appendChild(sw);
      sw.addEventListener("change", function () {
        sw.checked = false;
        if (host.tagName === "A") { window.location.assign(host.href); }
      });
    });
  }

  // Long lists load the next batch while you scroll (the Next button stays as the fallback without script)
  Array.prototype.forEach.call(document.querySelectorAll("nav.pager[data-more]"), function (nav) {
    if (!window.IntersectionObserver || !window.fetch) { return; }
    nav.classList.add("live");
    var busy = false;
    var load = function () {
      var url = nav.getAttribute("data-more");
      if (busy || !url) { return; }
      busy = true; nav.classList.add("busy");
      fetch(url, { credentials: "same-origin" }).then(function (r) { return r.text(); }).then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        var into = document.querySelector(nav.getAttribute("data-into"));
        var from = doc.querySelector(nav.getAttribute("data-into"));
        var next = doc.querySelector("nav.pager[data-more]");
        if (!into || !from) { throw new Error("no list"); }
        Array.prototype.forEach.call(from.children, function (el) { into.appendChild(document.importNode(el, true)); });
        var total = parseInt(nav.getAttribute("data-total"), 10);
        var shown = Math.min(total, into.children.length);
        var count = nav.querySelector(".pg-count");
        if (count) { count.textContent = count.getAttribute("data-fmt").replace("{n}", shown).replace("{total}", total); }
        if (next) { nav.setAttribute("data-more", next.getAttribute("data-more")); busy = false; nav.classList.remove("busy"); watch.unobserve(nav); watch.observe(nav); }
        else { nav.removeAttribute("data-more"); watch.disconnect(); nav.classList.remove("busy"); }
      }).catch(function () { nav.classList.remove("live", "busy"); watch.disconnect(); });
    };
    var watch = new IntersectionObserver(function (items) { if (items[0].isIntersecting) { load(); } }, { rootMargin: "700px 0px" });
    watch.observe(nav);
  });
})();

// A file chosen behind a page-header button (documents): the upload starts at once.
document.addEventListener("change", function (event) {
  var input = event.target;
  if (!input || !input.matches || !input.matches("input[type=file][data-send]") || !input.form || !input.files || !input.files.length) { return; }
  input.closest("label").classList.add("busy");
  if (input.form.requestSubmit) { input.form.requestSubmit(); } else { input.form.submit(); }
});

// The add button in the page header opens / closes the add form of the page and brings it into view.
document.addEventListener("click", function (event) {
  var btn = event.target.closest && event.target.closest("[data-add-toggle]");
  if (!btn) { return; }
  var card = document.getElementById(btn.getAttribute("data-add-toggle"));
  if (!card) { return; }
  card.open = !card.open;
  if (card.open) {
    card.scrollIntoView({ block: "nearest", behavior: "smooth" });
    var first = card.querySelector("input:not([type=hidden]):not([type=checkbox]), select, textarea");
    if (first && first.focus) { try { first.focus({ preventScroll: true }); } catch (e) { first.focus(); } }
  }
});

// Pages of integrations: search, "only changed", and the bits of a tapped byte (old value above, new value below, differing bits marked).
(function () {
  var list = document.getElementById("pm-list");
  if (!list) { return; }
  var q = document.getElementById("pm-q"), only = document.getElementById("pm-only");
  function apply() {
    var needle = q ? q.value.trim().toLowerCase() : "", changed = only && only.getAttribute("aria-pressed") === "true";
    Array.prototype.forEach.call(list.children, function (card) {
      var ok = (!needle || (card.getAttribute("data-q") || "").indexOf(needle) !== -1) && (!changed || card.getAttribute("data-changed") === "1");
      card.hidden = !ok;
    });
  }
  if (q) { q.addEventListener("input", apply); }
  if (only) { only.addEventListener("click", function () { only.setAttribute("aria-pressed", only.getAttribute("aria-pressed") === "true" ? "false" : "true"); only.classList.toggle("on"); apply(); }); }
  function bin(hex) { var n = parseInt(hex, 16); if (isNaN(n)) { return null; } var s = n.toString(2); while (s.length < 8) { s = "0" + s; } return s; }
  function two(n) { var s = n.toString(16).toUpperCase(); return s.length < 2 ? "0" + s : s; }
  function codeOf(el) { return el.closest(".pm-code"); }
  function cardOf(code) { return code.closest(".pm-unit"); }
  function selOf(code) { return code.querySelector(".pm-sel"); }
  function hexField(code) { var sel = selOf(code), card = cardOf(code); return card && sel ? card.querySelector('input[name="' + sel.getAttribute("data-field") + '"]') : null; }
  function cells(code) { return Array.prototype.slice.call(code.querySelectorAll(".pm-byte")); }
  function curCell(code) { return code.querySelector(".pm-byte.sel"); }
  function curIdx(code) { var c = curCell(code); return c ? cells(code).indexOf(c) : -1; }
  function J(inp) { try { return (inp && inp.value && JSON.parse(inp.value)) || {}; } catch (err) { return {}; } }
  function store(code, name) {  // the notes / groups of THIS hex field: read from the hidden field of the form, written back as text
    var sel = selOf(code), card = cardOf(code), inp = card.querySelector('input[name="' + name + '"]'), field = sel.getAttribute("data-field");
    return { get: function () { return J(inp)[field] || {}; }, set: function (v) { var all = J(inp); all[field] = v; inp.value = JSON.stringify(all); } };
  }
  function notes(code) { return store(code, "bitnotes"); }
  function groups(code) { return store(code, "bitgroups"); }
  function bitsOf(mask) { var out = []; for (var i = 0; i < 8; i++) { if ((mask >> i) & 1) { out.push(i); } } return out; }
  function gValue(byte, mask) { var r = 0, bs = bitsOf(mask); for (var n = 0; n < bs.length; n++) { r |= ((byte >> bs[n]) & 1) << n; } return r; }
  function gSet(byte, mask, val) { var bs = bitsOf(mask), v = byte; for (var n = 0; n < bs.length; n++) { v = ((val >> n) & 1) ? (v | (1 << bs[n])) : (v & ~(1 << bs[n])); } return v & 255; }
  function label(bs, word) { var run = true, i; for (i = 1; i < bs.length; i++) { if (bs[i] !== bs[i - 1] + 1) { run = false; } } return word + " " + (run ? bs[0] + "–" + bs[bs.length - 1] : bs.join(", ")); }
  function newByte(cell) { var n = parseInt(cell.getAttribute("data-new") || cell.getAttribute("data-old"), 16); return isNaN(n) ? 0 : n; }
  function markCells(code) {  // a dot on every byte that has a note or a group
    var n = notes(code).get(), g = groups(code).get();
    cells(code).forEach(function (c, i) {
      var has = !!(g[String(i)] && g[String(i)].length);
      Object.keys(n).forEach(function (k) { if (k.split(".")[0] === String(i) && n[k]) { has = true; } });
      var dot = c.querySelector(".dot"); if (dot) { dot.hidden = !has; }
    });
  }
  function renderGroups(code, idx) {
    var sel = selOf(code), box = sel.querySelector(".pm-glist"), g = (groups(code).get()[String(idx)] || []), cell = curCell(code), by = newByte(cell);
    box.innerHTML = "";
    g.forEach(function (gr, gi) {
      var row = document.createElement("div"); row.className = "pm-grow"; row.setAttribute("data-g", String(gi));
      var bs = bitsOf(gr.m), max = (1 << bs.length) - 1;
      row.innerHTML = '<b class="pm-gl"></b><input type="text" class="pm-gname" maxlength="200" autocomplete="off"><input type="number" class="pm-gval" min="0" max="' + max + '" inputmode="numeric"><button type="button" class="pm-gdrop"></button>';
      row.querySelector(".pm-gl").textContent = label(bs, sel.getAttribute("data-t-bits"));
      var nm = row.querySelector(".pm-gname"); nm.value = gr.l || ""; nm.placeholder = sel.getAttribute("data-t-name"); nm.setAttribute("aria-label", sel.getAttribute("data-t-name"));
      var vl = row.querySelector(".pm-gval"); vl.value = String(gValue(by, gr.m)); vl.setAttribute("aria-label", sel.getAttribute("data-t-value") + " 0–" + max);
      row.querySelector(".pm-gdrop").textContent = sel.getAttribute("data-t-drop");
      box.appendChild(row);
    });
    Array.prototype.forEach.call(sel.querySelectorAll(".pm-gchip"), function (chip) {
      var b = parseInt(chip.getAttribute("data-bit"), 10), taken = g.some(function (gr) { return (gr.m >> b) & 1; });
      chip.disabled = taken; if (taken) { chip.setAttribute("aria-pressed", "false"); }
    });
  }
  function paint(code) {  // the selected byte: original (one line), new (bits), the bit rows with their notes, the groups, the count
    var cell = curCell(code), sel = selOf(code);
    if (!cell) { return; }
    var o = bin(cell.getAttribute("data-old")), n = bin(cell.getAttribute("data-new")), idx = curIdx(code), g = groups(code).get()[String(idx)] || [], nt = notes(code).get();
    sel.querySelector(".pm-bn").textContent = sel.getAttribute("data-byte") + " " + idx;
    var bo = sel.querySelector(".pm-bo"); if (bo) { bo.textContent = o || "--------"; }
    var inp = sel.querySelector(".pm-bi"); if (document.activeElement !== inp) { inp.value = n || ""; }
    Array.prototype.forEach.call(sel.querySelectorAll(".pm-bitrows li:not(.pm-bh)"), function (li, k) {
      var cO = li.querySelector(".pm-bk-o"), cN = li.querySelector(".pm-bk-n"), note = li.querySelector(".pm-bnote");
      cO.checked = !!o && o.charAt(7 - k) === "1"; cN.checked = !!n && n.charAt(7 - k) === "1";
      li.classList.toggle("ch", !!o && !!n && o.charAt(7 - k) !== n.charAt(7 - k));
      var grp = g.filter(function (gr) { return (gr.m >> k) & 1; })[0];
      li.classList.toggle("grp", !!grp);
      note.disabled = !!grp;
      if (grp) { note.value = ""; note.placeholder = sel.getAttribute("data-t-grouped") + (grp.l ? ": " + grp.l : ""); }
      else if (document.activeElement !== note) { note.value = nt[idx + "." + k] || ""; note.placeholder = note.getAttribute("data-ph") || note.placeholder; }
    });
    renderGroups(code, idx); markCells(code);
    sel.hidden = false;
    var card = cardOf(code), cnt = card && card.querySelector(".pm-cnt");
    if (cnt) { var c = code.querySelectorAll(".pm-byte.ch").length; cnt.textContent = c + " B"; cnt.classList.toggle("on", c > 0); }
  }
  function refreshCell(c, v) {  // a byte of the new value: its text, whether it differs from the original, the small "was ..."
    c.setAttribute("data-new", v);
    var nEl = c.querySelector(".n"); if (nEl) { nEl.textContent = v || "–"; }
    var ch = (c.getAttribute("data-old") || "") !== v; c.classList.toggle("ch", ch);
    var was = c.querySelector(".was"); if (was) { was.hidden = !ch; }
  }
  function write(code, idx, value) {  // one byte of the NEW value changed: the cell, the field of the form
    var cs = cells(code), f = hexField(code), vals = cs.map(function (c) { return c.getAttribute("data-new"); });
    vals[idx] = two(value);
    cs.forEach(function (c, i) { refreshCell(c, vals[i] || ""); });
    if (f) { var spaced = /\s/.test(f.value || ""); f.value = vals.filter(function (v) { return v; }).join(spaced ? " " : ""); }
    paint(code);
  }
  function show(cell) {
    var code = codeOf(cell);
    if (!bin(cell.getAttribute("data-old")) && !bin(cell.getAttribute("data-new"))) { return; }
    Array.prototype.forEach.call(cell.parentNode.children, function (c) { c.classList.toggle("sel", c === cell); });
    paint(code);
  }
  function err(code, text) { var p = selOf(code).querySelector(".pm-gerr"); p.textContent = text || ""; p.hidden = !text; }
  list.addEventListener("change", function (e) {  // a bit row ticked or unticked
    var box = e.target; if (!box.classList || !box.classList.contains("pm-bk-n")) { return; }
    var code = codeOf(box), cell = curCell(code); if (!cell) { return; }
    var n = bin(cell.getAttribute("data-new")) || bin(cell.getAttribute("data-old")) || "00000000", k = parseInt(box.getAttribute("data-bit"), 10), at = 7 - k;
    n = n.substring(0, at) + (box.checked ? "1" : "0") + n.substring(at + 1);
    write(code, cells(code).indexOf(cell), parseInt(n, 2));
  });
  list.addEventListener("input", function (e) {
    var el = e.target, cl = el.classList;
    if (!cl) { return; }
    if (cl.contains("pm-bi")) {  // the new value typed as bits: valid with 8 of 0 / 1
      el.value = el.value.replace(/[^01]/g, "");
      if (el.value.length === 8) { var code = codeOf(el), cell = curCell(code); if (cell) { write(code, cells(code).indexOf(cell), parseInt(el.value, 2)); } }
      return;
    }
    if (cl.contains("pm-bnote")) {  // the note of a bit
      var cd = codeOf(el), ix = curIdx(cd), st = notes(cd), all = st.get(), key = ix + "." + el.getAttribute("data-bit");
      if (el.value.trim()) { all[key] = el.value; } else { delete all[key]; }
      st.set(all); markCells(cd); return;
    }
    if (cl.contains("pm-gname") || cl.contains("pm-gval")) {  // a group: its name, or its value as a number (sets its bits)
      var cd2 = codeOf(el), ix2 = curIdx(cd2), gs = groups(cd2), allg = gs.get(), list2 = allg[String(ix2)] || [], row = el.closest(".pm-grow"), gr = list2[parseInt(row.getAttribute("data-g"), 10)];
      if (!gr) { return; }
      if (cl.contains("pm-gname")) { gr.l = el.value; gs.set(allg); return; }
      var max = (1 << bitsOf(gr.m).length) - 1, v = parseInt(el.value, 10);
      if (isNaN(v) || v < 0 || v > max) { err(cd2, selOf(cd2).getAttribute("data-t-range") + " 0–" + max); return; }
      err(cd2, ""); write(cd2, ix2, gSet(newByte(curCell(cd2)), gr.m, v)); return;
    }
    if (el.tagName === "INPUT" && el.closest(".pm-form")) {  // the hex field typed by hand: the cells follow
      var card = el.closest(".pm-unit"), code2 = card && card.querySelector(".pm-code"), sel = code2 && selOf(code2);
      if (!sel || el.getAttribute("name") !== sel.getAttribute("data-field")) { return; }
      var hex = (el.value || "").replace(/\s+/g, "");
      cells(code2).forEach(function (c, i) { refreshCell(c, /^[0-9a-fA-F]*$/.test(hex) ? hex.substr(i * 2, 2).toUpperCase() : (c.getAttribute("data-new") || "")); });
      paint(code2);
    }
  });
  list.addEventListener("click", function (e) {
    var t = e.target, c = t.closest && t.closest(".pm-byte");
    if (c) { show(c); return; }
    if (!t.classList) { return; }
    var code = t.closest && t.closest(".pm-code"); if (!code) { return; }
    if (t.classList.contains("pm-gchip")) { t.setAttribute("aria-pressed", t.getAttribute("aria-pressed") === "true" ? "false" : "true"); err(code, ""); return; }
    if (t.classList.contains("pm-gbtn")) {  // group the chosen bits: their notes become the name of the group
      var sel = selOf(code), idx = curIdx(code), mask = 0;
      Array.prototype.forEach.call(sel.querySelectorAll('.pm-gchip[aria-pressed="true"]'), function (ch) { mask |= 1 << parseInt(ch.getAttribute("data-bit"), 10); });
      if (bitsOf(mask).length < 2) { err(code, sel.getAttribute("data-t-need")); return; }
      var gs = groups(code), allg = gs.get(), ns = notes(code), alln = ns.get(), parts = [];
      bitsOf(mask).forEach(function (b) { var k = idx + "." + b; if (alln[k] && parts.indexOf(alln[k]) < 0) { parts.push(alln[k]); } delete alln[k]; });
      (allg[String(idx)] = allg[String(idx)] || []).push({ m: mask, l: parts.join(" · ") });
      gs.set(allg); ns.set(alln);
      Array.prototype.forEach.call(sel.querySelectorAll(".pm-gchip"), function (ch) { ch.setAttribute("aria-pressed", "false"); });
      err(code, ""); paint(code); return;
    }
    if (t.classList.contains("pm-gdrop")) {  // dissolve a group: its name stays with its lowest bit
      var cd = code, ix = curIdx(cd), g2 = groups(cd), a2 = g2.get(), arr = a2[String(ix)] || [], row = t.closest(".pm-grow"), gi = parseInt(row.getAttribute("data-g"), 10), gone = arr.splice(gi, 1)[0];
      if (!arr.length) { delete a2[String(ix)]; }
      g2.set(a2);
      if (gone && gone.l) { var n2 = notes(cd), an = n2.get(); an[ix + "." + bitsOf(gone.m)[0]] = gone.l; n2.set(an); }
      paint(cd);
    }
  });
  list.addEventListener("keydown", function (e) { if ((e.key === "Enter" || e.key === " ") && e.target.classList && e.target.classList.contains("pm-byte")) { e.preventDefault(); show(e.target); } });
})();



// SORTING - ONE handle for every list a person may put in order (docs/design.md, "The sort handle"). A container [data-sortable] holds items
// [data-sort-item]; each has a .grip (the handle on its left). Drag the handle with the mouse or a finger, or press the arrow keys while it has the
// focus. While you drag, nothing in the page moves but the item itself and a line where it will land. Afterwards the container gets the event
// "sortchange"; with data-sort-post="<url>" the new order is also sent there (order=<data-sort-id>,<data-sort-id>,...).
(function () {
  var drag = null, timer = 0;
  function itemsOf(row) {  // the items of the list the row stands in, in their order
    return Array.prototype.filter.call(row.parentNode.children, function (el) { return el.hasAttribute("data-sort-item"); });
  }
  function relocate(row, best, before) { best.parentNode.insertBefore(row, before ? best : best.nextSibling); }
  function locate() {  // where the dragged item would land: before or after the item whose middle is nearest to the pointer
    var all = itemsOf(drag.row), rects = all.map(function (el) { return el.getBoundingClientRect(); }), best = -1, near = Infinity;
    all.forEach(function (el, i) {
      if (el === drag.row) { return; }
      var d = Math.hypot(drag.x - (rects[i].left + rects[i].width / 2), drag.y - (rects[i].top + rects[i].height / 2));
      if (d < near) { near = d; best = i; }
    });
    if (best < 0) { return { all: all, same: true }; }
    var r = rects[best], before = drag.y < r.top + r.height / 2, from = all.indexOf(drag.row), to = before ? best : best + 1;
    return { all: all, best: all[best], before: before, same: to === from || to === from + 1 };
  }
  function update() {
    var t = locate();
    drag.row.style.transform = "translateY(" + (drag.y - drag.y0 + window.pageYOffset - drag.s0) + "px)";
    t.all.forEach(function (r) { r.classList.remove("sort-before", "sort-after"); });
    if (!t.same) { t.best.classList.add(t.before ? "sort-before" : "sort-after"); }
    drag.at = t;
  }
  function changed(box) {
    box.dispatchEvent(new CustomEvent("sortchange", { bubbles: true }));
    var url = box.getAttribute("data-sort-post");
    if (!url || !window.fetch) { return; }
    var first = box.querySelector("[data-sort-item]"), ids = (first ? itemsOf(first) : []).map(function (el) { return el.getAttribute("data-sort-id"); }).join(",");
    fetch(url, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: "order=" + encodeURIComponent(ids) })
      .then(function (r) { if (!r.ok) { window.location.reload(); } })
      .catch(function () { window.location.reload(); });
  }
  function stop(drop) {
    if (!drag) { return; }
    var d = drag; drag = null;
    window.clearInterval(timer); timer = 0;
    d.row.classList.remove("sorting"); d.row.style.transform = "";
    (d.at ? d.at.all : []).forEach(function (r) { r.classList.remove("sort-before", "sort-after"); });
    if (drop && d.at && !d.at.same) {
      relocate(d.row, d.at.best, d.at.before);
      changed(d.box);
    }
  }
  document.addEventListener("pointerdown", function (e) {
    var grip = e.target.closest && e.target.closest("[data-sort-item] .grip");
    if (!grip || drag || (e.pointerType === "mouse" && e.button !== 0)) { return; }
    e.preventDefault();
    var row = grip.closest("[data-sort-item]");
    drag = { row: row, box: row.closest("[data-sortable]"), id: e.pointerId, x: e.clientX, y: e.clientY, x0: e.clientX, y0: e.clientY, s0: window.pageYOffset, at: null };
    row.classList.add("sorting");
    timer = window.setInterval(function () {  // near the top or the bottom of the screen the page scrolls on by itself
      if (!drag) { return; }
      var h = window.innerHeight;
      if (drag.y < 70) { window.scrollBy(0, -14); } else if (drag.y > h - 70) { window.scrollBy(0, 14); } else { return; }
      update();
    }, 30);
    update();
  });
  document.addEventListener("pointermove", function (e) {
    if (!drag || e.pointerId !== drag.id) { return; }
    drag.x = e.clientX; drag.y = e.clientY;
    update();
  });
  document.addEventListener("pointerup", function (e) { if (drag && e.pointerId === drag.id) { stop(true); } });
  document.addEventListener("pointercancel", function (e) { if (drag && e.pointerId === drag.id) { stop(false); } });
  document.addEventListener("keydown", function (e) {
    if (drag && e.key === "Escape") { stop(false); return; }
    var grip = e.target.closest && e.target.closest("[data-sort-item] .grip"), keys = { ArrowUp: -1, ArrowLeft: -1, ArrowDown: 1, ArrowRight: 1 };
    if (!grip || !keys[e.key]) { return; }
    e.preventDefault();
    var row = grip.closest("[data-sort-item]"), all = itemsOf(row), i = all.indexOf(row), other = all[i + keys[e.key]];
    if (!other) { return; }
    relocate(row, other, keys[e.key] < 0);
    changed(row.closest("[data-sortable]"));
    grip.focus();
  });
})();

// The odometer is edited in place: [data-odo-open] (the "change" under the figure, or the ghost odometer of a car without a reading) opens the box; Escape closes it.
document.addEventListener("click", function (e) {
  var open = e.target.closest && e.target.closest("[data-odo-open]");
  if (!open) { return; }
  var wrap = open.closest(".odo-edit"), form = wrap && wrap.querySelector(".odo-entry");
  if (!form) { return; }
  form.hidden = false; open.hidden = true;
  var input = form.querySelector("input[name=odometer]"); if (input) { input.focus(); }
});
document.addEventListener("keydown", function (e) {
  if (e.key !== "Escape") { return; }
  var form = e.target.closest && e.target.closest(".odo-entry");
  if (!form) { return; }
  var open = form.closest(".odo-edit").querySelector("[data-odo-open]");
  form.hidden = true; if (open) { open.hidden = false; open.focus(); }
});

// A form with data-sort-save sends itself in the background (with ajax=1) whenever one of its sortable lists is put in order, like the old arrows did.
document.addEventListener("sortchange", function (e) {
  var form = e.target.closest && e.target.closest("form[data-sort-save]");
  if (!form || !window.fetch) { return; }
  var data = new FormData(form); data.append("ajax", "1");
  fetch(form.getAttribute("action"), { method: "POST", credentials: "same-origin", body: data }).catch(function () { window.location.reload(); });
});

// Settings of a plugin with a list (rows of a name and a value): the plus adds a row (from the <template> of the list), the cross removes one; the
// rows are sorted with the handle (above). The rows are numbered again after every change, so the order saved is the order shown.
(function () {
  function numbers(box) {
    var rows = box.querySelectorAll(".lf-row"), key = box.getAttribute("data-lf"), add = box.querySelector(".lf-add");
    Array.prototype.forEach.call(rows, function (row, i) {
      var inputs = row.querySelectorAll("input");
      inputs[0].name = key + "__" + i + "n"; inputs[1].name = key + "__" + i + "v";
    });
    if (add) { add.setAttribute("data-n", String(rows.length)); }
  }
  document.addEventListener("sortchange", function (e) { if (e.target.hasAttribute && e.target.hasAttribute("data-lf")) { numbers(e.target); } });
  document.addEventListener("click", function (event) {
    var add = event.target.closest && event.target.closest(".lf-add"), del = event.target.closest && event.target.closest(".lf-row .lf-del");
    if (add) {
      var box = add.closest("[data-lf]"), tpl = box.querySelector("template[data-lf-row]");
      if (!tpl || box.querySelectorAll(".lf-row").length >= 30) { return; }
      var row = tpl.content.firstElementChild.cloneNode(true);
      box.insertBefore(row, tpl);
      numbers(box);
      row.querySelector("input").focus();
    } else if (del) {
      var holder = del.closest("[data-lf]");
      del.closest(".lf-row").remove();
      numbers(holder);
    }
  });
})();


// Settings pages of plugins: a field with data-showif-key shows only while that other setting has the value data-showif-eq; a slider shows its value.
(function () {
  var form = document.querySelector(".set-form");
  if (!form) { return; }
  function current(key) {
    var els = form.querySelectorAll('[name="' + key + '"]');
    if (!els.length) { return ""; }
    var el = els[0];
    if (el.type === "checkbox") { return el.checked ? "1" : "0"; }
    if (el.type === "radio") { var on = form.querySelector('[name="' + key + '"]:checked'); return on ? on.value : ""; }
    return el.value;
  }
  function apply() {
    Array.prototype.forEach.call(form.querySelectorAll("[data-showif-key]"), function (box) {
      var key = box.getAttribute("data-showif-key");
      if (key) { box.hidden = current(key) !== box.getAttribute("data-showif-eq"); }
    });
  }
  form.addEventListener("input", apply);
  form.addEventListener("change", apply);
  form.addEventListener("input", function (event) {
    var sl = event.target;
    if (sl && sl.hasAttribute && sl.hasAttribute("data-slider")) {
      var out = sl.parentNode.querySelector(".sl-val");
      if (out) { out.textContent = sl.value + (out.textContent.replace(/^[-0-9.,]+/, "")); }
    }
  });
  apply();
})();

// Tabs on the settings page of a plugin (a "tab" element in its settings): the links of [data-set-tabs] show the panels [data-tab-panel] and, for the
// first tab, everything marked [data-tabfor]; nothing is lost when you switch (one form). The tab sits in the address (#tab-<id>), also after Save.
(function () {
  var nav = document.querySelector("[data-set-tabs]");
  if (!nav) { return; }
  var form = document.querySelector(".set-form"), action = form ? form.getAttribute("action") : "";
  function fade() {  // many tabs: the bar scrolls sideways; a soft edge shows on the side where there is more
    var left = nav.scrollLeft > 4, right = nav.scrollLeft + nav.clientWidth < nav.scrollWidth - 4;
    nav.setAttribute("data-fade", left && right ? "both" : left ? "left" : right ? "right" : "");
  }
  nav.addEventListener("scroll", fade, { passive: true });
  window.addEventListener("resize", fade);
  function show(id) {
    Array.prototype.forEach.call(nav.querySelectorAll("a[data-tab]"), function (a) {
      var on = a.getAttribute("data-tab") === id;
      a.classList.toggle("on", on);
      if (on) { a.setAttribute("aria-current", "page"); } else { a.removeAttribute("aria-current"); }
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-tab-panel],[data-tabfor]"), function (el) {
      el.hidden = (el.getAttribute("data-tab-panel") || el.getAttribute("data-tabfor")) !== id;
    });
    if (form && action) { form.setAttribute("action", action.split("#")[0] + "#tab-" + id); }
    var on = nav.querySelector("a.on");
    if (on && on.scrollIntoView) { on.scrollIntoView({ inline: "center", block: "nearest" }); }  // the shown tab is never hidden at the edge
  }
  nav.addEventListener("click", function (e) {
    var a = e.target && e.target.closest && e.target.closest("a[data-tab]");
    if (!a) { return; }
    e.preventDefault();
    var id = a.getAttribute("data-tab");
    show(id);
    if (window.history && history.replaceState) { history.replaceState(null, "", "#tab-" + id); }
  });
  if (form) {  // a required field in a tab that is not shown would block the save without a word: show its tab (the browser then points at it)
    form.addEventListener("invalid", function (e) {
      var panel = e.target && e.target.closest && e.target.closest("[data-tab-panel]");
      if (panel && panel.hidden) {
        show(panel.getAttribute("data-tab-panel"));
        if (window.history && history.replaceState) { history.replaceState(null, "", "#tab-" + panel.getAttribute("data-tab-panel")); }
      }
    }, true);
  }
  fade();
  var m = /^#tab-(.+)$/.exec(location.hash || "");
  if (m && !nav.querySelector("a.err") && nav.querySelector('a[data-tab="' + m[1].replace(/"/g, "") + '"]')) { show(m[1]); }
})();

// Copy buttons: data-copy holds the text; the button's label flips to data-done for a moment.
document.addEventListener("click", function (e) {
  var b = e.target && e.target.closest && e.target.closest("[data-copy]");
  if (!b) { return; }
  var text = b.getAttribute("data-copy");
  function done() { var old = b.getAttribute("title"); b.setAttribute("title", b.getAttribute("data-done") || ""); b.classList.add("copied"); setTimeout(function () { b.classList.remove("copied"); b.setAttribute("title", old || ""); }, 1500); }
  if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(text).then(done, done); return; }
  var ta = document.createElement("textarea"); ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); } catch (err) { /* nothing to do */ } document.body.removeChild(ta); done();
});

// Equipment list: edit one feature in place, and filter while typing.
document.addEventListener("click", function (e) {
  var t = e.target && e.target.closest ? e.target : null;
  if (!t) { return; }
  var open = t.closest("[data-eqe]"), cancel = t.closest("[data-eqe-cancel]");
  if (!open && !cancel) { return; }
  var li = t.closest("li, [data-action]"); var form = li && li.querySelector(".eq-edit"); var btn = li && li.querySelector("[data-eqe]");
  if (!form && open && li && (li.hasAttribute("data-id") || li.hasAttribute("data-action"))) {  // the edit form is made when it is first needed (one shared template, not one hidden form per row: a long list stays light)
    var tpl = document.getElementById("eq-edit-tpl"), sec = document.getElementById("equipment");
    if (tpl) {
      form = tpl.content.firstElementChild.cloneNode(true);
      var vals = {};
      if (li.hasAttribute("data-action")) {
        form.action = li.getAttribute("data-action");
        try { vals = JSON.parse(li.getAttribute("data-vals") || "{}"); } catch (_) { vals = {}; }
      } else {
        form.action = ((sec && sec.getAttribute("data-item-url")) || "") + li.getAttribute("data-id");
        vals = { title: li.getAttribute("data-title"), code: li.getAttribute("data-code"), status: li.getAttribute("data-status"), category: li.getAttribute("data-cat") };
      }
      Object.keys(vals).forEach(function (k) { if (form.elements[k]) { form.elements[k].value = vals[k] == null ? "" : vals[k]; } });
      var del = form.querySelector("[data-del]"); if (del && li.getAttribute("data-del-action")) { del.setAttribute("formaction", li.getAttribute("data-del-action")); }
      (li.querySelector(".eq-body") || li).appendChild(form);
    }
  }
  if (!form) { return; }
  var show = !!open && form.hidden;
  form.hidden = !show; if (btn) { btn.setAttribute("aria-expanded", show ? "true" : "false"); }
});
document.addEventListener("input", function (e) {
  var box = e.target;
  if (!box || box.id !== "eq-search") { return; }
  var q = box.value.trim().toLowerCase(), shown = 0;
  Array.prototype.forEach.call(document.querySelectorAll(".eq details.eq, details.eq"), function (cat) {
    var any = 0;
    Array.prototype.forEach.call(cat.querySelectorAll("li[data-q]"), function (li) { var hit = !q || li.getAttribute("data-q").indexOf(q) !== -1; li.hidden = !hit; if (hit) { any++; } });
    Array.prototype.forEach.call(cat.querySelectorAll(".eq-gh"), function (h) { var ul = h.nextElementSibling; h.hidden = !!(ul && !ul.querySelector("li:not([hidden])")); });
    cat.hidden = !!q && !any; if (q && any) { cat.open = true; } shown += any;
  });
  Array.prototype.forEach.call(document.querySelectorAll("article[data-q]"), function (a) { var hit = !q || a.getAttribute("data-q").indexOf(q) !== -1; a.hidden = !hit; if (hit) { shown++; } });
  Array.prototype.forEach.call(document.querySelectorAll(".rec-grid > .rec-month"), function (h) { var n = h.nextElementSibling, any = false; while (n && !n.classList.contains("rec-month")) { if (!n.hidden) { any = true; } n = n.nextElementSibling; } h.hidden = !any; });
  var c = document.getElementById("eq-count");
  if (c) { c.textContent = q ? String(shown) : c.getAttribute("data-all") || c.textContent; }
});

// data-open-details="#id": opens that <details> and scrolls to it
document.addEventListener("click", function (e) {
  var b = e.target && e.target.closest && e.target.closest("[data-open-details]");
  if (!b) { return; }
  var d = document.querySelector(b.getAttribute("data-open-details"));
  if (d) { d.open = true; d.scrollIntoView({ behavior: "smooth", block: "center" }); }
});

// equipment area: the two light buttons open their panel below (one at a time)
document.addEventListener("click", function (e) {
  var b = e.target && e.target.closest && e.target.closest("[data-eqpanel]");
  if (!b) { return; }
  var box = b.closest("details.eq"), key = b.getAttribute("data-eqpanel");
  Array.prototype.forEach.call(box.querySelectorAll(".eq-panel"), function (p) { p.hidden = p.getAttribute("data-panel") !== key ? true : !p.hidden; });
});

// data-toggle-panel="#id": shows or hides that panel
document.addEventListener("click", function (e) {
  var b = e.target && e.target.closest && e.target.closest("[data-toggle-panel]");
  if (!b) { return; }
  var p = document.querySelector(b.getAttribute("data-toggle-panel"));
  if (p) { p.hidden = !p.hidden; if (!p.hidden) { p.scrollIntoView({ behavior: "smooth", block: "center" }); } }
});

// extra work: the dots button of a job opens its edit area
document.addEventListener("click", function (e) {
  var b = e.target && e.target.closest && e.target.closest("[data-za-edit]");
  if (!b) { return; }
  var card = b.closest(".za-card"), box = card && card.querySelector(".za-edit");
  if (box) { box.hidden = !box.hidden; b.setAttribute("aria-expanded", box.hidden ? "false" : "true"); }
});

/* record cards: a tap opens the card for editing in place; Cancel or Escape closes it */
(function () {
  function close(card) { card.classList.remove('editing'); }
  document.addEventListener('click', function (e) {
    var card = e.target.closest && e.target.closest('[data-rec-edit]');
    if (!card) return;
    if (e.target.closest('[data-rec-cancel]')) { close(card); return; }
    if (e.target.closest('[data-rec-open]')) { card.classList.add('editing'); var f0 = card.querySelector('.rec-inline input, .rec-inline select, .rec-inline textarea'); if (f0) f0.focus(); return; }
    if (card.classList.contains('editing') || e.target.closest('a, button, input, select, textarea, label, form')) return;
    card.classList.add('editing');
    var first = card.querySelector('.rec-inline input, .rec-inline select, .rec-inline textarea');
    if (first) first.focus();
  });
  document.addEventListener('keydown', function (e) {
    var card = e.target.closest && e.target.closest('[data-rec-edit]');
    if (!card) return;
    if (e.key === 'Escape') close(card);
    else if (e.key === 'Enter' && e.target === card && !card.classList.contains('editing')) card.classList.add('editing');
  });
})();

// Region card: how far this device's clock is from the server's (a wrong clock confuses times shown "like on the device")
(function () {
  var now = document.querySelector(".rg-now[data-now]");
  if (!now) { return; }
  var server = Date.parse(now.getAttribute("data-now")), diff = Math.round(Math.abs(Date.now() - server) / 60000);
  if (!isNaN(diff) && diff >= 2) {
    var el = now.querySelector(".rg-skew");
    if (el) { el.textContent = (now.getAttribute("data-skew") || "").replace("{n}", String(diff)); el.hidden = false; }
  }
})();
(function () {
  /* header actions are round icons without text: the name goes into aria-label / title */
  document.querySelectorAll(".page-head .actions .button, .page-head .actions button").forEach(function (el) {
    if (el.getAttribute("aria-label")) { if (!el.title) { el.title = el.getAttribute("aria-label"); } return; }
    var text = (el.textContent || "").replace(/\s+/g, " ").trim();
    if (text) { el.setAttribute("aria-label", text); el.title = text; }
  });
})();


// [data-show-with="<selector of a switch>"]: this part is shown only while that switch is on, [data-hide-with]: only while it is off - what depends on a
// switch folds away (and comes back) at once, the page shows only what is in use.
(function () {
  function sync(root) {
    Array.prototype.forEach.call((root || document).querySelectorAll("[data-show-with],[data-hide-with]"), function (el) {
      var shows = el.hasAttribute("data-show-with"), sw = document.querySelector(el.getAttribute(shows ? "data-show-with" : "data-hide-with"));
      if (sw && sw.type === "checkbox") { el.hidden = shows ? !sw.checked : sw.checked; }
    });
  }
  document.addEventListener("change", function (e) { if (e.target && e.target.type === "checkbox") { sync(); } });
  sync();
})();
