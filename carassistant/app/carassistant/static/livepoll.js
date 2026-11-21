// Demo car only: like a connected car, only the live values arrive. The page asks every few seconds whether they changed and
// updates just the parts that differ (no reload, so nothing flashes and the navigation stays put). Home and Security.
(function () {
  var url = document.body && document.body.getAttribute("data-live-poll");
  var path = location.pathname.replace(/\/+$/, "").replace(/^.*?(\/v\/)/, "/v/");
  if (!url || !window.fetch || !window.DOMParser || !/^\/v\/[^/]+(\/security)?$/.test(path)) { return; }
  if (/[?&]msg=/.test(location.search) && history.replaceState) { history.replaceState(null, "", location.pathname); }
  var last = null, busy = false;

  function idle() {
    var a = document.activeElement;
    return !document.hidden && !(a && /^(input|textarea|select)$/i.test(a.tagName)) && !document.querySelector("#wgrid.editing, #wgrid .dragging");
  }

  // Walk both trees together and replace only the smallest parts that differ (the widget grid keeps its element and its handlers).
  function sync(a, b) {
    if (a.outerHTML === b.outerHTML || (a.hasAttribute && a.hasAttribute("data-keep"))) { return; }  // data-keep: the car video runs by itself
    if (a.classList && b.classList && a.classList.contains("odo-drum") && b.classList.contains("odo-drum")) {  // the odometer: the digits just count on, no roll-in
      var ca = a.querySelectorAll("i"), cb = b.querySelectorAll("i");
      if (ca.length === cb.length) {
        ["data-odo", "aria-label"].forEach(function (n) { a.setAttribute(n, b.getAttribute(n)); });
        for (var k = 0; k < ca.length; k++) { ca[k].textContent = cb[k].textContent; }
        return;
      }
      b.classList.add("still");  // another number of digits: replace it, but without the effect
      a.replaceWith(b);
      return;
    }
    if (a.id === "wgrid") {
      Array.prototype.forEach.call(b.querySelectorAll(".odo-drum"), function (d) { d.classList.add("still"); });  // a rebuilt grid must not play the roll-in again
      a.innerHTML = b.innerHTML;
      return;
    }
    if (a.tagName === b.tagName && a.children.length === b.children.length && a.children.length > 0) {
      for (var i = 0; i < a.children.length; i++) { sync(a.children[i], b.children[i]); }
      return;
    }
    a.replaceWith(b);
  }

  function apply(html) {
    var doc = new DOMParser().parseFromString(html, "text/html");
    var co = document.querySelector(".content"), cn = doc.querySelector(".content");
    if (!co || !cn) { return; }
    Array.prototype.forEach.call(co.querySelectorAll(".flash"), function (f) { f.parentNode.removeChild(f); });
    sync(co, cn);
    // the alert dots on the tabs
    Array.prototype.forEach.call(document.querySelectorAll(".tab[href]"), function (t) {
      var m = doc.querySelector('.tab[href="' + t.getAttribute("href") + '"]');
      if (!m) { return; }
      if (m.getAttribute("data-alert")) { t.setAttribute("data-alert", m.getAttribute("data-alert")); } else { t.removeAttribute("data-alert"); }
    });
  }

  setInterval(function () {
    if (busy || !idle()) { return; }
    busy = true;
    fetch(url, { credentials: "same-origin", cache: "no-store" }).then(function (r) { return r.json(); }).then(function (d) {
      var changed = last !== null && d.v !== last;
      last = d.v;
      if (!changed) { return null; }
      return fetch(location.pathname, { credentials: "same-origin", cache: "no-store" }).then(function (r) { return r.text(); }).then(apply);
    }).catch(function () { /* offline: try again next time */ }).then(function () { busy = false; });
  }, 4000);
})();
