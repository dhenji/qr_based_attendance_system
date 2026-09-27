// features/session/service.ts
// Professor-facing service: open/close sessions, live feed, session codes

import { PROFESSOR_COURSES } from '$lib/features/professor/mock';
import { REPORT_SESSIONS, type ReportSessionRecord } from '$lib/features/report/mock';

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
	const session =
		MOCK_SESSIONS.find((item) => item.id === sessionId) ?? HISTORY_SESSIONS.get(sessionId);
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
	const offering = resolveOffering(session.offeringId);
	return {
		id: session.id,
		offeringId: session.offeringId,
		courseId: session.courseId,
		code: session.internalCode,
		// The projector shows session_code (the D12 HMAC stand-in); `code` is
		// the internal row label. Expose both so list rows and the live view
		// cannot disagree.
		session_code: session.sessionCode,
		course_code: offering.courseCode,
		course_name: offering.courseName,
		section: offering.section,
		createdAt: session.createdAt,
		expiresAt: session.expiresAt,
		presentCount: counts.present,
		lateCount: counts.late,
		absentCount: counts.absent,
		status: session.status
	};
};


// listSessions
// Recent/live sessions, optionally filtered by date range/offering/course.
export const listSessions = async (_params?: {
	from?: string;
	to?: string;
	courseId?: number;
	offeringId?: number;
}) => {
	if (MOCK) {
		const fromTime = _params?.from ? new Date(_params.from).getTime() : Number.NEGATIVE_INFINITY;
		const toTime = _params?.to ? new Date(_params.to).getTime() : Number.POSITIVE_INFINITY;
		const items = MOCK_SESSIONS.filter((session) => {
			if (_params?.offeringId !== undefined && session.offeringId !== _params.offeringId)
				return false;
			if (_params?.courseId !== undefined && session.courseId !== _params.courseId)
				return false;
			const created = new Date(session.createdAt).getTime();
			return created >= fromTime && created <= toTime;
		}).map(toLegacySummary);
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

	const session =
		MOCK_SESSIONS.find((item) => item.id === sessionId) ?? HISTORY_SESSIONS.get(sessionId);
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

	// History rows materialize into closed sessions on demand, so every row on
	// the history page opens a real projector view (already closed, with its
	// counts intact) instead of a "not found" error.
	const session =
		MOCK_SESSIONS.find((item) => item.id === sessionId) ??
		materializeHistorySession(sessionId);
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

// Session history (wireframe 3.5 / GET /professor/sessions/history).
// The live store only holds current activity, so completed-session history is
// derived from the deterministic report fixtures — the same rows behind the
// Reports tabs, so filters, tables, charts and CSV exports agree. Each row's
// numeric id is HISTORY_ID_BASE + its fixture index. Delete with the mock.

const HISTORY_ID_BASE = 100000;

export type SessionHistorySortBy = 'date' | 'code' | 'section' | 'rate';
export type SessionHistorySortDir = 'asc' | 'desc';

export type SessionHistoryRow = {
	id: number;
	offering_id: number;
	course_code: string;
	course_name: string;
	section: string;
	session_code: string;
	created_at: string;
	expires_at: string;
	present_count: number;
	late_count: number;
	absent_count: number;
	enrolled_count: number;
	compliance_rate: number;
	participation_rate: number;
	status: MockSessionStatus;
};

export type SessionHistoryFilters = {
	offeringId?: number;
	course?: string;
	section?: string;
	from?: string;
	to?: string;
	sortBy?: SessionHistorySortBy;
	sortDir?: SessionHistorySortDir;
	page?: number;
	size?: number;
};

const hashSeed = (value: string): number => {
	let hash = 2166136261;
	for (let index = 0; index < value.length; index += 1) {
		hash ^= value.charCodeAt(index);
		hash = Math.imul(hash, 16777619);
	}
	return hash >>> 0;
};

// Deterministic XX-XXXX stand-in in the mockSessionCode() shape, so history
// rows render the same code on every load. Delete with the mock.
const historyCodeFor = (sessionId: string): string => {
	const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
	const pick = (length: number, salt: number): string => {
		let state = (hashSeed(sessionId) + Math.imul(salt, 2654435761)) >>> 0;
		let out = '';
		for (let i = 0; i < length; i += 1) {
			state = (Math.imul(state, 1103515245) + 12345) >>> 0;
			out += alphabet[state % alphabet.length];
		}
		return out;
	};
	return `${pick(2, 1)}-${pick(4, 2)}`;
};

// Fixture times are display strings like "9:00 AM"; combine one with its date
// key into an ISO timestamp for the history row.
const parseHistoryTime = (dateKey: string, timeText: string): string => {
	const [year, month, day] = dateKey.split('-').map(Number);
	const match = /^(\d{1,2}):(\d{2})\s*([AP]M)$/i.exec(timeText.trim());
	const date = new Date(year, month - 1, day, 12, 0, 0);
	if (match) {
		let hours = Number(match[1]) % 12;
		if (match[3].toUpperCase() === 'PM') hours += 12;
		date.setHours(hours, Number(match[2]), 0, 0);
	}
	return date.toISOString();
};

// D36: compliance = present / enrolled;
// participation = (present + late + excused) / enrolled.
const toHistoryRow = (record: ReportSessionRecord, index: number): SessionHistoryRow => {
	const compliance = record.enrolled === 0 ? 0 : record.present / record.enrolled;
	const participation =
		record.enrolled === 0 ? 0 : (record.present + record.late + record.excused) / record.enrolled;
	return {
		id: HISTORY_ID_BASE + index,
		offering_id: record.offeringId,
		course_code: record.courseCode,
		course_name: record.courseName,
		section: record.section,
		session_code: historyCodeFor(record.sessionId),
		created_at: parseHistoryTime(record.date, record.startTime),
		expires_at: parseHistoryTime(record.date, record.endTime),
		present_count: record.present,
		late_count: record.late,
		absent_count: record.absent,
		enrolled_count: record.enrolled,
		compliance_rate: compliance,
		participation_rate: participation,
		status: 'closed'
	};
};

// listSessionHistory
// Paginated completed-session history (contract: GET /professor/sessions/history
// with ?offering_id&section&date_from&date_to). Sorted newest-first by default,
// matching the wireframe's Jul29-first table.
export const listSessionHistory = async (params?: SessionHistoryFilters) => {
	if (!MOCK)
		return { items: [], total: 0, page: 1, size: 20, avg_compliance: 0, total_sessions: 0 };

	let start = params?.from ?? '';
	let end = params?.to ?? '';
	if (start && end && start > end) [start, end] = [end, start];

	const rows = REPORT_SESSIONS.map((record, index) => ({ record, index })).filter(
		({ record }) =>
			(params?.offeringId === undefined || record.offeringId === params.offeringId) &&
			(params?.course === undefined || record.courseCode === params.course) &&
			(params?.section === undefined || record.section === params.section) &&
			(!start || record.date >= start) &&
			(!end || record.date <= end)
	);

	const items = rows.map(({ record, index }) => toHistoryRow(record, index));

	const sortBy = params?.sortBy ?? 'date';
	const direction = (params?.sortDir ?? 'desc') === 'asc' ? 1 : -1;
	items.sort((a, b) => {
		if (sortBy === 'code') return a.session_code.localeCompare(b.session_code) * direction;
		if (sortBy === 'section')
			return (
				(a.section.localeCompare(b.section) || a.created_at.localeCompare(b.created_at)) *
				direction
			);
		if (sortBy === 'rate') return (a.compliance_rate - b.compliance_rate) * direction;
		return a.created_at.localeCompare(b.created_at) * direction;
	});

	const size = Math.min(Math.max(params?.size ?? 20, 1), 100);
	const pageCount = Math.max(1, Math.ceil(items.length / size));
	const page = Math.min(Math.max(params?.page ?? 1, 1), pageCount);
	const avg_compliance =
		items.length === 0
			? 0
			: items.reduce((total, row) => total + row.compliance_rate, 0) / items.length;

	return {
		items: items.slice((page - 1) * size, page * size),
		total: items.length,
		page,
		size,
		avg_compliance,
		total_sessions: items.length
	};
};

// Materialize a history fixture into a closed MockSession on first access so
// getActiveSession (and the excuse actions) work for history ids exactly like
// live ones. Statuses are dealt out present → late → excused → absent so the
// projector counts match the history row; the excused reason is a mock
// placeholder — the contracts expose no per-student excuse text for completed
// sessions. Delete with the mock.
const HISTORY_SESSIONS = new Map<number, MockSession>();

const materializeHistorySession = (sessionId: number): MockSession | null => {
	const cached = HISTORY_SESSIONS.get(sessionId);
	if (cached) return cached;
	if (!Number.isInteger(sessionId)) return null;

	const index = sessionId - HISTORY_ID_BASE;
	const record = REPORT_SESSIONS[index];
	if (!record || index < 0) return null;

	const row = toHistoryRow(record, index);
	const createdAt = new Date(row.created_at).getTime();
	const offering = resolveOffering(record.offeringId);

	const students: MockRosterStudent[] = [];
	for (let i = 0; i < record.enrolled; i += 1) {
		const status: MockAttendanceStatus =
			i < record.present
				? 'present'
				: i < record.present + record.late
					? 'late'
					: i < record.present + record.late + record.excused
						? 'excused'
						: 'absent';
		const scanned = status === 'present' || status === 'late';
		students.push({
			studentNumber: `H${record.offeringId}-${record.date.replaceAll('-', '')}-${String(i + 1).padStart(3, '0')}`,
			name: rosterName(i),
			section: record.section,
			status,
			scannedAt: scanned
				? new Date(createdAt + (i + 1) * 2 * 60 * 1000).toISOString()
				: undefined,
			excuseReason: status === 'excused' ? 'Excused (recorded for a prior session)' : undefined,
			gps: scanned ? 'in' : null
		});
	}

	const session: MockSession = {
		id: row.id,
		offeringId: record.offeringId,
		courseId: record.courseId,
		internalCode: `SESSION-${record.date}-${record.offeringId}`,
		sessionCode: row.session_code,
		qrPayload: {
			v: 1,
			code: row.session_code,
			course: record.offeringId,
			radius: 50,
			pw: 15,
			lw: 5
		},
		createdAt: row.created_at,
		expiresAt: row.expires_at,
		scheduledEndTime: row.expires_at,
		status: 'closed',
		presentWindowMinutes: 15,
		lateWindowMinutes: 5,
		enrolledCount: record.enrolled,
		pendingSyncCount: 0,
		classroomName: offering.room,
		students
	};
	HISTORY_SESSIONS.set(sessionId, session);
	return session;
};

