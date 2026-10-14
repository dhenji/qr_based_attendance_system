// features/attendance/service.ts
// Professor attendance ledger (read-only).
//
// listRecords hits the real backend (GET /professor/attendance). The contract
// row carries no course identity, session code, or timestamps beyond
// scanned_at, so those join client-side: session_id -> session detail via
// listSessions, then offering_id -> course via the courses store. Rows whose
// session falls outside the directory (older than the cached page) render
// em dashes rather than invented values.
//
// Two wire vocabularies are normalized here: scanned_via arrives as
// qr_camera/manual_code (mapped to qr/manual for display), and
// face_match_score is a 0-1 fraction (scaled to the percent display the page
// renders). Read-only: no excuse/mark-present mutations here (D25) — those
// live on the active-session page.

import { get } from '$lib/api/client';
import type { Paginated } from '$lib/api/endpoints';
import type { ProfessorAttendanceItemResponse } from '$lib/shared/types';
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
};

export type AttendanceLedgerSortBy = 'date' | 'student' | 'section' | 'status' | 'time';
export type AttendanceLedgerSortDir = 'asc' | 'desc';

export type AttendanceLedgerFilters = {
	offeringId?: number;
	course?: string;
	section?: string;
	sessionId?: number;
	status?: ProfessorAttendanceStatus;
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

// Session + course directory, warmed once per page load. listSessions joins
// course names itself, so one cached page covers both lookups.
let directoryReady = false;
let sessionDirectory: SessionDirectory = new Map();

export const invalidateAttendanceDirectory = (): void => {
	directoryReady = false;
	sessionDirectory = new Map();
};

const ensureDirectory = async (): Promise<void> => {
	if (directoryReady) return;
	directoryReady = true;
	if (professorState.courses.length === 0 && !professorState.coursesError) {
		await initProfessorCourses();
	}
	try {
		const { items } = await listSessions({ size: 100 });
		sessionDirectory = new Map(
			items.map((session) => [
				session.id,
				{
					offeringId: session.offeringId,
					sessionCode: session.sessionCode,
					createdAt: session.createdAt,
					expiresAt: session.expiresAt ?? session.createdAt,
				},
			])
		);
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
	await ensureDirectory();

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
	if (params?.section !== undefined) query.section = params.section;
	if (params?.sessionId !== undefined) query.session_id = String(params.sessionId);
	if (params?.status !== undefined) query.status = params.status;
	if (params?.from) query.date_from = params.from;
	if (params?.to) query.date_to = params.to;

	const response = await get<Paginated<ProfessorAttendanceItemResponse>>(
		'attendanceList',
		query
	);

	const items: ProfessorAttendanceRow[] = (response.items ?? []).map((item) => {
		const session = sessionDirectory.get(item.session_id);
		const identity = session
			? courseIdentityFor(session.offeringId)
			: { code: '—', name: '', section: item.section ?? '—' };
		// created_at/expires_at fall back to scanned_at only for display/sort;
		// a row whose session is outside the recent directory has no true
		// session clock, so callers must treat these as scanned times.
		// excuse_reason has no contract field — always undefined by design.
		return {
			id: item.id,
			session_id: item.session_id,
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
		};
	});

	// Page counts only — the envelope carries total/page/size but no
	// aggregates, so summaryText must label these as page counts.
	const counts = { present: 0, late: 0, absent: 0, excused: 0, pending: 0, rejected: 0 };
	const sessionIds = new Set<number>();
	for (const item of items) {
		counts[item.status] += 1;
		sessionIds.add(item.session_id);
	}

	return {
		items,
		total: response.total,
		page: response.page,
		size: response.size,
		total_sessions: sessionIds.size,
		counts,
	};
};
