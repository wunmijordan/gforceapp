const STATIC_CACHE = "static-cache-v1";

// Install
self.addEventListener("install", (event) => {
  console.log("Service Worker installed");
  self.skipWaiting();
});

// Activate
self.addEventListener("activate", (event) => {
  console.log("Service Worker activated");

  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((key) => key !== STATIC_CACHE && caches.delete(key)))
    )
  );

  self.clients.claim();
});

// Fetch
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Prevent SW from touching WebSocket upgrade requests
  if (event.request.headers.get("upgrade") === "websocket") return;

  // ❌ Prevent caching Chrome extensions
  if (url.protocol.includes("chrome-extension")) {
    return;
  }

  // ❌ Prevent caching external CDN requests (Fixes your warnings)
  if (url.origin !== self.location.origin) {
    return event.respondWith(fetch(event.request));
  }

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
            // Only cache 200 OK responses
            if (response.status === 200) {
              cache.put(event.request, response.clone());
            }
            return response;
          })
          .catch(() => cached);

        return cached || fetchPromise;
      })
    );
  }
});

// Push notifications
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

  if (data.sound) {
    options.sound = `/static/sounds/${data.sound}.mp3`;
  }

  event.waitUntil(
    self.registration.showNotification(data.title || "Notification", options)
  );
});

// Notification click
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
