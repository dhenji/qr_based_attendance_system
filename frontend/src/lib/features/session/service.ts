// features/session/service.ts
// Professor-facing service: open/close sessions, live feed, session codes

import { PROFESSOR_COURSES } from '$lib/features/professor/mock';

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

type MockAttendanceStatus = 'present' | 'late' | 'absent' | 'excused' | 'pending';
type MockSessionStatus = 'active' | 'closed';

type MockRosterStudent = {
	studentNumber: string;
	name: string;
	section: string;
	status: MockAttendanceStatus;
	scannedAt?: string;
	excuseReason?: string;
	// The first status replaced by an excuse. Retained for D22 audit/revoke even
	// though the live-detail contract does not expose it.
	originalStatus?: Exclude<MockAttendanceStatus, 'excused'>;
	// MOCK-ONLY: the excuse create/update contracts accept only `reason`.
	// Internal notes are retained for the mock audit trail and must not be sent
	// to a future backend without a contract change.
	excuseNotes?: string;
	excuseRequestId?: number;
	excusedBy?: string;
	excusedAt?: string;
	// MOCK-ONLY: the contract detail DTO has no per-student geofence verdict.
	// It exists so the projector feed can render wireframe 3.3's GPS column and
	// must be removed when the professor session endpoints land.
	gps: 'in' | 'out' | null;
};

type MockExcuseRequest = {
	id: number;
	sessionId: number;
	studentNumber: string;
	initiatedBy: 'professor';
	initiatedVia: 'quick';
	reason: string;
	notes?: string;
	status: 'approved';
	reviewedBy: string;
	reviewedAt: string;
	createdAt: string;
};

type MockSession = {
	id: number;
	offeringId: number;
	courseId: number;
	internalCode: string;
	sessionCode: string;
	qrPayload: {
		v: 1;
		code: string;
		course: number;
		radius: number;
		pw: number;
		lw: number;
	};
	createdAt: string;
	expiresAt: string;
	scheduledEndTime: string;
	status: MockSessionStatus;
	presentWindowMinutes: number;
	lateWindowMinutes: number;
	enrolledCount: number;
	pendingSyncCount: number;
	classroomName?: string;
	classroomLat?: number;
	classroomLng?: number;
	students: MockRosterStudent[];
};

const ROSTER_FIRST_NAMES = [
	'Alice',
	'Ben',
	'Cora',
	'Dan',
	'Ella',
	'Frank',
	'Grace',
	'Henry',
	'Ivy',
	'Jonas',
	'Katrina',
	'Luis'
];
const ROSTER_LAST_NAMES = ['Santos', 'Reyes', 'Cruz', 'Mendoza', 'Torres', 'Garcia'];

const rosterName = (index: number): string =>
	`${ROSTER_FIRST_NAMES[index % ROSTER_FIRST_NAMES.length]} ${ROSTER_LAST_NAMES[Math.floor(index / ROSTER_FIRST_NAMES.length) % ROSTER_LAST_NAMES.length]}`;

const resolveOffering = (offeringId: number) => {
	const course = PROFESSOR_COURSES.find((item) => item.offeringId === offeringId);
	return {
		id: offeringId,
		courseId: course?.courseId ?? offeringId,
		courseCode: course?.courseCode ?? `OFFERING-${offeringId}`,
		courseName: course?.courseName ?? 'Unknown course',
		section: course?.section ?? '—',
		room: course?.classroomName ?? 'Room TBA',
		enrolledCount: course?.enrolledCount ?? 0
	};
};

const buildPendingRoster = (
	offeringId: number,
	count: number,
	section: string
): MockRosterStudent[] =>
	Array.from({ length: count }, (_, index) => ({
		studentNumber: `O${offeringId}-${String(index + 1).padStart(3, '0')}`,
		name: rosterName(index),
		section,
		status: 'pending',
		gps: null
	}));

