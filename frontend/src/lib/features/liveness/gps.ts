// gps.ts
// Shared GPS acquisition helper for the student scan flow.
import { acquire } from '$lib/shared/location/manager';
import { calculateDistanceMeters, type BestPosition } from '$lib/shared/utils/geo';
import { APIError } from '$lib/api/client';
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
	const state = await acquire({
		desiredAccuracy: 50,
		maxFixes: 3,
		timeoutMs: 10000,
		signal,
		fastMaximumAge,
	});

	if (state.error || state.latitude === null || state.longitude === null || state.accuracy === null) {
		const code = state.error?.code ?? 'location_unavailable';
		const message = state.error?.message ?? 'Unable to get your location.';
		throw new APIError(code, message);
	}

	const fix: BestPosition = {
		lat: state.latitude,
		lng: state.longitude,
		accuracy: state.accuracy,
		timestamp: state.timestamp ?? undefined,
	};

	const center = session.geofence;
	let distanceMeters: number | null = null;
	if (center.lat !== null && center.lng !== null) {
		distanceMeters = calculateDistanceMeters(fix.lat, fix.lng, center.lat, center.lng);
	}

	// Fall back to the backend default review threshold (100 m) when the
	// session payload omits it, so the client never labels a coarse fix
	// "high" just because the field was missing.
	const reviewThreshold = session.geofence.gpsReviewAccuracyThreshold;
	const effectiveThreshold =
		typeof reviewThreshold === 'number' &&
		Number.isFinite(reviewThreshold) &&
		reviewThreshold > 0
			? reviewThreshold
			: 100;
	let status: 'high' | 'moderate' | 'low';
	if (fix.accuracy > effectiveThreshold) {
		status = 'low';
	} else if (fix.accuracy <= 50) {
		status = 'high';
	} else {
		status = 'moderate';
	}

	return { fix, distanceMeters, status };
};