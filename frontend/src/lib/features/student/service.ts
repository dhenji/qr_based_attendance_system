// features/student/service.ts
// Student-facing service: profile, schedule, history, scan.
//
// Profile and dashboard hit their endpoint defs (the store falls back on
// 404). Schedule is live on GET /student/schedule. History is live on
// GET /student/attendance/history. Scan delegates to
// features/liveness/service.ts in real mode.

import { get, isMockMode, post } from '$lib/api/client';
import type {
	Paginated,
	StudentExcuseItemResponse,
	StudentExcuseSubmitResponse,
	StudentHistoryResponse,
	StudentHistoryStatus,
} from '$lib/api/endpoints';

export type { StudentHistoryStatus };
import type {
	ScheduleItemResponse,
	ScheduleResponse,
	ScheduledClass,
	Student,
	StudentDashboardResponse,
	StudentProfileResponse,
} from '$lib/shared/types';
import type { LivenessEvidence } from '$lib/shared/types';
import { submitAttendanceScan } from '$lib/features/liveness/service';
import { isWithinGeofence } from '$lib/shared/utils/geo';

// Profile view-model assembled from GET /student/profile.
//
// The endpoint is read-only by design (D32): name, program, year level and
// section are all roster-owned, and the UI presents them as disabled fields.
const toStudent = (p: StudentProfileResponse): Student => ({
	id: p.student_number,
	userId: '',
	studentNumber: p.student_number,
	email: p.email,
	firstName: p.first_name,
	middleName: p.middle_name ?? undefined,
	lastName: p.last_name,
	programCode: p.program_code,
	yearLevelLabel: p.year_level_label,
	section: p.section ?? undefined,
	faceEnrolled: p.face_enrolled,
	faceEnrolledAt: p.face_enrolled_at ?? undefined,
	faceEmbeddingVersion: p.face_embedding_version,
	createdAt: p.created_at,
	scanCount: p.scan_count,
	isActive: p.is_active,
});

export const getProfile = async (): Promise<Student | null> => {
	const response = await get<StudentProfileResponse>('studentProfile');
	return toStudent(response);
};

// Partial profile updates (merged over the existing record).
// Read-only per D32 and unimplemented server-side; the profile page renders its
// fields disabled rather than offering edits that would be rejected.
export const updateProfile = async (_updates: Partial<Student>): Promise<Student | null> => {
	return null;
};

// Schedule — live on GET /student/schedule (no params; identity from the
// Bearer token). One row per active enrollment ordered by offering_id;
// empty enrollments return { offerings: [] }. Real API by default; mocks
// only when PUBLIC_MOCK_MODE=true (see api/client.ts).
const toScheduledClass = (o: ScheduleItemResponse): ScheduledClass => ({
	offeringId: o.offering_id,
	courseId: o.course_id,
	courseCode: o.course_code,
	courseName: o.course_name,
	programCode: o.program_code,
	yearLevelLabel: o.year_level_label,
	semester: o.semester,
	scheduleDays: o.schedule_days,
	scheduleStartTime: o.schedule_start_time,
	scheduleEndTime: o.schedule_end_time,
	classroomName: o.classroom_name ?? undefined,
	professorName: o.professor_name ?? undefined,
});

export const getSchedule = async (): Promise<ScheduledClass[]> => {
	const response = await get<ScheduleResponse>('studentSchedule');
	return (response.offerings ?? []).map(toScheduledClass);
};

export type StudentHistoryFilters = {
	programId?: number;
	yearLevelId?: number;
	semester?: string;
	courseId?: number;
	status?: StudentHistoryStatus;
	from?: string;
	to?: string;
	sortBy?: 'date' | 'course' | 'section' | 'status' | 'time';
	sortDir?: 'asc' | 'desc';
	page?: number;
	size?: number;
};

export type StudentHistoryRow = {
	id: number;
	sessionId: number;
	courseCode: string;
	courseName: string;
	status: StudentHistoryStatus;
	originalStatus?: StudentHistoryStatus;
	excuseReason?: string;
	scannedAt: string;
	scannedVia?: 'qr' | 'manual' | string;
};

const viaForDisplay = (scannedVia: string | null | undefined): StudentHistoryRow['scannedVia'] => {
	if (!scannedVia) return undefined;
	if (scannedVia === 'qr_camera') return 'qr';
	if (scannedVia === 'manual_code') return 'manual';
	return scannedVia;
};

