// geo.ts
// Geofence math: Haversine distance between two coordinates, then a radius check.
import { APIError } from '$lib/api/client';

export type AccuracyStatus = 'high' | 'moderate' | 'low';

// Hard floor for GPS accuracy (metres). Fixes coarser than this are rejected by
// the backend (gps_accuracy_too_low) and are not queued for offline replay.
export const GPS_HARD_FLOOR_METERS = 1000;

// Great-circle distance in metres (convenience over calculateDistance).
export const calculateDistanceMeters = (
	lat1: number,
	lng1: number,
	lat2: number,
	lng2: number
): number => calculateDistance(lat1, lng1, lat2, lng2) * 1000;

export const clamp = (value: number, min: number, max: number): number =>
	Math.min(Math.max(value, min), max);

export const clampRadius = (value: number, min: number, max: number): number =>
	clamp(Math.round(value), min, max);

export const getAccuracyStatus = (
	accuracy: number,
	desiredAccuracy: number = 50
): AccuracyStatus => {
	if (!Number.isFinite(accuracy) || accuracy <= 0) return 'low';
	if (accuracy <= desiredAccuracy) return 'high';
	if (accuracy <= desiredAccuracy * 2) return 'moderate';
	return 'low';
};

export const isLowAccuracy = (accuracy: number, desiredAccuracy: number = 50): boolean =>
	!Number.isFinite(accuracy) || accuracy > desiredAccuracy;

export interface BestPosition {
	lat: number;
	lng: number;
	accuracy: number;
	timestamp?: number;
}

export interface BestPositionOptions {
	desiredAccuracy?: number;
	maxFixes?: number;
	timeoutMs?: number;
	maxAccuracy?: number;
	signal?: AbortSignal;
	fastFirst?: boolean;
	fastTimeoutMs?: number;
	fastAccuracyThreshold?: number;
	fastMaximumAge?: number;
}

// In-flight promise dedup: concurrent callers with the same option signature
// share a single watchPosition session.
const inflight = new Map<string, Promise<BestPosition>>();

