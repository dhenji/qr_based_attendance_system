import { post } from '$lib/api/client';
import type {
	AttendancePrecheckResponse,
	AttendanceScanResponse,
	SessionVerificationResponse,
} from '$lib/api/endpoints';
import type { LivenessEvidence } from '$lib/shared/types';
import { isWithinGeofence } from '$lib/shared/utils/geo';

export interface SessionVerification {
	sessionId: number;
	courseCode: string;
	courseName: string;
	expiresAt: string;
	// Center null = no classroom coordinates; both the server and the scan
	// page skip the geofence check in that case.
	geofence: { radius: number; lat: number | null; lng: number | null };
	programCode?: string;
	yearLevelLabel?: string;
	sessionType?: 'lecture' | 'lab';
	scheduledEndTime?: string;
	classroomName?: string | null;
	isRemote?: boolean;
	geofenceEnabled?: boolean;
}

export interface AttendanceScanResult {
	id: number;
	status: 'present' | 'late' | 'rejected';
	scannedAt: string;
	expiresAt: string;
}

// Scan precheck (D27 step-2 gate) — read-only, never writes attendance.
// The backend resolves the student from the authenticated user and only
// compares payload.student_number case-insensitively (403
// student_number_mismatch on spoof). 200 flags enrolled/already_scanned,
// which submitAttendanceScan would reject as 403 not_enrolled /
// 409 duplicate_scan. No idempotency key: the route reads none.
export interface AttendancePrecheckResult {
	enrolled: boolean;
	alreadyScanned: boolean;
	studentId: string;
	studentName: string;
	section?: string;
}

export const precheckScan = async (input: {
	sessionId: number;
	studentNumber: string;
}): Promise<AttendancePrecheckResult> => {
	const response = await post<AttendancePrecheckResponse>('attendancePrecheck', {
		session_id: input.sessionId,
		student_number: input.studentNumber,
	});

	return {
		enrolled: response.enrolled,
		alreadyScanned: response.already_scanned,
		studentId: response.student.student_id,
		studentName: response.student.name,
		section: response.student.section ?? undefined,
	};
};

export const verifySessionCode = async (code: string): Promise<SessionVerification> => {
	const response = await post<SessionVerificationResponse>('sessionQR', { code: code.trim() });

	return {
		sessionId: response.session_id,
		courseCode: response.course_code,
		courseName: response.course_name,
		expiresAt: response.expires_at,
		geofence: response.geofence,
		programCode: response.program_code,
		yearLevelLabel: response.year_level_label,
		sessionType: response.session_type,
		scheduledEndTime: response.scheduled_end_time,
		classroomName: response.classroom_name,
		isRemote: response.is_remote,
		geofenceEnabled: response.geofence_enabled,
	};
};

export const validateGPS = (
	studentLat: number,
	studentLng: number,
	centerLat: number,
	centerLng: number,
	radiusMetres: number
) => {
	return isWithinGeofence(studentLat, studentLng, centerLat, centerLng, radiusMetres);
};

// PLACEHOLDER face-match score. Read this before trusting the face step.
//
// `POST /student/attendance/scan` requires `face_match_score` (backend
// `ScanRequest.face_match_score`, a required float in 0.0..1.0 with no
// default). The server band-checks whatever number arrives:
//   < 0.65                -> 403 face_mismatch, nothing recorded
//   0.65 .. 0.70          -> recorded `pending`, queued for human review
//   >= 0.70 (FACE_MATCH_THRESHOLD) -> present / late
//
// It never compares that number to anything. The student's stored
// `face_embedding` is written by `_stub_embedding_blob` (all-zero 128-dim
// vectors tagged "stub": true) and is not read during a scan at all, and
// enrollment is not even required. So the score is a client assertion and the
// face step is currently decorative — what genuinely IS enforced server-side
// is the liveness evidence (blink + head turns + EAR mean + pnp), graded in
// `_validate_liveness_evidence`.
//
// Sending a fixed high value is a stopgap to keep the scan journey working, not
// a security control. Computing a real score needs a real reference embedding
// and a documented decrypt scheme for the cached blob, and the comparison has
// to happen server-side. Both are backend work.
//
// Every scan path funnels through `submitAttendanceScan`, so the default lives
// here rather than at the call sites — the offline replay in features/sync
// forwards queued payloads that also carry no score, and both used to produce a
// 422 (and a queue row marked terminally `rejected`, discarding the student's
// evidence). An explicitly-passed value still wins, so this can be replaced with
// a real computation without touching callers.
export const FACE_MATCH_SCORE_PLACEHOLDER = 1;

export const submitAttendanceScan = async (input: {
	sessionId: number;
	studentNumber: string;
	gps: { lat: number; lng: number; accuracy: number };
	livenessEvidence: LivenessEvidence;
	faceMatchScore?: number;
	scannedAt: string;
	// Queue replay id: sent as X-Idempotency-Key so a retried offline scan
	// can never double-record (docs/architecture/offline-first.md).
	idempotencyKey?: string;
}): Promise<AttendanceScanResult> => {
	const faceMatchScore = input.faceMatchScore ?? FACE_MATCH_SCORE_PLACEHOLDER;

	const response = await post<AttendanceScanResponse>(
		'attendanceScan',
		{
			session_id: input.sessionId,
			student_number: input.studentNumber,
			gps: input.gps,
			liveness_evidence: {
				blink_detected: input.livenessEvidence.blinkDetected,
				head_turn_left: input.livenessEvidence.headTurnLeft,
				head_turn_right: input.livenessEvidence.headTurnRight,
				ear_samples: input.livenessEvidence.earSamples,
				pnp_evidence: input.livenessEvidence.pnpEvidence,
			},
			face_match_score: faceMatchScore,
			scanned_at: input.scannedAt,
		},
		undefined,
		undefined,
		input.idempotencyKey === undefined ? undefined : { 'X-Idempotency-Key': input.idempotencyKey }
	);

	return {
		id: response.id,
		status: response.status,
		scannedAt: response.scanned_at,
		expiresAt: response.expires_at,
	};
};
