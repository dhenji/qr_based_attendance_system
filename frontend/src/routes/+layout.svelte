<script lang="ts">
	import { onMount } from 'svelte';
	import InstallPrompt from '$lib/components/InstallPrompt.svelte';
	import '$lib/shared/theme.css';
	import { initTheme } from '$lib/features/settings/theme';

	let { children } = $props();

	onMount(() => {
		initTheme();
	});
</script>

<svelte:head>
	<link rel="icon" type="image/svg+xml" href="/qr-attend-logo.svg" />
</svelte:head>

{@render children()}
<InstallPrompt />

<style>
	:global(html) {
		box-sizing: border-box;
		overflow-x: hidden;
	}
	:global(*, *::before, *::after) {
		box-sizing: inherit;
	}
	:global(body) {
		margin: 0;
	}
</style>
