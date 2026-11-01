import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
	clamp,
	clampRadius,
	getAccuracyStatus,
	isLowAccuracy,
	calculateDistanceMeters,
	isWithinGeofence,
	searchLocation
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