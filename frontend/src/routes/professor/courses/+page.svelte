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
			<button class="btn btn-secondary" type="button" onclick={() => void initProfessorCourses()}>Try again</button>
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
							{#if !course.scheduleOk}
								<span
									class="blocked-badge"
									title="Weekly schedule does not match the course units requirement — sessions cannot be opened. Contact your administrator."
								>
									<AppIcon name="alert" size={12} />
									Sessions blocked
								</span>
							{/if}
						</div>

						<p class="course-meta">
							{enrollmentText(course)} · Room TBA
						</p>
						<p class="course-term">{termText(course)} · {sectionText(course)}</p>

							<div class="course-actions">
								<button
									class="btn btn-primary"
									data-testid="open-session-{course.offeringId}"
									disabled={!course.scheduleOk}
									title={!course.scheduleOk ? 'Sessions cannot be opened — the weekly schedule does not match the course units requirement' : undefined}
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
		color: var(--text);
		margin: 0 0 0.25rem;
	}

	.muted {
		color: var(--text-muted);
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
		color: var(--text);
		cursor: pointer;
	}

	.group-toggle:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.group-chevron {
		display: inline-flex;
		color: var(--text-muted);
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
		background: var(--border);
	}

	.group-count {
		font-size: 0.8125rem;
		color: var(--text-muted);
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
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		box-shadow: var(--shadow-sm);
		transition: box-shadow 0.15s ease;
	}

	.course-list li:hover {
		box-shadow: var(--shadow-sm);
	}

	.course-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.0625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0;
		line-height: 1.3;
	}

	.course-units {
		color: var(--text-muted);
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
		background: var(--bg-muted);
		border: 1px solid var(--border);
		color: var(--text-secondary);
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.04em;
	}

	/* The lock marks the locked create-session variant (D11). */
	.cohort-badge :global(svg) {
		color: var(--text-muted);
	}

	/* The role rides the assignment: a primary and an assistant can both
	open sessions (D9), so this is informational only. */
	.role-badge {
		display: inline-block;
		padding: 0.1875rem 0.5rem;
		border-radius: 6px;
		background: var(--bg-muted);
		border: 1px solid var(--border);
		color: var(--text-muted);
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.04em;
	}

	.role-badge.primary {
		background: var(--success-bg);
		border-color: var(--success-bg);
		color: var(--success);
	}

	/* Sessions-open readiness (D82): the backend refuses opens on
	mis-scheduled offerings, so the button is disabled up front. */
	.blocked-badge {
		display: inline-flex;
		align-items: center;
		gap: 0.3125rem;
		padding: 0.1875rem 0.5rem;
		border-radius: 6px;
		background: var(--danger-bg);
		border: 1px solid var(--danger-bg);
		color: var(--danger);
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.04em;
	}

	.course-meta {
		margin: 0.25rem 0 0;
		font-size: 0.875rem;
		color: var(--text-strong);
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
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.btn-primary {
		background: var(--brand);
		border: 1px solid var(--brand);
		color: var(--on-brand);
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

	/* Reports deep-links to the offering-prefiltered reports page. */
	.btn:disabled {
		color: #94a3b8;
		background: var(--bg-page);
		border-color: var(--border);
		cursor: not-allowed;
	}

	/* --- Tally + empty state ------------------------------------------------- */

	.tally {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.5rem;
		font-size: 0.875rem;
		color: var(--text-muted);
	}

	.error {
		color: var(--danger);
		font-size: 0.9375rem;
		margin: 0;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 2rem;
		box-shadow: var(--shadow-sm);
	}

	.empty {
		color: var(--text-muted);
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
