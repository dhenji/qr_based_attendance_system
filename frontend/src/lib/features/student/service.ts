// features/student/service.ts
// Student-facing service: profile, schedule, history, scan

import type { Student, Course } from '$lib/shared/types';
import { isWithinGeofence } from '$lib/shared/utils/geo';

// MOCK flag — swap to false when backend student endpoints land
const MOCK = true;

// Mock data
// Hard-coded, face-enrolled student so the dashboard renders immediately.
const MOCK_STUDENT: Student = {
	id: 'student-1',
	userId: 'user-1',
	studentNumber: 'STU-001',
	firstName: 'John',
	middleName: 'Michael',
	lastName: 'Doe',
	programCode: 'BSIT',
	yearLevelLabel: '3rd',
	section: 'A',
	faceEnrolled: true,
	isActive: true,
};

// Profile
// Fetch the current user's student profile.
export const getProfile = async (): Promise<Student> => {
	if (MOCK) return MOCK_STUDENT;
	return MOCK_STUDENT;
};

// Partial profile updates (merged over the existing record).
export const updateProfile = async (updates: Partial<Student>): Promise<Student> => {
	if (MOCK) {
		return { ...MOCK_STUDENT, ...updates };
	}
	return { ...MOCK_STUDENT, ...updates };
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
	return { items: [], total: 0, page: 1, size: 20 };
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
	if (MOCK) {
		const statuses = ['present', 'late', 'rejected'] as const;
		return {
			attendance_id: Math.floor(Math.random() * 10000) + 1,
			status: statuses[Math.floor(Math.random() * statuses.length)],
			scanned_at: scanData.scannedAt,
			expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
		};
	}
	return {
		attendance_id: Math.floor(Math.random() * 10000) + 1,
		status: 'present' as const,
		scanned_at: scanData.scannedAt,
		expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
	};
};

export { isWithinGeofence };
