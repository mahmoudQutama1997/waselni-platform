import L from './leaflet'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'

// Leaflet guesses its default icon path from CSS. Vite inlines those tiny PNGs
// as data URIs, so the guess produces `data:...marker-icon.png` and markers
// disappear in production builds. Point Leaflet at the bundled assets instead.
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
})

export type MapMarkerKind = 'store' | 'pickup' | 'dropoff' | 'customer' | 'captain' | 'delivery' | 'route'

export type MarkerVisual = {
  kind: MapMarkerKind
  /** Primary name shown next to the pin (store name, "delivery location", captain name). */
  label?: string | null
  /** Secondary line, e.g. order status or the address. */
  sublabel?: string | null
  /** Real GPS bearing in degrees; rotates the rider arrow. */
  heading?: number | null
  /** Position is older than the freshness threshold. */
  stale?: boolean
  /** Another element owns the focus (e.g. filtered-out order). */
  dimmed?: boolean
  /** Captain assigned to the order on screen. */
  assigned?: boolean
  /** Short badge such as an order count for a clustered group. */
  badge?: string | number | null
}

/** City landmark glyphs — one silhouette per location meaning, never a bare dot. */
const GLYPHS: Record<MapMarkerKind, string> = {
  store:
    '<path d="M4.2 10.4V19a1.6 1.6 0 0 0 1.6 1.6h12.4A1.6 1.6 0 0 0 19.8 19v-8.6" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><path d="M3.4 9.6 5 4.9A2 2 0 0 1 6.9 3.5h10.2a2 2 0 0 1 1.9 1.4l1.6 4.7a3 3 0 0 1-5.7 1.9 3 3 0 0 1-5.8 0 3 3 0 0 1-5.7-1.9Z" fill="currentColor"/><path d="M9.6 20.6v-4.4h4.8v4.4" fill="none" stroke="currentColor" stroke-width="1.7"/>',
  customer:
    '<path d="M12 3.2 3.8 10v10a1.2 1.2 0 0 0 1.2 1.2h4.3v-6.1h5.4v6.1H19a1.2 1.2 0 0 0 1.2-1.2V10Z" fill="currentColor"/><path d="M12 3.2 3.8 10h16.4Z" fill="currentColor" opacity=".55"/>',
  delivery:
    '<path d="M12 2.6a6.6 6.6 0 0 0-6.6 6.6c0 4.8 6.6 12.2 6.6 12.2s6.6-7.4 6.6-12.2A6.6 6.6 0 0 0 12 2.6Z" fill="currentColor"/><circle cx="12" cy="9.2" r="2.5" fill="#fff"/>',
  pickup:
    '<path d="M6.4 8.2h11.2l1 11.2a1.4 1.4 0 0 1-1.4 1.5H6.8a1.4 1.4 0 0 1-1.4-1.5Z" fill="currentColor"/><path d="M9 8.2V6.5a3 3 0 0 1 6 0v1.7" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
  dropoff:
    '<path d="M6 3.4v17.2" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/><path d="M6.2 4.2h11.4l-2.3 4.1 2.3 4.1H6.2Z" fill="currentColor"/>',
  captain:
    '<circle cx="5.6" cy="17.4" r="3.1" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="18.4" cy="17.4" r="3.1" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M5.6 17.4h5.1l3.2-5.6h3.1" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M8.6 8.4h3.4l1.4 3.4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M14.4 6.2h3.1l1.4 2.6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  route:
    '<path d="M6 19c0-5 12-5 12-12" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-dasharray="4 4"/>',
}

const escapeHtml = (value: unknown) =>
  String(value ?? '').replace(/[&<>"']/g, character => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' } as Record<string, string>
  )[character] ?? character)

/**
 * Build a Leaflet icon from semantic map data. Labels are rendered outside the
 * pin so a store keeps its name attached to its real coordinates, and the
 * captain pin carries a bearing arrow driven by real GPS movement.
 */
export function createMarkerIcon(visual: MarkerVisual): ReturnType<typeof L.divIcon> {
  const classes = [
    'wm',
    `wm-${visual.kind}`,
    visual.stale ? 'is-stale' : '',
    visual.dimmed ? 'is-dimmed' : '',
    visual.assigned ? 'is-assigned' : '',
    visual.label ? 'has-label' : '',
  ].filter(Boolean).join(' ')

  const bearing = Number(visual.heading)
  const arrow = visual.kind === 'captain' && Number.isFinite(bearing)
    ? `<span class="wm-bearing" style="transform:rotate(${Math.round(bearing)}deg)"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5 19 20l-7-4.2L5 20Z" fill="currentColor"/></svg></span>`
    : ''
  const badge = visual.badge != null && visual.badge !== ''
    ? `<span class="wm-badge">${escapeHtml(visual.badge)}</span>`
    : ''

  return L.divIcon({
    className: `waselni-marker waselni-marker-${visual.kind}`,
    html: `<div class="${classes}" data-kind="${visual.kind}">`
      + `<span class="wm-pin"><span class="wm-glyph"><svg viewBox="0 0 24 24" aria-hidden="true">${GLYPHS[visual.kind]}</svg></span>${badge}${arrow}</span>`
      + (visual.label
        ? `<span class="wm-label"><b>${escapeHtml(visual.label)}</b>${visual.sublabel ? `<small>${escapeHtml(visual.sublabel)}</small>` : ''}</span>`
        : '')
      + '</div>',
    // A zero-size icon keeps the element anchored exactly on the coordinate;
    // CSS positions the pin above it, so labels never shift the real point.
    iconSize: [0, 0],
    iconAnchor: [0, 0],
    popupAnchor: [0, -44],
  })
}

/** Backwards-compatible helper used by the location pickers. */
export function mapMarker(kind: MapMarkerKind, extra: Partial<MarkerVisual> = {}) {
  return createMarkerIcon({ kind, ...extra })
}
