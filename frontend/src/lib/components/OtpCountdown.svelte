<script lang="ts">
	// Renders the "Expires in MM:SS" line and flips to the expired style once
	// the count hits zero. Driven by the parent's own countdown so the timer
	// stays in sync whenever the parent resets it (e.g. on resend).
	import { formatClock } from '$lib/features/auth/store.svelte';

	let { remaining = 300 } = $props<{ remaining?: number }>();

	const expired = $derived(remaining <= 0);
</script>

<span class="expiry" class:expired>Expires in <strong>{formatClock(remaining)}</strong></span>

<style>
	.expiry {
		color: var(--text-muted);
		font-size: 0.8125rem;
	}

	.expiry strong {
		color: var(--brand);
	}

	.expiry.expired strong {
		color: var(--danger);
	}
</style>
