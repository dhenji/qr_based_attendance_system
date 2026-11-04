// features/attendance/service.ts
// Professor attendance ledger (read-only).
//
// listRecords hits the real backend (GET /professor/attendance). The contract
// row carries no course identity, session code, or timestamps beyond
// scanned_at, so those join client-side: session_id -> session detail via
// listSessions, then offering_id -> course via the courses store. The session
// directory warms per filter scope (same date/type/offering window, up to 500
// sessions); rows outside it set sessionKnown=false and render em dashes
// rather than invented values, with missingCount/directoryIncomplete so the
// page can warn instead of silently showing scanned times as session dates.
//
// Two wire vocabularies are normalized here: scanned_via arrives as
// qr_camera/manual_code (mapped to qr/manual for display), and
// face_match_score is a 0-1 fraction (scaled to the percent display the page
// renders). Read-only: no excuse/mark-present mutations here (D25) — those
// live on the active-session page.

import { get } from '$lib/api/client';
import type { Paginated } from '$lib/api/endpoints';
import type { CourseType, ProfessorAttendanceItemResponse, ProfessorAttendanceLedgerResponse } from '$lib/shared/types';
import { listSessions } from '$lib/features/session/service';
import {
	initProfessorCourses,
	professorState,
} from '$lib/features/professor/store.svelte';

export type ProfessorAttendanceStatus =
	| 'present'
	| 'late'
	| 'absent'
	| 'excused'
	| 'pending'
	| 'rejected';

export type ProfessorAttendanceRow = {
	id: number;
	session_id: number;
	session_type: CourseType;
	session_code: string;
	created_at: string;
	expires_at: string;
	offering_id: number;
	course_code: string;
	course_name: string;
	section: string;
	student_number: string;
	student_name: string;
	status: ProfessorAttendanceStatus;
	original_status?: Exclude<ProfessorAttendanceStatus, 'excused'>;
	scanned_at?: string;
	scanned_via?: string;
	face_match_score?: number;
	excuse_reason?: string;
	// True when session_id resolved via the directory; false means the
	// session fell outside the warmed window — session_code/course fall back
	// to placeholders and created_at falls back to scanned_at.
	sessionKnown: boolean;
};

export type AttendanceLedgerSortBy = 'date' | 'student' | 'section' | 'status' | 'time';
export type AttendanceLedgerSortDir = 'asc' | 'desc';

export type AttendanceLedgerFilters = {
	offeringId?: number;
	programId?: number;
	yearLevelId?: number;
	academicYear?: string;
	semester?: string;
	course?: string;
	section?: string;
	sessionId?: number;
	sessionType?: CourseType;
	status?: ProfessorAttendanceStatus;
	search?: string;
	from?: string;
	to?: string;
	sortBy?: AttendanceLedgerSortBy;
	sortDir?: AttendanceLedgerSortDir;
	page?: number;
	size?: number;
};

type SessionDirectory = Map<
	number,
	{
		offeringId: number;
		sessionCode: string;
		createdAt: string;
		expiresAt: string;
	}
>;

// Session + course directory, warmed per filter scope. listSessions joins
// course names itself, so one cached scope covers both lookups. The directory
// pages up to DIRECTORY_MAX_PAGES so a full term fits; scopes beyond that
// surface as directoryIncomplete rather than invented values.
const DIRECTORY_PAGE_SIZE = 100;
const DIRECTORY_MAX_PAGES = 5;

type DirectoryScope = {
	from?: string;
	to?: string;
	offeringId?: number;
	sessionType?: CourseType;
};

let directoryReady = false;
let directoryScopeKey = '';
let sessionDirectory: SessionDirectory = new Map();

export const invalidateAttendanceDirectory = (): void => {
	directoryReady = false;
	directoryScopeKey = '';
	sessionDirectory = new Map();
};

