<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import { professorState, initProfessorCourses } from '$lib/features/professor/store.svelte';
	import type { ProfessorCourseSummary } from '$lib/shared/types';
	import { professorReport, professorSessionCreate } from '$lib/shared/constants/routes';

	onMount(() => {
		initProfessorCourses();
	});

	type ProgramGroup = {
		code: string;
		courses: ProfessorCourseSummary[];
	};

	const courses = $derived(professorState.courses);

	// Program-grouped (D6): buckets keyed by program code, kept in first-seen
	// order so the grouping follows the assignment order, not an alphabetical one.
	const groups: ProgramGroup[] = $derived.by(() => {
		const buckets = new Map<string, ProfessorCourseSummary[]>();

		for (const course of courses) {
			const bucket = buckets.get(course.programCode);
			if (bucket) {
				bucket.push(course);
			} else {
				buckets.set(course.programCode, [course]);
			}
		}

		return [...buckets].map(([code, groupCourses]) => ({ code, courses: groupCourses }));
	});

	// All groups start expanded; a key is only present once the group is
	// collapsed. Kept as a record rather than a Set so the state stays a plain
	// serialisable proxy.
	let collapsedPrograms = $state<Record<string, boolean>>({});

	const isCollapsed = (code: string) => collapsedPrograms[code] === true;

	const toggleProgram = (code: string) => {
		collapsedPrograms[code] = !isCollapsed(code);
	};

	const totalCourses = $derived(courses.length);
	const totalPrograms = $derived(groups.length);

	// Badge abbreviation for free-form year labels ("1st Year" -> "Y1").
	// Presentation-only: no contract field backs it.
	const shortYear = (label: string) => {
		const match = label.match(/^(\d+)/);
		if (match) return `Y${match[1]}`;
		return label.slice(0, 2).toUpperCase();
	};

	// `sections` is the derived set of student sections across the offering's
	// enrollments — an array, and empty when nothing is enrolled yet.
	const sectionText = (course: ProfessorCourseSummary) =>
		course.sections.length > 0 ? `Section ${course.sections.join(', ')}` : 'No section assigned';

	// Credit load, spelled out: the "3u" shorthand in the wireframe is too terse
	// to stand on its own next to the course name.
	const unitsText = (units: number) => `${units} ${units === 1 ? 'unit' : 'units'}`;

	const enrollmentText = (course: ProfessorCourseSummary) =>
		`${course.enrolledCount} ${course.enrolledCount === 1 ? 'student' : 'students'}`;

	const termText = (course: ProfessorCourseSummary) => `${course.academicYear} · ${course.semester}`;

	const today = $derived(
		new Date().toLocaleDateString(undefined, {
			weekday: 'long',
			year: 'numeric',
			month: 'long',
			day: 'numeric',
		})
	);
</script>

