// features/liveness/service.ts
// QR/GPS/Face challenge state machine

import type { LivenessEvidence } from '$lib/shared/types';
import { isWithinGeofence } from '$lib/shared/utils/geo';

// MOCK flag
const MOCK = true;

// QR scan initiation
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

// GPS validation
export const validateGPS = (
	studentLat: number,
	studentLng: number,
	centerLat: number,
	centerLng: number,
	radiusMetres: number
) => {
	return isWithinGeofence(studentLat, studentLng, centerLat, centerLng, radiusMetres);
};

// Face challenge result
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
