// Vehicle photos & videos.
// Home: the car's video plays ONCE and then stands still on its last frame (it is copied into a canvas, so leaving and coming back never
// shows the start again); tapping it plays it again. It starts when the picture is really visible, pauses when it is not, and falls back to the
// photo when it cannot play (power saving, errors, "reduce motion").
// Library page: thumbnails of videos load their first frame only when they are scrolled into view; a chosen file uploads at once.
(function () {
  // ---- what Home shows and the car's photo: every choice is saved at once (no Save button)
  var choose = document.getElementById("mediasel");
  if (choose) {
    Array.prototype.forEach.call(document.querySelectorAll('input[form="mediasel"]'), function (r) {
      r.addEventListener("change", function () { choose.submit(); });
    });
  }
  // ---- the library page
  // A chosen video: take one picture of it (about the middle, 640 px wide) and send it along as its preview; any failure just skips it.
  function takePoster(file, slot, done) {
    var url, vid = document.createElement("video"), finished = false;
    function end() { if (finished) { return; } finished = true; if (url) { URL.revokeObjectURL(url); } done(); }
    try {
      url = URL.createObjectURL(file); vid.muted = true; vid.preload = "metadata"; vid.setAttribute("playsinline", "");
      vid.addEventListener("loadedmetadata", function () { try { vid.currentTime = vid.duration > 1 ? vid.duration / 2 : 0; } catch (e) { end(); } }, { once: true });
      vid.addEventListener("seeked", function () {
        try {
          var w = Math.min(640, vid.videoWidth), h = Math.round(w * vid.videoHeight / vid.videoWidth), c = document.createElement("canvas");
          c.width = w; c.height = h; c.getContext("2d").drawImage(vid, 0, 0, w, h);
          c.toBlob(function (b) {
            try { if (b && window.DataTransfer) { var dt = new DataTransfer(); dt.items.add(new File([b], "poster.jpg", { type: "image/jpeg" })); slot.files = dt.files; } } catch (e) { /* no preview */ }
            end();
          }, "image/jpeg", 0.8);
        } catch (e) { end(); }
      }, { once: true });
      vid.addEventListener("error", end, { once: true });
      setTimeout(end, 4000); vid.src = url;
    } catch (e) { end(); }
  }
  Array.prototype.forEach.call(document.querySelectorAll("[data-autosubmit]"), function (el) {
    el.addEventListener("change", function () {
      var go = function () { if (el.form) { el.form.submit(); } else { el.submit(); } };
      var f = el.files && el.files[0], slot = el.form && el.form.querySelector(".poster-slot");
      if (el.hasAttribute("data-poster") && f && slot && /^video\//.test(f.type)) { takePoster(f, slot, go); } else { go(); }
    });
  });
  var thumbs = document.querySelectorAll(".media-pick video[data-src]");
  if (thumbs.length) {
    var load = function (v) {
      v.preload = "metadata";
      v.addEventListener("loadedmetadata", function () { try { if (v.duration > 1) { v.currentTime = v.duration / 2; } } catch (e) { /* keeps the first frame */ } }, { once: true });  // the preview is the middle of the video
      v.src = v.getAttribute("data-src"); v.removeAttribute("data-src");
    };
    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) { io.unobserve(e.target); load(e.target); } }); });
      Array.prototype.forEach.call(thumbs, function (v) { io.observe(v); });
    } else { Array.prototype.forEach.call(thumbs, load); }
  }

  // ---- the hero video
  var v = document.querySelector("video.hero-video");
  if (!v) { return; }
  var wrap = v.parentNode, kind = v.getAttribute("data-kind") || "adapt";
  function giveUp() { wrap.classList.add("failed"); if (v.parentNode) { v.parentNode.removeChild(v); } }
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) { giveUp(); return; }

  var done = false, seeking = false, canvas = null, shown = false, sampled = false, tries = 0, watchdog = null;
  // The video plays once per visit of the app. Its last frame is kept (as a picture, in the browser's session storage); coming back to Home shows
  // that picture at once - the video is not loaded or started again until it is tapped.
  var KEY = "ca.vp:" + (v.getAttribute("data-src") || ""), saved = null, usedSaved = false;
  try { saved = sessionStorage.getItem(KEY + ":img"); } catch (e) { saved = null; }
  var savedT = null, resumeAt = 0;  // the second the video had reached when the page was left before its end
  try { savedT = sessionStorage.getItem(KEY + ":t"); } catch (e) { savedT = null; }

  // "Match": the page rebuilds the video's background from its left and right edge colours (top to bottom), behind the video.
  function sampleBg() {
    var c = document.createElement("canvas"); c.width = 96; c.height = 54;
    var x = c.getContext("2d"); x.drawImage(v, 0, 0, 96, 54);
    var d = x.getImageData(0, 0, 96, 54).data, stops = [], r, rr, k, col, i, R, G, B, n, seen = 0;
    for (r = 0; r < 54; r += 4) {
      R = G = B = n = 0;
      for (rr = r; rr < Math.min(r + 4, 54); rr++) {
        for (k = 0; k < 8; k++) {
          col = k < 4 ? k : 92 + k; i = (rr * 96 + col) * 4;
          if (d[i + 3] > 0) { seen++; }
          R += d[i]; G += d[i + 1]; B += d[i + 2]; n++;
        }
      }
      stops.push("rgb(" + Math.round(R / n) + "," + Math.round(G / n) + "," + Math.round(B / n) + ") " + ((r + 2) / 54 * 100).toFixed(1) + "%");
    }
    return seen ? "linear-gradient(to bottom," + stops.join(",") + ")" : null;
  }
  function reveal() {
    if (kind === "adapt" && !sampled) {
      var g = null; try { g = sampleBg(); } catch (e) { g = null; }
      if (g) { wrap.style.setProperty("--hero-bg", g); sampled = true; }
      else if (tries++ < 6) { setTimeout(reveal, 120); return; }
      else { wrap.classList.remove("adapt"); wrap.classList.add("black"); }  // could not read the edges: blend like "Black"
    }
    wrap.classList.add("vplay");
  }
  function freeze() {
    if (canvas) { return true; }
    try {
      var w = v.videoWidth, h = v.videoHeight; if (!w || !h) { return false; }
      var c = document.createElement("canvas"); c.width = w; c.height = h;
      var x = c.getContext("2d"); x.drawImage(v, 0, 0, w, h);
      if (!x.getImageData(w >> 1, h >> 1, 1, 1).data[3] && !x.getImageData(2, 2, 1, 1).data[3]) { return false; }
      c.className = "hero-video hero-frozen"; c.setAttribute("aria-hidden", "true");
      v.parentNode.insertBefore(c, v.nextSibling); v.classList.add("vgone"); canvas = c; return true;
    } catch (e) { return false; }
  }
  function unfreeze() {
    v.classList.remove("vgone");
    if (canvas) { canvas.parentNode.removeChild(canvas); canvas = null; }
  }
  // A picture of what the video shows right now (or of its frozen last frame): kept when Home is left, so coming back never shows an empty box.
  function stillOf() {
    if (canvas && canvas.toDataURL) { try { return canvas.toDataURL("image/jpeg", 0.85); } catch (e) { return ""; } }
    try {
      var w = v.videoWidth, h = v.videoHeight; if (!w || !h || v.readyState < 2) { return ""; }
      var k = Math.min(1, 960 / w), c = document.createElement("canvas"); c.width = Math.round(w * k); c.height = Math.round(h * k);
      var x = c.getContext("2d"); x.drawImage(v, 0, 0, c.width, c.height);
      if (!x.getImageData(c.width >> 1, c.height >> 1, 1, 1).data[3] && !x.getImageData(2, 2, 1, 1).data[3]) { return ""; }
      return c.toDataURL("image/jpeg", 0.85);
    } catch (e) { return ""; }
  }
  function remember(partial) {
    var img = stillOf(); if (!img) { return; }
    try {
      sessionStorage.setItem(KEY + ":img", img);
      sessionStorage.setItem(KEY + ":bg", wrap.style.getPropertyValue("--hero-bg") || "");
      if (partial) { sessionStorage.setItem(KEY + ":t", String(v.currentTime || 0)); } else { sessionStorage.removeItem(KEY + ":t"); }
    } catch (e) { /* too big or no storage */ }
  }
  function leaving() { if (!done) { remember(true); } }
  document.addEventListener("ca:leave", leaving);
  window.addEventListener("pagehide", leaving);
  // Without a canvas: when Home comes back and the video no longer stands at its end, jump to the last frame (hidden meanwhile).
  function reseek() {
    if (!done || canvas || !isFinite(v.duration) || Math.abs(v.currentTime - v.duration) < 0.15) { return; }
    wrap.classList.remove("vplay"); seeking = true;
    try { v.currentTime = Math.max(0, v.duration - 0.04); } catch (e) { seeking = false; wrap.classList.add("vplay"); }
  }
  v.addEventListener("loadedmetadata", function () {
    if (v.videoWidth && v.videoHeight) { wrap.style.aspectRatio = v.videoWidth + " / " + v.videoHeight; }
    if (resumeAt > 0 && isFinite(v.duration)) {  // Home was left in the middle of the video: go on where it stopped (the picture of that moment stands meanwhile)
      if (resumeAt >= v.duration - 0.2) { done = true; seeking = true; try { v.currentTime = Math.max(0, v.duration - 0.04); } catch (e) { seeking = false; } }
      else { try { v.currentTime = resumeAt; } catch (e) { /* plays from the start */ } }
      resumeAt = 0;
    }
  });
  v.addEventListener("seeked", function () { if (seeking) { seeking = false; freeze(); wrap.classList.add("vplay"); } });
  v.addEventListener("loadeddata", reveal);  // the first frame shows at once: no empty box, and no photo, before the video starts
  v.addEventListener("playing", function () { reveal(); if (usedSaved && !done && canvas) { unfreeze(); usedSaved = false; } });  // the resumed video takes over from the picture
  v.addEventListener("ended", function () {
    done = true; v.pause(); freeze();
    remember(false);
    if (kind === "adapt" && sampled) { try { var g = sampleBg(); if (g) { wrap.style.setProperty("--hero-bg", g); } } catch (e) { /* keep the first sample */ } }
  });
  v.addEventListener("error", giveUp);
  function go() {
    if (done || v.ended || !shown || document.hidden) { return; }
    if (!watchdog) { watchdog = setTimeout(function () { if (!wrap.classList.contains("vplay")) { giveUp(); } }, 9000); }
    var p = v.play(); if (p && p.catch) { p.catch(function () { if (!wrap.classList.contains("vplay")) { giveUp(); } }); }
  }
  // Tap: plays again from the start (only when it is not running); the standing last frame is replaced at that very moment.
  wrap.addEventListener("click", function () {
    if (!v.parentNode) { return; }
    if (v.ended || v.paused) {
      if (!v.getAttribute("src")) { v.src = v.getAttribute("data-src"); }
      unfreeze(); try { v.currentTime = 0; } catch (e) { /* not seekable yet */ }
      done = false; shown = true;
      var p = v.play(); if (p && p.catch) { p.catch(function () { /* stays on the last frame */ }); }
    }
  });
  document.addEventListener("visibilitychange", function () { if (document.hidden) { if (!done) { remember(true); v.pause(); } } else if (done) { reseek(); } else { go(); } });
  if (saved) {
    var pic = new Image();
    pic.className = "hero-video hero-frozen"; pic.alt = ""; pic.setAttribute("aria-hidden", "true");
    var partial = savedT !== null && isFinite(parseFloat(savedT));  // left before the end: the video goes on from there
    pic.onload = function () {
      var bg = ""; try { bg = sessionStorage.getItem(KEY + ":bg") || ""; } catch (e) { bg = ""; }
      if (bg && kind === "adapt") { wrap.style.setProperty("--hero-bg", bg); }
      v.classList.add("vgone"); canvas = pic; done = !partial; usedSaved = true; sampled = true;
      wrap.classList.add("vplay");
    };
    pic.onerror = function () { try { sessionStorage.removeItem(KEY + ":img"); } catch (e) { /* ignore */ } };
    v.parentNode.insertBefore(pic, v.nextSibling);
    pic.src = saved;
    if (!partial) { return; }
    resumeAt = parseFloat(savedT);
  }
  v.src = v.getAttribute("data-src");
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (es) {
      es.forEach(function (e) { shown = e.isIntersecting; if (shown) { if (done) { reseek(); } else { go(); } } else if (!done) { v.pause(); } });
    }).observe(wrap);
  } else { shown = true; go(); }
})();
