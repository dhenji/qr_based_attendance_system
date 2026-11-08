import { describe, it, expect, vi, beforeEach } from 'vitest';
import { acquireGpsFix } from './gps';
import { requestBestPosition } from '$lib/shared/utils/geo';
import type { SessionVerification } from './service';

vi.mock('$lib/shared/utils/geo', () => ({
	requestBestPosition: vi.fn(),
	calculateDistanceMeters: vi.fn(() => 42)
}));

const makeSession = (geofence: { lat: number | null; lng: number | null; radius: number } | null = { lat: 10, lng: 20, radius: 50 }): SessionVerification =>
	({
		sessionId: 1,
		courseCode: 'CS101',
		courseName: 'Intro',
		expiresAt: '2026-01-01T00:00:00Z',
		geofence: geofence
			? { ...geofence, uncertaintyCapMeters: 50, gpsHardFloorMeters: 1000, gpsReviewAccuracyThreshold: 100 }
			: { lat: null, lng: null, radius: 0, uncertaintyCapMeters: 50, gpsHardFloorMeters: 1000, gpsReviewAccuracyThreshold: 100 },
		geofenceEnabled: true
	}) as SessionVerification;

describe('acquireGpsFix', () => {
	beforeEach(() => {
		vi.mocked(requestBestPosition).mockReset();
	});

	it('returns high status for accurate fix', async () => {
		vi.mocked(requestBestPosition).mockResolvedValue({ lat: 1, lng: 2, accuracy: 30, timestamp: 1 });
		const res = await acquireGpsFix(makeSession());
		expect(res.status).toBe('high');
		expect(res.fix).toMatchObject({ lat: 1, lng: 2, accuracy: 30 });
		expect(res.distanceMeters).toBe(42);
	});

	it('returns moderate status for 80m fix', async () => {
		vi.mocked(requestBestPosition).mockResolvedValue({ lat: 1, lng: 2, accuracy: 80, timestamp: 1 });
		const res = await acquireGpsFix(makeSession());
		expect(res.status).toBe('moderate');
	});

	it('returns low status for 150m fix', async () => {
		vi.mocked(requestBestPosition).mockResolvedValue({ lat: 1, lng: 2, accuracy: 150, timestamp: 1 });
		const res = await acquireGpsFix(makeSession());
		expect(res.status).toBe('low');
	});

	it('returns null distance when geofence has no center', async () => {
		vi.mocked(requestBestPosition).mockResolvedValue({ lat: 1, lng: 2, accuracy: 30, timestamp: 1 });
		const res = await acquireGpsFix(makeSession({ lat: null, lng: null, radius: 50 }));
		expect(res.distanceMeters).toBeNull();
	});

	it('propagates permission denied', async () => {
		const err = new Error('denied');
		(err as any).code = 'location_permission_denied';
		vi.mocked(requestBestPosition).mockRejectedValue(err);
		await expect(acquireGpsFix(makeSession())).rejects.toBe(err);
	});

	it('passes signal through', async () => {
		vi.mocked(requestBestPosition).mockResolvedValue({ lat: 1, lng: 2, accuracy: 30, timestamp: 1 });
		const controller = new AbortController();
		await acquireGpsFix(makeSession(), controller.signal);
		expect(requestBestPosition).toHaveBeenCalledWith(expect.objectContaining({ signal: controller.signal }));
	});
});