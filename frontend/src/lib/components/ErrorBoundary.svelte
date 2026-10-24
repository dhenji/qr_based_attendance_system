<script lang="ts">
	// ErrorBoundary — renders a recoverable error state for an error the caller
	// has ALREADY caught and passed in.
	//
	// It is NOT a render-error boundary: there is no try/catch here, so an
	// exception thrown while rendering a child cannot be caught by this
	// component. That job belongs to SvelteKit's `+error.svelte` (routes/
	// +error.svelte), which wraps the whole route tree. This component is the
	// presentational half: message, optional stack, and the recovery actions.
	//
	// `onretry` is a callback prop (runes idiom) rather than a dispatched
	// event. Dismissal is local state, never a mutation of the `error` prop —
	// writing to a `$props()` binding throws ownership_invalid_mutation in
	// Svelte 5, which is why the parent owns clearing/keeping the error.
	// Accepts a real Error, the loosely-shaped `App.Error` that SvelteKit's
	// `page.error` carries (message only, no name/stack), or a plain string.
	type ErrorLike = Error | { message?: string; stack?: string } | string | null;

	interface Props {
		error?: ErrorLike;
		showDetails?: boolean;
		fallback?: string;
		retryButton?: boolean;
		// Called after the panel hides. The parent decides what "retry" means
		// (clear the error, refetch, or reload).
		onretry?: () => void;
		children?: import('svelte').Snippet;
	}

	let {
		error = null,
		showDetails = false,
		fallback = 'Something went wrong. Please try again.',
		retryButton = true,
		onretry,
		children
	}: Props = $props();

	let dismissed = $state(false);
	let lastError = $state<ErrorLike>(null);

	// A *different* error re-shows the panel, so a failed refetch that returns
	// a fresh error is not swallowed by an earlier dismissal.
	$effect(() => {
		if (error && error !== lastError) {
			lastError = error;
			dismissed = false;
		}
	});

	function handleRetry() {
		dismissed = true;
		onretry?.();
	}

	function getErrorMessage(err: ErrorLike): string {
		if (!err) return fallback;
		if (typeof err === 'string') return err;
		return err.message || fallback;
	}

	function getErrorDetails(err: ErrorLike): string {
		if (!err || typeof err === 'string') return '';
		return err.stack ?? '';
	}
</script>

{#if error && !dismissed}
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
		background: var(--bg-card);
		border: 1px solid var(--danger-strong);
		border-radius: 12px;
		padding: 2.5rem 2rem;
		margin: 1rem 0;
		box-shadow: var(--shadow-sm);
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
		background: linear-gradient(90deg, var(--danger), var(--danger));
	}

	.error-icon {
		width: 56px;
		height: 56px;
		background: linear-gradient(135deg, var(--danger-bg), var(--danger-bg));
		color: var(--danger);
		border-radius: 12px;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1.5rem;
		font-weight: 700;
		margin: 0 auto 1.5rem;
		border: 2px solid var(--danger-strong);
		box-shadow: var(--shadow-sm);
	}

	.error-content {
		max-width: 500px;
		text-align: center;
	}

	.error-title {
		font-size: 1.375rem;
		font-weight: 700;
		color: var(--brand);
		margin: 0 0 0.75rem 0;
		letter-spacing: -0.025em;
	}

	.error-message {
		color: var(--text-muted);
		margin: 0 0 1.5rem 0;
		line-height: 1.6;
		font-size: 0.9375rem;
	}

	.error-details {
		margin: 1.5rem 0;
		text-align: left;
		background: var(--bg-muted);
		border-radius: 8px;
		border: 1px solid var(--border);
		overflow: hidden;
	}

	.error-details summary {
		cursor: pointer;
		color: var(--brand);
		font-weight: 600;
		padding: 1rem;
		background: var(--bg-muted);
		border-bottom: 1px solid var(--border);
		transition: background-color 0.15s;
	}

	.error-details summary:hover {
		background: var(--border);
	}

	.error-stack {
		background: var(--bg-card);
		border: none;
		border-radius: 0;
		padding: 1rem;
		font-family: var(--font-data);
		font-size: 0.8125rem;
		color: var(--text-secondary);
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
		background: var(--brand);
		color: var(--on-brand);
		box-shadow: var(--shadow-sm);
	}

	.retry-button:hover {
		background: var(--brand-hover);
		box-shadow: var(--shadow-sm);
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
		background: var(--bg-card);
		color: var(--text-muted);
		border: 1.5px solid var(--border-strong);
		box-shadow: var(--shadow-sm);
	}

	.reload-button:hover {
		background: var(--bg-muted);
		border-color: var(--text-muted);
		color: var(--text-secondary);
		box-shadow: var(--shadow-sm);
		transform: translateY(-1px);
	}

	.reload-button:active {
		transform: translateY(0);
	}

</style>