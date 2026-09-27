// features/attendance/service.ts
// Attendance evidence submission, records listing

import { REPORT_SESSIONS } from '$lib/features/report/mock';

// MOCK flag — swap to false when the backend attendance endpoints land
const MOCK = true;

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
	scanned_via?: 'qr' | 'gps' | 'face';
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

// submitEvidence
// Submit a complete attendance scan: photo/proof via GPS location and liveness
// checks. In mock mode we return a random result so the UI can exercise all paths.
export const submitEvidence = async (evidence: {
	sessionId: number;
	studentId: string;
	studentNumber: string;
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
		const via = ['qr', 'gps', 'face'] as const;
		return {
			id: Math.floor(Math.random() * 10000) + 1,
			sessionId: evidence.sessionId,
			studentId: evidence.studentId,
			status: statuses[Math.floor(Math.random() * statuses.length)],
			scannedAt: evidence.scannedAt,
			scannedVia: via[Math.floor(Math.random() * via.length)],
			faceMatchScore: evidence.faceMatchScore,
		};
	}
	return {
		id: Math.floor(Math.random() * 10000) + 1,
		sessionId: evidence.sessionId,
		studentId: evidence.studentId,
		status: 'present' as const,
		scannedAt: evidence.scannedAt,
		scannedVia: 'qr' as const,
		faceMatchScore: evidence.faceMatchScore,
	};
};

// --- Professor ledger (read-only, mock) --------------------------------------
// The live session store only holds current activity, so the cross-session
// ledger is derived from the deterministic report fixtures — the same rows
// behind Session History and Reports, so filters, tables, and CSV exports
// agree. Numeric session ids reuse HISTORY_ID_BASE + fixture index so a
// ledger row's View link materializes the same closed projector view as the
// history page (see session/service materializeHistorySession).
// Delete all of this with the mock.

const HISTORY_ID_BASE = 100000;

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

const hashSeed = (value: string): number => {
	let hash = 2166136261;
	for (let index = 0; index < value.length; index += 1) {
		hash ^= value.charCodeAt(index);
		hash = Math.imul(hash, 16777619);
	}
	return hash >>> 0;
};

// Deterministic XX-XXXX stand-in in the mockSessionCode() shape, so ledger
// rows render the same code as history rows on every load.
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
// key into an ISO timestamp for the ledger row.
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

const viaFor = (seed: number): 'qr' | 'gps' | 'face' => {
	const roll = seed % 10;
	if (roll < 7) return 'qr';
	if (roll < 9) return 'gps';
	return 'face';
};

// listRecords
// Fetch attendance records, optionally filtered by session/status/date range
// (professor-facing view). Returns a paginated response shape.
// Contract: GET /professor/attendance with
// ?course_id&offering_id&section&session_id&status&date_from&date_to&
// sort_by=date|student|section|status|time&sort_dir&page&size
// Read-only: no excuse/mark-present mutations here (D25) — those live on the
// active-session page.
export const listRecords = async (params?: AttendanceLedgerFilters) => {
	if (!MOCK)
		return {
			items: [],
			total: 0,
			page: 1,
			size: 20,
			total_sessions: 0,
			counts: { present: 0, late: 0, absent: 0, excused: 0, pending: 0, rejected: 0 }
		};

	let start = params?.from ?? '';
	let end = params?.to ?? '';
	if (start && end && start > end) [start, end] = [end, start];

	const items: ProfessorAttendanceRow[] = [];
	const sessionIds = new Set<number>();

	REPORT_SESSIONS.forEach((record, index) => {
		if (params?.offeringId !== undefined && record.offeringId !== params.offeringId)
			return;
		if (params?.course !== undefined && record.courseCode !== params.course) return;
		if (params?.section !== undefined && record.section !== params.section) return;
		if (params?.sessionId !== undefined && HISTORY_ID_BASE + index !== params.sessionId)
			return;
		if (start && record.date < start) return;
		if (end && record.date > end) return;

		const sessionId = HISTORY_ID_BASE + index;
		const sessionCode = historyCodeFor(record.sessionId);
		const createdAt = parseHistoryTime(record.date, record.startTime);
		const expiresAt = parseHistoryTime(record.date, record.endTime);
		const createdTime = new Date(createdAt).getTime();
		sessionIds.add(sessionId);

		for (let i = 0; i < record.enrolled; i += 1) {
			const status: ProfessorAttendanceStatus =
				i < record.present
					? 'present'
					: i < record.present + record.late
						? 'late'
						: i < record.present + record.late + record.excused
							? 'excused'
							: 'absent';
			if (params?.status !== undefined && status !== params.status) continue;
			const scanned = status === 'present' || status === 'late';
			const seed = hashSeed(`${record.sessionId}|${i}`);
			items.push({
				id: index * 1000 + i + 1,
				session_id: sessionId,
				session_code: sessionCode,
				created_at: createdAt,
				expires_at: expiresAt,
				offering_id: record.offeringId,
				course_code: record.courseCode,
				course_name: record.courseName,
				section: record.section,
				student_number: `H${record.offeringId}-${record.date.replaceAll('-', '')}-${String(i + 1).padStart(3, '0')}`,
				student_name: rosterName(i),
				status,
				original_status: status === 'excused' ? (seed % 3 === 0 ? 'late' : 'absent') : undefined,
				scanned_at: scanned
					? new Date(createdTime + (i + 1) * 2 * 60 * 1000).toISOString()
					: undefined,
				scanned_via: scanned ? viaFor(seed) : undefined,
				face_match_score: scanned ? Math.round((85 + (seed % 1500) / 100) * 100) / 100 : undefined,
				excuse_reason:
					status === 'excused' ? 'Excused (recorded for a prior session)' : undefined
			});
		}
	});

	const sortBy = params?.sortBy ?? 'date';
	const direction = (params?.sortDir ?? 'desc') === 'asc' ? 1 : -1;
	const statusOrder: Record<ProfessorAttendanceStatus, number> = {
		present: 0,
		late: 1,
		excused: 2,
		pending: 3,
		absent: 4,
		rejected: 5
	};
	items.sort((a, b) => {
		if (sortBy === 'student')
			return (
				(a.student_name.localeCompare(b.student_name) ||
					a.created_at.localeCompare(b.created_at)) *
				direction
			);
		if (sortBy === 'section')
			return (
				(a.section.localeCompare(b.section) || a.created_at.localeCompare(b.created_at)) *
				direction
			);
		if (sortBy === 'status')
			return (
				(statusOrder[a.status] - statusOrder[b.status] ||
					a.created_at.localeCompare(b.created_at)) *
				direction
			);
		if (sortBy === 'time')
			return (a.scanned_at ?? '').localeCompare(b.scanned_at ?? '') * direction;
		return a.created_at.localeCompare(b.created_at) * direction;
	});

	const size = Math.min(Math.max(params?.size ?? 20, 1), 100);
	const pageCount = Math.max(1, Math.ceil(items.length / size));
	const page = Math.min(Math.max(params?.page ?? 1, 1), pageCount);

	const counts = { present: 0, late: 0, absent: 0, excused: 0, pending: 0, rejected: 0 };
	for (const item of items) counts[item.status] += 1;

	return {
		items: items.slice((page - 1) * size, page * size),
		total: items.length,
		page,
		size,
		total_sessions: sessionIds.size,
		counts
	};
};
