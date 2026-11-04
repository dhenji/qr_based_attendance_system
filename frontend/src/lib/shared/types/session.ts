// session.ts
// Attendance session a professor opens. qrPayload is embedded in the QR code;
// pw/lw are the present and late windows. `students` is the live scan feed.
//
// The legacy `Session` interface below is the old mock shape. The wire
// interfaces mirror backend/src/features/session/schema.py exactly
// (snake_case); services map them to the camelCase view-models that pages
// render (course names join client-side from GET /professor/courses, since
// session rows carry only offering_id).
//
// `session_type` (D77) records whether the session is a lecture or a
// laboratory meeting; every read carries it and the list/history/ledger
// endpoints accept it as a filter.

import type { CourseType } from './admin';

export type SessionRowStatus = 'scheduled' | 'active' | 'closed';

export type SessionTypeFilter = CourseType;

// GET /professor/sessions
export interface SessionListItemResponse {
	id: number;
	offering_id: number;
	session_type: CourseType;
	session_code: string;
	created_at: string;
	expires_at: string | null;
	duration_minutes: number;
	present_count: number;
	late_count: number;
	absent_count: number;
	pending_count?: number;
	status: SessionRowStatus;
}

export type AttendanceValidationStatus =
	| 'present'
	| 'late'
	| 'absent'
	| 'excused'
	| 'pending'
	| 'rejected';

// GET /professor/sessions/history
export interface SessionHistoryItemResponse extends SessionListItemResponse {
	compliance_rate: number;
	participation_rate: number;
}

// POST /professor/sessions
export interface SessionReadResponse {
	id: number;
	session_code: string;
	offering_id: number;
	session_type: CourseType;
	is_remote: boolean;
	geofence_enabled?: boolean;
	qr_payload: {
		v: 1;
		code: string;
		offering: number;
		radius: number;
		pw: number;
		lw: number;
	};
	expires_at: string | null;
	// The scheduled window (D93): the offering's plan, or the override the
	// professor asked for. `schedule_overridden` says which.
	scheduled_start_time: string;
	scheduled_end_time: string;
	schedule_overridden: boolean;
	plan_source: string;
	// D94: when the session was actually opened, and — for an override — the
	// start it would have carried without one.
	actual_start_time: string | null;
	original_scheduled_start_time: string | null;
	override_reason: string | null;
	created_at: string;
}

// GET /professor/offerings/{id}/session-plan
//
// Everything a session for an offering inherits (D93). The open form renders
// this instead of re-deriving the schedule, so what the professor sees is
// what the server will store.
export interface SessionPlanResponse {
	offering_id: number;
	session_type: CourseType;
	// 'component' (the offering's active meeting for this type),
	// 'offering_legacy' (the offering's own schedule columns),
	// 'course_default' (no meeting configured) or 'none'.
	source: string;
	// The next occurrence, in the institution's local terms and as UTC.
	session_date: string | null;
	start_time: string | null;
	end_time: string | null;
	scheduled_start: string | null;
	scheduled_end: string | null;
	timezone: string;
	duration_minutes: number;
	present_window_minutes: number;
	late_window_minutes: number;
	classroom_name: string | null;
	classroom_lat: number | null;
	classroom_lng: number | null;
	radius_meters: number;
	override_capable: boolean;
	// D94: whether the session may be opened right now. The server's own
	// answer — the form never re-derives the window.
	start_window: SessionStartWindow | null;
}

// D94: the open window.
//
// `permitted` says whether a session may be opened at this very moment.
// `scheduled_date` / `start_time` / `end_time` are today's occurrence of the
// meeting in the institution's local terms, and are null when today is not
// one of the meeting's days.
export interface SessionStartWindow {
	permitted: boolean;
	// 'not_scheduled_today' | 'before_window' | 'after_window' | null
	reason: string | null;
	scheduled_date: string | null;
	start_time: string | null;
	end_time: string | null;
	scheduled_start: string | null;
	scheduled_end: string | null;
	opens_at: string | null;
	closes_at: string | null;
	current_time: string | null;
	timezone: string;
	early_open_minutes: number;
	late_open_minutes: number;
}

// GET /professor/sessions/active/{id}
export interface ActiveStudentItemResponse {
	student_number: string;
	name: string;
	section: string | null;
	status: AttendanceValidationStatus;
	scanned_at: string | null;
	excuse_reason: string | null;
}

