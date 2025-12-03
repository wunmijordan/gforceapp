const STATIC_CACHE = "static-cache-v1";

self.addEventListener("install", (event) => {
  console.log("Service Worker installed");
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  console.log("Service Worker activated");

  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((key) => key !== STATIC_CACHE && caches.delete(key)))
    )
  );

  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  // Prevent SW from touching WebSocket upgrade requests
  if (event.request.headers.get("upgrade") === "websocket") return;

  // Cache CSS, JS, images, fonts
  if (
    event.request.method === "GET" &&
    ["style", "script", "font", "image"].includes(event.request.destination)
  ) {
    event.respondWith(
      caches.open(STATIC_CACHE).then(async (cache) => {
        const cached = await cache.match(event.request);
        const fetchPromise = fetch(event.request)
          .then((response) => {
            cache.put(event.request, response.clone());
            return response;
          })
          .catch(() => cached);

        return cached || fetchPromise;
      })
    );
  }
});

self.addEventListener("push", (event) => {
  let data = {};
  if (event.data) data = event.data.json();

  const options = {
    body: data.body || "You have a new message",
    icon: "/static/images/icons/icon-192x192.png",
    badge: "/static/images/icons/icon-192x192.png",
    vibrate: data.vibration ? [200, 100, 200] : undefined,
    data: data.url || "/",
  };

  if (data.sound) options.sound = `/static/sounds/${data.sound}.mp3`;

  event.waitUntil(
    self.registration.showNotification(data.title || "Notification", options)
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  event.waitUntil(
    clients.matchAll({ type: "window" }).then((windowClients) => {
      for (const client of windowClients) {
        if (client.url === event.notification.data && "focus" in client) {
          return client.focus();
        }
      }
      return clients.openWindow(event.notification.data);
    })
  );
});
