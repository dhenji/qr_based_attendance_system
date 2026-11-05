// features/session/service.ts
// Professor-facing service: open/close sessions, live feed, session codes.
//
// Everything here hits the real backend (features/session/router.py) by
// default, and the endpoint mocks only when PUBLIC_MOCK_MODE=true. Course
// display names join client-side from the professor courses store, because
// session rows carry only offering_id.
//
// Not owned here: excuse actions live in features/excuse/service.ts
// (quickExcuseByIds / editExcuse / revokeExcuse / excuseAllAbsent), which
// wraps the live excuse router by integer id. Live-session rows carry only
// student numbers, so pages resolve through the excuse queue (which keeps
// integer ids) or use the mock typed-number quickExcuse in mock mode.

import { get, post } from '$lib/api/client';
import type { Paginated } from '$lib/api/endpoints';
import type {
	CourseType,
	LiveSession,
	LiveStudent,
	OpenedSession,
	SessionActiveResponse,
	SessionCloseResponse,
	SessionHistoryItemResponse,
	SessionListItemResponse,
	SessionPlanResponse,
	SessionReadResponse,
	SessionRowStatus,
	SessionSummary,
} from '$lib/shared/types';
import {
	initProfessorCourses,
	professorState,
} from '$lib/features/professor/store.svelte';

// A frozen sample in the exact shape session codes take. The create page
// imports this for its inert placeholder so the two cannot drift apart.
export const SESSION_CODE_SAMPLE = '7X-9K2M';

export type SessionHistorySortBy = 'date' | 'code' | 'rate';
export type SessionHistorySortDir = 'asc' | 'desc';

// History row: the contract row plus client-joined display fields. The
// backend item carries no course identity, section, or enrolled total, so
// those join/derive here (see below). `enrolledCount` is null when it cannot
// be derived exactly (a session with zero presents), and the page renders
// an em dash for it.
export type SessionHistoryRow = {
	id: number;
	offering_id: number;
	session_type: CourseType;
	course_code: string;
	course_name: string;
	section: string;
	session_code: string;
	created_at: string;
	expires_at: string | null;
	present_count: number;
	late_count: number;
	absent_count: number;
	enrolled_count: number | null;
	compliance_rate: number;
	participation_rate: number;
	status: SessionRowStatus;
};

export type SessionHistoryFilters = {
	offeringId?: number;
	course?: string;
	section?: string;
	sessionType?: CourseType;
	from?: string;
	to?: string;
	sortBy?: SessionHistorySortBy;
	sortDir?: SessionHistorySortDir;
	page?: number;
	size?: number;
};

// --- Course join ------------------------------------------------------------
//
// Session rows reference offerings only. The courses store (GET
// /professor/courses) resolves offering_id -> display identity. Warmed
// once per page load; an unclaimed professor simply joins nothing.
let coursesReady = false;

// Invalidate the warmed course join (e.g. after an admin assignment change).
// Next list call re-warms from GET /professor/courses.
export const invalidateCourseCache = (): void => {
	coursesReady = false;
};

const ensureCourses = async (): Promise<void> => {
	// A previous warm may have failed (or belonged to another account whose
	// state was reset) — drop the flag so we retry instead of serving stale/
	// empty course identity (which surfaces as generic "Offering N" names).
	if (coursesReady && professorState.courses.length === 0 && professorState.coursesError) {
		coursesReady = false;
	}
	if (coursesReady) return;
	coursesReady = true;
	if (professorState.courses.length === 0 && !professorState.coursesError) {
		await initProfessorCourses();
	}
	// If warming failed, allow the next call to retry rather than pinning the
	// empty state for the rest of the session.
	if (professorState.coursesError) {
		coursesReady = false;
	}
};

const courseFor = (offeringId: number) =>
	professorState.courses.find((course) => course.offeringId === offeringId) ?? null;

const courseCodeFor = (offeringId: number) => courseFor(offeringId)?.courseCode ?? `Offering ${offeringId}`;

const courseNameFor = (offeringId: number) => courseFor(offeringId)?.courseName ?? '';

const sectionsFor = (offeringId: number): string => {
	const sections = courseFor(offeringId)?.sections ?? [];
	return sections.length > 0 ? sections.join(', ') : '—';
};

