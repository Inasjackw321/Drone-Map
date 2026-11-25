/* Drone Map service worker: offline app shell + last known state. */
const VERSION = 'dm-v6';
const SHELL = [
  '/', '/index.html', '/styles.css', '/app.js', '/icons.js', '/basemap.js', '/snapshot.js', '/data/admin.json', '/manifest.webmanifest',
  '/icons/favicon.svg', '/icons/icon-192.png', '/icons/icon-512.png',
  '/vendor/leaflet/leaflet.css', '/vendor/leaflet/leaflet.js', '/vendor/leaflet-heat/leaflet-heat.js',
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => Promise.allSettled(SHELL.map(u => c.add(u)))).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION && k !== 'dm-tiles').map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;

  // live data: network first, fall back to the last good copy when offline
  if (url.pathname === '/api/state') {
    e.respondWith(fetch(e.request).then(res => {
      if (res.status === 200) { const copy = res.clone(); caches.open(VERSION).then(c => c.put('/api/state', copy)); }
      return res;
    }).catch(() => caches.match('/api/state').then(r => r || new Response('{}', { status: 503 }))));
    return;
  }
  if (url.pathname === '/api/occupied') {
    e.respondWith(fetch(e.request).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(VERSION).then(c => c.put('/api/occupied', copy)); }
      return res;
    }).catch(() => caches.match('/api/occupied')));
    return;
  }
  if (url.pathname.startsWith('/api/')) return;

  // map tiles: cache as they are viewed (bounded)
  if (url.hostname === 'tile.openstreetmap.org' || url.hostname === 'server.arcgisonline.com') {
    e.respondWith(caches.open('dm-tiles').then(async c => {
      const hit = await c.match(e.request);
      if (hit) return hit;
      const res = await fetch(e.request);
      if (res.ok) {
        c.put(e.request, res.clone());
        c.keys().then(keys => { if (keys.length > 800) keys.slice(0, keys.length - 800).forEach(k => c.delete(k)); });
      }
      return res;
    }).catch(() => fetch(e.request)));
    return;
  }

  // app shell: stale-while-revalidate
  e.respondWith(caches.open(VERSION).then(async c => {
    const hit = await c.match(e.request, { ignoreSearch: true });
    const net = fetch(e.request).then(res => { if (res.ok) c.put(e.request, res.clone()); return res; }).catch(() => hit);
    return hit || net;
  }));
});
