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
	import { Routes } from '$lib/shared/constants/routes';

	// Admin dashboard (wireframe 4.1). There is no GET /admin/dashboard on the
	// backend (Phase-12 gap), so the KPI row is derived from the first page of
	// the students/professors lists rather than hardcoded — the numbers can
	// never contradict the roster pages.
	onMount(() => {
		initAdminStudents({}, 1, 1);
		initAdminProfessors({}, 1, 1);
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
			value: '—',
			sub: 'Phase 3 next',
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
		color: #1e293b;
		margin: 0 0 0.25rem;
	}

	.muted {
		color: #64748b;
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
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
	}

	.kpi-value {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.75rem;
		font-weight: 700;
		color: #1e293b;
		line-height: 1;
	}

	.kpi-label {
		font-size: 0.8125rem;
		color: #64748b;
	}

	.kpi-sub {
		font-size: 0.75rem;
		color: #94a3b8;
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
		outline: 2px solid #2563eb;
		outline-offset: 2px;
	}

	.btn-primary {
		background: #1e3a5f;
		border: 1px solid #1e3a5f;
		color: white;
		box-shadow: 0 4px 14px rgba(30, 58, 95, 0.28);
	}

	.btn-primary:hover {
		background: #16324f;
		border-color: #16324f;
		transform: translateY(-1px);
	}

	.btn-secondary {
		background: white;
		border: 1px solid #cbd5e1;
		color: #0f172a;
	}

	.btn-secondary:hover {
		background: #f1f5f9;
	}

	.card {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		padding: 2rem;
		box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
	}

	.section-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.0625rem;
		font-weight: 700;
		color: #1e293b;
		margin: 0 0 1rem;
	}

	.steps {
		margin: 0;
		padding-left: 1.25rem;
		color: #475569;
		font-size: 0.9375rem;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.error {
		color: #dc2626;
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
