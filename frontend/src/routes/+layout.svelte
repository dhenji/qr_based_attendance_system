<script lang="ts">
	import InstallPrompt from '$lib/components/InstallPrompt.svelte';

	let { children } = $props();
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
