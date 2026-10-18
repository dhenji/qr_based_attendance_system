<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import {
		adminOfferingDetailState,
		adminOfferingsState,
		assignOfferingProfessor,
		bulkEnrollOffering,
		deleteArchivedOffering,
		endOfferingAssignment,
		initAdminOfferingDetail,
		loadOfferingAssignments,
		loadOfferingRoster,
		refreshAdminOfferingDetail,
		unenrollStudentFromOffering,
		updateAdminOffering,
	} from '$lib/features/admin/offerings/store.svelte';
	import {
		buildEnrollCsv,
		archiveComponent,
		createComponent,
		setOfferingActive,
		updateComponent,
	} from '$lib/features/admin/offerings/service';
	import { listCourses } from '$lib/features/admin/courses/service';
	import { listPrograms, listYearLevels } from '$lib/features/admin/programs/service';
	import { listProfessors, listStudents } from '$lib/features/admin/service';
	import {
		assignmentCreateSchema,
		componentCreateSchema,
		windowsWithinDuration,
	} from '$lib/features/admin/offerings/schema';
	import { totalExpectedSessions, weeklyHoursBreakdown, weeklySessionCount, weeklyWriteBlocked } from '$lib/shared/utils/schedule';
	import { csvFileSchema } from '$lib/features/admin/schema';
	import type {
		AdminBulkEnrollResult,
		AdminCourse,
		AdminProfessor,
		AdminRosterItem,
		AdminStudent,
		OfferingComponent,
		Program,
		YearLevel,
	} from '$lib/shared/types';
	import { sessionMixLabel } from '$lib/shared/types';
	import { Routes } from '$lib/shared/constants/routes';
	import { notifyEntityChanged, subscribeEntity } from '$lib/shared/utils/entityEvents';
	import { onFocusRevalidate } from '$lib/shared/utils/revalidateOnFocus';
	import { trapFocus } from '$lib/shared/actions/focusTrap';
	import DayPicker from '$lib/features/admin/offerings/components/DayPicker.svelte';
	import { APIError } from '$lib/api/client';
	import {
		WEEKLY_HOURS_CODES,
		friendlyActionError,
	} from '$lib/shared/utils/deleteErrors';

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

	// Settings form (offering-level only: rates and windows. Schedule and
	// rooms live on the class meetings below). Session weeks are term-scoped
	// (D86) and shown read-only here.
	let s_present = $state('');
	let s_late = $state('');
	let settingsError = $state<string | null>(null);
	let settingsBusy = $state(false);
	let archiveBusy = $state(false);

	// Scheduled components (D77: per-type schedules). The offering row
	// already carries its active components, so add/edit/remove refresh
	// the detail and render from there — no separate fetch.
	let compError = $state<string | null>(null);
	let compBusy = $state(false);
	// Confirm gate for the row-level Remove action (soft-archives the
	// meeting server-side; UI keeps the endpoint wording "archive").
	let removeCompTarget = $state<OfferingComponent | null>(null);
	let c_type = $state<'lecture' | 'lab'>('lab');
	let c_days = $state('');
	let c_start = $state('');
	let c_end = $state('');
	let c_room = $state('');
	let c_lat = $state('');
	let c_lng = $state('');
	let editingComp = $state<OfferingComponent | null>(null);
	// Confirm gate (D81): an edit that leaves the total mismatched without
	// converging needs a deliberate click — never silent persistence.
	let editConfirmOpen = $state(false);
	let e_days = $state('');
	// Legacy rows may carry free-text days outside the MTWHFSU alphabet that
	// the picker cannot represent; those edits keep a plain input so saving
	// can never silently drop characters. Decided when the edit opens.
	let e_customDays = $state(false);
	let e_start = $state('');
	let e_end = $state('');
	let e_room = $state('');
	let e_lat = $state('');
	let e_lng = $state('');

	// Weekly-hours requirement (D79): units are the required scheduled meeting
	// hours per week. Existing total plus live projections for the add and
	// edit drafts, so the total updates immediately when times change or a
	// row is removed. Null until the course lookup resolves.
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
	const addProjection = $derived(
		weeklyHoursBreakdown(
			[
				...detailRows,
				{ schedule_days: c_days, schedule_start_time: c_start, schedule_end_time: c_end },
			],
			course?.units ?? null
		)
	);
	const editProjection = $derived.by(() => {
		const target = editingComp;
		if (!target) return null;
		const targetId = target.id;
		return weeklyHoursBreakdown(
			[
				...detailRows.filter(
					(_, i) => (offering?.components ?? [])[i]?.id !== targetId
				),
				{ schedule_days: e_days, schedule_start_time: e_start, schedule_end_time: e_end },
			],
			course?.units ?? null
		);
	});

	// Grandfathered or mid-build totals off the requirement may only converge:
	// strictly closer without crossing sides (same rule as the backend
	// `_check_weekly_hours`). `course.units` is null until the lookup
	// resolves, so every projection below is gated on it.
	const addBlocked = $derived(
		course && addProjection
			? weeklyWriteBlocked(detailBreakdown?.scheduled ?? null, addProjection.scheduled, course.units)
			: false
	);

	// Assign-professor form.
	let assignOpen = $state(false);
	let a_professor_id = $state('');
	let a_primary = $state(false);
	let a_from = $state('');
	let a_to = $state('');
	let a_semester = $state('');
	let assignError = $state<string | null>(null);
	let assignBusy = $state(false);

	// Roster + bulk enroll.
	let sectionFilter = $state('');
	let bulkFile = $state<File | null>(null);
	let bulkBusy = $state(false);
	let bulkResult = $state<AdminBulkEnrollResult | null>(null);

	// Add-student modal (single-row bulk upload under the hood).
	const ADD_PAGE_SIZE = 8;
	let addOpen = $state(false);
	let addQuery = $state('');
	let addResults = $state<AdminStudent[]>([]);
	let addTotal = $state(0);
	let addPage = $state(1);
	let addSearching = $state(false);
	// Reactive array of the selected rows: `$state` proxies arrays but not
	// Map/Set, so selection lives here (house multi-select idiom — see
	// admin/analytics and admin/professors) while insertion order gives the
	// CSV row order and the error-line mapping for free. Objects, not ids:
	// the list only holds the current page, so an id-only set could not
	// rebuild rows chosen on other pages.
	let addSelected = $state<AdminStudent[]>([]);
	let addBusy = $state(false);
	let addReport = $state<{ enrolled: number; skipped: number; failures: string[] } | null>(
		null
	);
	let addSearchTimer: ReturnType<typeof setTimeout> | null = null;
	let unenrollTarget = $state<AdminRosterItem | null>(null);
	let unenrollBusy = $state(false);
	// alive-guard for the async onMount below: if the route unmounts while
	// the detail legs are still loading, destroy has already run and the
	// entity/focus subscriptions must never attach afterwards.
	let pageAlive = true;
	const autoRefreshStops: (() => void)[] = [];

	onDestroy(() => {
		pageAlive = false;
		if (addSearchTimer) clearTimeout(addSearchTimer);
		for (const stop of autoRefreshStops) stop();
	});

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
		await Promise.all([
			loadOfferingAssignments(offeringId),
			loadOfferingRoster(offeringId),
			resolveContext(o.courseId, o.programId, o.yearLevelId),
		]);
		if (!pageAlive) return;
		fillSettings();
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

	const professorName = (id: number): string => {
		const p = professorIndex.get(id);
		return p ? [p.firstName, p.middleName, p.lastName].filter(Boolean).join(' ') : `Professor ${id}`;
	};

	const professorEmail = (id: number): string => professorIndex.get(id)?.email ?? '';

	const fillSettings = () => {
		const o = adminOfferingDetailState.offering;
		if (!o) return;
		settingsError = null;
		s_present = String(o.presentWindowMinutes);
		s_late = String(o.lateWindowMinutes);
	};

	const onArchive = async () => {
		if (!offering || archiveBusy) return;
		archiveBusy = true;
		try {
			await setOfferingActive(offering.id, false);
			await refreshAdminOfferingDetail(offering.id);
			notifyEntityChanged('offerings');
		} catch (e: unknown) {
			adminOfferingDetailState.actionError =
				e instanceof Error && e.message ? e.message : 'Failed to archive offering';
		} finally {
			archiveBusy = false;
		}
	};

	const confirmArchive = async () => {
		await onArchive();
		if (offering && !offering.isActive) archiveConfirm = false;
	};

	const onReactivate = async () => {
		if (!offering || archiveBusy) return;
		archiveBusy = true;
		try {
			await setOfferingActive(offering.id, true);
			await refreshAdminOfferingDetail(offering.id);
			notifyEntityChanged('offerings');
		} catch (e: unknown) {
			adminOfferingDetailState.actionError =
				e instanceof Error && e.message ? e.message : 'Failed to reactivate offering';
		} finally {
			archiveBusy = false;
		}
	};

	let deleteOpen = $state(false);
	let deleteBusy = $state(false);
	let archiveConfirm = $state(false);

	const confirmDelete = async () => {
		if (!offering || deleteBusy) return;
		deleteBusy = true;
		try {
			await deleteArchivedOffering(offering.id);
			deleteOpen = false;
			notifyEntityChanged('offerings');
			await goto(Routes.ADMIN_OFFERINGS);
		} catch {
			// The store holds the friendly guard copy; mirror it onto the
			// detail state so the modal shows it on a direct landing.
			adminOfferingDetailState.actionError =
				adminOfferingsState.actionError ?? 'Failed to delete offering';
		} finally {
			deleteBusy = false;
		}
	};

	const submitSettings = async () => {
		if (!offering) return;
		settingsError = null;
		settingsBusy = true;
		try {
			const present = Number(s_present);
			const late = Number(s_late);
			if (!Number.isInteger(present) || present < 1 || present > 480 || !Number.isInteger(late) || late < 1 || late > 480) {
				settingsError = 'Windows must be whole minutes between 1 and 480';
				return;
			}
			if (course && !windowsWithinDuration(present, late, course.sessionDurationHours)) {
				settingsError = `Present + late windows exceed the ${course.courseCode} session duration (${course.sessionDurationHours * 60} min)`;
				return;
			}
			await updateAdminOffering(offering.id, {
				default_present_window_minutes: present,
				default_late_window_minutes: late,
			});
			fillSettings();
		} catch (e: unknown) {
			settingsError = e instanceof Error && e.message ? e.message : 'Save failed. Please try again.';
		} finally {
			settingsBusy = false;
		}
	};

	const openAssign = () => {
		assignError = null;
		a_professor_id = '';
		a_primary = false;
		a_from = new Date().toISOString().slice(0, 10);
		a_to = '';
		a_semester = offering?.semester ?? '';
		assignOpen = true;
	};

	// -- Scheduled components (D77) ----------------------------------------
	// The offering row carries its active components; add/edit/archive
	// refresh the detail and render from there.

	// Curated meeting-write errors: weekly 422s render the backend message
	// verbatim (it carries the tailored scheduled/limit/over/short numbers);
	// every other API failure maps through the friendly copy so raw row ids
	// never render.
	const compFailure = (e: unknown, fallback: string): string => {
		if (e instanceof APIError && e.code && WEEKLY_HOURS_CODES.has(e.code)) {
			return e.message;
		}
		return friendlyActionError(e, fallback);
	};

	const parseOptCoord = (raw: string, label: string, min: number, max: number): number | undefined => {
		const trimmed = raw.trim();
		if (!trimmed) return undefined;
		const value = Number(trimmed);
		if (!Number.isFinite(value) || value < min || value > max) {
			throw new Error(`${label} must be a number between ${min} and ${max}`);
		}
		return value;
	};

	const resetCompForm = () => {
		c_type = 'lab';
		c_days = '';
		c_start = '';
		c_end = '';
		c_room = '';
		c_lat = '';
		c_lng = '';
	};

	const submitAddComponent = async () => {
		if (!offering) return;
		compError = null;
		compBusy = true;
		try {
			const parsed = componentCreateSchema.safeParse({
				session_type: c_type,
				schedule_days: c_days,
				schedule_start_time: c_start,
				schedule_end_time: c_end,
				classroom_name: c_room || undefined,
			});
			if (!parsed.success) {
				compError = parsed.error.issues[0]?.message ?? 'Check the component and try again.';
				return;
			}
			// Duplicate pre-check on the backend unique key (session_type,
			// schedule_days, schedule_start_time), naming the table row it
			// clashes with — same idiom as the create surfaces.
			const clashIndex = offering.components.findIndex(
				(c) =>
					c.sessionType === parsed.data.session_type &&
					c.scheduleDays === parsed.data.schedule_days &&
					c.scheduleStartTime.slice(0, 5) === parsed.data.schedule_start_time.slice(0, 5)
			);
			if (clashIndex >= 0) {
				const hit = offering.components[clashIndex];
				const hitLabel = hit.sessionType === 'lab' ? 'Laboratory' : 'Lecture';
				compError = `Duplicates meeting ${clashIndex + 1} (${hitLabel} ${hit.scheduleDays} ${hit.scheduleStartTime.slice(0, 5)}). Change the type, days, or time.`;
				return;
			}
			// Weekly-hours requirement (backend 422 weekly_hours_exceed_units /
			// weekly_hours_below_units): the course's units are the required
			// scheduled meeting hours per week, counting all existing meetings
			// plus this draft. Off-requirement totals may only converge.
			if (course && addBlocked) {
				compError =
					addProjection && addProjection.status === 'under'
						? `Weekly scheduled hours (${addProjection.scheduled}h) fall short of the ${course.units}-unit requirement (${addProjection.limit}h) for ${course.courseCode} — lengthen a meeting instead.`
						: `Weekly scheduled hours (${addProjection?.scheduled}h) exceed the ${course.units}-unit requirement (${addProjection?.limit}h) for ${course.courseCode} — shorten a meeting first.`;
				return;
			}
			await createComponent(offering.id, {
				session_type: parsed.data.session_type,
				schedule_days: parsed.data.schedule_days,
				schedule_start_time: parsed.data.schedule_start_time,
				schedule_end_time: parsed.data.schedule_end_time,
				classroom_name: parsed.data.classroom_name || undefined,
				classroom_lat: parseOptCoord(c_lat, 'Latitude', -90, 90),
				classroom_lng: parseOptCoord(c_lng, 'Longitude', -180, 180),
			});
			resetCompForm();
			await refreshAdminOfferingDetail(offering.id);
			notifyEntityChanged('offerings');
		} catch (e: unknown) {
			compError = compFailure(e, 'Save failed. Please try again.');
		} finally {
			compBusy = false;
		}
	};

	const openEditComponent = (c: OfferingComponent) => {
		editingComp = c;
		editConfirmOpen = false;
		compError = null;
		e_days = c.scheduleDays;
		e_customDays = !/^[MTWHFSU]+$/.test(c.scheduleDays);
		e_start = c.scheduleStartTime.slice(0, 5);
		e_end = c.scheduleEndTime.slice(0, 5);
		e_room = c.classroomName ?? '';
		e_lat = c.classroomLat !== undefined ? String(c.classroomLat) : '';
		e_lng = c.classroomLng !== undefined ? String(c.classroomLng) : '';
	};

	const submitEditComponent = async () => {
		if (!offering || !editingComp) return;
		compError = null;
		const parsed = componentCreateSchema.safeParse({
			session_type: editingComp.sessionType,
			schedule_days: e_days,
			schedule_start_time: e_start,
			schedule_end_time: e_end,
			classroom_name: e_room || undefined,
		});
		if (!parsed.success) {
			compError = parsed.error.issues[0]?.message ?? 'Check the component and try again.';
			return;
		}
		// Confirm gate: a save that leaves the total mismatched without
		// converging (the pre-D81 blocker) needs a deliberate click.
		// Converging fixes and exact landings save straight through.
		if (
			course &&
			editProjection &&
			weeklyWriteBlocked(detailBreakdown?.scheduled ?? null, editProjection.scheduled, course.units)
		) {
			editConfirmOpen = true;
			return;
		}
		await persistEditComponent();
	};

	const persistEditComponent = async () => {
		if (!offering || !editingComp) return;
		editConfirmOpen = false;
		compBusy = true;
		compError = null;
		try {
			const parsed = componentCreateSchema.safeParse({
				session_type: editingComp.sessionType,
				schedule_days: e_days,
				schedule_start_time: e_start,
				schedule_end_time: e_end,
				classroom_name: e_room || undefined,
			});
			if (!parsed.success) {
				compError = parsed.error.issues[0]?.message ?? 'Check the component and try again.';
				return;
			}
			await updateComponent(offering.id, editingComp.id, {
				schedule_days: parsed.data.schedule_days,
				schedule_start_time: parsed.data.schedule_start_time,
				schedule_end_time: parsed.data.schedule_end_time,
				classroom_name: e_room.trim() ? e_room.trim() : null,
				classroom_lat: e_lat.trim() ? parseOptCoord(e_lat, 'Latitude', -90, 90) : null,
				classroom_lng: e_lng.trim() ? parseOptCoord(e_lng, 'Longitude', -180, 180) : null,
			});
			editingComp = null;
			await refreshAdminOfferingDetail(offering.id);
			notifyEntityChanged('offerings');
		} catch (e: unknown) {
			compError = compFailure(e, 'Save failed. Please try again.');
		} finally {
			compBusy = false;
		}
	};

	const removeMeetingRow = async (c: OfferingComponent): Promise<boolean> => {
		if (!offering || compBusy) return false;
		compError = null;
		compBusy = true;
		try {
			await archiveComponent(offering.id, c.id);
			if (editingComp?.id === c.id) editingComp = null;
			editConfirmOpen = false;
			await refreshAdminOfferingDetail(offering.id);
			notifyEntityChanged('offerings');
			return true;
		} catch (e: unknown) {
			compError = compFailure(e, 'Remove failed. Please try again.');
			return false;
		} finally {
			compBusy = false;
		}
	};

	const askRemoveMeeting = (c: OfferingComponent) => {
		if (compBusy) return;
		compError = null;
		removeCompTarget = c;
	};

	const confirmRemoveMeeting = async () => {
		if (!removeCompTarget) return;
		if (await removeMeetingRow(removeCompTarget)) removeCompTarget = null;
	};

	const submitAssign = async () => {
		if (!offering) return;
		assignError = null;
		assignBusy = true;
		try {
			const parsed = assignmentCreateSchema.safeParse({
				professor_id: a_professor_id,
				is_primary: a_primary,
				effective_from: a_from,
				effective_to: a_to || undefined,
				semester: a_semester,
			});
			if (!parsed.success) {
				assignError = parsed.error.issues[0]?.message ?? 'Check the form and try again.';
				return;
			}
			await assignOfferingProfessor(offering.id, {
				professor_id: parsed.data.professor_id,
				is_primary: parsed.data.is_primary,
				effective_from: parsed.data.effective_from,
				effective_to: parsed.data.effective_to || undefined,
				semester: parsed.data.semester,
			});
			assignOpen = false;
		} catch (e: unknown) {
			assignError = e instanceof Error && e.message ? e.message : 'Assign failed. Please try again.';
		} finally {
			assignBusy = false;
		}
	};

	const endRow = async (professorId: number) => {
		if (!offering) return;
		try {
			await endOfferingAssignment(offering.id, professorId);
		} catch {
			// Surfaced via the detail state's actionError.
		}
	};

	const applySection = () => {
		if (offering) loadOfferingRoster(offering.id, sectionFilter.trim() || undefined, 1);
	};

	const onBulkFile = (e: Event) => {
		const input = e.target as HTMLInputElement;
		const picked = input.files?.[0] ?? null;
		bulkFile = picked;
		bulkResult = null;
		if (picked) {
			const parsed = csvFileSchema.safeParse(picked);
			if (!parsed.success) {
				adminOfferingDetailState.actionError = parsed.error.issues[0]?.message ?? 'Invalid CSV file.';
				bulkFile = null;
				input.value = '';
			}
		}
	};

	const submitBulk = async () => {
		if (!offering || !bulkFile || bulkBusy) return;
		const parsed = csvFileSchema.safeParse(bulkFile);
		if (!parsed.success) {
			adminOfferingDetailState.actionError = parsed.error.issues[0]?.message ?? 'Invalid CSV file.';
			return;
		}
		bulkBusy = true;
		try {
			bulkResult = await bulkEnrollOffering(offering.id, bulkFile);
		} catch {
			// Surfaced via the detail state's actionError.
		} finally {
			bulkBusy = false;
		}
	};

	const openAdd = () => {
		addOpen = true;
		addQuery = '';
		addResults = [];
		addTotal = 0;
		addPage = 1;
		addReport = null;
		addSelected = [];
		adminOfferingDetailState.actionError = null;
		void loadAddCandidates(1);
	};

	const onAddQuery = () => {
		if (addSearchTimer) clearTimeout(addSearchTimer);
		addSearchTimer = setTimeout(() => void loadAddCandidates(1), 300);
	};

	// One loader for browse, pager, and search: empty query + cohort ids is
	// the browse list, a query narrows within it. Cohort-scoped, so only
	// students on the offering's program + year can take this course.
	const loadAddCandidates = async (page: number) => {
		const q = addQuery.trim();
		addSearching = true;
		try {
			const result = await listStudents({
				search: q || undefined,
				size: ADD_PAGE_SIZE,
				page,
				is_active: true,
				program_id: offering?.programId,
				year_level_id: offering?.yearLevelId,
			});
			if (q !== addQuery.trim()) return;
			addResults = result.items;
			addTotal = result.total;
			addPage = result.page;
		} catch (e: unknown) {
			adminOfferingDetailState.actionError =
				e instanceof Error && e.message ? e.message : 'Failed to load students';
		} finally {
			addSearching = false;
		}
	};

	const addTotalPages = $derived(Math.max(1, Math.ceil(addTotal / ADD_PAGE_SIZE)));

	const addCohortLabel = $derived(
		[programCode, yearLabel].filter(Boolean).join(' ') || 'this cohort'
	);

	const addEmptyCopy = $derived(
		addQuery.trim() ? `No matches in ${addCohortLabel}.` : `No students in ${addCohortLabel} yet.`
	);

	// The upload checks the CSV program against the offering, so a cross-
	// program pick is blocked here instead of round-tripping the error.
	const addProgramMismatch = $derived(
		programCode !== null &&
			addSelected.some((s) => s.programCode !== programCode)
	);

	// Enrollment status per candidate, read off the loaded roster page.
	// Advisory for rosters past page 1 (submit stays authoritative via the
	// skipped branch); membership itself never false-positives, so enrolled
	// rows are safe to disable.
	const enrolledIds = $derived(
		new Set(adminOfferingDetailState.roster.map((r) => r.studentId))
	);

	// House toggle idiom (admin/analytics, admin/professors): reassign
	// through filter/append so the reactive array invalidates.
	const toggleAddSelection = (student: AdminStudent) => {
		addSelected = addSelected.some((s) => s.id === student.id)
			? addSelected.filter((s) => s.id !== student.id)
			: [...addSelected, student];
	};

	const clearAddSelection = () => {
		if (addBusy) return;
		addSelected = [];
	};

	// Every eligible student on the visible page, so a cohort can be paged
	// through without checking boxes one by one.
	const pageEligible = $derived(
		addResults.filter((s) => !enrolledIds.has(s.studentId))
	);
	const pageAllSelected = $derived(
		pageEligible.length > 0 && pageEligible.every((s) => addSelected.some((x) => x.id === s.id))
	);
	const togglePageSelection = () => {
		if (addBusy || pageEligible.length === 0) return;
		addSelected = pageAllSelected
			? addSelected.filter((x) => !pageEligible.some((s) => s.id === x.id))
			: [...addSelected, ...pageEligible.filter((s) => !addSelected.some((x) => x.id === s.id))];
	};

	const submitAdd = async () => {
		const chosen = addSelected;
		if (!offering || chosen.length === 0 || addBusy || addProgramMismatch) return;
		addBusy = true;
		addReport = null;
		try {
			// Row order matches `chosen`, and the parser numbers data rows from
			// line 2, so an error line maps back to its student deterministically.
			const result = await bulkEnrollOffering(offering.id, buildEnrollCsv(chosen));
			const failures = result.errors.map((err) => {
				const student = chosen[err.line - 2];
				return student ? `${student.studentId} — ${err.reason}` : err.reason;
			});
			if (result.errors.length === 0 && result.skipped === 0) {
				addSelected = [];
				addOpen = false;
			} else {
				// Stay open with the report: the roster reload above already
				// flipped the newly-enrolled rows to "Already enrolled", so the
				// badges self-correct and a re-submit is at worst a repeat skip.
				addReport = {
					enrolled: result.enrolled,
					skipped: result.skipped,
					failures,
				};
			}
		} catch {
			// Surfaced via the detail state's actionError.
		} finally {
			addBusy = false;
		}
	};

	const askUnenroll = (row: AdminRosterItem) => {
		unenrollTarget = row;
	};

	const confirmUnenroll = async () => {
		if (!offering || !unenrollTarget || unenrollBusy) return;
		unenrollBusy = true;
		try {
			await unenrollStudentFromOffering(offering.id, unenrollTarget.studentId);
			unenrollTarget = null;
		} catch {
			// Surfaced via the detail state's actionError.
		} finally {
			unenrollBusy = false;
		}
	};

	const rosterTotalPages = $derived(
		Math.max(1, Math.ceil(adminOfferingDetailState.rosterTotal / 20))
	);
