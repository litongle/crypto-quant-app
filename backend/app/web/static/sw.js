// 币钱袋 PWA Service Worker v1
const CACHE_NAME = 'cq-sw-v7';
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
  '/web/static/js/events.js',
  '/web/static/manifest.json',
];

// Install: pre-cache static shell（逐项失败不拖垮整个 install，避免偶发 302/网络导致 SW 异常）
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async (cache) => {
      for (const url of STATIC_ASSETS) {
        try {
          await cache.add(url);
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
      .catch(() => caches.match(event.request))
  );
});
