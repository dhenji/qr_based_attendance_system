<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import {
		adminAuditState,
		adminStructureState,
		initAdminAudit,
		initStructureChanges,
		type AuditSortColumn,
	} from '$lib/features/admin/audit/store.svelte';
	import {
		AUDIT_ACTIONS,
		AUDIT_ENTITY_TYPES,
		auditCsv,
		downloadCsv,
		type AuditLogRow,
	} from '$lib/features/admin/audit/service';
	import { auditFilterSchema } from '$lib/features/admin/audit/schema';
import ConfirmExportDialog from '$lib/components/ConfirmExportDialog.svelte';
	import type { AuditAction, AuditEntityType } from '$lib/shared/types';
	import { Routes } from '$lib/shared/constants/routes';
	import { formatLocalDateTime } from '$lib/shared/utils/format';

	// Audit Logs (wireframe 4.8, `/admin/audit-logs`): contract-shaped trail
	// (Time/Actor/Action/Entity with old/new values) with entity/action/actor
	// + date-range filters, sortable Time / User / Action columns, pagination,
	// Print + CSV export. Rows are hybrid: live trail rows from
	// GET /admin/audit-logs (badged "seed" for legacy reasons) plus
	// record-creation rows derived from roster lists (badged "system record").
	// The Structure tab lists program/year/course mutations with old/new
	// values (D38, contracted academic-structure shape) and deep-links into
	// Program Management.

	type Tab = 'log' | 'structure';
	const TABS = [
		{ id: 'log', label: 'Action Log' },
		{ id: 'structure', label: 'Academic Structure' },
	] as const;

	let tab = $state<Tab>('log');
	let dateFrom = $state('');
	let dateTo = $state('');
	let entityType = $state('');
	let action = $state('');
	let performedBy = $state('');
	let formError = $state<string | null>(null);

	let pendingExport = $state<null | {
		run: () => void | Promise<void>;
		details?: { label: string; value: string }[];
		title?: string;
		message?: string;
		confirmLabel?: string;
		busyLabel?: string;
	}>(null);

	const actorLabel = (row: AuditLogRow): string =>
		row.performed_by === null || row.performed_by === undefined || row.performed_by === ''
			? '— (anonymous)'
			: String(row.performed_by);

	const entityLabel = (row: AuditLogRow): string =>
		row.entity_id === null || row.entity_id === undefined
			? row.entity_type
			: `${row.entity_type} #${row.entity_id}`;

	const changeLabel = (row: AuditLogRow): string => {
		const text = (value: unknown): string => {
			if (value === null || value === undefined) return '';
			if (typeof value === 'string') return value;
			try {
				return JSON.stringify(value);
			} catch {
				return String(value);
			}
		};
		const oldText = text(row.old_value);
		const newText = text(row.new_value);
		if (oldText && newText) return `${oldText} → ${newText}`;
		return newText || oldText || '—';
	};

	const totalPages = $derived(
		Math.max(1, Math.ceil(adminAuditState.total / adminAuditState.size))
	);

	// Client-side sorts over the loaded page (the feed takes no sort params).
	const visibleItems = $derived.by(() => {
		const items = [...adminAuditState.items];
		const dir = adminAuditState.sortDir === 'asc' ? 1 : -1;
		const key =
			adminAuditState.sortBy === 'time'
				? (r: AuditLogRow) => r.performed_at
				: adminAuditState.sortBy === 'user'
					? (r: AuditLogRow) => String(r.performed_by ?? '')
					: (r: AuditLogRow) => r.action;
		items.sort((a, b) => key(a).localeCompare(key(b)) * dir);
		return items;
	});

	const load = (page = 1) =>
		initAdminAudit(
			{
				date_from: dateFrom.trim() || undefined,
				date_to: dateTo.trim() || undefined,
				entity_type: (entityType || undefined) as AuditEntityType | undefined,
				action: (action || undefined) as AuditAction | undefined,
				performed_by: performedBy.trim() || undefined,
			},
			page,
			adminAuditState.size
		);

	onMount(async () => {
		await load(1);
		await initStructureChanges();
	});

	const applyFilters = async () => {
		formError = null;
		const parsed = auditFilterSchema.safeParse({
			date_from: dateFrom,
			date_to: dateTo,
			entity_type: entityType,
			action,
			performed_by: performedBy,
		});
		if (!parsed.success) {
			formError = parsed.error.issues[0]?.message ?? 'Check the filters and try again.';
			return;
		}
		await load(1);
	};

	const toggleSort = (column: AuditSortColumn) => {
		if (adminAuditState.sortBy === column) {
			adminAuditState.sortDir = adminAuditState.sortDir === 'asc' ? 'desc' : 'asc';
		} else {
			adminAuditState.sortBy = column;
			adminAuditState.sortDir = column === 'time' ? 'desc' : 'asc';
		}
	};

	const sortArrow = (column: AuditSortColumn) =>
		adminAuditState.sortBy === column
			? adminAuditState.sortDir === 'asc'
				? ' ▲'
				: ' ▼'
			: '';

	// Sort state for assistive tech, mirroring the professor ledger pattern
	// (professor/attendance/+page.svelte). Sort lives on the shared store here,
	// so these read `adminAuditState` rather than local bindings.
	const sortLabel = (column: AuditSortColumn, label: string): string => {
		if (adminAuditState.sortBy !== column) return `Sort by ${label.toLowerCase()} ascending`;
		return `Sort by ${label.toLowerCase()} ${adminAuditState.sortDir === 'asc' ? 'descending' : 'ascending'}`;
	};

	const ariaSort = (column: AuditSortColumn): 'ascending' | 'descending' | 'none' =>
		adminAuditState.sortBy === column
			? adminAuditState.sortDir === 'asc'
				? 'ascending'
				: 'descending'
			: 'none';

	const categoryLabel = (id: string): string =>
		AUDIT_ENTITY_TYPES.find((c) => c.id === id)?.label ?? id;

	const onExport = () =>
		downloadCsv(
			`audit-logs-${new Date().toISOString().slice(0, 10)}.csv`,
			auditCsv(adminAuditState.items)
		);

	// Remove the problematic formatTime function - using formatLocalDateTime from imports instead
