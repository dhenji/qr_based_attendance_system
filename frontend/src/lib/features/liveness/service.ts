// features/liveness/service.ts
// QR/GPS/Face challenge state machine

import type { LivenessEvidence } from '$lib/shared/types';
import { isWithinGeofence } from '$lib/shared/utils/geo';

// MOCK flag — swap to false when backend liveness endpoints land
const MOCK = true;

// initiateQRScan
// Kicks off a session scan: returns a freshly generated session code along with
// the course + geofence context and when the code expires (5 min in mock).
export const initiateQRScan = async (courseId: number, geofenceRadius = 50) => {
	if (MOCK) {
		return {
			sessionCode: `SESSION-${Math.random().toString(36).substring(2, 6).toUpperCase()}`,
			courseId,
			geofenceRadius,
			expiresAt: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
		};
	}
	return {
		sessionCode: `SESSION-${Math.random().toString(36).substring(2, 6).toUpperCase()}`,
		courseId,
		geofenceRadius,
		expiresAt: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
	};
};

// validateGPS
// Delegates the check to the Haversine-based geofence util: is the student
// within `radiusMetres` of the classroom center?
export const validateGPS = (
	studentLat: number,
	studentLng: number,
	centerLat: number,
	centerLng: number,
	radiusMetres: number
) => {
	return isWithinGeofence(studentLat, studentLng, centerLat, centerLng, radiusMetres);
};

// submitFaceChallenge
// Face-match result: "passed" requires both a sufficient liveness score
// (>70, D31-style threshold) and that a blink was actually detected.
export const submitFaceChallenge = async (
	faceMatchScore: number,
	livenessEvidence: LivenessEvidence
) => {
	if (MOCK) {
		return {
			passed: faceMatchScore > 70 && livenessEvidence.blinkDetected,
			score: faceMatchScore,
		};
	}
	return {
		passed: faceMatchScore > 70 && livenessEvidence.blinkDetected,
		score: faceMatchScore,
	};
};
