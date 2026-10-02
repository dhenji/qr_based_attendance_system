/// <reference types="@sveltejs/kit" />
/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" */

// Attendly offline shell (no backend involved).
//
// What this worker does:
// - Precaches the versioned app shell (SvelteKit `build` + `files` assets)
//   so reloads open the real UI while offline, with queued counts intact
//   from IndexedDB.
// - Serves navigations network-first with a cached-shell fallback, static
//   assets cache-first, and backend/API traffic network-only (the Cache API
//   keys ignore Authorization, so caching authed GETs would leak data across
//   accounts on shared devices).
// - Relays Background Sync `attendly-outbox` wake-ups to open pages via
//   postMessage; the page runs the authed drain it already owns
//   (sync/service.ts flushQueue).
//
// What it deliberately does NOT do: replay scans itself. The auth token
// lives in localStorage, which workers cannot read, so a closed app cannot
// authenticate — true closed-app drain would need cookie auth (backend).

import { build, files, version } from '$service-worker';

const SHELL_CACHE = `attendly-shell-${version}`;
const PRECACHE = [...build, ...files];

const isNavigation = (request: Request): boolean => request.mode === 'navigate';

const isBackendCall = (url: URL): boolean =>
	url.pathname.startsWith('/api/') || url.origin !== self.location.origin;

self.addEventListener('install', (event) => {
	(event as ExtendableEvent).waitUntil(
		(async () => {
			const cache = await caches.open(SHELL_CACHE);
			await cache.addAll(PRECACHE);
			await (self as unknown as ServiceWorkerGlobalScope).skipWaiting();
		})()
	);
});

self.addEventListener('activate', (event) => {
	(event as ExtendableEvent).waitUntil(
		(async () => {
			const keys = await caches.keys();
			await Promise.all(keys.filter((key) => key !== SHELL_CACHE).map((key) => caches.delete(key)));
			await (self as unknown as ServiceWorkerGlobalScope).clients.claim();
		})()
	);
});

self.addEventListener('fetch', (event) => {
	const { request } = event as FetchEvent;
	if (request.method !== 'GET') return;
	const url = new URL(request.url);

	// Backend and cross-origin traffic: never touch the cache.
	if (isBackendCall(url)) return;

	(event as FetchEvent).respondWith(
		(async () => {
			const cache = await caches.open(SHELL_CACHE);
			if (isNavigation(request)) {
				// App shell offline: fresh shell when reachable, cached shell
				// (root document) when not.
				try {
					const fresh = await fetch(request);
					void cache.put(request, fresh.clone()).catch(() => undefined);
					return fresh;
				} catch {
					const cached =
						(await cache.match(request)) ?? (await cache.match('/')) ?? (await cache.match('/index.html'));
					if (cached) return cached;
					throw new Error('Offline and no cached shell available.');
				}
			}
			// Versioned static assets: cache-first.
			const cached = await cache.match(request);
			if (cached) return cached;
			const fresh = await fetch(request);
			void cache.put(request, fresh.clone()).catch(() => undefined);
			return fresh;
		})()
	);
});

type SyncEventLike = ExtendableEvent & { tag: string };

self.addEventListener('sync', (event) => {
	const syncEvent = event as SyncEventLike;
	if (syncEvent.tag !== 'attendly-outbox') return;
	syncEvent.waitUntil(
		(async () => {
			const scope = self as unknown as ServiceWorkerGlobalScope;
			const clients = await scope.clients.matchAll({ type: 'window', includeUncontrolled: true });
			for (const client of clients) {
				client.postMessage({ type: 'FLUSH_OUTBOX' });
			}
		})()
	);
});
