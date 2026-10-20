<script lang="ts">
	import SkeletonDetail from '$lib/components/SkeletonDetail.svelte';
	import { onMount } from 'svelte';
	import { professorState, initProfessor } from '$lib/features/professor/store.svelte';

	onMount(() => {
		initProfessor();
	});

	const professor = $derived(professorState.professor);

	const fullName = $derived(
		professor
			? [professor.firstName, professor.middleName, professor.lastName].filter(Boolean).join(' ')
			: ''
	);

	const initials = $derived(
		professor
			? [professor.firstName, professor.lastName]
					.map((name) => (name ? name[0] : ''))
					.filter(Boolean)
					.join('')
			: ''
	);

	const accountLabel = $derived(
		professor?.createdAt
			? new Date(professor.createdAt).toLocaleDateString(undefined, {
					month: 'short',
					year: 'numeric',
				})
			: '—'
	);
</script>

<div class="wrap">
	<header class="header">
		<h1>My Profile</h1>
		<p class="muted">Read-only · identity is managed by your administrator</p>
	</header>

	{#if professorState.loading}
		<SkeletonDetail rows={4} label="Loading profile…" />
	{:else if professor}
		<section class="card identity">
			<div class="avatar">{initials}</div>
			<div class="identity-grid">
				<span class="field">Name</span>
				<span>{fullName}</span>
				<span class="field">Department</span>
				<span>{professor.department || '—'}</span>
				<span class="field">Email</span>
				<span>{professor.email || '—'}</span>
				<span class="field">Claim Status</span>
				<span>
					<span class="badge" class:ok={professor.claimStatus === 'Claimed'}>
						{professor.claimStatus === 'Claimed' ? 'Claimed' : 'Unclaimed'}
					</span>
				</span>
			</div>
		</section>

		<section class="card">
			<h2 class="section-title">Assigned Courses</h2>
			{#if professor.assignedCourses.length > 0}
				<ul class="courses">
					{#each professor.assignedCourses as course (course.offering_id)}
						<li class="course">
							<div class="course-main">
								<span class="course-title">{course.course_code} — {course.course_name}</span>
								<span class="course-sub">
									{course.program_code}·{course.year_level_label} · {course.semester} · {course.academic_year}
									{#if course.section.length > 0}
										· Sec. {course.section.join(', ')}
									{/if}
									{#if course.enrolled_count !== undefined}
										· {course.enrolled_count} enrolled
									{/if}
								</span>
							</div>
							<span class="badge" class:ok={course.is_primary}>
								{course.is_primary ? 'Primary' : 'Assistant'}
							</span>
						</li>
					{/each}
				</ul>
			{:else}
				<p class="muted">No course assignments for this term.</p>
			{/if}
		</section>

		<div class="admin-note">Changes handled by Admin.</div>

		<p class="meta muted">Account: {accountLabel} · Sessions: {professor.sessionCount ?? 0}</p>
	{:else if professorState.error}
		<p class="empty">Could not load your profile: {professorState.error}</p>
	{:else}
		<p class="empty">No profile data available for this account.</p>
	{/if}
</div>

<style>
	.wrap {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		max-width: 720px;
		margin-inline: auto;
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

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 1.5rem;
		box-shadow: var(--shadow-sm);
	}

	.section-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.0625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0 0 1rem;
	}

	.identity {
		display: flex;
		gap: 1.5rem;
		align-items: flex-start;
		flex-wrap: wrap;
	}

	.avatar {
		width: 72px;
		height: 72px;
		border-radius: 50%;
		background: var(--brand);
		color: var(--on-brand);
		display: flex;
		align-items: center;
		justify-content: center;
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.5rem;
		font-weight: 700;
		flex-shrink: 0;
	}

	.identity-grid {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 0.5rem 1.5rem;
		font-size: 0.9375rem;
		color: var(--text-secondary);
		min-width: 0;
	}

	.field {
		font-size: 0.8125rem;
		font-weight: 700;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.02em;
		padding-top: 0.0625rem;
	}

	.badge {
		display: inline-block;
		padding: 0.25rem 0.75rem;
		border-radius: 999px;
		font-size: 0.8125rem;
		font-weight: 700;
		background: var(--bg-muted);
		color: var(--text-muted);
		white-space: nowrap;
	}

	.badge.ok {
		background: var(--success-bg);
		color: var(--success);
	}

	.courses {
		list-style: none;
		padding: 0;
		margin: 0;
	}

	.course {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 0.75rem 0;
		border-bottom: 1px solid var(--divider);
	}

	.course:first-child {
		padding-top: 0;
	}

	.course:last-child {
		border-bottom: none;
		padding-bottom: 0;
	}

	.course-main {
		display: flex;
		flex-direction: column;
		gap: 0.1875rem;
		min-width: 0;
	}

	.course-title {
		font-size: 0.9375rem;
		font-weight: 700;
		color: var(--text-strong);
	}

	.course-sub {
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	.admin-note {
		padding: 0.75rem 1rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--bg-page);
		color: var(--text-muted);
		font-size: 0.875rem;
		text-align: center;
	}

	.meta {
		text-align: center;
		font-size: 0.8125rem;
	}

	.empty {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 2rem;
		color: var(--text-muted);
		font-size: 0.9375rem;
		margin: 0;
	}

	@media (max-width: 640px) {
		.identity {
			flex-direction: column;
			align-items: center;
			text-align: center;
		}

		.identity-grid {
			grid-template-columns: 1fr;
			text-align: left;
			width: 100%;
		}

		.course {
			flex-direction: column;
			align-items: flex-start;
		}
	}
</style>
