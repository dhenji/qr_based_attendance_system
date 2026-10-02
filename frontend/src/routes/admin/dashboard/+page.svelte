<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import {
		adminProfessorsState,
		adminStudentsState,
		initAdminProfessors,
		initAdminStudents,
	} from '$lib/features/admin/store.svelte';
	import {
		adminAttendanceState,
		adminScansState,
		initAttendanceOverview,
		initRecentScans,
	} from '$lib/features/admin/analytics/store.svelte';
	import { listPrograms } from '$lib/features/admin/programs/service';
	import { formatPercentage } from '$lib/shared/utils/format';
	import { Routes } from '$lib/shared/constants/routes';

	// Admin dashboard (wireframe 4.1). There is no GET /admin/dashboard on the
	// backend (Phase-12 gap), so the KPI row is derived from the first page of
	// the students/professors/programs lists rather than hardcoded — the
	// numbers can never contradict the roster pages. The scans feed and the
	// attendance strip come from the contract-shaped analytics mocks until the
	// analytics backend lands (Phase 7).
	let programsTotal = $state<number | null>(null);

	onMount(async () => {
		initAdminStudents({}, 1, 1);
		initAdminProfessors({}, 1, 1);
		initRecentScans(10);
		initAttendanceOverview();
		try {
			programsTotal = (await listPrograms({ page: 1, size: 1 })).total;
		} catch {
			programsTotal = null;
		}
	});

	const today = $derived(
		new Date().toLocaleDateString(undefined, {
			weekday: 'long',
			year: 'numeric',
			month: 'long',
			day: 'numeric',
		})
	);

	const kpis = $derived([
		{
			label: 'Students',
			value: String(adminStudentsState.total),
			sub: 'Roster total',
			loading: adminStudentsState.loading,
		},
		{
			label: 'Professors',
			value: String(adminProfessorsState.total),
			sub: 'Roster total',
			loading: adminProfessorsState.loading,
		},
		{
			label: 'Programs',
			value: programsTotal === null ? '—' : String(programsTotal),
			sub: 'Live total',
			loading: false,
		},
		{
			label: 'Face enrolled',
			value: `${adminStudentsState.items.filter((s) => s.faceEnrolled).length}`,
			sub: 'On this page',
			loading: adminStudentsState.loading,
		},
	]);

	const loadError = $derived(adminStudentsState.error ?? adminProfessorsState.error);
</script>

