<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte';
	import SkeletonTable from '$lib/components/SkeletonTable.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import TempPasswordModal from '$lib/components/TempPasswordModal.svelte';
	import {
		authState,
		isAdmin,
		isSuperAdmin,
		restoreSession,
	} from '$lib/features/auth/store.svelte';
	import {
		adminUsersState,
		deactivateAdminUser,
		initAdminUsers,
		reactivateAdminUser,
		refreshAdminUsers,
	} from '$lib/features/admin/store.svelte';
	import { createUser, resetUserPassword, getLockoutStatus, releaseLockout, resetLockoutCounter, grantLockoutOverride, revokeLockoutOverride } from '$lib/features/admin/service';
	import { adminUserCreateSchema } from '$lib/features/admin/schema';
	import type { AdminUser, AdminUserRole, LockoutStatus } from '$lib/shared/types';
	import { Routes } from '$lib/shared/constants/routes';
	import { notifyEntityChanged, subscribeEntity } from '$lib/shared/utils/entityEvents';
	import { onFocusRevalidate } from '$lib/shared/utils/revalidateOnFocus';
	import { trapFocus } from '$lib/shared/actions/focusTrap';
	import { formatLocalDate, formatLocalDateTime } from '$lib/shared/utils/format';
	import { friendlyActionError } from '$lib/shared/utils/deleteErrors';