// Session history — live on GET /student/attendance/history.
// Contract: ?program_id&year_level_id&semester&course_id&status&date_from&
// date_to&sort_by=date|course|section|status|time&sort_dir&page&size
// -> { items, total, page, size, summary } (summary covers the FULL filter set).
export const getSessionHistory = async (params: StudentHistoryFilters = {}) => {
	const query: Record<string, string> = {
		sort_by: params.sortBy ?? 'date',
		sort_dir: params.sortDir ?? 'desc',
		page: String(params.page ?? 1),
		size: String(params.size ?? 20),
	};
	if (params.programId !== undefined) query.program_id = String(params.programId);
	if (params.yearLevelId !== undefined) query.year_level_id = String(params.yearLevelId);
	if (params.semester) query.semester = params.semester;
	if (params.courseId !== undefined) query.course_id = String(params.courseId);
	if (params.status) query.status = params.status;
	if (params.from) query.date_from = params.from;
	if (params.to) query.date_to = params.to;

	const response = await get<StudentHistoryResponse>('studentHistory', query);

	const items: StudentHistoryRow[] = (response.items ?? []).map((item) => ({
		id: item.id,
		sessionId: item.session_id,
		courseCode: item.course_code,
		courseName: item.course_name,
		status: item.status,
		originalStatus: (item.original_status ?? undefined) as StudentHistoryRow['originalStatus'],
		excuseReason: item.excuse_reason ?? undefined,
		scannedAt: item.scanned_at,
		scannedVia: viaForDisplay(item.scanned_via),
	}));

	return {
		items,
		total: response.total ?? 0,
		page: response.page ?? 1,
		size: response.size ?? 20,
		summary: response.summary ?? {
			compliance_rate: 0,
			participation_rate: 0,
			counts: { present: 0, late: 0, absent: 0, excused: 0, rejected: 0 },
		},
	};
};

export const getDashboard = async (): Promise<StudentDashboardResponse> => {
	return get<StudentDashboardResponse>('studentDashboard');
};

// Student excuse requests — live on features/excuse/student_router.py.
// Submit creates a pending professor-reviewed request (201); list reads the
// student's own rows newest-first. Reason floor is 20 chars
// (REASON_MIN_LENGTH_STUDENT). Reason-only submits: attachments expect
// presigned-upload URLs (D24), which the UI does not collect yet.
// Real API by default; deterministic mocks only when PUBLIC_MOCK_MODE=true.
export interface StudentExcuseRequest {
	id: number;
	sessionId: number;
	reason: string;
	status: 'pending' | 'approved' | 'rejected';
	requestedAt: string;
	reviewedAt?: string;
	reviewNotes?: string;
}

const toStudentExcuse = (item: StudentExcuseItemResponse): StudentExcuseRequest => ({
	id: item.id,
	sessionId: item.session_id,
	reason: item.reason,
	status: item.status === 'approved' || item.status === 'rejected' ? item.status : 'pending',
	requestedAt: item.requested_at,
	reviewedAt: item.reviewed_at ?? undefined,
	reviewNotes: item.review_notes ?? undefined,
});

export const submitStudentExcuse = async (input: {
	sessionId: number;
	reason: string;
}): Promise<StudentExcuseRequest> => {
	const reason = input.reason.trim();
	if (reason.length < 20) throw new Error('Reason must be at least 20 characters.');
	const response = await post<StudentExcuseSubmitResponse>('studentExcuseSubmit', {
		session_id: input.sessionId,
		reason,
	});
	const now = new Date().toISOString();
	return {
		id: response.id,
		sessionId: input.sessionId,
		reason,
		status: 'pending',
		requestedAt: response.requested_at ?? now,
	};
};

export const listStudentExcuses = async (
	params: { page?: number; size?: number } = {}
): Promise<{ items: StudentExcuseRequest[]; total: number }> => {
	const response = await get<Paginated<StudentExcuseItemResponse>>('studentExcuseList', {
		page: String(params.page ?? 1),
		size: String(params.size ?? 20),
	});
	return {
		items: (response.items ?? []).map(toStudentExcuse),
		total: response.total ?? 0,
	};
};

// Attendance scan
// Mock mode randomizes the outcome so every UI branch (present/late/rejected)
// can be exercised. Real mode delegates to features/liveness/service.ts
// (POST /student/attendance/scan) so there is exactly one live scan path.
export const submitScan = async (scanData: {
	sessionId: number;
	qrStudentNumber: string;
	gps: { lat: number; lng: number; accuracy: number };
	livenessEvidence: LivenessEvidence;
	faceMatchScore: number;
	scannedAt: string;
}) => {
	const statuses = ['present', 'late', 'rejected'] as const;

	if (isMockMode()) {
		return {
			attendance_id: Math.floor(Math.random() * 10000) + 1,
			status: statuses[Math.floor(Math.random() * statuses.length)],
			scanned_at: scanData.scannedAt,
			expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
		};
	}

	const result = await submitAttendanceScan({
		sessionId: scanData.sessionId,
		studentNumber: scanData.qrStudentNumber,
		gps: scanData.gps,
		livenessEvidence: scanData.livenessEvidence,
		faceMatchScore: scanData.faceMatchScore,
		scannedAt: scanData.scannedAt,
	});

	return {
		attendance_id: result.id,
		status: result.status,
		scanned_at: result.scannedAt,
		expires_at: result.expiresAt,
	};
};

export { isWithinGeofence };
