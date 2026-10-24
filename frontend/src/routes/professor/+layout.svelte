<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { browser } from '$app/environment';
	import {
		authState,
		defaultRouteFor,
		doLogout,
		isProfessor,
		restoreSession
	} from '$lib/features/auth/store.svelte';
	import NotificationBell, {
		type NotificationBellItem,
	} from '$lib/components/NotificationBell.svelte';
	import Toast from '$lib/components/Toast.svelte';
	import {
		getProfessorPendingCount,
		maybeNotify,
		POLL_INTERVAL_MS,
		truncateNotifPreview,
	} from '$lib/features/notifications/poll';
	import { listExcuseRequests } from '$lib/features/excuse/service';
	import { Routes } from '$lib/shared/constants/routes';
	import { NAV_ICONS, type NavItem } from '$lib/shared/constants/navIcons';
	import { trapFocus } from '$lib/shared/actions/focusTrap';

	let { children } = $props();

	// Professor portal gate: anonymous visitors bounce to login (preserving the
	// clicked path in ?next=), signed-in non-professors go to their own portal.
	// restoreSession() runs first so the topbar shows the signed-in name when
	// there is one. Children stay ungated until the check passes, so a
	// logged-out portal-card click never paints protected UI before redirect.
	let gate = $state<'checking' | 'allowed'>('checking');
	//
	// Pending-excuse bell: polls the live pending-queue total (fail-soft —
	// mock/offline/401 hides the badge). Clicking opens the preview panel;
	// the panel action jumps to the queue.
	let pendingCount = $state(0);
	let notifToast = $state<string | null>(null);
	let notifPreview = $state<NotificationBellItem[]>([]);
	let notifLoading = $state(false);
	let pollTimer: ReturnType<typeof setInterval> | null = null;
	let refreshing = false;

	const refreshNotif = async () => {
		if (refreshing) return;
		refreshing = true;
		try {
			const next = await getProfessorPendingCount();
			if (next > pendingCount) {
				const fresh = next - pendingCount;
				notifToast = `${fresh} new excuse request${fresh === 1 ? '' : 's'} awaiting review — tap the bell to open the queue.`;
				maybeNotify('Excuse requests', 'New student excuse requests are awaiting review.');
			}
			pendingCount = next;
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
			const result = await listExcuseRequests({ status: 'pending', page: 1, size: 5 });
			notifPreview = result.items.map((row) => ({
				id: row.id,
				title: `${row.studentName} — ${row.courseCode}`,
				sub: truncateNotifPreview(row.reason),
			}));
		} catch {
			notifPreview = [];
		} finally {
			notifLoading = false;
		}
	};

	const openNotifQueue = () => void goto(Routes.PROFESSOR_EXCUSE_REQUESTS);

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
		} else if (!isProfessor()) {
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

	// Professor portal nav: Dashboard, My Courses, Sessions, History,
	// Attendance, Excuses, Reports, Profile, and Settings are all live.
	const navItems: NavItem[] = [
		{ label: 'Dashboard', path: Routes.PROFESSOR_DASHBOARD, enabled: true, icon: 'dashboard' },
		{ label: 'My Courses', path: Routes.PROFESSOR_COURSES, enabled: true, icon: 'courses' },
		{ label: 'Sessions', path: Routes.PROFESSOR_SESSIONS, enabled: true, icon: 'sessions' },
		{ label: 'History', path: Routes.PROFESSOR_SESSIONS_HISTORY, enabled: true, icon: 'history' },
		{ label: 'Attendance', path: Routes.PROFESSOR_ATTENDANCE, enabled: true, icon: 'attendance' },
		{ label: 'Excuses', path: Routes.PROFESSOR_EXCUSE_REQUESTS, enabled: true, icon: 'excuses' },
		{ label: 'Reports', path: Routes.PROFESSOR_REPORTS, enabled: true, icon: 'reports' },
		{ label: 'Profile', path: Routes.PROFESSOR_PROFILE, enabled: true, icon: 'profile' },
		{ label: 'Settings', path: Routes.PROFESSOR_SETTINGS, enabled: true, icon: 'settings' },
	];

	let collapsed = $state(true);
	let mobileOpen = $state(false);
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
			aria-expanded={mobileOpen || !collapsed}
			onclick={() => {
				if (window.matchMedia('(max-width: 640px)').matches) mobileOpen = !mobileOpen;
				else collapsed = !collapsed;
			}}
		>
			<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
				<path d="M4 6h16M4 12h16M4 18h16" />
			</svg>
		</button>

		<a class="brand" href={Routes.PROFESSOR_DASHBOARD}>
			<img src="/qr-attend-logo.svg" alt="Attendly logo" class="brand-logo" />
			<span class="brand-name" class:hidden={collapsed}>Attendly</span>
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
			actionLabel="Open excuse queue"
			onOpen={() => void loadNotifPreview()}
			onAction={openNotifQueue}
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
		{#if mobileOpen}
			<button type="button" class="drawer-backdrop" aria-label="Close sidebar" onclick={() => (mobileOpen = false)}></button>
		{/if}
		<aside class="sidebar" class:collapsed class:mobile-open={mobileOpen}>
			{#each navItems as item (item.label)}
				<a
					class="nav-link"
					class:active={isActive(item.path)}
					href={item.path}
					title={item.label}
					aria-current={isActive(item.path) ? 'page' : undefined}
					onclick={() => (mobileOpen = false)}
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

<svelte:window onkeydown={(e) => { if (e.key === 'Escape') { mobileOpen = false; if (logoutOpen) logoutOpen = false; } }} />

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

	.drawer-backdrop {
		display: none;
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

		.drawer-backdrop {
			display: block;
			position: fixed;
			inset: 0;
			background: var(--overlay);
			z-index: 50;
			border: 0;
			padding: 0;
			cursor: pointer;
		}

		.topbar {
			min-height: 56px;
		}

		.sidebar {
			position: fixed;
			top: 56px;
			left: 0;
			bottom: 0;
			z-index: 60;
			transform: translateX(-100%);
			transition: transform 0.2s ease;
			box-shadow: var(--shadow-lg);
		}

		.sidebar,
		.sidebar.collapsed {
			width: 220px;
		}

		.sidebar .nav-label,
		.sidebar .nav-label.hidden {
			display: inline;
			opacity: 1;
		}

		.sidebar .nav-link {
			justify-content: flex-start;
			padding: 0.625rem 0.75rem;
		}

		.sidebar.mobile-open {
			transform: translateX(0);
		}
	}

	@media (max-width: 360px) {
		.brand-name {
			display: none;
		}
	}
</style>
