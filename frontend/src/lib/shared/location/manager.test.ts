import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { acquire, validateGeofence, queryPermissionStatus } from './manager';
import { requestBestPosition } from '$lib/shared/utils/geo';

vi.mock('$lib/shared/utils/geo', () => ({
	requestBestPosition: vi.fn(),
	isWithinGeofence: vi.fn(() => true),
	isWithinGeofenceWithUncertainty: vi.fn(() => true),
}));

describe('manager.acquire', () => {
	beforeEach(() => {
		vi.mocked(requestBestPosition).mockReset();
	});

	it('returns a populated LocationState on success', async () => {
		vi.mocked(requestBestPosition).mockResolvedValue({ lat: 1, lng: 2, accuracy: 30, timestamp: 123 });
		const state = await acquire({ timeoutMs: 100 });
		expect(state.latitude).toBe(1);
		expect(state.longitude).toBe(2);
		expect(state.accuracy).toBe(30);
		expect(state.error).toBeNull();
		expect(state.source).toBe('gps');
		expect(state.loading).toBe(false);
	});

	it('returns an error state on failure', async () => {
		const err = new Error('boom');
		(err as any).code = 'location_timeout';
		vi.mocked(requestBestPosition).mockRejectedValue(err);
		const state = await acquire({ timeoutMs: 100 });
		expect(state.latitude).toBeNull();
		expect(state.error?.code).toBe('location_timeout');
		expect(state.loading).toBe(false);
	});

	it('passes signal through', async () => {
		vi.mocked(requestBestPosition).mockResolvedValue({ lat: 1, lng: 2, accuracy: 30, timestamp: 1 });
		const controller = new AbortController();
		await acquire({ signal: controller.signal });
		expect(requestBestPosition).toHaveBeenCalledWith(expect.objectContaining({ signal: controller.signal }));
	});
});

describe('manager.validateGeofence', () => {
	it('returns hard_floor when accuracy exceeds floor', () => {
		const r = validateGeofence({ lat: 0, lng: 0, accuracy: 2000 }, { lat: 0, lng: 0, radius: 50 }, 50, 1000);
		expect(r.reason).toBe('hard_floor');
		expect(r.ok).toBe(false);
	});

	it('returns ok when inside radius', () => {
		const r = validateGeofence({ lat: 0, lng: 0, accuracy: 10 }, { lat: 0, lng: 0, radius: 50 }, 50, 1000);
		expect(r.reason).toBe('ok');
		expect(r.ok).toBe(true);
	});
});

describe('manager.queryPermissionStatus', () => {
	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it('returns unsupported when permissions API is missing', async () => {
		vi.stubGlobal('navigator', {} as any);
		expect(await queryPermissionStatus()).toBe('unsupported');
	});
});