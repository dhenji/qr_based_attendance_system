/// <reference types="@sveltejs/kit" />
/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />

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

// The worker is production-only: under `vite dev` (incl. the docker compose
// dev stack on :5173) assets rebuild on every edit and the dev server drops
// connections during HMR restarts, so intercepting fetches only serves stale
// shells and turns transient blips into unhandled FetchEvent rejections
// (issue #223). Offline support is tested via `build + preview` instead.
// NOTE: only `$service-worker` / `$env/*` may be imported here — SvelteKit
// rejects `$app/environment` in worker bundles at build time, so the Vite
// `import.meta.env.DEV` flag (inlined per-bundle) is the environment gate.
const WORKER_ENABLED = !import.meta.env.DEV;

const SHELL_CACHE = `attendly-shell-${version}`;
const PRECACHE = [...build, ...files];

// `destination === 'document'` covers same-URL `/` requests whose mode is
// not `navigate` (preload / re-fetch during rebuilds), which previously fell
// through to the unguarded cache-first branch and rejected at fetch (#223).
const isNavigation = (request: Request): boolean =>
	request.mode === 'navigate' || request.destination === 'document';

const isBackendCall = (url: URL): boolean =>
	url.pathname.startsWith('/api/') || url.origin !== self.location.origin;

// Vite / SvelteKit internals must never be intercepted or cached: HMR
// (`/@*`, `/__*`), build metadata (`/.svelte-kit`), and data preloads
// (`?__data`) are ephemeral dev artifacts, not offline assets.
const isDevInternal = (url: URL): boolean =>
	url.pathname.startsWith('/@') ||
	url.pathname.startsWith('/__') ||
	url.pathname.startsWith('/.svelte-kit') ||
	url.searchParams.has('__data');

self.addEventListener('install', (event) => {
	if (!WORKER_ENABLED) return;
	(event as ExtendableEvent).waitUntil(
		(async () => {
			const cache = await caches.open(SHELL_CACHE);
			await cache.addAll(PRECACHE);
			await (self as unknown as ServiceWorkerGlobalScope).skipWaiting();
		})()
	);
});

self.addEventListener('activate', (event) => {
	if (!WORKER_ENABLED) return;
	(event as ExtendableEvent).waitUntil(
		(async () => {
			const keys = await caches.keys();
			await Promise.all(keys.filter((key) => key !== SHELL_CACHE).map((key) => caches.delete(key)));
			await (self as unknown as ServiceWorkerGlobalScope).clients.claim();
		})()
	);
});

self.addEventListener('fetch', (event) => {
	if (!WORKER_ENABLED) return;
	const { request } = event as FetchEvent;
	if (request.method !== 'GET') return;
	// Chrome throws if a worker calls respondWith on an `only-if-cached`
	// request with a non-`same-origin` mode — never intercept those.
	if (request.cache === 'only-if-cached' && request.mode !== 'same-origin') return;
	const url = new URL(request.url);
	if (url.protocol !== 'http:' && url.protocol !== 'https:') return;

	// Backend and cross-origin traffic: never touch the cache.
	if (isBackendCall(url)) return;
	// Dev internals: let them fall through to the network untouched.
	if (isDevInternal(url)) return;

	(event as FetchEvent).respondWith(
		(async () => {
			const cache = await caches.open(SHELL_CACHE);
			if (isNavigation(request)) {
				// App shell offline: fresh shell when reachable, cached shell
				// (root document) when not.
				try {
					const fresh = await fetch(request);
					void cache
						.put(request, fresh.clone())
						.catch((error: unknown) => console.debug('[sw] shell cache put failed:', error));
					return fresh;
				} catch {
					const cached =
						(await cache.match(request)) ?? (await cache.match('/')) ?? (await cache.match('/index.html'));
					if (cached) return cached;
					throw new Error('Offline and no cached shell available.');
				}
			}
			// Versioned static assets: cache-first, with a cached fallback so a
			// transient network blip never rejects the FetchEvent (#223).
			try {
				const cached = await cache.match(request);
				if (cached) return cached;
				const fresh = await fetch(request);
				void cache
					.put(request, fresh.clone())
					.catch((error: unknown) => console.debug('[sw] asset cache put failed:', error));
				return fresh;
			} catch {
				const fallback = await cache.match(request);
				if (fallback) return fallback;
				throw new Error('Offline and no cached asset available.');
			}
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
