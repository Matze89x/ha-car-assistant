/* A tab was clicked on the page before and that page changed while the marker was still swiping (see app.js): the marker goes on from where it
   would be now, so the movement is one piece. Runs right after the page, before the first paint. */
(function () {
  var raw = null;
  try { raw = sessionStorage.getItem("segFrom"); sessionStorage.removeItem("segFrom"); } catch (e) { return; }
  if (!raw) { return; }
  var f;
  try { f = JSON.parse(raw); } catch (e) { return; }
  var DUR = 340, spent = f ? Date.now() - f.t : DUR;
  if (!f || spent >= DUR || spent < 0) { return; }  /* it had finished on the old page */
  var bar = document.querySelectorAll("main .seg-tabs")[f.i];
  if (!bar || bar.querySelectorAll("a").length !== f.n) { return; }
  var on = bar.querySelector("a.on");
  if (!on) { return; }
  var box = bar.getBoundingClientRect(), b = on.getBoundingClientRect(), to = b.left - box.left + bar.scrollLeft - 1;
  if (Math.abs(to - f.left) < 2) { return; }
  var p = 1 - Math.pow(1 - spent / DUR, 3);  /* how far the old marker had come (ease out) */
  var ind = document.createElement("i");
  ind.className = "seg-ind";
  ind.style.transition = "none";
  ind.style.width = (f.w + (b.width - f.w) * p) + "px";
  ind.style.transform = "translateX(" + (f.left + (to - f.left) * p) + "px)";
  bar.classList.add("sliding"); bar.appendChild(ind);
  void ind.offsetWidth;
  ind.style.transition = "";
  ind.style.transitionDuration = (DUR - spent) + "ms";
  ind.style.width = b.width + "px";
  ind.style.transform = "translateX(" + to + "px)";
  setTimeout(function () { bar.classList.remove("sliding"); if (ind.parentNode) { ind.parentNode.removeChild(ind); } }, DUR - spent + 80);
})();
