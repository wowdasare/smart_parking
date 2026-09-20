{% load static %}{% comment %}
  Service worker for the ATU Smart Parking PWA.

  Served from the site root (/sw.js) rather than /static/js/ on purpose: a
  worker's default scope is the directory it is served from, and it has to be
  "/" to control every page in the app.

  CACHING POLICY — the important part.

  This app is role-gated: a student, a security officer and an admin all see
  different HTML at the same URLs. Caching rendered pages would mean the next
  person to open the app on a shared phone could be served the previous
  person's dashboard straight out of the cache. So:

    * HTML navigations  -> network only, with the offline page as the fallback
                           when the network is gone. Nothing is ever stored.
    * Static assets     -> cached. CSS, JS, icons and fonts carry no personal
                           data, and caching them is what makes the app open
                           instantly and feel native.

  The trade-off is deliberate: offline means "you get the offline page", not
  "you get a stale copy of your bookings". Showing someone an out-of-date slot
  as if it were live is worse than telling them plainly they're offline.
{% endcomment %}
// Bump CACHE_VERSION to force every client to drop its old caches on activate.
const CACHE_VERSION = 'v1';
const STATIC_CACHE = 'atu-parking-static-' + CACHE_VERSION;
const OFFLINE_URL = '{% url "offline" %}';

// Same-origin assets worth having before the first offline load.
const PRECACHE_URLS = [
    OFFLINE_URL,
    '{% static "css/main.css" %}',
    '{% static "js/main.js" %}',
    '{% static "img/atu-badge.png" %}',
    '{% static "img/icon-192.png" %}',
    '{% static "img/icon-512.png" %}',
];

// Third-party origins we cache at runtime (Bootstrap, icon font, Google Fonts).
// All are version-pinned URLs, so a plain cache-first read can't go stale.
const CACHEABLE_ORIGINS = [
    'https://cdn.jsdelivr.net',
    'https://fonts.googleapis.com',
    'https://fonts.gstatic.com',
];

self.addEventListener('install', (event) => {
    event.waitUntil((async () => {
        const cache = await caches.open(STATIC_CACHE);
        // addAll() is atomic — one 404 would throw away the whole install — so
        // each URL is added on its own and allowed to fail independently.
        await Promise.all(PRECACHE_URLS.map(async (url) => {
            try {
                await cache.add(new Request(url, { cache: 'reload' }));
            } catch (err) {
                console.warn('[sw] could not precache', url, err);
            }
        }));
        await self.skipWaiting();
    })());
});

self.addEventListener('activate', (event) => {
    event.waitUntil((async () => {
        const names = await caches.keys();
        await Promise.all(
            names
                .filter((name) => name.startsWith('atu-parking-') && name !== STATIC_CACHE)
                .map((name) => caches.delete(name))
        );
        await self.clients.claim();
    })());
});

// Lets the page tell a waiting worker to take over immediately (see base.html).
self.addEventListener('message', (event) => {
    if (event.data === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});

function isCacheableAsset(request, url) {
    if (request.method !== 'GET') return false;
    if (CACHEABLE_ORIGINS.includes(url.origin)) return true;
    if (url.origin !== self.location.origin) return false;
    // Same-origin: only the static dir. Never /media/ (uploaded permit
    // documents and vehicle photos are private) and never app routes.
    return url.pathname.startsWith('{% get_static_prefix %}');
}

self.addEventListener('fetch', (event) => {
    const request = event.request;
    const url = new URL(request.url);

    // Never touch non-GET, the Django admin, or the sensor API — those must
    // always hit the network and must never be replayed from a cache.
    if (request.method !== 'GET') return;
    if (url.origin === self.location.origin &&
        (url.pathname.startsWith('/admin/') || url.pathname.startsWith('/api/'))) {
        return;
    }

    // HTML navigations: straight to the network, offline page on failure.
    if (request.mode === 'navigate') {
        event.respondWith((async () => {
            try {
                return await fetch(request);
            } catch (err) {
                const cache = await caches.open(STATIC_CACHE);
                const offline = await cache.match(OFFLINE_URL);
                return offline || new Response(
                    '<h1>Offline</h1><p>ATU Smart Parking needs a connection.</p>',
                    { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
                );
            }
        })());
        return;
    }

    if (!isCacheableAsset(request, url)) return;

    // Assets: serve from cache immediately, refresh in the background.
    event.respondWith((async () => {
        const cache = await caches.open(STATIC_CACHE);
        const cached = await cache.match(request);

        const network = fetch(request).then((response) => {
            // Opaque (cross-origin, no-cors) responses have status 0 but are
            // still valid to store and replay for fonts and CDN files.
            if (response && (response.ok || response.type === 'opaque')) {
                cache.put(request, response.clone());
            }
            return response;
        }).catch(() => null);

        return cached || (await network) || Response.error();
    })());
});
