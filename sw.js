// Cache-first service worker for media assets (images/video/audio) so they
// load over the network once and then come straight from disk cache on every
// later open — important on throttled/VPN connections.
//
// Media files keep stable filenames across content updates (e.g. swapping
// architect_phase1.png art under the same name), so a cache-first strategy
// can serve stale content forever. If you replace a media file's *content*
// while keeping its filename, bump CACHE_VERSION below to invalidate the
// old cache.
const CACHE_VERSION = 'v2';
const CACHE_NAME = `zhidao-media-${CACHE_VERSION}`;
const MEDIA_RE = /\.(png|jpe?g|gif|webp|svg|mp4|mp3|ogg|wav)(\?.*)?$/i;

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET' || !MEDIA_RE.test(req.url)) return;

  event.respondWith(
    caches.open(CACHE_NAME).then(async (cache) => {
      const cached = await cache.match(req);
      if (cached) return cached;
      try {
        const resp = await fetch(req);
        if (resp && (resp.ok || resp.type === 'opaque')) cache.put(req, resp.clone());
        return resp;
      } catch (err) {
        return cached || Response.error();
      }
    })
  );
});
