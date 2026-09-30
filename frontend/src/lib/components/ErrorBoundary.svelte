<script lang="ts">
	import { createEventDispatcher } from 'svelte';

	interface Props {
		error?: Error | string | null;
		showDetails?: boolean;
		fallback?: string;
		retryButton?: boolean;
		children?: import('svelte').Snippet;
	}

	let {
		error = null,
		showDetails = false,
		fallback = 'Something went wrong. Please try again.',
		retryButton = true,
		children
	}: Props = $props();

	const dispatch = createEventDispatcher();

	function handleRetry() {
		dispatch('retry');
		error = null;
	}

	function getErrorMessage(err: Error | string | null): string {
		if (!err) return fallback;
		if (typeof err === 'string') return err;
		return err.message || fallback;
	}

	function getErrorDetails(err: Error | string | null): string {
		if (!err || typeof err === 'string') return '';
		return err.stack || '';
	}
</script>

{#if error}
	<div class="error-boundary">
		<div class="error-icon">
			!
		</div>

		<div class="error-content">
			<h3 class="error-title">Oops! Something went wrong</h3>
			<p class="error-message">{getErrorMessage(error)}</p>

			{#if showDetails && getErrorDetails(error)}
				<details class="error-details">
					<summary>Technical details</summary>
					<pre class="error-stack">{getErrorDetails(error)}</pre>
				</details>
			{/if}

			<div class="error-actions">
				{#if retryButton}
					<button class="retry-button" onclick={handleRetry}>
						Try Again
					</button>
				{/if}

				<button
					class="reload-button"
					onclick={() => window.location.reload()}
				>
					Reload Page
				</button>
			</div>
		</div>
	</div>
{:else}
	{@render children?.()}
{/if}

<style>
	.error-boundary {
		background: white;
		border: 1px solid #fca5a5;
		border-radius: 12px;
		padding: 2.5rem 2rem;
		margin: 1rem 0;
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
		position: relative;
		overflow: hidden;
	}

	.error-boundary::before {
		content: '';
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		height: 4px;
		background: linear-gradient(90deg, #dc2626, #ef4444);
	}

	.error-icon {
		width: 56px;
		height: 56px;
		background: linear-gradient(135deg, #fee2e2, #fecaca);
		color: #dc2626;
		border-radius: 12px;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1.5rem;
		font-weight: 700;
		margin: 0 auto 1.5rem;
		border: 2px solid #fca5a5;
		box-shadow: 0 2px 8px rgba(220, 38, 38, 0.1);
	}

	.error-content {
		max-width: 500px;
		text-align: center;
	}

	.error-title {
		font-size: 1.375rem;
		font-weight: 700;
		color: #1e3a5f;
		margin: 0 0 0.75rem 0;
		letter-spacing: -0.025em;
	}

	.error-message {
		color: #6b7280;
		margin: 0 0 1.5rem 0;
		line-height: 1.6;
		font-size: 0.9375rem;
	}

	.error-details {
		margin: 1.5rem 0;
		text-align: left;
		background: #f9fafb;
		border-radius: 8px;
		border: 1px solid #e5e7eb;
		overflow: hidden;
	}

	.error-details summary {
		cursor: pointer;
		color: #1e3a5f;
		font-weight: 600;
		padding: 1rem;
		background: #f3f4f6;
		border-bottom: 1px solid #e5e7eb;
		transition: background-color 0.15s;
	}

	.error-details summary:hover {
		background: #e5e7eb;
	}

	.error-stack {
		background: #ffffff;
		border: none;
		border-radius: 0;
		padding: 1rem;
		font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
		font-size: 0.8125rem;
		color: #374151;
		overflow-x: auto;
		white-space: pre-wrap;
		word-break: break-word;
		line-height: 1.4;
		margin: 0;
	}

	.error-actions {
		display: flex;
		gap: 0.75rem;
		justify-content: center;
		margin-top: 2rem;
		flex-wrap: wrap;
	}

	.retry-button,
	.reload-button {
		padding: 0.75rem 1.5rem;
		border-radius: 8px;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.15s;
		border: none;
		font-size: 0.9375rem;
		font-family: inherit;
		position: relative;
		overflow: hidden;
	}

	.retry-button {
		background: #1e3a5f;
		color: white;
		box-shadow: 0 2px 4px rgba(30, 58, 95, 0.2);
	}

	.retry-button:hover {
		background: #16324f;
		box-shadow: 0 4px 8px rgba(30, 58, 95, 0.3);
		transform: translateY(-1px);
	}

	.retry-button:active {
		transform: translateY(0);
	}

	.retry-button:disabled {
		opacity: 0.6;
		cursor: not-allowed;
		transform: none;
	}

	.reload-button {
		background: white;
		color: #6b7280;
		border: 1.5px solid #d1d5db;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
	}

	.reload-button:hover {
		background: #f9fafb;
		border-color: #9ca3af;
		color: #374151;
		box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
		transform: translateY(-1px);
	}

	.reload-button:active {
		transform: translateY(0);
	}

	/* Dark mode support */
	@media (prefers-color-scheme: dark) {
		.error-boundary {
			background-color: #450a0a;
			border-color: #7f1d1d;
		}

		.error-title {
			color: #f87171;
		}

		.error-message {
			color: #fca5a5;
		}

		.error-details summary {
			color: #f87171;
		}

		.error-details summary:hover {
			color: #fca5a5;
		}

		.error-stack {
			background-color: #1f2937;
			border-color: #374151;
			color: #d1d5db;
		}

		.retry-button {
			background-color: #dc2626;
		}

		.retry-button:hover {
			background-color: #ef4444;
		}

		.reload-button {
			background-color: #374151;
			color: #d1d5db;
			border-color: #6b7280;
		}

		.reload-button:hover {
			background-color: #4b5563;
			border-color: #9ca3af;
		}
	}
</style>