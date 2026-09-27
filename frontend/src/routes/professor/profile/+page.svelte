<script lang="ts">
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
		<p class="muted">Loading…</p>
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
						{professor.claimStatus === 'Claimed' ? '✅ Claimed' : 'Unclaimed'}
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

	.card {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		padding: 1.5rem;
		box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
	}

	.section-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.0625rem;
		font-weight: 700;
		color: #1e293b;
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
		background: #1e3a5f;
		color: white;
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
		color: #334155;
		min-width: 0;
	}

	.field {
		font-size: 0.8125rem;
		font-weight: 700;
		color: #64748b;
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
		background: #f1f5f9;
		color: #64748b;
		white-space: nowrap;
	}

	.badge.ok {
		background: #dcfce7;
		color: #16a34a;
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
		border-bottom: 1px solid #f1f5f9;
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
		color: #0f172a;
	}

	.course-sub {
		font-size: 0.8125rem;
		color: #64748b;
	}

	.admin-note {
		padding: 0.75rem 1rem;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		background: #f8fafc;
		color: #64748b;
		font-size: 0.875rem;
		text-align: center;
	}

	.meta {
		text-align: center;
		font-size: 0.8125rem;
	}

	.empty {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		padding: 2rem;
		color: #64748b;
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
