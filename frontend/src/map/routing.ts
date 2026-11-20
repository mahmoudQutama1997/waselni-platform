/**
 * Road routing through the project's configured OSRM service.
 *
 * Every helper here treats routing as an optional dependency: when OSRM is
 * unreachable the caller draws an explicitly approximate straight line and says
 * so, instead of inventing a distance or an ETA.
 */

const configured = ((import.meta.env.VITE_OSRM_URL as string | undefined) || '').trim()
export const OSRM_BASE = (configured || 'https://router.project-osrm.org').replace(/\/+$/, '')

export type LatLng = { lat: number; lng: number }
export type RoadRoute = {
  coords: [number, number][]
  distanceKm: number
  durationMinutes: number
}

const cache = new Map<string, RoadRoute>()
const CACHE_LIMIT = 80
const ROAD_METERS_PER_DEGREE = 111_320

export function isValidLatLng(lat: unknown, lng: unknown): boolean {
  if (lat === null || lat === undefined || lat === '' || lng === null || lng === undefined || lng === '') return false
  const latNumber = Number(lat)
  const lngNumber = Number(lng)
  return Number.isFinite(latNumber) && Number.isFinite(lngNumber)
    && latNumber >= -90 && latNumber <= 90 && lngNumber >= -180 && lngNumber <= 180
}

/** Great-circle distance in kilometres. Used for fallbacks and movement checks. */
export function haversineKm(a: LatLng, b: LatLng): number {
  const toRad = (value: number) => (value * Math.PI) / 180
  const dLat = toRad(b.lat - a.lat)
  const dLng = toRad(b.lng - a.lng)
  const lat1 = toRad(a.lat)
  const lat2 = toRad(b.lat)
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2
  return 2 * 6371 * Math.asin(Math.min(1, Math.sqrt(h)))
}

/**
 * Cardinal bearing (0 = north, clockwise) between two GPS fixes. Real OSRM
 * routes do not carry a rider heading, so the captain arrow is derived from his
 * own consecutive positions; null means "not enough movement to know".
 */
export function bearingBetween(from: LatLng, to: LatLng): number | null {
  if (haversineKm(from, to) < 0.008) return null
  const toRad = (value: number) => (value * Math.PI) / 180
  const dLng = toRad(to.lng - from.lng)
  const y = Math.sin(dLng) * Math.cos(toRad(to.lat))
  const x = Math.cos(toRad(from.lat)) * Math.sin(toRad(to.lat))
    - Math.sin(toRad(from.lat)) * Math.cos(toRad(to.lat)) * Math.cos(dLng)
  const degrees = (Math.atan2(y, x) * 180) / Math.PI
  return (degrees + 360) % 360
}

export function formatDistance(km: number, labels: { kilometers: string; meters: string }): string {
  if (!Number.isFinite(km)) return '—'
  if (km < 1) return `${Math.round(km * 1000)} ${labels.meters}`
  return `${km < 10 ? km.toFixed(1) : Math.round(km)} ${labels.kilometers}`
}

export function formatDuration(minutes: number, labels: { minutes: string }): string {
  if (!Number.isFinite(minutes)) return '—'
  if (minutes < 60) return `${Math.max(1, Math.round(minutes))} ${labels.minutes}`
  const hours = Math.floor(minutes / 60)
  const rest = Math.round(minutes % 60)
  return `${hours}:${String(rest).padStart(2, '0')}`
}

const cacheKey = (from: LatLng, to: LatLng) =>
  `${from.lat.toFixed(5)},${from.lng.toFixed(5)};${to.lat.toFixed(5)},${to.lng.toFixed(5)}`

function remember(key: string, route: RoadRoute) {
  if (cache.size >= CACHE_LIMIT) {
    const oldest = cache.keys().next().value
    if (oldest) cache.delete(oldest)
  }
  cache.set(key, route)
}

/**
 * Fetch a road-following route. Returns null when routing is unavailable, so
 * the map can degrade honestly instead of throwing.
 */
export async function fetchRoadRoute(
  from: LatLng,
  to: LatLng,
  options: { signal?: AbortSignal; timeoutMs?: number } = {},
): Promise<RoadRoute | null> {
  if (!isValidLatLng(from.lat, from.lng) || !isValidLatLng(to.lat, to.lng)) return null
  const key = cacheKey(from, to)
  const hit = cache.get(key)
  if (hit) return hit

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), options.timeoutMs ?? 9000)
  const relayAbort = () => controller.abort()
  options.signal?.addEventListener('abort', relayAbort)
  if (options.signal?.aborted) controller.abort()

  try {
    const url = `${OSRM_BASE}/route/v1/driving/${from.lng},${from.lat};${to.lng},${to.lat}`
      + '?overview=full&geometries=geojson&steps=false'
    const response = await fetch(url, { signal: controller.signal, headers: { Accept: 'application/json' } })
    if (!response.ok) return null
    const data = await response.json()
    const best = data?.routes?.[0]
    const coordinates: [number, number][] | undefined = best?.geometry?.coordinates
    if (!best || !Array.isArray(coordinates) || coordinates.length < 2) return null
    const route: RoadRoute = {
      coords: coordinates.map(([lng, lat]) => [lat, lng] as [number, number]),
      distanceKm: Number(best.distance) / 1000,
      durationMinutes: Number(best.duration) / 60,
    }
    if (!Number.isFinite(route.distanceKm) || !Number.isFinite(route.durationMinutes)) return null
    remember(key, route)
    return route
  } catch {
    return null
  } finally {
    clearTimeout(timeout)
    options.signal?.removeEventListener('abort', relayAbort)
  }
}

/** Straight-line fallback, clearly marked as approximate by the map. */
export function straightRoute(from: LatLng, to: LatLng): RoadRoute {
  return {
    coords: [[from.lat, from.lng], [to.lat, to.lng]],
    distanceKm: haversineKm(from, to),
    durationMinutes: (haversineKm(from, to) / 25) * 60,
  }
}

/** Age of a GPS fix in milliseconds, or null when it has no timestamp. */
export function locationAgeMs(iso: string | null | undefined, now = Date.now()): number | null {
  if (!iso) return null
  const timestamp = new Date(iso).getTime()
  if (!Number.isFinite(timestamp)) return null
  return Math.max(0, now - timestamp)
}

/** A captain fix older than this is shown as "last known", never as live. */
export const STALE_AFTER_MS = 45_000

export function isLocationStale(iso: string | null | undefined, thresholdMs = STALE_AFTER_MS): boolean {
  const age = locationAgeMs(iso)
  return age === null ? false : age > thresholdMs
}

/** Approximate metres per degree of longitude at a latitude, for clustering. */
export const metresPerDegree = (latitude: number) => ({
  lat: ROAD_METERS_PER_DEGREE,
  lng: ROAD_METERS_PER_DEGREE * Math.max(0.2, Math.cos((latitude * Math.PI) / 180)),
})
