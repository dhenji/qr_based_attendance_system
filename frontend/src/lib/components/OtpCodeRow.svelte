<script lang="ts">
	// OtpCodeRow.svelte
	// Single row: code-validity countdown · separator · resend button with cooldown.
	// Used by login, register, and forgot-password so the three flows are
	// visually and behaviourally identical.

	import OtpCountdown from './OtpCountdown.svelte';
	import { formatClock, type OtpWindow } from '$lib/features/auth/store.svelte';

	let { win, busy = false, onresend }: { win: OtpWindow; busy?: boolean; onresend: () => void } = $props();
</script>

<div class="otp-code-row">
	<OtpCountdown remaining={win.remaining} />
	<span class="sep">·</span>
	<button
		class="resend-btn"
		disabled={win.resendIn > 0 || busy}
		onclick={onresend}
	>
		{#if busy}
			Sending…
		{:else if win.resendIn > 0}
			Resend in {formatClock(win.resendIn)}
		{:else}
			Resend code
		{/if}
	</button>
</div>

<style>
	.otp-code-row {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.375rem;
		color: var(--text-muted);
		font-size: 0.8125rem;
		margin: 0.5rem 0 1.25rem;
	}

	.sep {
		color: var(--border-strong);
	}

	.resend-btn {
		background: none;
		border: none;
		cursor: pointer;
		color: var(--accent);
		font-size: 0.8125rem;
		font-weight: 600;
		font-family: inherit;
		padding: 0;
	}

	.resend-btn:hover:not(:disabled) {
		text-decoration: underline;
	}

	.resend-btn:disabled {
		color: var(--text-muted);
		cursor: not-allowed;
		text-decoration: none;
	}
</style>