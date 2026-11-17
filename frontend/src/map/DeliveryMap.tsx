import L from './leaflet'
import { useEffect, useRef, useState } from 'react'
import { createTileLayer } from './tiles'
import { createMarkerIcon, type MapMarkerKind } from './markers'
import {
  bearingBetween,
  fetchRoadRoute,
  formatDistance,
  formatDuration,
  haversineKm,
  isValidLatLng,
  straightRoute,
  type RoadRoute,
} from './routing'
import type { LegendEntry, MapLabels } from './labels'

export type MapPoint = {
  id: string
  kind: MapMarkerKind
  lat: number | string | null | undefined
  lng: number | string | null | undefined
  label?: string | null
  sublabel?: string | null
  /** Real bearing in degrees, when the caller already knows it. */
  heading?: number | null
  stale?: boolean
  dimmed?: boolean
  assigned?: boolean
  draggable?: boolean
  image?: string | null
  popup?: { title?: string | null; lines?: Array<string | null | undefined> }
  onClick?: () => void
}

export type RouteSpec = { from: [number, number]; to: [number, number]; key?: string } | null

type Props = {
  points: MapPoint[]
  route?: RouteSpec
  /** Cheap secondary lines (other active orders) drawn thin and dashed. */
  secondaryLines?: Array<[number, number][]>
  /** Changing this refits the viewport; changing GPS fixes must not. */
  fitKey?: string
  labels: MapLabels
  legend?: LegendEntry[]
  height?: number
  className?: string
  emptyText?: string
  errorText?: string
  loading?: boolean
  showMetrics?: boolean
  cluster?: boolean
  onPointMove?: (id: string, lat: number, lng: number) => void
  onPointClick?: (id: string) => void
}

const ROUTE_COLOR = '#7c3aed'
const ROUTE_STYLE = { color: ROUTE_COLOR, weight: 6, opacity: 0.92, lineCap: 'round' as const, lineJoin: 'round' as const }

// `leaflet` ships no type declarations in this project; these aliases keep the
// handles self-documenting without importing types that do not exist.
type LeafletMap = ReturnType<typeof L.map>
type LeafletMarker = ReturnType<typeof L.marker>
type LeafletLayerGroup = ReturnType<typeof L.layerGroup>

type DragRecord = { marker: LeafletMarker; lat: number; lng: number; heading: number | null }

const pointSignature = (point: MapPoint, showLabel: boolean, derivedHeading: number | null) => [
  point.kind,
  showLabel ? point.label || '' : '',
  point.sublabel || '',
  point.stale ? 1 : 0,
  point.dimmed ? 1 : 0,
  point.assigned ? 1 : 0,
  Math.round(point.heading ?? derivedHeading ?? -1),
].join('|')

const buildPopup = (point: MapPoint, labels: MapLabels): HTMLElement => {
  const root = document.createElement('div')
  root.className = 'wm-popup'

  const heading = document.createElement('b')
  heading.textContent = point.popup?.title || point.label || labels.order
  root.appendChild(heading)

  if (point.image) {
    const image = document.createElement('img')
    image.src = point.image
    image.alt = ''
    image.loading = 'lazy'
    image.className = 'wm-popup-image'
    image.addEventListener('error', () => image.remove())
    root.appendChild(image)
  }

  const lines = [point.sublabel, ...(point.popup?.lines || [])].filter(
    (line): line is string => typeof line === 'string' && line.trim().length > 0,
  )
  for (const line of lines) {
    const paragraph = document.createElement('p')
    paragraph.textContent = line
    root.appendChild(paragraph)
  }

  if (point.stale) {
    const stale = document.createElement('span')
    stale.className = 'wm-popup-stale'
    stale.textContent = labels.stale
    root.appendChild(stale)
  }
  return root
}

const buildClusterPopup = (points: MapPoint[], labels: MapLabels): HTMLElement => {
  const root = document.createElement('div')
  root.className = 'wm-popup'
  const heading = document.createElement('b')
  heading.textContent = `${points.length} ${labels.store}`
  root.appendChild(heading)
  for (const point of points) {
    const paragraph = document.createElement('p')
    paragraph.textContent = point.label || point.popup?.title || labels.store
    root.appendChild(paragraph)
  }
  return root
}

const arrowIcon = (degrees: number) => L.divIcon({
  className: 'wm-route-arrow',
  html: `<span style="transform:rotate(${Math.round(degrees)}deg)"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 19 20l-7-4.4L5 20Z" fill="currentColor"/></svg></span>`,
  iconSize: [0, 0],
  iconAnchor: [0, 0],
})