const createSeedSession = (): MockSession => {
	const offering = resolveOffering(1);
	const createdAt = Date.now() - 20 * 60 * 1000;
	const statuses: MockAttendanceStatus[] = [
		...Array<MockAttendanceStatus>(15).fill('present'),
		...Array<MockAttendanceStatus>(3).fill('late'),
		...Array<MockAttendanceStatus>(2).fill('absent'),
		'excused',
		...Array<MockAttendanceStatus>(9).fill('pending')
	];

	return {
		id: 1,
		offeringId: offering.id,
		courseId: offering.courseId,
		internalCode: 'SESSION-2024-001',
		sessionCode: SESSION_CODE_SAMPLE,
		qrPayload: {
			v: 1,
			code: SESSION_CODE_SAMPLE,
			course: offering.id,
			radius: 50,
			pw: 15,
			lw: 5
		},
		createdAt: new Date(createdAt).toISOString(),
		expiresAt: new Date(createdAt + 60 * 60 * 1000).toISOString(),
		scheduledEndTime: new Date(createdAt + 2 * 60 * 60 * 1000).toISOString(),
		status: 'active',
		presentWindowMinutes: 15,
		lateWindowMinutes: 5,
		enrolledCount: 30,
		pendingSyncCount: 3,
		students: statuses.map((status, index) => ({
			studentNumber: `O1-${String(index + 1).padStart(3, '0')}`,
			name: rosterName(index),
			section: offering.section,
			status,
			scannedAt:
				status === 'present' || status === 'late'
					? new Date(createdAt + (index + 1) * 45 * 1000).toISOString()
					: undefined,
			excuseReason: status === 'excused' ? 'Medical certificate submitted' : undefined,
			originalStatus: status === 'excused' ? 'absent' : undefined,
			excuseRequestId: status === 'excused' ? 1 : undefined,
			excusedBy: status === 'excused' ? 'professor' : undefined,
			excusedAt: status === 'excused' ? new Date().toISOString() : undefined,
			gps: status === 'present' || status === 'late' ? 'in' : null
		}))
	};
};

// Mock data
// The seeded session backs both the legacy session list and the projector view.
// Dashboard fixture id 1 / offering 1 intentionally points here.
const MOCK_SESSIONS: MockSession[] = [createSeedSession()];
const MOCK_EXCUSE_REQUESTS: MockExcuseRequest[] = [];
let nextExcuseRequestId = 1;

const seedExcuseAudit = (): void => {
	const student = MOCK_SESSIONS[0]?.students.find((item) => item.status === 'excused');
	if (!student) return;
	const createdAt = new Date().toISOString();
	MOCK_EXCUSE_REQUESTS.push({
		id: nextExcuseRequestId,
		sessionId: MOCK_SESSIONS[0].id,
		studentNumber: student.studentNumber,
		initiatedBy: 'professor',
		initiatedVia: 'quick',
		reason: student.excuseReason ?? 'Medical certificate submitted',
		status: 'approved',
		reviewedBy: 'professor',
		reviewedAt: createdAt,
		createdAt
	});
	nextExcuseRequestId += 1;
};

seedExcuseAudit();

const countStatuses = (session: MockSession) => {
	const counts = { present: 0, late: 0, pending: 0, absent: 0, excused: 0 };
	for (const student of session.students) counts[student.status] += 1;
	return counts;
};

const QUICK_EXCUSE_MIN_REASON_LENGTH = 10;

const normalizeReason = (reason: string): string => reason.trim();

const assertExcuseReason = (reason: string): string => {
	const normalized = normalizeReason(reason);
	if (normalized.length < QUICK_EXCUSE_MIN_REASON_LENGTH) {
		throw new Error(
			`Excuse reason must be at least ${QUICK_EXCUSE_MIN_REASON_LENGTH} characters.`
		);
	}
	return normalized;
};

const normalizeNotes = (notes?: string): string | undefined => {
	const normalized = notes?.trim();
	return normalized ? normalized : undefined;
};

const findMockSession = (sessionId: number): MockSession => {
	const session = MOCK_SESSIONS.find((item) => item.id === sessionId);
	if (!session) throw new Error(`Session ${sessionId} was not found.`);
	return session;
};

