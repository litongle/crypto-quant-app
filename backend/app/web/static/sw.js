// 币钱袋 PWA Service Worker v1
const CACHE_NAME = 'cq-sw-v1';
const STATIC_ASSETS = [
  '/web/',
  '/web/static/css/app.css',
  '/web/static/js/api.js',
  '/web/static/js/dashboard.js',
  '/web/static/js/strategy.js',
  '/web/static/js/backtest.js',
  '/web/static/js/accounts.js',
  '/web/static/js/market.js',
  '/web/static/js/trading.js',
  '/web/static/manifest.json',
];

// Install: pre-cache static shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
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
