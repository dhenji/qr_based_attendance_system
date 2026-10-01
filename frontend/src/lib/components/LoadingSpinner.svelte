<script lang="ts">
	interface Props {
		size?: 'sm' | 'md' | 'lg';
		message?: string;
		fullscreen?: boolean;
	}

	let { size = 'md', message = 'Loading...', fullscreen = false }: Props = $props();

	const sizeClasses = {
		sm: 'spinner-sm',
		md: 'spinner-md',
		lg: 'spinner-lg'
	};
</script>

{#if fullscreen}
	<div class="loading-overlay">
		<div class="loading-content">
			<div class="spinner {sizeClasses[size]}"></div>
			{#if message}
				<span class="loading-message">{message}</span>
			{/if}
		</div>
	</div>
{:else}
	<div class="loading-inline">
		<div class="spinner {sizeClasses[size]}"></div>
		{#if message}
			<span class="loading-message">{message}</span>
		{/if}
	</div>
{/if}

<style>
	.loading-overlay {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		background-color: rgba(255, 255, 255, 0.9);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
	}

	.loading-content {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 12px;
	}

	.loading-inline {
		display: flex;
		align-items: center;
		gap: 8px;
		justify-content: center;
		padding: 16px;
	}

	/* Base spinner styles.
	 * The leading edge is currentColor so the ring stays legible in every context:
	 * inside the navy .btn-primary submit buttons a hardcoded navy edge would be
	 * the same colour as the background and the rotation would be invisible, while
	 * on the light page backgrounds the inherited dark text colour reads correctly.
	 * The track is currentColor at low alpha for the same reason. */
	.spinner {
		/* Fallback first: engines without color-mix drop the two lines below. */
		border: 2px solid #e5e7eb;
		border-top-color: currentColor;
		border-color: color-mix(in srgb, currentColor 25%, transparent);
		border-top-color: currentColor;
		border-radius: 50%;
		/* Defaults so the ring can never collapse to a zero-size dot if a size
		 * class goes missing; the variants below still win on specificity. */
		width: 24px;
		height: 24px;
		animation: spin-animation 0.8s linear infinite;
		display: inline-block;
	}

	/* Size variants */
	.spinner.spinner-sm {
		width: 16px;
		height: 16px;
	}

	.spinner.spinner-md {
		width: 24px;
		height: 24px;
	}

	.spinner.spinner-lg {
		width: 32px;
		height: 32px;
		border-width: 3px;
	}

	.loading-message {
		color: #374151;
		font-size: 14px;
		font-weight: 500;
		margin-left: 8px;
	}

	/* Keyframe animation */
	@keyframes spin-animation {
		0% {
			transform: rotate(0deg);
		}
		100% {
			transform: rotate(360deg);
		}
	}

	/* Dark mode support */
	@media (prefers-color-scheme: dark) {
		.loading-overlay {
			background-color: rgba(17, 24, 39, 0.9);
		}

		.loading-message {
			color: #d1d5db;
		}
	}
</style>