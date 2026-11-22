/* The marker of a tab bar slides from where it was on the page before (see app.js). Runs right after the page, before the first paint. */
(function () {
  var raw = null;
  try { raw = sessionStorage.getItem("segFrom"); sessionStorage.removeItem("segFrom"); } catch (e) { return; }
  if (!raw) { return; }
  var f;
  try { f = JSON.parse(raw); } catch (e) { return; }
  if (!f || Date.now() - f.t > 4000) { return; }
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
  requestAnimationFrame(function () { requestAnimationFrame(function () {
    ind.style.width = b.width + "px";
    ind.style.transform = "translateX(" + to + "px)";
  }); });
  setTimeout(function () { bar.classList.remove("sliding"); if (ind.parentNode) { ind.parentNode.removeChild(ind); } }, 450);
})();
