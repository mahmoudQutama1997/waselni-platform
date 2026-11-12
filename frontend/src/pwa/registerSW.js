const UPDATE_EVENT = 'waselni:sw-update'

let registration = null
let reloadArmed = false

function notifyUpdate() {
  window.dispatchEvent(new CustomEvent(UPDATE_EVENT))
}

export function registerServiceWorker() {
  if (!('serviceWorker' in navigator) || !import.meta.env.PROD) return

  window.addEventListener('load', async () => {
    try {
      registration = await navigator.serviceWorker.register('/sw.js', { scope: '/' })

      if (registration.waiting) notifyUpdate()

      registration.addEventListener('updatefound', () => {
        const installing = registration.installing
        if (!installing) return
        installing.addEventListener('statechange', () => {
          if (installing.state === 'installed' && navigator.serviceWorker.controller) {
            notifyUpdate()
          }
        })
      })

      navigator.serviceWorker.addEventListener('controllerchange', () => {
        if (reloadArmed) window.location.reload()
      })

      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
          registration.update().catch(() => {})
        }
      })
    } catch (error) {
      console.warn('Waselni service worker registration failed', error)
    }
  })
}

export function applyServiceWorkerUpdate() {
  const waiting = registration && registration.waiting
  if (!waiting) return
  reloadArmed = true
  waiting.postMessage({ type: 'SKIP_WAITING' })
}

export function watchForServiceWorkerUpdate(handler) {
  window.addEventListener(UPDATE_EVENT, handler)
  return () => window.removeEventListener(UPDATE_EVENT, handler)
}
