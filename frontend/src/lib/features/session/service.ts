// features/session/service.ts
// Professor-facing service: open/close sessions, live feed, session codes

// MOCK flag — swap to false when professor session endpoints land
const MOCK = true;

// Mock stand-in for the server-side HMAC code (D12). The shape is two base36
// chars, a dash, then four more — `XX-XXXX`.
export const mockSessionCode = (): string =>
	`${Math.random().toString(36).substring(2, 4).toUpperCase()}-${Math.random()
		.toString(36)
		.substring(2, 6)
		.toUpperCase()}`;

// A frozen sample in the exact shape mockSessionCode() returns. The create page
// imports this for its inert placeholder so the two cannot drift apart — they
// did once, and the wider placeholder silently overflowed its card on mobile.
export const SESSION_CODE_SAMPLE = '7X-9K2M';

// Mock data
// One pre-seeded active session so the professor UI has something to render.
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

// listSessions
// Paginated list of sessions, optionally filtered by date range/course.
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

// openSession
// Create a new attendance session against a course offering. qrPayload is what
// gets rendered into the QR code students scan.
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
		// D12: the scheduled class end, which caps the computed expiry. ISO 8601.
		scheduledEndTime?: string;
	}
) => {
	const durationMinutes = options?.durationMinutes ?? 90;
	const presentWindowMinutes = options?.presentWindowMinutes ?? 15;
	const lateWindowMinutes = options?.lateWindowMinutes ?? 5;
	const geofenceRadius = options?.geofenceRadius ?? 50;

	// D12: expires_at = min(created_at + duration_minutes, scheduled_end_time),
	// so a session can never outlive the scheduled class.
	const durationEnd = Date.now() + durationMinutes * 60 * 1000;
	const scheduledEnd = options?.scheduledEndTime
		? new Date(options.scheduledEndTime).getTime()
		: Number.POSITIVE_INFINITY;

	// The real code is HMAC-derived server-side; in mock mode it is a random
	// stand-in so the projector card has something to render.
	const code = MOCK ? mockSessionCode() : '';

	return {
		id: MOCK_SESSIONS.length + 1,
		offeringId,
		code: `SESSION-${Date.now().toString(36)}`,
		qrPayload: {
			v: 1,
			code,
			course: offeringId,
			radius: geofenceRadius,
			pw: presentWindowMinutes,
			lw: lateWindowMinutes,
		},
		classroomName: options?.classroomName,
		classroomLat: options?.classroomLat,
		classroomLng: options?.classroomLng,
		expiresAt: new Date(Math.min(durationEnd, scheduledEnd)).toISOString(),
		scheduledEndTime: options?.scheduledEndTime,
	};
};

// closeSession
// Mark a session closed; students can no longer scan against it.
export const closeSession = async (sessionId: number) => {
	if (MOCK) {
		return { id: sessionId, status: 'closed' as const };
	}
	return { id: sessionId, status: 'closed' as const };
};

// getActiveSession
// Fetch one session's live feed: enrolled students with scan status and the
// running present/late/absent/excused/pending counts.
export const getActiveSession = async (sessionId: number) => {
	if (MOCK) {
		return {
			id: sessionId,
			courseId: 1,
			code: 'SESSION-2024-001',
			qrPayload: {
				v: 1,
			code: SESSION_CODE_SAMPLE,
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
