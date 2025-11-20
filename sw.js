// sw.js

// Install event
self.addEventListener('install', event => {
  console.log('Service Worker installed');
  self.skipWaiting(); // activate immediately
});

// Activate event
self.addEventListener('activate', event => {
  console.log('Service Worker activated');
  // clients.claim() is optional if you want immediate control over pages
});

// Handle push events
self.addEventListener("push", function (event) {
  let data = {};
  if (event.data) {
    data = event.data.json();
  }

  const options = {
    body: data.body || "You have a new message",
    icon: "/static/images/icons/icon-192x192.png",
    badge: "/static/images/icons/icon-192x192.png",
    vibrate: data.vibration ? [200, 100, 200] : undefined,
    data: data.url || "/",
  };

  // iOS ignores sound, but Android may respect it if allowed
  if (data.sound) options.sound = `/static/sounds/${data.sound}.mp3`;

  event.waitUntil(
    self.registration.showNotification(data.title || "Notification", options)
  );
});

// Handle notification clicks
self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  event.waitUntil(
    clients.openWindow(event.notification.data)
  );
});
