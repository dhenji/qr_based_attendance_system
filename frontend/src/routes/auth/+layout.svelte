<script lang="ts">
	import { Routes } from '$lib/shared/constants/routes';

	let { children } = $props();
</script>

<header class="nav">
	<a class="nav-brand" href={Routes.HOME}>
		<img src="/qr-attend-logo.svg" alt="Attendly logo" class="nav-logo" />
		<span class="nav-name">Attendly</span>
	</a>
	<nav class="nav-links" aria-label="Auth">
		<a class="nav-link" href={Routes.ABOUT}>About</a>
		<a class="nav-link" href={Routes.PRIVACY_POLICY}>Privacy Policy</a>
		<a class="nav-link" href={Routes.COOKIES}>Cookies</a>
	</nav>
</header>

{@render children()}

<style>
	:global(main.auth) {
		min-height: calc(100vh - 3.75rem);
		position: relative;
		isolation: isolate;
	}

	/* Blueprint atmosphere behind every auth card. The z-index -1 layers sit
	 * above main's own background (isolation creates the stacking context) and
	 * below the form wrapper, so the page background token still governs dark
	 * mode. Purely decorative. */
	:global(main.auth::before) {
		content: '';
		position: absolute;
		inset: 0;
		z-index: -1;
		pointer-events: none;
		background:
			radial-gradient(46rem 26rem at 12% -8%, color-mix(in srgb, var(--accent) 10%, transparent), transparent 65%),
			radial-gradient(38rem 26rem at 100% 108%, color-mix(in srgb, var(--brand) 9%, transparent), transparent 62%),
			linear-gradient(to right, color-mix(in srgb, var(--border) 55%, transparent) 1px, transparent 1px),
			linear-gradient(to bottom, color-mix(in srgb, var(--border) 55%, transparent) 1px, transparent 1px);
		background-size: auto, auto, 40px 40px, 40px 40px;
		mask-image: radial-gradient(ellipse 82% 82% at 50% 45%, #000, transparent 86%);
		-webkit-mask-image: radial-gradient(ellipse 82% 82% at 50% 45%, #000, transparent 86%);
		opacity: 0.85;
	}

	:global(main.auth::after) {
		content: '';
		position: absolute;
		top: 11%;
		right: 7%;
		width: 56px;
		height: 56px;
		z-index: -1;
		border-top: 2px solid color-mix(in srgb, var(--accent) 35%, transparent);
		border-right: 2px solid color-mix(in srgb, var(--accent) 35%, transparent);
		border-top-right-radius: 8px;
		opacity: 0.7;
		pointer-events: none;
	}

	:global(main.auth > .wrapper) {
		position: relative;
		z-index: 1;
		animation: auth-rise 0.45s cubic-bezier(0.22, 1, 0.36, 1) both;
	}

	@keyframes auth-rise {
		from {
			opacity: 0;
			transform: translateY(10px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.nav {
		position: sticky;
		top: 0;
		z-index: 20;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 0.75rem 1.5rem;
		background: color-mix(in srgb, var(--brand) 32%, #080f1a);
		border-bottom: 1px solid rgba(255, 255, 255, 0.08);
		box-shadow: 0 10px 30px rgba(2, 6, 23, 0.18);
		box-sizing: border-box;
		font-family: var(--font-ui);
	}

	.nav::after {
		content: '';
		position: absolute;
		left: 0;
		right: 0;
		bottom: -1px;
		height: 1px;
		background: linear-gradient(
			90deg,
			transparent,
			color-mix(in srgb, var(--accent) 55%, transparent),
			transparent
		);
		pointer-events: none;
	}

	.nav-brand {
		display: flex;
		align-items: center;
		gap: 0.625rem;
		text-decoration: none;
	}

	.nav-logo {
		width: 34px;
		height: 34px;
		display: block;
	}

	.nav-name {
		color: var(--on-brand);
		font-weight: 700;
		font-size: 1.125rem;
		letter-spacing: -0.02em;
		white-space: nowrap;
	}

	.nav-links {
		display: flex;
		align-items: center;
		gap: 0.125rem;
		flex-wrap: wrap;
		justify-content: flex-end;
	}

	.nav-link {
		padding: 0.5rem 0.875rem;
		border-radius: 8px;
		color: color-mix(in srgb, var(--on-brand) 70%, transparent);
		font-size: 0.875rem;
		font-weight: 500;
		text-decoration: none;
		white-space: nowrap;
		transition: background 0.15s ease, color 0.15s ease;
	}

	.nav-link:hover {
		background: rgba(255, 255, 255, 0.08);
		color: var(--on-brand);
	}

	@media (max-width: 640px) {
		.nav {
			padding: 0.625rem 1rem;
		}

		.nav-links {
			display: none;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		:global(main.auth > .wrapper) {
			animation: none;
		}
	}
</style>