const findMockStudent = (session: MockSession, studentNumber: string): MockRosterStudent => {
	const student = session.students.find((item) => item.studentNumber === studentNumber);
	if (!student) throw new Error(`Student ${studentNumber} was not found in session ${session.id}.`);
	return student;
};

const recordMockExcuse = (
	session: MockSession,
	student: MockRosterStudent,
	reason: string,
	notes: string | undefined
): MockExcuseRequest => {
	const createdAt = new Date().toISOString();
	const request: MockExcuseRequest = {
		id: nextExcuseRequestId,
		sessionId: session.id,
		studentNumber: student.studentNumber,
		initiatedBy: 'professor',
		initiatedVia: 'quick',
		reason,
		notes,
		status: 'approved',
		reviewedBy: 'professor',
		reviewedAt: createdAt,
		createdAt
	};
	nextExcuseRequestId += 1;
	MOCK_EXCUSE_REQUESTS.push(request);
	return request;
};

// D13: students without scans become absent when scanning can no longer
// succeed. Apply that transition in the mock when a session expires naturally
// or is formally closed. Delete with the mock.
const expirePendingScans = (session: MockSession): void => {
	for (const student of session.students) {
		if (student.status === 'pending') student.status = 'absent';
	}
};

// In mock mode every poll may move at most one pending student into the feed,
// so the projector's three-second refresh visibly changes. Delete with the mock.
const advanceMockSession = (session: MockSession, now: number): void => {
	if (session.status === 'closed' || new Date(session.expiresAt).getTime() <= now) {
		expirePendingScans(session);
		return;
	}

	const pending = session.students.find((student) => student.status === 'pending');
	if (!pending) return;

	const minutesSinceCreation = (now - new Date(session.createdAt).getTime()) / 60000;
	pending.status =
		minutesSinceCreation <= session.presentWindowMinutes ? 'present' : 'late';
	pending.scannedAt = new Date(now).toISOString();
	pending.gps = 'in';
};

const toLiveOffering = (session: MockSession) => {
	const offering = resolveOffering(session.offeringId);
	return {
		id: offering.id,
		course_code: offering.courseCode,
		course_name: offering.courseName,
		section: offering.section,
		room: offering.room
	};
};

const toLegacySummary = (session: MockSession) => {
	const counts = countStatuses(session);
	return {
		id: session.id,
		offeringId: session.offeringId,
		courseId: session.courseId,
		code: session.internalCode,
		createdAt: session.createdAt,
		expiresAt: session.expiresAt,
		presentCount: counts.present,
		lateCount: counts.late,
		absentCount: counts.absent,
		status: session.status
	};
};


