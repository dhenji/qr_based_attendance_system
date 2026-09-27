// features/session/service.ts
// Professor-facing service: open/close sessions, live feed, session codes.
//
// Everything here hits the real backend (features/session/router.py) by
// default, and the endpoint mocks only when PUBLIC_MOCK_MODE=true. Course
// display names join client-side from the professor courses store, because
// session rows carry only offering_id.
//
// Not owned here: excuse actions. There are no excuse endpoints on the
// backend yet, so excuseStudent / editStudentExcuse / revokeStudentExcuse /
// excuseAllAbsent stay as documented stubs that throw — the live view hides
// those buttons until the excuse slice lands.

import { get, post } from '$lib/api/client';
import type { Paginated } from '$lib/api/endpoints';
import type {
	LiveSession,
	LiveStudent,
	OpenedSession,
	SessionActiveResponse,
	SessionCloseResponse,
	SessionHistoryItemResponse,
	SessionListItemResponse,
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

const ensureCourses = async (): Promise<void> => {
	if (coursesReady) return;
	coursesReady = true;
	if (professorState.courses.length === 0 && !professorState.coursesError) {
		await initProfessorCourses();
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
// Recent/live sessions, optionally filtered by date range or offering.
// Course display names join client-side; sorting stays on the page.
export const listSessions = async (params?: {
	from?: string;
	to?: string;
	offeringId?: number;
	page?: number;
	size?: number;
}) => {
	await ensureCourses();

	const query: Record<string, string> = {};
	if (params?.from) query.from = params.from;
	if (params?.to) query.to = params.to;
	if (params?.offeringId !== undefined) query.offering_id = String(params.offeringId);
	query.page = String(params?.page ?? 1);
	query.size = String(params?.size ?? 50);

	const response = await get<Paginated<SessionListItemResponse>>('sessionList', query);

	const items: SessionSummary[] = (response.items ?? []).map((item) => ({
		id: item.id,
		offeringId: item.offering_id,
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
		status: item.status,
	}));

	return { items, total: response.total, page: response.page, size: response.size };
};

// openSession
// Create a new attendance session against a course offering. qrPayload is what
// gets rendered into the QR code students scan. Omitted window/classroom
// fields fall back server-side to the offering defaults, then the app
// defaults — but the form always sends explicit values so the projector
// preview never disagrees with what was stored.
export const openSession = async (
	offeringId: number,
	options?: {
		durationMinutes?: number;
		presentWindowMinutes?: number;
		lateWindowMinutes?: number;
		geofenceRadius?: number;
		// D17: a classroom override replaces the offering defaults when set.
		classroomName?: string;
		classroomLat?: number;
		classroomLng?: number;
	}
): Promise<OpenedSession> => {
	const body: Record<string, number | string> = { offering_id: offeringId };
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

	const response = await post<SessionReadResponse>('sessionCreate', body);

	return {
		id: response.id,
		offeringId: response.offering_id,
		sessionCode: response.session_code,
		qrPayload: response.qr_payload,
		expiresAt: response.expires_at,
		scheduledEndTime: response.scheduled_end_time,
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

// excuseStudent
// Professor quick-excuse for an absent or late student. No excuse endpoint
// exists on the backend yet, so this stays a stub that throws — the live
// view hides excuse actions until the excuse slice lands.
export const excuseStudent = async (
	_sessionId: number,
	_studentNumber: string,
	_input: { reason: string; notes?: string }
): Promise<never> => {
	throw new Error('Excuse actions are unavailable until excuse endpoints land.');
};

// editStudentExcuse
// Same stub status as excuseStudent (see above).
export const editStudentExcuse = async (
	_sessionId: number,
	_studentNumber: string,
	_input: { reason?: string; notes?: string }
): Promise<never> => {
	throw new Error('Excuse actions are unavailable until excuse endpoints land.');
};

// revokeStudentExcuse
// Same stub status as excuseStudent (see above).
export const revokeStudentExcuse = async (
	_sessionId: number,
	_studentNumber: string
): Promise<never> => {
	throw new Error('Excuse actions are unavailable until excuse endpoints land.');
};

// excuseAllAbsent
// Same stub status as excuseStudent (see above).
export const excuseAllAbsent = async (
	_sessionId: number,
	_input: { reason: string; notes?: string }
): Promise<never> => {
	throw new Error('Excuse actions are unavailable until excuse endpoints land.');
};

// getActiveSession
// Fetch one session's live feed in the professor contract shape. The old mock
// carried a per-student `gps` verdict and internal excuse notes; the contract
// exposes neither, so both are gone — `excuse_reason` is the only per-student
// excuse text. A backend 404 (wrong id, or another professor's session)
// rejects, and the page renders its not-found state from that.
export const getActiveSession = async (sessionId: number): Promise<LiveSession> => {
	await ensureCourses();
	const response = await get<SessionActiveResponse>('sessionActive', undefined, `/active/${sessionId}`);

	const students: LiveStudent[] = (response.students ?? []).map((student) => ({
		studentNumber: student.student_number,
		name: student.name,
		section: student.section,
		status: student.status,
		scannedAt: student.scanned_at,
		excuseReason: student.excuse_reason,
	}));

	return {
		id: response.id,
		offeringId: response.offering,
		offeringCode: courseCodeFor(response.offering),
		offeringName: courseNameFor(response.offering),
		offeringSections: sectionsFor(response.offering),
		sessionCode: response.session_code,
		scanWindowRemaining: response.scan_window_remaining,
		scheduledEndTime: response.scheduled_end_time,
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
			avg_compliance:
				items.length === 0
					? 0
					: items.reduce((total, row) => total + row.compliance_rate, 0) / items.length,
			total_sessions: response.total,
		};
	}

	// Course-filtered path: fan out per offering, merge, sort, slice.
	const merged: SessionHistoryRow[] = [];
	for (const offeringId of offeringIds) {
		if (offeringId === undefined) continue;
		const query: Record<string, string> = {
			offering_id: String(offeringId),
			sort_by: 'date',
			sort_dir: 'desc',
			page: '1',
			size: '100',
		};
		if (params?.section !== undefined) query.section = params.section;
		if (params?.from) query.date_from = params.from;
		if (params?.to) query.date_to = params.to;
		const response = await get<Paginated<SessionHistoryItemResponse>>('sessionHistory', query);
		for (const item of response.items ?? []) merged.push(toRow(item));
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
		avg_compliance:
			merged.length === 0
				? 0
				: merged.reduce((total, row) => total + row.compliance_rate, 0) / merged.length,
		total_sessions: merged.length,
	};
};