// listSessions
// Recent/live sessions, optionally filtered by date range, offering, or
// type. Course display names join client-side; sorting stays on the page.
export const listSessions = async (params?: {
	from?: string;
	to?: string;
	offeringId?: number;
	sessionType?: CourseType;
	page?: number;
	size?: number;
}) => {
	await ensureCourses();

	const query: Record<string, string> = {};
	if (params?.from) query.date_from = params.from;
	if (params?.to) query.date_to = params.to;
	if (params?.offeringId !== undefined) query.offering_id = String(params.offeringId);
	if (params?.sessionType) query.session_type = params.sessionType;
	query.page = String(params?.page ?? 1);
	query.size = String(params?.size ?? 50);

	const response = await get<Paginated<SessionListItemResponse>>('sessionList', query);

	const items: SessionSummary[] = (response.items ?? []).map((item) => ({
		id: item.id,
		offeringId: item.offering_id,
		sessionType: item.session_type ?? 'lecture',
		courseCode: courseCodeFor(item.offering_id),
		courseName: courseNameFor(item.offering_id),
		section: sectionsFor(item.offering_id),
		sessionCode: item.session_code,
		createdAt: item.created_at,
		expiresAt: item.expires_at,
		durationMinutes: item.duration_minutes,
		presentCount: item.present_count,
		lateCount: item.late_count,
		absentCount: item.absent_count,
		pendingCount: item.pending_count ?? 0,
		status: item.status,
	}));

	return { items, total: response.total, page: response.page, size: response.size };
};

// getSessionPlan
// What a session for this offering would inherit (D93): the meeting it
// belongs to, the next occurrence of that meeting, the attendance windows,
// the classroom and the geofence radius. The open form renders this instead
// of re-deriving the schedule, so what the professor sees is what the
// server will store.
export const getSessionPlan = async (
	offeringId: number,
	sessionType: CourseType = 'lecture'
): Promise<SessionPlanResponse> => {
	const query: Record<string, string> = { session_type: sessionType };

	return get<SessionPlanResponse>('sessionPlan', query, `/${offeringId}/session-plan`);
};

// openSession
// Create a new attendance session against a course offering. qrPayload is what
// gets rendered into the QR code students scan.
//
// The session inherits the offering's configuration (D93), so the form sends
// only what the professor actually changed: an omitted window, radius or
// coordinate is resolved server-side from the offering's plan. `sessionDate`
// and `startTime` are the schedule exception — a wall-clock date and time in
// the institution's timezone — and either one marks the session as
// overridden.
export const openSession = async (
	offeringId: number,
	options?: {
		sessionType?: CourseType;
		durationMinutes?: number;
		presentWindowMinutes?: number;
		lateWindowMinutes?: number;
		geofenceRadius?: number;
		// D17: a classroom override replaces the offering defaults when set.
		classroomName?: string;
		classroomLat?: number;
		classroomLng?: number;
		classroomOverride?: boolean;
		// Remote/online session: skips the geofence.
		isRemote?: boolean;
		// Whether the geofence is enforced for this session.
		geofenceEnabled?: boolean;
		// D93: the schedule exception.
		sessionDate?: string;
		startTime?: string;
		// D94: why the professor moved the class, in their own words.
		overrideReason?: string;
	}
): Promise<OpenedSession> => {
	const body: Record<string, number | string | boolean> = { offering_id: offeringId };
	if (options?.sessionType !== undefined) body.session_type = options.sessionType;
	if (options?.durationMinutes !== undefined) body.duration_minutes = options.durationMinutes;
	if (options?.presentWindowMinutes !== undefined)
		body.present_window_minutes = options.presentWindowMinutes;
	if (options?.lateWindowMinutes !== undefined)
		body.late_window_minutes = options.lateWindowMinutes;
	if (options?.geofenceRadius !== undefined) body.classroom_radius_meters = options.geofenceRadius;
	if (options?.classroomName !== undefined && options.classroomName.trim() !== '')
		body.classroom_name = options.classroomName.trim();
	if (options?.classroomLat !== undefined) body.classroom_lat = options.classroomLat;
	if (options?.classroomLng !== undefined) body.classroom_lng = options.classroomLng;
	if (options?.classroomOverride !== undefined) body.classroom_override = options.classroomOverride;
	if (options?.isRemote !== undefined) body.is_remote = options.isRemote;
	if (options?.geofenceEnabled !== undefined) body.geofence_enabled = options.geofenceEnabled;
	if (options?.sessionDate !== undefined) body.session_date = options.sessionDate;
	if (options?.startTime !== undefined) body.start_time = options.startTime;
	if (options?.overrideReason !== undefined && options.overrideReason.trim() !== '')
		body.override_reason = options.overrideReason.trim();

	const response = await post<SessionReadResponse>('sessionCreate', body);

	return {
		id: response.id,
		offeringId: response.offering_id,
		sessionType: response.session_type ?? 'lecture',
		isRemote: response.is_remote ?? false,
		sessionCode: response.session_code,
		qrPayload: response.qr_payload,
		expiresAt: response.expires_at,
		scheduledStartTime: response.scheduled_start_time,
		scheduledEndTime: response.scheduled_end_time,
		scheduleOverridden: response.schedule_overridden ?? false,
		actualStartTime: response.actual_start_time ?? null,
		originalScheduledStartTime: response.original_scheduled_start_time ?? null,
		overrideReason: response.override_reason ?? null,
		createdAt: response.created_at,
	};
};

