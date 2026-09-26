// features/student/service.ts
// Student-facing service: profile, schedule, history, scan.
//
// Profile and dashboard are wired to the real API. Schedule and history still
// return empty results because their endpoints land in Phase 4/5 — they are
// left empty rather than filled with invented rows.

import { get, isMockMode } from '$lib/api/client';
import type {
	Course,
	Student,
	StudentDashboardResponse,
	StudentProfileResponse,
} from '$lib/shared/types';
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

// Schedule — no subjects enrolled yet (empty state)
export const getSchedule = async (): Promise<Course[]> => {
	return [];
};

// Session history — no attendance records yet (empty state)
export const getSessionHistory = async (_params?: {
	programId?: number;
	yearLevelId?: number;
	status?: string;
}) => {
	return { items: [] as unknown[], total: 0, page: 1, size: 20 };
};

export const getDashboard = async (): Promise<StudentDashboardResponse> => {
	return get<StudentDashboardResponse>('studentDashboard');
};

// Attendance scan
// Submit a full scan (QR + GPS + liveness). Mock mode randomizes the outcome
// so every UI branch (present/late/rejected) can be exercised.
export const submitScan = async (scanData: {
	sessionId: number;
	qrStudentNumber: string;
	gps: { lat: number; lng: number; accuracy: number };
	livenessEvidence: {
		blinkDetected: boolean;
		headTurnLeft: boolean;
		headTurnRight: boolean;
		earSamples: number[];
		pnpEvidence: object;
	};
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

	// The live scan path lives in features/liveness/service.ts, which already
	// talks to POST /student/attendance/scan. This stays the mock-shaped
	// fallback for the dashboard store until the two are unified.
	return {
		attendance_id: Math.floor(Math.random() * 10000) + 1,
		status: 'present' as const,
		scanned_at: scanData.scannedAt,
		expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
	};
};

export { isWithinGeofence };