</script>

<div class="page">
	<header class="header">
		<div>
			<h1>Audit Logs</h1>
			<p class="muted">Audit-trail rows come from the server log · record-creation rows are derived from roster created_at</p>
		</div>
		<div class="header-actions">
			<button class="btn btn-secondary" onclick={() => (pendingExport = { run: () => window.print(), title: 'Confirm Print', message: 'Are you sure you want to print this data? Your browser’s print dialog will open after you confirm.', confirmLabel: 'Confirm Print', details: [{ label: 'Format', value: 'Print' }] })}>Print</button>
			<button class="btn btn-primary" data-testid="export-logs" onclick={() => (pendingExport = { run: onExport, details: [{ label: 'Format', value: 'CSV' }, { label: 'Rows', value: String(adminAuditState.items.length) }] })}>Export Logs</button>
		</div>
	</header>

	<nav class="tabs" aria-label="Audit sections">
		{#each TABS as t (t.id)}
			<button class:active={tab === t.id} onclick={() => (tab = t.id)}>{t.label}</button>
		{/each}
	</nav>

	{#if tab === 'log'}
		<section class="card filters" aria-label="Audit filters">
			<input class="input" type="date" aria-label="From date" bind:value={dateFrom} />
			<input class="input" type="date" aria-label="To date" bind:value={dateTo} />
			<select class="input" aria-label="Entity type filter" bind:value={entityType}>
				<option value="">All entities</option>
				{#each AUDIT_ENTITY_TYPES as c (c.id)}
					<option value={c.id}>{c.label}</option>
				{/each}
			</select>
			<select class="input" aria-label="Action filter" bind:value={action}>
				<option value="">All actions</option>
				{#each AUDIT_ACTIONS as a (a.id)}
					<option value={a.id}>{a.label}</option>
				{/each}
			</select>
			<input
				class="input search"
				type="search"
				placeholder="Actor (e.g. Admin, system)…"
				aria-label="Filter by actor"
				bind:value={performedBy}
				onkeydown={(e) => {
					if (e.key === 'Enter') applyFilters();
				}}
			/>
			<button class="btn btn-secondary" data-testid="apply" onclick={applyFilters}>Apply</button>
			{#if formError}
				<p class="error" role="alert">{formError}</p>
			{/if}
		</section>

		{#if adminAuditState.loading && adminAuditState.items.length === 0}
			<section class="card"><p class="muted">Loading…</p></section>
		{:else if adminAuditState.error}
			<section class="card"><p class="error">Could not load audit logs: {adminAuditState.error}</p></section>
		{:else if visibleItems.length === 0}
			<section class="card">
				<p class="empty">No log entries match these filters.</p>
			</section>
		{:else}
			<section class="card table-wrap" aria-busy={adminAuditState.loading}>
				<table>
					<thead>
						<tr>
<th scope="col" aria-sort={ariaSort('time')}>
							<button class="th-btn" type="button" onclick={() => toggleSort('time')} aria-label={sortLabel('time', 'Time')}>
								Time<span aria-hidden="true">{sortArrow('time')}</span>
							</button>
						</th>
						<th scope="col" aria-sort={ariaSort('user')}>
							<button class="th-btn" type="button" onclick={() => toggleSort('user')} aria-label={sortLabel('user', 'User')}>
								User<span aria-hidden="true">{sortArrow('user')}</span>
							</button>
						</th>
						<th scope="col" aria-sort={ariaSort('action')}>
							<button class="th-btn" type="button" onclick={() => toggleSort('action')} aria-label={sortLabel('action', 'Action')}>
								Action<span aria-hidden="true">{sortArrow('action')}</span>
							</button>
						</th>
						</tr>
					</thead>
					<tbody>
						{#each visibleItems as r (r.id)}
							<tr>
								<td class="nowrap">{formatLocalDateTime(r.performed_at)}</td>
								<td>
									<div class="strong">{actorLabel(r)}</div>
									<div class="muted small">{entityLabel(r)}</div>
								</td>
								<td>
									<div>
										<span class="badge">{categoryLabel(r.entity_type)}</span>
										{#if r.origin === 'system'}
											<span class="badge live">system record</span>
										{/if}
									</div>
									<div class="strong">{r.action.replace(/_/g, ' ')}</div>
									<div class="muted small">{changeLabel(r)}</div>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
				<div class="pager">
					<button
						class="btn btn-secondary"
						disabled={adminAuditState.page <= 1}
						onclick={() => load(adminAuditState.page - 1)}
					>
						‹ Prev
					</button>
					<span class="muted">Page {adminAuditState.page} of {totalPages} · {adminAuditState.total} entries</span>
					<button
						class="btn btn-secondary"
						disabled={adminAuditState.page >= totalPages}
						onclick={() => load(adminAuditState.page + 1)}
					>
						Next ›
					</button>
				</div>
			</section>
		{/if}
	{:else}
		<section class="card">
			<div class="row-head">
				<div>
					<h2 class="card-title">Academic Structure Changes</h2>
					<p class="muted">Manual, intentional, audited mutations (D38) — manage them in Program Management.</p>
				</div>
				<button class="btn btn-secondary" onclick={() => goto(Routes.ADMIN_PROGRAMS)}>Edit Programs →</button>
			</div>
			{#if adminStructureState.loading && adminStructureState.items.length === 0}
				<p class="muted">Loading…</p>
			{:else if adminStructureState.error}
				<p class="error">{adminStructureState.error}</p>
			{:else if adminStructureState.items.length === 0}
				<p class="empty">No structural changes recorded.</p>
			{:else}
				<div class="table-wrap" aria-busy={adminStructureState.loading}>
					<table>
						<thead>
							<tr><th>When</th><th>Action</th><th>Entity</th><th>Change</th><th>By</th></tr>
						</thead>
						<tbody>
							{#each adminStructureState.items as c (c.id)}
								<tr>
									<td class="nowrap">{formatLocalDateTime(c.performed_at)}</td>
									<td class="strong">{c.action.replace(/_/g, ' ')}</td>
									<td>{c.entity_type} #{c.entity_id}</td>
									<td>
										{#if c.old_value}
											<span class="muted small">{c.old_value} → </span>
										{/if}
										<span class="strong">{c.new_value ?? '—'}</span>
									</td>
									<td>{c.performed_by}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</section>
	{/if}
	{#if pendingExport}
		<ConfirmExportDialog
			title={pendingExport.title}
			message={pendingExport.message}
			confirmLabel={pendingExport.confirmLabel}
			busyLabel={pendingExport.busyLabel}
			details={pendingExport.details}
			onconfirm={pendingExport.run}
			onclose={() => (pendingExport = null)}
		/>
	{/if}
</div>

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

	.muted.small {
		font-size: 0.75rem;
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

	.card-title {
		margin: 0 0 0.375rem;
		font-size: 1.125rem;
		font-weight: 700;
		color: var(--text);
	}

	.row-head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
		margin-bottom: 1rem;
	}

	.tabs {
		display: flex;
		gap: 0.25rem;
		border-bottom: 2px solid var(--border);
	}

	.tabs button {
		background: none;
		border: none;
		padding: 0.625rem 1rem;
		font-size: 0.9375rem;
		font-weight: 600;
		font-family: inherit;
		color: var(--text-muted);
		cursor: pointer;
		border-bottom: 2px solid transparent;
		margin-bottom: -2px;
	}

	.tabs button:hover {
		color: var(--text-strong);
	}

	.tabs button.active {
		color: var(--brand);
		border-bottom-color: var(--brand);
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
		flex: 1 1 200px;
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
		vertical-align: top;
	}

	th {
		color: var(--text-muted);
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.nowrap {
		white-space: nowrap;
	}

	.strong {
		font-weight: 700;
	}

	td .strong {
		font-size: 0.875rem;
	}

	.th-btn {
		background: none;
		border: none;
		padding: 0;
		font: inherit;
		color: inherit;
		cursor: pointer;
		white-space: nowrap;
	}

	.th-btn:hover {
		color: var(--text-strong);
	}

	.th-btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
		border-radius: 4px;
	}

	.badge {
		display: inline-block;
		padding: 0.125rem 0.5rem;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--brand);
		background: var(--info-bg);
		margin: 0 0.375rem 0.25rem 0;
	}

	.badge.live {
		color: var(--success);
		background: var(--success-bg);
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
		margin: 0;
		flex-basis: 100%;
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

	.table-wrap {
		overflow-x: auto;
	}

	@media (max-width: 640px) {
		.card {
			padding: 1.25rem;
		}
	}
</style>
