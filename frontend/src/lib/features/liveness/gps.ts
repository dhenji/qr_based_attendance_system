// gps.ts
// Shared GPS acquisition helper for the student scan flow.
import { requestBestPosition, calculateDistanceMeters, type BestPosition } from '$lib/shared/utils/geo';
import type { SessionVerification } from './service';

export interface GpsAcquisitionResult {
	fix: BestPosition;
	distanceMeters: number | null;
	status: 'high' | 'moderate' | 'low';
}

export const acquireGpsFix = async (
	session: SessionVerification,
	signal?: AbortSignal,
	fastMaximumAge: number = 0
): Promise<GpsAcquisitionResult> => {
	const fix = await requestBestPosition({
		desiredAccuracy: 50,
		maxFixes: 3,
		timeoutMs: 10000,
		signal,
		fastMaximumAge
	});
	const center = session.geofence;
	let distanceMeters: number | null = null;
	if (center.lat !== null && center.lng !== null) {
		distanceMeters = calculateDistanceMeters(fix.lat, fix.lng, center.lat, center.lng);
	}
	const reviewThreshold = session.geofence.gpsReviewAccuracyThreshold;
	const hasReviewThreshold =
		typeof reviewThreshold === 'number' &&
		Number.isFinite(reviewThreshold) &&
		reviewThreshold > 0;
	let status: 'high' | 'moderate' | 'low';
	if (hasReviewThreshold && fix.accuracy > (reviewThreshold as number)) {
		status = 'low';
	} else if (fix.accuracy <= 50) {
		status = 'high';
	} else if (hasReviewThreshold && fix.accuracy <= (reviewThreshold as number)) {
		status = 'moderate';
	} else {
		status = 'high';
	}
	return { fix, distanceMeters, status };
};
