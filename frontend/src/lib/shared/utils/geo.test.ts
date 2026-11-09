import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
	clamp,
	clampRadius,
	getAccuracyStatus,
	isLowAccuracy,
	calculateDistanceMeters,
	isWithinGeofence,
	isWithinGeofenceWithUncertainty,
	searchLocation,
	reverseGeocode,
	requestBestPosition
} from './geo';

describe('clamp', () => {
	it('clamps below min', () => {
		expect(clamp(-5, 0, 10)).toBe(0);
	});
	it('clamps above max', () => {
		expect(clamp(15, 0, 10)).toBe(10);
	});
	it('returns value when in range', () => {
		expect(clamp(5, 0, 10)).toBe(5);
	});
});

describe('clampRadius', () => {
	it('rounds and clamps', () => {
		expect(clampRadius(4.6, 1, 10)).toBe(5);
		expect(clampRadius(0, 1, 10)).toBe(1);
		expect(clampRadius(20, 1, 10)).toBe(10);
	});
});

describe('getAccuracyStatus', () => {
	it('returns low for non-finite or <=0', () => {
		expect(getAccuracyStatus(NaN)).toBe('low');
		expect(getAccuracyStatus(0)).toBe('low');
		expect(getAccuracyStatus(-1)).toBe('low');
	});
	it('returns high when within desired', () => {
		expect(getAccuracyStatus(30, 50)).toBe('high');
		expect(getAccuracyStatus(50, 50)).toBe('high');
	});
	it('returns moderate between desired and 2x', () => {
		expect(getAccuracyStatus(75, 50)).toBe('moderate');
	});
	it('returns low above 2x', () => {
		expect(getAccuracyStatus(150, 50)).toBe('low');
	});
});

describe('isLowAccuracy', () => {
	it('true for non-finite or > desired', () => {
		expect(isLowAccuracy(NaN)).toBe(true);
		expect(isLowAccuracy(60, 50)).toBe(true);
	});
	it('false when within desired', () => {
		expect(isLowAccuracy(40, 50)).toBe(false);
	});
});

describe('calculateDistanceMeters', () => {
	it('returns ~0 for identical points', () => {
		expect(calculateDistanceMeters(0, 0, 0, 0)).toBe(0);
	});
	it('returns positive distance for distinct points', () => {
		const d = calculateDistanceMeters(0, 0, 0.001, 0.001);
		expect(d).toBeGreaterThan(0);
	});
});

describe('isWithinGeofence', () => {
	it('returns false for invalid inputs', () => {
		expect(isWithinGeofence(NaN, 0, 0, 0, 10)).toBe(false);
		expect(isWithinGeofence(0, 0, 0, 0, -1)).toBe(false);
	});
	it('returns true when within radius', () => {
		expect(isWithinGeofence(0, 0, 0, 0, 10)).toBe(true);
	});
	it('returns false when outside radius', () => {
		expect(isWithinGeofence(0, 0, 10, 10, 1)).toBe(false);
	});
});

