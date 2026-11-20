import L from './leaflet';
import { getStadiaKey } from './stadiaAuth';

const Leaflet = L as any;

type Options = {
  tileUrl: string;
  attribution: string;
  maxZoom?: number;
};

type Tile = HTMLImageElement & {
  _stadiaAbort?: AbortController;
  _stadiaObjectUrl?: string;
  _stadiaSettled?: boolean;
};

function base64ToBlob(base64: string, contentType: string): Blob {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], { type: contentType });
}

async function requestTileBlob(url: string, key: string, signal: AbortSignal): Promise<Blob> {
  const { CapacitorHttp } = await import('@capacitor/core');
  if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
  // Stadia requires Authorization: Stadia-Auth <key>, which WebView fetch rejects via CORS.
  // CapacitorHttp uses the native URLSession/OkHttp stack, so the header reaches Stadia.
  const response = await CapacitorHttp.get({
    url,
    headers: {
      Authorization: `Stadia-Auth ${key}`,
      'Cache-Control': 'no-store',
      Pragma: 'no-cache',
    },
    responseType: 'blob',
    connectTimeout: 15000,
    readTimeout: 15000,
  });
  if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
  if (response.status < 200 || response.status >= 300) {
    throw new Error(`Map tile request failed (${response.status}).`);
  }
  if (typeof response.data !== 'string' || !response.data) {
    throw new Error('Map tile response was empty.');
  }
  const contentType = response.headers?.['content-type'] || response.headers?.['Content-Type'] || 'image/png';
  return base64ToBlob(response.data, contentType);
}

function cleanupTile(tile: Tile, layer: any) {
  const controller = tile._stadiaAbort;
  if (controller) {
    controller.abort();
    layer._stadiaControllers?.delete(controller);
    tile._stadiaAbort = undefined;
  }
  if (tile._stadiaObjectUrl) {
    URL.revokeObjectURL(tile._stadiaObjectUrl);
    layer._stadiaUrls?.delete(tile._stadiaObjectUrl);
    tile._stadiaObjectUrl = undefined;
  }
  tile._stadiaSettled = true;
}

export function createStadiaTileLayer({ tileUrl, attribution, maxZoom = 19 }: Options) {
  const Layer = Leaflet.GridLayer.extend({
    initialize(this: any) {
      Leaflet.GridLayer.prototype.initialize.call(this, {
        maxZoom,
        attribution,
        tileSize: 256,
        updateWhenIdle: false,
        keepBuffer: 2,
      });
      this._stadiaUrl = tileUrl;
      this._stadiaControllers = new Set<AbortController>();
      this._stadiaUrls = new Set<string>();
      this.on('tileunload', (event: any) => cleanupTile(event.tile as Tile, this));
    },
    createTile(this: any, coords: any, done: (error: Error | null, tile?: HTMLElement) => void) {
      const tile = document.createElement('img') as Tile;
      tile.alt = '';
      tile.decoding = 'async';
      tile.setAttribute('role', 'presentation');
      const controller = new AbortController();
      tile._stadiaAbort = controller;
      this._stadiaControllers.add(controller);
      const retina = Leaflet.Browser.retina ? '@2x' : '';
      const url = Leaflet.Util.template(this._stadiaUrl, {
        z: coords.z,
        x: coords.x,
        y: coords.y,
        r: retina,
        s: '',
      });
      const finish = (error: Error | null) => {
        if (tile._stadiaSettled) return;
        tile._stadiaSettled = true;
        this._stadiaControllers.delete(controller);
        done(error, tile);
      };
      getStadiaKey()
        .then((key) => {
          if (!key) throw new Error('Map authentication is unavailable.');
          if (controller.signal.aborted) return null;
          return requestTileBlob(url, key, controller.signal);
        })
        .then((blob) => {
          if (!blob || controller.signal.aborted || tile._stadiaSettled) return;
          const objectUrl = URL.createObjectURL(blob);
          tile._stadiaObjectUrl = objectUrl;
          this._stadiaUrls.add(objectUrl);
          tile.onload = () => {
            if (controller.signal.aborted) return;
            finish(null);
          };
          tile.onerror = () => {
            if (controller.signal.aborted) return;
            finish(new Error('Map tile could not be displayed.'));
          };
          tile.src = objectUrl;
        })
        .catch((error) => {
          if (controller.signal.aborted || error?.name === 'AbortError') return;
          finish(error instanceof Error ? error : new Error('Map tile request failed.'));
        });
      return tile;
    },
    onRemove(this: any, map: any) {
      this._stadiaControllers.forEach((controller: AbortController) => controller.abort());
      this._stadiaControllers.clear();
      this._stadiaUrls.forEach((url: string) => URL.revokeObjectURL(url));
      this._stadiaUrls.clear();
      Leaflet.GridLayer.prototype.onRemove.call(this, map);
    },
  });
  return new Layer();
}
