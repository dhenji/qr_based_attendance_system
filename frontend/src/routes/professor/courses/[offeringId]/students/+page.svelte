<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte';
	import SkeletonTable from '$lib/components/SkeletonTable.svelte';
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import { professorState, initProfessorCourses } from '$lib/features/professor/store.svelte';
	import { listOfferingStudents } from '$lib/features/professor/service';
	import type { AdminRosterItem } from '$lib/shared/types';
	import { Routes } from '$lib/shared/constants/routes';
	import { debounce } from '$lib/shared/utils/debounce';

	const offeringId = $derived(Number(page.params.offeringId));

	let loading = $state(true);
	let error = $state<string | null>(null);
	let items = $state<AdminRosterItem[]>([]);
	let total = $state(0);
	let searchQuery = $state('');
	const scheduleLoad = debounce(() => void load());

	const offering = $derived(
		professorState.courses.find((c) => c.offeringId === offeringId) ?? null
	);

	const title = $derived(
		offering ? `${offering.courseCode} — ${offering.courseName}` : `Offering ${offeringId}`
	);

	onMount(async () => {
		if (professorState.courses.length === 0 && !professorState.coursesLoading) {
			await initProfessorCourses();
		}
		await load();
	});

	onDestroy(() => scheduleLoad.cancel());

	async function load() {
		loading = true;
		error = null;
		try {
			const result = await listOfferingStudents(offeringId, {
				search: searchQuery.trim() || undefined,
				page: 1,
				size: 100,
			});
			items = result.items;
			total = result.total;
		} catch (e) {
			error = e instanceof Error && e.message ? e.message : 'Failed to load enrolled students';
		} finally {
			loading = false;
		}
	}
</script>

<div class="page page-enter">
	<header class="header">
		<button class="btn btn-secondary" type="button" onclick={() => goto(Routes.PROFESSOR_COURSES)}>
			<AppIcon name="chevron" size={16} />
			Back to courses
		</button>
		<h1>Enrolled Students</h1>
		<p class="muted">{title}</p>
	</header>

	<div class="toolbar">
		<input
			class="search"
			type="search"
			placeholder="Search by name, ID, or email…"
			bind:value={searchQuery}
			oninput={() => scheduleLoad()}
		/>
	</div>

	{#if loading}
		<SkeletonTable rows={6} cols={4} label="Loading enrolled students…" />
	{:else if error}
		<section class="card">
			<p class="error">Could not load enrolled students: {error}</p>
			<button class="btn btn-secondary" type="button" onclick={() => void load()}>Try again</button>
		</section>
	{:else if items.length === 0 && !searchQuery.trim()}
		<section class="card">
			<EmptyState icon="users" title="No students enrolled" hint="Students enrolled in this offering will appear here." />
		</section>
	{:else}
		<section class="card">
			<p class="summary">{total} {total === 1 ? 'student' : 'students'} enrolled</p>
			{#if items.length === 0}
				<p class="empty-search">No students match your search.</p>
			{:else}
			<div class="table-wrap">
				<table>
					<thead>
						<tr>
							<th>Student ID</th>
							<th>Name</th>
							<th>Email</th>
							<th>Section</th>
						</tr>
					</thead>
					<tbody>
						{#each items as student (student.studentId)}
							<tr>
								<td>{student.studentId}</td>
								<td>{student.name}</td>
								<td>{student.email ?? '—'}</td>
								<td>{student.section ?? '—'}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			{/if}
		</section>
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
		flex-direction: column;
		gap: 0.5rem;
	}
	.header h1 {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.5rem;
		font-weight: 700;
		color: var(--text);
		margin: 0;
	}
	.muted {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0;
	}
	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 1.5rem;
		box-shadow: var(--shadow-sm);
	}
	.toolbar {
		margin-bottom: 1rem;
	}
	.search {
		width: 100%;
		max-width: 320px;
		padding: 0.5rem 0.75rem;
		border-radius: 8px;
		border: 1px solid var(--border-strong);
		background: var(--bg-card);
		color: var(--text);
		font-family: inherit;
		font-size: 0.875rem;
	}
	.summary {
		margin: 0 0 1rem;
		font-size: 0.875rem;
		color: var(--text-strong);
		font-weight: 600;
	}
	.empty-search {
		margin: 0;
		font-size: 0.875rem;
		color: var(--text-muted);
		font-style: italic;
	}
	.table-wrap {
		overflow-x: auto;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.875rem;
	}
	th, td {
		padding: 0.625rem 0.75rem;
		text-align: left;
		border-bottom: 1px solid var(--border);
	}
	th {
		font-weight: 700;
		color: var(--text-secondary);
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}
	.error {
		color: var(--danger);
		font-size: 0.9375rem;
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
	}
	.btn-secondary {
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		color: var(--text-strong);
		align-self: flex-start;
	}
</style>