/* Offline shell only: no orders, admin pages, personal data or dynamic HTML are cached. */
const CACHE_NAME = "saber-actros-pwa-shell-v1";
const STATIC_ASSETS = [
  "/static/offline.html",
  "/static/hero.webp",
  "/static/flag-dz.svg",
  "/static/install.js",
  "/static/icons/icon-180.png",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});
self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(key => key.startsWith("saber-actros-pwa-shell-") && key !== CACHE_NAME)
        .map(key => caches.delete(key)))
    ).then(() => self.clients.claim())
  );
});
self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(async () =>
        await caches.match("/static/offline.html") || Response.error()
      )
    );
    return;
  }
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;
        return fetch(request).then(response => {
          if (response.ok) {
            event.waitUntil(caches.open(CACHE_NAME)
              .then(cache => cache.put(request, response.clone())));
          }
          return response;
        });
      })
    );
  }
});
