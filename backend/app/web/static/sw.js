// Alpha-7 PWA Service Worker v1
const CACHE_NAME = 'cq-sw-v143';
const STATIC_ASSETS = [
  '/web/',
  '/web/static/css/app.css',
  '/web/static/js/api.js',
  '/web/static/js/dashboard.js',
  '/web/static/js/kline.js',
  '/web/static/js/strategy.js',
  '/web/static/js/backtest.js',
  '/web/static/js/accounts.js',
  '/web/static/js/paper.js',
  '/web/static/js/settings-drawer.js',
  '/web/static/js/instance-drawer.js',
  '/web/static/js/instance-logs-drawer.js',
  '/web/static/js/events.js',
  '/web/static/js/symbol-selector.js',
  '/web/static/vendor/lightweight-charts.standalone.production.min.js',
  '/web/static/vendor/qrcode.min.js',
  '/web/static/manifest.json',
  '/web/static/fonts/geist/Geist-Variable.woff2',
  '/web/static/fonts/jetbrains-mono/JetBrainsMono-Variable.woff2',
];

// Install: pre-cache static shell（逐项失败不拖垮整个 install，避免偶发 302/网络导致 SW 异常）
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async (cache) => {
      for (const url of STATIC_ASSETS) {
        try {
          // cache: 'reload' 强制绕过 HTTP cache，避免 install 时拿到旧版
          await cache.add(new Request(url, { cache: 'reload' }));
        } catch {
          /* 忽略单项预缓存失败 */
        }
      }
    })
  );
  self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch: network-first for API, cache-first for static
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API calls: network only (never cache sensitive data)
  if (url.pathname.startsWith('/api/')) {
    return;
  }

  // Static assets: stale-while-revalidate
  if (STATIC_ASSETS.some((a) => url.pathname.endsWith(a) || url.pathname === a)) {
    event.respondWith(
      caches.open(CACHE_NAME).then((cache) =>
        cache.match(event.request).then((cached) => {
          const fetched = fetch(event.request).then((response) => {
            if (response.ok) cache.put(event.request, response.clone());
            return response;
          }).catch(() => cached);
          return cached || fetched;
        })
      )
    );
    return;
  }

  // Everything else: network first, fallback to cache
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok && event.request.method === 'GET') {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(async () => {
        const matched = await caches.match(event.request);
        if (matched) return matched;
        // SPA deep link 离线兜底：/web/<page> 没缓存时 fallback 到 /web/ (index.html)
        if (url.pathname.startsWith('/web/') && !url.pathname.startsWith('/web/static/')) {
          return caches.match('/web/');
        }
        return undefined;
      })
  );
});
