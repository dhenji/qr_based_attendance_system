<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import {
		getProfessor,
		listOfferings,
		offeringLabel,
	} from '$lib/features/admin/service';
	import type { AdminOffering, AdminProfessor } from '$lib/shared/types';
	import { Routes } from '$lib/shared/constants/routes';

	// Professor profile (admin): card opened by clicking a professor's email
	// on the roster. Read-only; edits stay on the list modals. Courses come
	// from the row's assigned_courses (offering_id + course_code), enriched
	// with semester/year when the offering list has a match.

	const professorId = $derived(Number(page.params.id));

	let professor = $state<AdminProfessor | null>(null);
	let offerings = $state<AdminOffering[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	const fullName = $derived(
		professor
			? [professor.firstName, professor.middleName, professor.lastName]
					.filter(Boolean)
					.join(' ')
			: ''
	);

	const offeringById = $derived(new Map(offerings.map((o) => [o.id, o])));

	const courseLabel = (offeringId: number, courseCode: string): string => {
		const match = offeringById.get(offeringId);
		return match ? `${courseCode} · ${offeringLabel(match)}` : `${courseCode} · Offering ${offeringId}`;
	};

	onMount(async () => {
		if (!Number.isFinite(professorId) || professorId <= 0) {
			error = 'Invalid professor id.';
			loading = false;
			return;
		}
		try {
			const [row, offeringPage] = await Promise.all([
				getProfessor(professorId),
				listOfferings({ is_active: true, page: 1, size: 50 }).catch(() => ({
					items: [] as AdminOffering[],
					total: 0,
					page: 1,
					size: 50,
				})),
			]);
			professor = row;
			offerings = offeringPage.items;
		} catch (e: unknown) {
			error = e instanceof Error && e.message ? e.message : 'Could not load professor.';
		} finally {
			loading = false;
		}
	});

	const back = () => {
		goto(Routes.ADMIN_PROFESSORS);
	};
</script>

<svelte:head>
	<title>{professor ? `${fullName} · Professor` : 'Professor profile'}</title>
</svelte:head>

<div class="page">
	<button class="btn btn-secondary back" data-testid="back-to-professors" onclick={back}>
		‹ Back to professors
	</button>

	{#if loading}
		<section class="card"><p class="muted">Loading professor…</p></section>
	{:else if error || !professor}
		<section class="card">
			<p class="error" role="alert">{error ?? 'Professor not found.'}</p>
			<button class="btn btn-secondary" onclick={back}>Back to professors</button>
		</section>
	{:else}
		<section class="card profile" aria-label="Professor profile">
			<div class="profile-head">
				<div class="avatar" aria-hidden="true">
					{(professor.firstName[0] ?? '?') + (professor.lastName[0] ?? '')}
				</div>
				<div>
					<h1>{fullName}</h1>
					<p class="muted mono">{professor.email}</p>
					<div class="pills">
						<span class={professor.isActive ? 'status-active' : 'status-inactive'}>
							{professor.isActive ? 'Active' : 'Inactive'}
						</span>
						<span class="claim" class:claimed={professor.claimStatus === 'Claimed'}>
							{professor.claimStatus}
						</span>
					</div>
				</div>
			</div>
			<dl class="facts">
				<div>
					<dt>Department</dt>
					<dd>{professor.department ?? '—'}</dd>
				</div>
				<div>
					<dt>Email</dt>
					<dd class="mono">{professor.email}</dd>
				</div>
				<div>
					<dt>Claim status</dt>
					<dd>{professor.claimStatus}</dd>
				</div>
				<div>
					<dt>Status</dt>
					<dd>{professor.isActive ? 'Active' : 'Inactive'}</dd>
				</div>
				<div>
					<dt>Member since</dt>
					<dd>{new Date(professor.createdAt).toLocaleDateString()}</dd>
				</div>
			</dl>
		</section>

		<section class="card" aria-label="Assigned courses">
			<h2 class="section-title">
				Courses taught · {professor.assigned_courses.length}
			</h2>
			{#if professor.assigned_courses.length === 0}
				<p class="muted">No course assignments yet. Assign offerings from the roster edit form.</p>
			{:else}
				<ul class="courses">
					{#each professor.assigned_courses as c (c.offering_id)}
						<li>{courseLabel(c.offering_id, c.course_code)}</li>
					{/each}
				</ul>
			{/if}
		</section>
	{/if}
</div>

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
		font-family: system-ui, sans-serif;
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
		font-weight: 700;
		font-size: 1.25rem;
		text-transform: uppercase;
		flex-shrink: 0;
	}

	.muted {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0;
	}

	.mono {
		font-variant-numeric: tabular-nums;
		font-weight: 500;
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
		grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
		gap: 1rem;
		margin: 0;
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

	.section-title {
		margin: 0 0 1rem;
		font-size: 1.125rem;
		font-weight: 700;
		color: var(--text);
	}

	.courses {
		margin: 0;
		padding-left: 1.25rem;
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		font-size: 0.9375rem;
		color: var(--text-strong);
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
