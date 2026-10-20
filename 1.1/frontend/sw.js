const CACHE_NAME = 'dream-v1.1';
const ASSETS_TO_CACHE = [
  '/',
  '/index.html',
  '/css/style.css',
  '/js/app.js',
  '/manifest.webmanifest',
  '/icons/icon.svg'
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  if (e.request.url.includes('/api/')) {
    e.respondWith(fetch(e.request));
    return;
  }

  e.respondWith(
    fetch(e.request).catch(() => {
      return caches.match(e.request);
    })
  );
});
