<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { browser } from '$app/environment';
	import {
		authState,
		defaultRouteFor,
		doLogout,
		isAdmin,
		isSuperAdmin,
		restoreSession,
	} from '$lib/features/auth/store.svelte';
	import NotificationBell, {
		type NotificationBellItem,
	} from '$lib/components/NotificationBell.svelte';
	import Toast from '$lib/components/Toast.svelte';
	import { listAdminExcuses } from '$lib/features/admin/excuses/service';
	import { POLL_INTERVAL_MS, truncateNotifPreview } from '$lib/features/notifications/poll';
	import { Routes } from '$lib/shared/constants/routes';
	import { NAV_ICONS, type NavItem } from '$lib/shared/constants/navIcons';
	import { trapFocus } from '$lib/shared/actions/focusTrap';

	let { children } = $props();

	// Admin portal gate: anonymous visitors bounce to login (preserving the
	// clicked path in ?next=), signed-in non-admins go to their own portal.
	// restoreSession() runs first so the topbar shows the signed-in name when
	// there is one. Children stay ungated until the check passes, so a
	// logged-out portal-card click never paints protected UI before redirect.
	let gate = $state<'checking' | 'allowed'>('checking');

	// Pending-excuse bell (read-only workload view): polls the live pending
	// total (fail-soft — mock/offline/401 hides the badge). Clicking opens
	// the preview panel; the panel action jumps to the Excuses page.
	let pendingCount = $state(0);
	let notifPreview = $state<NotificationBellItem[]>([]);
	let notifLoading = $state(false);
	let notifToast = $state<string | null>(null);
	let pollTimer: ReturnType<typeof setInterval> | null = null;
	let refreshing = false;
	// False while the last poll failed. Without it, a transient error resets
	// pendingCount to 0 and the next successful poll would announce every
	// already-pending request as "new".
	let pollHealthy = true;

	const refreshNotif = async () => {
		if (refreshing) return;
		refreshing = true;
		try {
			const result = await listAdminExcuses({ status: 'pending', page: 1, size: 1 });
			const next = result.total ?? 0;
			if (pollHealthy && next > pendingCount) {
				const fresh = next - pendingCount;
				notifToast = `${fresh} new excuse request${fresh === 1 ? '' : 's'} awaiting review — tap the bell to open the queue.`;
			}
			pendingCount = next;
			pollHealthy = true;
		} catch {
			pendingCount = 0;
			pollHealthy = false;
		} finally {
			refreshing = false;
		}
	};

	const onNotifFocus = () => {
		if (document.visibilityState !== 'visible') return;
		void refreshNotif();
	};

	// Lazy preview for the bell panel: newest pending requests, fail-soft
	// (the badge count is the source of truth; a failed preview just shows
	// the empty state, never an error).
	const loadNotifPreview = async () => {
		notifLoading = true;
		try {
			const result = await listAdminExcuses({ status: 'pending', page: 1, size: 5 });
			notifPreview = (result.items ?? []).map((row) => ({
				id: row.id,
				title: `Excuse request #${row.id}`,
				sub: truncateNotifPreview(row.reason),
			}));
		} catch {
			notifPreview = [];
		} finally {
			notifLoading = false;
		}
	};

	const openNotifExcuses = () => void goto(Routes.ADMIN_EXCUSES);

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
		} else if (!isAdmin()) {
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

// MVP nav: Dashboard, Students, Professors, Programs, Courses,
// Offerings, Analytics, Audit Logs and Settings are live. Settings reads the
// real system backend (app_settings persists, backups download as encrypted
// archives). Users is super_admin-only (backend require_role(SUPER_ADMIN)) and
// stays hidden for plain admins.
	const baseNavItems: NavItem[] = [
		{ label: 'Dashboard', path: Routes.ADMIN_DASHBOARD, enabled: true, icon: 'dashboard' },
		{ label: 'Setup Wizard', path: Routes.ADMIN_SETUP_WIZARD, enabled: true, icon: 'wizard' },
		{ label: 'Students', path: Routes.ADMIN_STUDENTS, enabled: true, icon: 'students' },
		{ label: 'Professors', path: Routes.ADMIN_PROFESSORS, enabled: true, icon: 'professors' },
		{ label: 'Programs', path: Routes.ADMIN_PROGRAMS, enabled: true, icon: 'programs' },
		{ label: 'Courses', path: Routes.ADMIN_COURSES, enabled: true, icon: 'courses' },
		{ label: 'Offerings', path: Routes.ADMIN_OFFERINGS, enabled: true, icon: 'offerings' },
		{ label: 'Analytics', path: Routes.ADMIN_ANALYTICS, enabled: true, icon: 'reports' },
		{ label: 'Attendance Review', path: Routes.ADMIN_ATTENDANCE, enabled: true, icon: 'review' },
		{ label: 'Excuses', path: Routes.ADMIN_EXCUSES, enabled: true, icon: 'excuses' },
		{ label: 'Audit Logs', path: Routes.ADMIN_AUDIT_LOGS, enabled: true, icon: 'audit' },
		{ label: 'Settings', path: Routes.ADMIN_SYSTEM_SETTINGS, enabled: true, icon: 'settings' },
		{ label: 'Profile', path: Routes.ADMIN_PROFILE, enabled: true, icon: 'profile' },
	];

	const navItems = $derived([
		...baseNavItems,
		...(isSuperAdmin()
			? [{ label: 'Users', path: Routes.ADMIN_USERS, enabled: true, icon: 'users' } satisfies NavItem]
			: []),
	]);

	let collapsed = $state(true);
	let logoutOpen = $state(false);

	const isActive = (path: string) => page.url.pathname === path || page.url.pathname.startsWith(`${path}/`);

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

		<a class="brand" href={Routes.ADMIN_DASHBOARD}>
			<img src="/qr-attend-logo.svg" alt="Attendly logo" class="brand-logo" />
			<span class="brand-name" class:hidden={collapsed}>Attendly · Admin</span>
		</a>

		<div class="topbar-spacer"></div>

		{#if displayName}
			<span class="who" title={authState.user?.email ?? displayName}>{displayName}</span>
		{/if}

		<NotificationBell
			count={pendingCount}
			buttonLabel={pendingCount > 0 ? `${pendingCount} pending excuse requests` : 'No new notifications'}
			panelTitle={pendingCount > 0 ? `${pendingCount} excuse request${pendingCount === 1 ? '' : 's'} awaiting review` : 'Excuse requests'}
			items={notifPreview}
			loading={notifLoading}
			emptyText="You're caught up — no pending excuse requests."
			actionLabel="Open Excuses"
			onOpen={() => void loadNotifPreview()}
			onAction={openNotifExcuses}
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
		<Toast message={notifToast} onDismiss={() => (notifToast = null)} />
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
						{@html NAV_ICONS[item.icon]}
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
		box-shadow: var(--shadow-sm);
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
		box-shadow: var(--shadow-sm);
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
		color: var(--text-secondary);
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
