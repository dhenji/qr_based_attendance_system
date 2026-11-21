<script lang="ts">
	import SkeletonDetail from '$lib/components/SkeletonDetail.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { getStudent } from '$lib/features/admin/service';
	import type { AdminStudent } from '$lib/shared/types';
	import { Routes } from '$lib/shared/constants/routes';
	import { subscribeEntity } from '$lib/shared/utils/entityEvents';
	import { onFocusRevalidate } from '$lib/shared/utils/revalidateOnFocus';
	import { formatLocalDateTime } from '$lib/shared/utils/format';

	// Student profile (admin): read-only card opened by clicking a student's
	// email on the roster. Edits stay on the Student Management modal.
	// Auto-refresh keeps the row current after edits elsewhere.

	const studentId = $derived(Number(page.params.id));

	let student = $state<AdminStudent | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	const autoRefreshStops: (() => void)[] = [];

	onDestroy(() => {
		for (const stop of autoRefreshStops) stop();
	});

	const fullName = (s: AdminStudent) =>
		[s.firstName, s.middleName, s.lastName].filter(Boolean).join(' ');

	const load = async () => {
		if (!Number.isFinite(studentId) || studentId <= 0) {
			error = 'Invalid student id.';
			loading = false;
			return;
		}
		loading = true;
		error = null;
		try {
			student = await getStudent(studentId);
		} catch (e: unknown) {
			error = e instanceof Error && e.message ? e.message : 'Could not load student.';
		} finally {
			loading = false;
		}
	};

	const refreshVisible = () => {
		if (!loading) void load();
	};

	const back = () => {
		goto(Routes.ADMIN_STUDENTS);
	};

	onMount(() => {
		void load();
		autoRefreshStops.push(
			subscribeEntity('students', refreshVisible),
			onFocusRevalidate(refreshVisible)
		);
	});
</script>

<svelte:head>
	<title>{student ? `${fullName(student)} · Student` : 'Student profile'}</title>
</svelte:head>

<div class="page">
	<button class="btn btn-secondary back" data-testid="back-to-students" onclick={back}>
		‹ Back to students
	</button>

	{#if loading}
		<SkeletonDetail rows={5} label="Loading student…" />
	{:else if error || !student}
		<section class="card">
			<p class="error" role="alert">{error ?? 'Student not found.'}</p>
			<button class="btn btn-secondary" onclick={back}>Back to students</button>
		</section>
	{:else}
		<section class="card profile" aria-label="Student profile">
			<div class="profile-head">
				<div class="avatar" aria-hidden="true">
					{(student.firstName[0] ?? '?') + (student.lastName[0] ?? '')}
				</div>
				<div class="profile-meta">
					<h1>{fullName(student)}</h1>
					<p class="muted mono">{student.email}</p>
					<div class="pills">
						<span class={student.isActive ? 'status-active' : 'status-inactive'}>
							{student.isActive ? 'Active' : 'Inactive'}
						</span>
						<span class="claim" class:claimed={student.claimStatus === 'Claimed'}>
							{student.claimStatus}
						</span>
					</div>
				</div>
			</div>
			<dl class="facts">
				<div>
					<dt>Student ID</dt>
					<dd class="mono">{student.studentId}</dd>
				</div>
				<div>
					<dt>Program</dt>
					<dd>{student.programCode}</dd>
				</div>
				<div>
					<dt>Year level</dt>
					<dd>{student.yearLevelLabel}</dd>
				</div>
				<div>
					<dt>Section</dt>
					<dd>{student.section || '—'}</dd>
				</div>
				<div>
					<dt>Face enrolled</dt>
					<dd>{student.faceEnrolled ? 'Yes' : 'No'}</dd>
				</div>
				{#if student.faceEnrolledAt}
					<div>
						<dt>Face enrolled at</dt>
						<dd>{formatLocalDateTime(student.faceEnrolledAt, { date: {} })}</dd>
					</div>
				{/if}
				<div>
					<dt>Scan count</dt>
					<dd>{student.scanCount}</dd>
				</div>
				<div>
					<dt>Member since</dt>
					<dd>{formatLocalDateTime(student.createdAt, { date: {} })}</dd>
				</div>
			</dl>
		</section>
	{/if}
</div>

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
	}

	.back {
		align-self: flex-start;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 1.5rem;
		box-shadow: var(--shadow-sm);
	}

	.profile-head {
		display: flex;
		gap: 1rem;
		align-items: center;
		margin-bottom: 1.25rem;
	}

	.profile-meta {
		min-width: 0;
		overflow-wrap: anywhere;
	}

	.profile-head h1 {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.5rem;
		font-weight: 700;
		color: var(--text);
		margin: 0 0 0.25rem;
	}

	.avatar {
		width: 3.5rem;
		height: 3.5rem;
		border-radius: 999px;
		background: var(--brand);
		color: var(--on-brand);
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1.125rem;
		font-weight: 700;
		flex-shrink: 0;
	}

	.pills {
		display: flex;
		gap: 0.5rem;
		margin-top: 0.5rem;
		flex-wrap: wrap;
	}

	.status-active,
	.status-inactive,
	.claim {
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

	.claim {
		background: var(--divider);
		color: var(--text-muted);
	}

	.claim.claimed {
		background: var(--success-bg);
		color: var(--success);
	}

	.facts {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
		gap: 1rem;
		margin: 0;
	}

	@media (max-width: 640px) {
		.profile-head {
			flex-direction: column;
			align-items: flex-start;
		}
	}

	.facts dt {
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--text-muted);
		margin-bottom: 0.25rem;
	}

	.facts dd {
		margin: 0;
		font-size: 0.9375rem;
		color: var(--text-strong);
		font-weight: 500;
	}

	.mono {
		font-variant-numeric: tabular-nums;
		font-weight: 500;
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
	}

	.btn-secondary:hover {
		background: var(--divider);
	}
</style>