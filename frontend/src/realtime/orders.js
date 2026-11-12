const TOKEN_KEY = 'waselni_access'
const SUBPROTOCOL_PREFIX = 'waselni.jwt.'
const MAX_RECONNECT_MS = 30000
const IDLE_CLOSE_MS = 5000

let socket = null
let reconnectTimer = null
let idleTimer = null
let attempts = 0
let listenersBound = false
const subscribers = new Set()

function accessToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

function socketUrl() {
  const apiBase = (import.meta.env.VITE_API_URL || '/api').trim()
  const apiOrigin = apiBase.startsWith('http') ? new URL(apiBase).origin : window.location.origin
  const url = new URL('/ws/orders/', apiOrigin)
  url.protocol = apiOrigin.startsWith('https:') ? 'wss:' : 'ws:'
  return url.toString()
}

function emit(name, detail) {
  window.dispatchEvent(new CustomEvent(name, { detail }))
}

function scheduleReconnect(closeCode) {
  if (!subscribers.size || !accessToken()) return
  const immediateAuthRetry = closeCode === 4401 || closeCode === 4403
  const delay = immediateAuthRetry
    ? Math.min(5000, 1500 * (attempts + 1))
    : Math.min(MAX_RECONNECT_MS, 1000 * 2 ** attempts) + Math.random() * 400
  attempts += 1
  window.clearTimeout(reconnectTimer)
  reconnectTimer = window.setTimeout(connect, delay)
}

function connect() {
  if (!subscribers.size) return
  const token = accessToken()
  if (!token) return
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return

  window.clearTimeout(reconnectTimer)
  const ws = new WebSocket(socketUrl(), [`${SUBPROTOCOL_PREFIX}${token}`, 'waselni.v1'])
  socket = ws

  ws.onopen = () => {
    attempts = 0
    emit('waselni:realtime', { connected: true })
  }

  ws.onmessage = (event) => {
    let message
    try {
      message = JSON.parse(event.data)
    } catch {
      return
    }
    if (!message || typeof message !== 'object') return
    subscribers.forEach((handler) => {
      try {
        handler(message)
      } catch (error) {
        console.warn('Waselni order subscriber failed', error)
      }
    })
    emit('waselni:order-event', message)
  }

  ws.onclose = (event) => {
    if (socket === ws) socket = null
    emit('waselni:realtime', { connected: false })
    scheduleReconnect(event.code)
  }

  ws.onerror = () => {
    ws.close()
  }
}

function bindGlobalEvents() {
  if (listenersBound) return
  listenersBound = true

  window.addEventListener('online', () => connect())
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') connect()
  })
  window.addEventListener('waselni:auth-cleared', () => {
    window.clearTimeout(reconnectTimer)
    window.clearTimeout(idleTimer)
    attempts = 0
    subscribers.clear()
    if (socket) {
      socket.onclose = null
      socket.close()
      socket = null
    }
    emit('waselni:realtime', { connected: false })
  })
}

/**
 * Subscribe to the single authenticated order-events socket.
 * Returns an unsubscribe function. The socket is shared by every screen.
 */
export function subscribeToOrders(handler) {
  bindGlobalEvents()
  subscribers.add(handler)
  window.clearTimeout(idleTimer)
  connect()

  return () => {
    subscribers.delete(handler)
    if (subscribers.size) return
    window.clearTimeout(idleTimer)
    idleTimer = window.setTimeout(() => {
      if (subscribers.size || !socket) return
      reconnectTimer && window.clearTimeout(reconnectTimer)
      socket.onclose = null
      socket.close()
      socket = null
      attempts = 0
      emit('waselni:realtime', { connected: false })
    }, IDLE_CLOSE_MS)
  }
}

export function isRealtimeConnected() {
  return Boolean(socket && socket.readyState === WebSocket.OPEN)
}
