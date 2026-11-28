<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte';
	import SkeletonDetail from '$lib/components/SkeletonDetail.svelte';
	import SkeletonTable from '$lib/components/SkeletonTable.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import {
		adminOfferingDetailState,
		initAdminOfferingDetail,
		loadOfferingAssignments,
		loadOfferingRoster,
		refreshAdminOfferingDetail,
	} from '$lib/features/admin/offerings/store.svelte';
	import { listCourses } from '$lib/features/admin/courses/service';
	import { getSettings } from '$lib/features/admin/settings/service';
	import { listPrograms, listYearLevels } from '$lib/features/admin/programs/service';
	import { listProfessors } from '$lib/features/admin/service';
	import { totalExpectedSessions, weeklyHoursBreakdown, weeklySessionCount } from '$lib/shared/utils/schedule';
	import type {
		AdminCourse,
		AdminProfessor,
		AdminRosterItem,
		Program,
		YearLevel,
	} from '$lib/shared/types';
	import { sessionMixLabel } from '$lib/shared/types';
	import { Routes } from '$lib/shared/constants/routes';
	import { subscribeEntity } from '$lib/shared/utils/entityEvents';
	import { onFocusRevalidate } from '$lib/shared/utils/revalidateOnFocus';
	import OfferingSettingsCard from '$lib/features/admin/offerings/components/OfferingSettingsCard.svelte';
	import OfferingMeetingsCard from '$lib/features/admin/offerings/components/OfferingMeetingsCard.svelte';
	import OfferingDangerZone from '$lib/features/admin/offerings/components/OfferingDangerZone.svelte';
	import OfferingAssignmentsCard from '$lib/features/admin/offerings/components/OfferingAssignmentsCard.svelte';
	import BulkEnrollCard from '$lib/features/admin/offerings/components/BulkEnrollCard.svelte';
	import AddStudentModal from '$lib/features/admin/offerings/components/AddStudentModal.svelte';
	import UnenrollStudentDialog from '$lib/features/admin/offerings/components/UnenrollStudentDialog.svelte';

	// Offering Detail (wireframe 4.5d, admin-manual §2.4): schedule, classroom
	// GPS, weeks, and default windows live here — the course template page
	// only shows units/duration. Tabs:
	// - Overview: identity + schedule + classroom + windows.
	// - Professors: assignments with effective dating (D7-D9); ending sets
	//   effective_to=today, history is never rewritten.
	// - Enrolled: roster with section filter + bulk CSV enroll of EXISTING
	//   students (creating new students stays on /admin/students/import).
	// - Settings: mutable fields only — course/program/year/semester/
	//   academic_year are identity and not patchable (contract).
	//
	// This page owns tab routing, the page-level loads, focus revalidation,
	// the overview, and the roster table. Each tab's form surfaces live in
	// components under features/admin/offerings/components/.

	const offeringId = $derived(Number(page.params.id));
	const offering = $derived(adminOfferingDetailState.offering);

	type OfferingTab = 'overview' | 'professors' | 'enrolled' | 'settings';
	const OFFERING_TABS: OfferingTab[] = ['overview', 'professors', 'enrolled', 'settings'];

	// Deep-linkable tabs (?tab=professors) so the Setup Wizard completion
	// screen can point at the next step directly. Read once on entry (same
	// convention as ?offering= on professor session create); in-page tab
	// clicks stay local state. Unknown values fall back to overview.
	const initialTab = (): OfferingTab => {
		const raw = page.url.searchParams.get('tab');
		return OFFERING_TABS.includes(raw as OfferingTab) ? (raw as OfferingTab) : 'overview';
	};

	let tab = $state<OfferingTab>(initialTab());

	let course = $state<AdminCourse | null>(null);
	let programCode = $state<string | null>(null);
	let yearLabel = $state<string | null>(null);
	let professorIndex = $state<Map<number, AdminProfessor>>(new Map());

	// The system-wide defaults, for the "inherit" placeholders and the
	// effective-value hints. Read once; they only change in Admin -> System
	// Settings.
	let systemDefaults = $state<{ present: number; late: number; radius: number } | null>(
		null
	);

	// Roster filter. Kept on the page so focus revalidation preserves the
	// current section and page.
	let sectionFilter = $state('');
	let unenrollTarget = $state<AdminRosterItem | null>(null);

	// Add-student modal (single-row bulk upload under the hood). Mounted only
	// while open so every open starts with a clean search and selection.
	let addOpen = $state(false);

	// alive-guard for the async onMount below: if the route unmounts while
	// the detail legs are still loading, destroy has already run and the
	// entity/focus subscriptions must never attach afterwards.
	let pageAlive = true;
	const autoRefreshStops: (() => void)[] = [];

	onDestroy(() => {
		pageAlive = false;
		for (const stop of autoRefreshStops) stop();
	});

	// Weekly-hours requirement (D79): units are the required scheduled meeting
	// hours per week. The meetings card owns the add/edit drafts; this page
	// derives the stored total the overview, settings, and danger zone share.
	const detailRows = $derived(
		(offering?.components ?? []).map((c) => ({
			schedule_days: c.scheduleDays,
			schedule_start_time: c.scheduleStartTime,
			schedule_end_time: c.scheduleEndTime,
		}))
	);
	const detailBreakdown = $derived(weeklyHoursBreakdown(detailRows, course?.units ?? null));
	// Sessions per week, counted from the meetings above — one per meeting
	// day — same helper as the Setup Wizard. Read-only here: every meeting
	// write re-syncs the stored column server-side, so this is always current.
	const detailSessionCount = $derived(weeklySessionCount(detailRows));
	// Term total, same product the risk batch uses as its expected session
	// count. Weeks are derived from the offering's term (D86), so this is
	// read-only.
	const detailExpectedTotal = $derived(
		offering
			? totalExpectedSessions(String(detailSessionCount), String(offering.semesterWeeks))
			: null
	);
	const overviewExpectedTotal = $derived(
		offering ? totalExpectedSessions(String(offering.sessionsPerWeek), String(offering.semesterWeeks)) : null
	);
	const rosterTotalPages = $derived(
		Math.max(1, Math.ceil(adminOfferingDetailState.rosterTotal / 20))
	);
	const rosterStudentIds = $derived(adminOfferingDetailState.roster.map((r) => r.studentId));

	// Own entity -> refresh the detail regions (covers edits made on other
	// tabs; the store mutators emit after their own reloads). Roster keeps
	// the current section filter and page.
	const refreshVisible = () => {
		if (!Number.isFinite(offeringId) || offeringId <= 0) return;
		if (adminOfferingDetailState.loading) return;
		void refreshAdminOfferingDetail(offeringId);
		if (!adminOfferingDetailState.assignmentsLoading) void loadOfferingAssignments(offeringId);
		if (!adminOfferingDetailState.rosterLoading)
			void loadOfferingRoster(
				offeringId,
				sectionFilter.trim() || undefined,
				adminOfferingDetailState.rosterPage
			);
	};

	onMount(async () => {
		if (!Number.isFinite(offeringId) || offeringId <= 0) return;
		await initAdminOfferingDetail(offeringId);
		const o = adminOfferingDetailState.offering;
		if (!o) return;
		// The system-wide defaults, for the "inherit" placeholders (D93).
		try {
			const settings = await getSettings();
			systemDefaults = {
				present: settings.present_window_default,
				late: settings.late_window_default,
				radius: settings.geofence_default_radius
			};
		} catch {
			systemDefaults = null;
		}
		await Promise.all([
			loadOfferingAssignments(offeringId),
			loadOfferingRoster(offeringId),
			resolveContext(o.courseId, o.programId, o.yearLevelId),
		]);
		if (!pageAlive) return;
		autoRefreshStops.push(
			subscribeEntity('offerings', refreshVisible),
			onFocusRevalidate(refreshVisible)
		);
	});

	const resolveContext = async (courseId: number, programId: number, yearId: number) => {
		try {
			course = (await listCourses({ page: 1, size: 100 })).items.find((c) => c.id === courseId) ?? null;
		} catch {
			course = null;
		}
		try {
			const programs: Program[] = (await listPrograms({ page: 1, size: 50 })).items;
			programCode = programs.find((p) => p.id === programId)?.code ?? null;
		} catch {
			programCode = null;
		}
		try {
			const years: YearLevel[] = await listYearLevels(programId);
			yearLabel = years.find((y) => y.id === yearId)?.label ?? null;
		} catch {
			yearLabel = null;
		}
		try {
			const professors = (await listProfessors({ page: 1, size: 100 })).items;
			professorIndex = new Map(professors.map((p) => [p.id, p]));
		} catch {
			professorIndex = new Map();
		}
	};

	const applySection = () => {
		if (offering) loadOfferingRoster(offering.id, sectionFilter.trim() || undefined, 1);
	};

	const openAdd = () => {
		adminOfferingDetailState.actionError = null;
		addOpen = true;
	};

	const askUnenroll = (row: AdminRosterItem) => {
		unenrollTarget = row;
	};
