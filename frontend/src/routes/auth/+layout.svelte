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
		background: var(--brand);
		box-shadow: 0 2px 12px rgba(15, 23, 42, 0.25);
		box-sizing: border-box;
		font-family: 'DM Sans', system-ui, sans-serif;
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
		white-space: nowrap;
	}

	.nav-links {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		flex-wrap: wrap;
		justify-content: flex-end;
	}

	.nav-link {
		padding: 0.5rem 0.875rem;
		border-radius: 8px;
		color: var(--border);
		font-size: 0.9375rem;
		font-weight: 500;
		text-decoration: none;
		white-space: nowrap;
		transition: background 0.15s ease, color 0.15s ease;
	}

	.nav-link:hover {
		background: rgba(255, 255, 255, 0.1);
		color: var(--on-brand);
	}
</style>