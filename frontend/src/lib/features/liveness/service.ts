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
	scheduledStartTime?: string;
	scheduledEndTime?: string;
	classroomName?: string | null;
	isRemote?: boolean;
	geofenceEnabled?: boolean;
}

export interface AttendanceScanResult {
	id: number;
	status: 'present' | 'late' | 'rejected' | 'pending';
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
		scheduledStartTime: response.scheduled_start_time,
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

export const submitAttendanceScan = async (input: {
	sessionId: number;
	studentNumber: string;
	// Location is optional: scans against sessions with no geofence (remote,
	// disabled, or no classroom coordinates) do not collect GPS.
	gps?: { lat: number; lng: number; accuracy: number } | null;
	livenessEvidence: LivenessEvidence;
	liveFaceEmbedding?: string;
	liveFaceImage?: string;
	scannedAt: string;
	// Queue replay id: sent as X-Idempotency-Key so a retried offline scan
	// can never double-record (docs/architecture/offline-first.md).
	idempotencyKey?: string;
}): Promise<AttendanceScanResult> => {
	const response = await post<AttendanceScanResponse>(
		'attendanceScan',
		{
			session_id: input.sessionId,
			student_number: input.studentNumber,
			gps: input.gps ?? null,
			liveness_evidence: {
				blink_detected: input.livenessEvidence.blinkDetected,
				head_turn_left: input.livenessEvidence.headTurnLeft,
				head_turn_right: input.livenessEvidence.headTurnRight,
				ear_samples: input.livenessEvidence.earSamples,
				pnp_evidence: input.livenessEvidence.pnpEvidence,
				face_count: input.livenessEvidence.faceCount ?? 1,
			},
			live_face_embedding: input.liveFaceEmbedding ?? null,
		live_face_image: input.liveFaceImage ?? null,
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
