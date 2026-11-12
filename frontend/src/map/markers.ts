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

export type MapMarkerKind = 'store' | 'pickup' | 'dropoff' | 'customer' | 'captain' | 'delivery'

export function mapMarker(kind: MapMarkerKind) {
  return L.divIcon({
    className: `waselni-marker waselni-marker-${kind}`,
    html: '<span class="waselni-marker-pin"><span class="waselni-marker-core"></span></span>',
    iconSize: [32, 40],
    iconAnchor: [16, 38],
    popupAnchor: [0, -32],
  })
}
