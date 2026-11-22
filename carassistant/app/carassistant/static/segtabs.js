/* A tab was clicked on the page before and this page opened (see app.js): the marker starts where it was and swipes to the active tab. Runs right
   after the page, before the first paint; the short wait lets the page fade in first, so the swipe is seen. */
(function () {
  var raw = null;
  try { raw = sessionStorage.getItem("segFrom"); sessionStorage.removeItem("segFrom"); } catch (e) { return; }
  if (!raw) { return; }
  var f;
  try { f = JSON.parse(raw); } catch (e) { return; }
  if (!f || Date.now() - f.t > 5000) { return; }
  var bar = document.querySelectorAll("main .seg-tabs")[f.i];
  if (!bar || bar.querySelectorAll("a").length !== f.n) { return; }
  var on = bar.querySelector("a.on");
  if (!on) { return; }
  var box = bar.getBoundingClientRect(), b = on.getBoundingClientRect(), to = b.left - box.left + bar.scrollLeft - 1;
  if (Math.abs(to - f.left) < 2) { return; }
  var ind = document.createElement("i");
  ind.className = "seg-ind";
  ind.style.width = f.w + "px";
  ind.style.transform = "translateX(" + f.left + "px)";
  bar.classList.add("sliding"); bar.appendChild(ind);
  setTimeout(function () {
    ind.style.width = b.width + "px";
    ind.style.transform = "translateX(" + to + "px)";
  }, 40);
  setTimeout(function () { bar.classList.remove("sliding"); if (ind.parentNode) { ind.parentNode.removeChild(ind); } }, 700);
})();
