# WASELNI PWA Platform — Final QA Report

**Date:** 2026-11-12  
**Scope:** Customer, Merchant and Captain installable PWAs, with the existing Admin dashboard preserved  
**Backend:** one shared Django/DRF/Channels API and database for all applications  
**Result:** **No failing automated checks.** Three functional/UI defects found during QA were fixed and re-tested.

---

## 1. What was verified

All applications run against the same Django backend, JWT authentication, database and permission rules. No mock data was introduced and no API was replaced.

| Area | Check | Result |
|---|---|---|
| Backend | `manage.py check` | PASS — no issues |
| Backend | `makemigrations --check --dry-run` | PASS — no model drift |
| Backend | Full Django test suite | **PASS — 82 tests, 0 failures** |
| Backend | Real HTTP end-to-end API run (isolated SQLite DB + media dir) | PASS — 54 assertions across admin, merchant, captain, customer, uploads, media, CORS, eligibility, order lifecycle and settlements |
| Backend | WebSocket handshake, JWT authentication and order dispatch | PASS — real server + Node WebSocket client |
| Frontend | TypeScript typecheck (`tsc --noEmit`, JS checked through Vite) | PASS |
| Frontend | Production builds: customer, merchant, captain, admin | PASS (4/4) |
| PWA | Per-role manifest, icons, iOS splash images, service worker, offline page, SPA fallbacks | PASS for 4/4 roles (artifact validator) |
| PWA | Service worker runtime (customer preview build) | PASS — activated, controlling the page, app shell precached |
| Customer app | Login, storefront, map/location selection, cart, orders, account, logout | PASS |
| Merchant app | Login, forced temporary-password change, dashboard, order pipeline, catalog/report/settlement APIs | PASS |
| Captain app | Login, forced password change, eligibility panel, online/offline, GPS sharing, priced accept, full ride workflow | PASS |
| Admin | Login, live dashboard, map, user management, subscriptions, stores/captains/orders APIs | PASS |
| Mobile UX | Arabic RTL/LTR layout, no horizontal overflow, 16 px inputs (no iOS zoom), 52 px bottom navigation | PASS |
| Security | Upload validation, role permissions, CORS/CSRF allow-lists, WebSocket token handling, no secrets in frontend code | PASS |
| Deployment prep | Render blueprint, Vercel per-role configuration, environment documentation, Arabic install guide | PASS |

### Not executed (external or environment limitations)

| Item | Status | Reason |
|---|---|---|
| Installation on a physical iPhone / Android device | **NOT EXECUTED** | No physical device or remote HTTPS host available in this environment. Steps are documented in §6 and in `PWA_DEPLOYMENT_AND_INSTALL_AR.md`. |
| Airplane-mode / OS-level offline toggle | **NOT EXECUTED** | Browser tooling could not force a reliable offline network state. Service-worker rules and cached assets were validated, but the full offline user journey still needs a device test. |
| Real production deployment (Render/Vercel) | **NOT EXECUTED** | Requires account credentials and explicit authorization; deployment was intentionally not performed. |
| Native push notifications | **NOT IMPLEMENTED** | The platform uses in-app notifications + sound while the app is open; see limitations in §5. It is not claimed to support background push. |
| Payment-gateway settlement | Out of scope | Existing subscription/payment records are preserved; no payment provider was added. |

---

## 2. Defects found during QA and fixed

1. **Untranslated role slug in Arabic headers**  
   The dashboard header and the Admin user list rendered `merchant · الرئيسية` instead of `تاجر · الرئيسية`.  
   Fixed in `frontend/src/App.jsx` by resolving `<role>Role` translations before falling back to the raw role value.

2. **Assigned ride orders had no action to start the trip**  
   A captain could accept a ride, but the UI showed no button to move `assigned → picked_up`, blocking the ride workflow.  
   Fixed in `frontend/src/App.jsx`; the button now appears for assigned ride orders. Verified in the browser through `picked_up → delivering → completed`.

3. **Active order disappeared when a captain went offline or became ineligible**  
   `GET /api/orders/available/` returned an empty list for offline/ineligible captains, hiding orders already assigned to them and preventing completion.  
   Fixed in `backend/core/views.py`: dispatchable orders remain hidden, but the captain's own assigned orders stay visible. Two regression tests were added in `backend/core/test_eligibility.py`.

Earlier QA fixes retained in this change set: nested checkout `<form>` console error, iOS input zoom, WebSocket subprotocol negotiation, missing ASGI middleware `__init__`, central upload validation, and stale dispatch tests.

---

## 3. Test evidence

