<script lang="ts">
	import { goto } from '$app/navigation';
	import {
		adminOfferingDetailState,
		adminOfferingsState,
		deleteArchivedOffering,
		refreshAdminOfferingDetail,
	} from '$lib/features/admin/offerings/store.svelte';
	import { setOfferingActive } from '$lib/features/admin/offerings/service';
	import type { WeeklyHoursBreakdown } from '$lib/shared/utils/schedule';
	import { Routes } from '$lib/shared/constants/routes';
	import { notifyEntityChanged } from '$lib/shared/utils/entityEvents';
	import { trapFocus } from '$lib/shared/actions/focusTrap';
	import type { AdminCourse, AdminOffering } from '$lib/shared/types';

	// Danger zone: archive -> reactivate -> permanent delete. Reactivation is
	// blocked while the weekly schedule is off the course-units requirement.

	interface Props {
		offering: AdminOffering;
		course: AdminCourse | null;
		breakdown: WeeklyHoursBreakdown | null;
	}

	let { offering, course, breakdown }: Props = $props();

	let archiveBusy = $state(false);
	let archiveConfirm = $state(false);
	let reactivateConfirm = $state(false);
	let deleteOpen = $state(false);
	let deleteBusy = $state(false);

	const onArchive = async () => {
		if (archiveBusy) return;
		archiveBusy = true;
		try {
			await setOfferingActive(offering.id, false);
			await refreshAdminOfferingDetail(offering.id);
			notifyEntityChanged('offerings');
		} catch (e: unknown) {
			adminOfferingDetailState.actionError =
				e instanceof Error && e.message ? e.message : 'Failed to archive offering';
		} finally {
			archiveBusy = false;
		}
	};

	const confirmArchive = async () => {
		await onArchive();
		if (adminOfferingDetailState.offering?.isActive === false) archiveConfirm = false;
	};

	const onReactivate = async () => {
		if (archiveBusy) return;
		archiveBusy = true;
		try {
			await setOfferingActive(offering.id, true);
			await refreshAdminOfferingDetail(offering.id);
			notifyEntityChanged('offerings');
		} catch (e: unknown) {
			adminOfferingDetailState.actionError =
				e instanceof Error && e.message ? e.message : 'Failed to reactivate offering';
		} finally {
			archiveBusy = false;
		}
	};

	const confirmDelete = async () => {
		if (deleteBusy) return;
		deleteBusy = true;
		try {
			await deleteArchivedOffering(offering.id);
			deleteOpen = false;
			notifyEntityChanged('offerings');
			await goto(Routes.ADMIN_OFFERINGS);
		} catch {
			// The store holds the friendly guard copy; mirror it onto the
			// detail state so the modal shows it on a direct landing.
			adminOfferingDetailState.actionError =
				adminOfferingsState.actionError ?? 'Failed to delete offering';
		} finally {
			deleteBusy = false;
		}
	};
</script>

<section class="card danger">
	<h2 class="card-title">Danger zone</h2>
	<p class="muted">
		Status: <strong>{offering.isActive ? 'Active' : 'Inactive'}</strong>. Archiving
		flips this offering to inactive — sessions history is kept. Reactivating
		restores it, but requires the weekly scheduled hours to match the course
		units requirement. Deletion is permanent and blocked while students,
		sessions, or professor assignments still use this offering.
	</p>
	<div class="danger-actions">
		{#if offering.isActive}
			<button class="btn btn-danger" disabled={archiveBusy} onclick={() => { adminOfferingDetailState.actionError = null; archiveConfirm = true; }}>
				Archive offering
			</button>
		{:else}
			<button
				class="btn btn-success"
				disabled={archiveBusy || (!!course && !!breakdown && breakdown.status !== 'ok')}
				title={!!course && !!breakdown && breakdown.status !== 'ok' ? 'Weekly scheduled hours do not match the course units requirement — fix the meetings first' : undefined}
				onclick={() => (reactivateConfirm = true)}
			>
				{archiveBusy ? 'Reactivating…' : 'Reactivate offering'}
			</button>
		{/if}
		<button
			class="btn btn-danger"
			disabled={deleteBusy || offering.isActive}
			title={offering.isActive ? 'Archive first — only archived offerings can be deleted' : undefined}
			onclick={() => { adminOfferingDetailState.actionError = null; deleteOpen = true; }}
		>
			Delete permanently
		</button>
	</div>
	{#if !offering.isActive}
		<p class="hint">Delete is blocked while students, sessions, or professor assignments still use this offering.</p>
	{/if}
</section>

{#if archiveConfirm}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="offering-archive-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (archiveConfirm = false) }}
		>
			<h2 id="offering-archive-title" class="modal-title">Archive this offering?</h2>
			<p class="modal-text">
				It will be flipped to inactive. Sessions history is kept, and you can
				reactivate it anytime.
			</p>
			{#if adminOfferingDetailState.actionError}
				<p class="error" role="alert">{adminOfferingDetailState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (archiveConfirm = false)}>Cancel</button>
				<button class="btn btn-danger" aria-busy={archiveBusy} disabled={archiveBusy} onclick={confirmArchive}>
					{archiveBusy ? 'Archiving…' : 'Archive'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if reactivateConfirm}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="offering-reactivate-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (reactivateConfirm = false) }}
		>
			<h2 id="offering-reactivate-title" class="modal-title">Reactivate this offering?</h2>
			<p class="modal-text">
				{course ? `${course.courseCode} — ${course.courseName}` : `Offering ${offering.id}`} will be restored to the active list.
			</p>
			{#if adminOfferingDetailState.actionError}
				<p class="error" role="alert">{adminOfferingDetailState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" disabled={archiveBusy} onclick={() => (reactivateConfirm = false)}>Cancel</button>
				<button
					class="btn btn-success"
					disabled={archiveBusy}
					onclick={async () => { await onReactivate(); if (adminOfferingDetailState.offering?.isActive) reactivateConfirm = false; }}
				>
					{archiveBusy ? 'Reactivating…' : 'Reactivate'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if deleteOpen}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="offering-delete-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (deleteOpen = false) }}
		>
			<h2 id="offering-delete-title" class="modal-title">Permanently delete this offering?</h2>
			<p class="modal-text">
				The offering and its meetings will be removed for good.
				If students, sessions, or professor assignments still use it, deletion will be blocked
				and the offering stays archived.
			</p>
			{#if adminOfferingDetailState.actionError}
				<p class="error" role="alert">{adminOfferingDetailState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (deleteOpen = false)}>Cancel</button>
				<button class="btn btn-danger" disabled={deleteBusy} onclick={confirmDelete}>
					{deleteBusy ? 'Deleting…' : 'Delete'}
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

	.card .muted {
		margin-bottom: 1rem;
	}

	.danger {
		border-color: var(--danger-bg);
	}

	.danger-actions {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.muted {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0;
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
	}
</style>
