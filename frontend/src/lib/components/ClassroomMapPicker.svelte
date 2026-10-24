<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { searchLocation, type LocationSearchResult } from '$lib/shared/utils/geo';

	interface Props {
		lat: number | null;
		lng: number | null;
		onChange: (lat: number, lng: number) => void;
		onClear?: () => void;
		height?: string;
	}

	let { lat = $bindable(null), lng = $bindable(null), onChange, onClear, height = '380px' }: Props = $props();

	let container: HTMLDivElement | null = null;
	let map: any = null;
	let marker: any = null;
	let leaflet: any = null;

	let searchQuery = $state('');
	let results = $state<LocationSearchResult[]>([]);
	let searching = $state(false);
	let showResults = $state(false);
	let searchTimer: ReturnType<typeof setTimeout> | null = null;
	let expanded = $state(false);
	const effectiveHeight = $derived(expanded ? '70vh' : height);

	const DEFAULT_CENTER: [number, number] = [14.5995, 120.9842];
	const DEFAULT_ZOOM = 16;

	function placeMarker(m: any, L: any, latitude: number, longitude: number) {
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
		searchQuery = '';
		onClear?.();
	}

	onMount(async () => {
		if (!container) return;
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

		const center: [number, number] =
			lat !== null && lng !== null ? [lat, lng] : DEFAULT_CENTER;
		const zoom = lat !== null && lng !== null ? DEFAULT_ZOOM : 4;

		map = L.map(container).setView(center, zoom);
		L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
			attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
			maxZoom: 19,
		}).addTo(map);

		if (lat !== null && lng !== null) placeMarker(map, L, lat, lng);

		map.on('click', (e: any) => {
			const { lat: la, lng: lo } = e.latlng;
			lat = la;
			lng = lo;
			placeMarker(map, L, la, lo);
			onChange(la, lo);
		});
	});

	onDestroy(() => {
		if (map) {
			map.remove();
			map = null;
		}
	});

	// React to external lat/lng changes (e.g. "use my location").
	$effect(() => {
		if (map && leaflet && lat !== null && lng !== null) {
			// Only re-place if marker missing or position differs notably
			const ll = marker?.getLatLng?.();
			if (!ll || Math.abs(ll.lat - lat) > 1e-9 || Math.abs(ll.lng - lng) > 1e-9) {
				placeMarker(map, leaflet, lat, lng);
			}
		}
	});

	// Leaflet does not auto-recompute tile layout when its container is
	// resized (e.g. the Enlarge/Shrink toggle), which leaves gray blank
	// space. Invalidate after the new height is applied.
	$effect(() => {
		// Touch expanded so this re-runs on every toggle.
		void expanded;
		void height;
		if (!map) return;
		const invalidate = () => map.invalidateSize();
		const raf = requestAnimationFrame(() => setTimeout(invalidate, 0));
		return () => cancelAnimationFrame(raf);
	});
</script>

<svelte:head>
	<link
		rel="stylesheet"
		href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
	/>
</svelte:head>

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
		<button type="button" class="map-tool-btn" onclick={() => (expanded = !expanded)}>
			{expanded ? 'Shrink' : 'Enlarge'}
		</button>
		<button
			type="button"
			class="map-tool-btn"
			onclick={() => {
				if (map && marker) {
					const pos = marker.getLatLng();
					map.setView(pos, Math.max(map.getZoom(), 16));
				}
			}}
		>
			Recenter
		</button>
		<button type="button" class="map-tool-btn" onclick={clearPin}>
			Clear pin
		</button>
	</div>
	<div bind:this={container} class="map-container"></div>
</div>

<style>
	.map-picker {
		width: 100%;
		border: 1px solid var(--border, #ccc);
		border-radius: 8px;
		overflow: hidden;
		display: flex;
		flex-direction: column;
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
</style>
