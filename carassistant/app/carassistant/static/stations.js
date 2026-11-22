// Stations: "around me" asks the browser for the phone's position (only when the button is pressed) and searches there.
(function () {
  var form = document.getElementById("stform"), me = document.getElementById("st-me");
  if (!form || !me) { return; }
  var msg = document.getElementById("st-msg");
  function say(text) { if (msg) { msg.textContent = text; msg.hidden = !text; } }
  me.addEventListener("click", function (e) {
    e.preventDefault();
    say("");
    if (!navigator.geolocation) { say(form.getAttribute("data-denied")); return; }
    me.classList.add("off");
    navigator.geolocation.getCurrentPosition(function (p) {
      document.getElementById("st-lat").value = p.coords.latitude.toFixed(5);
      document.getElementById("st-lon").value = p.coords.longitude.toFixed(5);
      form.submit();
    }, function () { me.classList.remove("off"); say(form.getAttribute("data-denied")); }, { enableHighAccuracy: false, timeout: 12000, maximumAge: 60000 });
  });
  // the car button must search around the car: forget a position that came from the phone
  var car = document.getElementById("st-car");
  if (car) { car.addEventListener("click", function () { document.getElementById("st-lat").value = ""; document.getElementById("st-lon").value = ""; }); }
})();
