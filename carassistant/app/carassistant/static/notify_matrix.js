// Settings > User > Notifications: a tab per car (the last one is for the cars added later) shows only that car's messages; every message is a switch and the
// form saves by itself (data-live). The tab of the car you are working with is open first; the tab you chose last stays open while you stay in this window.
(function () {
  var form = document.getElementById("nm-form"), bar = form && form.querySelector(".nm-tabs");
  if (!bar) { return; }  // no car yet: the one panel is shown as it is
  var tabs = Array.prototype.slice.call(bar.querySelectorAll("[data-nm-tab]"));
  function find(key) { return tabs.filter(function (t) { return t.getAttribute("data-nm-tab") === key; })[0]; }
  function show(key, focus) {
    var on = find(key);
    if (!on) { return; }
    tabs.forEach(function (t) {
      var yes = t === on;
      t.classList.toggle("on", yes);
      t.setAttribute("aria-selected", yes ? "true" : "false");
      t.tabIndex = yes ? 0 : -1;
    });
    Array.prototype.forEach.call(form.querySelectorAll(".nm-panel"), function (p) { p.hidden = p.getAttribute("data-panel") !== key; });
    if (bar.scrollWidth > bar.clientWidth + 1) { bar.scrollLeft = on.offsetLeft - (bar.clientWidth - on.offsetWidth) / 2; }  // the open tab in the middle (more-l / more-r follow by themselves)
    if (focus) { on.focus(); }
    try { sessionStorage.setItem("nm-car", key); } catch (e) {}
  }
  bar.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest("[data-nm-tab]");
    if (!t) { return; }
    e.preventDefault();
    show(t.getAttribute("data-nm-tab"));
  });
  bar.addEventListener("keydown", function (e) {  // the arrow keys walk along the tabs
    var at = tabs.indexOf(document.activeElement), to = -1;
    if (at < 0) { return; }
    if (e.key === "ArrowRight") { to = (at + 1) % tabs.length; }
    else if (e.key === "ArrowLeft") { to = (at + tabs.length - 1) % tabs.length; }
    else if (e.key === "Home") { to = 0; }
    else if (e.key === "End") { to = tabs.length - 1; }
    if (to < 0) { return; }
    e.preventDefault();
    show(tabs[to].getAttribute("data-nm-tab"), true);
  });
  try { var was = sessionStorage.getItem("nm-car"); if (was && find(was)) { show(was); } } catch (e) {}
})();
