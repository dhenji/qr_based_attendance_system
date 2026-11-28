<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte';
	import SkeletonTable from '$lib/components/SkeletonTable.svelte';
	import {
		adminOfferingDetailState,
		assignOfferingProfessor,
		endOfferingAssignment,
		permanentlyRemoveOfferingAssignment,
		reassignOfferingProfessor,
		reopenOfferingAssignment,
	} from '$lib/features/admin/offerings/store.svelte';
	import type { AssignmentCreateInput, AssignmentReassignInput } from '$lib/features/admin/offerings/schema';
	import { assignmentCreateSchema, assignmentReassignSchema } from '$lib/features/admin/offerings/schema';
	import { trapFocus } from '$lib/shared/actions/focusTrap';
	import type { AdminAssignment, AdminOffering, AdminProfessor } from '$lib/shared/types';

	// Professor assignments (detail page, Professors tab). Assignments carry
	// effective dating (D7-D9); ending sets effective_to=today and history is
	// never rewritten. Seven confirmation flows live here: assign form ->
	// confirm, reassign form -> confirm, end, reopen, permanent remove.

	interface Props {
		offering: AdminOffering;
		professors: Map<number, AdminProfessor>;
	}

	let { offering, professors }: Props = $props();

	const isoToday = (): string => new Date().toISOString().slice(0, 10);

	const addDaysIso = (iso: string, days: number): string => {
		const date = new Date(`${iso}T00:00:00Z`);
		date.setUTCDate(date.getUTCDate() + days);
		return date.toISOString().slice(0, 10);
	};

	const professorName = (id: number): string => {
		const p = professors.get(id);
		return p ? [p.firstName, p.middleName, p.lastName].filter(Boolean).join(' ') : `Professor ${id}`;
	};

	const professorEmail = (id: number): string => professors.get(id)?.email ?? '';

	// Assign-professor form.
	let assignOpen = $state(false);
	let a_professor_id = $state('');
	let a_primary = $state(false);
	let a_from = $state('');
	let a_to = $state('');
	let assignError = $state<string | null>(null);
	let assignBusy = $state(false);
	let assignConfirmOpen = $state(false);
	let pendingAssign = $state<AssignmentCreateInput | null>(null);

	// Reassign-professor form.
	let reassignOpen = $state(false);
	let reassignTarget = $state<AdminAssignment | null>(null);
	let r_new_professor_id = $state('');
	let r_primary = $state(false);
	let r_from = $state('');
	let r_to = $state('');
	let reassignError = $state<string | null>(null);
	let reassignBusy = $state(false);
	let reassignConfirmOpen = $state(false);
	let pendingReassign = $state<AssignmentReassignInput | null>(null);

	// End-assignment confirmation.
	let endAssignmentTarget = $state<AdminAssignment | null>(null);
	let endAssignmentBusy = $state(false);
	const endAssignmentIsFuture = $derived(
		endAssignmentTarget ? endAssignmentTarget.effectiveFrom > isoToday() : false
	);

	// Reopen-assignment confirmation (undo an accidental End).
	let reopenTarget = $state<AdminAssignment | null>(null);
	let reopenBusy = $state(false);
	let reopenAsAssistant = $state(false);

	// Permanent removal is a correction path for assignments that never opened
	// a session. End remains the normal removal action.
	let permanentRemoveTarget = $state<AdminAssignment | null>(null);
	let permanentRemoveBusy = $state(false);

	const openAssign = () => {
		assignError = null;
		a_professor_id = '';
		a_primary = false;
		a_from = isoToday();
		a_to = '';
		assignOpen = true;
	};

	const submitAssign = () => {
		assignError = null;
		const parsed = assignmentCreateSchema.safeParse({
			professor_id: a_professor_id,
			is_primary: a_primary,
			effective_from: a_from,
			effective_to: a_to || undefined,
		});
		if (!parsed.success) {
			assignError = parsed.error.issues[0]?.message ?? 'Check the form and try again.';
			return;
		}
		pendingAssign = parsed.data;
		assignOpen = false;
		assignConfirmOpen = true;
	};

	const confirmAssign = async () => {
		if (!pendingAssign) return;
		assignBusy = true;
		try {
			await assignOfferingProfessor(offering.id, {
				professor_id: pendingAssign.professor_id,
				is_primary: pendingAssign.is_primary,
				effective_from: pendingAssign.effective_from,
				effective_to: pendingAssign.effective_to || undefined,
			});
			assignConfirmOpen = false;
			pendingAssign = null;
		} catch (e: unknown) {
			assignError = e instanceof Error && e.message ? e.message : 'Assign failed. Please try again.';
			assignConfirmOpen = false;
			assignOpen = true;
		} finally {
			assignBusy = false;
		}
	};

	const cancelAssignConfirm = () => {
		assignConfirmOpen = false;
		assignOpen = true;
	};

	const openReassign = (assignment: AdminAssignment) => {
		reassignError = null;
		reassignTarget = assignment;
		r_new_professor_id = '';
		r_primary = assignment.isPrimary;
		// A scheduled row may be replaced on its own start date. A started
		// row must be replaced later; a row that started today defaults to
		// tomorrow so the old assignment never gets an inverted range.
		const today = isoToday();
		r_from =
			assignment.effectiveFrom > today
				? assignment.effectiveFrom
				: assignment.effectiveFrom === today
					? addDaysIso(today, 1)
					: today;
		r_to = '';
		reassignOpen = true;
	};

	const submitReassign = () => {
		if (!reassignTarget) return;
		reassignError = null;
		const parsed = assignmentReassignSchema.safeParse({
			new_professor_id: r_new_professor_id,
			is_primary: r_primary,
			effective_from: r_from || undefined,
			effective_to: r_to || undefined,
		});
		if (!parsed.success) {
			reassignError = parsed.error.issues[0]?.message ?? 'Check the form and try again.';
			return;
		}
		pendingReassign = parsed.data;
		reassignOpen = false;
		reassignConfirmOpen = true;
	};

	const confirmReassign = async () => {
		if (!reassignTarget || !pendingReassign) return;
		reassignBusy = true;
		try {
			await reassignOfferingProfessor(offering.id, reassignTarget.professorId, {
				new_professor_id: pendingReassign.new_professor_id,
				is_primary: pendingReassign.is_primary,
				old_effective_from: reassignTarget.effectiveFrom,
				effective_from: pendingReassign.effective_from,
				effective_to: pendingReassign.effective_to || undefined,
			});
			reassignConfirmOpen = false;
			reassignTarget = null;
			pendingReassign = null;
		} catch (e: unknown) {
			reassignError = e instanceof Error && e.message ? e.message : 'Reassign failed. Please try again.';
			reassignConfirmOpen = false;
			reassignOpen = true;
		} finally {
			reassignBusy = false;
		}
	};

	const cancelReassignConfirm = () => {
		reassignConfirmOpen = false;
		reassignOpen = true;
	};

	const askEndAssignment = (assignment: AdminAssignment) => {
		adminOfferingDetailState.actionError = null;
		endAssignmentTarget = assignment;
	};

	const confirmEndAssignment = async () => {
		if (!endAssignmentTarget) return;
		endAssignmentBusy = true;
		try {
			await endOfferingAssignment(
				offering.id,
				endAssignmentTarget.professorId,
				endAssignmentTarget.effectiveFrom
			);
			endAssignmentTarget = null;
		} catch {
			// Surfaced via the detail state's actionError.
		} finally {
			endAssignmentBusy = false;
		}
	};

	const canReopenAssignment = (assignment: AdminAssignment): boolean =>
		!!assignment.effectiveTo &&
		!adminOfferingDetailState.assignments.some(
			(other) =>
				other.professorId === assignment.professorId &&
				other.effectiveFrom > assignment.effectiveFrom
		);

	const openReopen = (assignment: AdminAssignment) => {
		adminOfferingDetailState.actionError = null;
		reopenAsAssistant = false;
		reopenTarget = assignment;
	};

	const confirmReopen = async () => {
		if (!reopenTarget) return;
		reopenBusy = true;
		try {
			await reopenOfferingAssignment(
				offering.id,
				reopenTarget.professorId,
				reopenTarget.effectiveFrom,
				reopenTarget.isPrimary && reopenAsAssistant ? false : undefined
			);
			reopenTarget = null;
			reopenAsAssistant = false;
		} catch {
			// Surfaced via the detail state's actionError.
		} finally {
			reopenBusy = false;
		}
	};

	// Permanent removal is a post-End cleanup: End first, then erase a row
	// whose end date has arrived and that never opened a session. Rows with a
	// future end date are still live; ended rows with session history stay
	// visible but disabled, so the reason is on screen rather than in a 409.
	const isEndedAssignment = (assignment: AdminAssignment): boolean =>
		assignment.effectiveTo != null && assignment.effectiveTo <= isoToday();

	const canPermanentlyRemoveAssignment = (assignment: AdminAssignment): boolean =>
		isEndedAssignment(assignment) && !assignment.hasSessions;

	const askPermanentRemove = (assignment: AdminAssignment) => {
		adminOfferingDetailState.actionError = null;
		permanentRemoveTarget = assignment;
	};

	const confirmPermanentRemove = async () => {
		if (!permanentRemoveTarget) return;
		permanentRemoveBusy = true;
		try {
			await permanentlyRemoveOfferingAssignment(
				offering.id,
				permanentRemoveTarget.professorId,
				permanentRemoveTarget.effectiveFrom
			);
			permanentRemoveTarget = null;
		} catch {
			// Surfaced via the detail state's actionError.
		} finally {
			permanentRemoveBusy = false;
		}
	};
