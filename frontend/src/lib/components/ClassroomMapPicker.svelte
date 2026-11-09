<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { searchLocation, type LocationSearchResult, reverseGeocode } from '$lib/shared/utils/geo';
	import { acquire } from '$lib/shared/location/manager';
import { toMapPickerMessage } from '$lib/features/liveness/errors';

	interface Props {
		lat: number | null;
		lng: number | null;
		onChange: (lat: number, lng: number) => void;
		onClear?: () => void;
		height?: string;
		radius?: number | null;
		allowLocate?: boolean;
	}

	let {
	lat = $bindable(null),
	lng = $bindable(null),
	onChange,
	onClear,
	height = '380px',
	radius = null,
	allowLocate = true
}: Props = $props();

	let container: HTMLDivElement | null = null;
	let map: any = null;
	let marker: any = null;
	let leaflet: any = null;
	let resizeObserver: ResizeObserver | null = null;
let gpsMarker: any = null;
let gpsAccuracyCircle: any = null;
let radiusCircle: any = null;

	let locating = $state(false);
	let gpsError = $state<string | null>(null);
	let gpsAccuracy = $state<number | null>(null);
	let gpsAddress = $state<string | null>(null);
	let locateAbortController: AbortController | null = null;

	let searchQuery = $state('');
	let results = $state<LocationSearchResult[]>([]);
	let searching = $state(false);
	let showResults = $state(false);
	let searchTimer: ReturnType<typeof setTimeout> | null = null;
	let expanded = $state(false);
	const effectiveHeight = $derived(expanded ? '70vh' : height);

	const DEFAULT_CENTER: [number, number] = [14.5995, 120.9842];
	const DEFAULT_ZOOM = 16;

	function accuracyBandColor(accuracy: number): string {
		if (accuracy <= 50) return '#16a34a';
		if (accuracy <= 100) return '#b45309';
		return '#dc2626';
	}

	function placeMarker(m: any, L: any, latitude: number, longitude: number) {
		if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return;
		if (marker) {
			marker.setLatLng([latitude, longitude]);
		} else {
			marker = L.marker([latitude, longitude], { draggable: true }).addTo(m);
			marker.on('dragend', () => {
				const pos = marker.getLatLng();
				lat = pos.lat;
				lng = pos.lng;
				onChange(pos.lat, pos.lng);
			});
		}
		m.setView([latitude, longitude], Math.max(m.getZoom(), 14));
	}

	async function locate() {
		if (!allowLocate || locating) return;
		if (!map || !leaflet) {
			gpsError = 'Map is still loading. Try again in a moment.';
			return;
		}
		locating = true;
		gpsError = null;
		gpsAddress = null;
		const controller = new AbortController();
		locateAbortController = controller;
		try {
			const state = await acquire({
				desiredAccuracy: 50,
				maxFixes: 3,
				timeoutMs: 10000,
				maxAccuracy: 1000,
				fastMaximumAge: 5000,
				signal: controller.signal
			});
			if (state.error || state.latitude === null || state.longitude === null || state.accuracy === null) {
				const err = new Error(state.error?.message ?? 'Unable to get your location.');
				(err as any).code = state.error?.code ?? 'location_unavailable';
				gpsError = toMapPickerMessage(err, 'Unable to get your location.');
				return;
			}
			const fix = { lat: state.latitude, lng: state.longitude, accuracy: state.accuracy };
			gpsAccuracy = fix.accuracy;
			lat = fix.lat;
			lng = fix.lng;
			// Best-effort reverse geocode for display; never blocks the pin.
			if (typeof reverseGeocode === 'function') {
				reverseGeocode(fix.lat, fix.lng).then((label) => {
					if (label) gpsAddress = label;
				});
			}
			placeMarker(map, leaflet, fix.lat, fix.lng);
			if (gpsMarker) {
				gpsMarker.remove();
				gpsMarker = null;
			}
			const icon = leaflet.divIcon({
				className: 'gps-marker',
				html: '<div style="width:12px;height:12px;border-radius:50%;background:#2563eb;border:2px solid #fff;box-shadow:0 0 0 2px #2563eb;"></div>',
				iconSize: [12, 12]
			});
			gpsMarker = leaflet.marker([fix.lat, fix.lng], { icon, interactive: false }).addTo(map);
			if (gpsAccuracyCircle) {
				try { gpsAccuracyCircle.remove(); } catch { /* ignore */ }
				gpsAccuracyCircle = null;
			}
			const circleColor = accuracyBandColor(fix.accuracy);
			gpsAccuracyCircle = leaflet.circle([fix.lat, fix.lng], {
				radius: Math.max(1, Math.min(fix.accuracy, 1000)),
				color: circleColor,
				weight: 1,
				fillColor: circleColor,
				fillOpacity: 0.08,
				dashArray: '4 4'
			}).addTo(map);
			onChange(fix.lat, fix.lng);
		} catch (e: any) {
			gpsError = toMapPickerMessage(e, 'Unable to get your location.');
		} finally {
			locating = false;
			locateAbortController = null;
		}
	}

	function scheduleSearch() {
		if (searchTimer) clearTimeout(searchTimer);
		const q = searchQuery;
		if (q.trim().length < 3) {
			results = [];
			showResults = false;
			return;
		}
		searchTimer = setTimeout(async () => {
			searching = true;
			const found = await searchLocation(q);
			results = found;
			showResults = found.length > 0;
			searching = false;
		}, 300);
	}

	function selectResult(r: LocationSearchResult) {
		lat = r.lat;
		lng = r.lng;
		if (map && leaflet) placeMarker(map, leaflet, r.lat, r.lng);
		onChange(r.lat, r.lng);
		showResults = false;
		searchQuery = r.label;
	}

	function clearPin() {
		lat = null;
		lng = null;
		if (marker) {
			marker.remove();
			marker = null;
		}
		if (gpsMarker) {
			gpsMarker.remove();
			gpsMarker = null;
		}
		if (gpsAccuracyCircle) {
			try { gpsAccuracyCircle.remove(); } catch { /* ignore */ }
			gpsAccuracyCircle = null;
		}
		gpsAccuracy = null;
		gpsAddress = null;
		gpsError = null;
		searchQuery = '';
		onClear?.();
	}

	onMount(async () => {
		if (!container) return;
		if (!document.querySelector('link[data-leaflet-css]')) {
			const link = document.createElement('link');
			link.rel = 'stylesheet';
			link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
			link.dataset.leafletCss = 'true';
			document.head.appendChild(link);
		}
		const L = (await import('leaflet')).default;
		leaflet = L;

		// Fix default icon paths under Vite.
		// @ts-expect-error
		delete L.Icon.Default.prototype._getIconUrl;
		L.Icon.Default.mergeOptions({
			iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
			iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
			shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
		});

		const hasPin =
			lat !== null &&
			lng !== null &&
			Number.isFinite(lat) &&
			Number.isFinite(lng);
		const center: [number, number] = hasPin
			? [lat as number, lng as number]
			: DEFAULT_CENTER;
		const zoom = hasPin ? DEFAULT_ZOOM : 4;

		map = L.map(container, { keyboard: false }).setView(center, zoom);
		L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
			attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
			maxZoom: 19,
		}).addTo(map);

		if (hasPin) placeMarker(map, L, lat as number, lng as number);

		map.on('click', (e: any) => {
			const { lat: la, lng: lo } = e.latlng;
			lat = la;
			lng = lo;
			placeMarker(map, L, la, lo);
			onChange(la, lo);
		});

		// Leaflet does not recompute its tile layout when the container is
		// resized by anything other than the Enlarge/Shrink toggle (e.g. a
		// room selection that swaps the map in/out, or a parent reflow),
		// which leaves gray blank tiles overlapping the form. Observe the
		// container and invalidate on every size change.
		if (typeof ResizeObserver !== 'undefined' && container) {
			resizeObserver = new ResizeObserver(() => {
				if (!map) return;
				requestAnimationFrame(() => {
					try {
						map.invalidateSize();
					} catch {
						// map may have been removed; ignore.
					}
				});
			});
			resizeObserver.observe(container);
		}
	});

	onDestroy(() => {
		if (locateAbortController) {
			try { locateAbortController.abort(); } catch { /* ignore */ }
			locateAbortController = null;
		}
		if (resizeObserver) {
			resizeObserver.disconnect();
			resizeObserver = null;
		}
		if (gpsMarker) {
			try { gpsMarker.remove(); } catch { /* ignore */ }
			gpsMarker = null;
		}
		if (gpsAccuracyCircle) {
			try { gpsAccuracyCircle.remove(); } catch { /* ignore */ }
			gpsAccuracyCircle = null;
		}
		if (radiusCircle) {
			try { radiusCircle.remove(); } catch { /* ignore */ }
			radiusCircle = null;
		}
		if (map) {
			map.remove();
			map = null;
		}
	});

	// React to external lat/lng changes (e.g. "use my location").
	$effect(() => {
		if (
			map &&
			leaflet &&
			lat !== null &&
			lng !== null &&
			Number.isFinite(lat) &&
			Number.isFinite(lng)
		) {
			// Only re-place if marker missing or position differs notably
			const ll = marker?.getLatLng?.();
			if (!ll || Math.abs(ll.lat - lat) > 1e-9 || Math.abs(ll.lng - lng) > 1e-9) {
				placeMarker(map, leaflet, lat, lng);
			}
		}
	});

	// Keep the radius circle in sync without changing zoom.
	$effect(() => {
		if (!map || !leaflet) return;
		const r = radius;
		const la = lat;
		const lo = lng;
		if (radiusCircle) {
			radiusCircle.remove();
			radiusCircle = null;
		}
		if (r !== null && r !== undefined && la !== null && lo !== null) {
			radiusCircle = leaflet.circle([la, lo], {
				radius: r,
				color: '#2563eb',
				weight: 2,
				fillColor: '#2563eb',
				fillOpacity: 0.12
			}).addTo(map);
		}
	});

	// Leaflet does not auto-recompute tile layout when its container is
	// resized (e.g. the Enlarge/Shrink toggle), which leaves gray blank
	// space. Invalidate after the new height is applied. Also re-run when
	// the pinned location changes (room selection) so tiles re-flow instead
	// of overlapping stale content.
	$effect(() => {
		// Touch these so this re-runs on every relevant change.
		void expanded;
		void height;
		if (!map) return;
		const invalidate = () => map.invalidateSize();
		const raf = requestAnimationFrame(() => setTimeout(invalidate, 0));
		return () => cancelAnimationFrame(raf);
	});
