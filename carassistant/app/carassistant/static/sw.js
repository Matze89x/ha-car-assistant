// Service worker of Car Assistant: shows a notification when the server sends a web push and opens the app when it is tapped.
self.addEventListener("install", function () { self.skipWaiting(); });
self.addEventListener("activate", function (event) { event.waitUntil(self.clients.claim()); });
self.addEventListener("push", function (event) {
  var data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = { body: event.data ? event.data.text() : "" }; }
  var base = self.registration.scope;
  event.waitUntil(self.registration.showNotification(data.title || "Car Assistant", {
    body: data.body || "",
    icon: new URL("icon/192.png", base).href,
    badge: new URL("icon/96.png", base).href,
    tag: data.tag || undefined,
    data: { url: data.url || base },
  }));
});
self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  // the address of the page (a path of this app is resolved against the app's own address, so it is always on the same origin)
  var target = new URL((event.notification.data && event.notification.data.url) || "/", self.registration.scope).href;
  event.waitUntil((async function () {
    var list = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    var open = list.find(function (w) { return "focus" in w; });
    if (open) {
      try {  // the window that is open goes to the page ...
        if ("navigate" in open) { var moved = await open.navigate(target); await (moved || open).focus(); return; }
      } catch (e) { /* a window this worker does not control, or a system that refuses: the address is opened the standard way below */ }
      try { await open.focus(); } catch (e) { /* ... and a window that cannot be focused is not the end of it */ }
    }
    return self.clients.openWindow(target);  // no window yet (or none could be taken there): open the page
  })());
});
