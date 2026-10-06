<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import TempPasswordModal from '$lib/components/TempPasswordModal.svelte';
	import {
		authState,
		isSuperAdmin,
		restoreSession,
	} from '$lib/features/auth/store.svelte';
	import {
		adminUsersState,
		deactivateAdminUser,
		initAdminUsers,
		refreshAdminUsers,
	} from '$lib/features/admin/store.svelte';
	import { createUser, resetUserPassword } from '$lib/features/admin/service';
	import { adminUserCreateSchema } from '$lib/features/admin/schema';
	import type { AdminUser, AdminUserRole } from '$lib/shared/types';
	import { Routes } from '$lib/shared/constants/routes';
	import { trapFocus } from '$lib/shared/actions/focusTrap';
	import { formatLocalDate } from '$lib/shared/utils/format';

	// User Management (super_admin only, wireframe 4.13): wraps
	// GET/POST /admin/users, PATCH /{id}/deactivate, and
	// POST /{id}/reset-password. Plain admins never see this page — the layout
	// hides the nav item and this guard bounces them to the dashboard. Still no
	// edit/reactivate/delete: the backend mounts no such routes, so the UI
	// omits the buttons rather than calling 404s.

	let search = $state('');
	let roleFilter = $state<'all' | AdminUserRole>('all');
	let statusFilter = $state<'all' | 'active' | 'inactive'>('all');

	let formOpen = $state(false);
	let formError = $state<string | null>(null);
	let formBusy = $state(false);
	let deactivateTarget = $state<AdminUser | null>(null);
	let deactivateBusy = $state(false);
	let createdTemp = $state<{ email: string; tempPassword: string } | null>(null);
	let copied = $state(false);
	// Credential reset; shares TempPasswordModal with the students and
	// professors rosters because the backend has one path behind all three.
	let resetTarget = $state<AdminUser | null>(null);

	let f_email = $state('');
	let f_role = $state<'admin' | 'professor' | 'student'>('admin');
	let f_first_name = $state('');
	let f_middle_name = $state('');
	let f_last_name = $state('');
	let f_username = $state('');

	const roleParam = $derived(roleFilter === 'all' ? undefined : roleFilter);
	const isActiveFilter = $derived(
		statusFilter === 'all' ? undefined : statusFilter === 'active'
	);

	const totalPages = $derived(
		Math.max(1, Math.ceil(adminUsersState.total / adminUsersState.size))
	);

	const selfId = $derived(authState.user?.id ?? null);
	const isSelf = (u: AdminUser) => selfId !== null && String(u.id) === String(selfId);

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

	onMount(async () => {
		const user = await restoreSession();
		if (!user || !isSuperAdmin()) {
			await goto(Routes.ADMIN_DASHBOARD);
			return;
		}
		load(1);
	});

	const applyFilters = () => {
		load(1);
	};

	const displayName = (u: AdminUser) =>
		[u.firstName, u.lastName].filter(Boolean).join(' ') || u.email;

	const openCreate = () => {
		formError = null;
		f_email = '';
		f_role = 'admin';
		f_first_name = '';
		f_middle_name = '';
		f_last_name = '';
		f_username = '';
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
				username: f_username || undefined,
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
				username: d.username || undefined,
			});
			formOpen = false;
			copied = false;
			createdTemp = { email: result.user.email, tempPassword: result.tempPassword };
			await refreshAdminUsers();
		} catch (e: unknown) {
			formError = e instanceof Error && e.message ? e.message : 'Save failed. Please try again.';
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
			<p class="muted">Super-admin only · create and deactivate accounts · {adminUsersState.total} total</p>
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
			placeholder="Search email, username, name…"
			aria-label="Search users"
			bind:value={search}
			onkeydown={(e) => {
				if (e.key === 'Enter') applyFilters();
			}}
		/>
		<select class="input" aria-label="Role filter" bind:value={roleFilter} onchange={applyFilters}>
			<option value="all">All roles</option>
			<option value="super_admin">Super Admin</option>
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
		<section class="card"><p class="muted">Loading…</p></section>
	{:else if adminUsersState.error}
		<section class="card"><p class="error">Could not load users: {adminUsersState.error}</p></section>
	{:else if adminUsersState.items.length === 0}
		<section class="card">
			<p class="empty">No users match these filters.</p>
		</section>
	{:else}
		<section class="card table-wrap">
			{#if adminUsersState.actionError}
				<p class="error" role="alert">{adminUsersState.actionError}</p>
			{/if}
			<table>
				<thead>
					<tr>
						<th>Name</th>
						<th>Email</th>
						<th>Role</th>
						<th>Status</th>
						<th>Created</th>
						<th><span class="sr">Actions</span></th>
					</tr>
				</thead>
				<tbody>
					{#each adminUsersState.items as u (u.id)}
						<tr>
							<td>{displayName(u)}</td>
							<td class="mono">{u.email}</td>
							<td>{u.role}</td>
							<td>
								<span class={u.isActive ? 'status-active' : 'status-inactive'}>
									{u.isActive ? 'Active' : 'Inactive'}
								</span>
							</td>
							<td class="mono">{formatLocalDate(u.createdAt)}</td>
							<td class="row-actions">
								{#if u.isActive}
									{#if isSelf(u)}
										<span class="hint" title="You cannot deactivate your own account">You</span>
									{:else}
										<button class="link danger" onclick={() => (deactivateTarget = u)}>
											Deactivate
										</button>
									{/if}
								{:else}
									<span class="hint">Deactivated</span>
								{/if}
								<button class="link" onclick={() => (resetTarget = u)}>Reset password</button>
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
						<option value="admin">Admin</option>
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
					<label>Username (optional)<input class="input" bind:value={f_username} placeholder="auto-generated" /></label>
				</div>
				<p class="hint">Student/professor accounts link to a matching active roster row by email; admin accounts need no roster row. A temporary password is shown once after creation.</p>
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (formOpen = false)}>Cancel</button>
				<button class="btn btn-primary" data-testid="save-user" disabled={formBusy} onclick={submitForm}>
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
				{displayName(deactivateTarget)} ({deactivateTarget.email}) will lose access
				immediately. This cannot be undone from the UI — there is no reactivate
				endpoint.
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

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
		font-family: system-ui, sans-serif;
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

	.empty {
		color: var(--text-muted);
		font-size: 0.9375rem;
		margin: 0;
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
		font-family: system-ui, sans-serif;
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
</style>
