import L from './leaflet';
import { isNativePlatform } from '../platform';
import { createStadiaTileLayer } from './stadiaTileLayer';
import { MAP_TILE_URL, MAP_ATTRIBUTION } from '../config';

export { MAP_TILE_URL, MAP_ATTRIBUTION };

/**
 * Install the licence attribution for the active tile provider.
 *
 * Leaflet's default control prefixes the line with its own "Leaflet" link,
 * which is optional branding and makes the strip wrap on narrow panels. The
 * provider attribution (OpenStreetMap, Stadia Maps, …) is kept in full because
 * it is a licence requirement.
 */
export function attachAttribution(map: ReturnType<typeof L.map>) {
  L.control.attribution({ prefix: false }).addTo(map);
  return map;
}

export function createTileLayer(options: { maxZoom?: number; attribution?: string } = {}) {
  const maxZoom = options.maxZoom ?? 19;
  const attribution = options.attribution ?? MAP_ATTRIBUTION;
  if (isNativePlatform()) {
    return createStadiaTileLayer({ tileUrl: MAP_TILE_URL, attribution, maxZoom });
  }
  return L.tileLayer(MAP_TILE_URL, { maxZoom, attribution });
}
