<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { browser } from '$app/environment';
	import {
		authState,
		defaultRouteFor,
		doLogout,
		isStudent,
		restoreSession
	} from '$lib/features/auth/store.svelte';
	import NotificationBell, {
		type NotificationBellItem,
	} from '$lib/components/NotificationBell.svelte';
	import {
		getStudentUpdateCount,
		markStudentSeen,
		maybeNotify,
		POLL_INTERVAL_MS,
		truncateNotifPreview,
	} from '$lib/features/notifications/poll';
	import { listStudentExcuses } from '$lib/features/student/service';
	import { Routes } from '$lib/shared/constants/routes';
	import { trapFocus } from '$lib/shared/actions/focusTrap';

	let { children } = $props();

	// Student portal gate: anonymous visitors bounce to login (preserving the
	// clicked path in ?next=), signed-in non-students go to their own portal.
	// restoreSession() runs first so the topbar shows the signed-in name when
	// there is one. Children stay ungated until the check passes, so a
	// logged-out portal-card click never paints protected UI before redirect.
	let gate = $state<'checking' | 'allowed'>('checking');
	//
	// Excuse-decision bell: polls the student's own excuse list for newly
	// reviewed rows (fail-soft — mock/offline/401 hides the badge). Clicking
	// the bell opens the preview panel; the panel action marks them seen and
	// jumps to History.
	let notifCount = $state(0);
	let notifToast = $state<string | null>(null);
	let notifPreview = $state<NotificationBellItem[]>([]);
	let notifLoading = $state(false);
	let pollTimer: ReturnType<typeof setInterval> | null = null;
	let refreshing = false;
	let notifGeneration = 0;

	const refreshNotif = async () => {
		if (refreshing) return;
		refreshing = true;
		const generation = notifGeneration;
		try {
			const next = await getStudentUpdateCount();
			if (generation !== notifGeneration) return;
			if (next > notifCount) {
				const fresh = next - notifCount;
				notifToast = `${fresh} excuse decision${fresh === 1 ? '' : 's'} from your professor — tap the bell to review.`;
				maybeNotify('Excuse decision', 'Your professor reviewed your excuse request.');
			}
			notifCount = next;
		} finally {
			refreshing = false;
		}
	};

	const onNotifFocus = () => {
		if (document.visibilityState !== 'visible') return;
		void refreshNotif();
	};

	// Guard for the async attach below: restoreSession() is awaited, and
	// destroy can win that race. If it does, lifecycle teardown has already
	// run — attaching the interval/listeners afterwards would leak them until
	// the next full page unload.
	let notifAlive = true;

	onMount(async () => {
		const user = await restoreSession();
		if (!user) {
			await goto(`${Routes.LOGIN}?next=${encodeURIComponent(page.url.pathname)}`, {
				replaceState: true,
			});
		} else if (!isStudent()) {
			await goto(defaultRouteFor(user), { replaceState: true });
		} else {
			gate = 'allowed';
			void refreshNotif();
			if (!notifAlive) return;
			pollTimer = setInterval(() => {
				if (!document.hidden) void refreshNotif();
			}, POLL_INTERVAL_MS);
			window.addEventListener('focus', onNotifFocus);
			document.addEventListener('visibilitychange', onNotifFocus);
		}
	});

	onDestroy(() => {
		notifAlive = false;
		// onDestroy also runs during SSR teardown, where window/document do
		// not exist — and onMount (the only place listeners attach) never
		// runs on the server, so there is nothing to clean up there.
		if (!browser) return;
		if (pollTimer) {
			clearInterval(pollTimer);
			pollTimer = null;
		}
		window.removeEventListener('focus', onNotifFocus);
		document.removeEventListener('visibilitychange', onNotifFocus);
	});

	// Lazy preview for the bell panel: newest reviewed decisions first,
	// fail-soft (the badge count is the source of truth; a failed preview
	// just shows the empty state, never an error).
	const loadNotifPreview = async () => {
		notifLoading = true;
		try {
			const { items } = await listStudentExcuses({ page: 1, size: 10 });
			notifPreview = items
				.filter((row) => row.status !== 'pending')
				.sort((a, b) => (b.reviewedAt ?? '').localeCompare(a.reviewedAt ?? ''))
				.slice(0, 5)
				.map((row) => ({
					id: row.id,
					title: `Excuse ${row.status}`,
					sub: truncateNotifPreview(row.reason),
				}));
		} catch {
			notifPreview = [];
		} finally {
			notifLoading = false;
		}
	};

	const openNotifHistory = async () => {
		notifGeneration += 1;
		markStudentSeen();
		notifCount = 0;
		notifToast = null;
		await goto(Routes.HISTORY);
	};

	const navItems = [
		{ label: 'Dashboard', path: Routes.DASHBOARD, enabled: true, icon: 'dashboard' },
		{ label: 'Scan', path: Routes.SCAN, enabled: true, icon: 'scan' },
		{ label: 'History', path: Routes.HISTORY, enabled: true, icon: 'history' },
		{ label: 'Schedule', path: Routes.SCHEDULE, enabled: true, icon: 'schedule' },
		{ label: 'Profile', path: Routes.PROFILE, enabled: true, icon: 'profile' },
		{ label: 'Settings', path: Routes.SETTINGS, enabled: true, icon: 'settings' },
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
	let logoutOpen = $state(false);

	const isActive = (path: string) => page.url.pathname === path;

	// Greeting in the sidebar, from the session the layout just restored.
	const displayName = $derived(
		authState.user
			? [authState.user.firstName, authState.user.lastName].filter(Boolean).join(' ') ||
				authState.user.email
			: ''
	);

	const onConfirmLogout = async () => {
		logoutOpen = false;
		await doLogout();
	};
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

		{#if displayName}
			<span class="who" title={authState.user?.email ?? displayName}>{displayName}</span>
		{/if}

		<NotificationBell
			count={notifCount}
			buttonLabel={notifCount > 0 ? `${notifCount} new excuse decisions` : 'No new notifications'}
			panelTitle={notifCount > 0 ? `${notifCount} professor decision${notifCount === 1 ? '' : 's'} on your excuses` : 'Excuse decisions'}
			items={notifPreview}
			loading={notifLoading}
			emptyText="No professor decisions yet — you'll see them here."
			actionLabel="Review in History"
			onOpen={() => void loadNotifPreview()}
			onAction={() => void openNotifHistory()}
		/>

		<button class="icon-btn logout" type="button" data-testid="logout" onclick={() => (logoutOpen = true)} aria-label="Logout">
			<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
				<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
				<path d="m16 17 5-5-5-5" />
				<path d="M21 12H9" />
			</svg>
		</button>
	</header>

	{#if notifToast}
		<p class="toast" role="status">
			<span>{notifToast}</span>
			<button type="button" onclick={() => (notifToast = null)} aria-label="Dismiss notification">
				Dismiss
			</button>
		</p>
	{/if}

	<div class="body">
		<aside class="sidebar" class:collapsed>
			{#each navItems as item (item.label)}
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
			{/each}
		</aside>

		<main class="content">
			{#if gate === 'allowed'}
				{@render children()}
			{:else}
				<p class="gate-loading" role="status">Checking your session…</p>
			{/if}
		</main>
	</div>
</div>

<svelte:window onkeydown={(e) => { if (logoutOpen && e.key === 'Escape') logoutOpen = false; }} />

{#if logoutOpen}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="logout-dialog-title"
			tabindex={-1}
			use:trapFocus={{ onEscape: () => (logoutOpen = false) }}
		>
			<h2 id="logout-dialog-title" class="modal-title">Log out?</h2>
			<p class="modal-text">Are you sure you want to logout?</p>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (logoutOpen = false)}>Cancel</button>
				<button class="btn btn-danger" data-testid="confirm-logout" onclick={onConfirmLogout}>Logout</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.shell {
		min-height: 100vh;
		font-family: system-ui, sans-serif;
		background: var(--bg-page);
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
		background: var(--brand);
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
		color: var(--border-strong);
		cursor: pointer;
		flex-shrink: 0;
	}

	.menu-btn:hover,
	.icon-btn:hover {
		background: rgba(255, 255, 255, 0.1);
		color: var(--on-brand);
	}

	.toast {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin: 0.75rem 1.5rem 0;
		padding: 0.625rem 0.875rem;
		border-radius: 8px;
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		box-shadow: var(--shadow-sm);
		font-size: 0.875rem;
		color: var(--text-strong);
	}

	.toast button {
		border: 0;
		background: none;
		padding: 0;
		color: var(--accent);
		font: inherit;
		font-weight: 600;
		cursor: pointer;
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
		color: var(--on-brand);
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

	.who {
		font-size: 0.8125rem;
		font-weight: 600;
		color: rgba(255, 255, 255, 0.9);
		max-width: 12rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
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
		background: var(--bg-card);
		border-right: 1px solid var(--border);
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
		color: var(--text-secondary);
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

	.nav-link:hover {
		background: var(--bg-hover);
		transform: translateX(2px);
	}

	.nav-link.active {
		background: var(--accent);
		color: var(--on-brand);
		box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
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

	.gate-loading {
		color: var(--text-muted);
		font-size: 0.9375rem;
		margin: 0;
	}

	.modal-overlay {
		position: fixed;
		inset: 0;
		z-index: 100;
		background: var(--overlay);
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
	}

	.modal {
		width: 100%;
		max-width: 360px;
		background: var(--bg-card);
		border-radius: 12px;
		box-shadow: var(--shadow-lg);
		padding: 1.75rem 1.5rem;
		text-align: center;
		font-family: system-ui, sans-serif;
	}

	.modal-title {
		margin: 0 0 0.375rem;
		font-size: 1.25rem;
		font-weight: 700;
		color: var(--text);
	}

	.modal-text {
		margin: 0 0 1.5rem;
		font-size: 0.9375rem;
		color: #475569;
	}

	.modal-actions {
		display: flex;
		gap: 0.75rem;
		justify-content: center;
	}

	.btn {
		padding: 0.625rem 1.25rem;
		border: none;
		border-radius: 8px;
		font-size: 0.9375rem;
		font-weight: 600;
		font-family: system-ui, sans-serif;
		cursor: pointer;
		transition: background 0.15s ease, color 0.15s ease;
	}

	.btn-ghost {
		background: var(--bg-muted);
		color: var(--text-secondary);
	}

	.btn-ghost:hover {
		background: var(--border);
	}

	.btn-danger {
		background: var(--danger);
		color: var(--on-brand);
	}

	.btn-danger:hover {
		background: var(--danger-strong);
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