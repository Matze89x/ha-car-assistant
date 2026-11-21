// Magnifier next to the vehicle fields (only when switched on under Settings > System): opens a Google search for the vehicle and the field in a
// new tab. The app sends nothing: the address is built here and only opened by a click.
(function () {
  var form = document.getElementById("vform");
  if (!form) { return; }
  var FIELDS = ["variant", "model_type", "hsn", "tsn", "engine", "engine_code", "gearbox_code", "oil_spec", "oil_l", "power_kw", "displacement_ccm",
    "gross_weight_kg", "tank_l", "battery_kwh", "battery", "paint_code", "seats"];
  function val(name) { var e = document.querySelector('#vform [name="' + name + '"], [form="vform"][name="' + name + '"]'); return e && e.value ? e.value.trim() : ""; }
  FIELDS.forEach(function (name) {
    var input = document.querySelector('[form="vform"][name="' + name + '"]') || form.querySelector('[name="' + name + '"]');
    if (!input || input.tagName !== "INPUT") { return; }
    var label = input.closest("label");
    if (!label || label.querySelector(".gs")) { return; }
    var node = label.firstChild, text = "";
    while (node && !text) { if (node.nodeType === 3) { text = node.textContent.replace(/\*/g, "").trim(); } node = node.nextSibling; }
    var a = document.createElement("a");
    a.className = "gs"; a.target = "_blank"; a.rel = "noopener noreferrer"; a.title = text; a.setAttribute("aria-label", text);
    a.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path fill="currentColor" d="M9.5,3A6.5,6.5 0 0,1 16,9.5C16,11.11 15.41,12.59 14.44,13.73L14.71,14H15.5L20.5,19L19,20.5L14,15.5V14.71L13.73,14.44C12.59,15.41 11.11,16 9.5,16A6.5,6.5 0 0,1 3,9.5A6.5,6.5 0 0,1 9.5,3M9.5,5C7,5 5,7 5,9.5C5,12 7,14 9.5,14C12,14 14,12 14,9.5C14,7 12,5 9.5,5Z"/></svg>';
    a.href = "#";
    a.addEventListener("click", function () {
      var car = [val("make"), val("model"), val("year"), val("variant"), val("engine")].filter(function (x, i, all) { return x && all.indexOf(x) === i; }).join(" ");
      a.href = "https://www.google.com/search?q=" + encodeURIComponent((car + " - " + text).trim());
    });
    label.classList.add("has-gs");
    input.insertAdjacentElement("afterend", a);
  });
})();
