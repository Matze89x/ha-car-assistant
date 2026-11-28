// Demo car only: like a connected car, only the live values arrive. The page asks every few seconds whether they changed and
// updates just the parts that differ (no reload, so nothing flashes and the navigation stays put). Home and Security; on the Charging page the card of the wallbox.
(function () {
  var url = document.body && document.body.getAttribute("data-live-poll");
  var path = location.pathname.replace(/\/+$/, "").replace(/^.*?(\/v\/)/, "/v/");
  if (!url || !window.fetch || !window.DOMParser || !/^\/v\/[^/]+(\/security|\/e\/fuel)?$/.test(path)) { return; }
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
      if (ca.length === cb.length && a.getAttribute("data-odo") === b.getAttribute("data-odo")) { return; }  // the same figure: leave the rolled strips alone
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
      if (a.classList && a.classList.contains("wd") && a.className !== b.className) { a.className = b.className; }  // a tile's state colour (charging -> fault)
      // The parts are taken BEFORE anything is replaced: a part that is put into the page leaves the tree it came from, and with a live list the next one
      // would be the wrong one (a card with the pill of one state and the note of another).
      var pa = parts(a), pb = parts(b);
      if (pa.length !== pb.length || pa.some(function (p, n) { return p.nodeType !== pb[n].nodeType; })) { a.replaceWith(b); return; }  // other words between the elements
      for (var i = 0; i < pa.length; i++) {
        if (pa[i].nodeType === 3) { if (pa[i].nodeValue !== pb[i].nodeValue) { pa[i].nodeValue = pb[i].nodeValue; } } else { sync(pa[i], pb[i]); }
      }
      return;
    }
    a.replaceWith(b);
  }

  // The elements of a node and the words that stand between them (an icon and its label), without the blanks of the markup.
  function parts(n) {
    return Array.prototype.filter.call(n.childNodes, function (c) { return c.nodeType === 1 || (c.nodeType === 3 && /\S/.test(c.nodeValue)); });
  }

  // The attributes of an element that stays (the state of the card, the class of the ring, the length of the arc, the width of a bar) are changed in place, so that
  // what has a transition in the style sheet moves instead of jumping; an opened <details> stays open.
  function attrs(a, b) {
    if (a.nodeType !== 1 || b.nodeType !== 1 || a.tagName !== b.tagName) { return; }
    Array.prototype.forEach.call(b.attributes, function (x) { if (a.getAttribute(x.name) !== x.value) { a.setAttribute(x.name, x.value); } });
    Array.prototype.slice.call(a.attributes).forEach(function (x) { if (x.name !== "open" && !b.hasAttribute(x.name)) { a.removeAttribute(x.name); } });
    if (a.children.length === b.children.length) { for (var i = 0; i < a.children.length; i++) { attrs(a.children[i], b.children[i]); } }
  }

  function apply(html) {
    var doc = new DOMParser().parseFromString(html, "text/html");
    if (/\/e\/fuel$/.test(path)) {  // the Charging page holds forms: only the card of the wallbox is read again, never what somebody is typing
      var card = document.getElementById("wb"), fresh = doc.getElementById("wb");
      if (card && fresh) {
        try {
          attrs(card, fresh);
          sync(card, fresh);
        } catch (e) {  // whatever went wrong: the card as the server says it, whole
          if (window.console) { console.error("livepoll: " + e); }
          card.replaceWith(new DOMParser().parseFromString(html, "text/html").getElementById("wb"));
        }
      }
      return;
    }
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
