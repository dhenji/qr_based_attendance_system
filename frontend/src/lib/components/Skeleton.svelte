<script lang="ts">
	// Skeleton
	// Shimmering placeholder primitive. Composed by SkeletonTable /
	// SkeletonCards, and usable directly for detail-page blocks.
	// Decorative by design: aria-hidden, because the surrounding page keeps a
	// `role="status"` "Loading…" text for screen readers. The shimmer stops
	// under prefers-reduced-motion, falling back to a flat muted block.
	interface Props {
		variant?: 'line' | 'block' | 'circle';
		/** Any CSS length, or a number interpreted as px. Defaults per variant. */
		width?: string | number;
		height?: string | number;
		class?: string;
	}

	let { variant = 'line', width, height, class: className = '' }: Props = $props();

	const cssSize = (v: string | number | undefined) =>
		typeof v === 'number' ? `${v}px` : v;

	const style = $derived(
		[
			width !== undefined ? `width: ${cssSize(width)}` : '',
			height !== undefined ? `height: ${cssSize(height)}` : '',
		]
			.filter(Boolean)
			.join('; ')
	);
</script>

<span class="skeleton skeleton-{variant} {className}" style={style} aria-hidden="true"></span>

<style>
	.skeleton {
		display: block;
		flex-shrink: 0;
		width: 100%;
		border-radius: 6px;
		/* Theme tokens keep the shimmer legible in light and dark. */
		background: linear-gradient(
			90deg,
			var(--bg-muted) 25%,
			var(--border) 37%,
			var(--bg-muted) 63%
		);
		background-size: 400% 100%;
		animation: skeleton-shimmer 1.4s ease infinite;
	}

	.skeleton-line {
		height: 0.85rem;
	}

	.skeleton-block {
		height: 4rem;
		border-radius: 8px;
	}

	.skeleton-circle {
		width: 2.5rem;
		height: 2.5rem;
		border-radius: 50%;
		aspect-ratio: 1;
	}

	@keyframes skeleton-shimmer {
		0% {
			background-position: 100% 50%;
		}
		100% {
			background-position: 0 50%;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.skeleton {
			animation: none;
			background: var(--bg-muted);
		}
	}
</style>
