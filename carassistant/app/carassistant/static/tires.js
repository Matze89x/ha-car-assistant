/* Tyre edit page: the three season tabs switch the panels of the one form without a reload (nothing typed is lost) */
(function () {
  var form = document.querySelector("form[data-tabs]");
  if (!form) return;
  var view = form.querySelector("[data-view]");
  form.addEventListener("click", function (e) {
    var tab = e.target.closest("[data-tab]");
    if (!tab) return;
    e.preventDefault();
    e.stopPropagation();
    var sn = tab.getAttribute("data-tab");
    form.querySelectorAll("[data-tab]").forEach(function (t) { t.classList.toggle("on", t === tab); });
    form.querySelectorAll("[data-panel]").forEach(function (p) { p.hidden = p.getAttribute("data-panel") !== sn; });
    if (view) view.value = sn;
  }, true);
})();
