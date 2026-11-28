<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import {
		adminOfferingDetailState,
		bulkEnrollOffering,
	} from '$lib/features/admin/offerings/store.svelte';
	import { buildEnrollCsv } from '$lib/features/admin/offerings/service';
	import { listStudents } from '$lib/features/admin/service';
	import { debounce } from '$lib/shared/utils/debounce';
	import { trapFocus } from '$lib/shared/actions/focusTrap';
	import type { AdminOffering, AdminStudent } from '$lib/shared/types';

	// Add-student wizard (detail page, Enrolled tab): search the offering's
	// cohort, multi-select across pages, and submit through the same bulk-CSV
	// path as the upload card. Mounted only while open, so every open starts
	// with a clean search, selection, and report.

	interface Props {
		offering: AdminOffering;
		programCode: string | null;
		yearLabel: string | null;
		enrolledStudentIds: string[];
		onclose: () => void;
	}

	let { offering, programCode, yearLabel, enrolledStudentIds, onclose }: Props = $props();

	const ADD_PAGE_SIZE = 8;
	let addQuery = $state('');
	let addResults = $state<AdminStudent[]>([]);
	let addTotal = $state(0);
	let addPage = $state(1);
	let addSearching = $state(false);
	// Reactive array of the selected rows: `$state` proxies arrays but not
	// Map/Set, so selection lives here (house multi-select idiom — see
	// admin/analytics and admin/professors) while insertion order gives the
	// CSV row order and the error-line mapping for free. Objects, not ids:
	// the list only holds the current page, so an id-only set could not
	// rebuild rows chosen on other pages.
	let addSelected = $state<AdminStudent[]>([]);
	let addBusy = $state(false);
	let addReport = $state<{ enrolled: number; skipped: number; failures: string[] } | null>(
		null
	);
	const addSearchDebounced = debounce(() => void loadAddCandidates(1));

	onDestroy(() => addSearchDebounced.cancel());
	onMount(() => void loadAddCandidates(1));

	const onAddQuery = () => {
		addSearchDebounced();
	};

	// One loader for browse, pager, and search: empty query + cohort ids is
	// the browse list, a query narrows within it. Cohort-scoped, so only
	// students on the offering's program + year can take this course.
	const loadAddCandidates = async (page: number) => {
		const q = addQuery.trim();
		addSearching = true;
		try {
			const result = await listStudents({
				search: q || undefined,
				size: ADD_PAGE_SIZE,
				page,
				is_active: true,
				program_id: offering.programId,
				year_level_id: offering.yearLevelId,
			});
			if (q !== addQuery.trim()) return;
			addResults = result.items;
			addTotal = result.total;
			addPage = result.page;
		} catch (e: unknown) {
			adminOfferingDetailState.actionError =
				e instanceof Error && e.message ? e.message : 'Failed to load students';
		} finally {
			addSearching = false;
		}
	};

	const addTotalPages = $derived(Math.max(1, Math.ceil(addTotal / ADD_PAGE_SIZE)));

	const addCohortLabel = $derived(
		[programCode, yearLabel].filter(Boolean).join(' ') || 'this cohort'
	);

	const addEmptyCopy = $derived(
		addQuery.trim() ? `No matches in ${addCohortLabel}.` : `No students in ${addCohortLabel} yet.`
	);

	// The upload checks the CSV program against the offering, so a cross-
	// program pick is blocked here instead of round-tripping the error.
	const addProgramMismatch = $derived(
		programCode !== null &&
			addSelected.some((s) => s.programCode !== programCode)
	);

	// Enrollment status per candidate, read off the loaded roster page.
	// Advisory for rosters past page 1 (submit stays authoritative via the
	// skipped branch); membership itself never false-positives, so enrolled
	// rows are safe to disable.
	const enrolledIds = $derived(new Set(enrolledStudentIds));

	// House toggle idiom (admin/analytics, admin/professors): reassign
	// through filter/append so the reactive array invalidates.
	const toggleAddSelection = (student: AdminStudent) => {
		addSelected = addSelected.some((s) => s.id === student.id)
			? addSelected.filter((s) => s.id !== student.id)
			: [...addSelected, student];
	};

	const clearAddSelection = () => {
		if (addBusy) return;
		addSelected = [];
	};

	// Every eligible student on the visible page, so a cohort can be paged
	// through without checking boxes one by one.
	const pageEligible = $derived(
		addResults.filter((s) => !enrolledIds.has(s.studentId))
	);
	const pageAllSelected = $derived(
		pageEligible.length > 0 && pageEligible.every((s) => addSelected.some((x) => x.id === s.id))
	);
	const togglePageSelection = () => {
		if (addBusy || pageEligible.length === 0) return;
		addSelected = pageAllSelected
			? addSelected.filter((x) => !pageEligible.some((s) => s.id === x.id))
			: [...addSelected, ...pageEligible.filter((s) => !addSelected.some((x) => x.id === s.id))];
	};

	const submitAdd = async () => {
		const chosen = addSelected;
		if (chosen.length === 0 || addBusy || addProgramMismatch) return;
		addBusy = true;
		addReport = null;
		try {
			// Row order matches `chosen`, and the parser numbers data rows from
			// line 2, so an error line maps back to its student deterministically.
			const result = await bulkEnrollOffering(offering.id, buildEnrollCsv(chosen));
			const failures = result.errors.map((err) => {
				const student = chosen[err.line - 2];
				return student ? `${student.studentId} — ${err.reason}` : err.reason;
			});
			if (result.errors.length === 0 && result.skipped === 0) {
				addSelected = [];
				onclose();
			} else {
				// Stay open with the report: the roster reload above already
				// flipped the newly-enrolled rows to "Already enrolled", so the
				// badges self-correct and a re-submit is at worst a repeat skip.
				addReport = {
					enrolled: result.enrolled,
					skipped: result.skipped,
					failures,
				};
			}
		} catch {
			// Surfaced via the detail state's actionError.
		} finally {
			addBusy = false;
		}
	};
