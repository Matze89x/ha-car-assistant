// The page of the Home Assistant plugin (habridge.py, docs/home-assistant.md): choose the entity of Home Assistant for every interface and see at once what it
// delivers. The app asks Home Assistant, this page only asks the app (an administrator only): entities to choose from, and a reading of what is typed.
(function () {
  var form = document.querySelector("[data-hb-form]");
  if (!form || !window.fetch) { return; }
  var panel = form.querySelector("[data-hb-panel]");
  var previewUrl = form.getAttribute("data-preview"), entitiesUrl = form.getAttribute("data-entities");
  var T = { all: form.getAttribute("data-all") || "", none: form.getAttribute("data-none") || "", noha: form.getAttribute("data-noha") || "" };
  var active = null, showAll = false, typing = null, asking = 0, checking = null, busy = false;
  var ENTITY = /^[a-z][a-z0-9_]*\.[a-z0-9_]+$/i;  // what an entity of Home Assistant looks like: while only words are typed, the field is searching, not wrong

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text !== undefined && text !== null) { n.textContent = text; }
    return n;
  }

  // the options of a row are there once an entity is chosen
  function syncOptions(input) {
    var box = input.closest(".hb-in, .hb-lrow");
    var options = box && box.querySelector(".hb-opts");
    if (options) { options.hidden = !ENTITY.test(input.value.trim()); }
  }

  // ---- what each field says (the line under it)
  function setStatus(input, info) {
    var box = input.closest(".hb-in, .hb-lrow");
    var line = box && box.querySelector("[data-hb-status]");
    if (!line) { return; }
    var level = info && info.level ? info.level : "idle";
    line.setAttribute("data-level", level);
    line.textContent = "";
    var dot = el("i", "av-dot" + (level === "ok" || level === "warn" || level === "bad" ? " " + level : ""));
    dot.setAttribute("aria-hidden", "true");
    line.appendChild(dot);
    line.appendChild(el("b", "", info ? info.text : ""));
    if (info && info.from) { line.appendChild(document.createTextNode(" ")); line.appendChild(el("small", "", info.from)); }
  }

  function check() {
    if (busy) { checking = true; return; }
    busy = true;
    var body = new URLSearchParams(new FormData(form));
    fetch(previewUrl, { method: "POST", body: body, credentials: "same-origin", headers: { "Accept": "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        busy = false;
        if (!data) { return; }
        var note = form.querySelector("[data-hb-noha]");
        if (note) { note.hidden = data.ha !== false; }  // (Home Assistant cannot be reached: the line says so)
        Array.prototype.forEach.call(form.querySelectorAll("[data-hb-entity]"), function (input) {
          var typed = input.value.trim();
          var searching = input === active && !ENTITY.test(typed);  // (words for the list below, no entity yet: nothing to say about it)
          setStatus(input, typed && !searching ? (data.rows || {})[input.name] : null);
        });
        if (checking) { checking = null; check(); }
      })
      .catch(function () { busy = false; });
  }

  function later() { clearTimeout(typing); typing = setTimeout(check, 450); }

  // ---- the list of entities to choose from
  function close() { panel.hidden = true; active = null; }

  function open(input) {
    active = input;
    var holder = input.closest(".hb-fld");
    if (holder && panel.previousElementSibling !== holder) { holder.insertAdjacentElement("afterend", panel); }
    panel.hidden = false;
    ask();
  }

  function ask() {
    if (!active) { return; }
    var mine = ++asking;
    var url = entitiesUrl + "?slot=" + encodeURIComponent(active.getAttribute("data-slot")) + "&q=" + encodeURIComponent(active.value.trim()) + "&all=" + (showAll ? 1 : 0);
    fetch(url, { credentials: "same-origin", headers: { "Accept": "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) { if (mine === asking && data) { draw(data); } })
      .catch(function () { /* the list stays as it is */ });
  }

  function draw(data) {
    panel.textContent = "";
    var list = el("div", "hb-list-opts");
    (data.entities || []).forEach(function (e) {
      var b = el("button", "hb-opt");
      b.type = "button"; b.setAttribute("role", "option"); b.setAttribute("data-id", e.id);
      var names = el("span", "hb-on");
      names.appendChild(el("b", "", e.name || e.id));
      if (e.name) { names.appendChild(el("small", "", e.id)); }
      var where = [e.device, e.area].filter(function (x, i, all) { return x && all.indexOf(x) === i; }).join(" · ");
      if (where) { names.appendChild(el("small", "hb-ctx", where)); }  // the device and the area, as Home Assistant shows them
      b.appendChild(names);
      b.appendChild(el("i", "", (e.state + (e.unit ? " " + e.unit : "")).trim()));
      list.appendChild(b);
    });
    if (!(data.entities || []).length) { list.appendChild(el("p", "hint hb-none", data.ha === false ? T.noha : T.none)); }
    panel.appendChild(list);
    var foot = el("label", "check hb-all");
    var box = document.createElement("input");
    box.type = "checkbox"; box.checked = showAll;
    box.addEventListener("change", function () { showAll = box.checked; ask(); if (active) { active.focus(); } });
    foot.appendChild(box);
    foot.appendChild(el("span", "", T.all));
    panel.appendChild(foot);
  }

  panel.addEventListener("mousedown", function (e) { e.preventDefault(); });  // choosing must not take the focus from the field first
  panel.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest(".hb-opt");
    if (!b || !active) { return; }
    var input = active;
    input.value = b.getAttribute("data-id");
    syncOptions(input);
    close();
    input.dispatchEvent(new Event("change", { bubbles: true }));
    check();
  });

  form.addEventListener("focusin", function (e) { if (e.target.matches && e.target.matches("[data-hb-entity]") && active !== e.target) { open(e.target); } });
  form.addEventListener("input", function (e) {
    if (e.target.matches && e.target.matches("[data-hb-entity]")) { syncOptions(e.target); }
    if (e.target.matches && e.target.matches("[data-hb-entity]")) { if (active !== e.target) { open(e.target); } else { clearTimeout(typing); typing = setTimeout(function () { ask(); check(); }, 250); } }
  });
  form.addEventListener("change", function (e) { if (!panel.contains(e.target)) { later(); } });
  form.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && active) { close(); }
    if (e.key === "Enter" && e.target.matches && e.target.matches("[data-hb-entity], .hb-n")) { e.preventDefault(); }  // Enter picks nothing and does not save by accident
    if (e.key === "ArrowDown" && active && e.target === active) { var first = panel.querySelector(".hb-opt"); if (first) { e.preventDefault(); first.focus(); } }
  });
  panel.addEventListener("keydown", function (e) {
    var cur = document.activeElement;
    if (!cur || !cur.classList.contains("hb-opt")) { return; }
    if (e.key === "ArrowDown" && cur.nextElementSibling) { e.preventDefault(); cur.nextElementSibling.focus(); }
    if (e.key === "ArrowUp") { e.preventDefault(); if (cur.previousElementSibling) { cur.previousElementSibling.focus(); } else if (active) { active.focus(); } }
  });
  form.addEventListener("click", function (e) {
    var pick = e.target.closest && e.target.closest("[data-hb-pick]");
    if (pick) { var input = pick.closest(".hb-fld").querySelector("[data-hb-entity]"); input.focus(); if (active !== input) { open(input); } else { close(); } return; }
    var add = e.target.closest && e.target.closest("[data-hb-add]");
    if (add) { addRow(add.closest(".hb-in").querySelector("[data-hb-list]")); return; }
    var del = e.target.closest && e.target.closest("[data-hb-del]");
    if (del) { var row = del.closest("[data-hb-lrow]"); if (active && row.contains(active)) { close(); } row.remove(); check(); }
  });
  document.addEventListener("click", function (e) { if (active && !form.contains(e.target)) { close(); } });
  document.addEventListener("focusin", function (e) { if (active && !form.contains(e.target)) { close(); } });

  // ---- a row more in a list (doors, windows, lights, warnings)
  function addRow(list) {
    if (!list) { return; }
    var next = parseInt(list.getAttribute("data-next"), 10) || 0, max = parseInt(list.getAttribute("data-max"), 10) || 16;
    if (list.querySelectorAll("[data-hb-lrow]").length >= max) { return; }
    var tpl = list.querySelector("template[data-hb-tpl]");
    var holder = document.createElement("div");
    holder.innerHTML = tpl.innerHTML.replace(/\.#\./g, "." + next + ".").replace(/\.#"/g, "." + next + '"');
    var row = holder.firstElementChild;
    list.insertBefore(row, tpl);
    list.setAttribute("data-next", String(next + 1));
    var name = row.querySelector(".hb-n");
    if (name) { name.focus(); }
  }

  check();
  setInterval(function () { if (!document.hidden) { check(); } }, 15000);  // the car moves on: the lines say what Home Assistant says now
})();
