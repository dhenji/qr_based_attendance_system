<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import DayPicker from '$lib/components/DayPicker.svelte';
	import {
		adminOfferingsState,
		initAdminOfferings,
		refreshAdminOfferings,
		toggleOfferingActive,
	} from '$lib/features/admin/offerings/store.svelte';
	import {
		createOffering,
		enrichOfferings,
		offeringTitle,
	} from '$lib/features/admin/offerings/service';
	import { listCourses } from '$lib/features/admin/courses/service';
	import { listPrograms, listYearLevels } from '$lib/features/admin/programs/service';
	import {
		offeringCreateSchema,
		windowsWithinDuration,
	} from '$lib/features/admin/offerings/schema';
	import type { AdminCourse, AdminOffering, Program, YearLevel } from '$lib/shared/types';
	import { adminOffering } from '$lib/shared/constants/routes';
	import { notifyEntityChanged, subscribeEntity } from '$lib/shared/utils/entityEvents';
	import { onFocusRevalidate } from '$lib/shared/utils/revalidateOnFocus';
	import { trapFocus } from '$lib/shared/actions/focusTrap';
	import { friendlyActionError } from '$lib/shared/utils/deleteErrors';

	// Offering list: program/year/semester instances of course templates (D44).
	// Filters are the backend list query itself — Program → Year → Semester →
	// Course + Status cascade server-side (?program_id&year_level_id&semester&
	// course_id&is_active). Year ids are per-program, so the year dropdown only
	// enables once a program is picked (same constraint as students); semester
	// options come from the picked year's term_structure. The search box and
	// Course header toggle narrow/sort the loaded page client-side.

	let search = $state('');
	let programFilter = $state('');
	let yearFilter = $state('');
	let semesterFilter = $state('');
	let courseFilter = $state('');
	let statusFilter = $state<'all' | 'active' | 'inactive'>('all');
	let sortDir = $state<'asc' | 'desc'>('asc');

	let programOptions = $state<Program[]>([]);
	let yearOptions = $state<YearLevel[]>([]);
	let courseOptions = $state<AdminCourse[]>([]);
	let yearsCache = $state<Map<number, YearLevel[]>>(new Map());

	let formOpen = $state(false);
	let formError = $state<string | null>(null);
	let formBusy = $state(false);

	// Create-form fields (strings for inputs; ids coerced by zod on submit).
	let m_course_id = $state('');
	let m_program_id = $state('');
	let m_year_level_id = $state('');
	let m_semester = $state('');
	let m_academic_year = $state('');
	let m_sessions_per_week = $state('2');
	let m_semester_weeks = $state('18');
	let m_schedule_days = $state('');
	let m_start = $state('');
	let m_end = $state('');
	let m_course_type = $state<'lecture' | 'lab'>('lecture');
	let m_classroom = $state('');
	let m_lat = $state('');
	let m_lng = $state('');
	let m_present = $state('5');
	let m_late = $state('10');
	let m_yearOptions = $state<YearLevel[]>([]);

	const isActiveFilter = $derived(
		statusFilter === 'all' ? undefined : statusFilter === 'active'
	);

	const totalPages = $derived(
		Math.max(1, Math.ceil(adminOfferingsState.total / adminOfferingsState.size))
	);

	// Semester options for the filter: the picked year's term codes.
	const semesterOptions = $derived(
		yearFilter
			? (yearOptions.find((y) => String(y.id) === yearFilter)?.terms ?? [])
			: []
	);

	// Joined rows: the contract carries ids only, so course/program/year
	// display names resolve against the loaded dropdown sources + cache.
	const visibleItems = $derived.by(() => {
		const allYears = [...yearsCache.values()].flat();
		const enriched = enrichOfferings(
			adminOfferingsState.items,
			courseOptions,
			programOptions,
			[...yearOptions, ...allYears]
		);
		const term = search.trim().toLowerCase();
		const narrowed = term
			? enriched.filter((o) =>
					`${o.courseCode ?? ''} ${o.courseName ?? ''} ${o.programCode ?? ''}`
						.toLowerCase()
						.includes(term)
				)
			: [...enriched];
		const dir = sortDir === 'asc' ? 1 : -1;
		narrowed.sort(
			(a, b) =>
				(a.courseCode ?? `~${a.courseId}`).localeCompare(b.courseCode ?? `~${b.courseId}`) * dir
		);
		return narrowed;
	});

	const cacheYears = async (programId: number) => {
		if (yearsCache.has(programId)) return;
		try {
			const years = await listYearLevels(programId);
			yearsCache.set(programId, years);
			// Reassign to trigger rune reactivity on the Map.
			yearsCache = new Map(yearsCache);
		} catch {
			// Join falls back to ids; the table still renders.
		}
	};

	const load = (page = 1) =>
		initAdminOfferings(
			{
				program_id: programFilter ? Number(programFilter) : undefined,
				year_level_id: yearFilter ? Number(yearFilter) : undefined,
				semester: semesterFilter.trim() || undefined,
				course_id: courseFilter ? Number(courseFilter) : undefined,
				is_active: isActiveFilter,
			},
			page,
			adminOfferingsState.size
		).then(async () => {
			// Warm the year-label cache for every program on the loaded page.
			const ids = [...new Set(adminOfferingsState.items.map((o) => o.programId))];
			await Promise.all(ids.map(cacheYears));
		});

	const autoRefreshStops: (() => void)[] = [];

	onDestroy(() => {
		for (const stop of autoRefreshStops) stop();
	});

	const refreshVisible = () => {
		if (!adminOfferingsState.loading) void refreshAdminOfferings();
	};

	const reloadCourseLookups = async () => {
		try {
			courseOptions = (await listCourses({ page: 1, size: 100 })).items;
		} catch {
			courseOptions = [];
		}
	};

	const reloadProgramLookups = async () => {
		try {
			programOptions = (await listPrograms({ page: 1, size: 50 })).items;
		} catch {
			programOptions = [];
		}
		// Year labels/terms may have changed (rename, new year, new terms):
		// drop the join cache so rows re-resolve, then re-warm the picked
		// program's cascade.
		yearsCache = new Map();
		if (programFilter) {
			try {
				yearOptions = await listYearLevels(Number(programFilter));
			} catch {
				yearOptions = [];
			}
			await cacheYears(Number(programFilter));
		}
	};

	onMount(async () => {
		try {
			programOptions = (await listPrograms({ page: 1, size: 50 })).items;
		} catch {
			programOptions = [];
		}
		try {
			courseOptions = (await listCourses({ page: 1, size: 100 })).items;
		} catch {
			courseOptions = [];
		}
		await load(1);
		autoRefreshStops.push(
			subscribeEntity('offerings', refreshVisible),
			// Lookup entities feed the cascade pickers and the joined rows:
			// reload options only, never the offerings query itself.
			subscribeEntity('programs', () => void reloadProgramLookups()),
			subscribeEntity('courses', () => void reloadCourseLookups()),
			onFocusRevalidate(refreshVisible)
		);
	});

	const changeProgram = async () => {
		yearFilter = '';
		semesterFilter = '';
		yearOptions = [];
		if (programFilter) {
			const pid = Number(programFilter);
			try {
				yearOptions = await listYearLevels(pid);
			} catch {
				yearOptions = [];
			}
			await cacheYears(pid);
		}
		await load(1);
	};

	const changeYear = async () => {
		semesterFilter = '';
		await load(1);
	};

	const applyFilters = () => {
		load(1);
	};

	const openCreate = async () => {
		formError = null;
		m_course_id = '';
		m_program_id = '';
		m_year_level_id = '';
		m_semester = '';
		m_academic_year = '';
		m_sessions_per_week = '2';
		m_semester_weeks = '18';
		m_schedule_days = '';
		m_start = '';
		m_end = '';
		m_course_type = 'lecture';
		m_classroom = '';
		m_lat = '';
		m_lng = '';
		m_present = '5';
		m_late = '10';
		m_yearOptions = [];
		if (courseOptions.length === 0) {
			try {
				courseOptions = (await listCourses({ page: 1, size: 100 })).items;
			} catch {
				courseOptions = [];
			}
		}
		formOpen = true;
	};

	const changeModalProgram = async () => {
		m_year_level_id = '';
		m_yearOptions = [];
		if (m_program_id) {
			try {
				m_yearOptions = await listYearLevels(Number(m_program_id));
			} catch {
				m_yearOptions = [];
			}
		}
	};

	const modalSemesterOptions = $derived(
		m_year_level_id
			? (m_yearOptions.find((y) => String(y.id) === m_year_level_id)?.terms ?? [])
			: []
	);

	const parseCoord = (raw: string, label: string, min: number, max: number): number | undefined => {
		const trimmed = raw.trim();
		if (!trimmed) return undefined;
		const value = Number(trimmed);
		if (!Number.isFinite(value) || value < min || value > max) {
			throw new Error(`${label} must be a number between ${min} and ${max}`);
		}
		return value;
	};

	const submitForm = async () => {
		formError = null;
		formBusy = true;
		try {
			const parsed = offeringCreateSchema.safeParse({
				course_id: m_course_id,
				program_id: m_program_id,
				year_level_id: m_year_level_id,
				semester: m_semester,
				academic_year: m_academic_year,
				sessions_per_week: m_sessions_per_week,
				semester_weeks: m_semester_weeks,
				schedule_days: m_schedule_days,
				schedule_start_time: m_start,
				schedule_end_time: m_end,
				course_type: m_course_type,
				classroom_name: m_classroom || undefined,
				default_present_window_minutes: m_present,
				default_late_window_minutes: m_late,
			});
			if (!parsed.success) {
				formError = parsed.error.issues[0]?.message ?? 'Check the form and try again.';
				return;
			}
			// Windows-sum guard (backend 422 windows_exceed_duration): present
			// + late must fit inside the selected course's session duration.
			const course = courseOptions.find((c) => c.id === parsed.data.course_id);
			if (
				course &&
				!windowsWithinDuration(
					parsed.data.default_present_window_minutes,
					parsed.data.default_late_window_minutes,
					course.sessionDurationHours
				)
			) {
				formError = `Present + late windows exceed the ${course.courseCode} session duration (${course.sessionDurationHours * 60} min)`;
				return;
			}
			const lat = parseCoord(m_lat, 'Latitude', -90, 90);
			const lng = parseCoord(m_lng, 'Longitude', -180, 180);
			await createOffering({
				course_id: parsed.data.course_id,
				program_id: parsed.data.program_id,
				year_level_id: parsed.data.year_level_id,
				semester: parsed.data.semester,
				academic_year: parsed.data.academic_year,
				sessions_per_week: parsed.data.sessions_per_week,
				semester_weeks: parsed.data.semester_weeks,
				schedule_days: parsed.data.schedule_days,
				schedule_start_time: parsed.data.schedule_start_time,
				schedule_end_time: parsed.data.schedule_end_time,
				course_type: parsed.data.course_type,
				classroom_name: parsed.data.classroom_name || undefined,
				classroom_lat: lat,
				classroom_lng: lng,
				default_present_window_minutes: parsed.data.default_present_window_minutes,
				default_late_window_minutes: parsed.data.default_late_window_minutes,
			});
			formOpen = false;
			await refreshAdminOfferings();
			notifyEntityChanged('offerings');
		} catch (e: unknown) {
			formError = friendlyActionError(e, 'Save failed. Please try again.');
		} finally {
			formBusy = false;
		}
	};

	const rowTitle = (o: AdminOffering) => offeringTitle(o);
