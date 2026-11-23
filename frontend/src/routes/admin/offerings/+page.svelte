<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte';
	import SkeletonTable from '$lib/components/SkeletonTable.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import MeetingRowsEditor, {
		blankMeeting,
		type MeetingDraft,
	} from '$lib/features/admin/offerings/components/MeetingRowsEditor.svelte';
	import AcademicYearPicker from '$lib/components/AcademicYearPicker.svelte';
	import { findDuplicateMeetings, findOverlappingMeetings, totalExpectedSessions, weeklyHoursBreakdown, weeklySessionCount } from '$lib/shared/utils/schedule';
	import {
		adminOfferingsState,
		deleteArchivedOffering,
		initAdminOfferings,
		refreshAdminOfferings,
		toggleOfferingActive,
	} from '$lib/features/admin/offerings/store.svelte';
	import {
		createOffering,
		enrichOfferings,
		findConflictingOffering,
		offeringTitle,
	} from '$lib/features/admin/offerings/service';
	import { listCourses } from '$lib/features/admin/courses/service';
	import { listPrograms, listYearLevels } from '$lib/features/admin/programs/service';
	import { getSettings } from '$lib/features/admin/settings/service';
	import { DEFAULT_TERM_WEEKS } from '$lib/shared/constants/terms';
	import {
		componentCreateSchema,
		offeringCreateSchema,
		windowsWithinDuration,
	} from '$lib/features/admin/offerings/schema';
	import type { AdminCourse, AdminOffering, Program, YearLevel } from '$lib/shared/types';
	import { sessionMixLabel } from '$lib/shared/types';
	import { adminOffering } from '$lib/shared/constants/routes';
	import { notifyEntityChanged, subscribeEntity } from '$lib/shared/utils/entityEvents';
	import { APIError } from '$lib/api/client';
	import { WEEKLY_HOURS_CODES } from '$lib/shared/utils/deleteErrors';
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
	let fieldErrors = $state<Record<string, string>>({});
	let formBusy = $state(false);
	// 409 rescue: the conflicting offering may sit under a different year
	// level than the one being scheduled, so link straight to it.
	let conflictOffering = $state<AdminOffering | null>(null);

	let deleteTarget = $state<AdminOffering | null>(null);
	let deleteBusy = $state(false);

	// Deactivate confirm (Deactivate flips to inactive; Reactivate stays
	// immediate since it only restores).
	let deactivateTarget = $state<AdminOffering | null>(null);
	let deactivateBusy = $state(false);
	let reactivateTarget = $state<AdminOffering | null>(null);
	let reactivateBusy = $state(false);

	// Create-form fields (strings for inputs; ids coerced by zod on submit).
	// Meetings (D77): one row per weekly meeting, each with its own type,
	// days, time, and room — edited with the shared MeetingRowsEditor (also
	// used by the Setup Wizard step 3). Meeting 1 also feeds the offering's
	// own schedule/room columns (the legacy display default).
	let meetings = $state<MeetingDraft[]>([blankMeeting()]);
	let meetingErrors = $state<string[]>([]);
	let m_course_id = $state('');
	let m_program_id = $state('');
	let m_year_level_id = $state('');
	let m_semester = $state('');
	let m_academic_year = $state('');
	// D93: blank means "follow the system default" (Admin -> System
	// Settings), so a new offering is born inheriting rather than carrying a
	// hard-coded 5/10 that nobody chose.
	let m_present = $state('');
	let m_late = $state('');
	let systemDefaults = $state<{ present: number; late: number } | null>(null);
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
			? (yearOptions.find((y) => String(y.id) === String(yearFilter))?.terms ?? [])
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

	// alive-guard for the async onMount below: if the route unmounts while
	// the lookups/first page are still loading, destroy has already run and
	// the entity/focus subscriptions must never attach afterwards.
	let pageAlive = true;
	const autoRefreshStops: (() => void)[] = [];

	onDestroy(() => {
		pageAlive = false;
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
		// The system-wide window defaults, for the "inherit" placeholders
		// (D93). Read once; they only change in Admin -> System Settings.
		try {
			const settings = await getSettings();
			systemDefaults = {
				present: settings.present_window_default,
				late: settings.late_window_default
			};
		} catch {
			systemDefaults = null;
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
		if (!pageAlive) return;
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

	// D93: a window field is either a whole number of minutes or "inherit
	// the system default" (blank). The schema passes the blank through as
	// an empty string; this turns it into null so the payload omits it.
	const windowNumber = (raw: unknown): number | null => {
		if (raw === undefined || raw === null || raw === '') return null;
		const value = Number(raw);
		return Number.isInteger(value) ? value : null;
	};

	const openCreate = async () => {
		formError = null;
		fieldErrors = {};
		conflictOffering = null;
		meetingErrors = [];
		m_course_id = '';
		m_program_id = '';
		m_year_level_id = '';
		m_semester = '';
		m_academic_year = defaultAcademicYear();
		meetings = [blankMeeting()];
		m_present = '';
		m_late = '';
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
		m_semester = '';
		m_yearOptions = [];
		if (m_program_id) {
			try {
				m_yearOptions = await listYearLevels(Number(m_program_id));
			} catch {
				m_yearOptions = [];
			}
		}
	};

	// Year change resets the semester to the new year's first term (same as
	// the Setup Wizard) so a stale term code from another year cannot leak
	// into the submit.
	const changeModalYear = () => {
		m_semester = '';
		const year = m_yearOptions.find((y) => String(y.id) === String(m_year_level_id));
		if (year && year.terms.length > 0) {
			m_semester = year.terms[0].code;
		}
	};

	// Academic-year suggestion from the calendar (August start): editable,
	// just a starting value so the field is rarely blank. Same default as
	// the Setup Wizard step 3.
	const defaultAcademicYear = (): string => {
		const now = new Date();
		const year = now.getFullYear();
		const start = now.getMonth() + 1 >= 8 ? year : year - 1;
		return `${start}-${start + 1}`;
	};

	const modalSemesterOptions = $derived(
		m_year_level_id
			? (m_yearOptions.find((y) => String(y.id) === String(m_year_level_id))?.terms ?? [])
			: []
	);

	// Shared schedule rows for the derives below: one entry per meeting row.
	const modalScheduleRows = $derived(
		meetings.map((m) => ({
			schedule_days: m.days,
			schedule_start_time: m.start,
			schedule_end_time: m.end,
		}))
	);

	// Same-day time intersections across meeting rows (any types). Guidance
	// only — the backend permits overlaps, so these never block the submit.
	const overlapNotes = $derived(
		findOverlappingMeetings(modalScheduleRows).map(
			(o) => `Meetings ${o.a + 1} and ${o.b + 1} overlap on ${o.days}.`
		)
	);

	// Units requirement (D79): the picked course's units are the required
	// scheduled meeting hours per week. Null until a course is
	// picked, so the banner below stays hidden instead of showing NaN.
	const modalCourse = $derived(courseOptions.find((c) => String(c.id) === m_course_id) ?? null);
	const modalBreakdown = $derived(
		weeklyHoursBreakdown(modalScheduleRows, modalCourse?.units ?? null)
	);

	// Sessions per week is one per meeting day — same helper as the Setup
	// Wizard, so both create surfaces count identically.
	const modalSessionsPerWeek = $derived(weeklySessionCount(modalScheduleRows));

	// Term total, same product the risk batch uses as its expected session
	// count. Weeks come from the selected term (D86) — read-only here; the
	// fallback matches the shared default when a term has none configured.
	const modalTerm = $derived(
		modalSemesterOptions.find((t) => t.code === m_semester) ?? null
	);
	const modalTermWeeks = $derived(modalTerm?.weeks ?? DEFAULT_TERM_WEEKS);
	const modalExpectedTotal = $derived(
		totalExpectedSessions(String(modalSessionsPerWeek), String(modalTermWeeks))
	);

	// 409 rescue lookup, shared by both save buttons. Null when the identity
	// fields cannot name a conflict or the lookup itself fails — callers fall
	// back to the generic friendly message then.
	const resolveConflict = async (): Promise<AdminOffering | null> => {
		const courseId = Number(m_course_id);
		const programId = Number(m_program_id);
		if (!Number.isInteger(courseId) || courseId <= 0) return null;
		if (!Number.isInteger(programId) || programId <= 0) return null;
		try {
			return await findConflictingOffering({
				course_id: courseId,
				program_id: programId,
				semester: m_semester,
				academic_year: m_academic_year,
			});
		} catch {
			return null;
		}
	};

	const conflictCourse = $derived.by(() => {
		const c = conflictOffering;
		return c ? (courseOptions.find((x) => x.id === c.courseId) ?? null) : null;
	});
	const conflictProgram = $derived.by(() => {
		const c = conflictOffering;
		return c ? (programOptions.find((x) => x.id === c.programId) ?? null) : null;
	});
	const conflictYearLabel = $derived.by(() => {
		const c = conflictOffering;
		if (!c) return null;
		return m_yearOptions.find((y) => y.id === c.yearLevelId)?.label ?? `Year ${c.yearLevelId}`;
	});
	const conflictHref = $derived.by(() => {
		const c = conflictOffering;
		return c ? adminOffering(c.id) : '';
	});

	const parseCoord = (raw: string, label: string, min: number, max: number): number | undefined => {
		const trimmed = raw.trim();
		if (!trimmed) return undefined;
		const value = Number(trimmed);
		if (!Number.isFinite(value) || value < min || value > max) {
			throw new Error(`${label} must be a number between ${min} and ${max}`);
		}
		return value;
	};

	const submitForm = async (openAfter = false) => {
		formError = null;
		fieldErrors = {};
		conflictOffering = null;
		meetingErrors = [];
		formBusy = true;
		try {
			// Meeting 1 feeds the offering's own schedule columns (the
			// legacy display default); every row is stored as a component.
			const first = meetings[0];
			if (!first) {
				formError = 'Add at least one meeting.';
				return;
			}
			const parsed = offeringCreateSchema.safeParse({
				course_id: m_course_id,
				program_id: m_program_id,
				year_level_id: m_year_level_id,
				semester: m_semester,
				academic_year: m_academic_year,
				// Sessions/week is one per meeting day (shared helper above).
				sessions_per_week: modalSessionsPerWeek,
				schedule_days: first.days,
				schedule_start_time: first.start,
				schedule_end_time: first.end,
				classroom_name: first.room || undefined,
				default_present_window_minutes: m_present,
				default_late_window_minutes: m_late,
			});
			if (!parsed.success) {
				const errs: Record<string, string> = {};
				for (const issue of parsed.error.issues) {
					const key = issue.path.join('.') || '_';
					if (!errs[key]) errs[key] = issue.message;
				}
				fieldErrors = errs;
				formError = parsed.error.issues[0]?.message ?? 'Check the form and try again.';
				return;
			}
			// D93: a blank field means "follow the system default", so the
			// offering stores NULL and the session resolves the value from
			// Admin -> System Settings. Only an explicit value is sent.
			const present = windowNumber(parsed.data.default_present_window_minutes);
			const late = windowNumber(parsed.data.default_late_window_minutes);
			// Windows-sum guard (backend 422 windows_exceed_duration): present
			// + late must fit inside the selected course's session duration.
			const course = courseOptions.find((c) => c.id === parsed.data.course_id);
			if (
				course &&
				present !== null &&
				late !== null &&
				!windowsWithinDuration(present, late, course.sessionDurationHours)
			) {
				formError = `Present + late windows exceed the ${course.courseCode} session duration (${course.sessionDurationHours * 60} min)`;
				return;
			}
			const components: {
				session_type: 'lecture' | 'lab';
				schedule_days: string;
				schedule_start_time: string;
				schedule_end_time: string;
				classroom_name?: string;
				classroom_lat?: number;
				classroom_lng?: number;
			}[] = [];
			// Per-row failures render inline under the offending row; the
			// banner carries the first one so the error is also announced.
			const rowErrors: string[] = meetings.map(() => '');
			for (let i = 0; i < meetings.length; i += 1) {
				const m = meetings[i];
				const rowParsed = componentCreateSchema.safeParse({
					session_type: m.type,
					schedule_days: m.days,
					schedule_start_time: m.start,
					schedule_end_time: m.end,
					classroom_name: m.room || undefined,
				});
				if (!rowParsed.success) {
					rowErrors[i] =
						rowParsed.error.issues[0]?.message ?? 'Check the meeting and try again.';
					continue;
				}
				try {
					components.push({
						session_type: rowParsed.data.session_type,
						schedule_days: rowParsed.data.schedule_days,
						schedule_start_time: rowParsed.data.schedule_start_time,
						schedule_end_time: rowParsed.data.schedule_end_time,
						...(rowParsed.data.classroom_name ? { classroom_name: rowParsed.data.classroom_name } : {}),
						...(m.lat.trim() ? { classroom_lat: parseCoord(m.lat, `Meeting ${i + 1} latitude`, -90, 90) } : {}),
						...(m.lng.trim() ? { classroom_lng: parseCoord(m.lng, `Meeting ${i + 1} longitude`, -180, 180) } : {}),
					});
				} catch (e: unknown) {
					rowErrors[i] = e instanceof Error && e.message ? e.message : 'Check the coordinates and try again.';
				}
			}
			// Exact-duplicate rows per the backend unique key (session_type,
			// schedule_days, schedule_start_time) — checked over the rows
			// that parsed, so one bad row cannot mask another.
			const validRows = meetings
				.map((m, index) => ({ m, index }))
				.filter(({ index }) => !rowErrors[index])
				.map(({ m, index }) => ({
					index,
					session_type: m.type,
					schedule_days: m.days,
					schedule_start_time: m.start,
				}));
			for (const dup of findDuplicateMeetings(validRows)) {
				rowErrors[dup.index] = `Duplicates meeting ${dup.first + 1}. Change the type, days, or time.`;
			}
			meetingErrors = rowErrors;
			const firstRowError = rowErrors.find((message) => message !== '');
			if (firstRowError !== undefined) {
				formError = firstRowError;
				return;
			}
			// Weekly-hours requirement (backend 422 weekly_hours_exceed_units /
			// weekly_hours_below_units): the course's units are the required
			// scheduled meeting hours per week. Creation carries the whole
			// schedule, so it must match exactly. Runs after per-row
			// validation so invalid rows (which contribute nothing to the
			// total) cannot mask or fake the sum.
			if (modalCourse && modalBreakdown && modalBreakdown.status !== 'ok') {
				formError =
					modalBreakdown.status === 'over'
						? `Weekly scheduled hours (${modalBreakdown.scheduled}h) exceed the ${modalCourse.units}-unit requirement (${modalBreakdown.limit}h) for ${modalCourse.courseCode} — remove or shorten a meeting.`
						: `Weekly scheduled hours (${modalBreakdown.scheduled}h) fall short of the ${modalCourse.units}-unit requirement (${modalBreakdown.limit}h) for ${modalCourse.courseCode} — add or lengthen a meeting.`;
				return;
			}
			const head = components[0];
			const saved = await createOffering({
				course_id: parsed.data.course_id,
				program_id: parsed.data.program_id,
				year_level_id: parsed.data.year_level_id,
				semester: parsed.data.semester,
				academic_year: parsed.data.academic_year,
				sessions_per_week: parsed.data.sessions_per_week,
				schedule_days: parsed.data.schedule_days,
				schedule_start_time: parsed.data.schedule_start_time,
				schedule_end_time: parsed.data.schedule_end_time,
				components,
				classroom_name: parsed.data.classroom_name || undefined,
				classroom_lat: head?.classroom_lat,
				classroom_lng: head?.classroom_lng,
				...(present !== null ? { default_present_window_minutes: present } : {}),
				...(late !== null ? { default_late_window_minutes: late } : {}),
			});
			formOpen = false;
			await refreshAdminOfferings();
			notifyEntityChanged('offerings');
			// "Save & open" lands on the new offering's detail page, where
			// professor assignment and enrollment live.
			if (openAfter) await goto(adminOffering(saved.id));
		} catch (e: unknown) {
			// 409 rescue: the conflicting offering may sit under a different
			// year level, so look it up and link straight to it instead of
			// leaving a dead-end message.
			if (e instanceof APIError && e.code === 'offering_exists') {
				conflictOffering = await resolveConflict();
				if (!conflictOffering) {
					formError = friendlyActionError(e, 'Save failed. Please try again.');
				}
			} else if (e instanceof APIError && e.code && WEEKLY_HOURS_CODES.has(e.code)) {
				// Race safety: the guards above already block mismatches, but a
				// backend 422 from another surface still shows its numbers.
				formError = e.message;
			} else {
				formError = friendlyActionError(e, 'Save failed. Please try again.');
			}
		} finally {
			formBusy = false;
		}
	};

	const confirmDelete = async () => {
		if (!deleteTarget) return;
		deleteBusy = true;
		try {
			await deleteArchivedOffering(deleteTarget.id);
			deleteTarget = null;
		} finally {
			deleteBusy = false;
		}
	};

	const closeDelete = () => {
		adminOfferingsState.actionError = null;
		deleteTarget = null;
	};

	const confirmDeactivate = async () => {
		if (!deactivateTarget || deactivateBusy) return;
		deactivateBusy = true;
		try {
			await toggleOfferingActive(deactivateTarget);
			deactivateTarget = null;
		} finally {
			deactivateBusy = false;
		}
	};

	const closeDeactivate = () => {
		adminOfferingsState.actionError = null;
		deactivateTarget = null;
	};

	const confirmReactivate = async () => {
		if (!reactivateTarget || reactivateBusy) return;
		reactivateBusy = true;
		try {
			await toggleOfferingActive(reactivateTarget);
			if (!adminOfferingsState.actionError) reactivateTarget = null;
		} finally {
			reactivateBusy = false;
		}
	};

	const closeReactivate = () => {
		adminOfferingsState.actionError = null;
		reactivateTarget = null;
	};

	const rowTitle = (o: AdminOffering) => offeringTitle(o);
</script>

<div class="page page-enter">
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
				<option value={y.id}>{y.label}{y.terms.length === 0 ? ' (no terms)' : ''}</option>
			{/each}
		</select>
		<select
			class="input"
			aria-label="Semester filter"
			bind:value={semesterFilter}
			onchange={applyFilters}
			disabled={!yearFilter || semesterOptions.length === 0}
			title={!yearFilter
				? "Pick a year level first — semesters are the year level's terms"
				: semesterOptions.length === 0
					? 'This year level has no terms configured'
					: undefined}
		>
			<option value="">All semesters</option>
			{#each semesterOptions as t (t.code)}
				<option value={t.code}>{t.label}</option>
			{/each}
		</select>
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
		<SkeletonTable rows={8} cols={7} label="Loading offerings…" />
	{:else if adminOfferingsState.error}
		<section class="card"><p class="error">Could not load offerings: {adminOfferingsState.error}</p></section>
	{:else if visibleItems.length === 0}
		<section class="card">
			<EmptyState
				icon="file"
				title="No offerings match these filters"
				hint="Add the first one — it instances a course template for a program and year."
			/>
		</section>
	{:else}
		<section class="card table-wrap" aria-busy={adminOfferingsState.loading}>
			{#if adminOfferingsState.actionError && !deleteTarget && !deactivateTarget}
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
						<th scope="col">Type</th>
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
							<td>
								<span class="badge type-lab" class:type-lec={o.sessionTypes.length === 1 && o.sessionTypes[0] === 'lecture'}>
									{sessionMixLabel(o.sessionTypes)}
								</span>
							</td>
							<td>{o.enrolledCount}</td>
							<td>
								<span class="badge" class:inactive={!o.isActive}>
									{o.isActive ? 'Active' : 'Inactive'}
								</span>
							</td>
							<td>
								<div class="row-actions">
									<button class="link" onclick={() => goto(adminOffering(o.id))}>Open</button>
									{#if o.isActive}
										<button
											class="link"
											onclick={() => { adminOfferingsState.actionError = null; deactivateTarget = o; }}
										>
											Deactivate
										</button>
									{:else}
										<button
											class="link success"
											onclick={() => { adminOfferingsState.actionError = null; reactivateTarget = o; }}
										>
											Reactivate
										</button>
									{/if}
									{#if !o.isActive}
										<button
											class="link danger"
											onclick={() => { adminOfferingsState.actionError = null; deleteTarget = o; }}
										>
											Delete
										</button>
									{/if}
								</div>
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
			{#if conflictOffering}
				{@const conflict = conflictOffering}
				<p class="error" role="alert">
					{conflictCourse?.courseCode ?? `Course ${conflict.courseId}`} is already
					offered for {conflictProgram?.code ?? `Program ${conflict.programId}`} · {conflict.semester}
					{conflict.academicYear}{conflictYearLabel ? ` under ${conflictYearLabel}` : ''}.
					<a class="link strong" href={conflictHref}>Open offering</a>
				</p>
			{/if}
			<div class="form">
				<h3 class="section-title">Identity</h3>
				<div class="grid2">
					<label>Course *
						<select class="input" bind:value={m_course_id} disabled={formBusy} aria-required="true">
							<option value="">Pick a course…</option>
							{#each courseOptions as c (c.id)}
								<option value={c.id}>{c.courseCode} — {c.courseName}</option>
							{/each}
						</select>
						{#if fieldErrors.course_id}<p class="field-error">{fieldErrors.course_id}</p>{/if}
					</label>
					<label>Academic year *
						<AcademicYearPicker bind:value={m_academic_year} disabled={formBusy} />
						{#if fieldErrors.academic_year}<p class="field-error">{fieldErrors.academic_year}</p>{/if}
					</label>
				</div>
				<div class="grid2">
					<label>Program *
						<select class="input" bind:value={m_program_id} onchange={changeModalProgram} disabled={formBusy} aria-required="true">
							<option value="">Pick a program…</option>
							{#each programOptions as p (p.id)}
								<option value={p.id}>{p.code} — {p.name}</option>
							{/each}
						</select>
						{#if fieldErrors.program_id}<p class="field-error">{fieldErrors.program_id}</p>{/if}
					</label>
					<label>Year level *
						<select class="input" bind:value={m_year_level_id} disabled={!m_program_id || formBusy} onchange={changeModalYear} aria-required="true">
							<option value="">Pick a year…</option>
							{#each m_yearOptions as y (y.id)}
								<option value={y.id} disabled={y.terms.length === 0}>
									{y.label}{y.terms.length === 0 ? ' (no terms)' : ''}
								</option>
							{/each}
						</select>
						{#if fieldErrors.year_level_id}<p class="field-error">{fieldErrors.year_level_id}</p>{/if}
					</label>
				</div>
				<label>Semester *
					<select class="input" bind:value={m_semester} aria-label="Pick a semester" disabled={!m_year_level_id || formBusy} title={!m_year_level_id ? 'Pick a year level first' : undefined} aria-required="true">
						<option value="">{m_year_level_id ? 'Pick a term…' : 'Pick a year level first…'}</option>
						{#each modalSemesterOptions as t (t.code)}
							<option value={t.code}>{t.label}</option>
						{/each}
					</select>
					{#if fieldErrors.semester}<p class="field-error">{fieldErrors.semester}</p>{/if}
				</label>
				<p class="hint">Meetings per week: {modalSessionsPerWeek} (counted automatically — one per meeting day).</p>
				{#if m_semester && modalTerm}
					<p class="hint" data-testid="expected-sessions">
						{modalSessionsPerWeek} sessions/week × {modalTermWeeks} weeks = {modalExpectedTotal} expected sessions this term.
						<span class="muted">Weeks come from the term (edit in Manage Terms).</span>
					</p>
				{:else}
					<p class="hint">Pick a semester to see the expected session total.</p>
				{/if}
				<p class="hint">One offering per course + program + term + academic year — the year level doesn't disambiguate, so re-offering the same course in the same term fails as a duplicate.</p>

				<h3 class="section-title">Schedule</h3>
				<MeetingRowsEditor bind:rows={meetings} rowErrors={meetingErrors} busy={formBusy} showMap={true} />
				{#if overlapNotes.length > 0}
					{#each overlapNotes as note (note)}
						<p class="warn" role="note">
							{note} Overlapping meetings are allowed, but sessions for one offering run one at a time.
						</p>
					{/each}
				{/if}
				{#if modalBreakdown}
					{#if modalBreakdown.status === 'ok'}
						<p class="hint">{modalBreakdown.scheduled}h scheduled of {modalBreakdown.limit}h weekly requirement ({modalCourse?.courseCode} · exact) across {meetings.length} {meetings.length === 1 ? 'meeting' : 'meetings'}.</p>
					{:else if modalBreakdown.status === 'over'}
						<p class="error" role="alert">{modalBreakdown.scheduled}h scheduled of {modalBreakdown.limit}h weekly requirement ({modalCourse?.courseCode} · {-modalBreakdown.remaining}h over) across {meetings.length} {meetings.length === 1 ? 'meeting' : 'meetings'}.</p>
					{:else}
						<p class="error" role="alert">{modalBreakdown.scheduled}h scheduled of {modalBreakdown.limit}h weekly requirement ({modalCourse?.courseCode} · {modalBreakdown.remaining}h short) across {meetings.length} {meetings.length === 1 ? 'meeting' : 'meetings'}.</p>
					{/if}
				{/if}

				<h3 class="section-title">Attendance windows</h3>
				<div class="grid2">
					<label>Present window, min<input class="input" inputmode="numeric" placeholder={systemDefaults ? `System default (${systemDefaults.present})` : 'System default'} bind:value={m_present} disabled={formBusy} /></label>
					<label>Late window, min<input class="input" inputmode="numeric" placeholder={systemDefaults ? `System default (${systemDefaults.late})` : 'System default'} bind:value={m_late} disabled={formBusy} /></label>
				</div>
				<p class="hint">Course, program, year, semester, and academic year are identity — they cannot be changed after creation.</p>
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (formOpen = false)}>Cancel</button>
				<button class="btn btn-secondary" data-testid="save-open-offering" aria-busy={formBusy} disabled={formBusy} onclick={() => void submitForm(true)}>
					{formBusy ? 'Saving…' : 'Save & open'}
				</button>
				<button class="btn btn-primary" data-testid="save-offering" aria-busy={formBusy} disabled={formBusy} onclick={() => void submitForm(false)}>
					{formBusy ? 'Saving…' : 'Save'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if reactivateTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="reactivate-offering-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (reactivateBusy ? undefined : (reactivateTarget = null)) }}
		>
			<h2 id="reactivate-offering-title" class="modal-title">Reactivate this offering?</h2>
			<p class="modal-text">
				{rowTitle(reactivateTarget)} will be restored to the active list.
			</p>
			{#if adminOfferingsState.actionError}
				<p class="error" role="alert">{adminOfferingsState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" disabled={reactivateBusy} onclick={closeReactivate}>Cancel</button>
				<button class="btn btn-success" disabled={reactivateBusy} onclick={confirmReactivate}>
					{reactivateBusy ? 'Reactivating…' : 'Reactivate'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if deactivateTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="deactivate-offering-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: closeDeactivate }}
		>
			<h2 id="deactivate-offering-title" class="modal-title">Deactivate this offering?</h2>
			<p class="modal-text">
				{rowTitle(deactivateTarget)} will be flipped to inactive. Sessions history
				is kept, and you can reactivate it anytime.
			</p>
			{#if adminOfferingsState.actionError}
				<p class="error" role="alert">{adminOfferingsState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={closeDeactivate}>Cancel</button>
				<button class="btn btn-danger" disabled={deactivateBusy} onclick={confirmDeactivate}>
					{deactivateBusy ? 'Deactivating…' : 'Deactivate'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if deleteTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="delete-offering-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: closeDelete }}
		>
			<h2 id="delete-offering-title" class="modal-title">Permanently delete this offering?</h2>
			<p class="modal-text">
				{rowTitle(deleteTarget)} will be removed for good, along with its meetings.
				If students, sessions, or professor assignments still use it, deletion will be blocked
				and the offering stays archived.
			</p>
			{#if adminOfferingsState.actionError}
				<p class="error" role="alert">{adminOfferingsState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={closeDelete}>Cancel</button>
				<button class="btn btn-danger" disabled={deleteBusy} onclick={confirmDelete}>
					{deleteBusy ? 'Deleting…' : 'Delete'}
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

	.badge.type-lec {
		color: var(--success);
		background: var(--success-bg);
	}

	.badge.type-lab {
		color: var(--warning-text);
		background: var(--warning-bg);
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

	.link.danger {
		color: var(--danger);
	}

	.link.success {
		color: var(--success);
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

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0 0 1rem;
	}

	.warn {
		font-size: 0.8125rem;
		color: var(--text-secondary);
		background: var(--bg-muted);
		border: 1px solid var(--border-strong);
		border-left: 3px solid var(--accent);
		border-radius: 8px;
		padding: 0.625rem 0.875rem;
		margin: 0;
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

	.modal-text {
		margin: 0 0 1.5rem;
		font-size: 0.9375rem;
		color: var(--text-secondary);
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

	.section-title {
		font-size: 0.875rem;
		font-weight: 700;
		color: var(--text-strong);
		margin: 0.5rem 0 0;
		padding-top: 0.5rem;
		border-top: 1px solid var(--divider);
	}

	.section-title:first-child {
		border-top: none;
		padding-top: 0;
	}

	.field-error {
		color: var(--danger);
		font-size: 0.75rem;
		margin: 0;
	}

	.modal-actions {
		display: flex;
		gap: 0.75rem;
		justify-content: flex-end;
		margin-top: 1.5rem;
		position: sticky;
		bottom: 0;
		background: var(--bg-card);
		padding-top: 0.75rem;
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
