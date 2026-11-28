<script lang="ts">
	import { bulkEnrollOffering, adminOfferingDetailState } from '$lib/features/admin/offerings/store.svelte';
	import { csvFileSchema } from '$lib/features/admin/schema';
	import type { AdminBulkEnrollResult } from '$lib/shared/types';

	// Bulk roster enrollment (detail page, Enrolled tab): upload a CSV of
	// EXISTING students. The upload is validated client-side before the
	// request; the server reports per-line failures instead of applying them.

	interface Props {
		offeringId: number;
	}

	let { offeringId }: Props = $props();

	let bulkFile = $state<File | null>(null);
	let bulkBusy = $state(false);
	let bulkResult = $state<AdminBulkEnrollResult | null>(null);

	const onBulkFile = (e: Event) => {
		const input = e.target as HTMLInputElement;
		const picked = input.files?.[0] ?? null;
		bulkFile = picked;
		bulkResult = null;
		if (picked) {
			const parsed = csvFileSchema.safeParse(picked);
			if (!parsed.success) {
				adminOfferingDetailState.actionError = parsed.error.issues[0]?.message ?? 'Invalid CSV file.';
				bulkFile = null;
				input.value = '';
			}
		}
	};

	const submitBulk = async () => {
		if (!bulkFile || bulkBusy) return;
		const parsed = csvFileSchema.safeParse(bulkFile);
		if (!parsed.success) {
			adminOfferingDetailState.actionError = parsed.error.issues[0]?.message ?? 'Invalid CSV file.';
			return;
		}
		bulkBusy = true;
		try {
			bulkResult = await bulkEnrollOffering(offeringId, bulkFile);
		} catch {
			// Surfaced via the detail state's actionError.
		} finally {
			bulkBusy = false;
		}
	};
</script>

<section class="card">
	<h2 class="card-title">Bulk enroll</h2>
	<p class="muted">CSV of EXISTING students: student_id, first_name, middle_name, last_name, email, program_code, year_level, section. Rows that fail (unknown id, email mismatch, wrong program) are reported per line, not applied.</p>
	<div class="filters">
		<input class="input" type="file" accept=".csv,text/csv" onchange={onBulkFile} aria-label="Roster CSV file" />
		<button class="btn btn-primary" aria-busy={bulkBusy} disabled={!bulkFile || bulkBusy} onclick={submitBulk}>
			{bulkBusy ? 'Uploading…' : 'Upload'}
		</button>
	</div>
	{#if bulkResult}
		<p class="muted" role="status">
			Enrolled {bulkResult.enrolled} · skipped {bulkResult.skipped}
			{#if bulkResult.errors.length > 0}
				· {bulkResult.errors.length} error{bulkResult.errors.length === 1 ? '' : 's'}:
			{/if}
		</p>
		{#if bulkResult.errors.length > 0}
			<ul class="error-list">
				{#each bulkResult.errors as err (err.line)}
					<li>Line {err.line}: {err.reason}</li>
				{/each}
			</ul>
		{/if}
	{/if}
</section>

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

	.muted {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0;
	}

	.filters {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
		align-items: center;
		margin-bottom: 1rem;
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

	.error-list {
		color: var(--danger);
		font-size: 0.8125rem;
		margin: 0.5rem 0 0;
		padding-left: 1.25rem;
	}

	@media (max-width: 640px) {
		.card {
			padding: 1.25rem;
		}
	}
</style>