// Acquire the best available GPS fix using watchPosition. Collects up to
// `maxFixes` fixes, stopping early once a fix meets `desiredAccuracy`.
// A fast first fix (low accuracy, short timeout) is attempted first when
// available, falling back to the high-accuracy watch otherwise.
// The watcher and the overall timeout are cleared on every code path.
export const requestBestPosition = async (
	options?: BestPositionOptions
): Promise<BestPosition> => {
	const desiredAccuracy = options?.desiredAccuracy ?? 50;
	const maxFixes = (() => {
		const v = options?.maxFixes;
		if (v === undefined) return 3;
		if (!Number.isFinite(v) || v < 1) return 1;
		return Math.floor(v);
	})();
	const timeoutMs = (() => {
		const v = options?.timeoutMs;
		if (v === undefined) return 8000;
		if (!Number.isFinite(v) || v < 0) return 0;
		return v;
	})();
	const maxAccuracy = options?.maxAccuracy ?? Infinity;
	const signal = options?.signal;
	const fastFirst = options?.fastFirst ?? true;
	const fastTimeoutMs = (() => {
		const v = options?.fastTimeoutMs;
		if (v === undefined) return 2000;
		if (!Number.isFinite(v) || v < 0) return 0;
		return v;
	})();
	const fastAccuracyThreshold = options?.fastAccuracyThreshold ?? desiredAccuracy;
	const fastMaximumAge = (() => {
		const v = options?.fastMaximumAge;
		if (v === undefined) return 0;
		if (!Number.isFinite(v) || v < 0) return 0;
		return v;
	})();

	if (typeof navigator === 'undefined' || !navigator.geolocation) {
		throw new APIError('location_unavailable', 'We could not determine your current location. Enable location services and try again.');
	}

	const effectiveFastFirst =
		fastFirst && typeof navigator.geolocation.getCurrentPosition === 'function';

	const key = `${desiredAccuracy}|${maxFixes}|${timeoutMs}|${maxAccuracy}|${effectiveFastFirst}|${fastTimeoutMs}|${fastAccuracyThreshold}|${fastMaximumAge}`;

	let promise = inflight.get(key);
	if (!promise) {
		promise = (async () => {
			// Fast first fix: one-shot low-accuracy attempt.
			if (effectiveFastFirst) {
				const fast = await new Promise<BestPosition | null>((resolve, reject) => {
					let settled = false;
					const done = (value: BestPosition | null) => {
						if (settled) return;
						settled = true;
						resolve(value);
					};
					const fail = (err: APIError) => {
						if (settled) return;
						settled = true;
						reject(err);
					};
					try {
						navigator.geolocation.getCurrentPosition(
							(pos) => {
								const c = pos.coords;
								if (
									!Number.isFinite(c.latitude) ||
									!Number.isFinite(c.longitude) ||
									!Number.isFinite(c.accuracy)
								) {
									done(null);
									return;
								}
								if (c.accuracy <= 0) {
									done(null);
									return;
								}
								if (c.latitude < -90 || c.latitude > 90) {
									done(null);
									return;
								}
								if (c.longitude < -180 || c.longitude > 180) {
									done(null);
									return;
								}
								if (pos.timestamp != null && Number.isFinite(pos.timestamp)) {
									if (pos.timestamp >= 1e12 && Date.now() - pos.timestamp > 30 * 1000) {
										done(null);
										return;
									}
								}
								const fix: BestPosition = {
									lat: c.latitude,
									lng: c.longitude,
									accuracy: c.accuracy,
									timestamp: pos.timestamp,
								};
								if (fix.accuracy <= fastAccuracyThreshold && fix.accuracy <= maxAccuracy) {
									done(fix);
								} else {
									done(null);
								}
							},
							(err) => {
								if (err.code === err.PERMISSION_DENIED) {
									fail(new APIError('location_permission_denied', 'Location permission is required to verify your attendance. Enable location access in your device settings.'));
								} else {
									done(null);
								}
							},
							{ enableHighAccuracy: false, maximumAge: fastMaximumAge, timeout: fastTimeoutMs }
						);
					} catch {
						done(null);
					}
				}).catch((e) => {
					if (e instanceof APIError && e.code === 'location_permission_denied') {
						throw e;
					}
					return null;
				});
				if (fast) {
					return fast;
				}
			}

			// High-accuracy watch phase.
			return new Promise<BestPosition>((resolve, reject) => {
				let best: BestPosition | null = null;
				let fixes = 0;
				let watchId: number | null = null;
				let timer: ReturnType<typeof setTimeout> | null = null;
				let settled = false;

				const cleanup = () => {
					if (watchId !== null) {
						try {
							navigator.geolocation.clearWatch(watchId);
						} catch {
							// ignore
						}
						watchId = null;
					}
					if (timer !== null) {
						clearTimeout(timer);
						timer = null;
					}
				};

				const finish = (value: BestPosition) => {
					if (settled) return;
					settled = true;
					cleanup();
					if (inflight.get(key) === promise) inflight.delete(key);
					if (value.accuracy > maxAccuracy) {
						reject(
							new APIError(
								'location_accuracy_too_low',
								'Unable to get a sufficiently accurate location. Move to an area with a clearer signal and try again.'
							)
						);
					} else {
						resolve(value);
					}
				};

				const fail = (err: APIError) => {
					if (settled) return;
					settled = true;
					cleanup();
					if (inflight.get(key) === promise) inflight.delete(key);
					reject(err);
				};

				timer = setTimeout(() => {
					if (best) finish(best);
					else
						fail(
							new APIError('location_timeout', 'We could not determine your current location in time. Move to an area with a clearer signal and try again.')
						);
				}, timeoutMs);

				try {
					watchId = navigator.geolocation.watchPosition(
						(pos) => {
							const c = pos.coords;
							if (
								!Number.isFinite(c.latitude) ||
								!Number.isFinite(c.longitude) ||
								!Number.isFinite(c.accuracy)
							) {
								return;
							}
							if (c.accuracy <= 0) return;
							if (c.latitude < -90 || c.latitude > 90) return;
							if (c.longitude < -180 || c.longitude > 180) return;
							if (pos.timestamp != null && Number.isFinite(pos.timestamp)) {
								if (pos.timestamp >= 1e12 && Date.now() - pos.timestamp > 30 * 1000) return;
							}
							fixes += 1;
							const fix: BestPosition = {
								lat: c.latitude,
								lng: c.longitude,
								accuracy: c.accuracy,
								timestamp: pos.timestamp,
							};
							if (best === null || fix.accuracy < best.accuracy) best = fix;
							if (import.meta.env.DEV) {
								// eslint-disable-next-line no-console
								console.debug('[geo] fix', {
									lat: fix.lat,
									lng: fix.lng,
									accuracy: fix.accuracy,
									timestamp: fix.timestamp,
									fixes,
									bestAccuracy: best?.accuracy
								});
							}
							if (best !== null && best.accuracy <= desiredAccuracy) {
								finish(best);
							} else if (fixes >= maxFixes) {
								finish((best ?? fix) as BestPosition);
							}
						},
						(err) => {
							if (err.code === err.PERMISSION_DENIED) {
								fail(new APIError('location_permission_denied', 'Location permission is required to verify your attendance. Enable location access in your device settings.'));
							} else if (err.code === err.TIMEOUT) {
								fail(new APIError('location_timeout', 'We could not determine your current location in time. Move to an area with a clearer signal and try again.'));
							} else {
								fail(new APIError('location_unavailable', 'We could not determine your current location. Enable location services and try again.'));
							}
						},
						{ enableHighAccuracy: true, maximumAge: 0, timeout: timeoutMs }
					);
				} catch {
					fail(new APIError('location_unavailable', 'We could not determine your current location. Enable location services and try again.'));
				}
			});
		})();
		inflight.set(key, promise);
		promise.catch(() => {});
		promise.finally(() => {
			if (inflight.get(key) === promise) inflight.delete(key);
		}).catch(() => {});
	}

	if (!signal) return promise;
	if (signal.aborted) {
		throw new APIError('location_unavailable', 'Location request was cancelled.');
	}
	return new Promise<BestPosition>((resolve, reject) => {
		const onAbort = () => {
			reject(new APIError('location_unavailable', 'Location request was cancelled.'));
		};
		const remove = () => signal.removeEventListener('abort', onAbort);
		signal.addEventListener('abort', onAbort, { once: true });
		promise.then(
			(v) => {
				remove();
				resolve(v);
			},
			(e) => {
				remove();
				reject(e);
			}
		);
	});
};

