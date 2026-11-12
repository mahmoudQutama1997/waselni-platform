const tileUrl = (import.meta.env.VITE_MAP_TILE_URL || '').trim()
const attribution = (import.meta.env.VITE_MAP_ATTRIBUTION || '').trim()

export const MAP_TILE_URL =
  tileUrl || 'https://tiles.stadiamaps.com/tiles/alidade_bright/{z}/{x}/{y}{r}.png'
export const MAP_ATTRIBUTION =
  attribution || '&copy; Stadia Maps &copy; OpenStreetMap contributors'

export const GEOCODING_REVERSE_URL = (
  import.meta.env.VITE_GEOCODING_URL || 'https://nominatim.openstreetmap.org/reverse'
)
  .trim()
  .replace(/\/+$/, '')
export const GEOCODING_SEARCH_URL = (
  import.meta.env.VITE_GEOCODING_SEARCH_URL || 'https://nominatim.openstreetmap.org/search'
)
  .trim()
  .replace(/\/+$/, '')

/** Append query params to a provider URL that may already contain a query string. */
export function geocodeUrl(base, params) {
  const query = new URLSearchParams(params).toString()
  return `${base}${base.includes('?') ? '&' : '?'}${query}`
}

export function hasConfiguredMaps() {
  return Boolean(tileUrl)
}
