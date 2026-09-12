<script lang="ts">
	type IconName = 'camera' | 'qr' | 'shield' | 'offline';

	let { name, size = 24 }: { name: IconName; size?: number } = $props();
</script>

<svg
	width={size}
	height={size}
	viewBox="0 0 24 24"
	fill="none"
	stroke="currentColor"
	stroke-width="1.5"
	stroke-linecap="round"
	stroke-linejoin="round"
	aria-hidden="true"
>
	{#if name === 'camera'}
		<path d="M4 8h3l1.5-2h7L17 8h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1Z" />
		<circle cx="12" cy="13.5" r="3.5" />
	{:else if name === 'qr'}
		<rect x="4" y="4" width="6" height="6" rx="1" />
		<rect x="14" y="4" width="6" height="6" rx="1" />
		<rect x="4" y="14" width="6" height="6" rx="1" />
		<path d="M14 14h3v3h-3z" />
		<path d="M20 14v3M17 20h3" />
	{:else if name === 'shield'}
		<path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3Z" />
		<path d="m9 12 2 2 4-4" />
	{:else}
		<circle cx="12" cy="12" r="8.5" />
		<path d="M3.5 12h17" />
		<path d="M12 3.5c2.2 2.2 3.5 5.3 3.5 8.5s-1.3 6.3-3.5 8.5c-2.2-2.2-3.5-5.3-3.5-8.5s1.3-6.3 3.5-8.5Z" />
	{/if}
</svg>