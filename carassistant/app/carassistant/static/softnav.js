// Instant page changes: a click on a link of the app loads the next page in the background and swaps it in, without a browser reload. Nothing
// flashes, the styles and scripts stay loaded, and with the browser's page transition the change is a short fade. Everything else (forms,
// downloads, the login) stays an ordinary page load; anything unexpected falls back to one.
(function () {
  var ca = window.__ca;
  if (!ca || !window.fetch || !window.DOMParser || !document.querySelector(".shell:not(.setup)")) { return; }
  ca.keep = true;  // this file's own listeners are never removed
  var NO = /^\/(login|logout|setup|auth|passkey|static|icon|api|backup|export)(\/|$)|\/(export|backup|download|files|photo|video|media|ics|csv|json)(\/|$|\.)|\.[a-z0-9]{2,5}$/i;
  var token = 0, pending = null, scrolls = {}, shown = location.href.split("#")[0];

  // the system and every car are apps of their own: "/v/<car>" is one scope, everything else (settings, cars list, about ...) the system
  function scopeOf(path) {
    var m = /(?:^|\/)(?:v|app)\/([^/]+)(?:\/|$)/.exec(path.replace(/^\/api\/hassio_ingress\/[^/]+/, ""));  // /app/<car> is the start address of a car's web app
    return m ? "v/" + m[1] : "system";
  }

  function sameApp(a) {
    if (a.origin !== location.origin || a.target && a.target !== "_self" || a.hasAttribute("download") || a.hasAttribute("data-hard")) { return false; }
    if (a.pathname === location.pathname && a.search === location.search) { return false; }  // a jump inside the page
    if (scopeOf(a.pathname) !== scopeOf(location.pathname)) { return false; }  // another car or the system: a page of its own (its own design, icon and web app)
    return !NO.test(a.pathname.replace(/^\/api\/hassio_ingress\/[^/]+/, ""));  // behind Home Assistant the address starts with its ingress path
  }

  function fetchPage(url) {
    return fetch(url, { credentials: "same-origin", headers: { "X-Soft-Nav": "1" } }).then(function (r) {
      var type = r.headers.get("content-type") || "";
      if (!r.ok || type.indexOf("text/html") < 0 || /\/(login|logout|setup)(\/|$|\?)/.test(r.url)) { return null; }
      return r.text().then(function (html) { return { url: r.url, html: html }; });
    });
  }

  function loadStyles(doc) {
    var have = {};
    Array.prototype.forEach.call(document.head.querySelectorAll('link[rel="stylesheet"]'), function (l) { have[l.getAttribute("href")] = l; });
    var wait = [], want = {};
    Array.prototype.forEach.call(doc.head.querySelectorAll('link[rel="stylesheet"]'), function (l) {
      var href = l.getAttribute("href");
      want[href] = true;
      if (have[href]) { return; }
      var n = document.createElement("link");
      n.rel = "stylesheet"; n.href = href; if (l.media) { n.media = l.media; }
      wait.push(new Promise(function (ok) { n.onload = n.onerror = ok; }));
      document.head.appendChild(n);
    });
    Object.keys(have).forEach(function (href) { if (!want[href]) { have[href].parentNode.removeChild(have[href]); } });
    return Promise.all(wait);
  }

  // The navigation (side bar / bottom bar) stays in the page for good, like in a one-page app: only its state changes (active entry, dots),
  // so the marker glides once by itself. Replacing the bar with a new copy made it jump, flash and glide twice. Returns false when the bar
  // differs (other entries) - then the whole body is replaced as before.
  function keepNav(body) {
    var oldSide = document.querySelector(".shell > .side"), newSide = body.querySelector(".shell > .side");
    var oc = document.querySelector(".shell > .content"), nc = body.querySelector(".shell > .content");
    if (!oldSide || !newSide || !oc || !nc) { return false; }
    var ob = oldSide.querySelector("#tabbar"), nb = newSide.querySelector("#tabbar");
    if (!ob || !nb) { return false; }
    var ot = ob.querySelectorAll(".tab"), nt = nb.querySelectorAll(".tab");
    if (ot.length !== nt.length) { return false; }
    for (var i = 0; i < ot.length; i++) { if (ot[i].getAttribute("href") !== nt[i].getAttribute("href")) { return false; } }
    ob.className = nb.className;
    ["data-i", "data-d", "style"].forEach(function (n) { var v = nb.getAttribute(n); if (v === null) { ob.removeAttribute(n); } else { ob.setAttribute(n, v); } });
    for (var j = 0; j < ot.length; j++) {
      ot[j].classList.toggle("on", nt[j].classList.contains("on"));
      ["data-alert", "aria-label", "aria-current"].forEach(function (n) { var v = nt[j].getAttribute(n); if (v === null) { ot[j].removeAttribute(n); } else { ot[j].setAttribute(n, v); } });
    }
    ob.setAttribute("data-kept", "1");
    var of = oldSide.querySelector(".sb-foot"), nf = newSide.querySelector(".sb-foot");
    if (of && nf) { of.innerHTML = nf.innerHTML; }
    oc.replaceWith(nc);
    ["data-haptics", "data-live-poll"].forEach(function (n) { var v = body.getAttribute(n); if (v === null) { document.body.removeAttribute(n); } else { document.body.setAttribute(n, v); } });
    return true;
  }

  function swap(doc, url, push) {
    try { document.dispatchEvent(new Event("ca:leave")); } catch (e) { /* the old page may keep a still of its video (media.js) */ }
    ca.reset();
    var root = document.documentElement;
    ["lang", "dir", "data-theme"].forEach(function (n) { var v = doc.documentElement.getAttribute(n); if (v === null) { root.removeAttribute(n); } else { root.setAttribute(n, v); } });
    var accentNew = doc.getElementById("accent-custom"), accentOld = document.getElementById("accent-custom");
    if (accentNew && accentOld) { accentOld.textContent = accentNew.textContent; }
    document.title = doc.title;
    Array.prototype.forEach.call(doc.head.querySelectorAll('meta[name="color-scheme"],meta[name="theme-color"]'), function (m) {
      var old = document.head.querySelector('meta[name="' + m.getAttribute("name") + '"]' + (m.getAttribute("media") ? '[media="' + m.getAttribute("media") + '"]' : ""));
      if (old) { old.setAttribute("content", m.getAttribute("content")); }
    });
    var body = document.adoptNode(doc.body);
    var scripts = Array.prototype.slice.call(doc.head.querySelectorAll("script[src]")).concat(Array.prototype.slice.call(body.querySelectorAll("script[src]")));
    Array.prototype.forEach.call(document.head.querySelectorAll("script[src]"), function (o) {  // the page scripts of the old page: they run again below
      if (!/\/static\/(embed|softnav)\.js/.test(o.getAttribute("src"))) { o.parentNode.removeChild(o); }
    });
    if (!keepNav(body)) { document.body.replaceWith(body); }
    if (push) { history.pushState({ soft: 1 }, "", url); }
    window.scrollTo(0, 0);
    scripts.forEach(function (s) {
      var src = s.getAttribute("src");
      if (/\/static\/(embed|softnav)\.js/.test(src)) { return; }
      var n = document.createElement("script");
      n.src = src; n.async = false;
      document.head.appendChild(n);
    });
  }

  function go(url, push) {
    var mine = ++token;
    var job = pending && pending.url === url ? pending.job : fetchPage(url);
    pending = null;
    job.then(function (page) {
      if (mine !== token) { return; }
      if (!page) { location.assign(url); return; }
      var doc = new DOMParser().parseFromString(page.html, "text/html");
      if (!doc.querySelector(".shell:not(.setup)")) { location.assign(url); return; }
      scrolls[location.href] = window.scrollY;
      loadStyles(doc).then(function () {
        if (mine !== token) { return; }
        var run = function () {
          swap(doc, page.url, push);
          shown = page.url.split("#")[0];
          var hash = new URL(url, location.href).hash;  // a link with an anchor (#rp-list) keeps the reader at that card instead of the top
          var target = hash.length > 1 ? document.getElementById(decodeURIComponent(hash.slice(1))) : null;
          if (target) { history.replaceState(history.state, "", shown + hash); target.scrollIntoView(); }
        };
        run();  // no page transition: the bar stays, the content is swapped at once (a fade of the whole page made the bar flash)
      });
    }).catch(function () { location.assign(url); });
  }

  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) { return; }
    var a = e.target.closest && e.target.closest("a[href]");
    if (a && a.closest("#tabbar, .side") && a.origin === location.origin && a.pathname === location.pathname && a.search === location.search && !a.hash && !e.defaultPrevented) {
      e.preventDefault();  // the page you are on: a second tap on its entry takes you to the top, nothing reloads or glides
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    if (!a || !a.closest(".shell") || !sameApp(a)) { return; }
    e.preventDefault();
    go(a.href, true);
  });

  // start loading while the finger / mouse is still going down: the page is often there by the time the click ends
  function early(e) {
    var a = e.target.closest && e.target.closest("a[href]");
    if (!a || !a.closest(".shell") || !sameApp(a) || (pending && pending.url === a.href)) { return; }
    pending = { url: a.href, job: fetchPage(a.href) };
    pending.job.catch(function () { pending = null; });
  }
  document.addEventListener("pointerdown", early, { passive: true });

  window.addEventListener("popstate", function () { if (location.href.split("#")[0] !== shown) { go(location.href, false); } });
  ca.keep = false;
})();