describe('searchLocation', () => {
	let fetchMock: ReturnType<typeof vi.fn>;

	beforeEach(() => {
		fetchMock = vi.fn();
		vi.stubGlobal('fetch', fetchMock);
	});

	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it('returns [] for short queries', async () => {
		expect(await searchLocation('ab')).toEqual([]);
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('returns parsed results on success', async () => {
		fetchMock.mockResolvedValue({
			ok: true,
			json: async () => ({
				features: [
					{
						geometry: { coordinates: [121.0, 14.5] },
						properties: { name: 'Manila', city: 'Manila', country: 'PH' }
					}
				]
			})
		});
		const res = await searchLocation('Manila');
		expect(res).toEqual([{ label: 'Manila, Manila, PH', lat: 14.5, lng: 121.0 }]);
	});

	it('returns [] on empty features', async () => {
		fetchMock.mockResolvedValue({
			ok: true,
			json: async () => ({ features: [] })
		});
		expect(await searchLocation('Manila')).toEqual([]);
	});

	it('returns [] on non-ok response', async () => {
		fetchMock.mockResolvedValue({ ok: false, json: async () => ({}) });
		expect(await searchLocation('Manila')).toEqual([]);
	});

	it('returns [] on fetch failure', async () => {
		fetchMock.mockRejectedValue(new Error('network'));
		expect(await searchLocation('Manila')).toEqual([]);
	});
});

describe('requestBestPosition', () => {
	let watchCallback: ((pos: any) => void) | null = null;
	let errorCallback: ((err: any) => void) | null = null;
	let clearWatch: ReturnType<typeof vi.fn>;
	let watchPosition: ReturnType<typeof vi.fn>;

	beforeEach(() => {
		watchCallback = null;
		errorCallback = null;
		clearWatch = vi.fn();
		watchPosition = vi.fn((success, error, _opts) => {
			watchCallback = success;
			errorCallback = error;
			return 1;
		});
		vi.stubGlobal('navigator', {
			geolocation: { watchPosition, clearWatch }
		} as any);
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllGlobals();
	});

	const makePos = (lat: number, lng: number, accuracy: number) => ({
		coords: { latitude: lat, longitude: lng, accuracy },
		timestamp: 12345
	});

	it('returns the lowest-accuracy fix among collected fixes', async () => {
		const promise = requestBestPosition({ desiredAccuracy: 1, maxFixes: 3, timeoutMs: 1000 });
		// first fix accuracy 100
		watchCallback!(makePos(1, 2, 100));
		// second fix accuracy 10
		watchCallback!(makePos(3, 4, 10));
		// third triggers maxFixes
		watchCallback!(makePos(5, 6, 50));
		const res = await promise;
		expect(res).toEqual({ lat: 3, lng: 4, accuracy: 10, timestamp: 12345 });
	});

	it('stops early once a fix meets desiredAccuracy', async () => {
		const promise = requestBestPosition({ desiredAccuracy: 50, maxFixes: 3, timeoutMs: 1000 });
		watchCallback!(makePos(1, 2, 40));
		const res = await promise;
		expect(res.accuracy).toBe(40);
		// further fixes should not matter
	});

	it('does not stop on a coarse fix when desiredAccuracy is small', async () => {
		const promise = requestBestPosition({ desiredAccuracy: 50, maxFixes: 2, timeoutMs: 1000 });
		watchCallback!(makePos(1, 2, 100)); // coarse, should not stop (maxFixes 2)
		watchCallback!(makePos(3, 4, 10)); // stops via maxFixes
		const res = await promise;
		expect(res).toEqual({ lat: 3, lng: 4, accuracy: 10, timestamp: 12345 });
	});

	it('throws location_timeout when no fix arrives', async () => {
		const promise = requestBestPosition({ desiredAccuracy: 50, maxFixes: 3, timeoutMs: 100 });
		vi.advanceTimersByTime(100);
		await expect(promise).rejects.toMatchObject({ code: 'location_timeout' });
	});

	it('ignores fixes with non-finite coordinates', async () => {
		const promise = requestBestPosition({ desiredAccuracy: 50, maxFixes: 1, timeoutMs: 1000 });
		watchCallback!({ coords: { latitude: NaN, longitude: 1, accuracy: 10 }, timestamp: 1 });
		watchCallback!(makePos(2, 3, 20));
		const res = await promise;
		expect(res).toEqual({ lat: 2, lng: 3, accuracy: 20, timestamp: 12345 });
	});

	it('maps permission denied error', async () => {
		const promise = requestBestPosition({ desiredAccuracy: 50, maxFixes: 3, timeoutMs: 1000 });
		errorCallback!({ code: 1, PERMISSION_DENIED: 1, TIMEOUT: 3 });
		await expect(promise).rejects.toMatchObject({ code: 'location_permission_denied' });
	});
});
describe('requestBestPosition edge cases', () => {
	let watchCallback: ((pos: any) => void) | null = null;
	let errorCallback: ((err: any) => void) | null = null;
	let clearWatch: ReturnType<typeof vi.fn>;
	let watchPosition: ReturnType<typeof vi.fn>;

	beforeEach(() => {
		watchCallback = null;
		errorCallback = null;
		clearWatch = vi.fn();
		watchPosition = vi.fn((success, error, _opts) => {
			watchCallback = success;
			errorCallback = error;
			return 1;
		});
		vi.stubGlobal('navigator', {
			geolocation: { watchPosition, clearWatch }
		} as any);
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllGlobals();
	});

	const makePos = (lat: number, lng: number, accuracy: number, timestamp?: number) => ({
		coords: { latitude: lat, longitude: lng, accuracy },
		timestamp: timestamp ?? 12345
	});

	it('ignores fixes with non-positive accuracy', async () => {
		const promise = requestBestPosition({ desiredAccuracy: 50, maxFixes: 2, timeoutMs: 1000 });
		watchCallback!(makePos(1, 2, 0));
		watchCallback!(makePos(3, 4, 20));
		const res = await promise;
		expect(res).toEqual({ lat: 3, lng: 4, accuracy: 20, timestamp: 12345 });
	});

	it('ignores fixes with out-of-range coords', async () => {
		const promise = requestBestPosition({ desiredAccuracy: 50, maxFixes: 2, timeoutMs: 1000 });
		watchCallback!({ coords: { latitude: 100, longitude: 1, accuracy: 10 }, timestamp: 1 });
		watchCallback!(makePos(3, 4, 20));
		const res = await promise;
		expect(res).toEqual({ lat: 3, lng: 4, accuracy: 20, timestamp: 12345 });
	});

	it('rejects with location_accuracy_too_low when maxAccuracy exceeded', async () => {
		const promise = requestBestPosition({ desiredAccuracy: 50, maxFixes: 1, timeoutMs: 1000, maxAccuracy: 10 });
		watchCallback!(makePos(1, 2, 20));
		await expect(promise).rejects.toMatchObject({ code: 'location_accuracy_too_low' });
	});

	it('maps permission denied', async () => {
		const promise = requestBestPosition({ desiredAccuracy: 50, maxFixes: 3, timeoutMs: 1000 });
		errorCallback!({ code: 1, PERMISSION_DENIED: 1, TIMEOUT: 3 });
		await expect(promise).rejects.toMatchObject({ code: 'location_permission_denied' });
	});

	it('times out with no fix', async () => {
		const promise = requestBestPosition({ desiredAccuracy: 50, maxFixes: 3, timeoutMs: 100 });
		vi.advanceTimersByTime(100);
		await expect(promise).rejects.toMatchObject({ code: 'location_timeout' });
	});

	it('clamps maxFixes < 1 to 1', async () => {
		const promise = requestBestPosition({ desiredAccuracy: 50, maxFixes: 0, timeoutMs: 1000 });
		watchCallback!(makePos(1, 2, 20));
		const res = await promise;
		expect(res).toEqual({ lat: 1, lng: 2, accuracy: 20, timestamp: 12345 });
	});

	it('clamps timeoutMs < 0 to 0', async () => {
		const promise = requestBestPosition({ desiredAccuracy: 50, maxFixes: 3, timeoutMs: -5 });
		// timeout 0 fires immediately
		vi.advanceTimersByTime(0);
		await expect(promise).rejects.toMatchObject({ code: 'location_timeout' });
	});

	it('ignores stale timestamp (>=1e12, >30s old)', async () => {
		const now = Date.now();
		const promise = requestBestPosition({ desiredAccuracy: 50, maxFixes: 2, timeoutMs: 1000 });
		watchCallback!(makePos(1, 2, 10, now - 60000));
		watchCallback!(makePos(3, 4, 20, now));
		const res = await promise;
		expect(res).toEqual({ lat: 3, lng: 4, accuracy: 20, timestamp: now });
	});
});

describe('requestBestPosition in-flight dedup', () => {
	let watchCallback: ((pos: any) => void) | null = null;
	let watchPosition: ReturnType<typeof vi.fn>;

	beforeEach(() => {
		watchCallback = null;
		watchPosition = vi.fn((success, _error, _opts) => {
			watchCallback = success;
			return 1;
		});
		vi.stubGlobal('navigator', {
			geolocation: { watchPosition, clearWatch: vi.fn() }
		} as any);
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllGlobals();
	});

	it('shares one watch across concurrent calls', async () => {
		const p1 = requestBestPosition({ desiredAccuracy: 50, maxFixes: 3, timeoutMs: 1000 });
		const p2 = requestBestPosition({ desiredAccuracy: 50, maxFixes: 3, timeoutMs: 1000 });
		expect(watchPosition).toHaveBeenCalledTimes(1);
		watchCallback!({ coords: { latitude: 1, longitude: 2, accuracy: 10 }, timestamp: 12345 });
		const [r1, r2] = await Promise.all([p1, p2]);
		expect(r1).toEqual(r2);
	});
});

describe('requestBestPosition fast first fix', () => {
	let watchCallback: ((pos: any) => void) | null = null;
	let errorCallback: ((err: any) => void) | null = null;
	let getCurrentPosition: ReturnType<typeof vi.fn>;
	let watchPosition: ReturnType<typeof vi.fn>;

	beforeEach(() => {
		watchCallback = null;
		errorCallback = null;
		getCurrentPosition = vi.fn();
		watchPosition = vi.fn((success, error, _opts) => {
			watchCallback = success;
			errorCallback = error;
			return 1;
		});
		vi.stubGlobal('navigator', {
			geolocation: { watchPosition, clearWatch: vi.fn(), getCurrentPosition }
		} as any);
	});

	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it('returns fast fix when good', async () => {
		getCurrentPosition.mockImplementation((success: any) => {
			success({ coords: { latitude: 1, longitude: 2, accuracy: 10 }, timestamp: Date.now() });
		});
		const res = await requestBestPosition({ desiredAccuracy: 50, maxFixes: 3, timeoutMs: 1000, fastTimeoutMs: 100 });
		expect(res).toMatchObject({ lat: 1, lng: 2, accuracy: 10 });
	});

	it('falls through on coarse fast fix', async () => {
		getCurrentPosition.mockImplementation((success: any) => {
			success({ coords: { latitude: 1, longitude: 2, accuracy: 200 }, timestamp: Date.now() });
		});
		const p = requestBestPosition({ desiredAccuracy: 50, maxFixes: 2, timeoutMs: 1000, fastTimeoutMs: 100 });
		await new Promise((r) => setTimeout(r, 0));
		await new Promise((r) => setTimeout(r, 0));
		watchCallback!({ coords: { latitude: 3, longitude: 4, accuracy: 40 }, timestamp: Date.now() });
		const res = await p;
		expect(res.accuracy).toBe(40);
	});

	it('propagates permission denied', async () => {
		getCurrentPosition.mockImplementation((_s: any, error: any) => {
			error({ code: 1, PERMISSION_DENIED: 1, TIMEOUT: 3 });
		});
		const p = requestBestPosition({ desiredAccuracy: 50, maxFixes: 3, timeoutMs: 1000, fastTimeoutMs: 100 });
		await expect(p).rejects.toMatchObject({ code: 'location_permission_denied' });
	});

	it('skips fast path when fastFirst is false', async () => {
		const p = requestBestPosition({ desiredAccuracy: 50, maxFixes: 1, timeoutMs: 1000, fastFirst: false });
		expect(getCurrentPosition).not.toHaveBeenCalled();
		watchCallback!({ coords: { latitude: 5, longitude: 6, accuracy: 20 }, timestamp: Date.now() });
		const res = await p;
		expect(res).toMatchObject({ lat: 5, lng: 6, accuracy: 20 });
	});

	it('shares one watch when getCurrentPosition absent', async () => {
		// remove getCurrentPosition
		const nav = (globalThis as any).navigator;
		delete nav.geolocation.getCurrentPosition;
		const p1 = requestBestPosition({ desiredAccuracy: 50, maxFixes: 3, timeoutMs: 1000 });
		const p2 = requestBestPosition({ desiredAccuracy: 50, maxFixes: 3, timeoutMs: 1000 });
		expect(watchPosition).toHaveBeenCalledTimes(1);
		watchCallback!({ coords: { latitude: 1, longitude: 2, accuracy: 10 }, timestamp: Date.now() });
		const [r1, r2] = await Promise.all([p1, p2]);
		expect(r1).toEqual(r2);
	});
});

describe('isWithinGeofenceWithUncertainty', () => {
	it('returns false for invalid inputs', () => {
		expect(isWithinGeofenceWithUncertainty(NaN, 0, 0, 0, 10, 5, 50)).toBe(false);
		expect(isWithinGeofenceWithUncertainty(0, 0, 0, 0, -1, 5, 50)).toBe(false);
	});
	it('blocks hard outside positions', () => {
		// ~111m away with 50m uncertainty -> 61m > 10m radius
		expect(isWithinGeofenceWithUncertainty(0, 0.001, 0, 0, 10, 50, 50)).toBe(false);
	});
	it('allows review-band positions within radius+uncertainty', () => {
		// ~55m away with 50m uncertainty -> 5m <= 10m radius
		expect(isWithinGeofenceWithUncertainty(0, 0.0005, 0, 0, 10, 50, 50)).toBe(true);
	});
	it('falls back to 50m cap for zero or negative cap', () => {
		expect(isWithinGeofenceWithUncertainty(0, 0.0005, 0, 0, 10, 50, 0)).toBe(true);
		expect(isWithinGeofenceWithUncertainty(0, 0.0005, 0, 0, 10, 50, -5)).toBe(true);
	});
});

describe('reverseGeocode', () => {
	let fetchMock: ReturnType<typeof vi.fn>;

	beforeEach(() => {
		fetchMock = vi.fn();
		vi.stubGlobal('fetch', fetchMock);
	});

	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it('returns null for invalid coordinates', async () => {
		expect(await reverseGeocode(NaN, 0)).toBeNull();
		expect(await reverseGeocode(0, 200)).toBeNull();
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('returns a label on success', async () => {
		fetchMock.mockResolvedValue({
			ok: true,
			json: async () => ({
				features: [{ properties: { name: 'Manila', city: 'Manila', country: 'PH' } }]
			})
		});
		const res = await reverseGeocode(14.5, 121.0);
		expect(res).toBe('Manila, Manila, PH');
	});

	it('falls back to coords when no label parts', async () => {
		fetchMock.mockResolvedValue({
			ok: true,
			json: async () => ({ features: [{ properties: {} }] })
		});
		const res = await reverseGeocode(14.5, 121.0);
		expect(res).toBe('14.5000, 121.0000');
	});

	it('returns null on empty features', async () => {
		fetchMock.mockResolvedValue({ ok: true, json: async () => ({ features: [] }) });
		expect(await reverseGeocode(14.5, 121.0)).toBeNull();
	});

	it('returns null on non-ok response', async () => {
		fetchMock.mockResolvedValue({ ok: false, json: async () => ({}) });
		expect(await reverseGeocode(14.5, 121.0)).toBeNull();
	});

	it('returns null on fetch failure', async () => {
		fetchMock.mockRejectedValue(new Error('network'));
		expect(await reverseGeocode(14.5, 121.0)).toBeNull();
	});
});
