// features/student/service.ts
// Student-facing service: profile, schedule, history, scan.
//
// Profile and dashboard hit their endpoint defs (backend routes pending —
// the store falls back on 404). Schedule stays empty (GET /student/schedule
// has no backend yet). History is live on GET /student/attendance/history.
// Scan delegates to features/liveness/service.ts in real mode.

import { get, isMockMode } from '$lib/api/client';
import type {
	StudentHistoryResponse,
	StudentHistoryStatus,
} from '$lib/api/endpoints';

export type { StudentHistoryStatus };
import type {
	Course,
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

// Schedule — no backend yet (GET /student/schedule unimplemented).
// Empty rather than invented rows.
export const getSchedule = async (): Promise<Course[]> => {
	return [];
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