- Backend: `Ran 82 tests in 299.344s — OK`.
- WebSocket: authenticated connection accepted; unauthenticated handshake rejected; order events dispatched to the correct recipient.
- REST E2E: 54 assertions passed, including media upload/serving, eligibility enforcement, stale-dispatch conflicts, order transitions and cash settlement records.
- Frontend: typecheck passed; all four `vite build` runs completed; only the informational chunk-size warning was emitted.
- PWA artifacts: all roles have Arabic RTL manifests, start URLs, icons, 20 iOS splash images, shortcuts, `sw.js`, `offline.html`, `404.html`, `_headers` and `_redirects`.
- Browser checks used an isolated QA database with one customer, one merchant, one approved captain and one admin; no production data was touched.

---

## 4. Security and data-handling notes

- JWTs stay in `localStorage`; the API client refreshes on 401 and clears auth on failure.
- WebSocket authentication uses the `waselni.jwt.<token>` subprotocol; the server selects `waselni.v1` and never echoes the token. Legacy `?token=` remains only as a fallback.
- Service worker never caches `/api/`, `/ws/` or `/media/`; order status and private data are network-only. Only the app shell and static assets are cached.
- Uploads are validated by extension, MIME type, size and actual image decode (plus PDF signature for documents).
- CORS/CSRF origins are explicit allow-lists and can be extended with environment variables; no wildcard with credentials.
- No API keys, passwords or JWT secrets are present in frontend source or generated bundles.
- Production checks were run previously; the only warning was the deliberately short local test `SECRET_KEY`, which must be replaced by a generated value in deployment.

---

## 5. Known limitations (must be communicated to operations)

1. **No background push notifications.** The apps use the Web Notification API and Web Audio while open. iOS requires the PWA to be installed and still restricts notifications; Android/desktop behavior depends on browser permissions. This is not a replacement for FCM/APNs.
2. **No background GPS tracking.** Captain location is sent only while the app is open and the captain is online; browsers throttle or suspend background geolocation, especially on iOS.
3. **Free-tier hosting behavior.** Render free web services sleep when idle; the first request after sleep is slow. Free Render disks are ephemeral, so uploaded media can be lost on redeploy unless persistent storage/object storage is configured.
4. **Cross-process WebSockets need Redis/Key Value.** Without `REDIS_URL` or `REDIS_HOST`/`REDIS_PORT`, the in-memory channel layer only works within a single process.
5. **Map/geocoding providers.** Default tiles use Stadia Maps and geocoding uses public Nominatim. Production use must respect each provider's licence/usage policy and should set `VITE_MAP_TILE_URL`, `VITE_MAP_ATTRIBUTION`, `VITE_GEOCODING_URL` and `VITE_GEOCODING_SEARCH_URL`.
6. **Offline mode is app-shell only.** Cached pages load, but orders, prices and statuses require the network and are never served stale.
7. The header connection pill indicates browser network connectivity, not captain dispatch availability; the captain eligibility panel is the authoritative online/offline state.

---

## 6. تثبيت التطبيقات على الهاتف (بالعربية)

> يجب نشر التطبيق على HTTPS أولاً. لا تعمل ميزات PWA كاملة عبر HTTP أو localhost على جهاز آخر.

### iPhone / iPad (Safari)

1. افتح رابط التطبيق المخصص (الزبون أو التاجر أو الكابتن) في **Safari**.
2. اضغط زر **المشاركة** (مربع مع سهم للأعلى).
3. اختر **إضافة إلى الشاشة الرئيسية**.
4. اكتب الاسم ثم اضغط **إضافة**.
5. افتح الأيقونة من الشاشة الرئيسية، سجّل الدخول، واسمح بالوصول إلى الموقع عند طلبه.
6. للتاجر/الكابتن: استخدم رابط التطبيق الخاص بدورك، ولا تشارك حسابك مع دور آخر.

### Android (Chrome)

1. افتح رابط التطبيق في **Chrome**.
2. اضغط قائمة النقاط الثلاث.
3. اختر **تثبيت التطبيق** أو **إضافة إلى الشاشة الرئيسية**.
4. أكّد التثبيت ثم افتح الأيقونة.
5. اسمح بالإشعارات والموقع من إعدادات المتصفح عند الحاجة.

الدليل الكامل مع إعدادات النشر والمتغيرات: `PWA_DEPLOYMENT_AND_INSTALL_AR.md`.

---

## 7. Repository state

- Changes were tested locally and committed to this repository only.
- **No remote is configured in this working copy, so nothing was pushed and GitHub was not updated.**
- No force-push, deployment or production setting was changed.
- QA used a temporary SQLite database and media directory outside the repository; the Admin password reset performed for testing applied only to that isolated QA database.
