<script lang="ts">
	// AppIcon
	// Inline SVG icon set (Lucide-style paths): camera, QR, shield, offline,
	// users, chart, plus, file, chevron, lock, pin, check, alert.
	// Renders whichever icon is named by the `name` prop at the given `size`.
	type IconName =
		| 'camera'
		| 'qr'
		| 'shield'
		| 'offline'
		| 'users'
		| 'chart'
		| 'plus'
		| 'file'
		| 'chevron'
		| 'lock'
		| 'pin'
		| 'check'
		| 'alert';

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
	<!-- Icon paths: the leading branches match their name explicitly; -->
	<!-- the trailing {:else} branch is the default 'offline' icon. -->
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
	{:else if name === 'users'}
		<circle cx="9" cy="8" r="3.5" />
		<path d="M2.5 20c0-3.6 2.9-5.5 6.5-5.5s6.5 1.9 6.5 5.5" />
		<path d="M16.5 5.2a3.5 3.5 0 0 1 0 5.6" />
		<path d="M18 14.8c2.1.7 3.5 2.4 3.5 5.2" />
	{:else if name === 'chart'}
		<path d="M4 20h16" />
		<path d="M7 20v-6" />
		<path d="M12 20V6" />
		<path d="M17 20v-9" />
	{:else if name === 'plus'}
		<path d="M12 5v14M5 12h14" />
	{:else if name === 'file'}
		<path d="M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7l-4-4Z" />
		<path d="M14 3v4h4" />
		<path d="M9 13h6M9 17h4" />
	{:else if name === 'chevron'}
		<path d="m6 9 6 6 6-6" />
	{:else if name === 'lock'}
		<rect x="4" y="10" width="16" height="11" rx="2" />
		<path d="M8 10V7a4 4 0 0 1 8 0v3" />
	{:else if name === 'pin'}
		<path d="M12 21s7-5.7 7-11a7 7 0 0 0-14 0c0 5.3 7 11 7 11Z" />
		<circle cx="12" cy="10" r="2.5" />
	{:else if name === 'check'}
		<path d="m5 13 4.5 4.5L19 7" />
	{:else if name === 'alert'}
		<path d="M12 4 2.5 20.5h19L12 4Z" />
		<path d="M12 10v4" />
		<path d="M12 17.5h.01" />
	{:else}
		<circle cx="12" cy="12" r="8.5" />
		<path d="M3.5 12h17" />
		<path d="M12 3.5c2.2 2.2 3.5 5.3 3.5 8.5s-1.3 6.3-3.5 8.5c-2.2-2.2-3.5-5.3-3.5-8.5s1.3-6.3 3.5-8.5Z" />
	{/if}
</svg>