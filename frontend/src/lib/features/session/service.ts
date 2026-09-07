// features/session/service.ts
// Professor-facing service: open/close sessions, live feed, session codes

// MOCK flag
const MOCK = true;

// Mock sessions
const MOCK_SESSIONS = [
	{
		id: 1,
		courseId: 1,
		code: 'SESSION-2024-001',
		qrPayload: {
			v: 1,
			code: 'A7X-9K2M',
			course: 1,
			radius: 50,
			pw: 15,
			lw: 5,
		},
		expiresAt: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
		scheduledEndTime: new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString(),
		createdAt: new Date().toISOString(),
		presentCount: 0,
		lateCount: 0,
		absentCount: 25,
		status: 'active' as const,
		students: [],
	},
];

// List sessions
export const listSessions = async (_params?: {
	from?: string;
	to?: string;
	courseId?: number;
}) => {
	if (MOCK) {
		return {
			items: MOCK_SESSIONS,
			total: MOCK_SESSIONS.length,
			page: 1,
			size: 20,
		};
	}
	return { items: [], total: 0, page: 1, size: 20 };
};

// Open new session
export const openSession = async (
	courseId: number,
	options?: {
		durationMinutes?: number;
		presentWindowMinutes?: number;
		lateWindowMinutes?: number;
		geofenceRadius?: number;
		classroomName?: string;
	}
) => {
	if (MOCK) {
		return {
			id: MOCK_SESSIONS.length + 1,
			courseId,
			code: `SESSION-${Date.now().toString(36)}`,
			qrPayload: {
				v: 1,
				code: `A${Math.random().toString(36).substring(2, 4).toUpperCase()}-${Math.random()
					.toString(36)
					.substring(2, 4).toUpperCase()}`,
				course: courseId,
				radius: options?.geofenceRadius || 50,
				pw: options?.presentWindowMinutes || 15,
				lw: options?.lateWindowMinutes || 5,
			},
			expiresAt: new Date(
				Date.now() + (options?.durationMinutes || 90) * 60 * 1000
			).toISOString(),
			scheduledEndTime: new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString(),
		};
	}
	return {
		id: MOCK_SESSIONS.length + 1,
		courseId,
		code: `SESSION-${Date.now().toString(36)}`,
		qrPayload: {
			v: 1,
			code: 'A7X-9K2M',
			course: courseId,
			radius: options?.geofenceRadius || 50,
			pw: options?.presentWindowMinutes || 15,
			lw: options?.lateWindowMinutes || 5,
		},
		expiresAt: new Date(
			Date.now() + (options?.durationMinutes || 90) * 60 * 1000
		).toISOString(),
		scheduledEndTime: new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString(),
	};
};

// Close session
export const closeSession = async (sessionId: number) => {
	if (MOCK) {
		return { id: sessionId, status: 'closed' as const };
	}
	return { id: sessionId, status: 'closed' as const };
};

// Get active session detail
export const getActiveSession = async (sessionId: number) => {
	if (MOCK) {
		return {
			id: sessionId,
			courseId: 1,
			code: 'SESSION-2024-001',
			qrPayload: {
				v: 1,
				code: 'A7X-9K2M',
				course: 1,
				radius: 50,
				pw: 15,
				lw: 5,
			},
			expiresAt: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
			scheduledEndTime: new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString(),
			status: 'active' as const,
			students: [
				{
					studentId: 'student-1',
					name: 'John Doe',
					section: 'A',
					status: 'present' as const,
					scannedAt: new Date().toISOString(),
				},
			],
			counts: {
				present: 20,
				late: 3,
				absent: 2,
				excused: 0,
				pending: 0,
			},
		};
	}
	return null;
};