// closeSession
// Mark a session closed; students can no longer scan against it.
export const closeSession = async (sessionId: number) => {
	const response = await post<SessionCloseResponse>('sessionClose', undefined, undefined, `/${sessionId}/close`);

	return {
		id: response.id,
		status: response.status,
		finalCounts: response.final_counts,
	};
};

// getActiveSession
// Fetch one session's live feed in the professor contract shape. The old mock
// carried a per-student `gps` verdict and internal excuse notes; the contract
// exposes neither, so both are gone — `excuse_reason` is the only per-student
// excuse text. A backend 404 (wrong id, or another professor's session)
// rejects, and the page renders its not-found state from that.
export const getActiveSession = async (
	sessionId: number,
	signal?: AbortSignal | null
): Promise<LiveSession> => {
	await ensureCourses();
	const response = await get<SessionActiveResponse>(
		'sessionActive',
		undefined,
		`/${sessionId}`,
		signal ? { signal } : undefined
	);

	const students: LiveStudent[] = (response.students ?? []).map((student) => ({
		studentNumber: student.student_number,
		name: student.name,
		section: student.section,
		status: student.status,
		scannedAt: student.scanned_at,
		excuseReason: student.excuse_reason,
	}));

	const course = courseFor(response.offering);

	return {
		id: response.id,
		offeringId: response.offering,
		sessionType: response.session_type ?? 'lecture',
		isRemote: response.is_remote ?? false,
		offeringCode: courseCodeFor(response.offering),
		offeringName: courseNameFor(response.offering),
		offeringSections: sectionsFor(response.offering),
		offeringProgram: response.program_code ?? course?.programCode ?? null,
		offeringYearLevel: response.year_level_label ?? course?.yearLevelLabel ?? null,
		sessionCode: response.session_code,
		scanWindowRemaining: response.scan_window_remaining,
		scheduledStartTime: response.scheduled_start_time,
		scheduledEndTime: response.scheduled_end_time,
		expiresAt: response.expires_at ?? null,
		status: response.status,
		enrolledCount: response.enrolled_count,
		remaining: response.remaining,
		pendingSyncCount: response.pending_sync_count,
		students,
		counts: response.counts,
	};
};

