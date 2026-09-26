import { post } from '$lib/api/client';
import type { AttendanceScanResponse, SessionVerificationResponse } from '$lib/api/endpoints';
import type { LivenessEvidence } from '$lib/shared/types';
import { isWithinGeofence } from '$lib/shared/utils/geo';

export interface SessionVerification {
	sessionId: number;
	courseCode: string;
	courseName: string;
	expiresAt: string;
	geofence: { radius: number; lat: number; lng: number };
}

export interface AttendanceScanResult {
	id: number;
	status: 'present' | 'late' | 'rejected';
	scannedAt: string;
	expiresAt: string;
}

export const verifySessionCode = async (code: string): Promise<SessionVerification> => {
	const response = await post<SessionVerificationResponse>('sessionQR', { code: code.trim() });

	return {
		sessionId: response.session_id,
		courseCode: response.course_code,
		courseName: response.course_name,
		expiresAt: response.expires_at,
		geofence: response.geofence,
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
	gps: { lat: number; lng: number; accuracy: number };
	livenessEvidence: LivenessEvidence;
	faceMatchScore?: number;
	scannedAt: string;
}): Promise<AttendanceScanResult> => {
	const response = await post<AttendanceScanResponse>('attendanceScan', {
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
		...(input.faceMatchScore === undefined ? {} : { face_match_score: input.faceMatchScore }),
		scanned_at: input.scannedAt,
	});

	return {
		id: response.id,
		status: response.status,
		scannedAt: response.scanned_at,
		expiresAt: response.expires_at,
	};
};
