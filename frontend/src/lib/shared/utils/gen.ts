// shared/utils/gen.ts
// Fake data generation for mocks/fixtures

import type { Student, Session, AttendanceRecord } from '$lib/shared/types';

// Minimal fake-name generator (no external dep)
const fake = {
	firstName: () => ['John', 'Maria', 'James', 'Anna', 'Carlos'][Math.floor(Math.random() * 5)],
	middleName: () => ['Michael', 'Marie', 'Lee', 'Rose', 'Anthony'][Math.floor(Math.random() * 5)],
	lastName: () => ['Doe', 'Smith', 'Garcia', 'Brown', 'Davis'][Math.floor(Math.random() * 5)],
	word: (len: number) => Math.random().toString(36).substring(2, 2 + len),
	sentence: () => 'Sample reason for absence',
};

// Fake-data helpers
// Generate realistic-looking entities for mocks/fixtures. Each generator
// accepts overrides that are spread last, so callers can force specific values.
export const generateStudent = (overrides?: Partial<Student>): Student => ({
	id: Math.random().toString(36).substring(2, 9),
	userId: Math.random().toString(36).substring(2, 9),
	studentNumber: `STU-${Math.random().toString(36).substring(2, 6).toUpperCase()}`,
	firstName: fake.firstName(),
	middleName: fake.middleName(),
	lastName: fake.lastName(),
	programCode: fake.word(3).toUpperCase(),
	yearLevelLabel: `${Math.floor(Math.random() * 4) + 1}rd`,
	section: `${String.fromCharCode(65 + Math.floor(Math.random() * 4))}A`,
	faceEnrolled: Math.random() > 0.5,
	isActive: true,
	...overrides,
});

export const generateSession = (overrides?: Partial<Session>): Session => ({
	id: Math.floor(Math.random() * 1000) + 1,
	courseId: Math.floor(Math.random() * 50) + 1,
	code: `A${Math.random().toString(36).substring(2, 4).toUpperCase()}-${Math.random()
		.toString(36)
		.substring(2, 4).toUpperCase()}`,
	qrPayload: {
		v: 1,
		code: `${Math.random().toString(36).substring(2, 4).toUpperCase()}-${Math.random()
			.toString(36)
			.substring(2, 4).toUpperCase()}`,
		course: 1,
		radius: 50,
		pw: 15,
		lw: 5,
	},
	expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
	scheduledEndTime: new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString(),
	createdAt: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
	presentCount: Math.floor(Math.random() * 50),
	lateCount: Math.floor(Math.random() * 10),
	absentCount: Math.floor(Math.random() * 10),
	status: 'active',
	students: [],
	...overrides,
});

export const generateAttendanceRecord = (overrides?: Partial<AttendanceRecord>): AttendanceRecord => {
	const statuses: AttendanceRecord['status'][] = ['present', 'late', 'rejected'];
	const via: AttendanceRecord['scannedVia'][] = ['qr', 'gps', 'face'];
	return {
		id: Math.floor(Math.random() * 10000) + 1,
		sessionId: Math.floor(Math.random() * 50) + 1,
		studentId: Math.random().toString(36).substring(2, 9),
		studentNumber: `STU-${Math.random().toString(36).substring(2, 6).toUpperCase()}`,
		status: statuses[Math.floor(Math.random() * statuses.length)],
		scannedAt: new Date(Date.now() - Math.random() * 2 * 60 * 60 * 1000).toISOString(),
		scannedVia: via[Math.floor(Math.random() * via.length)],
		faceMatchScore: Math.random() * 100,
		gps: {
			lat: 13.7563 + (Math.random() - 0.5) * 0.01,
			lng: 100.5018 + (Math.random() - 0.5) * 0.01,
			accuracy: 5 + Math.random() * 5,
		},
		excuseReason: Math.random() > 0.7 ? fake.sentence() : undefined,
		...overrides,
	};
};