</script>

<div class="page">
	<div class="page-top">
		<button class="btn btn-secondary" onclick={() => goto(Routes.ADMIN_OFFERINGS)}>
			← Back to Offering Management
		</button>
	</div>

	{#if adminOfferingDetailState.loading}
		<SkeletonDetail rows={7} label="Loading offering…" />
	{:else if adminOfferingDetailState.error || !offering}
		<section class="card">
			<p class="error">Could not load offering: {adminOfferingDetailState.error ?? 'Not found'}</p>
		</section>
	{:else}
		<header class="header">
			<div>
				<h1>{course ? `${course.courseCode} — ${course.courseName}` : `Offering ${offering.id}`}</h1>
				<p class="muted">
					{[programCode ?? `Program ${offering.programId}`, yearLabel ?? `Year ${offering.yearLevelId}`].join(' · ')}
					· {offering.semester} {offering.academicYear} ·
					<span class="badge" class:inactive={!offering.isActive}>
						{offering.isActive ? 'Active' : 'Inactive'}
					</span>
				</p>
			</div>
		</header>

		{#if adminOfferingDetailState.actionError}
			<section class="card"><p class="error" role="alert">{adminOfferingDetailState.actionError}</p></section>
		{/if}

		<nav class="tabs" aria-label="Offering sections">
			<button class:active={tab === 'overview'} onclick={() => (tab = 'overview')}>Overview</button>
			<button class:active={tab === 'professors'} onclick={() => (tab = 'professors')}>Professors</button>
			<button class:active={tab === 'enrolled'} onclick={() => (tab = 'enrolled')}>Enrolled</button>
			<button class:active={tab === 'settings'} onclick={() => (tab = 'settings')}>Settings</button>
		</nav>

		<div class="tab-panel" hidden={tab !== 'overview'}>
			<section class="card">
				<dl class="facts">
					{#if offering.components.length === 0}
						<div><dt>Schedule</dt><dd>{offering.scheduleDays} {offering.scheduleStartTime.slice(0, 5)}–{offering.scheduleEndTime.slice(0, 5)}</dd></div>
					{/if}
					<div>
						<dt>Meetings</dt>
						<dd>
							<span class="badge type-lab" class:type-lec={offering.sessionTypes.length === 1 && offering.sessionTypes[0] === 'lecture'}>
								{sessionMixLabel(offering.sessionTypes)}
							</span>
						</dd>
					</div>
					{#each offering.components as comp (comp.id)}
						<div>
							<dt>{comp.sessionType === 'lab' ? 'Laboratory' : 'Lecture'}</dt>
							<dd>{comp.scheduleDays} {comp.scheduleStartTime.slice(0, 5)}–{comp.scheduleEndTime.slice(0, 5)}{comp.classroomName ? ` · ${comp.classroomName}` : ''}</dd>
						</div>
					{/each}
					<div><dt>Meetings</dt><dd>{offering.sessionsPerWeek} {offering.sessionsPerWeek === 1 ? 'meeting' : 'meetings'}/week{' '}<span class="sep" aria-hidden="true">•</span>{' '}{offering.semesterWeeks} {offering.semesterWeeks === 1 ? 'week' : 'weeks'}{#if overviewExpectedTotal !== null}{' '}<span class="sep" aria-hidden="true">•</span>{' '}{overviewExpectedTotal} {overviewExpectedTotal === 1 ? 'session' : 'sessions'}{/if}</dd></div>
					{#if detailBreakdown && course && detailBreakdown.status !== 'ok'}
						<div>
							<dt>Sessions</dt>
							<dd>
								<span
									class="badge blocked"
									title={`Weekly schedule ${detailBreakdown.scheduled}h does not match the ${course.units}-unit requirement`}
								>
									<AppIcon name="alert" size={12} />
									Blocked — schedule mismatch
								</span>
							</dd>
						</div>
					{/if}
					{#if offering.components.length === 0}
						<div><dt>Classroom</dt><dd>{offering.classroomName ?? '—'}</dd></div>
					{/if}
					{#if offering.classroomLat !== undefined && offering.classroomLng !== undefined}
						<div><dt>Geofence center</dt><dd>{offering.classroomLat}, {offering.classroomLng}</dd></div>
					{/if}
					<div><dt>Present window</dt><dd>{offering.presentWindowMinutes ?? systemDefaults?.present ?? '—'} min{offering.presentWindowMinutes === null ? ' (system default)' : ''}</dd></div>
					<div><dt>Late window</dt><dd>{offering.lateWindowMinutes ?? systemDefaults?.late ?? '—'} min{offering.lateWindowMinutes === null ? ' (system default)' : ''}</dd></div>
					<div><dt>Enrolled</dt><dd>{offering.enrolledCount}</dd></div>
				</dl>
				{#if course}
					<p class="muted">Template: {course.courseCode} · {course.units} units · {course.sessionDurationHours}h default session</p>
				{/if}
			</section>
		</div>

		<div class="tab-panel" hidden={tab !== 'professors'}>
			<OfferingAssignmentsCard {offering} professors={professorIndex} />
		</div>

		<div class="tab-panel" hidden={tab !== 'enrolled'}>
			<section class="card">
				<div class="row-head">
					<h2 class="card-title">Roster ({adminOfferingDetailState.rosterTotal})</h2>
					<button class="btn btn-primary" onclick={openAdd}>Add student</button>
				</div>
				<div class="filters">
					<input
						class="input"
						placeholder="Section (e.g. A)"
						aria-label="Section filter"
						bind:value={sectionFilter}
						onkeydown={(e) => {
							if (e.key === 'Enter') applySection();
						}}
					/>
					<button class="btn btn-secondary" onclick={applySection}>Apply</button>
				</div>
				{#if adminOfferingDetailState.rosterLoading}
					<SkeletonTable bare rows={4} cols={6} label="Loading roster…" />
				{:else if adminOfferingDetailState.roster.length === 0}
					<EmptyState icon="users" title="No students enrolled yet" />
				{:else}
					<div class="table-wrap">
						<table>
							<thead>
								<tr>
									<th scope="col">Student ID</th>
									<th scope="col">Name</th>
									<th scope="col">Section</th>
									<th scope="col">Enrolled</th>
									<th scope="col"><span class="sr">Actions</span></th>
								</tr>
							</thead>
							<tbody>
								{#each adminOfferingDetailState.roster as r (r.studentId)}
									<tr>
										<td class="strong">{r.studentId}</td>
										<td>{r.name}</td>
										<td>{r.section ?? '—'}</td>
										<td>{r.enrolledAt.slice(0, 10)}</td>
										<td>
											<div class="row-actions">
												<button class="link" onclick={() => askUnenroll(r)}>Remove</button>
											</div>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
					<div class="pager">
						<button
							class="btn btn-secondary"
							disabled={adminOfferingDetailState.rosterPage <= 1}
							onclick={() => offering && loadOfferingRoster(offering.id, sectionFilter.trim() || undefined, adminOfferingDetailState.rosterPage - 1)}
						>
							‹ Prev
						</button>
						<span class="muted">Page {adminOfferingDetailState.rosterPage} of {rosterTotalPages}</span>
						<button
							class="btn btn-secondary"
							disabled={adminOfferingDetailState.rosterPage >= rosterTotalPages}
							onclick={() => offering && loadOfferingRoster(offering.id, sectionFilter.trim() || undefined, adminOfferingDetailState.rosterPage + 1)}
						>
							Next ›
						</button>
					</div>
				{/if}
			</section>

			<BulkEnrollCard offeringId={offering.id} />
		</div>

		<div class="tab-panel" hidden={tab !== 'settings'}>
			<OfferingMeetingsCard {offering} {course} breakdown={detailBreakdown} rows={detailRows} />
			<OfferingSettingsCard
				{offering}
				{course}
				{systemDefaults}
				sessionCount={detailSessionCount}
				expectedTotal={detailExpectedTotal}
			/>
			<OfferingDangerZone {offering} {course} breakdown={detailBreakdown} />
		</div>
	{/if}
</div>

{#if addOpen && offering}
	<AddStudentModal
		{offering}
		{programCode}
		{yearLabel}
		enrolledStudentIds={rosterStudentIds}
		onclose={() => (addOpen = false)}
	/>
{/if}

{#if unenrollTarget && offering}
	<UnenrollStudentDialog
		offeringId={offering.id}
		row={unenrollTarget}
		onclose={() => (unenrollTarget = null)}
	/>
{/if}

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
	}

	.header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
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

	.card-title {
		margin: 0 0 0.375rem;
		font-size: 1.125rem;
		font-weight: 700;
		color: var(--text);
	}

	.card .muted {
		margin-bottom: 1rem;
	}

	.tabs {
		display: flex;
		gap: 0.25rem;
		border-bottom: 2px solid var(--border);
	}

	.tabs button {
		background: none;
		border: none;
		padding: 0.625rem 1rem;
		font-size: 0.9375rem;
		font-weight: 600;
		font-family: inherit;
		color: var(--text-muted);
		cursor: pointer;
		border-bottom: 2px solid transparent;
		margin-bottom: -2px;
	}

	.tabs button:hover {
		color: var(--text-strong);
	}

	.tabs button.active {
		color: var(--brand);
		border-bottom-color: var(--brand);
	}

	/* Inactive tabs stay mounted so inline form drafts (settings, bulk file)
		survive a tab switch; the attribute keeps them out of layout and the
		accessibility tree. */
	.tab-panel {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
	}

	.tab-panel[hidden] {
		display: none;
	}

	.row-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
		margin-bottom: 1rem;
	}

	.row-head .card-title {
		margin: 0;
	}

	.facts {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.75rem 1.5rem;
		margin: 0 0 1rem;
	}

	.facts div {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}

	.facts dt {
		font-size: 0.75rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--text-muted);
	}

	.facts dd {
		margin: 0;
		font-size: 0.9375rem;
		color: var(--text-strong);
		font-weight: 600;
	}

	.facts dd .sep {
		color: var(--text-muted);
		font-weight: 400;
	}

	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.875rem;
	}

	th,
	td {
		text-align: left;
		padding: 0.625rem 0.5rem;
		border-bottom: 1px solid var(--divider);
		vertical-align: middle;
	}

	th {
		color: var(--text-muted);
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.strong {
		font-weight: 700;
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

	.badge.type-lec {
		color: var(--success);
		background: var(--success-bg);
	}

	.badge.type-lab {
		color: var(--warning-text);
		background: var(--warning-bg);
	}

	/* Blocked-sessions callout: icon + tinted box, unmissable next to the
	totals it explains. */
	.badge.blocked {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		color: var(--danger);
		background: var(--danger-bg);
	}

	.row-actions {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
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

	/* Back button reads as its own header block, so the .page flex gap
	 * does not push it a full row apart (same pattern as Program Management). */
	.page-top {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 0.75rem;
	}

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0 0 1rem;
	}

	.filters {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
		align-items: center;
		margin-bottom: 1rem;
	}

	.pager {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		margin-top: 1rem;
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

	.table-wrap {
		overflow-x: auto;
	}

	@media (max-width: 640px) {
		.card {
			padding: 1.25rem;
		}

		.facts {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