/**
 * One delivery map for every portal.
 *
 * The map, its tile layer, and each marker are created once and then mutated in
 * place: GPS updates move an existing marker, route redraws happen only when the
 * route key changes, and the viewport refits only when `fitKey` changes.
 */
export default function DeliveryMap({
  points,
  route = null,
  secondaryLines,
  fitKey,
  labels,
  legend,
  height = 320,
  className = '',
  emptyText,
  errorText,
  loading = false,
  showMetrics = true,
  cluster = false,
  onPointMove,
  onPointClick,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<LeafletMap | null>(null)
  const markerLayer = useRef<LeafletLayerGroup | null>(null)
  const routeLayer = useRef<LeafletLayerGroup | null>(null)
  const secondaryLayer = useRef<LeafletLayerGroup | null>(null)
  const secondaryKey = useRef('')
  const markers = useRef<Map<string, DragRecord>>(new Map())
  const lastCoords = useRef<Map<string, { lat: number; lng: number; heading: number | null }>>(new Map())
  const lastRouteKey = useRef('')
  const routeController = useRef<AbortController | null>(null)
  const lastFitKey = useRef('')
  const moveHandler = useRef(onPointMove)
  const clickHandler = useRef(onPointClick)
  const labelsRef = useRef(labels)
  moveHandler.current = onPointMove
  clickHandler.current = onPointClick
  labelsRef.current = labels

  const [zoom, setZoom] = useState(11)
  const [routeState, setRouteState] = useState<'idle' | 'loading' | 'road' | 'approx'>('idle')
  const [metrics, setMetrics] = useState<RoadRoute | null>(null)

  const validPoints = points.filter(point => isValidLatLng(point.lat, point.lng))
  const signature = validPoints.map(point => `${point.id}:${point.lat}:${point.lng}`).join('|')
    + `#${zoom}#${fitKey || ''}`

  // Create the map once. Cleanup removes it, its layers and its listeners.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = L.map(containerRef.current, { scrollWheelZoom: false, zoomControl: false, attributionControl: true })
    map.setView([31.95, 35.21], 11)
    createTileLayer({ maxZoom: 19 }).addTo(map)
    markerLayer.current = L.layerGroup().addTo(map)
    secondaryLayer.current = L.layerGroup().addTo(map)
    routeLayer.current = L.layerGroup().addTo(map)
    mapRef.current = map
    const syncZoom = () => {
      setZoom(map.getZoom())
      const container = map.getContainer()
      container.dataset.zoom = map.getZoom() < 12 ? 'far' : 'near'
    }
    map.on('zoomend', syncZoom)
    syncZoom()
    const resize = setTimeout(() => map.invalidateSize(), 160)
    return () => {
      clearTimeout(resize)
      map.off('zoomend', syncZoom)
      map.remove()
      mapRef.current = null
      markerLayer.current = null
      routeLayer.current = null
      secondaryLayer.current = null
      markers.current.clear()
      lastCoords.current.clear()
      lastRouteKey.current = ''
      routeController.current?.abort()
    }
  }, [])

  // Markers: diff by id, mutate existing ones, never rebuild the layer.
  useEffect(() => {
    const layer = markerLayer.current
    const map = mapRef.current
    if (!layer || !map) return

    const showLabels = zoom >= 12
    const clusterable = cluster && zoom < 12
    const seen = new Set<string>()

    // Group crowded non-captain markers into count badges while zoomed out.
    const groups = new Map<string, MapPoint[]>()
    if (clusterable) {
      for (const point of validPoints) {
        if (point.kind === 'captain' || point.draggable || point.assigned) continue
        const cell = `${Math.round(Number(point.lat) * 25)}:${Math.round(Number(point.lng) * 25)}`
        const bucket = groups.get(cell) || []
        bucket.push(point)
        groups.set(cell, bucket)
      }
    }

    for (const [cell, group] of groups) {
      if (group.length < 2) continue
      const id = `cluster:${cell}`
      seen.add(id)
      const lat = group.reduce((sum, point) => sum + Number(point.lat), 0) / group.length
      const lng = group.reduce((sum, point) => sum + Number(point.lng), 0) / group.length
      const existing = markers.current.get(id)
      const icon = createMarkerIcon({ kind: 'store', badge: group.length })
      if (!existing) {
        const marker = L.marker([lat, lng], { icon, keyboard: false, riseOnHover: true })
        marker.bindPopup(buildClusterPopup(group, labelsRef.current))
        marker.addTo(layer)
        markers.current.set(id, { marker, lat, lng, heading: null })
      } else {
        existing.marker.setLatLng([lat, lng])
        existing.marker.setIcon(icon)
      }
    }

    for (const point of validPoints) {
      if (clusterable && point.kind !== 'captain' && !point.draggable && !point.assigned) {
        const cell = `${Math.round(Number(point.lat) * 25)}:${Math.round(Number(point.lng) * 25)}`
        if ((groups.get(cell)?.length || 0) > 1) continue
      }
      const lat = Number(point.lat)
      const lng = Number(point.lng)
      seen.add(point.id)

      // Derive the rider arrow from real movement between two GPS fixes.
      const previous = lastCoords.current.get(point.id)
      let derivedHeading: number | null = null
      if (previous) {
        if (haversineKm(previous, { lat, lng }) > 0.008) {
          derivedHeading = bearingBetween(previous, { lat, lng })
          lastCoords.current.set(point.id, { lat, lng, heading: derivedHeading })
        }
      } else {
        lastCoords.current.set(point.id, { lat, lng, heading: point.heading ?? null })
      }
      const heading = point.heading ?? derivedHeading ?? lastCoords.current.get(point.id)?.heading ?? null
      const label = showLabels || point.kind === 'captain' ? point.label : null
      const record = markers.current.get(point.id)

      const nextSignature = pointSignature(point, Boolean(label), derivedHeading)

      if (!record) {
        const icon = createMarkerIcon({
          kind: point.kind,
          label,
          sublabel: point.kind === 'captain' ? (point.stale ? labelsRef.current.stale : point.sublabel) : point.sublabel,
          heading,
          stale: point.stale,
          dimmed: point.dimmed,
          assigned: point.assigned,
        })
        const marker = L.marker([lat, lng], {
          icon,
          draggable: Boolean(point.draggable),
          keyboard: false,
          riseOnHover: true,
          zIndexOffset: point.assigned ? 500 : point.kind === 'captain' ? 300 : 0,
        })
        marker.bindPopup(buildPopup(point, labelsRef.current))
        if (point.draggable) {
          const id = point.id
          marker.on('dragend', () => {
            const position = marker.getLatLng()
            moveHandler.current?.(id, position.lat, position.lng)
          })
        }
        ;(marker.options as { waselniSignature?: string }).waselniSignature = nextSignature
        if (clickHandler.current) {
          const id = point.id
          marker.on('click', () => clickHandler.current?.(id))
        }
        marker.addTo(layer)
        markers.current.set(point.id, { marker, lat, lng, heading })
        continue
      }

      const recordSignature = (record.marker.options as { waselniSignature?: string }).waselniSignature
      if (record.lat !== lat || record.lng !== lng) {
        record.marker.setLatLng([lat, lng])
        record.lat = lat
        record.lng = lng
      }
      if (recordSignature !== nextSignature) {
        record.marker.setIcon(createMarkerIcon({
          kind: point.kind,
          label,
          sublabel: point.kind === 'captain' ? (point.stale ? labelsRef.current.stale : point.sublabel) : point.sublabel,
          heading,
          stale: point.stale,
          dimmed: point.dimmed,
          assigned: point.assigned,
        }))
        ;(record.marker.options as { waselniSignature?: string }).waselniSignature = nextSignature
        record.marker.setPopupContent(buildPopup(point, labelsRef.current))
        record.heading = heading
      }
    }

    // Drop markers whose data left the view model (completed order, unassigned).
    for (const [id, record] of markers.current) {
      if (seen.has(id)) continue
      layer.removeLayer(record.marker)
      markers.current.delete(id)
      lastCoords.current.delete(id)
    }
  }, [signature, validPoints, zoom, cluster])

  // Secondary (other active orders) lines: thin, dashed, no ETA claimed.
  useEffect(() => {
    const layer = secondaryLayer.current
    if (!layer) return
    const key = JSON.stringify(secondaryLines || [])
    if (key === secondaryKey.current) return
    secondaryKey.current = key
    layer.clearLayers()
    for (const line of secondaryLines || []) {
      if (line.length < 2) continue
      L.polyline(line, { color: '#a78bfa', weight: 2.5, opacity: 0.55, dashArray: '5 8' }).addTo(layer)
    }
  }, [secondaryLines])

  // Route: redraw only when its endpoints actually change.
  const routeKey = route ? `${route.from[0].toFixed(5)},${route.from[1].toFixed(5)}>${route.to[0].toFixed(5)},${route.to[1].toFixed(5)}` : ''

  useEffect(() => {
    const layer = routeLayer.current
    if (!layer) return
    if (!route) {
      layer.clearLayers()
      lastRouteKey.current = ''
      setRouteState('idle')
      setMetrics(null)
      return
    }
    if (routeKey === lastRouteKey.current) return
    lastRouteKey.current = routeKey
    layer.clearLayers()
    routeController.current?.abort()
    const controller = new AbortController()
    routeController.current = controller
    setRouteState('loading')

    const from = { lat: route.from[0], lng: route.from[1] }
    const to = { lat: route.to[0], lng: route.to[1] }
    fetchRoadRoute(from, to, { signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return
      const drawn = result ?? straightRoute(from, to)
      const line = L.polyline(drawn.coords, result ? ROUTE_STYLE : { ...ROUTE_STYLE, dashArray: '9 9', weight: 5, opacity: 0.8 })
      line.addTo(layer)
      if (result && drawn.coords.length > 8) {
        const step = Math.max(1, Math.floor(drawn.coords.length / 10))
        for (let index = step; index < drawn.coords.length - 1; index += step) {
          const previous = drawn.coords[index - 1]
          const next = drawn.coords[index + 1]
          const degrees = bearingBetween(
            { lat: previous[0], lng: previous[1] },
            { lat: next[0], lng: next[1] },
          )
          if (degrees == null) continue
          L.marker(drawn.coords[index], { icon: arrowIcon(degrees), interactive: false, keyboard: false }).addTo(layer)
        }
      }
      setMetrics(drawn)
      setRouteState(result ? 'road' : 'approx')
    })
  }, [routeKey, route])

  // Refit only on a real data change, not on every GPS tick.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    // Refit on a new data set or explicit request — never on a GPS tick.
    const key = `${fitKey || ''}#${validPoints.map(point => point.id).join('|')}`
    if (!validPoints.length) {
      lastFitKey.current = key
      return
    }
    if (key === lastFitKey.current) return
    lastFitKey.current = key
    const bounds = L.latLngBounds(validPoints.map(point => [Number(point.lat), Number(point.lng)] as [number, number]))
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [42, 42], maxZoom: 15 })
  }, [fitKey, signature, validPoints])

  const recenter = () => {
    const map = mapRef.current
    if (!map || !validPoints.length) return
    const bounds = L.latLngBounds(validPoints.map(point => [Number(point.lat), Number(point.lng)] as [number, number]))
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [42, 42], maxZoom: 15 })
  }

  const hasRoute = Boolean(route)
  const stateLabel = routeState === 'road' ? labels.routeRoad : routeState === 'approx' ? labels.routeApprox : ''

  return (
    <div className={`wm-shell ${className}`.trim()} style={{ height }}>
      <div ref={containerRef} className="wm-canvas" role="application" aria-label={labels.map} />
      <div className="wm-controls">
        <button type="button" onClick={() => mapRef.current?.zoomIn()} aria-label={labels.zoomIn} title={labels.zoomIn}>+</button>
        <button type="button" onClick={() => mapRef.current?.zoomOut()} aria-label={labels.zoomOut} title={labels.zoomOut}>−</button>
        <button type="button" onClick={recenter} aria-label={labels.recenter} title={labels.recenter} disabled={!validPoints.length}>◎</button>
      </div>
      {legend && legend.length > 0 && validPoints.length > 0 && (
        <ul className="wm-legend">
          {legend.map(entry => (
            <li key={`${entry.kind}-${entry.label}`}>
              <i className={`wm-swatch wm-swatch-${entry.kind}`} aria-hidden="true" />
              {entry.label}
            </li>
          ))}
        </ul>
      )}
      {loading && <div className="wm-overlay"><span className="wm-spinner" aria-hidden="true" />{labels.loading}</div>}
      {!loading && !validPoints.length && <div className="wm-overlay wm-overlay-empty">{emptyText || labels.noPoints}</div>}
      {errorText && <div className="wm-overlay wm-overlay-error">{errorText}</div>}
      {showMetrics && hasRoute && (
        <div className={`wm-metrics ${routeState === 'approx' ? 'is-approx' : ''}`}>
          {metrics && routeState !== 'loading' ? (
            <>
              <span>{labels.distance}: <b>{formatDistance(metrics.distanceKm, labels)}</b></span>
              <span>{labels.duration}: <b>{formatDuration(metrics.durationMinutes, labels)}</b></span>
            </>
          ) : (
            <span>{labels.route}</span>
          )}
          {stateLabel && <small className={routeState === 'approx' ? 'wm-chip-approx' : 'wm-chip-road'}>{stateLabel}</small>}
          {!routeState || routeState === 'loading' ? (
            routeState === 'loading' ? <small className="wm-chip-muted">{labels.loading}</small> : null
          ) : null}
        </div>
      )}
    </div>
  )
}