// listSessionHistory
// Paginated completed-session history (contract: GET
// /professor/sessions/history with ?offering_id&section&date_from&date_to&
// sort_by&sort_dir&page&size). Sorted newest-first by default, matching the
// wireframe's Jul29-first table.
//
// Two client-side enrichments, both flagged on the row type: course identity
// joins from the courses store, and `enrolled_count` derives from
// present/compliance_rate (compliance = present/enrolled server-side, so the
// quotient is exact; null when compliance is zero).
//
// The backend filters by offering_id, not course code. When the page filters
// by course, fan out one query per matching offering and merge — a professor
// holds a handful of offerings, and this keeps pagination and totals exact.
// `section` passes straight through (the backend accepts it); the row's
// display section joins from the courses store. Server-side sort covers
// date/code/rate; course-filtered merges sort client-side with the same key.
export const listSessionHistory = async (params?: SessionHistoryFilters) => {
	await ensureCourses();

	const sortBy = params?.sortBy ?? 'date';
	const sortDir = params?.sortDir ?? 'desc';

	const offeringIds =
		params?.offeringId !== undefined
			? [params.offeringId]
			: params?.course !== undefined
				? professorState.courses
						.filter((course) => course.courseCode === params.course)
						.map((course) => course.offeringId)
				: [undefined];

	const direction = sortDir === 'asc' ? 1 : -1;
	const compareRows = (a: SessionHistoryRow, b: SessionHistoryRow): number => {
		if (sortBy === 'code') return a.session_code.localeCompare(b.session_code) * direction;
		if (sortBy === 'rate') return (a.compliance_rate - b.compliance_rate) * direction;
		return a.created_at.localeCompare(b.created_at) * direction;
	};

	const toRow = (item: SessionHistoryItemResponse): SessionHistoryRow => ({
		id: item.id,
		offering_id: item.offering_id,
		session_type: item.session_type ?? 'lecture',
		course_code: courseCodeFor(item.offering_id),
		course_name: courseNameFor(item.offering_id),
		section: sectionsFor(item.offering_id),
		session_code: item.session_code,
		created_at: item.created_at,
		expires_at: item.expires_at,
		present_count: item.present_count,
		late_count: item.late_count,
		absent_count: item.absent_count,
		enrolled_count:
			item.compliance_rate > 0 ? Math.round(item.present_count / item.compliance_rate) : null,
		compliance_rate: item.compliance_rate,
		participation_rate: item.participation_rate,
		status: item.status,
	});

	// Single-offering (or unfiltered) path: one query, server-side sort/page.
	if (offeringIds.length <= 1) {
		const query: Record<string, string> = {
			sort_by: sortBy,
			sort_dir: sortDir,
			page: String(params?.page ?? 1),
			size: String(params?.size ?? 20),
		};
		if (offeringIds[0] !== undefined) query.offering_id = String(offeringIds[0]);
		if (params?.sessionType) query.session_type = params.sessionType;
		if (params?.section !== undefined) query.section = params.section;
		if (params?.from) query.date_from = params.from;
		if (params?.to) query.date_to = params.to;

		const response = await get<Paginated<SessionHistoryItemResponse>>('sessionHistory', query);
		const items = (response.items ?? []).map(toRow);
		return {
			items,
			total: response.total,
			page: response.page,
			size: response.size,
			// Page average only — the backend returns no scope aggregate, so
			// callers must label this as the current page, not the term.
			avg_compliance:
				items.length === 0
					? 0
					: items.reduce((total, row) => total + row.compliance_rate, 0) / items.length,
			total_sessions: response.total,
			avg_scope: 'page' as const,
		};
	}

	// Course-filtered path: fan out per offering, merge, sort, slice.
	// Each offering is paged to exhaustion (size 100 is the server max), so
	// offerings with >100 sessions are fully merged, not truncated.
	const merged: SessionHistoryRow[] = [];
	for (const offeringId of offeringIds) {
		if (offeringId === undefined) continue;
		let page = 1;
		for (;;) {
			const query: Record<string, string> = {
				offering_id: String(offeringId),
				sort_by: 'date',
				sort_dir: 'desc',
				page: String(page),
				size: '100',
			};
			if (params?.section !== undefined) query.section = params.section;
			if (params?.sessionType) query.session_type = params.sessionType;
			if (params?.from) query.date_from = params.from;
			if (params?.to) query.date_to = params.to;
			const response = await get<Paginated<SessionHistoryItemResponse>>('sessionHistory', query);
			for (const item of response.items ?? []) merged.push(toRow(item));
			const total = response.total ?? 0;
			const got = page * 100;
			if ((response.items ?? []).length < 100 || got >= total) break;
			page += 1;
		}
	}
	merged.sort(compareRows);

	const size = Math.min(Math.max(params?.size ?? 20, 1), 100);
	const pageCount = Math.max(1, Math.ceil(merged.length / size));
	const page = Math.min(Math.max(params?.page ?? 1, 1), pageCount);
	const items = merged.slice((page - 1) * size, page * size);

	return {
		items,
		total: merged.length,
		page,
		size,
		// Merged-set average (all offerings matching the course filter), not a
		// backend scope total — label accordingly.
		avg_compliance:
			merged.length === 0
				? 0
				: merged.reduce((total, row) => total + row.compliance_rate, 0) / merged.length,
		total_sessions: merged.length,
		avg_scope: 'filtered' as const,
	};
};
