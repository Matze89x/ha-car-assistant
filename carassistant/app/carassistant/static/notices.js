(function () {
  /* ONE place for every notice: the slot under the page header. Page introductions (the hint under the header), "saved" messages, warnings and errors
     all land there in the same tile, with an icon and the tint of their kind. */
  var main = document.querySelector("main"), slot = main && main.querySelector(".notice-slot"), icons = document.getElementById("notice-icons");
  if (!slot) { return; }
  function icon(kind) { var s = icons && icons.content.querySelector('[data-k="' + kind + '"]'); return s ? s.firstElementChild.cloneNode(true) : null; }
  function tile(kind, nodes, cls) {
    var box = document.createElement("div"), body = document.createElement("span");
    box.className = "notice " + kind + (cls ? " " + cls : "");
    box.setAttribute("role", kind === "err" || kind === "warn" ? "alert" : "status");
    var ic = icon(kind); if (ic) { box.appendChild(ic); }
    nodes.forEach(function (n) { body.appendChild(n); });
    box.appendChild(body);
    return box;
  }
  /* messages: ?m=saved and every old .flash in the page */
  main.querySelectorAll(".flash").forEach(function (el) {
    if (el.hidden || el.id || el.closest(".notice-slot") || el.closest("dialog")) { return; }
    var kind = el.classList.contains("err") ? "err" : el.classList.contains("warn") ? "warn" : "ok";
    var box = tile(kind, Array.prototype.slice.call(el.childNodes), "");
    slot.appendChild(box); el.remove();
    if (kind === "ok") { setTimeout(function () { box.classList.add("fading"); setTimeout(function () { box.classList.add("gone"); }, 600); }, 4000); }
  });
  /* the introduction of the page: the hint right under the header (and the tabs) becomes the info tile */
  var next = slot.nextElementSibling;
  if (next) {
    var hint = null;
    if (next.matches("p.hint, span.hint")) { hint = next; }
    else if (next.matches(".set-scope")) { hint = next; }
    else if (next.matches(".pk-bar") && next.children.length === 1 && next.firstElementChild.classList.contains("hint")) { hint = next; }
    if (hint) {
      var nodes = Array.prototype.slice.call(hint.childNodes).filter(function (n) { return !(n.nodeType === 1 && n.tagName === "svg"); });
      var info = tile("info", nodes, "");
      slot.appendChild(info); hint.remove();
    }
  }
  /* "saved" fades away after a moment (the server placed it already) */
  slot.querySelectorAll(".notice.ok").forEach(function (box) {
    setTimeout(function () { box.classList.add("fading"); setTimeout(function () { box.classList.add("gone"); }, 600); }, 4000);
  });
})();
