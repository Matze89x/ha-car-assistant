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
  var url = (event.notification.data && event.notification.data.url) || self.registration.scope;
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (list) {
    for (var i = 0; i < list.length; i++) { if ("focus" in list[i]) { if ("navigate" in list[i]) { list[i].navigate(url); } return list[i].focus(); } }
    return self.clients.openWindow(url);
  }));
});
