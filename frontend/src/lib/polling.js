/**
 * Shared data-refresh helpers.
 *
 * Screens receive updates from several triggers at once (interval, WebSocket,
 * window focus, network reconnect, visibility change). Without coalescing each
 * trigger fires its own request, so one order event could cause three or four
 * identical API calls. `makeCoalescedLoader` keeps at most one request in
 * flight and ignores triggers that arrive immediately after a completed load.
 */

/** True when the tab is in the background and should not spend requests. */
export function isHidden() {
  return typeof document !== 'undefined' && document.visibilityState === 'hidden';
}

/**
 * Wrap a loader so concurrent or back-to-back triggers share one request.
 * Returns a zero-argument function (safe to pass straight to addEventListener).
 */
export function makeCoalescedLoader(load, { minGap = 1500, skipWhenHidden = true } = {}) {
  let inFlight = null;
  let lastFinishedAt = 0;

  return function refresh() {
    if (skipWhenHidden && isHidden()) return null;
    if (inFlight) return inFlight;
    if (Date.now() - lastFinishedAt < minGap) return null;

    inFlight = Promise.resolve()
      .then(load)
      .catch(() => {
        // The loader owns its error state; never surface an unhandled rejection.
      })
      .finally(() => {
        inFlight = null;
        lastFinishedAt = Date.now();
      });

    return inFlight;
  };
}

/**
 * De-duplicate list rows by id (falling back to order_number). Backends that
 * merge two querysets, or paginated responses joined client-side, can repeat a
 * row; rendering the same order twice is always wrong.
 */
export function uniqueRows(list) {
  if (!Array.isArray(list)) return [];
  const seen = new Set();
  const rows = [];
  for (const row of list) {
    const key = row?.id ?? row?.order_number ?? row?.reference;
    if (key == null) {
      rows.push(row);
      continue;
    }
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push(row);
  }
  return rows;
}