<div class="courses">
	<header class="header">
		<div>
			<h1>My Courses</h1>
			<p class="muted">{today}</p>
		</div>
	</header>

	{#if professorState.coursesLoading}
		<section class="card">
			<p class="muted">Loading…</p>
		</section>
	{:else if professorState.coursesError}
		<section class="card">
			<p class="error">Could not load your courses: {professorState.coursesError}</p>
		</section>
	{:else if courses.length === 0}
		<section class="card">
			<p class="empty">
				No course assignments yet. Offerings assigned to you will appear here, grouped
				by program.
			</p>
		</section>
	{:else}
		{#each groups as group (group.code)}
			<section class="group">
				<button
					class="group-toggle"
					aria-expanded={!isCollapsed(group.code)}
					aria-controls="group-{group.code}"
					data-testid="group-toggle-{group.code}"
					onclick={() => toggleProgram(group.code)}
				>
					<span class="group-chevron" class:collapsed={isCollapsed(group.code)}>
						<AppIcon name="chevron" size={16} />
					</span>
					<span class="group-code">{group.code}</span>
					<span class="group-rule" aria-hidden="true"></span>
					<span class="group-count">
						{group.courses.length}
						{group.courses.length === 1 ? 'course' : 'courses'}
					</span>
				</button>

				<ul class="course-list" id="group-{group.code}" hidden={isCollapsed(group.code)}>
					{#each group.courses as course (course.offeringId)}
						<li>
							<h2 class="course-title">
								{course.courseCode} — {course.courseName}
								<span class="course-units">({unitsText(course.units)})</span>
							</h2>

						<div class="course-badges">
							<span class="cohort-badge">
								{course.programCode}·{shortYear(course.yearLevelLabel)}
								<AppIcon name="lock" size={12} />
							</span>
							<span class="role-badge" class:primary={course.isPrimary}>
								{course.isPrimary ? 'Primary' : 'Assistant'}
							</span>
						</div>

						<p class="course-meta">
							{enrollmentText(course)} · Room TBA
						</p>
						<p class="course-term">{termText(course)} · {sectionText(course)}</p>

							<div class="course-actions">
								<button
									class="btn btn-primary"
									data-testid="open-session-{course.offeringId}"
									onclick={() => goto(professorSessionCreate(course.offeringId))}
								>
									<AppIcon name="qr" size={18} />
									Open Session
								</button>
								<button
									class="btn btn-secondary"
									data-testid="reports-{course.offeringId}"
									onclick={() => goto(professorReport(course.offeringId))}
								>
									<AppIcon name="chart" size={18} />
									Reports
								</button>
							</div>
						</li>
					{/each}
				</ul>
			</section>
		{/each}

		<footer class="tally">
			<span>Total: {totalCourses} courses across {totalPrograms} programs</span>
		</footer>
	{/if}
</div>

<style>
	.courses {
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

	/* --- Program groups ------------------------------------------------------ */

	.group {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.group-toggle {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		width: 100%;
		padding: 0.25rem 0;
		background: none;
		border: none;
		font-family: inherit;
		color: #1e293b;
		cursor: pointer;
	}

	.group-toggle:focus-visible {
		outline: 2px solid #2563eb;
		outline-offset: 2px;
	}

	.group-chevron {
		display: inline-flex;
		color: #64748b;
		transition: transform 0.15s ease;
	}

	/* Collapsed groups point the chevron the other way. */
	.group-chevron.collapsed {
		transform: rotate(-90deg);
	}

	.group-code {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.0625rem;
		font-weight: 700;
		letter-spacing: 0.02em;
	}

	/* The rule is the wireframe's flanking dashes, drawn as one hairline. */
	.group-rule {
		flex: 1 1 auto;
		height: 1px;
		background: #e2e8f0;
	}

	.group-count {
		font-size: 0.8125rem;
		color: #64748b;
	}

	/* --- Course cards -------------------------------------------------------- */

	.course-list {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.course-list[hidden] {
		display: none;
	}

	.course-list li {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		padding: 1.5rem;
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
		transition: box-shadow 0.15s ease;
	}

	.course-list li:hover {
		box-shadow: 0 6px 24px rgba(15, 23, 42, 0.1);
	}

	.course-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.0625rem;
		font-weight: 700;
		color: #1e293b;
		margin: 0;
		line-height: 1.3;
	}

	.course-units {
		color: #64748b;
		font-weight: 600;
	}

	.course-badges {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.cohort-badge {
		display: inline-flex;
		align-items: center;
		gap: 0.3125rem;
		padding: 0.1875rem 0.5rem;
		border-radius: 6px;
		background: #f1f5f9;
		border: 1px solid #e2e8f0;
		color: #334155;
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.04em;
	}

	/* The lock marks the locked create-session variant (D11). */
	.cohort-badge :global(svg) {
		color: #64748b;
	}

	/* The role rides the assignment: a primary and an assistant can both
	open sessions (D9), so this is informational only. */
	.role-badge {
		display: inline-block;
		padding: 0.1875rem 0.5rem;
		border-radius: 6px;
		background: #f1f5f9;
		border: 1px solid #e2e8f0;
		color: #64748b;
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.04em;
	}

	.role-badge.primary {
		background: #dcfce7;
		border-color: #bbf7d0;
		color: #16a34a;
	}

	.course-meta {
		margin: 0.25rem 0 0;
		font-size: 0.875rem;
		color: #0f172a;
	}

	.course-term {
		margin: 0;
		font-size: 0.8125rem;
		color: #94a3b8;
	}

	.course-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		margin-top: 0.75rem;
	}

	/* --- Buttons ------------------------------------------------------------- */

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

	/* Reports deep-links to the offering-prefiltered reports page. */
	.btn:disabled {
		color: #94a3b8;
		background: #f8fafc;
		border-color: #e2e8f0;
		cursor: not-allowed;
	}

	/* --- Tally + empty state ------------------------------------------------- */

	.tally {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.5rem;
		font-size: 0.875rem;
		color: #64748b;
	}

	.error {
		color: #dc2626;
		font-size: 0.9375rem;
		margin: 0;
	}

	.card {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		padding: 2rem;
		box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
	}

	.empty {
		color: #64748b;
		font-size: 0.9375rem;
		margin: 0;
	}

	@media (max-width: 640px) {
		.course-list li,
		.card {
			padding: 1.25rem;
		}

		.course-actions .btn {
			flex: 1 1 auto;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.group-chevron,
		.btn,
		.course-list li {
			transition: none;
		}
	}
</style>
