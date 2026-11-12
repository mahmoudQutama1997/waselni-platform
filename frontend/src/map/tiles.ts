import L from './leaflet';
import { isNativePlatform } from '../platform';
import { createStadiaTileLayer } from './stadiaTileLayer';
import { MAP_TILE_URL, MAP_ATTRIBUTION } from '../config';

export { MAP_TILE_URL, MAP_ATTRIBUTION };

export function createTileLayer(options: { maxZoom?: number; attribution?: string } = {}) {
  const maxZoom = options.maxZoom ?? 19;
  const attribution = options.attribution ?? MAP_ATTRIBUTION;
  if (isNativePlatform()) {
    return createStadiaTileLayer({ tileUrl: MAP_TILE_URL, attribution, maxZoom });
  }
  return L.tileLayer(MAP_TILE_URL, { maxZoom, attribution });
}