// Great-circle distance between (lat1, lng1) and (lat2, lng2) in km.
export const calculateDistance = (
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number
): number => {
  const R = 6371; // Earth radius in km
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLng / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c; // Returns km
};

// True when the student's position is within the classroom's radius (metres).
// Invalid coordinates or a negative radius never match — fail closed rather
// than letting NaN compare its way into a false present.
export const isWithinGeofence = (
	studentLat: number,
	studentLng: number,
	centerLat: number,
	centerLng: number,
	radiusMetres: number
): boolean => {
	if (
		!Number.isFinite(studentLat) ||
		!Number.isFinite(studentLng) ||
		!Number.isFinite(centerLat) ||
		!Number.isFinite(centerLng) ||
		!Number.isFinite(radiusMetres) ||
		radiusMetres < 0
	) {
		return false;
	}
	const distanceKm = calculateDistance(studentLat, studentLng, centerLat, centerLng);
	const distanceMetres = distanceKm * 1000;
	return distanceMetres <= radiusMetres;
};

// A single search result returned by the Photon (Komoot) geocoder.
export interface LocationSearchResult {
	label: string;
	lat: number;
	lng: number;
}

// Search for a place by free-text query. Returns up to `limit` results.
// Uses Photon (https://photon.komoot.io), which supports CORS and needs no
// API key. Returns an empty list on network/parse failure so callers can
// degrade gracefully.
export const searchLocation = async (
	query: string,
	limit: number = 5
): Promise<LocationSearchResult[]> => {
	const trimmed = query.trim();
	if (trimmed.length < 3) return [];
	try {
		const url = `https://photon.komoot.io/api/?q=${encodeURIComponent(trimmed)}&limit=${limit}`;
		const response = await fetch(url, { headers: { Accept: 'application/json' } });
		if (!response.ok) return [];
		const data = (await response.json()) as {
			features?: Array<{
				geometry?: { coordinates?: [number, number] };
				properties?: { name?: string; street?: string; city?: string; country?: string };
			}>;
		};
		const out: LocationSearchResult[] = [];
		for (const feature of data.features ?? []) {
			const coords = feature.geometry?.coordinates;
			if (!coords || coords.length < 2) continue;
			const [lng, lat] = coords;
			if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;
			const p = feature.properties ?? {};
			const label = [p.name, p.street, p.city, p.country].filter(Boolean).join(', ');
			out.push({ label: label || `${lat.toFixed(4)}, ${lng.toFixed(4)}`, lat, lng });
		}
		return out;
	} catch {
		return [];
	}
};