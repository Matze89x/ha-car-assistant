// Home: edit the widgets live. "Edit widgets" turns Home into an editor: drag a widget by its grip to move it (the others
// shift), drag the bar on its right edge to make it small or wide, tap the eye to hide it. Every change is saved at once.
(function () {
  var grid = document.getElementById("wgrid");
  var btn = document.getElementById("wd-toggle");
  var tpl = document.getElementById("wd-tpl");
  if (!grid || !btn || !tpl || !window.fetch) { return; }

  var saveTimer = null;
  function slots() { return Array.prototype.slice.call(grid.querySelectorAll(".wd-slot")); }

  function save() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function () {
      var fd = new FormData();
      fd.append("ajax", "1");
      slots().forEach(function (s) {
        var k = s.getAttribute("data-k");
        fd.append("k", k);
        fd.append("size_" + k, s.classList.contains("m") ? "m" : "s");
        if (!s.classList.contains("off")) { fd.append("on_" + k, "1"); }
        if (s.hasAttribute("data-opts")) {  // settings of the widget (its edit button)
          JSON.parse(s.getAttribute("data-opts")).forEach(function (o) { fd.append("opt_" + k + "_" + o.key, s.getAttribute("data-opt-" + o.key)); });
        }
      });
      fetch(grid.getAttribute("data-save"), { method: "POST", body: fd, credentials: "same-origin" });
    }, 250);
  }

  // Smooth reflow: remember where every slot was, change the layout, slide each one from its old place.
  function flip(change) {
    var all = slots(), before = all.map(function (s) { return s.getBoundingClientRect(); });
    change();
    if (!all[0] || !all[0].animate) { return; }
    all.forEach(function (s, i) {
      var now = s.getBoundingClientRect(), dx = before[i].left - now.left, dy = before[i].top - now.top;
      if (dx || dy) { s.animate([{ transform: "translate(" + dx + "px," + dy + "px)" }, { transform: "none" }], { duration: 180, easing: "ease-out" }); }
    });
  }

  function setSize(slot, size) {
    slot.classList.toggle("m", size === "m");
    slot.classList.toggle("s", size !== "m");
    Array.prototype.forEach.call(slot.querySelectorAll(".wd"), function (w) { w.classList.toggle("m", size === "m"); w.classList.toggle("s", size !== "m"); });  // every look of the widget
  }

  function setLabel(editing) {
    var span = btn.querySelector(".lbl");
    if (span) { span.textContent = grid.getAttribute(editing ? "data-done" : "data-edit"); }
  }

  // The edit button of a widget opens its settings window: one select per option (the look, later more). Changes apply and save at once.
  var labels = {};
  try { labels = JSON.parse(grid.getAttribute("data-labels") || "{}"); } catch (err) { labels = {}; }
  function openSettings(slot) {
    var dlg = document.getElementById("wopt"), body = document.getElementById("wopt-body");
    if (!dlg || !body || !dlg.showModal) { return; }
    document.getElementById("wopt-t").textContent = slot.getAttribute("data-title") || "";
    body.textContent = "";
    JSON.parse(slot.getAttribute("data-opts")).forEach(function (o) {
      var label = document.createElement("label"), sel = document.createElement("select");
      label.textContent = labels[o.key] || o.key;
      o.choices.forEach(function (c) {
        var opt = document.createElement("option");
        opt.value = c; opt.textContent = labels[o.key + "." + c] || c;
        if (c === slot.getAttribute("data-opt-" + o.key)) { opt.selected = true; }
        sel.appendChild(opt);
      });
      sel.addEventListener("change", function () {
        flip(function () { slot.setAttribute("data-opt-" + o.key, sel.value); });
        save();
      });
      label.appendChild(sel);
      body.appendChild(label);
    });
    dlg.showModal();
  }

  function enter() {
    document.body.classList.add("page-editing");  // the picture shows its own "Edit" button
    grid.classList.add("editing");
    slots().forEach(function (s) { if (!s.querySelector(".wd-ctl")) { s.appendChild(tpl.content.cloneNode(true)); } });
    setLabel(true);
  }
  function leave() { grid.classList.remove("editing"); document.body.classList.remove("page-editing"); setLabel(false); }

  // "Edit page" turns the dashboard itself into the editor (widgets can be moved, resized, hidden; the picture gets an "Edit" button); the same button finishes.
  btn.addEventListener("click", function (e) {
    e.preventDefault();
    if (grid.classList.contains("editing")) { leave(); } else { enter(); }
  });
  // coming back from an upload / delete inside the picture window: stay in edit mode and open the window again
  if (/[?&]edit=1/.test(location.search)) {
    enter();
    var dlg0 = document.getElementById("pe");
    if (dlg0 && dlg0.showModal) { dlg0.showModal(); }
    if (history.replaceState) { history.replaceState(null, "", location.pathname); }
  }

  // In edit mode the widgets are not links.
  grid.addEventListener("click", function (e) {
    if (!grid.classList.contains("editing")) { return; }
    var eye = e.target.closest && e.target.closest(".wd-eye");
    if (eye) { e.preventDefault(); eye.closest(".wd-slot").classList.toggle("off"); save(); return; }
    var eb = e.target.closest && e.target.closest(".wd-edit-btn");
    if (eb) { e.preventDefault(); openSettings(eb.closest(".wd-slot")); return; }
    if (e.target.closest && e.target.closest("a.wd-addtile")) { return; }
    if (e.target.closest && e.target.closest("a")) { e.preventDefault(); }
  }, true);

  // Drag to move / drag the edge to resize.
  var drag = null;
  grid.addEventListener("pointerdown", function (e) {
    if (!grid.classList.contains("editing")) { return; }
    var grip = e.target.closest && e.target.closest(".wd-grip");
    var rs = e.target.closest && e.target.closest(".wd-rs");
    if (!grip && !rs) { return; }
    var slot = e.target.closest(".wd-slot");
    if (rs && slot && slot.classList.contains("locked")) { return; }  // Attention, vehicle data and position stay one full row
    e.preventDefault();
    try { e.target.setPointerCapture(e.pointerId); } catch (err) { /* not supported: the document listeners below still work */ }
    drag = { slot: slot, mode: grip ? "move" : "size", x0: e.clientX, y: e.clientY, id: e.pointerId };
    grid.classList.add(grip ? "is-dragging" : "is-resizing");
    if (rs) { slot.classList.add("resizing"); }
    if (grip) {
      var r = slot.getBoundingClientRect(), g = slot.querySelector(".wd").cloneNode(true);
      g.className += " wd-ghost";
      g.style.width = r.width + "px"; g.style.height = r.height + "px";
      g.style.left = r.left + "px"; g.style.top = r.top + "px";
      drag.dx = e.clientX - r.left; drag.dy = e.clientY - r.top;
      document.body.appendChild(g);
      drag.ghost = g;
      slot.classList.add("dragging");
    }
  });

  document.addEventListener("pointermove", function (e) {
    if (!drag || e.pointerId !== drag.id) { return; }
    e.preventDefault();
    if (drag.mode === "size") {
      var dx = e.clientX - drag.x0, isWide = drag.slot.classList.contains("m");
      if (dx > 40 && !isWide) { flip(function () { setSize(drag.slot, "m"); }); drag.x0 = e.clientX; }
      else if (dx < -40 && isWide) { flip(function () { setSize(drag.slot, "s"); }); drag.x0 = e.clientX; }
      return;
    }
    drag.y = e.clientY;
    autoscroll();
    drag.ghost.style.left = e.clientX - drag.dx + "px";
    drag.ghost.style.top = e.clientY - drag.dy + "px";
    var under = document.elementFromPoint(e.clientX, e.clientY), target = under && under.closest && under.closest(".wd-slot");
    if (!target || target === drag.slot) { return; }
    var rect = target.getBoundingClientRect();
    var before = target.classList.contains("m") ? e.clientY < rect.top + rect.height / 2 : e.clientX < rect.left + rect.width / 2;
    flip(function () { grid.insertBefore(drag.slot, before ? target : target.nextSibling); });
  });

  // Long pages: scroll while a widget is held near the top or bottom edge of the screen.
  var scrolling = false;
  function autoscroll() {
    if (scrolling) { return; }
    scrolling = true;
    (function step() {
      if (!drag || drag.mode !== "move") { scrolling = false; return; }
      var edge = 90, speed = 0;
      if (drag.y < edge) { speed = -Math.ceil((edge - drag.y) / 6); }
      else if (drag.y > window.innerHeight - edge) { speed = Math.ceil((drag.y - (window.innerHeight - edge)) / 6); }
      if (speed) { window.scrollBy(0, speed); }
      requestAnimationFrame(step);
    })();
  }

  function finish(e) {
    if (!drag || (e && e.pointerId !== drag.id)) { return; }
    grid.classList.remove("is-dragging", "is-resizing");
    drag.slot.classList.remove("resizing");
    if (drag.ghost) { drag.ghost.parentNode.removeChild(drag.ghost); }
    drag.slot.classList.remove("dragging");
    drag = null;
    save();
  }
  document.addEventListener("pointerup", finish);
  document.addEventListener("pointercancel", finish);

  // Touch: pressing a widget for half a second opens the editor (like on a phone's home screen) instead of the system's link menu.
  var hold = null, swallow = false;
  function cancelHold() { if (hold) { clearTimeout(hold.timer); hold = null; } }
  grid.addEventListener("pointerdown", function (e) {
    if (e.pointerType === "mouse" || grid.classList.contains("editing")) { return; }
    if (!(e.target.closest && e.target.closest(".wd-slot"))) { return; }
    cancelHold();
    hold = { x: e.clientX, y: e.clientY, timer: setTimeout(function () {
      hold = null;
      swallow = true;
      enter();
      if (navigator.vibrate) { try { navigator.vibrate(12); } catch (err) { /* no haptics */ } }
    }, 500) };
  });
  document.addEventListener("pointermove", function (e) {
    if (hold && Math.abs(e.clientX - hold.x) + Math.abs(e.clientY - hold.y) > 10) { cancelHold(); }
  });
  ["pointerup", "pointercancel", "scroll"].forEach(function (n) { document.addEventListener(n, cancelHold, true); });
  // The release after the long press must not follow the link under the finger.
  grid.addEventListener("click", function (e) {
    if (!swallow) { return; }
    swallow = false;
    e.preventDefault();
    e.stopPropagation();
  }, true);
  grid.addEventListener("pointerdown", function () { swallow = false; }, true);
})();

// The odometer drums: after the roll-in the last three units of distance tick up to the real value (a few text changes, finished with the roll-in).
(function () {
  var el = Array.prototype.filter.call(document.querySelectorAll(".odo-drum[data-odo]"), function (d) { return d.offsetParent !== null && !d.closest(".odo-flip"); })[0];  // the plate rolls by itself (app.js)
  if (!el || (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)) { return; }
  var n = parseInt(el.getAttribute("data-odo"), 10), cells = el.querySelectorAll("i");
  if (isNaN(n) || n < 3 || String(n - 3).length !== cells.length) { return; }
  function show(v) { var s = String(v); for (var i = 0; i < cells.length; i++) { cells[i].textContent = s.charAt(i); } }
  show(n - 3);
  var step = 0;
  setTimeout(function tick() { step += 1; show(n - 3 + step); if (step < 3) { setTimeout(tick, 330); } }, 300);  // done about when the roll-in has settled
})();
