const cacheName = 'hoc-trung-app-v2'

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(cacheName)
    const shell = await fetch('/', { cache: 'reload' })
    if (!shell.ok) throw new Error('App shell could not be fetched')
    const html = await shell.clone().text()
    const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map(match => match[1])
    await cache.addAll([...new Set([...assets, '/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png'])])
    await cache.put('/', shell)
    await self.skipWaiting()
  })())
})

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    await Promise.all((await caches.keys()).filter(key => key.startsWith('hoc-trung-app-') && key !== cacheName).map(key => caches.delete(key)))
    await self.clients.claim()
  })())
})

self.addEventListener('fetch', event => {
  const request = event.request
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return

  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(async () => (await caches.match('/')) || Response.error()))
  } else if (url.pathname.startsWith('/assets/') || url.pathname.startsWith('/icons/') || url.pathname === '/manifest.webmanifest') {
    event.respondWith((async () => {
      const cache = await caches.open(cacheName)
      const cached = await cache.match(request)
      if (cached) return cached
      const result = await fetch(request)
      if (result.ok) await cache.put(request, result.clone())
      return result
    })())
  }
})
