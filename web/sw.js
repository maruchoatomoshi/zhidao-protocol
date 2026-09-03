const CACHE_PREFIX = 'zhidao-';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key.startsWith(CACHE_PREFIX)).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

// Network-only for the pilot. This deliberately replaces the aggressive
// Travel Season cache so lessons and teacher feedback cannot become stale.
self.addEventListener('fetch', () => {});