// listSessions
// Paginated list of sessions, optionally filtered by date range/course.
export const listSessions = async (_params?: {
	from?: string;
	to?: string;
	courseId?: number;
}) => {
	if (MOCK) {
		const items = MOCK_SESSIONS.filter(
			(session) => _params?.courseId === undefined || session.courseId === _params.courseId
		).map(toLegacySummary);
		return {
			items,
			total: items.length,
			page: 1,
			size: 20
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
	const offering = resolveOffering(offeringId);
	const durationMinutes = options?.durationMinutes ?? 90;
	const presentWindowMinutes = options?.presentWindowMinutes ?? 15;
	const lateWindowMinutes = options?.lateWindowMinutes ?? 5;
	const geofenceRadius = options?.geofenceRadius ?? 50;

	// D12: expires_at = min(created_at + duration_minutes, scheduled_end_time),
	// so a session can never outlive the scheduled class.
	const createdAt = Date.now();
	const durationEnd = createdAt + durationMinutes * 60 * 1000;
	const scheduledEnd = options?.scheduledEndTime
		? new Date(options.scheduledEndTime).getTime()
		: Number.POSITIVE_INFINITY;

	// The real code is HMAC-derived server-side; in mock mode it is a random
	// stand-in so the projector card has something to render.
	const code = MOCK ? mockSessionCode() : '';
	const expiresAt = new Date(Math.min(durationEnd, scheduledEnd));

	const session: MockSession = {
		id: MOCK_SESSIONS.reduce((max, item) => Math.max(max, item.id), 0) + 1,
		offeringId: offering.id,
		courseId: offering.courseId,
		internalCode: `SESSION-${createdAt.toString(36)}`,
		sessionCode: code,
		qrPayload: {
			v: 1,
			code,
			course: offering.id,
			radius: geofenceRadius,
			pw: presentWindowMinutes,
			lw: lateWindowMinutes
		},
		createdAt: new Date(createdAt).toISOString(),
		expiresAt: expiresAt.toISOString(),
		scheduledEndTime:
			options?.scheduledEndTime ?? new Date(createdAt + 2 * 60 * 60 * 1000).toISOString(),
		status: 'active',
		presentWindowMinutes,
		lateWindowMinutes,
		enrolledCount: offering.enrolledCount,
		pendingSyncCount: 0,
		classroomName: options?.classroomName,
		classroomLat: options?.classroomLat,
		classroomLng: options?.classroomLng,
		students: buildPendingRoster(offering.id, offering.enrolledCount, offering.section)
	};

	if (MOCK) MOCK_SESSIONS.push(session);

	return {
		id: session.id,
		offeringId: session.offeringId,
		courseId: session.courseId,
		code: session.internalCode,
		sessionCode: session.sessionCode,
		qrPayload: session.qrPayload,
		classroomName: session.classroomName,
		classroomLat: session.classroomLat,
		classroomLng: session.classroomLng,
		createdAt: session.createdAt,
		expiresAt: session.expiresAt,
		scheduledEndTime: session.scheduledEndTime
	};
};

// closeSession
// Mark a session closed; students can no longer scan against it.
export const closeSession = async (sessionId: number) => {
	if (!MOCK) return { id: sessionId, status: 'closed' as const, final_counts: null };

	const session = MOCK_SESSIONS.find((item) => item.id === sessionId);
	if (!session) {
		return {
			id: sessionId,
			status: 'closed' as const,
			final_counts: { present: 0, late: 0, pending: 0, absent: 0, excused: 0 }
		};
	}

	session.status = 'closed';
	expirePendingScans(session);
	return { id: session.id, status: session.status, final_counts: countStatuses(session) };
};

// excuseStudent
// Professor quick-excuse for an absent or late student. Mirrors D21 path A:
// one approved mock request, immediate status override, and D22 preservation
// of the replaced status.
export const excuseStudent = async (
	sessionId: number,
	studentNumber: string,
	input: { reason: string; notes?: string }
) => {
	if (!MOCK) throw new Error('Excuse actions are unavailable until professor session endpoints land.');

	const session = findMockSession(sessionId);
	const student = findMockStudent(session, studentNumber);
	if (student.status !== 'absent' && student.status !== 'late') {
		throw new Error('Only absent or late students can be excused.');
	}

	const reason = assertExcuseReason(input.reason);
	const notes = normalizeNotes(input.notes);
	const originalStatus = student.originalStatus ?? student.status;
	const request = recordMockExcuse(session, student, reason, notes);
	const excusedAt = new Date().toISOString();

	student.originalStatus = originalStatus;
	student.status = 'excused';
	student.excuseReason = reason;
	student.excuseNotes = notes;
	student.excuseRequestId = request.id;
	student.excusedBy = request.reviewedBy;
	student.excusedAt = excusedAt;

	return {
		excuse_request_id: request.id,
		status: request.status,
		original_status: originalStatus,
		new_status: student.status
	};
};

// editStudentExcuse
// Update the reason/notes for an existing professor excuse. The first
// original status remains untouched for D22 audit.
export const editStudentExcuse = async (
	sessionId: number,
	studentNumber: string,
	input: { reason?: string; notes?: string }
) => {
	if (!MOCK) throw new Error('Excuse actions are unavailable until professor session endpoints land.');

	const session = findMockSession(sessionId);
	const student = findMockStudent(session, studentNumber);
	if (student.status !== 'excused' || student.originalStatus === undefined) {
		throw new Error('Only an existing excuse can be edited.');
	}
	if (input.reason === undefined && input.notes === undefined) {
		throw new Error('Provide an updated reason or note.');
	}

	if (input.reason !== undefined) student.excuseReason = assertExcuseReason(input.reason);
	if (input.notes !== undefined) student.excuseNotes = normalizeNotes(input.notes);

	const request = MOCK_EXCUSE_REQUESTS.find((item) => item.id === student.excuseRequestId);
	if (request) {
		if (student.excuseReason !== undefined) request.reason = student.excuseReason;
		request.notes = student.excuseNotes;
		request.reviewedAt = new Date().toISOString();
	}

	return {
		excuse_request_id: student.excuseRequestId,
		status: 'approved' as const,
		original_status: student.originalStatus,
		new_status: student.status,
		reason: student.excuseReason,
		notes: student.excuseNotes
	};
};

// revokeStudentExcuse
// Reverse a professor excuse and restore the preserved pre-excuse status.
export const revokeStudentExcuse = async (sessionId: number, studentNumber: string) => {
	if (!MOCK) throw new Error('Excuse actions are unavailable until professor session endpoints land.');

	const session = findMockSession(sessionId);
	const student = findMockStudent(session, studentNumber);
	if (student.status !== 'excused' || student.originalStatus === undefined) {
		throw new Error('Only an existing excuse can be revoked.');
	}

	const revertedTo = student.originalStatus;
	student.status = revertedTo;
	delete student.originalStatus;
	delete student.excuseReason;
	delete student.excuseNotes;
	delete student.excuseRequestId;
	delete student.excusedBy;
	delete student.excusedAt;

	return { reverted_to: revertedTo };
};

// excuseAllAbsent
// Bulk-excuse every currently absent student. Re-running the same reason only
// affects students who are still absent, preserving D23 idempotency.
export const excuseAllAbsent = async (
	sessionId: number,
	input: { reason: string; notes?: string }
) => {
	if (!MOCK) throw new Error('Excuse actions are unavailable until professor session endpoints land.');

	const session = findMockSession(sessionId);
	const reason = assertExcuseReason(input.reason);
	const notes = normalizeNotes(input.notes);
	const excusedAt = new Date().toISOString();

	const absent = session.students.filter((student) => student.status === 'absent');
	for (const student of absent) {
		const request = recordMockExcuse(session, student, reason, notes);
		student.originalStatus = 'absent';
		student.status = 'excused';
		student.excuseReason = reason;
		student.excuseNotes = notes;
		student.excuseRequestId = request.id;
		student.excusedBy = request.reviewedBy;
		student.excusedAt = excusedAt;
	}

	return { excused_count: absent.length, reason };
};

// getActiveSession
// Fetch one session's live feed in the professor contract shape. The per-student
// `gps` field is mock-only; the contract does not expose a geofence verdict.
export const getActiveSession = async (sessionId: number) => {
	if (!MOCK) return null;

	const session = MOCK_SESSIONS.find((item) => item.id === sessionId);
	if (!session) return null;

	const now = Date.now();
	advanceMockSession(session, now);

	const counts = countStatuses(session);
	const scanWindowRemaining =
		session.status === 'closed'
			? 0
			: Math.max(0, Math.round((new Date(session.expiresAt).getTime() - now) / 1000));

	return {
		id: session.id,
		offering: toLiveOffering(session),
		session_code: session.sessionCode,
		scan_window_remaining: scanWindowRemaining,
		scheduled_end_time: session.scheduledEndTime,
		status: session.status,
		enrolled_count: session.enrolledCount,
		remaining: Math.max(0, session.enrolledCount - counts.present - counts.late),
		pending_sync_count: session.pendingSyncCount,
		students: session.students.map((student) => ({
			studentNumber: student.studentNumber,
			name: student.name,
			section: student.section,
			status: student.status,
			scannedAt: student.scannedAt,
			excuseReason: student.excuseReason,
			// MOCK-ONLY: retained so excuse edits can prefill internal notes.
			// The create/update excuse contracts accept only `reason`.
			excuse_notes: student.excuseNotes,
			gps: student.gps
		})),
		counts
	};
};

