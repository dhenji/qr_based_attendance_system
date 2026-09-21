<script lang="ts">
	import { page } from '$app/state';
	import { doLogout } from '$lib/features/auth/store.svelte';
	import { Routes } from '$lib/shared/constants/routes';

	let { children } = $props();

	const navItems = [
		{ label: 'Dashboard', path: Routes.DASHBOARD, enabled: true, icon: 'dashboard' },
		{ label: 'Scan', path: Routes.SCAN, enabled: true, icon: 'scan' },
		{ label: 'History', path: Routes.HISTORY, enabled: true, icon: 'history' },
		{ label: 'Schedule', path: Routes.SCHEDULE, enabled: false, icon: 'schedule' },
		{ label: 'Profile', path: Routes.PROFILE, enabled: false, icon: 'profile' },
		{ label: 'Settings', path: Routes.SETTINGS, enabled: false, icon: 'settings' },
	] as const;

	const iconPaths: Record<string, string> = {
		dashboard:
			'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
		scan: '<path d="M4 8h3l1.5-2h7L17 8h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1Z"/><circle cx="12" cy="13.5" r="3.5"/>',
		history: '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><path d="M12 8v4l3 2"/>',
		schedule:
			'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4"/><path d="M3 10h18"/>',
		profile: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
		settings:
			'<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3h.1a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5h.1a1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9v.1a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
	};

	let collapsed = $state(true);

	const isActive = (path: string) => page.url.pathname === path;
</script>

<div class="shell">
	<header class="topbar" data-navbar>
		<button
			class="menu-btn"
			aria-label="Toggle sidebar"
			aria-expanded={!collapsed}
			onclick={() => (collapsed = !collapsed)}
		>
			<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
				<path d="M4 6h16M4 12h16M4 18h16" />
			</svg>
		</button>

		<a class="brand" href={Routes.DASHBOARD}>
			<img src="/qr-attend-logo.svg" alt="Attendly logo" class="brand-logo" />
			<span class="brand-name" class:hidden={collapsed}>Attendly</span>
		</a>

		<div class="topbar-spacer"></div>

		<button class="icon-btn" aria-label="Notifications" title="No notifications yet">
			<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
				<path d="M6 9a6 6 0 0 1 12 0c0 4 2 5 2 6H4c0-1 2-2 2-6Z" />
				<path d="M10 19a2 2 0 0 0 4 0" />
			</svg>
		</button>

		<button class="icon-btn logout" data-testid="logout" onclick={doLogout} aria-label="Logout">
			<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
				<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
				<path d="m16 17 5-5-5-5" />
				<path d="M21 12H9" />
			</svg>
		</button>
	</header>

	<div class="body">
		<aside class="sidebar" class:collapsed>
			{#each navItems as item (item.label)}
				{#if item.enabled}
					<a
						class="nav-link"
						class:active={isActive(item.path)}
						href={item.path}
						title={item.label}
						aria-current={isActive(item.path) ? 'page' : undefined}
					>
						<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
							{@html iconPaths[item.icon]}
						</svg>
						<span class="nav-label" class:hidden={collapsed}>{item.label}</span>
					</a>
				{:else}
					<span class="nav-link disabled" title={`${item.label} (coming soon)`}>
						<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
							{@html iconPaths[item.icon]}
						</svg>
						<span class="nav-label" class:hidden={collapsed}>{item.label}</span>
					</span>
				{/if}
			{/each}
		</aside>

		<main class="content">
			{@render children()}
		</main>
	</div>
</div>

<style>
	.shell {
		min-height: 100vh;
		font-family: system-ui, sans-serif;
		background: #f8fafc;
		overflow-x: hidden;
	}

	.topbar {
		position: sticky;
		top: 0;
		z-index: 10;
		width: 100%;
		display: flex;
		align-items: center;
		gap: 0.875rem;
		padding: 0.75rem 1.5rem;
		background: #1e293b;
		box-shadow: 0 2px 12px rgba(15, 23, 42, 0.25);
	}

	.menu-btn,
	.icon-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 40px;
		height: 40px;
		border: none;
		border-radius: 8px;
		background: transparent;
		color: #cbd5e1;
		cursor: pointer;
		flex-shrink: 0;
	}

	.menu-btn:hover,
	.icon-btn:hover {
		background: rgba(255, 255, 255, 0.1);
		color: white;
	}

	.brand {
		display: flex;
		align-items: center;
		gap: 0.625rem;
		text-decoration: none;
		min-width: 0;
	}

	.brand-logo {
		width: 34px;
		height: 34px;
		display: block;
	}

	.brand-name {
		color: white;
		font-weight: 700;
		font-size: 1.125rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		min-width: 0;
	}

	.topbar-spacer {
		flex: 1;
	}

	.logout:hover {
		background: rgba(220, 38, 38, 0.25);
	}

	.body {
		display: flex;
		min-height: calc(100vh - 64px);
		min-width: 0;
	}

	.sidebar {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		width: 220px;
		flex-shrink: 0;
		background: white;
		border-right: 1px solid #e2e8f0;
		padding: 1rem 0.75rem;
		transition: width 0.2s ease;
	}

	.sidebar.collapsed {
		width: 72px;
		align-items: center;
	}

	.nav-link {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		width: 100%;
		color: #334155;
		text-decoration: none;
		padding: 0.625rem 0.75rem;
		border-radius: 8px;
		font-size: 0.9375rem;
		font-weight: 500;
		white-space: nowrap;
		overflow: hidden;
		transition: background 0.15s ease, color 0.15s ease, transform 0.15s ease;
	}

	.sidebar.collapsed .nav-link {
		justify-content: center;
		padding: 0.625rem;
	}

	.nav-link:hover:not(.disabled) {
		background: #f1f5f9;
		transform: translateX(2px);
	}

	.nav-link.active {
		background: #2563eb;
		color: white;
		box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
	}

	.nav-link.disabled {
		color: #94a3b8;
		cursor: not-allowed;
	}

	.nav-icon {
		width: 22px;
		height: 22px;
		flex-shrink: 0;
	}

	.nav-label {
		transition: opacity 0.15s ease;
	}

	.hidden {
		display: none;
	}

	.content {
		flex: 1 1 auto;
		min-width: 0;
		width: 100%;
		max-width: 1100px;
		margin-inline: auto;
		padding: 2rem 2rem 3rem;
	}

	@media (max-width: 640px) {
		.topbar {
			padding: 0.625rem 0.875rem;
			gap: 0.5rem;
		}

		.content {
			padding: 1.25rem 1.25rem 2.5rem;
		}
	}

	@media (max-width: 360px) {
		.brand-name {
			display: none;
		}
	}
</style>