// Loaded in the <head> without defer, so the class is set before the first paint (no layout jump on every page).
// Embedded in Home Assistant (iframe): the surrounding app already handles the notch, so drop our own safe-area margins.
// An installed web app (home screen): the little "change car" sign is not needed there - every car has its own web app.
try { if (window.navigator.standalone === true || (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches)) { document.documentElement.classList.add("is-app"); } } catch (e) { /* no class */ }
try { if (window.self !== window.top) { document.documentElement.classList.add("embedded"); } } catch (e) { document.documentElement.classList.add("embedded"); }
// Instant page changes (softnav.js) replace the page without a browser reload. For that every listener a page script puts on the document /
// window and every timer it starts is remembered here, so the next page can start from a clean state (no handler runs twice, no old timer goes on).
(function () {
  var add = EventTarget.prototype.addEventListener, setI = window.setInterval, setT = window.setTimeout;
  var listeners = [], timers = [];
  window.__ca = { keep: false, listeners: listeners, timers: timers, add: add };
  EventTarget.prototype.addEventListener = function (type, fn, opts) {
    if (!window.__ca.keep && (this === document || this === window || this === document.documentElement)) { listeners.push([this, type, fn, opts]); }
    return add.call(this, type, fn, opts);
  };
  window.setInterval = function () { var id = setI.apply(window, arguments); if (!window.__ca.keep) { timers.push(id); } return id; };
  window.setTimeout = function () { var id = setT.apply(window, arguments); if (!window.__ca.keep) { timers.push(id); } return id; };
  window.__ca.reset = function () {
    listeners.splice(0).forEach(function (l) { l[0].removeEventListener(l[1], l[2], l[3]); });
    timers.splice(0).forEach(function (id) { clearInterval(id); clearTimeout(id); });
  };
})();
