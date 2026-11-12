import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { ROLES } from './src/pwa/roles.js'

const frontendDir = path.dirname(fileURLToPath(import.meta.url))
const portalRoles = ['customer', 'captain', 'merchant', 'admin']
const assetRoot = path.join(frontendDir, 'pwa-assets')

const SPLASH_SCREENS = [
  { w: 320, h: 568, r: 2, orientation: 'portrait' },
  { w: 375, h: 667, r: 2, orientation: 'portrait' },
  { w: 414, h: 736, r: 3, orientation: 'portrait' },
  { w: 414, h: 896, r: 2, orientation: 'portrait' },
  { w: 375, h: 812, r: 3, orientation: 'portrait' },
  { w: 414, h: 896, r: 3, orientation: 'portrait' },
  { w: 390, h: 844, r: 3, orientation: 'portrait' },
  { w: 393, h: 852, r: 3, orientation: 'portrait' },
  { w: 428, h: 926, r: 3, orientation: 'portrait' },
  { w: 430, h: 932, r: 3, orientation: 'portrait' },
  { w: 768, h: 1024, r: 2, orientation: 'portrait' },
  { w: 834, h: 1194, r: 2, orientation: 'portrait' },
  { w: 1024, h: 1366, r: 2, orientation: 'portrait' },
  { w: 667, h: 375, r: 2, orientation: 'landscape' },
  { w: 736, h: 414, r: 3, orientation: 'landscape' },
  { w: 834, h: 1194, r: 2, orientation: 'landscape' },
  { w: 896, h: 414, r: 3, orientation: 'landscape' },
  { w: 932, h: 430, r: 3, orientation: 'landscape' },
  { w: 1024, h: 768, r: 2, orientation: 'landscape' },
  { w: 1366, h: 1024, r: 2, orientation: 'landscape' },
]

const CONTENT_TYPES = {
  '.png': 'image/png',
  '.json': 'application/json; charset=utf-8',
  '.webmanifest': 'application/manifest+json; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.svg': 'image/svg+xml',
}

