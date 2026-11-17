// Custom SVG map markers shared by every Leaflet map in the platform.
// Using divIcon keeps the markers stylable and avoids emoji glyphs.

const SVG_NS = 'http://www.w3.org/2000/svg'

function svg(paths, viewBox = '0 0 24 24') {
  const element = document.createElementNS(SVG_NS, 'svg')
  element.setAttribute('viewBox', viewBox)
  element.setAttribute('fill', 'none')
  element.setAttribute('stroke', 'currentColor')
  element.setAttribute('stroke-width', '2')
  element.setAttribute('stroke-linecap', 'round')
  element.setAttribute('stroke-linejoin', 'round')
  for (const [tag, attrs] of paths) {
    const node = document.createElementNS(SVG_NS, tag)
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value)
    element.appendChild(node)
  }
  return element
}

const GLYPHS = {
  store: [['path', { d: 'M3.5 10h17l-1.8-6H5.3zM5 10v10h14V10M9.5 20v-6h5v6' }]],
  customer: [['circle', { cx: '12', cy: '8', r: '3.8' }], ['path', { d: 'M4.5 21a7.5 7.5 0 0 1 15 0' }]],
  captain: [['circle', { cx: '6', cy: '17', r: '3.2' }], ['circle', { cx: '18', cy: '17', r: '3.2' }], ['path', { d: 'm6 17 4-8h4l4 8M10 9H7M14 9l2-3' }]],
  pickup: [['path', { d: 'M12 3 4.5 6v6c0 4.5 3.2 7.5 7.5 9 4.3-1.5 7.5-4.5 7.5-9V6L12 3Z' }], ['path', { d: 'm9 12 2 2 4-4' }]],
  destination: [['path', { d: 'M3.5 12.5V4h8.5l8.5 8.5-8.5 8.5z' }], ['circle', { cx: '7.5', cy: '8', r: '1.4' }]],
}

/** Build a Leaflet divIcon marker for a role. Returns null when Leaflet is absent. */
export function markerIcon(L, kind = 'store', { label = '' } = {}) {
  if (!L?.divIcon) return null
  const wrapper = document.createElement('div')
  wrapper.className = `w-marker-pin w-marker-pin--${kind}`
  wrapper.appendChild(svg(GLYPHS[kind] || GLYPHS.store))
  if (label) wrapper.title = label
  return L.divIcon({
    html: wrapper.outerHTML,
    className: 'w-marker',
    iconSize: kind === 'captain' || kind === 'destination' ? [38, 38] : [34, 34],
    iconAnchor: kind === 'captain' || kind === 'destination' ? [19, 19] : [17, 32],
    popupAnchor: [0, -30],
  })
}

/** Safely add/update a marker on a layer group. */
export function placeMarker(L, layer, store, kind, point, popup) {
  if (!L || !layer || !point || !point.every(Number.isFinite)) return null
  const marker = L.marker(point, { icon: markerIcon(L, kind) })
  if (popup) marker.bindPopup(popup)
  marker.addTo(layer)
  store.push(marker)
  return marker
}
