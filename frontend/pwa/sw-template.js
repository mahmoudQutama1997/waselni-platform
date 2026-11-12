/* Generated at build time for one Waselni app. Do not edit dist/sw.js by hand. */
const CACHE_PREFIX = 'waselni-__ROLE__-'
const CACHE_NAME = CACHE_PREFIX + '__VERSION__'
const PRECACHE_URLS = __PRECACHE__
const OFFLINE_URL = '/offline.html'
const NETWORK_ONLY_PREFIXES = ['/api/', '/ws/', '/media/']

function isNetworkOnly(url) {
  return NETWORK_ONLY_PREFIXES.some((prefix) => url.pathname.startsWith(prefix))
}

function isStaticAsset(request, url) {
  if (url.origin !== self.location.origin) return false
  if (isNetworkOnly(url)) return false
  return ['script', 'style', 'font', 'image', 'manifest'].includes(request.destination)
}

async function updateShellCache(request, response) {
  if (!response || !response.ok) return
  const copy = response.clone()
  const cache = await caches.open(CACHE_NAME)
  await cache.put('/index.html', copy)
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .catch(() => undefined)
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME)
            .map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  )
})

self.addEventListener('message', (event) => {
  const data = event.data || {}
  if (data.type === 'SKIP_WAITING') {
    self.skipWaiting()
  }
  if (data.type === 'GET_VERSION' && event.source) {
    event.source.postMessage({ type: 'SW_VERSION', version: '__VERSION__' })
  }
})

self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return
  if (isNetworkOnly(url)) return

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          updateShellCache(request, response)
          return response
        })
        .catch(async () => {
          const cache = await caches.open(CACHE_NAME)
          return (
            (await cache.match('/index.html')) ||
            (await cache.match(OFFLINE_URL)) ||
            new Response('Offline', { status: 503, headers: { 'Content-Type': 'text/plain' } })
          )
        })
    )
    return
  }

  if (isStaticAsset(request, url)) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached
        return fetch(request).then((response) => {
          if (response && response.ok) {
            const copy = response.clone()
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy))
          }
          return response
        })
      })
    )
  }
})
