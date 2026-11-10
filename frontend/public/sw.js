
const CACHE = 'waselni-shell-v3';
const SHELL = ['/', '/manifest.webmanifest'];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE)
      .then(cache => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys =>
        Promise.all(
          keys
            .filter(key => key.startsWith('waselni-shell-') && key !== CACHE)
            .map(key => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;

  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  if (
    url.origin !== self.location.origin ||
    url.pathname.startsWith('/api/') ||
    url.pathname.startsWith('/ws/') ||
    url.pathname.startsWith('/media/')
  ) {
    return;
  }

  // Network-first for page navigation.
  if (request.mode === 'navigate') {
    event.respondWith(
      (async () => {
        try {
          const response = await fetch(request);

          if (response.ok) {
            // Clone immediately, before any asynchronous cache operation.
            const responseCopy = response.clone();

            try {
              const cache = await caches.open(CACHE);
              await cache.put('/', responseCopy);
            } catch (error) {
              console.warn('Service Worker cache update failed:', error);
            }
          }

          return response;
        } catch (error) {
          const cached = await caches.match('/');
          if (cached) return cached;

          return new Response('Offline - page unavailable', {
            status: 503,
            headers: { 'Content-Type': 'text/plain; charset=utf-8' }
          });
        }
      })()
    );

    return;
  }

  // Cache-first for other same-origin GET requests.
  event.respondWith(
    caches.match(request)
      .then(cached => cached || fetch(request))
  );
});
