<script lang="ts">
	import {
		adminOfferingDetailState,
		unenrollStudentFromOffering,
	} from '$lib/features/admin/offerings/store.svelte';
	import { trapFocus } from '$lib/shared/actions/focusTrap';
	import type { AdminRosterItem } from '$lib/shared/types';

	// Roster unenroll confirmation (detail page, Enrolled tab). The store
	// reloads the roster and the offering after a successful removal.

	interface Props {
		offeringId: number;
		row: AdminRosterItem;
		onclose: () => void;
	}

	let { offeringId, row, onclose }: Props = $props();

	let unenrollBusy = $state(false);

	const confirmUnenroll = async () => {
		if (unenrollBusy) return;
		unenrollBusy = true;
		try {
			await unenrollStudentFromOffering(offeringId, row.studentId);
			onclose();
		} catch {
			// Surfaced via the detail state's actionError.
		} finally {
			unenrollBusy = false;
		}
	};
</script>

<div class="modal-overlay" role="presentation">
	<div
		class="modal"
		role="dialog"
		aria-modal="true"
		aria-labelledby="unenroll-title"
		tabindex="-1"
		use:trapFocus={{ onEscape: onclose }}
	>
		<h2 id="unenroll-title" class="modal-title">Remove student?</h2>
		<p class="muted">
			{row.name} ({row.studentId}) will be unenrolled from
			this offering. Past attendance history is kept; future scans will be blocked.
		</p>
		{#if adminOfferingDetailState.actionError}
			<p class="error" role="alert">{adminOfferingDetailState.actionError}</p>
		{/if}
		<div class="modal-actions">
			<button class="btn btn-ghost" onclick={onclose}>Cancel</button>
			<button class="btn btn-danger" disabled={unenrollBusy} onclick={confirmUnenroll}>
				{unenrollBusy ? 'Removing…' : 'Remove'}
			</button>
		</div>
	</div>
</div>

<style>
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

	.muted {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0;
	}

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0 0 1rem;
	}

	.modal-actions {
		display: flex;
		gap: 0.75rem;
		justify-content: flex-end;
		margin-top: 1.5rem;
	}
</style>