<div class="dashboard">
	<header class="header">
		<div>
			<h1>Admin Dashboard</h1>
			<p class="muted">{today}</p>
		</div>
	</header>

	{#if loadError}
		<section class="card">
			<p class="error">Could not load roster counts: {loadError}</p>
		</section>
	{/if}

	<section class="kpis">
		{#each kpis as kpi (kpi.label)}
			<div class="kpi">
				<span class="kpi-value">{kpi.loading ? '…' : kpi.value}</span>
				<span class="kpi-label">{kpi.label}</span>
				<span class="kpi-sub">{kpi.sub}</span>
			</div>
		{/each}
	</section>

	<section class="actions">
		<button
			class="btn btn-primary"
			data-testid="import-students"
			onclick={() => goto(Routes.ADMIN_STUDENTS_IMPORT)}
		>
			<AppIcon name="file" size={18} />
			Import Students
		</button>
		<button
			class="btn btn-secondary"
			data-testid="manage-students"
			onclick={() => goto(Routes.ADMIN_STUDENTS)}
		>
			<AppIcon name="users" size={18} />
			Manage Students
		</button>
		<button
			class="btn btn-secondary"
			data-testid="manage-professors"
			onclick={() => goto(Routes.ADMIN_PROFESSORS)}
		>
			<AppIcon name="users" size={18} />
			Manage Professors
		</button>
	</section>

	<section class="card">
		<div class="section-head">
			<h2 class="section-title">Attendance at a glance</h2>
			<button class="link" onclick={() => goto(Routes.ADMIN_ATTENDANCE)}>Full overview →</button>
		</div>
		{#if adminAttendanceState.loading}
			<p class="muted">Loading…</p>
		{:else if adminAttendanceState.error}
			<p class="error">{adminAttendanceState.error}</p>
		{:else if adminAttendanceState.items.length === 0}
			<p class="muted">No attendance data yet.</p>
		{:else}
			<ul class="strip">
				{#each adminAttendanceState.items.slice(0, 4) as r (r.course_id)}
					<li>
						<span class="strong">{r.course_code}</span>
						<span class="muted">{r.sessions_count} sessions · {formatPercentage(r.avg_rate)}</span>
					</li>
				{/each}
			</ul>
		{/if}
		<button class="btn btn-secondary" onclick={() => goto(Routes.ADMIN_ANALYTICS)}>
			<AppIcon name="chart" size={18} />
			Open Analytics
		</button>
	</section>

	<section class="card">
		<div class="section-head">
			<h2 class="section-title">Recent scans</h2>
		</div>
		{#if adminScansState.loading}
			<p class="muted">Loading…</p>
		{:else if adminScansState.error}
			<p class="error">{adminScansState.error}</p>
		{:else if adminScansState.items.length === 0}
			<p class="muted">No scans yet.</p>
		{:else}
			<ul class="scans">
				{#each adminScansState.items as s (s.id)}
					<li>
						<span class="strong">{s.student_name}</span>
						<span class="muted">{s.course_code} · {s.status} · {s.scanned_at.slice(0, 16).replace('T', ' ')}</span>
					</li>
				{/each}
			</ul>
		{/if}
	</section>

	<section class="card">
		<h2 class="section-title">Getting started</h2>
		<ol class="steps">
			<li>Import the student roster from CSV, or add students one by one.</li>
			<li>Add professor records so they can claim their accounts at registration.</li>
			<li>Deactivate (rather than delete) records that leave; permanent delete lives behind the archive guard.</li>
		</ol>
	</section>
</div>

<style>
	.dashboard {
		display: flex;
		flex-direction: column;
		gap: 2rem;
		font-family: system-ui, sans-serif;
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

	.kpis {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: 1rem;
	}

	.kpi {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		padding: 1.25rem;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
	}

	.kpi-value {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.75rem;
		font-weight: 700;
		color: var(--text);
		line-height: 1;
	}

	.kpi-label {
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	.kpi-sub {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
	}

	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.75rem 1.25rem;
		border-radius: 8px;
		font-size: 0.9375rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
		white-space: nowrap;
		transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
	}

	.btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.btn-primary {
		background: var(--brand);
		border: 1px solid var(--brand);
		color: var(--on-brand);
		box-shadow: var(--shadow-sm);
	}

	.btn-primary:hover {
		background: var(--brand-hover);
		border-color: var(--brand-hover);
		transform: translateY(-1px);
	}

	.btn-secondary {
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		color: var(--text-strong);
	}

	.btn-secondary:hover {
		background: var(--bg-hover);
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 2rem;
		box-shadow: var(--shadow-sm);
	}

	.section-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.0625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0;
	}

	.section-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
		margin-bottom: 1rem;
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

	.strong {
		font-weight: 700;
	}

	.strip,
	.scans {
		list-style: none;
		margin: 0 0 1rem;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.625rem;
	}

	.strip li {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 1rem;
		border-bottom: 1px solid var(--divider);
		padding-bottom: 0.625rem;
	}

	.scans li {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
		border-bottom: 1px solid var(--divider);
		padding-bottom: 0.625rem;
	}

	.steps {
		margin: 0;
		padding-left: 1.25rem;
		color: var(--text-secondary);
		font-size: 0.9375rem;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.error {
		color: var(--danger);
		font-size: 0.9375rem;
		margin: 0;
	}

	@media (max-width: 640px) {
		.kpis {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}

		.actions .btn {
			flex: 1 1 auto;
		}

		.card {
			padding: 1.25rem;
		}
	}
</style>
