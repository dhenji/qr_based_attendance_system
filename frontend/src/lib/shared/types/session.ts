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

export type SessionRowStatus = 'active' | 'closed';

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
	qr_payload: {
		v: 1;
		code: string;
		offering: number;
		radius: number;
		pw: number;
		lw: number;
	};
	expires_at: string | null;
	scheduled_end_time: string;
	created_at: string;
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
	session_code: string;
	scan_window_remaining: number;
	scheduled_end_time: string;
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

// View-models (course names joined client-side from the courses store)

export interface SessionSummary {
	id: number;
	offeringId: number;
	sessionType: CourseType;
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
	offeringCode: string;
	offeringName: string;
	offeringSections: string;
	sessionCode: string;
	scanWindowRemaining: number;
	scheduledEndTime: string;
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
	scheduledEndTime: string;
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