const scopeKey = (scope: DirectoryScope): string =>
	[scope.from ?? '', scope.to ?? '', scope.offeringId ?? '', scope.sessionType ?? ''].join('|');

const ensureCoursesWarmed = async (): Promise<void> => {
	if (professorState.courses.length === 0 && !professorState.coursesError) {
		await initProfessorCourses();
	}
};

const ensureDirectory = async (scope: DirectoryScope): Promise<void> => {
	const key = scopeKey(scope);
	if (directoryReady && key === directoryScopeKey) return;
	directoryScopeKey = key;
	directoryReady = true;
	await ensureCoursesWarmed();
	try {
		const dir: SessionDirectory = new Map();
		for (let page = 1; page <= DIRECTORY_MAX_PAGES; page += 1) {
			const { items } = await listSessions({
				from: scope.from,
				to: scope.to,
				offeringId: scope.offeringId,
				sessionType: scope.sessionType,
				page,
				size: DIRECTORY_PAGE_SIZE
			});
			for (const session of items) {
				dir.set(session.id, {
					offeringId: session.offeringId,
					sessionCode: session.sessionCode,
					createdAt: session.createdAt,
					expiresAt: session.expiresAt ?? session.createdAt
				});
			}
			if (items.length < DIRECTORY_PAGE_SIZE) break;
		}
		sessionDirectory = dir;
	} catch {
		sessionDirectory = new Map();
	}
};

const courseIdentityFor = (offeringId: number): { code: string; name: string; section: string } => {
	const course = professorState.courses.find((item) => item.offeringId === offeringId) ?? null;
	return {
		code: course?.courseCode ?? `Offering ${offeringId}`,
		name: course?.courseName ?? '',
		section: course && course.sections.length > 0 ? course.sections.join(', ') : '—',
	};
};

const viaForDisplay = (scannedVia: string | null): string | undefined => {
	if (scannedVia === 'qr_camera') return 'qr';
	if (scannedVia === 'manual_code') return 'manual';
	return scannedVia ?? undefined;
};