function buildManifest(role) {
  const meta = ROLES[role] || ROLES.all
  const separator = meta.startUrl.includes('?') ? '&' : '?'
  return {
    id: `/?app=${meta.key}`,
    name: meta.appNameAr,
    short_name: meta.shortNameAr,
    description: meta.descriptionAr,
    lang: 'ar',
    dir: 'rtl',
    start_url: `${meta.startUrl}${separator}source=pwa`,
    scope: '/',
    display: 'standalone',
    display_override: ['window-controls-overlay', 'standalone', 'minimal-ui'],
    orientation: meta.orientation,
    theme_color: meta.themeColor,
    background_color: meta.backgroundColor,
    categories: [...new Set([meta.category, 'delivery', 'shopping'])],
    icons: [
      { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
      { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
      { src: '/icons/maskable-192.png', sizes: '192x192', type: 'image/png', purpose: 'maskable' },
      { src: '/icons/maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
      { src: '/icons/monochrome-512.png', sizes: '512x512', type: 'image/png', purpose: 'monochrome' },
    ],
    shortcuts: (meta.shortcuts || []).map((shortcut) => ({
      name: shortcut.name,
      short_name: shortcut.short_name,
      url: shortcut.url,
      icons: shortcut.icons.map((icon) => ({ ...icon, src: `/${icon.src}` })),
    })),
    prefer_related_applications: false,
  }
}

function buildOfflinePage(role) {
  const meta = ROLES[role] || ROLES.all
  const template = fs.readFileSync(path.join(frontendDir, 'pwa', 'offline-template.html'), 'utf8')
  return template
    .replaceAll('__APP_NAME__', meta.appNameAr)
    .replaceAll('__APP_NAME_EN__', meta.appNameEn)
    .replaceAll('__THEME__', meta.themeColor)
    .replaceAll('__BG__', meta.backgroundColor)
}

function buildServiceWorker(role, version, precache) {
  const template = fs.readFileSync(path.join(frontendDir, 'pwa', 'sw-template.js'), 'utf8')
  return template
    .replaceAll('__ROLE__', role)
    .replaceAll('__VERSION__', version)
    .replaceAll('__PRECACHE__', JSON.stringify(precache, null, 2))
}

function htmlTags(role) {
  const meta = ROLES[role] || ROLES.all
  const tags = [
    { tag: 'meta', attrs: { name: 'application-name', content: meta.appNameEn }, injectTo: 'head' },
    { tag: 'meta', attrs: { name: 'apple-mobile-web-app-capable', content: 'yes' }, injectTo: 'head' },
    { tag: 'meta', attrs: { name: 'mobile-web-app-capable', content: 'yes' }, injectTo: 'head' },
    { tag: 'meta', attrs: { name: 'apple-mobile-web-app-status-bar-style', content: 'default' }, injectTo: 'head' },
    { tag: 'meta', attrs: { name: 'apple-mobile-web-app-title', content: meta.shortNameAr }, injectTo: 'head' },
    { tag: 'meta', attrs: { name: 'format-detection', content: 'telephone=no' }, injectTo: 'head' },
    { tag: 'meta', attrs: { name: 'color-scheme', content: 'light' }, injectTo: 'head' },
    { tag: 'link', attrs: { rel: 'apple-touch-icon', sizes: '180x180', href: '/icons/icon-180.png' }, injectTo: 'head' },
    { tag: 'link', attrs: { rel: 'icon', type: 'image/png', sizes: '32x32', href: '/icons/favicon-32.png' }, injectTo: 'head' },
    { tag: 'link', attrs: { rel: 'icon', type: 'image/png', sizes: '16x16', href: '/icons/favicon-16.png' }, injectTo: 'head' },
    { tag: 'link', attrs: { rel: 'mask-icon', href: '/icons/monochrome-512.png', color: meta.themeColor }, injectTo: 'head' },
    {
      tag: 'script',
      children: `(function(){try{var lang=localStorage.getItem('waselni_lang')||'ar';var rtl=lang!=='en';document.documentElement.lang=lang;document.documentElement.dir=rtl?'rtl':'ltr';document.documentElement.style.backgroundColor=${JSON.stringify(meta.backgroundColor)};}catch(e){}})();`,
      injectTo: 'head',
    },
  ]

  for (const screen of SPLASH_SCREENS) {
    tags.push({
      tag: 'link',
      attrs: {
        rel: 'apple-touch-startup-image',
        media: `(device-width: ${screen.w}px) and (device-height: ${screen.h}px) and (-webkit-device-pixel-ratio: ${screen.r}) and (orientation: ${screen.orientation})`,
        href: `/splash/splash-${screen.w * screen.r}x${screen.h * screen.r}.png`,
      },
      injectTo: 'head',
    })
  }

  return tags
}

function listRolesAssets(role) {
  const roleDir = path.join(assetRoot, role)
  if (!fs.existsSync(roleDir)) {
    throw new Error(
      `Missing PWA assets for "${role}". Run: python scripts/generate_pwa_assets.py`
    )
  }
  const files = []
  for (const folder of ['icons', 'splash']) {
    const dir = path.join(roleDir, folder)
    if (!fs.existsSync(dir)) continue
    for (const name of fs.readdirSync(dir)) {
      files.push({ folder, name, file: path.join(dir, name) })
    }
  }
  return files
}

function sendFile(res, filePath) {
  if (!fs.existsSync(filePath)) return false
  res.setHeader('Content-Type', CONTENT_TYPES[path.extname(filePath)] || 'application/octet-stream')
  res.end(fs.readFileSync(filePath))
  return true
}

/** Generates the role-specific manifest, icons, splash screens, service worker and hosting files. */
function waselniPwa(role, config) {
  const meta = ROLES[role] || ROLES.all
  const manifest = buildManifest(role)

  return {
    name: 'waselni-pwa',
    configResolved(resolved) {
      config = resolved
    },
    buildStart() {
      listRolesAssets(role)
    },
    transformIndexHtml(html) {
      return {
        html: html
          .replaceAll('__WASELNI_TITLE__', `${meta.appNameAr} | ${meta.appNameEn}`)
          .replaceAll('__WASELNI_DESCRIPTION__', meta.descriptionAr)
          .replaceAll('__WASELNI_THEME__', meta.themeColor)
          .replaceAll('__WASELNI_BACKGROUND__', meta.backgroundColor)
          .replaceAll('__WASELNI_APP_NAME__', meta.appNameAr),
        tags: htmlTags(role),
      }
    },
    generateBundle(_options, bundle) {
      for (const asset of listRolesAssets(role)) {
        this.emitFile({
          type: 'asset',
          fileName: `${asset.folder}/${asset.name}`,
          source: fs.readFileSync(asset.file),
        })
      }

      this.emitFile({
        type: 'asset',
        fileName: 'manifest.webmanifest',
        source: JSON.stringify(manifest, null, 2),
      })

      this.emitFile({
        type: 'asset',
        fileName: 'offline.html',
        source: buildOfflinePage(role),
      })

      const buildAssets = Object.keys(bundle)
        .filter((fileName) => /\.(js|css)$/.test(fileName))
        .map((fileName) => `/${fileName}`)

      const precache = [
        '/index.html',
        '/offline.html',
        '/manifest.webmanifest',
        '/icons/icon-192.png',
        '/icons/icon-512.png',
        '/icons/icon-180.png',
        '/icons/maskable-192.png',
        '/icons/maskable-512.png',
        ...buildAssets,
      ]

      const version = crypto
        .createHash('sha256')
        .update(`${role}:${precache.join('|')}`)
        .digest('hex')
        .slice(0, 12)

      this.emitFile({
        type: 'asset',
        fileName: 'sw.js',
        source: buildServiceWorker(role, version, precache),
      })

      this.emitFile({
        type: 'asset',
        fileName: '_redirects',
        source: '/*    /index.html   200\n',
      })

      this.emitFile({
        type: 'asset',
        fileName: '_headers',
        source: [
          '/*',
          '  X-Content-Type-Options: nosniff',
          '  X-Frame-Options: SAMEORIGIN',
          '  Referrer-Policy: strict-origin-when-cross-origin',
          '  Permissions-Policy: geolocation=(self), camera=(), microphone=()',
          '',
          '/sw.js',
          '  Cache-Control: no-cache, no-store, must-revalidate',
          '  Service-Worker-Allowed: /',
          '  Content-Type: application/javascript; charset=utf-8',
          '',
          '/manifest.webmanifest',
          '  Cache-Control: no-cache',
          '  Content-Type: application/manifest+json; charset=utf-8',
          '',
          '/index.html',
          '  Cache-Control: no-cache',
          '',
          '/assets/*',
          '  Cache-Control: public, max-age=31536000, immutable',
          '',
          '/icons/*',
          '  Cache-Control: public, max-age=604800',
          '',
          '/splash/*',
          '  Cache-Control: public, max-age=604800',
          '',
        ].join('\n'),
      })

      this.emitFile({
        type: 'asset',
        fileName: 'vercel.json',
        source: JSON.stringify(          {
            cleanUrls: false,
            rewrites: [
              {
                source:
                  '/((?!assets/|icons/|splash/|sw\\.js|manifest\\.webmanifest|offline\\.html|_headers|_redirects|vercel\\.json).*)',
                destination: '/index.html',
              },
            ],
            headers: [
              {
                source: '/sw.js',
                headers: [{ key: 'Cache-Control', value: 'no-cache, no-store, must-revalidate' }],
              },
              {
                source: '/(.*)',
                headers: [
                  { key: 'X-Content-Type-Options', value: 'nosniff' },
                  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
                ],
              },
              {
                source: '/assets/(.*)',
                headers: [{ key: 'Cache-Control', value: 'public, max-age=31536000, immutable' }],
              },
            ],
          },
          null,
          2
        ),
      })

      const indexHtml = bundle['index.html']
      if (indexHtml && typeof indexHtml.source === 'string') {
        this.emitFile({ type: 'asset', fileName: '404.html', source: indexHtml.source })
      }
    },
    closeBundle() {
      if (!config || config.command !== 'build') return
      const outDir = path.resolve(config.root, config.build.outDir)
      const indexFile = path.join(outDir, 'index.html')
      if (fs.existsSync(indexFile)) {
        fs.copyFileSync(indexFile, path.join(outDir, '404.html'))
      }
    },
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const requestPath = (req.url || '/').split('?')[0]

        if (requestPath === '/manifest.webmanifest') {
          res.setHeader('Content-Type', CONTENT_TYPES['.webmanifest'])
          res.setHeader('Cache-Control', 'no-cache')
          res.end(JSON.stringify(manifest, null, 2))
          return
        }

        if (requestPath === '/offline.html') {
          res.setHeader('Content-Type', CONTENT_TYPES['.html'])
          res.end(buildOfflinePage(role))
          return
        }

        if (requestPath === '/sw.js') {
          res.setHeader('Content-Type', CONTENT_TYPES['.js'])
          res.end(
            "self.addEventListener('install',()=>self.skipWaiting());" +
              "self.addEventListener('activate',(event)=>{event.waitUntil(caches.keys().then((keys)=>Promise.all(keys.map((key)=>caches.delete(key)))).then(()=>self.registration.unregister()))});"
          )
          return
        }

        const assetMatch = requestPath.match(/^\/(icons|splash)\/([A-Za-z0-9._-]+)$/)
        if (assetMatch) {
          const filePath = path.join(assetRoot, role, assetMatch[1], assetMatch[2])
          if (sendFile(res, filePath)) return
        }

        next()
      })
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backend = env.WASELNI_BACKEND_URL || 'http://127.0.0.1:8000'
  const portal = portalRoles.includes(mode) ? mode : 'all'
  const role = env.VITE_WASELNI_APP_ROLE || portal

  return {
    plugins: [react(), tailwindcss(), waselniPwa(role, null)],
    define: {
      'import.meta.env.VITE_WASELNI_APP_ROLE': JSON.stringify(role),
    },
    server: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': { target: backend, changeOrigin: true },
        '/media': { target: backend, changeOrigin: true },
        '/ws': { target: backend, ws: true, changeOrigin: true },
      },
    },
    build: {
      outDir: portal === 'all' ? 'dist' : `dist/${portal}`,
      emptyOutDir: true,
      rollupOptions: { input: 'index.html' },
    },
  }
})