import { APIError } from '$lib/api/client';

	// User Management (ADMIN guard: admin + super_admin, wireframe 4.13): wraps
	// GET/POST /admin/users, PATCH /{id}/deactivate, PATCH /{id}/reactivate,
	// and POST /{id}/reset-password. Plain admins never see this page — the
	// layout hides the nav item and this guard bounces them to the dashboard.

	let search = $state('');
	let roleFilter = $state<'all' | AdminUserRole>('all');
	let statusFilter = $state<'all' | 'active' | 'inactive'>('all');

	let formOpen = $state(false);
	let formError = $state<string | null>(null);
	let formBusy = $state(false);
	let deactivateTarget = $state<AdminUser | null>(null);
	let deactivateBusy = $state(false);
	let reactivateTarget = $state<AdminUser | null>(null);
	let reactivateBusy = $state(false);
	let createdTemp = $state<{ email: string; tempPassword: string } | null>(null);
	let copied = $state(false);
	// Credential reset; shares TempPasswordModal with the students and
	// professors rosters because the backend has one path behind all three.
	let resetTarget = $state<AdminUser | null>(null);

	// Account lockout modal state.
	let lockoutTarget = $state<AdminUser | null>(null);
	let lockoutStatus = $state<LockoutStatus | null>(null);
	let lockoutLoading = $state(false);
	let lockoutError = $state<string | null>(null);
	let lockoutBusyAction = $state<string | null>(null);
	let lockoutNotice = $state<string | null>(null);
	let lockoutAction = $state<'release' | 'reset' | 'override' | 'release-reset'>('release');
	let actionReason = $state('');
	let revokeReason = $state('');
	let overrideMinutes = $state(15);

	$effect(() => {
		if (!lockoutStatus) return;
		const expired = lockoutStatus.isLocked && lockoutStatus.remainingMinutes === undefined;
		const releaseAvailable = lockoutStatus.isPermanentlyLocked || (lockoutStatus.isLocked && !expired);
		const overrideAvailable = lockoutStatus.isLocked && !lockoutStatus.isPermanentlyLocked && !expired;
		if (lockoutAction === 'release' && !releaseAvailable) lockoutAction = 'reset';
		if ((lockoutAction === 'override' || lockoutAction === 'release-reset') && !overrideAvailable) {
			lockoutAction = releaseAvailable ? 'release' : 'reset';
		}
	});

	let f_email = $state('');
	let f_role = $state<'admin' | 'professor' | 'student'>(isSuperAdmin() ? 'admin' : 'professor');
	let f_first_name = $state('');
	let f_middle_name = $state('');
	let f_last_name = $state('');

	const roleParam = $derived(roleFilter === 'all' ? undefined : roleFilter);
	const isActiveFilter = $derived(
		statusFilter === 'all' ? undefined : statusFilter === 'active'
	);

	const totalPages = $derived(
		Math.max(1, Math.ceil(adminUsersState.total / adminUsersState.size))
	);

	const selfId = $derived(authState.user?.id ?? null);
	const isSelf = (u: AdminUser) => selfId !== null && String(u.id) === String(selfId);
	const canMutateUser = (u: AdminUser) => isSuperAdmin() || (u.role !== 'admin' && u.role !== 'super_admin');

	const load = (page = 1) =>
		initAdminUsers(
			{
				search: search.trim() || undefined,
				role: roleParam,
				is_active: isActiveFilter,
			},
			page,
			adminUsersState.size
		);

	// alive-guard for the async onMount below: if the route unmounts while
	// restoreSession() is still in flight, destroy has already run and the
	// entity/focus subscriptions must never attach afterwards.
	let pageAlive = true;
	const autoRefreshStops: (() => void)[] = [];

	onDestroy(() => {
		pageAlive = false;
		for (const stop of autoRefreshStops) stop();
	});

	const refreshVisible = () => {
		if (!adminUsersState.loading) void refreshAdminUsers();
	};

	onMount(async () => {
		const user = await restoreSession();
		if (!user || !isAdmin()) {
			await goto(Routes.ADMIN_DASHBOARD);
			return;
		}
		if (!pageAlive) return;
		load(1);
		autoRefreshStops.push(
			subscribeEntity('users', refreshVisible),
			onFocusRevalidate(refreshVisible)
		);
	});

	const applyFilters = () => {
		load(1);
	};

	const displayName = (u: AdminUser) =>
		[u.firstName, u.lastName].filter(Boolean).join(' ') ||
		u.email ||
		`${u.role} #${u.id}`;

	const describe = (e: unknown): string => {
		if (e instanceof APIError) return e.message || 'Request failed.';
		return e instanceof Error && e.message ? e.message : 'Request failed.';
	};

	const openLockout = async (u: AdminUser) => {
		lockoutTarget = u;
		lockoutStatus = null;
		lockoutLoading = true;
		lockoutError = null;
		lockoutNotice = null;
		actionReason = '';
		revokeReason = '';
		overrideMinutes = 15;
		try {
			const status = await getLockoutStatus(u.id);
			if (!pageAlive) return;
			if (status.userId !== u.id) return;
			lockoutStatus = status;
			const expired = status.isLocked && status.remainingMinutes === undefined;
			const releaseAvailable = status.isPermanentlyLocked || (status.isLocked && !expired);
			lockoutAction = releaseAvailable ? 'release' : 'reset';
		} catch (e: unknown) {
			if (!pageAlive) return;
			const msg = describe(e);
			if (e instanceof APIError && e.code === 'user_not_found') {
				lockoutTarget = null;
				lockoutStatus = null;
				await refreshAdminUsers();
				return;
			}
			lockoutError = msg;
		} finally {
			if (pageAlive) lockoutLoading = false;
		}
	};

	const refreshLockoutStatus = async () => {
		if (!lockoutTarget) return;
		const u = lockoutTarget;
		lockoutLoading = true;
		lockoutError = null;
		try {
			const status = await getLockoutStatus(u.id);
			if (!pageAlive) return;
			lockoutStatus = status;
			const expired2 = status.isLocked && status.remainingMinutes === undefined;
			const releaseAvailable2 = status.isPermanentlyLocked || (status.isLocked && !expired2);
			const available = (v: string) =>
				v === 'release'
					? releaseAvailable2
					: v === 'override' || v === 'release-reset'
						? status.isLocked && !status.isPermanentlyLocked && !expired2
						: true;
			if (!available(lockoutAction)) {
				lockoutAction = releaseAvailable2 ? 'release' : 'reset';
			}
		} catch (e: unknown) {
			if (!pageAlive) return;
			const msg = describe(e);
			if (e instanceof APIError && e.code === 'user_not_found') {
				lockoutTarget = null;
				lockoutStatus = null;
				await refreshAdminUsers();
				return;
			}
			lockoutError = msg;
		} finally {
			if (pageAlive) lockoutLoading = false;
		}
	};

	const closeLockout = () => {
		lockoutTarget = null;
		lockoutStatus = null;
		lockoutLoading = false;
		lockoutError = null;
		lockoutNotice = null;
		lockoutBusyAction = null;
	};

	const runLockoutAction = async (action: string, fn: () => Promise<void>, clearReason: () => void) => {
		lockoutBusyAction = action;
		lockoutNotice = null;
		lockoutError = null;
		try {
			await fn();
			if (!pageAlive) return;
			clearReason();
			lockoutNotice = 'Action completed successfully.';
			await refreshLockoutStatus();
		} catch (e: unknown) {
			if (!pageAlive) return;
			lockoutError = describe(e);
			await refreshLockoutStatus();
		} finally {
			if (pageAlive) lockoutBusyAction = null;
		}
	};

	const openCreate = () => {
		formError = null;
		f_email = '';
		f_role = isSuperAdmin() ? 'admin' : 'professor';
		f_first_name = '';
		f_middle_name = '';
		f_last_name = '';
		formOpen = true;
	};

	const submitForm = async () => {
		formError = null;
		formBusy = true;
		try {
			const parsed = adminUserCreateSchema.safeParse({
				email: f_email,
				role: f_role,
				first_name: f_first_name,
				middle_name: f_middle_name || undefined,
				last_name: f_last_name,
			});
			if (!parsed.success) {
				formError = parsed.error.issues[0]?.message ?? 'Check the form and try again.';
				return;
			}
			const d = parsed.data;
			const result = await createUser({
				email: d.email,
				role: d.role,
				first_name: d.first_name,
				middle_name: d.middle_name || undefined,
				last_name: d.last_name,
			});
			formOpen = false;
			copied = false;
			createdTemp = { email: result.user.email ?? '', tempPassword: result.tempPassword };
			await refreshAdminUsers();
			notifyEntityChanged('users');
		} catch (e: unknown) {
			formError = friendlyActionError(e, 'Save failed. Please try again.');
		} finally {
			formBusy = false;
		}
	};

	const confirmDeactivate = async () => {
		if (!deactivateTarget) return;
		deactivateBusy = true;
		try {
			await deactivateAdminUser(deactivateTarget);
			deactivateTarget = null;
		} finally {
			deactivateBusy = false;
		}
	};

	const confirmReactivate = async () => {
		if (!reactivateTarget) return;
		reactivateBusy = true;
		try {
			await reactivateAdminUser(reactivateTarget);
			reactivateTarget = null;
		} finally {
			reactivateBusy = false;
		}
	};

	const copyTemp = async () => {
		if (!createdTemp) return;
		try {
			await navigator.clipboard.writeText(createdTemp.tempPassword);
			copied = true;
		} catch {
			copied = false;
		}
	};