</script>

<section class="card">
	<div class="row-head">
		<h2 class="card-title">Assignments</h2>
		<button class="btn btn-primary" onclick={openAssign}>Assign professor</button>
	</div>
	{#if adminOfferingDetailState.assignmentsLoading}
		<SkeletonTable bare rows={3} cols={6} label="Loading assignments…" />
	{:else if adminOfferingDetailState.assignments.length === 0}
		<EmptyState
			icon="users"
			title="No professors assigned yet"
			hint="Any professor with an active assignment may open sessions for this offering."
		/>
	{:else}
		<div class="table-wrap">
			<table>
				<thead>
					<tr>
						<th scope="col">Professor</th>
						<th scope="col">Role</th>
						<th scope="col">Effective</th>
						<th scope="col">Semester</th>
						<th scope="col"><span class="sr">Actions</span></th>
					</tr>
				</thead>
				<tbody>
					{#each adminOfferingDetailState.assignments as a (`${a.professorId}:${a.effectiveFrom}`)}
						<tr>
							<td>
								<div class="strong">{professorName(a.professorId)}</div>
								<div class="muted small">{professorEmail(a.professorId)}</div>
							</td>
							<td>
								<span class="badge" class:inactive={!a.isPrimary}>
									{a.isPrimary ? 'Primary' : 'Assistant'}
								</span>
							</td>
							<td>{a.effectiveFrom} → {a.effectiveTo ?? 'ongoing'}</td>
							<td>{a.semester}</td>
							<td>
								<div class="row-actions">
									{#if !a.effectiveTo}
										<button class="link" onclick={() => openReassign(a)}>Reassign</button>
										<button class="link" onclick={() => askEndAssignment(a)}>End</button>
									{:else if canReopenAssignment(a)}
										<button class="link" onclick={() => openReopen(a)}>Reopen</button>
									{:else}
										<span class="muted small">ended</span>
									{/if}
									{#if isEndedAssignment(a)}
										<button
											class="link danger-link"
											disabled={!canPermanentlyRemoveAssignment(a)}
											title={a.hasSessions
												? 'This assignment has sessions; its history must be kept.'
												: 'Permanently erase this ended assignment. Only available when no sessions were opened under it.'}
											onclick={() => askPermanentRemove(a)}
										>
											Remove permanently
										</button>
									{/if}
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		<p class="hint">Mid-term replacement: use <strong>Reassign</strong> to hand the offering to another professor in one step. Only one primary professor may cover an offering at a time; assistants may overlap. Ending an assignment keeps it active through today; use <strong>Reopen</strong> on an ended row to undo an accidental end, or assign the same professor with a start date after the ended assignment. <strong>Remove permanently</strong> appears only after an assignment is ended; ended rows that opened a session keep their history and stay disabled.</p>
	{/if}
</section>

{#if assignOpen}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="assign-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (assignOpen = false) }}
		>
			<h2 id="assign-title" class="modal-title">Assign professor</h2>
			{#if assignError}
				<p class="error" role="alert">{assignError}</p>
			{/if}
			<div class="form">
				<label>Professor
					<select class="input" bind:value={a_professor_id}>
						<option value="">Pick a professor…</option>
						{#each [...professors.values()] as p (p.id)}
							<option value={p.id}>{p.firstName} {p.lastName} — {p.email}</option>
						{/each}
					</select>
				</label>
				<label class="check">
					<input type="checkbox" bind:checked={a_primary} /> Primary (uncheck for assistant)
				</label>
				<p class="hint">
					Only one primary professor can cover an offering at a time. Leave this unchecked to add an assistant.
				</p>
				<div class="grid2">
					<label>Effective from<input class="input" type="date" bind:value={a_from} /></label>
					<label>Effective to (optional)<input class="input" type="date" bind:value={a_to} /></label>
				</div>
				<p class="hint">Semester: <strong>{offering.semester}</strong></p>
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (assignOpen = false)}>Cancel</button>
				<button class="btn btn-primary" onclick={submitAssign}>
					Review assignment
				</button>
			</div>
		</div>
	</div>
{/if}

{#if assignConfirmOpen && pendingAssign}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="assign-confirm-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: cancelAssignConfirm }}
		>
			<h2 id="assign-confirm-title" class="modal-title">Assign this professor?</h2>
			<p class="modal-text">
				<strong>{professorName(pendingAssign.professor_id)}</strong> will be assigned to this offering as
				{pendingAssign.is_primary ? 'primary' : 'assistant'} from {pendingAssign.effective_from}
				{pendingAssign.effective_to ? ` to ${pendingAssign.effective_to}` : ''}.
			</p>
			<p class="muted">
				Semester: {offering.semester} · {offering.academicYear}
			</p>
			{#if assignError}
				<p class="error" role="alert">{assignError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={cancelAssignConfirm}>Back</button>
				<button class="btn btn-primary" disabled={assignBusy} onclick={confirmAssign}>
					{assignBusy ? 'Assigning…' : 'Confirm assign'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if reassignOpen && reassignTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="reassign-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (reassignOpen = false) }}
		>
			<h2 id="reassign-title" class="modal-title">Reassign professor</h2>
			{#if reassignError}
				<p class="error" role="alert">{reassignError}</p>
			{/if}
			<div class="form">
				<p class="hint">
					Current: <strong>{professorName(reassignTarget.professorId)}</strong> — {reassignTarget.effectiveFrom} → {reassignTarget.effectiveTo ?? 'ongoing'}
				</p>
				<label>Replacement professor
					<select class="input" bind:value={r_new_professor_id}>
						<option value="">Pick a professor…</option>
						{#each [...professors.values()] as p (p.id)}
							<option value={p.id} disabled={p.id === reassignTarget.professorId}>
								{p.firstName} {p.lastName} — {p.email}
							</option>
						{/each}
					</select>
				</label>
				<label class="check">
					<input type="checkbox" bind:checked={r_primary} /> Primary (uncheck for assistant)
				</label>
				<p class="hint">
					Only one primary professor can cover an offering at a time. Leave this unchecked to reassign as an assistant.
				</p>
				<div class="grid2">
					<label>Effective from<input class="input" type="date" bind:value={r_from} /></label>
					<label>Effective to (optional)<input class="input" type="date" bind:value={r_to} /></label>
				</div>
				<p class="hint">Semester: <strong>{offering.semester}</strong></p>
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (reassignOpen = false)}>Cancel</button>
				<button class="btn btn-primary" onclick={submitReassign}>
					Review reassignment
				</button>
			</div>
		</div>
	</div>
{/if}

{#if reassignConfirmOpen && pendingReassign && reassignTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="reassign-confirm-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: cancelReassignConfirm }}
		>
			<h2 id="reassign-confirm-title" class="modal-title">Reassign this professor?</h2>
			<p class="modal-text">
				<strong>{professorName(reassignTarget.professorId)}</strong> will be replaced by
				<strong>{professorName(pendingReassign.new_professor_id)}</strong> on this offering.
			</p>
			<p class="muted">
				New effective from {pendingReassign.effective_from ?? 'today'}
				{pendingReassign.effective_to ? ` to ${pendingReassign.effective_to}` : ''} · Semester {offering.semester}
			</p>
			{#if reassignError}
				<p class="error" role="alert">{reassignError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={cancelReassignConfirm}>Back</button>
				<button class="btn btn-primary" disabled={reassignBusy} onclick={confirmReassign}>
					{reassignBusy ? 'Reassigning…' : 'Confirm reassign'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if endAssignmentTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="end-assignment-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (endAssignmentTarget = null) }}
		>
			<h2 id="end-assignment-title" class="modal-title">
				{endAssignmentIsFuture ? 'Cancel this scheduled assignment?' : 'End this assignment?'}
			</h2>
			{#if endAssignmentIsFuture}
				<p class="modal-text">
					<strong>{professorName(endAssignmentTarget.professorId)}</strong>'s scheduled assignment starts on
					{endAssignmentTarget.effectiveFrom} and has not begun. Cancelling removes it from the offering.
				</p>
			{:else}
				<p class="modal-text">
					<strong>{professorName(endAssignmentTarget.professorId)}</strong> will remain assigned through today
					({isoToday()}). The assignment ends tomorrow; past sessions stay attributed to them. After ending,
					you can use <strong>Remove permanently</strong> on the ended row if no sessions were opened under it.
				</p>
			{/if}
			{#if adminOfferingDetailState.actionError}
				<p class="error" role="alert">{adminOfferingDetailState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (endAssignmentTarget = null)}>Back</button>
				<button class="btn btn-danger" disabled={endAssignmentBusy} onclick={confirmEndAssignment}>
					{endAssignmentBusy
						? endAssignmentIsFuture
							? 'Cancelling…'
							: 'Ending…'
						: endAssignmentIsFuture
							? 'Cancel assignment'
							: 'End assignment'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if reopenTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="reopen-assignment-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (reopenTarget = null) }}
		>
			<h2 id="reopen-assignment-title" class="modal-title">Reopen this assignment?</h2>
			<p class="modal-text">
				<strong>{professorName(reopenTarget.professorId)}</strong> will become active again on this offering
				from {reopenTarget.effectiveFrom} with no end date as
				<strong>{reopenTarget.isPrimary && !reopenAsAssistant ? 'primary' : 'assistant'}</strong>.
				This undoes the previous end action.
			</p>
			{#if reopenTarget.isPrimary}
				<label class="check">
					<input type="checkbox" bind:checked={reopenAsAssistant} /> Reopen as assistant
				</label>
				<p class="hint">
					Choose this if another professor is already primary for these dates.
				</p>
			{/if}
			{#if adminOfferingDetailState.actionError}
				<p class="error" role="alert">{adminOfferingDetailState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (reopenTarget = null)}>Back</button>
				<button class="btn btn-primary" disabled={reopenBusy} onclick={confirmReopen}>
					{reopenBusy ? 'Reopening…' : 'Reopen assignment'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if permanentRemoveTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="permanent-remove-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (permanentRemoveTarget = null) }}
		>
			<h2 id="permanent-remove-title" class="modal-title">Permanently remove this assignment?</h2>
			<p class="modal-text">
				<strong>{professorName(permanentRemoveTarget.professorId)}</strong>'s assignment from
				{permanentRemoveTarget.effectiveFrom} → {permanentRemoveTarget.effectiveTo ?? 'ongoing'}
				({offering.semester}) will be erased from history. This cannot be undone, and the
				assignment can no longer be reopened.
			</p>
			<p class="hint">
				Sessions are never deleted. If any session was opened under this assignment, the server
				blocks removal and you must use <strong>End</strong> instead.
			</p>
			{#if adminOfferingDetailState.actionError}
				<p class="error" role="alert">{adminOfferingDetailState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (permanentRemoveTarget = null)}>Back</button>
				<button
					class="btn btn-danger"
					disabled={permanentRemoveBusy}
					onclick={confirmPermanentRemove}
				>
					{permanentRemoveBusy ? 'Removing…' : 'Remove permanently'}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
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
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
		margin-bottom: 1rem;
	}

	.row-head .card-title {
		margin: 0;
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

	.strong {
		font-weight: 700;
	}

	td .strong {
		font-size: 0.875rem;
	}

	.muted {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0;
	}

	.muted.small {
		font-size: 0.75rem;
	}

	.badge {
		display: inline-block;
		padding: 0.125rem 0.5rem;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--success);
		background: var(--success-bg);
	}

	.badge.inactive {
		color: var(--text-muted);
		background: var(--divider);
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

	.danger-link {
		color: var(--danger);
	}

	.danger-link:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.danger-link:disabled:hover {
		text-decoration: none;
	}

	.hint {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin: 1rem 0 0;
	}

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0 0 1rem;
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

	.form label.check {
		flex-direction: row;
		align-items: center;
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

	.input:disabled {
		background: var(--divider);
		color: var(--text-muted);
		cursor: not-allowed;
	}

	.grid2 {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.875rem;
	}

	.table-wrap {
		overflow-x: auto;
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

	.modal-actions {
		display: flex;
		gap: 0.75rem;
		justify-content: flex-end;
		margin-top: 1.5rem;
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
