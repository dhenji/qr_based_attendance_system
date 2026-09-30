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

	/* Base spinner styles */
	.spinner {
		border: 2px solid #e5e7eb;
		border-top: 2px solid #1e3a5f;
		border-radius: 50%;
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

		.spinner {
			border-color: #374151;
			border-top-color: #60a5fa;
		}
	}
</style>