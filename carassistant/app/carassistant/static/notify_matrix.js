// Settings > User > Notifications: choose a car, then switch its messages on or off (yes / no); the form saves by itself (data-live).
(function () {
  var form = document.getElementById("nm-form"), pick = document.getElementById("nm-select");
  if (!form || !pick) { return; }
  function show() {
    Array.prototype.forEach.call(form.querySelectorAll(".nm-panel"), function (p) { p.hidden = p.getAttribute("data-panel") !== pick.value; });
    try { sessionStorage.setItem("nm-car", pick.value); } catch (e) {}
  }
  try { var was = sessionStorage.getItem("nm-car"); if (was && pick.querySelector('option[value="' + was + '"]')) { pick.value = was; } } catch (e) {}
  pick.addEventListener("change", show);
  show();
})();