</script>

<div class="page">
	<header class="header">
		<div>
			<h1>Offering Management</h1>
			<p class="muted">Program/year instances of course templates · {adminOfferingsState.total} total</p>
		</div>
		<div class="header-actions">
			<button class="btn btn-primary" data-testid="add-offering" onclick={openCreate}>
				<AppIcon name="plus" size={18} />
				Add Offering
			</button>
		</div>
	</header>

	<section class="card filters">
		<input
			class="input search"
			type="search"
			placeholder="Search course code or name…"
			aria-label="Search offerings"
			bind:value={search}
		/>
		<select class="input" aria-label="Program filter" bind:value={programFilter} onchange={changeProgram}>
			<option value="">All programs</option>
			{#each programOptions as p (p.id)}
				<option value={p.id}>{p.code} — {p.name}</option>
			{/each}
		</select>
		<select
			class="input"
			aria-label="Year level filter"
			bind:value={yearFilter}
			onchange={changeYear}
			disabled={!programFilter}
			title={!programFilter ? 'Pick a program first — year levels belong to a program' : undefined}
		>
			<option value="">All years</option>
			{#each yearOptions as y (y.id)}
				<option value={y.id}>{y.label}</option>
			{/each}
		</select>
		{#if semesterOptions.length > 0}
			<select class="input" aria-label="Semester filter" bind:value={semesterFilter} onchange={applyFilters}>
				<option value="">All semesters</option>
				{#each semesterOptions as t (t.code)}
					<option value={t.code}>{t.label}</option>
				{/each}
			</select>
		{:else}
			<input
				class="input"
				placeholder="Semester (e.g. 1st Sem)"
				aria-label="Semester filter"
				bind:value={semesterFilter}
				onkeydown={(e) => {
					if (e.key === 'Enter') applyFilters();
				}}
			/>
		{/if}
		<select class="input" aria-label="Course filter" bind:value={courseFilter} onchange={applyFilters}>
			<option value="">All courses</option>
			{#each courseOptions as c (c.id)}
				<option value={c.id}>{c.courseCode} — {c.courseName}</option>
			{/each}
		</select>
		<select class="input" aria-label="Status filter" bind:value={statusFilter} onchange={applyFilters}>
			<option value="all">All statuses</option>
			<option value="active">Active</option>
			<option value="inactive">Inactive</option>
		</select>
		<button class="btn btn-secondary" data-testid="apply" onclick={applyFilters}>Apply</button>
	</section>

	{#if adminOfferingsState.loading && adminOfferingsState.items.length === 0}
		<section class="card"><p class="muted">Loading…</p></section>
	{:else if adminOfferingsState.error}
		<section class="card"><p class="error">Could not load offerings: {adminOfferingsState.error}</p></section>
	{:else if visibleItems.length === 0}
		<section class="card">
			<p class="empty">No offerings match these filters. Add the first one — it instances a course template for a program and year.</p>
		</section>
	{:else}
		<section class="card table-wrap" aria-busy={adminOfferingsState.loading}>
			{#if adminOfferingsState.actionError}
				<p class="error" role="alert">{adminOfferingsState.actionError}</p>
			{/if}
			<table>
				<thead>
					<tr>
						<th scope="col" aria-sort={sortDir === 'asc' ? 'ascending' : 'descending'}>
							<button
								class="th-btn"
								type="button"
								onclick={() => (sortDir = sortDir === 'asc' ? 'desc' : 'asc')}
								aria-label={`Sort by course ${sortDir === 'asc' ? 'descending' : 'ascending'}`}
							>
								Course<span aria-hidden="true">{sortDir === 'asc' ? ' ▲' : ' ▼'}</span>
							</button>
						</th>
						<th scope="col">Cohort</th>
						<th scope="col">Term</th>
						<th scope="col">Schedule</th>
						<th scope="col">Enrolled</th>
						<th scope="col">Status</th>
						<th scope="col"><span class="sr">Actions</span></th>
					</tr>
				</thead>
				<tbody>
					{#each visibleItems as o (o.id)}
						<tr title={rowTitle(o)}>
							<td><button class="link strong" onclick={() => goto(adminOffering(o.id))}>{o.courseCode ?? `Course ${o.courseId}`}</button></td>
							<td>{[o.programCode ?? `Program ${o.programId}`, o.yearLevelLabel ?? `Year ${o.yearLevelId}`].join(' · ')}</td>
							<td>{o.semester} {o.academicYear}</td>
							<td>{o.scheduleDays} {o.scheduleStartTime.slice(0, 5)}–{o.scheduleEndTime.slice(0, 5)}</td>
							<td>{o.enrolledCount}</td>
							<td>
								<span class="badge" class:inactive={!o.isActive}>
									{o.isActive ? 'Active' : 'Inactive'}
								</span>
							</td>
							<td class="row-actions">
								<button class="link" onclick={() => goto(adminOffering(o.id))}>Open</button>
								<button
									class="link"
									onclick={() => void toggleOfferingActive(o)}
								>
									{o.isActive ? 'Deactivate' : 'Reactivate'}
								</button>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
			<div class="pager">
				<button
					class="btn btn-secondary"
					disabled={adminOfferingsState.page <= 1}
					onclick={() => load(adminOfferingsState.page - 1)}
				>
					‹ Prev
				</button>
				<span class="muted">Page {adminOfferingsState.page} of {totalPages}</span>
				<button
					class="btn btn-secondary"
					disabled={adminOfferingsState.page >= totalPages}
					onclick={() => load(adminOfferingsState.page + 1)}
				>
					Next ›
				</button>
			</div>
		</section>
	{/if}
</div>

{#if formOpen}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal wide"
			role="dialog"
			aria-modal="true"
			aria-labelledby="offering-form-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (formOpen = false) }}
		>
			<h2 id="offering-form-title" class="modal-title">Add offering</h2>
			{#if formError}
				<p class="error" role="alert">{formError}</p>
			{/if}
			<div class="form">
				<div class="grid2">
					<label>Course
						<select class="input" bind:value={m_course_id}>
							<option value="">Pick a course…</option>
							{#each courseOptions as c (c.id)}
								<option value={c.id}>{c.courseCode} — {c.courseName}</option>
							{/each}
						</select>
					</label>
					<label>Academic year<input class="input" bind:value={m_academic_year} placeholder="2025-2026" /></label>
				</div>
				<div class="grid2">
					<label>Program
						<select class="input" bind:value={m_program_id} onchange={changeModalProgram}>
							<option value="">Pick a program…</option>
							{#each programOptions as p (p.id)}
								<option value={p.id}>{p.code} — {p.name}</option>
							{/each}
						</select>
					</label>
					<label>Year level
						<select class="input" bind:value={m_year_level_id} disabled={!m_program_id}>
							<option value="">Pick a year…</option>
							{#each m_yearOptions as y (y.id)}
								<option value={y.id}>{y.label}</option>
							{/each}
						</select>
					</label>
				</div>
				<DayPicker bind:value={m_schedule_days} />
				<label>Semester
					{#if modalSemesterOptions.length > 0}
						<select class="input" bind:value={m_semester}>
							<option value="">Pick a term…</option>
							{#each modalSemesterOptions as t (t.code)}
								<option value={t.code}>{t.label}</option>
							{/each}
						</select>
					{:else}
						<input class="input" bind:value={m_semester} placeholder="1st Sem" />
					{/if}
				</label>
				<div class="grid2">
					<label>Start time<input class="input" type="time" bind:value={m_start} /></label>
					<label>End time<input class="input" type="time" bind:value={m_end} /></label>
				</div>
				<div class="field">
					<span class="form-label">Course Type</span>
					<div class="toggle-group" role="group" aria-label="Course type">
						<button
							type="button"
							class="toggle-btn"
							class:selected={m_course_type === 'lecture'}
							aria-pressed={m_course_type === 'lecture'}
							onclick={() => (m_course_type = 'lecture')}
						>
							Lecture
						</button>
						<button
							type="button"
							class="toggle-btn"
							class:selected={m_course_type === 'lab'}
							aria-pressed={m_course_type === 'lab'}
							onclick={() => (m_course_type = 'lab')}
						>
							Laboratory
						</button>
					</div>
					<p class="hint">
						{m_course_type === 'lab'
							? 'Laboratory sessions require classroom coordinates and geofence for attendance tracking.'
							: 'Lecture sessions use offering defaults. Geofence is optional.'}
					</p>
				</div>
				<div class="grid2">
					<label>Sessions / week<input class="input" inputmode="numeric" bind:value={m_sessions_per_week} /></label>
					<label>Semester weeks<input class="input" inputmode="numeric" bind:value={m_semester_weeks} /></label>
				</div>
				<label>Classroom (optional)<input class="input" bind:value={m_classroom} placeholder="Lab 101" /></label>
				<div class="grid2">
					<label>Latitude (optional)<input class="input" inputmode="decimal" bind:value={m_lat} placeholder="14.5995" /></label>
					<label>Longitude (optional)<input class="input" inputmode="decimal" bind:value={m_lng} placeholder="120.9842" /></label>
				</div>
				<div class="grid2">
					<label>Present window, min<input class="input" inputmode="numeric" bind:value={m_present} /></label>
					<label>Late window, min<input class="input" inputmode="numeric" bind:value={m_late} /></label>
				</div>
				<p class="hint">Course, program, year, semester, and academic year are identity — they cannot be changed after creation.</p>
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (formOpen = false)}>Cancel</button>
				<button class="btn btn-primary" data-testid="save-offering" disabled={formBusy} onclick={submitForm}>
					{formBusy ? 'Saving…' : 'Save'}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
		font-family: system-ui, sans-serif;
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

	.header-actions {
		display: flex;
		gap: 0.75rem;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 1.5rem;
		box-shadow: var(--shadow-sm);
	}

	.filters {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
		align-items: center;
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

	.input:disabled {
		background: var(--divider);
		color: var(--text-muted);
		cursor: not-allowed;
	}

	.search {
		flex: 1 1 240px;
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

	/* Status pill in the Active/Inactive column. */
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

	.th-btn {
		background: none;
		border: none;
		padding: 0;
		font: inherit;
		color: inherit;
		cursor: pointer;
		white-space: nowrap;
	}

	.th-btn:hover {
		color: var(--text-strong);
	}

	.th-btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
		border-radius: 4px;
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

	.link.strong {
		font-size: 0.875rem;
		font-weight: 700;
	}

	.sr {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
	}

	.pager {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		margin-top: 1rem;
	}

	.empty {
		color: var(--text-muted);
		font-size: 0.9375rem;
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
		transition: background 0.15s ease, border-color 0.15s ease;
	}

	.btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-primary {
		background: var(--brand);
		border: 1px solid var(--brand);
		color: var(--on-brand);
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--brand-hover);
	}

	.btn-secondary {
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		color: var(--text-strong);
	}

	.btn-secondary:hover:not(:disabled) {
		background: var(--divider);
	}

	.btn-ghost {
		background: var(--divider);
		border: 1px solid transparent;
		color: var(--text-secondary);
	}

	.toggle-group {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.toggle-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.375rem;
		padding: 0.5rem 0.875rem;
		border-radius: 8px;
		border: 1px solid var(--border-strong);
		background: var(--bg-card);
		color: var(--text-strong);
		font-family: inherit;
		font-size: 0.8125rem;
		font-weight: 600;
		cursor: pointer;
		transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
	}

	.toggle-btn:hover {
		background: var(--bg-hover);
	}

	.toggle-btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.toggle-btn.selected {
		background: var(--brand);
		border-color: var(--brand);
		color: var(--on-brand);
	}

	.form-label {
		font-size: 0.8125rem;
		font-weight: 600;
		letter-spacing: 0.02em;
		color: var(--text-secondary);
		margin-bottom: 0.375rem;
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}

	.modal-overlay {
		position: fixed;
		inset: 0;
		z-index: 100;
		background: var(--overlay);
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
	}

	.modal {
		width: 100%;
		max-width: 520px;
		max-height: 90vh;
		overflow-y: auto;
		background: var(--bg-card);
		border-radius: 12px;
		box-shadow: var(--shadow-lg);
		padding: 1.75rem 1.5rem;
		font-family: system-ui, sans-serif;
	}

	.modal.wide {
		max-width: 640px;
	}

	.modal-title {
		margin: 0 0 1rem;
		font-size: 1.25rem;
		font-weight: 700;
		color: var(--text);
	}

	.form {
		display: flex;
		flex-direction: column;
		gap: 0.875rem;
	}

	.form label {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.grid2 {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.875rem;
	}

	.hint {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin: 0;
	}

	.modal-actions {
		display: flex;
		gap: 0.75rem;
		justify-content: flex-end;
		margin-top: 1.5rem;
	}

	.table-wrap {
		overflow-x: auto;
	}

	@media (max-width: 640px) {
		.card {
			padding: 1.25rem;
		}

		.grid2 {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