</script>

<div class="page">
	<div class="page-top">
		<button class="btn btn-secondary" onclick={() => goto(Routes.ADMIN_OFFERINGS)}>
			← Back to Offering Management
		</button>
	</div>

	{#if adminOfferingDetailState.loading}
		<section class="card"><p class="muted">Loading…</p></section>
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

		{#if adminOfferingDetailState.actionError && !deleteOpen && !archiveConfirm}
			<section class="card"><p class="error" role="alert">{adminOfferingDetailState.actionError}</p></section>
		{/if}

		<nav class="tabs" aria-label="Offering sections">
			<button class:active={tab === 'overview'} onclick={() => (tab = 'overview')}>Overview</button>
			<button class:active={tab === 'professors'} onclick={() => (tab = 'professors')}>Professors</button>
			<button class:active={tab === 'enrolled'} onclick={() => (tab = 'enrolled')}>Enrolled</button>
			<button class:active={tab === 'settings'} onclick={() => (tab = 'settings')}>Settings</button>
		</nav>

		{#if tab === 'overview'}
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
					<div><dt>Present window</dt><dd>{offering.presentWindowMinutes} min</dd></div>
					<div><dt>Late window</dt><dd>{offering.lateWindowMinutes} min</dd></div>
					<div><dt>Enrolled</dt><dd>{offering.enrolledCount}</dd></div>
				</dl>
				{#if course}
					<p class="muted">Template: {course.courseCode} · {course.units} units · {course.sessionDurationHours}h default session</p>
				{/if}
			</section>
		{:else if tab === 'professors'}
			<section class="card">
				<div class="row-head">
					<h2 class="card-title">Assignments</h2>
					<button class="btn btn-primary" onclick={openAssign}>Assign professor</button>
				</div>
				{#if adminOfferingDetailState.assignmentsLoading}
					<p class="muted">Loading assignments…</p>
				{:else if adminOfferingDetailState.assignments.length === 0}
					<p class="empty">No professors assigned yet. Any professor with an active assignment may open sessions for this offering.</p>
				{:else}
					<div class="table-wrap">
						<table>
							<thead>
								<tr>
									<th>Professor</th>
									<th>Role</th>
									<th>Effective</th>
									<th>Semester</th>
									<th><span class="sr">Actions</span></th>
								</tr>
							</thead>
							<tbody>
								{#each adminOfferingDetailState.assignments as a (a.professorId)}
									<tr>
										<td>
											<div class="strong">{professorName(a.professorId)}</div>
											<div class="muted small">{professorEmail(a.professorId)}</div>
										</td>
										<td>
											<span class="badge" class:inactive={!a.isPrimary}>
												{a.isPrimary ? 'Primary' : 'Assistant'}
											</span>
										</td>
										<td>{a.effectiveFrom} → {a.effectiveTo ?? 'ongoing'}</td>
										<td>{a.semester}</td>
										<td>
											<div class="row-actions">
												{#if !a.effectiveTo}
													<button class="link" onclick={() => endRow(a.professorId)}>End</button>
												{:else}
													<span class="muted small">ended</span>
												{/if}
											</div>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
					<p class="hint">Mid-term replacement: end the old assignment, then create the new one — history is never rewritten.</p>
				{/if}
			</section>
		{:else if tab === 'enrolled'}
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
					<p class="muted">Loading roster…</p>
				{:else if adminOfferingDetailState.roster.length === 0}
					<p class="empty">No students enrolled yet.</p>
				{:else}
					<div class="table-wrap">
						<table>
							<thead>
								<tr>
									<th>Student ID</th>
									<th>Name</th>
									<th>Section</th>
									<th>Enrolled</th>
									<th><span class="sr">Actions</span></th>
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

			<section class="card">
				<h2 class="card-title">Bulk enroll</h2>
				<p class="muted">CSV of EXISTING students: student_id, first_name, middle_name, last_name, email, program_code, year_level, section. Rows that fail (unknown id, email mismatch, wrong program) are reported per line, not applied.</p>
				<div class="filters">
					<input class="input" type="file" accept=".csv,text/csv" onchange={onBulkFile} aria-label="Roster CSV file" />
					<button class="btn btn-primary" disabled={!bulkFile || bulkBusy} onclick={submitBulk}>
						{bulkBusy ? 'Uploading…' : 'Upload'}
					</button>
				</div>
				{#if bulkResult}
					<p class="muted" role="status">
						Enrolled {bulkResult.enrolled} · skipped {bulkResult.skipped}
						{#if bulkResult.errors.length > 0}
							· {bulkResult.errors.length} error{bulkResult.errors.length === 1 ? '' : 's'}:
						{/if}
					</p>
					{#if bulkResult.errors.length > 0}
						<ul class="error-list">
							{#each bulkResult.errors as err (err.line)}
								<li>Line {err.line}: {err.reason}</li>
							{/each}
						</ul>
					{/if}
				{/if}
			</section>
		{:else}
			<section class="card">
				<h2 class="card-title">Class meetings</h2>
				<p class="muted">Each row is one weekly meeting with its own days, time, and room. A course with a Monday laboratory and a Wednesday lecture is two rows — sessions inherit the room of their meeting type.</p>
				{#if detailBreakdown && course}
					{#if detailBreakdown.status === 'ok'}
						<p class="hint">{detailBreakdown.scheduled}h scheduled of {detailBreakdown.limit}h weekly requirement ({course.courseCode} · exact).</p>
					{:else if detailBreakdown.status === 'over'}
						<p class="error" role="alert">{detailBreakdown.scheduled}h scheduled of {detailBreakdown.limit}h weekly requirement ({course.courseCode} · {-detailBreakdown.remaining}h over).</p>
					{:else}
						<p class="error" role="alert">{detailBreakdown.scheduled}h scheduled of {detailBreakdown.limit}h weekly requirement ({course.courseCode} · {detailBreakdown.remaining}h short).</p>
					{/if}
					{#if detailBreakdown.status !== 'ok'}
						<div class="blocked-note" role="note">
							<AppIcon name="alert" size={16} />
							<span><strong>Sessions cannot be opened for this offering</strong> until the total matches — new sessions are refused and reactivation is disabled.</span>
						</div>
					{/if}
				{/if}
				{#if compError}
					<p class="error" role="alert">{compError}</p>
				{/if}
				{#if offering.components.length === 0}
					<p class="empty">No active components. Add one below so sessions have a schedule to inherit.</p>
				{:else}
					<div class="table-wrap">
						<table>
							<thead>
								<tr>
									<th>Type</th>
									<th>Days</th>
									<th>Time</th>
									<th>Room</th>
									<th><span class="sr">Actions</span></th>
								</tr>
							</thead>
							<tbody>
								{#each offering.components as comp (comp.id)}
									<tr>
										<td>
											<span class="badge type-lab" class:type-lec={comp.sessionType === 'lecture'}>
												{comp.sessionType === 'lab' ? 'Laboratory' : 'Lecture'}
											</span>
										</td>
										<td>{comp.scheduleDays}</td>
										<td>{comp.scheduleStartTime.slice(0, 5)}–{comp.scheduleEndTime.slice(0, 5)}</td>
										<td>{comp.classroomName ?? '—'}</td>
										<td>
											<div class="row-actions">
												<button class="link" onclick={() => openEditComponent(comp)}>Edit</button>
												<button class="link" disabled={compBusy} onclick={() => askRemoveMeeting(comp)}>Remove</button>
											</div>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
				{#if editingComp}
					<div class="comp-edit">
						<h3 class="sub-title">Edit {editingComp.sessionType === 'lab' ? 'laboratory' : 'lecture'} meeting</h3>
						{#if e_customDays}
							<label>Days<input class="input" bind:value={e_days} placeholder="MWF" /></label>
						{:else}
							<DayPicker bind:value={e_days} />
						{/if}
						<div class="grid2">
							<label>Start time<input class="input" type="time" bind:value={e_start} /></label>
							<label>End time<input class="input" type="time" bind:value={e_end} /></label>
						</div>
						<label>Room (optional)<input class="input" bind:value={e_room} placeholder="Lab 101" /></label>
						<div class="grid2">
							<label>Latitude (optional)<input class="input" inputmode="decimal" bind:value={e_lat} /></label>
							<label>Longitude (optional)<input class="input" inputmode="decimal" bind:value={e_lng} /></label>
						</div>
						{#if course && editProjection}
							<p class="hint">Saving would bring the weekly total to {editProjection.scheduled}h of {editProjection.limit}h ({editProjection.status === 'ok' ? 'exact' : editProjection.status === 'under' ? `${editProjection.remaining}h short` : `${-editProjection.remaining}h over`}). Reshapes save freely — the panel above tracks the total back to exact.</p>
						{/if}
						<div class="modal-actions">
							<button class="btn btn-ghost" onclick={() => { editingComp = null; editConfirmOpen = false; }}>Cancel</button>
							<button class="btn btn-primary" disabled={compBusy} onclick={submitEditComponent}>
								{compBusy ? 'Saving…' : 'Save'}
							</button>
						</div>
					</div>
				{:else}
					<div class="comp-add">
						<h3 class="sub-title">Add a meeting</h3>
						<p class="hint">One row, one time: days on the same row share the time below. For a different time, add another row.</p>
						<DayPicker bind:value={c_days} />
						<label>Type
							<select class="input" bind:value={c_type}>
								<option value="lecture">Lecture</option>
								<option value="lab">Laboratory</option>
							</select>
						</label>
						<div class="grid2">
							<label>Start time<input class="input" type="time" bind:value={c_start} /></label>
							<label>End time<input class="input" type="time" bind:value={c_end} /></label>
						</div>
						<label>Room (optional)<input class="input" bind:value={c_room} placeholder="Lab 101" /></label>
						<div class="grid2">
							<label>Latitude (optional)<input class="input" inputmode="decimal" bind:value={c_lat} placeholder="14.5995" /></label>
							<label>Longitude (optional)<input class="input" inputmode="decimal" bind:value={c_lng} placeholder="120.9842" /></label>
						</div>
						<p class="hint">Laboratory meetings should carry coordinates: lab sessions enforce the geofence and inherit this room when the professor opens them without an override.</p>
						{#if course && addProjection && c_days.trim() && c_start && c_end}
							{#if addBlocked}
								<p class="error" role="alert">Adding this meeting would bring the weekly total to {addProjection.scheduled}h of {addProjection.limit}h ({addProjection.status === 'under' ? `${addProjection.remaining}h short` : `${-addProjection.remaining}h over`}).</p>
							{:else}
								<p class="hint">Adding this meeting would bring the weekly total to {addProjection.scheduled}h of {addProjection.limit}h ({addProjection.status === 'ok' ? 'exact' : addProjection.status === 'under' ? `${addProjection.remaining}h short` : `${-addProjection.remaining}h over`}).</p>
							{/if}
						{/if}
						<div class="modal-actions">
							<button class="btn btn-secondary" disabled={compBusy} onclick={submitAddComponent}>
								{compBusy ? 'Adding…' : 'Add meeting'}
							</button>
						</div>
					</div>
				{/if}
			</section>

			<section class="card">
				<h2 class="card-title">Offering settings</h2>
				<p class="muted">Rates and windows only. Course, program, year, semester, and academic year are identity — they cannot be changed after creation.</p>
				{#if settingsError}
					<p class="error" role="alert">{settingsError}</p>
				{/if}
				<div class="form">
					<div class="grid2">
						<label>Sessions / week (automatic)<input class="input" value={detailSessionCount} disabled aria-label="Sessions per week, counted automatically from the meetings" /></label>
						<label>Semester weeks (from term)<input class="input" value={offering.semesterWeeks} disabled aria-label="Session weeks, set on the term in Manage Terms" /></label>
					</div>
					<p class="hint">Sessions per week are counted from the class meetings above — one per meeting day — and update automatically when meetings change.</p>
					{#if detailExpectedTotal !== null}
						<p class="hint">{detailSessionCount} sessions/week × {offering.semesterWeeks} weeks = {detailExpectedTotal} expected sessions this term. Edit the term's weeks in Program Management → Year Levels → Manage Terms.</p>
					{/if}
					<div class="grid2">
						<label>Present window, min<input class="input" inputmode="numeric" bind:value={s_present} /></label>
						<label>Late window, min<input class="input" inputmode="numeric" bind:value={s_late} /></label>
					</div>
					<p class="hint">Present + late windows must fit the course session duration.</p>
				</div>
				<div class="modal-actions">
					<button class="btn btn-ghost" onclick={fillSettings}>Reset</button>
					<button class="btn btn-primary" disabled={settingsBusy} onclick={submitSettings}>
						{settingsBusy ? 'Saving…' : 'Save'}
					</button>
				</div>
			</section>

			<section class="card danger">
				<h2 class="card-title">Danger zone</h2>
				<p class="muted">
					Status: <strong>{offering.isActive ? 'Active' : 'Inactive'}</strong>. Archiving
					flips this offering to inactive — sessions history is kept. Reactivating
					restores it, but requires the weekly scheduled hours to match the course
					units requirement. Deletion is permanent and blocked while students,
					sessions, or professor assignments still use this offering.
				</p>
				<div class="danger-actions">
					{#if offering.isActive}
						<button class="btn btn-danger" disabled={archiveBusy} onclick={() => { adminOfferingDetailState.actionError = null; archiveConfirm = true; }}>
							Archive offering
						</button>
					{:else}
						<button
							class="btn btn-secondary"
							disabled={archiveBusy || (!!course && !!detailBreakdown && detailBreakdown.status !== 'ok')}
							title={!!course && !!detailBreakdown && detailBreakdown.status !== 'ok' ? 'Weekly scheduled hours do not match the course units requirement — fix the meetings first' : undefined}
							onclick={onReactivate}
						>
							{archiveBusy ? 'Reactivating…' : 'Reactivate offering'}
						</button>
					{/if}
					<button
						class="btn btn-danger"
						disabled={deleteBusy || offering.isActive}
						title={offering.isActive ? 'Archive first — only archived offerings can be deleted' : undefined}
						onclick={() => { adminOfferingDetailState.actionError = null; deleteOpen = true; }}
					>
						Delete permanently
					</button>
				</div>
				{#if !offering.isActive}
					<p class="hint">Delete is blocked while students, sessions, or professor assignments still use this offering.</p>
				{/if}
			</section>
		{/if}
	{/if}
</div>

{#if assignOpen && offering}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="assign-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (assignOpen = false) }}
		>
			<h2 id="assign-title" class="modal-title">Assign professor</h2>
			{#if assignError}
				<p class="error" role="alert">{assignError}</p>
			{/if}
			<div class="form">
				<label>Professor
					<select class="input" bind:value={a_professor_id}>
						<option value="">Pick a professor…</option>
						{#each [...professorIndex.values()] as p (p.id)}
							<option value={p.id}>{p.firstName} {p.lastName} — {p.email}</option>
						{/each}
					</select>
				</label>
				<label class="check">
					<input type="checkbox" bind:checked={a_primary} /> Primary (uncheck for assistant)
				</label>
				<div class="grid2">
					<label>Effective from<input class="input" type="date" bind:value={a_from} /></label>
					<label>Effective to (optional)<input class="input" type="date" bind:value={a_to} /></label>
				</div>
				<label>Semester<input class="input" bind:value={a_semester} placeholder="1st Sem" /></label>
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (assignOpen = false)}>Cancel</button>
				<button class="btn btn-primary" disabled={assignBusy} onclick={submitAssign}>
					{assignBusy ? 'Saving…' : 'Assign'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if addOpen && offering}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="add-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (addOpen = false) }}
		>
			<h2 id="add-title" class="modal-title">Add student</h2>
			<div class="form">
				<label>Find student
					<input
						class="input"
						placeholder="ID, name, or email"
						aria-label="Find student"
						bind:value={addQuery}
						oninput={onAddQuery}
					/>
				</label>
				{#if addSearching && addResults.length === 0}
					<p class="muted">Searching…</p>
				{:else if addResults.length === 0}
					<p class="empty">{addEmptyCopy}</p>
				{:else}
					<div class="pick-bar">
						<label class="check pick-all">
							<input
								type="checkbox"
								checked={pageAllSelected}
								disabled={addBusy || pageEligible.length === 0}
								onchange={togglePageSelection}
							/>
							<span>Select all on page</span>
						</label>
						{#if addSelected.length > 0}
							<span class="muted">{addSelected.length} selected</span>
							<button class="link" disabled={addBusy} onclick={clearAddSelection}>
								Clear
							</button>
						{/if}
					</div>
					<ul class="pick-list">
						{#each addResults as s (s.id)}
							<li class="pick-row">
								{#if enrolledIds.has(s.studentId)}
									<span class="muted">{s.studentId} — {s.firstName} {s.lastName}</span>
									<span class="badge inactive">Already enrolled</span>
								{:else}
									<label class="check">
										<input
											type="checkbox"
											checked={addSelected.some((x) => x.id === s.id)}
											disabled={addBusy}
											aria-label={`Select ${s.studentId}`}
											onchange={() => toggleAddSelection(s)}
										/>
										<span>{s.studentId} — {s.firstName} {s.lastName} ({s.programCode})</span>
									</label>
									<span class="badge">Can enroll</span>
								{/if}
							</li>
						{/each}
					</ul>
					{#if !addSearching && addTotalPages > 1}
						<div class="pager">
							<button
								class="btn btn-secondary"
								disabled={addPage <= 1 || addBusy}
								onclick={() => void loadAddCandidates(addPage - 1)}
							>
								‹ Prev
							</button>
							<span class="muted">Page {addPage} of {addTotalPages}</span>
							<button
								class="btn btn-secondary"
								disabled={addPage >= addTotalPages || addBusy}
								onclick={() => void loadAddCandidates(addPage + 1)}
							>
								Next ›
							</button>
						</div>
					{/if}
				{/if}
				{#if addReport}
					<p class="muted" role="status">
						Enrolled {addReport.enrolled} · skipped {addReport.skipped}
						{#if addReport.failures.length > 0} · {addReport.failures.length} error{addReport.failures.length === 1 ? '' : 's'}:{/if}
					</p>
					{#each addReport.failures as failure (failure)}
						<p class="error" role="alert">{failure}</p>
					{/each}
				{/if}
				{#if adminOfferingDetailState.actionError}
					<p class="error" role="alert">{adminOfferingDetailState.actionError}</p>
				{/if}
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (addOpen = false)}>Cancel</button>
				<button
					class="btn btn-primary"
					disabled={addSelected.length === 0 || addBusy || addProgramMismatch}
					onclick={submitAdd}
				>
					{addBusy ? 'Enrolling…' : addSelected.length > 1 ? `Enroll ${addSelected.length}` : 'Enroll'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if editConfirmOpen && course && editProjection && offering}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="edit-confirm-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (editConfirmOpen = false) }}
		>
			<h2 id="edit-confirm-title" class="modal-title">Save a mismatched total?</h2>
			<p class="modal-text">
				Saving would leave the weekly total at {editProjection.scheduled}h against the
				{course.units}-unit requirement ({editProjection.status === 'under' ? `${editProjection.remaining}h short` : `${-editProjection.remaining}h over`}).
				The red panels will track it until the schedule converges back to exact.
			</p>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (editConfirmOpen = false)}>Cancel</button>
				<button class="btn btn-primary" disabled={compBusy} onclick={() => void persistEditComponent()}>
					{compBusy ? 'Saving…' : 'Save anyway'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if unenrollTarget && offering}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="unenroll-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (unenrollTarget = null) }}
		>
			<h2 id="unenroll-title" class="modal-title">Remove student?</h2>
			<p class="muted">
				{unenrollTarget.name} ({unenrollTarget.studentId}) will be unenrolled from
				this offering. Past attendance history is kept; future scans will be blocked.
			</p>
			{#if adminOfferingDetailState.actionError}
				<p class="error" role="alert">{adminOfferingDetailState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (unenrollTarget = null)}>Cancel</button>
				<button class="btn btn-danger" disabled={unenrollBusy} onclick={confirmUnenroll}>
					{unenrollBusy ? 'Removing…' : 'Remove'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if archiveConfirm && offering}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="offering-archive-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (archiveConfirm = false) }}
		>
			<h2 id="offering-archive-title" class="modal-title">Archive this offering?</h2>
			<p class="modal-text">
				It will be flipped to inactive. Sessions history is kept, and you can
				reactivate it anytime.
			</p>
			{#if adminOfferingDetailState.actionError}
				<p class="error" role="alert">{adminOfferingDetailState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (archiveConfirm = false)}>Cancel</button>
				<button class="btn btn-danger" disabled={archiveBusy} onclick={confirmArchive}>
					{archiveBusy ? 'Archiving…' : 'Archive'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if deleteOpen && offering}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="offering-delete-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (deleteOpen = false) }}
		>
			<h2 id="offering-delete-title" class="modal-title">Permanently delete this offering?</h2>
			<p class="modal-text">
				The offering and its meetings will be removed for good.
				If students, sessions, or professor assignments still use it, deletion will be blocked
				and the offering stays archived.
			</p>
			{#if adminOfferingDetailState.actionError}
				<p class="error" role="alert">{adminOfferingDetailState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (deleteOpen = false)}>Cancel</button>
				<button class="btn btn-danger" disabled={deleteBusy} onclick={confirmDelete}>
					{deleteBusy ? 'Deleting…' : 'Delete'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if removeCompTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="component-remove-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (removeCompTarget = null) }}
		>
			<h2 id="component-remove-title" class="modal-title">Remove this meeting?</h2>
			<p class="modal-text">
				It will be taken off this offering's active schedule. Attendance history
				for past sessions is kept.
			</p>
			{#if compError}
				<p class="error" role="alert">{compError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (removeCompTarget = null)}>Cancel</button>
				<button class="btn btn-danger" disabled={compBusy} onclick={confirmRemoveMeeting}>
					{compBusy ? 'Removing…' : 'Remove'}
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

	.muted.small {
		font-size: 0.75rem;
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

	.danger {
		border-color: var(--danger-bg);
	}

	.danger-actions {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
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

	td .strong {
		font-size: 0.875rem;
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

	.blocked-note {
		display: flex;
		align-items: flex-start;
		gap: 0.5rem;
		font-size: 0.8125rem;
		color: var(--danger);
		background: var(--danger-bg);
		border: 1px solid var(--danger-bg);
		border-radius: 8px;
		padding: 0.625rem 0.875rem;
		margin: 0;
	}

	.blocked-note :global(svg) {
		flex-shrink: 0;
		margin-top: 0.125rem;
	}

	.sub-title {
		margin: 1rem 0 0.5rem;
		font-size: 1rem;
		font-weight: 700;
		color: var(--text);
	}

	.comp-edit,
	.comp-add {
		display: flex;
		flex-direction: column;
		gap: 0.875rem;
		margin-top: 1.25rem;
		padding-top: 1.25rem;
		border-top: 1px solid var(--divider);
	}

	/* Inside the meeting forms the flex `gap` owns the vertical rhythm —
		section-level margins would otherwise stack on top of it (e.g. a
		2.4rem pile-up between the heading and its hint). */
	.comp-edit > .hint,
	.comp-add > .hint,
	.comp-add > .error,
	.comp-edit > .sub-title,
	.comp-add > .sub-title {
		margin: 0;
	}

	.comp-edit label,
	.comp-add label {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
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

	.error-list {
		color: var(--danger);
		font-size: 0.8125rem;
		margin: 0.5rem 0 0;
		padding-left: 1.25rem;
	}

	.hint {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin: 1rem 0 0;
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

	.btn-danger {
		background: var(--danger);
		border: 1px solid var(--danger);
		color: var(--on-brand);
	}

	.btn-danger:hover:not(:disabled) {
		background: var(--danger-strong);
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

	.form label.check {
		flex-direction: row;
		align-items: center;
		gap: 0.5rem;
	}

	.pick-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 0.25rem;
	}

	.pick-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
	}

	.pick-bar {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		font-size: 0.8125rem;
	}

	.grid2 {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.875rem;
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

		.grid2,
		.facts {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