export interface SessionActiveResponse {
	id: number;
	offering: number;
	session_type: CourseType;
	is_remote?: boolean;
	session_code: string;
	scan_window_remaining: number;
	scheduled_start_time: string;
	scheduled_end_time: string;
	expires_at: string | null;
	program_code?: string | null;
	year_level_label?: string | null;
	status: SessionRowStatus;
	enrolled_count: number;
	remaining: number;
	pending_sync_count: number;
	students: ActiveStudentItemResponse[];
	counts: {
		present: number;
		late: number;
		pending: number;
		absent: number;
		excused: number;
	};
}

// POST /professor/sessions/{id}/close
export interface SessionCloseResponse {
	id: number;
	status: 'closed';
	final_counts: {
		present: number;
		late: number;
		pending: number;
		absent: number;
		excused: number;
	};
}

// GET /professor/attendance
export interface ProfessorAttendanceItemResponse {
	id: number;
	student_number: string;
	student_name: string;
	section: string | null;
	session_id: number;
	session_type: CourseType;
	status: AttendanceValidationStatus;
	original_status: AttendanceValidationStatus | null;
	scanned_at: string;
	scanned_via: string | null;
	face_match_score: number | null;
}

export interface ProfessorAttendanceLedgerResponse {
	items: ProfessorAttendanceItemResponse[];
	total: number;
	page: number;
	size: number;
	counts?: Record<string, number>;
	total_students?: number;
	total_sessions?: number;
}

// View-models (course names joined client-side from the courses store)

export interface SessionSummary {
	id: number;
	offeringId: number;
	sessionType: CourseType;
	isRemote?: boolean;
	courseCode: string;
	courseName: string;
	section: string;
	sessionCode: string;
	createdAt: string;
	expiresAt: string | null;
	durationMinutes: number;
	presentCount: number;
	lateCount: number;
	absentCount: number;
	pendingCount: number;
	status: SessionRowStatus;
}

export interface SessionHistorySummary extends SessionSummary {
	complianceRate: number;
	participationRate: number;
}

export interface LiveStudent {
	studentNumber: string;
	name: string;
	section: string | null;
	status: AttendanceValidationStatus;
	scannedAt: string | null;
	excuseReason: string | null;
}

export interface LiveSession {
	id: number;
	offeringId: number;
	sessionType: CourseType;
	isRemote?: boolean;
	offeringCode: string;
	offeringName: string;
	offeringSections: string;
	offeringProgram: string | null;
	offeringYearLevel: string | null;
	sessionCode: string;
	scanWindowRemaining: number;
	scheduledStartTime: string;
	scheduledEndTime: string;
	expiresAt: string | null;
	status: SessionRowStatus;
	enrolledCount: number;
	remaining: number;
	pendingSyncCount: number;
	students: LiveStudent[];
	counts: {
		present: number;
		late: number;
		pending: number;
		absent: number;
		excused: number;
	};
}

export interface OpenedSession {
	id: number;
	offeringId: number;
	sessionType: CourseType;
	isRemote?: boolean;
	sessionCode: string;
	qrPayload: {
		v: 1;
		code: string;
		offering: number;
		radius: number;
		pw: number;
		lw: number;
	};
	expiresAt: string | null;
	// The scheduled window (D93): the offering's plan, or the override the
	// professor asked for.
	scheduledStartTime: string;
	scheduledEndTime: string;
	scheduleOverridden: boolean;
	// D94: when the session was really opened, and — for an override — the
	// start it would have carried without one.
	actualStartTime: string | null;
	originalScheduledStartTime: string | null;
	overrideReason: string | null;
	createdAt: string;
}
export interface Session {
  id: number;
  courseId: number;
  code: string;
  qrPayload: {
    v: number;
    code: string;
    course: number;
    radius: number;
    pw: number;
    lw: number;
  };
  expiresAt: string;
  scheduledEndTime: string;
  createdAt: string;
  presentCount: number;
  lateCount: number;
  absentCount: number;
  status: "active" | "closed";
  students: Array<{
    studentId: string;
    name: string;
    section: string;
    status: "present" | "late" | "absent" | "excused" | "rejected";
    scannedAt?: string;
  }>;
}