// listRecords
// Fetch attendance records, optionally filtered by session/status/date range
// (professor-facing view). Returns a paginated response shape.
// Contract: GET /professor/attendance with
// ?course_id&offering_id&section&session_id&status&date_from&date_to&
// sort_by=date|student|section|status|time&sort_dir&page&size
//
// The backend filters by course_id, not course code: the page's course filter
// resolves code -> course_id here. A code can exist in two programs — when it
// is ambiguous no course_id is sent and the page filters the joined rows
// client-side instead of guessing the wrong course.
// Counts and the distinct-session total cover the returned page only (the
// envelope carries no aggregates); `total` stays the server global.
export const listRecords = async (params?: AttendanceLedgerFilters) => {
	await ensureCoursesWarmed();

	// Resolve the directory scope before warming: same date/type window as
	// the ledger query, narrowed to the offering when the course filter maps
	// to exactly one. Ambiguous codes warm unfiltered so no offering is missed.
	let scopeOfferingId = params?.offeringId;
	if (scopeOfferingId === undefined && params?.course !== undefined) {
		const matches = professorState.courses.filter(
			(course) => course.courseCode === params.course
		);
		if (matches.length === 1 && matches[0].courseId !== undefined) {
			scopeOfferingId = matches[0].offeringId;
		}
	}
	// A single-session view only needs that session; the directory still
	// warms the surrounding scope so course identity resolves.
	await ensureDirectory({
		from: params?.from,
		to: params?.to,
		offeringId: scopeOfferingId,
		sessionType: params?.sessionType
	});

	const query: Record<string, string> = {
		sort_by: params?.sortBy ?? 'date',
		sort_dir: params?.sortDir ?? 'desc',
		page: String(params?.page ?? 1),
		size: String(params?.size ?? 20),
	};
	if (params?.offeringId !== undefined) query.offering_id = String(params.offeringId);
	if (params?.course !== undefined) {
		const matches = professorState.courses.filter(
			(course) => course.courseCode === params.course
		);
		// Exactly one owner: safe to push down. Ambiguous or unknown: leave
		// the server unfiltered so the joined code filter below decides.
		if (matches.length === 1 && matches[0].courseId !== undefined) {
			query.course_id = String(matches[0].courseId);
		}
	}
	if (params?.programId !== undefined) query.program_id = String(params.programId);
	if (params?.yearLevelId !== undefined) query.year_level_id = String(params.yearLevelId);
	if (params?.academicYear !== undefined) query.academic_year = params.academicYear;
	if (params?.semester !== undefined) query.semester = params.semester;
	if (params?.section !== undefined) query.section = params.section;
	if (params?.sessionId !== undefined) query.session_id = String(params.sessionId);
	if (params?.search !== undefined) query.search = params.search;
	if (params?.sessionType) query.session_type = params.sessionType;
	if (params?.status !== undefined) query.status = params.status;
	if (params?.from) query.date_from = params.from;
	if (params?.to) query.date_to = params.to;

	const response = await get<ProfessorAttendanceLedgerResponse>(
		'attendanceList',
		query
	);

	const items: ProfessorAttendanceRow[] = (response.items ?? []).map((item) => {
		const session = sessionDirectory.get(item.session_id);
		const identity = session
			? courseIdentityFor(session.offeringId)
			: { code: '—', name: '', section: item.section ?? '—' };
		// created_at/expires_at fall back to scanned_at only for display/sort;
		// a row whose session is outside the warmed window has no true
		// session clock, so callers must check sessionKnown before trusting
		// the date/code (the page warns and the export flags these rows).
		// excuse_reason has no contract field — always undefined by design.
		return {
			id: item.id,
			session_id: item.session_id,
			session_type: item.session_type ?? 'lecture',
			session_code: session?.sessionCode ?? '—',
			created_at: session?.createdAt ?? item.scanned_at,
			expires_at: session?.expiresAt ?? item.scanned_at,
			offering_id: session?.offeringId ?? 0,
			course_code: identity.code,
			course_name: identity.name,
			section: item.section ?? identity.section,
			student_number: item.student_number,
			student_name: item.student_name,
			status: item.status,
			original_status: (item.original_status ?? undefined) as
				| Exclude<ProfessorAttendanceStatus, 'excused'>
				| undefined,
			scanned_at: item.scanned_at ?? undefined,
			scanned_via: viaForDisplay(item.scanned_via),
			face_match_score:
				item.face_match_score === null || item.face_match_score === undefined
					? undefined
					: item.face_match_score <= 1
						? item.face_match_score * 100
						: item.face_match_score,
			excuse_reason: undefined,
			sessionKnown: session !== undefined
		};
	});

	// Prefer server-side aggregates when present; fall back to page counts.
	const counts = response.counts
		? {
				present: response.counts.present ?? 0,
				late: response.counts.late ?? 0,
				absent: response.counts.absent ?? 0,
				excused: response.counts.excused ?? 0,
				pending: response.counts.pending ?? 0,
				rejected: response.counts.rejected ?? 0
		  }
		: { present: 0, late: 0, absent: 0, excused: 0, pending: 0, rejected: 0 };
	const sessionIds = new Set<number>();
	let missingCount = 0;
	if (!response.counts) {
		for (const item of items) {
			counts[item.status] += 1;
			sessionIds.add(item.session_id);
			if (!item.sessionKnown) missingCount += 1;
		}
	} else {
		for (const item of items) {
			if (!item.sessionKnown) missingCount += 1;
		}
	}

	return {
		items,
		total: response.total,
		page: response.page,
		size: response.size,
		total_sessions: response.total_sessions ?? sessionIds.size,
		total_students: response.total_students ?? 0,
		counts,
		missingCount,
		directoryIncomplete: missingCount > 0
	};
};