</script>

<div class="page">
	<header class="header">
		<div>
			<h1>User Management</h1>
			<p class="muted">Super-admin only · create, deactivate, and reactivate accounts · {adminUsersState.total} total</p>
		</div>
		<div class="header-actions">
			<button class="btn btn-primary" data-testid="add-user" onclick={openCreate}>
				<AppIcon name="plus" size={18} />
				Add
			</button>
		</div>
	</header>

	<section class="card filters">
		<input
			class="input search"
			type="search"
			placeholder="Search email, name…"
			aria-label="Search users"
			bind:value={search}
			onkeydown={(e) => {
				if (e.key === 'Enter') applyFilters();
			}}
		/>
		<select class="input" aria-label="Role filter" bind:value={roleFilter} onchange={applyFilters}>
			<option value="all">All roles</option>
			{#if isSuperAdmin()}
				<option value="super_admin">Super Admin</option>
			{/if}
			<option value="admin">Admin</option>
			<option value="professor">Professor</option>
			<option value="student">Student</option>
		</select>
		<select class="input" aria-label="Status filter" bind:value={statusFilter} onchange={applyFilters}>
			<option value="all">All statuses</option>
			<option value="active">Active</option>
			<option value="inactive">Inactive</option>
		</select>
		<button class="btn btn-secondary" data-testid="apply" onclick={applyFilters}>Apply</button>
	</section>

	{#if adminUsersState.loading}
		<SkeletonTable rows={8} cols={6} label="Loading users…" />
	{:else if adminUsersState.error}
		<section class="card"><p class="error">Could not load users: {adminUsersState.error}</p></section>
	{:else if adminUsersState.items.length === 0}
		<section class="card">
			<EmptyState
				icon="users"
				title="No users match these filters"
				hint="Create the first account with the + button."
			/>
		</section>
	{:else}
		<section class="card table-wrap">
			{#if adminUsersState.actionError}
				<p class="error" role="alert">{adminUsersState.actionError}</p>
			{/if}
			<table>
				<thead>
					<tr>
						<th scope="col">Name</th>
						<th scope="col">Email</th>
						<th scope="col">Role</th>
						<th scope="col">Status</th>
						<th scope="col">Created</th>
						<th scope="col"><span class="sr">Actions</span></th>
					</tr>
				</thead>
				<tbody>
					{#each adminUsersState.items as u (u.id)}
						<tr>
							<td>{displayName(u)}</td>
							<td class="mono">{u.email ?? 'Restricted'}</td>
							<td>{u.role}</td>
							<td>
								<span class={u.isActive ? 'status-active' : 'status-inactive'}>
									{u.isActive ? 'Active' : 'Inactive'}
								</span>
							</td>
							<td class="mono">{formatLocalDate(u.createdAt)}</td>
							<td>
								<div class="row-actions">
									{#if u.isActive}
										{#if isSelf(u)}
											<span class="hint" title="You cannot deactivate your own account">You</span>
										{:else if canMutateUser(u)}
											<button class="link danger" onclick={() => (deactivateTarget = u)}>
												Deactivate
											</button>
										{/if}
									{:else if canMutateUser(u)}
										<button class="link" onclick={() => (reactivateTarget = u)}>
											Reactivate
										</button>
									{/if}
									{#if canMutateUser(u)}
										<button class="link" onclick={() => (resetTarget = u)}>Reset password</button>
									{/if}
									{#if !isSelf(u)}
										<button class="link" onclick={() => openLockout(u)}>Lockout</button>
									{/if}
									{#if !canMutateUser(u) && !isSelf(u)}
										<span class="hint" title="View only: insufficient permissions to modify this account">View only</span>
									{/if}
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
			<div class="pager">
				<button
					class="btn btn-secondary"
					disabled={adminUsersState.page <= 1}
					onclick={() => load(adminUsersState.page - 1)}
				>
					‹ Prev
				</button>
				<span class="muted">Page {adminUsersState.page} of {totalPages}</span>
				<button
					class="btn btn-secondary"
					disabled={adminUsersState.page >= totalPages}
					onclick={() => load(adminUsersState.page + 1)}
				>
					Next ›
				</button>
			</div>
		</section>
	{/if}
</div>

{#if formOpen}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="user-form-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (formBusy ? undefined : (formOpen = false)) }}
		>
			<h2 id="user-form-title" class="modal-title">Add user</h2>
			{#if formError}
				<p class="error" role="alert">{formError}</p>
			{/if}
			<div class="form">
				<label>Email<input class="input" type="email" bind:value={f_email} placeholder="sam.t.torres@isu.edu.ph" /></label>
				<label>Role
					<select class="input" bind:value={f_role}>
						{#if isSuperAdmin()}
							<option value="admin">Admin</option>
						{/if}
						<option value="professor">Professor</option>
						<option value="student">Student</option>
					</select>
				</label>
				<div class="grid2">
					<label>First name<input class="input" bind:value={f_first_name} /></label>
					<label>Middle name<input class="input" bind:value={f_middle_name} placeholder="optional" /></label>
				</div>
				<div class="grid2">
					<label>Last name<input class="input" bind:value={f_last_name} /></label>
				</div>
				<p class="hint">Student/professor accounts link to a matching active roster row by email; admin accounts need no roster row. A temporary password is shown once after creation.</p>
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (formOpen = false)}>Cancel</button>
				<button class="btn btn-primary" data-testid="save-user" aria-busy={formBusy} disabled={formBusy} onclick={submitForm}>
					{formBusy ? 'Saving…' : 'Save'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if deactivateTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="deactivate-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (deactivateBusy ? undefined : (deactivateTarget = null)) }}
		>
			<h2 id="deactivate-title" class="modal-title">Deactivate account?</h2>
			<p class="modal-text">
				{displayName(deactivateTarget)} ({deactivateTarget.email ?? 'restricted account'}) will lose access
				immediately. You can reactivate the account later from this page.
			</p>
			{#if adminUsersState.actionError}
				<p class="error" role="alert">{adminUsersState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (deactivateTarget = null)}>Cancel</button>
				<button class="btn btn-danger" disabled={deactivateBusy} onclick={confirmDeactivate}>
					{deactivateBusy ? 'Deactivating…' : 'Deactivate'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if reactivateTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="reactivate-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (reactivateBusy ? undefined : (reactivateTarget = null)) }}
		>
			<h2 id="reactivate-title" class="modal-title">Reactivate account?</h2>
			<p class="modal-text">
				{displayName(reactivateTarget)} ({reactivateTarget.email ?? 'restricted account'}) will regain access
				immediately. Their password, MFA settings, and role are unchanged.
			</p>
			{#if adminUsersState.actionError}
				<p class="error" role="alert">{adminUsersState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (reactivateTarget = null)}>Cancel</button>
				<button class="btn btn-primary" disabled={reactivateBusy} onclick={confirmReactivate}>
					{reactivateBusy ? 'Reactivating…' : 'Reactivate'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if createdTemp}
	<div class="modal-overlay" role="presentation">
		<!-- Shown-once temp password: Escape is deliberately inert so a stray
		     keypress cannot discard the only copy. Copy or Done to leave. -->
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="temp-title"
			tabindex="-1"
			use:trapFocus
		>
			<h2 id="temp-title" class="modal-title">Temporary password</h2>
			<p class="modal-text">
				Account <strong class="mono">{createdTemp.email}</strong> created. Share this
				password once — it will not be shown again, and the account must change it
				at first sign-in.
			</p>
			<p class="temp mono" data-testid="temp-password">{createdTemp.tempPassword}</p>
			<div class="modal-actions">
				<button class="btn btn-secondary" onclick={copyTemp}>
					{copied ? 'Copied' : 'Copy'}
				</button>
				<button class="btn btn-primary" onclick={() => (createdTemp = null)}>Done</button>
			</div>
		</div>
	</div>
{/if}

{#if resetTarget}
	<TempPasswordModal
		subject={displayName(resetTarget)}
		subjectKind="account"
		onconfirm={() => resetUserPassword(resetTarget!.id)}
		onclose={() => (resetTarget = null)}
	/>
{/if}

{#if lockoutTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal lockout-modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="lockout-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (lockoutBusyAction ? undefined : closeLockout()) }}
		>
			<header class="lockout-header">
				<div>
					<h2 id="lockout-title" class="modal-title">Account lockout</h2>
					<p class="lockout-subtitle">
						<span class="lockout-name">{displayName(lockoutTarget)}</span>
						<span class="lockout-email mono">{lockoutTarget.email ?? 'Restricted'}</span>
					</p>
				</div>
				<span class="status-badge" class:locked={lockoutStatus?.isLocked} class:permanent={lockoutStatus?.isPermanentlyLocked}>
					{lockoutStatus?.isPermanentlyLocked ? 'Permanently locked' : lockoutStatus?.isLocked ? 'Locked' : lockoutStatus ? 'Not locked' : '—'}
				</span>
			</header>

			{#if lockoutNotice}
				<p class="alert alert-success" role="status">{lockoutNotice}</p>
			{/if}
			{#if lockoutError}
				<p class="alert alert-error" role="alert">{lockoutError}</p>
			{/if}

			{#if lockoutLoading && !lockoutStatus}
				<div class="lockout-loading" aria-live="polite">
					<span class="spinner" aria-hidden="true"></span>
					Loading lockout status…
				</div>
			{:else if lockoutStatus}
				<section class="lockout-status" aria-label="Lockout status">
					{#if lockoutStatus.isPermanentlyLocked}
						<div class="status-row">
							<span class="status-label">State</span>
							<span class="status-value">Permanently locked</span>
						</div>
					{/if}
					<div class="status-row">
						<span class="status-label">Level</span>
						<span class="status-value">{lockoutStatus.lockoutLevel}</span>
					</div>
					{#if !lockoutStatus.isPermanentlyLocked}
						<div class="status-row">
							<span class="status-label">Duration</span>
							<span class="status-value">{lockoutStatus.lockoutDurationMinutes} min</span>
						</div>
					{/if}
					{#if lockoutStatus.lockedAt}
						<div class="status-row">
							<span class="status-label">Locked at</span>
							<span class="status-value">{formatLocalDateTime(lockoutStatus.lockedAt)}</span>
						</div>
					{/if}
					{#if !lockoutStatus.isPermanentlyLocked && lockoutStatus.lockedUntil}
						<div class="status-row">
							<span class="status-label">Locked until</span>
							<span class="status-value">{formatLocalDateTime(lockoutStatus.lockedUntil)}</span>
						</div>
					{/if}
					{#if !lockoutStatus.isPermanentlyLocked}
						<div class="status-row">
							<span class="status-label">Remaining</span>
							<span class="status-value">
								{#if lockoutStatus.remainingMinutes !== undefined}
									{lockoutStatus.remainingMinutes} min
								{:else if lockoutStatus.isLocked}
									Expired (clears on next login attempt)
								{:else}
									—
								{/if}
							</span>
						</div>
					{/if}
					{#if lockoutStatus.lastLockoutAt}
						<div class="status-row">
							<span class="status-label">Last lockout</span>
							<span class="status-value">{formatLocalDateTime(lockoutStatus.lastLockoutAt)}</span>
						</div>
					{/if}
					{#if lockoutStatus.overrideUntil}
						<div class="status-row">
							<span class="status-label">Override until</span>
							<span class="status-value">{formatLocalDateTime(lockoutStatus.overrideUntil)}</span>
						</div>
					{/if}
					{#if lockoutStatus.overrideRemainingMinutes !== undefined}
						<div class="status-row">
							<span class="status-label">Override remaining</span>
							<span class="status-value">{lockoutStatus.overrideRemainingMinutes} min</span>
						</div>
					{/if}
				</section>

				{#if (lockoutStatus.isLocked || lockoutStatus.lockoutLevel > 0) && canMutateUser(lockoutTarget)}
					<section class="lockout-section">
						<h3 class="section-title">Lockout action</h3>
						<p class="section-help">Choose an action and provide a reason.</p>
						<label class="field">
							<span>Action</span>
							<select class="input" bind:value={lockoutAction} onchange={() => { actionReason = ''; overrideMinutes = 15; }}>
								{#if lockoutStatus.isLocked && !lockoutStatus.isPermanentlyLocked && lockoutStatus.remainingMinutes !== undefined}
									<option value="release">Release lockout</option>
									<option value="override">Grant temporary override</option>
									<option value="release-reset">Release and reset counter</option>
								{/if}
								{#if lockoutStatus.isLocked && !lockoutStatus.isPermanentlyLocked && lockoutStatus.remainingMinutes === undefined}
									<!-- expired: no release/override/combined -->
								{/if}
								{#if lockoutStatus.isLocked && lockoutStatus.isPermanentlyLocked}
									<option value="release">Release lockout</option>
								{/if}
								<option value="reset">Reset escalation counter</option>
							</select>
							<p class="section-help action-help">
								{#if lockoutAction === 'release'}
									Clears the active lockout immediately.
								{:else if lockoutAction === 'reset'}
									Resets the violation counter to zero.
								{:else if lockoutAction === 'override'}
									Allows login even while locked, for the chosen duration.
								{:else if lockoutAction === 'release-reset'}
									Releases the lockout and resets the escalation counter in one step.
								{/if}
							</p>
						</label>
						{#if lockoutAction === 'override' && lockoutStatus.isLocked && !lockoutStatus.isPermanentlyLocked}
							<label class="field">
								<span>Duration (minutes, 1–60)</span>
								<input class="input" type="number" min="1" max="60" bind:value={overrideMinutes} />
							</label>
						{/if}
						<label class="field">
							<span>Reason <span class="required">*</span></span>
							<textarea class="input" bind:value={actionReason} placeholder="Required (3–500 characters)" rows="2" aria-required="true"></textarea>
							<span class="field-help">{actionReason.trim().length}/500</span>
						</label>
						<button
							class="btn btn-primary"
							title={actionReason.trim().length < 3 || actionReason.trim().length > 500 ? 'Enter a valid reason (3–500 characters)' : ''}
							disabled={lockoutBusyAction !== null || actionReason.trim().length < 3 || actionReason.trim().length > 500 || (lockoutAction === 'override' && (overrideMinutes < 1 || overrideMinutes > 60))}
							onclick={() => {
								const reason = actionReason.trim();
								if (lockoutAction === 'release') {
									runLockoutAction('release', () => releaseLockout(lockoutTarget!.id, reason), () => (actionReason = ''));
								} else if (lockoutAction === 'reset') {
									runLockoutAction('reset', () => resetLockoutCounter(lockoutTarget!.id, reason), () => (actionReason = ''));
								} else if (lockoutAction === 'override') {
									runLockoutAction('override', () => grantLockoutOverride(lockoutTarget!.id, overrideMinutes, reason), () => (actionReason = ''));
								} else if (lockoutAction === 'release-reset') {
									runLockoutAction(
										'release-reset',
										async () => {
											await releaseLockout(lockoutTarget!.id, reason);
											await resetLockoutCounter(lockoutTarget!.id, reason);
										},
										() => (actionReason = '')
									);
								}
							}}
						>
							{lockoutBusyAction === 'release'
								? 'Releasing…'
								: lockoutBusyAction === 'reset'
									? 'Resetting…'
									: lockoutBusyAction === 'override'
										? 'Granting…'
										: lockoutBusyAction === 'release-reset'
											? 'Processing…'
											: 'Submit'}
						</button>
					</section>
				{/if}

				{#if lockoutStatus.overrideUntil && canMutateUser(lockoutTarget)}
					<section class="lockout-section">
						<h3 class="section-title">Revoke override</h3>
						<p class="section-help">Ends the active override immediately.</p>
						<label class="field">
							<span>Reason <span class="required">*</span></span>
							<textarea class="input" bind:value={revokeReason} placeholder="Required (3–500 characters)" rows="2" aria-required="true"></textarea>
							<span class="field-help">{revokeReason.trim().length}/500</span>
						</label>
						<button
							class="btn btn-danger"
							title={revokeReason.trim().length < 3 || revokeReason.trim().length > 500 ? 'Enter a valid reason (3–500 characters)' : ''}
							disabled={lockoutBusyAction !== null || revokeReason.trim().length < 3 || revokeReason.trim().length > 500}
							onclick={() =>
								runLockoutAction('revoke', () => revokeLockoutOverride(lockoutTarget!.id, revokeReason.trim()), () => (revokeReason = ''))}
						>
							{lockoutBusyAction === 'revoke' ? 'Revoking…' : 'Revoke override'}
						</button>
					</section>
				{/if}
			{/if}

			<div class="modal-actions">
				<button class="btn btn-ghost" disabled={lockoutBusyAction !== null} onclick={closeLockout}>Close</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
	}

	.header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
	}

	.header h1 {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0 0 0.25rem;
	}

	.muted {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0;
	}

	.header-actions {
		display: flex;
		gap: 0.75rem;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 1.5rem;
		box-shadow: var(--shadow-sm);
	}

	.filters {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
		align-items: center;
	}

	.input {
		padding: 0.625rem 0.875rem;
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		color: var(--text-strong);
		background: var(--bg-card);
	}

	.input:focus {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
	}

	.search {
		flex: 1 1 240px;
	}

	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.875rem;
	}

	th,
	td {
		text-align: left;
		padding: 0.625rem 0.5rem;
		border-bottom: 1px solid var(--divider);
		vertical-align: middle;
	}

	th {
		color: var(--text-muted);
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.mono {
		font-variant-numeric: tabular-nums;
		font-weight: 500;
	}

	.status-active,
	.status-inactive {
		display: inline-block;
		padding: 0.125rem 0.625rem;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 600;
		white-space: nowrap;
	}

	.status-active {
		background: var(--success-bg);
		color: var(--success);
	}

	.status-inactive {
		background: var(--danger-bg);
		color: var(--danger);
	}

	.row-actions {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.link {
		background: none;
		border: none;
		padding: 0;
		color: var(--accent);
		font-size: 0.8125rem;
		font-weight: 600;
		cursor: pointer;
	}

	.link:hover {
		text-decoration: underline;
	}

	.link.danger {
		color: var(--danger);
	}

	.sr {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
	}

	.pager {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		margin-top: 1rem;
	}

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0 0 1rem;
	}

	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.625rem 1rem;
		border-radius: 8px;
		font-size: 0.875rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
		white-space: nowrap;
		transition: background 0.15s ease, border-color 0.15s ease;
	}

	.btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-primary {
		background: var(--brand);
		border: 1px solid var(--brand);
		color: var(--on-brand);
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--brand-hover);
	}

	.btn-secondary {
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		color: var(--text-strong);
	}

	.btn-secondary:hover:not(:disabled) {
		background: var(--divider);
	}

	.btn-ghost {
		background: var(--divider);
		border: 1px solid transparent;
		color: var(--text-secondary);
	}

	.btn-danger {
		background: var(--danger);
		border: 1px solid var(--danger);
		color: var(--on-brand);
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
		max-width: 520px;
		max-height: 90vh;
		overflow-y: auto;
		background: var(--bg-card);
		border-radius: 12px;
		box-shadow: var(--shadow-lg);
		padding: 1.75rem 1.5rem;
	}

	.modal-title {
		margin: 0 0 1rem;
		font-size: 1.25rem;
		font-weight: 700;
		color: var(--text);
	}

	.modal-text {
		margin: 0 0 1.5rem;
		font-size: 0.9375rem;
		color: var(--text-secondary);
	}

	.form {
		display: flex;
		flex-direction: column;
		gap: 0.875rem;
	}

	.form label {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.grid2 {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.875rem;
	}

	.hint {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin: 0;
	}

	.temp {
		background: var(--bg-muted);
		border: 1px dashed var(--border-strong);
		border-radius: 8px;
		padding: 0.875rem 1rem;
		font-size: 1rem;
		text-align: center;
		margin: 0 0 1.5rem;
		word-break: break-all;
	}

	.modal-actions {
		display: flex;
		gap: 0.75rem;
		justify-content: flex-end;
		margin-top: 1.5rem;
	}

	.table-wrap {
		overflow-x: auto;
	}

	@media (max-width: 640px) {
		.card {
			padding: 1.25rem;
		}

		.grid2 {
			grid-template-columns: minmax(0, 1fr);
		}
	}

	.lockout-modal {
		max-width: 600px;
	}

	.lockout-header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
		margin-bottom: 1rem;
	}

	.lockout-subtitle {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
		margin: 0.25rem 0 0;
		font-size: 0.875rem;
		color: var(--text-muted);
	}

	.lockout-name {
		font-weight: 600;
		color: var(--text);
	}

	.status-badge {
		display: inline-flex;
		align-items: center;
		padding: 0.25rem 0.75rem;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 700;
		background: var(--success-bg);
		color: var(--success);
		white-space: nowrap;
	}

	.status-badge.locked {
		background: var(--danger-bg);
		color: var(--danger);
	}

	.status-badge.permanent {
		background: var(--danger-bg);
		color: var(--danger);
		font-weight: 800;
	}

	.alert {
		padding: 0.625rem 0.875rem;
		border-radius: 8px;
		font-size: 0.875rem;
		margin: 0 0 1rem;
	}

	.alert-success {
		background: var(--success-bg);
		color: var(--success);
	}

	.alert-error {
		background: var(--danger-bg);
		color: var(--danger);
	}

	.lockout-loading {
		display: flex;
		align-items: center;
		gap: 0.625rem;
		padding: 1rem 0;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.spinner {
		width: 1rem;
		height: 1rem;
		border: 2px solid var(--border);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: lockout-spin 0.8s linear infinite;
	}

	@keyframes lockout-spin {
		to {
			transform: rotate(360deg);
		}
	}

	.lockout-status {
		display: grid;
		grid-template-columns: 1fr;
		gap: 0.375rem;
		padding: 0.875rem 1rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--bg-muted);
		margin-bottom: 1rem;
	}

	.status-row {
		display: flex;
		justify-content: space-between;
		gap: 1rem;
		font-size: 0.875rem;
	}

	.status-label {
		color: var(--text-muted);
		font-weight: 600;
	}

	.status-value {
		color: var(--text);
		text-align: right;
	}

	.lockout-section {
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 0.875rem 1rem;
		margin-bottom: 0.875rem;
		display: flex;
		flex-direction: column;
		gap: 0.625rem;
	}

	.section-title {
		margin: 0;
		font-size: 0.9375rem;
		font-weight: 700;
		color: var(--text);
	}

	.section-help {
		margin: 0;
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.required {
		color: var(--danger);
	}

	.field-help {
		font-size: 0.75rem;
		color: var(--text-muted);
		text-align: right;
	}


</style>