</script>


<div class="map-picker" style="height: {effectiveHeight};">
	<div class="map-search">
		<input
			class="map-search-input"
			type="search"
			placeholder="Search a place or address…"
			bind:value={searchQuery}
			oninput={scheduleSearch}
			onfocus={() => { if (results.length > 0) showResults = true; }}
			onblur={() => setTimeout(() => (showResults = false), 150)}
			aria-label="Search location"
		/>
		{#if searching}
			<span class="map-search-status" aria-live="polite">Searching…</span>
		{/if}
		{#if showResults && results.length > 0}
			<ul class="map-search-results" role="listbox">
				{#each results as r (r.label + r.lat + r.lng)}
					<li>
						<button
							type="button"
							class="map-search-result"
							onclick={() => selectResult(r)}
						>
							{r.label}
						</button>
					</li>
				{/each}
			</ul>
		{/if}
		{#if showResults && !searching && results.length === 0 && searchQuery.trim().length >= 3}
			<p class="map-search-status">No results found.</p>
		{/if}
	</div>
	<div class="map-toolbar">
		<button type="button" class="map-tool-btn" aria-label="Enlarge or shrink map" onclick={() => (expanded = !expanded)}>
			{expanded ? 'Shrink' : 'Enlarge'}
		</button>
		{#if allowLocate}
			<button type="button" class="map-tool-btn" aria-label="Use my location" disabled={locating} aria-busy={locating} onclick={() => void locate()}>
				{locating ? 'Getting your current location...' : 'Use my location'}
			</button>
		{/if}
		<button
			type="button"
			class="map-tool-btn"
			aria-label="Recenter map"
			onclick={() => {
				if (map && marker) {
					const pos = marker.getLatLng();
					map.setView(pos, Math.max(map.getZoom(), 16));
				}
			}}
		>
			Recenter
		</button>
		<button type="button" class="map-tool-btn" aria-label="Clear pin" onclick={clearPin}>
			Clear pin
		</button>
	</div>
	{#if gpsError}
		<p class="map-gps-error" role="alert">{gpsError}</p>
		<button type="button" class="map-tool-btn" disabled={locating} onclick={() => void locate()}>Retry</button>
	{/if}
	{#if gpsAccuracy !== null}
		<p class="map-gps-accuracy" class:good={gpsAccuracy <= 50} class:warn={gpsAccuracy > 50 && gpsAccuracy <= 100} class:poor={gpsAccuracy > 100} role="status" aria-live="polite">
			GPS accuracy: {Math.round(gpsAccuracy)} m
			{#if radius !== null}
				· radius {radius} m
			{/if}
		</p>
	{/if}
	{#if gpsAddress}
		<p class="map-gps-address" role="status">{gpsAddress}</p>
	{/if}
	{#if lat === null && lng === null}
		<div class="map-empty-hint" aria-hidden="true">Click the map or use your location to set coordinates</div>
	{/if}
	<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
	<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
	<div
		bind:this={container}
		class="map-container"
		tabindex="0"
		role="application"
		aria-label="Interactive map"
		onkeydown={(e) => {
			if (e.key === 'Enter' || e.key === ' ') {
				e.preventDefault();
				if (!map) return;
				const c = map.getCenter();
				if (!Number.isFinite(c?.lat) || !Number.isFinite(c?.lng)) return;
				lat = c.lat;
				lng = c.lng;
				placeMarker(map, leaflet, c.lat, c.lng);
				onChange(c.lat, c.lng);
			}
		}}
	></div>
</div>

<style>
	.map-picker {
		width: 100%;
		border: 1px solid var(--border, #ccc);
		border-radius: 8px;
		overflow: hidden;
		display: flex;
		flex-direction: column;
		/* Contain Leaflet's high internal z-indexes (panes up to 1000) inside
		   this widget so they cannot paint over the page or modals. */
		isolation: isolate;
	}
	.map-search {
		position: relative;
		padding: 6px;
		border-bottom: 1px solid var(--border, #ccc);
		background: var(--bg-card, #fff);
	}
	.map-search-input {
		width: 100%;
		padding: 6px 8px;
		border: 1px solid var(--border-strong, #aaa);
		border-radius: 6px;
		font-size: 0.875rem;
	}
	.map-search-status {
		display: block;
		margin-top: 4px;
		font-size: 0.75rem;
		color: var(--text-muted, #666);
	}
	.map-search-results {
		list-style: none;
		margin: 4px 0 0;
		padding: 0;
		max-height: 160px;
		overflow-y: auto;
		border: 1px solid var(--border, #ccc);
		border-radius: 6px;
		background: var(--bg-card, #fff);
	}
	.map-search-result {
		width: 100%;
		text-align: left;
		padding: 6px 8px;
		border: none;
		background: transparent;
		cursor: pointer;
		font-size: 0.8125rem;
	}
	.map-search-result:hover {
		background: var(--bg-hover, #eee);
	}
	.map-container {
		width: 100%;
		flex: 1 1 auto;
		min-height: 120px;
		/* Establish a stacking context for Leaflet's container; pane/control
		   z-indexes resolve here instead of leaking into the page. */
		position: relative;
		z-index: 0;
		isolation: isolate;
	}
	.map-toolbar {
		display: flex;
		gap: 6px;
		padding: 4px 6px;
		border-bottom: 1px solid var(--border, #ccc);
		background: var(--bg-card, #fff);
	}
	.map-tool-btn {
		padding: 4px 10px;
		border: 1px solid var(--border-strong, #aaa);
		border-radius: 6px;
		background: var(--bg-card, #fff);
		font-size: 0.75rem;
		font-weight: 600;
		cursor: pointer;
	}

	.map-gps-error {
		margin: 0.25rem 0.5rem;
		font-size: 0.75rem;
		color: var(--danger, #dc2626);
	}
	.map-gps-accuracy {
		margin: 0.25rem 0.5rem 0.5rem;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--text-muted, #666);
	}
	.map-gps-accuracy.good {
		color: var(--success, #16a34a);
	}
	.map-gps-accuracy.warn {
		color: var(--warning-text, #b45309);
	}
	.map-gps-accuracy.poor {
		color: var(--danger, #dc2626);
	}
	.map-gps-address {
		margin: 0 0.5rem 0.5rem;
		font-size: 0.75rem;
		color: var(--text-muted, #666);
	}
	.map-empty-hint {
		position: absolute;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		pointer-events: none;
		opacity: 0.7;
		font-size: 0.8125rem;
		color: var(--text-muted, #666);
		background: var(--bg-card, #fff);
		padding: 6px 10px;
		border-radius: 6px;
		z-index: 1;
	}
	.map-tool-btn:focus-visible,
	.map-container:focus-visible {
		outline: 2px solid var(--accent, #2563eb);
		outline-offset: 2px;
	}
</style>
