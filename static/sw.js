/* SonicWave service worker — makes the site installable as an app.
   Strategy: network-first with cache fallback for the app shell & icons,
   never caches API or audio (always live). */
const CACHE = "sonicwave-v1";
const SHELL = ["/", "/manifest.json", "/icon-192.png", "/icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;              // never touch CDNs/audio
  if (url.pathname.startsWith("/api/")) return;                 // API is always live
  e.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok && (url.pathname === "/" || /\.(png|json|ico)$/.test(url.pathname))) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(req).then((m) => m || caches.match("/")))
  );
});
