<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import ConfirmExportDialog from '$lib/components/ConfirmExportDialog.svelte';
	import {
		adminAuditState,
		adminStructureState,
		auditLabelContext,
		initAdminAudit,
		initStructureChanges,
		type AuditSortColumn,
	} from '$lib/features/admin/audit/store.svelte';
	import {
		AUDIT_ACTIONS,
		AUDIT_ENTITY_TYPES,
		downloadCsv,
	} from '$lib/features/admin/audit/service';
	import {
		AUDIT_ENTITY_LABELS,
		auditCsv,
		buildRowView,
		type AuditRowView,
	} from '$lib/features/admin/audit/present';
	import { auditFilterSchema } from '$lib/features/admin/audit/schema';
	import { Routes } from '$lib/shared/constants/routes';
	import { formatTime, formatUTCTimestamp } from '$lib/shared/utils/format';
	import type { AuditAction, AuditEntityType } from '$lib/shared/types';

	// Admin Audit Logs (wireframe 4.8, `/admin/audit-logs`).
	//
	// Two tabs over the same audit trail:
	//
	// - "Action Log" — every recorded action, newest first. The actor is a
	//   name, the action is a verb, the subject is a record name, and the
	//   change is a field-level diff. The stored values stay one click away,
	//   because an administrator investigating a change sometimes needs the
	//   exact snapshot.
	// - "Academic Structure" — the structural slice of the same trail
	//   (program / year level / course / offering), on its own pager.
	//
	// The two row sources are kept apart. The trail is what the server
	// recorded; the roster rows are an inference from a record's creation
	// date, which is useful but is not evidence, so they are shown in their
	// own block under their own heading.

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
	let actorId = $state('');
	let formError = $state<string | null>(null);
	/** The row whose stored values are shown. */
	let expanded = $state<number | null>(null);

	let pendingExport = $state<null | {
		run: () => void | Promise<void>;
		details?: { label: string; value: string }[];
		title?: string;
		message?: string;
		confirmLabel?: string;
		busyLabel?: string;
	}>(null);

	// --- Rows ---------------------------------------------------------------

	// The name lookups live in a plain resolver, so `labelVersion` is the
	// dependency that tells a derived to recompute once they land.
	const views = $derived.by(() => {
		adminAuditState.labelVersion;
		const ctx = auditLabelContext();
		return adminAuditState.all.map((row) => buildRowView(row, ctx));
	});

	const trailViews = $derived(views.filter((v) => v.origin === 'trail'));
	const rosterViews = $derived(views.filter((v) => v.origin === 'roster'));

	// Sorting runs across everything loaded, then the page is sliced — so
	// the ordering is not confined to one page of results.
	const sortedTrail = $derived.by(() => {
		const items = [...trailViews];
		const dir = adminAuditState.sortDir === 'asc' ? 1 : -1;
		const key =
			adminAuditState.sortBy === 'time'
				? (v: AuditRowView) => v.occurredAt
				: adminAuditState.sortBy === 'user'
					? (v: AuditRowView) => v.actor.name.toLowerCase()
					: (v: AuditRowView) => v.action.label.toLowerCase();
		items.sort((a, b) => key(a).localeCompare(key(b)) * dir);
		return items;
	});

	const sortedRoster = $derived.by(() => {
		const items = [...rosterViews];
		items.sort((a, b) => (a.occurredAt < b.occurredAt ? 1 : -1));
		return items;
	});

	const totalPages = $derived(
		Math.max(1, Math.ceil(sortedTrail.length / adminAuditState.size))
	);

	const pagedTrail = $derived(
		sortedTrail.slice(
			(adminAuditState.page - 1) * adminAuditState.size,
			adminAuditState.page * adminAuditState.size
		)
	);

	// --- Structure rows -----------------------------------------------------

	const structureViews = $derived.by(() => {
		adminAuditState.labelVersion;
		const ctx = auditLabelContext();
		return adminStructureState.items.map((row) =>
			buildRowView({ ...row, origin: 'trail' as const }, ctx)
		);
	});

	const structurePages = $derived(
		Math.max(1, Math.ceil(adminStructureState.total / adminStructureState.size))
	);

	// --- Actor options ------------------------------------------------------

	const actorOptions = $derived.by(() => {
		adminAuditState.labelVersion;
		return [...auditLabelContext().users.entries()]
			.map(([id, user]) => ({ id, ...user }))
			.sort((a, b) => a.name.localeCompare(b.name));
	});

	// --- Day grouping -------------------------------------------------------

	const dayHeading = (iso: string): string => {
		const date = new Date(iso);
		if (Number.isNaN(date.getTime())) return 'Unknown date';
		const today = new Date();
		const yesterday = new Date();
		yesterday.setDate(today.getDate() - 1);
		const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();
		if (sameDay(date, today)) return 'Today';
		if (sameDay(date, yesterday)) return 'Yesterday';
		return date.toLocaleDateString(undefined, {
			weekday: 'short',
			year: 'numeric',
			month: 'short',
			day: 'numeric',
		});
	};

	const grouped = $derived.by(() => {
		const groups: { heading: string; rows: AuditRowView[] }[] = [];
		for (const view of pagedTrail) {
			const heading = dayHeading(view.occurredAt);
			const last = groups[groups.length - 1];
			if (last && last.heading === heading) last.rows.push(view);
			else groups.push({ heading, rows: [view] });
		}
		return groups;
	});

	// --- Loading ------------------------------------------------------------

	const load = async (page = 1) => {
		expanded = null;
		// The backend types `performed_by` as an int, so only a real id is
		// ever sent. A half-typed value is dropped rather than turned into a
		// request the server would reject.
		const actor = Number(actorId);
		await initAdminAudit(
			{
				date_from: dateFrom.trim() || undefined,
				date_to: dateTo.trim() || undefined,
				entity_type: (entityType || undefined) as AuditEntityType | undefined,
				action: (action || undefined) as AuditAction | undefined,
				performed_by: actorId && Number.isFinite(actor) && actor > 0 ? actor : undefined,
			},
			page
		);
	};

	onMount(async () => {
		await load(1);
		await initStructureChanges(1, adminStructureState.size);
	});

	const applyFilters = async () => {
		formError = null;
		const parsed = auditFilterSchema.safeParse({
			date_from: dateFrom,
			date_to: dateTo,
			entity_type: entityType,
			action,
			performed_by: actorId,
		});
		if (!parsed.success) {
			formError = parsed.error.issues[0]?.message ?? 'Check the filters and try again.';
			return;
		}
		await load(1);
	};

	const clearFilters = async () => {
		dateFrom = '';
		dateTo = '';
		entityType = '';
		action = '';
		actorId = '';
		formError = null;
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

	const toggleDetails = (id: number) => {
		expanded = expanded === id ? null : id;
	};

	const jsonBlock = (value: Record<string, unknown> | null): string =>
		value === null ? '—' : JSON.stringify(value, null, 2);

	const onExport = () =>
		downloadCsv(
			`audit-logs-${new Date().toISOString().slice(0, 10)}.csv`,
			auditCsv(sortedTrail)
		);
</script>

<div class="page">
	<header class="header">
		<div>
			<h1>Audit Logs</h1>
			<p class="muted">
				Every change recorded by the system, who made it, and what it changed.
			</p>
		</div>
		<div class="header-actions">
			<button class="btn btn-secondary" onclick={() => (pendingExport = { run: () => window.print(), title: 'Confirm Print', message: 'Are you sure you want to print this data? Your browser’s print dialog will open after you confirm.', confirmLabel: 'Confirm Print', details: [{ label: 'Format', value: 'Print' }] })}>Print</button>
			<button class="btn btn-primary" data-testid="export-logs" onclick={() => (pendingExport = { run: onExport, details: [{ label: 'Format', value: 'CSV' }, { label: 'Rows', value: String(sortedTrail.length) }] })}>Export Logs</button>
		</div>
	</header>

	<nav class="tabs" aria-label="Audit sections">
		{#each TABS as t (t.id)}
			<button class:active={tab === t.id} onclick={() => (tab = t.id)}>{t.label}</button>
		{/each}
	</nav>

	{#if tab === 'log'}
		<section class="card filters" aria-label="Audit filters">
			<label class="field">
				<span>From (UTC)</span>
				<input class="input" type="date" bind:value={dateFrom} />
			</label>
			<label class="field">
				<span>To (UTC)</span>
				<input class="input" type="date" bind:value={dateTo} />
			</label>
			<label class="field">
				<span>Record type</span>
				<select class="input" bind:value={entityType}>
					<option value="">All records</option>
					{#each AUDIT_ENTITY_TYPES as c (c.id)}
						<option value={c.id}>{c.label}</option>
					{/each}
				</select>
			</label>
			<label class="field">
				<span>Action</span>
				<select class="input" bind:value={action}>
					<option value="">All actions</option>
					{#each AUDIT_ACTIONS as a (a.id)}
						<option value={a.id}>{a.label}</option>
					{/each}
				</select>
			</label>
			{#if adminAuditState.actorNamesAvailable}
				<label class="field">
					<span>Actor</span>
					<select class="input" bind:value={actorId}>
						<option value="">All actors</option>
						{#each actorOptions as u (u.email)}
							<option value={String(u.id)}>{u.name} — {u.role}</option>
						{/each}
					</select>
				</label>
			{:else}
				<label class="field">
					<span>Actor id</span>
					<input
						class="input"
						type="number"
						min="1"
						placeholder="User id"
						bind:value={actorId}
					/>
				</label>
			{/if}
			<div class="filter-actions">
				<button class="btn btn-secondary" data-testid="apply" onclick={applyFilters}>Apply</button>
				<button class="btn btn-secondary" onclick={clearFilters}>Clear</button>
			</div>
			{#if formError}
				<p class="error" role="alert">{formError}</p>
			{/if}
		</section>

		{#if !adminAuditState.actorNamesAvailable}
			<p class="note">
				Actor names are only visible to super-admins, so account changes are shown
				by user id.
			</p>
		{/if}
		{#if adminAuditState.labelsPartial}
			<p class="note">
				There are more records than one page can load, so some names are missing
				and fall back to their id. Narrow the date range to see the rest.
			</p>
		{/if}

		{#if adminAuditState.loading && adminAuditState.all.length === 0}
			<section class="card"><p class="muted">Loading…</p></section>
		{:else if adminAuditState.error}
			<section class="card"><p class="error">Could not load audit logs: {adminAuditState.error}</p></section>
		{:else if sortedTrail.length === 0 && sortedRoster.length === 0}
			<section class="card">
				<p class="empty">No changes match these filters.</p>
			</section>
		{:else}
			<section class="card table-wrap" aria-busy={adminAuditState.loading}>
				<table>
					<thead>
						<tr>
							<th scope="col" aria-sort={ariaSort('time')}>
								<button class="th-btn" type="button" onclick={() => toggleSort('time')} aria-label={sortLabel('time', 'When')}>
									When<span aria-hidden="true">{sortArrow('time')}</span>
								</button>
							</th>
							<th scope="col" aria-sort={ariaSort('user')}>
								<button class="th-btn" type="button" onclick={() => toggleSort('user')} aria-label={sortLabel('user', 'Actor')}>
									Actor<span aria-hidden="true">{sortArrow('user')}</span>
								</button>
							</th>
							<th scope="col" aria-sort={ariaSort('action')}>
								<button class="th-btn" type="button" onclick={() => toggleSort('action')} aria-label={sortLabel('action', 'Action')}>
									Action<span aria-hidden="true">{sortArrow('action')}</span>
								</button>
							</th>
							<th scope="col">Record</th>
							<th scope="col">Changes</th>
							<th scope="col"><span class="sr-only">Details</span></th>
						</tr>
					</thead>
					<tbody>
						{#each grouped as group (group.heading)}
							<tr class="day-head">
								<td colspan="6">{group.heading}</td>
							</tr>
							{#each group.rows as view (view.id)}
								<tr>
									<td class="nowrap">
										<div class="mono-data when-time">{formatTime(view.occurredAt)}</div>
										<div class="muted small" title={formatUTCTimestamp(view.occurredAt)}>
											{dayHeading(view.occurredAt)}
										</div>
									</td>
									<td>
										<div class="strong">{view.actor.name}</div>
										{#if view.actor.role}
											<div class="muted small">{view.actor.role.replace(/_/g, ' ')}</div>
										{/if}
									</td>
									<td>
										<span class="chip tone-{view.action.tone}">{view.action.label}</span>
										<div class="muted small">{view.summary}</div>
									</td>
									<td>
										<div class="strong">
											{#if view.entity.href}
												<a class="link" href={view.entity.href}>{view.entity.label}</a>
											{:else}
												{view.entity.label}
											{/if}
										</div>
										{#if view.entity.sublabel}
											<div class="muted small">{view.entity.sublabel}</div>
										{/if}
										<div class="muted small mono-data" title="The stored record reference">
											{AUDIT_ENTITY_LABELS[view.entity.type]}
											{view.entity.id === null ? '' : ` #${view.entity.id}`}
										</div>
									</td>
									<td>
										{#if view.changes.length > 0}
											<ul class="changes">
												{#each view.changes as change (change.field)}
													<li>
														<span class="field-label">{change.label}</span>
														{#if change.before !== '—'}
															<span class="before">{change.before}</span>
														{/if}
														{#if change.before !== '—' && change.after !== '—'}
															<span class="arrow" aria-label="changed to">→</span>
														{/if}
														{#if change.after !== '—'}
															<span class="after">{change.after}</span>
														{/if}
													</li>
												{/each}
											</ul>
										{:else}
											<span class="muted small">No field values recorded</span>
										{/if}
									</td>
									<td class="toggle-cell">
										<button
											class="icon-btn"
											type="button"
											aria-expanded={expanded === view.id}
											aria-label={expanded === view.id ? `Hide the stored values for this change` : `Show the stored values for this change`}
											onclick={() => toggleDetails(view.id)}
										>
											<AppIcon name="chevron" size={18} />
										</button>
									</td>
								</tr>
								<tr class="detail-row" class:open={expanded === view.id}>
									<td colspan="6">
										<div class="detail-grid">
											<div>
												<h4>Before</h4>
												<pre class="raw">{jsonBlock(view.raw.old_value)}</pre>
											</div>
											<div>
												<h4>After</h4>
												<pre class="raw">{jsonBlock(view.raw.new_value)}</pre>
											</div>
										</div>
										<p class="muted small">
											Entry #{view.id} · recorded {formatUTCTimestamp(view.occurredAt)} ·
											{AUDIT_ENTITY_LABELS[view.entity.type]}
											{view.entity.id === null ? '' : ` #${view.entity.id}`}
										</p>
									</td>
								</tr>
							{/each}
						{/each}
					</tbody>
				</table>
				<div class="pager">
					<button
						class="btn btn-secondary"
						disabled={adminAuditState.page <= 1}
						onclick={() => (adminAuditState.page = adminAuditState.page - 1)}
					>
						‹ Prev
					</button>
					<span class="muted">
						Page {adminAuditState.page} of {totalPages} · {sortedTrail.length} audited change{sortedTrail.length === 1 ? '' : 's'}
					</span>
					<button
						class="btn btn-secondary"
						disabled={adminAuditState.page >= totalPages}
						onclick={() => (adminAuditState.page = adminAuditState.page + 1)}
					>
						Next ›
					</button>
				</div>
				{#if adminAuditState.trailTotal > adminAuditState.trailLoaded}
					<p class="muted small">
						Showing the {adminAuditState.trailLoaded} most recent of {adminAuditState.trailTotal} matching
						audit entries. Narrow the date range to reach older ones.
					</p>
				{/if}
			</section>

			{#if sortedRoster.length > 0}
				<section class="card table-wrap">
					<div class="row-head">
						<div>
							<h2 class="card-title">Recently added records</h2>
							<p class="muted">
								Inferred from each record's creation date — these are not audited events.
							</p>
						</div>
					</div>
					<table>
						<thead>
							<tr>
								<th scope="col">When</th>
								<th scope="col">Action</th>
								<th scope="col">Record</th>
							</tr>
						</thead>
						<tbody>
							{#each sortedRoster as view (view.id)}
								<tr>
									<td class="nowrap">
										<div class="mono-data when-time">{formatTime(view.occurredAt)}</div>
										<div class="muted small">{dayHeading(view.occurredAt)}</div>
									</td>
									<td>
										<span class="chip tone-create">{view.action.label}</span>
										<div class="muted small">Added</div>
									</td>
									<td>
										<div class="strong">
											{#if view.entity.href}
												<a class="link" href={view.entity.href}>{view.entity.label}</a>
											{:else}
												{view.entity.label}
											{/if}
										</div>
										{#if view.entity.sublabel}
											<div class="muted small">{view.entity.sublabel}</div>
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
					{#if adminAuditState.rosterTruncated}
						<p class="muted small">
							Only the most recent {adminAuditState.rosterCount} additions are shown — the scan is
							capped, so older records are not listed here.
						</p>
					{/if}
				</section>
			{/if}
		{/if}
	{:else}
		<section class="card">
			<div class="row-head">
				<div>
					<h2 class="card-title">Academic Structure Changes</h2>
					<p class="muted">
						Changes to programs, year levels, courses and offerings. Manage them in Program
						Management.
					</p>
				</div>
				<button class="btn btn-secondary" onclick={() => goto(Routes.ADMIN_PROGRAMS)}>Edit Programs →</button>
			</div>
			{#if adminStructureState.loading && adminStructureState.items.length === 0}
				<p class="muted">Loading…</p>
			{:else if adminStructureState.error}
				<p class="error">{adminStructureState.error}</p>
			{:else if structureViews.length === 0}
				<p class="empty">No structural changes recorded.</p>
			{:else}
				<div class="table-wrap" aria-busy={adminStructureState.loading}>
					<table>
						<thead>
							<tr>
								<th scope="col">When</th>
								<th scope="col">Change</th>
								<th scope="col">Record</th>
								<th scope="col">Details</th>
								<th scope="col">By</th>
							</tr>
						</thead>
						<tbody>
							{#each structureViews as view (view.id)}
								<tr>
									<td class="nowrap">
										<div class="mono-data when-time">{formatTime(view.occurredAt)}</div>
										<div class="muted small" title={formatUTCTimestamp(view.occurredAt)}>
											{dayHeading(view.occurredAt)}
										</div>
									</td>
									<td>
										<span class="chip tone-{view.action.tone}">{view.action.label}</span>
										<div class="muted small">{view.summary}</div>
									</td>
									<td>
										<div class="strong">
											{#if view.entity.href}
												<a class="link" href={view.entity.href}>{view.entity.label}</a>
											{:else}
												{view.entity.label}
											{/if}
										</div>
										{#if view.entity.sublabel}
											<div class="muted small">{view.entity.sublabel}</div>
										{/if}
									</td>
									<td>
										{#if view.changes.length > 0}
											<ul class="changes">
												{#each view.changes as change (change.field)}
													<li>
														<span class="field-label">{change.label}</span>
														{#if change.before !== '—'}
															<span class="before">{change.before}</span>
														{/if}
														{#if change.before !== '—' && change.after !== '—'}
															<span class="arrow" aria-label="changed to">→</span>
														{/if}
														{#if change.after !== '—'}
															<span class="after">{change.after}</span>
														{/if}
													</li>
												{/each}
											</ul>
										{:else}
											<span class="muted small">No field values recorded</span>
										{/if}
									</td>
									<td>
										<div class="strong">{view.actor.name}</div>
										{#if view.actor.role}
											<div class="muted small">{view.actor.role.replace(/_/g, ' ')}</div>
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
				<div class="pager">
					<button
						class="btn btn-secondary"
						disabled={adminStructureState.page <= 1}
						onclick={() => initStructureChanges(adminStructureState.page - 1, adminStructureState.size)}
					>
						‹ Prev
					</button>
					<span class="muted">
						Page {adminStructureState.page} of {structurePages} · {adminStructureState.total} change{adminStructureState.total === 1 ? '' : 's'}
					</span>
					<button
						class="btn btn-secondary"
						disabled={adminStructureState.page >= structurePages}
						onclick={() => initStructureChanges(adminStructureState.page + 1, adminStructureState.size)}
					>
						Next ›
					</button>
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
		font-family: var(--font-ui);
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
		gap: 0.875rem;
		flex-wrap: wrap;
		align-items: flex-end;
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.field > span {
		font-size: 0.6875rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.filter-actions {
		display: flex;
		gap: 0.5rem;
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

	.when-time {
		font-size: 0.9375rem;
		font-weight: 600;
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

	.day-head td {
		background: var(--bg-muted);
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.chip {
		display: inline-block;
		padding: 0.125rem 0.5rem;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 600;
		margin: 0 0.375rem 0.25rem 0;
		background: var(--info-bg);
		color: var(--info-text);
		white-space: nowrap;
	}

	.chip.tone-create {
		background: var(--success-bg);
		color: var(--success);
	}

	.chip.tone-update {
		background: var(--info-bg);
		color: var(--info-text);
	}

	.chip.tone-remove {
		background: var(--danger-bg);
		color: var(--danger);
	}

	.chip.tone-security {
		background: var(--warning-bg);
		color: var(--warning-text);
	}

	.chip.tone-automation {
		background: var(--bg-muted);
		color: var(--text-secondary);
	}

	.changes {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.changes li {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.375rem;
	}

	.field-label {
		font-size: 0.6875rem;
		font-weight: 700;
		letter-spacing: 0.03em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.before {
		color: var(--text-muted);
		text-decoration: line-through;
		text-decoration-color: var(--border-strong);
	}

	.after {
		font-weight: 600;
		color: var(--text-strong);
	}

	.arrow {
		color: var(--text-muted);
	}

	.link {
		color: var(--accent);
		text-decoration: none;
	}

	.link:hover {
		text-decoration: underline;
	}

	.toggle-cell {
		width: 2rem;
		text-align: center;
	}

	.icon-btn {
		background: none;
		border: 1px solid transparent;
		border-radius: 6px;
		padding: 0.25rem;
		color: var(--text-muted);
		cursor: pointer;
		display: inline-flex;
	}

	.icon-btn:hover {
		background: var(--bg-hover);
		color: var(--text-strong);
	}

	.icon-btn[aria-expanded='true'] {
		background: var(--bg-hover);
		color: var(--text-strong);
	}

	.icon-btn :global(svg) {
		transform: rotate(-90deg);
		transition: transform 0.15s ease;
	}

	.icon-btn[aria-expanded='true'] :global(svg) {
		transform: rotate(0deg);
	}

	.detail-row {
		display: none;
	}

	.detail-row.open {
		display: table-row;
	}

	.detail-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
		gap: 1rem;
	}

	.detail-grid h4 {
		margin: 0 0 0.375rem;
		font-size: 0.6875rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.raw {
		margin: 0;
		padding: 0.625rem 0.75rem;
		background: var(--bg-muted);
		border-radius: 6px;
		font-family: var(--font-data);
		font-size: 0.75rem;
		line-height: 1.5;
		white-space: pre-wrap;
		word-break: break-word;
		max-height: 18rem;
		overflow: auto;
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

	.note {
		margin: 0;
		padding: 0.625rem 0.875rem;
		background: var(--info-bg);
		color: var(--info-text);
		border-radius: 8px;
		font-size: 0.875rem;
	}

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0;
		flex-basis: 100%;
	}

	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		padding: 0;
		margin: -1px;
		overflow: hidden;
		clip: rect(0, 0, 0, 0);
		white-space: nowrap;
		border: 0;
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

	/* The stored values are the last resort, but a printed audit trail that
	   omits them is not the same evidence. Printing shows every one. */
	@media print {
		.detail-row {
			display: table-row !important;
		}
	}
</style>
