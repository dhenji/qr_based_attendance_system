// gps.ts
// Shared GPS acquisition helper for the student scan flow.
import { requestBestPosition, calculateDistanceMeters, type BestPosition } from '$lib/shared/utils/geo';
import type { SessionVerification } from './service';

export interface GpsAcquisitionResult {
	fix: BestPosition;
	distanceMeters: number | null;
	status: 'high' | 'low';
}

export const acquireGpsFix = async (
	session: SessionVerification,
	signal?: AbortSignal,
	fastMaximumAge: number = 5000
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
	const status: 'high' | 'low' = fix.accuracy <= 50 ? 'high' : 'low';
	return { fix, distanceMeters, status };
};