</script>

<div class="modal-overlay" role="presentation">
	<div
		class="modal"
		role="dialog"
		aria-modal="true"
		aria-labelledby="add-title"
		tabindex="-1"
		use:trapFocus={{ onEscape: onclose }}
	>
		<h2 id="add-title" class="modal-title">Add student</h2>
		<div class="form">
			<label>Find student
				<input
					class="input"
					placeholder="ID, name, or email"
					aria-label="Find student"
					bind:value={addQuery}
					oninput={onAddQuery}
				/>
			</label>
			{#if addSearching && addResults.length === 0}
				<p class="muted">Searching…</p>
			{:else if addResults.length === 0}
				<p class="empty">{addEmptyCopy}</p>
			{:else}
				<div class="pick-bar">
					<label class="check pick-all">
						<input
							type="checkbox"
							checked={pageAllSelected}
							disabled={addBusy || pageEligible.length === 0}
							onchange={togglePageSelection}
						/>
						<span>Select all on page</span>
					</label>
					{#if addSelected.length > 0}
						<span class="muted">{addSelected.length} selected</span>
						<button class="link" disabled={addBusy} onclick={clearAddSelection}>
							Clear
						</button>
					{/if}
				</div>
				<ul class="pick-list">
					{#each addResults as s (s.id)}
						<li class="pick-row">
							{#if enrolledIds.has(s.studentId)}
								<span class="muted">{s.studentId} — {s.firstName} {s.lastName}</span>
								<span class="badge inactive">Already enrolled</span>
							{:else}
								<label class="check">
									<input
										type="checkbox"
										checked={addSelected.some((x) => x.id === s.id)}
										disabled={addBusy}
										aria-label={`Select ${s.studentId}`}
										onchange={() => toggleAddSelection(s)}
									/>
									<span>{s.studentId} — {s.firstName} {s.lastName} ({s.programCode})</span>
								</label>
								<span class="badge">Can enroll</span>
							{/if}
						</li>
					{/each}
				</ul>
				{#if !addSearching && addTotalPages > 1}
					<div class="pager">
						<button
							class="btn btn-secondary"
							disabled={addPage <= 1 || addBusy}
							onclick={() => void loadAddCandidates(addPage - 1)}
						>
							‹ Prev
						</button>
						<span class="muted">Page {addPage} of {addTotalPages}</span>
						<button
							class="btn btn-secondary"
							disabled={addPage >= addTotalPages || addBusy}
							onclick={() => void loadAddCandidates(addPage + 1)}
						>
							Next ›
						</button>
					</div>
				{/if}
			{/if}
			{#if addReport}
				<p class="muted" role="status">
					Enrolled {addReport.enrolled} · skipped {addReport.skipped}
					{#if addReport.failures.length > 0} · {addReport.failures.length} error{addReport.failures.length === 1 ? '' : 's'}:{/if}
				</p>
				{#each addReport.failures as failure (failure)}
					<p class="error" role="alert">{failure}</p>
				{/each}
			{/if}
			{#if adminOfferingDetailState.actionError}
				<p class="error" role="alert">{adminOfferingDetailState.actionError}</p>
			{/if}
		</div>
		<div class="modal-actions">
			<button class="btn btn-ghost" onclick={onclose}>Cancel</button>
			<button
				class="btn btn-primary"
				disabled={addSelected.length === 0 || addBusy || addProgramMismatch}
				onclick={submitAdd}
			>
				{addBusy ? 'Enrolling…' : addSelected.length > 1 ? `Enroll ${addSelected.length}` : 'Enroll'}
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

	.muted {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0;
	}

	.empty {
		color: var(--text-muted);
		font-size: 0.9375rem;
		margin: 0;
	}

	.pick-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 0.25rem;
	}

	.pick-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
	}

	.pick-bar {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		font-size: 0.8125rem;
	}

	.pager {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		margin-top: 1rem;
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
