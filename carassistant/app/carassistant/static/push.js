// Web push on the notification card of the signed-in person (Settings > User): turn notifications on or off for THIS device (browser or home-screen app).
// What is sent is chosen in the matrix below it. Failures never break the page.
(function () {
  var box = document.getElementById("push-box");
  if (!box || !window.fetch) { return; }
  var btn = document.getElementById("push-on"), msg = document.getElementById("push-msg"), base = box.getAttribute("data-base") || "";
  var labels = { on: box.getAttribute("data-label-on"), off: box.getAttribute("data-label-off") };
  function say(t) { msg.textContent = t; msg.hidden = !t; }
  function toBuf(s) { s = s.replace(/-/g, "+").replace(/_/g, "/"); while (s.length % 4) { s += "="; } var b = atob(s), a = new Uint8Array(b.length); for (var i = 0; i < b.length; i++) { a[i] = b.charCodeAt(i); } return a; }
  function label() { var u = navigator.userAgent; return /iPhone/.test(u) ? "iPhone" : /iPad/.test(u) ? "iPad" : /Macintosh/.test(u) ? "Mac" : /Android/.test(u) ? "Android" : /Windows/.test(u) ? "Windows" : "Device"; }
  function post(url, body) { return fetch(url, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }).then(function (r) { return r.json(); }); }
  var testForm = document.getElementById("push-test");
  function off() { btn.hidden = true; if (testForm) { testForm.hidden = true; } }
  if (location.protocol !== "https:" || !window.isSecureContext) { off(); return; }  // notifications only work on an https page: nothing is offered anywhere else (the explanation at the top of the card says so)
  var ios = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  var installed = window.navigator.standalone === true || (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches);
  if (ios && !installed) { off(); say(box.getAttribute("data-ios")); return; }  // iOS only delivers web push to an app added to the home screen
  var supported = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window && window.isSecureContext;
  if (!supported) { off(); say(box.getAttribute("data-unsupported")); return; }
  function paint(on) { btn.setAttribute("data-on", on ? "1" : "0"); btn.querySelector("span").textContent = on ? labels.off : labels.on; btn.classList.toggle("primary", !on); }
  navigator.serviceWorker.getRegistration(base + "/").then(function (reg) { return reg ? reg.pushManager.getSubscription() : null; })
    .then(function (sub) { return sub ? post(base + "/push/status", { endpoint: sub.endpoint }).then(function (r) { return !!r.on; }) : false; })
    .then(paint).catch(function () { paint(false); });
  btn.addEventListener("click", async function () {
    btn.disabled = true; say("");
    var step = "";
    try {
      var turningOff = btn.getAttribute("data-on") === "1";
      if (!turningOff) {  // the permission is asked first, straight from the tap: iOS refuses it after other waiting
        step = "permission";
        if ((await Notification.requestPermission()) !== "granted") { say(box.getAttribute("data-denied")); btn.disabled = false; return; }
      }
      step = "service worker";
      var reg = await navigator.serviceWorker.register(base + "/sw.js", { scope: base + "/" });
      await navigator.serviceWorker.ready;
      var existing = await reg.pushManager.getSubscription();
      if (existing && turningOff) {  // switch off on this device
        step = "switch off";
        await post(base + "/push/unsubscribe", { endpoint: existing.endpoint });
        await existing.unsubscribe();
        location.reload();
        return;
      }
      step = "server key";
      var k = await (await fetch(base + "/push/key", { credentials: "same-origin" })).json();
      if (!k.ok) { say(k.error); btn.disabled = false; return; }
      step = "subscribe";
      var sub = existing || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: toBuf(k.key) });
      step = "register device";
      var r = await post(base + "/push/subscribe", { sub: sub.toJSON(), label: label() });
      if (!r.ok) { say(r.error); btn.disabled = false; return; }
      location.reload();
    } catch (e) { say(box.getAttribute("data-failed") + " (" + step + ": " + ((e && (e.name || e.message)) || "error") + (e && e.message && e.name ? " - " + e.message : "") + ")"); btn.disabled = false; }
  });
})();
