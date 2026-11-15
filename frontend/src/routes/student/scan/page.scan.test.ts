import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';

vi.mock('$app/navigation', () => ({
	goto: vi.fn()
}));

vi.mock('$app/state', () => ({
	page: {
		url: new URL('http://localhost/student/scan')
	}
}));

vi.mock('$lib/features/liveness/model', () => ({
	initFaceModel: vi.fn().mockResolvedValue(undefined)
}));

vi.mock('$lib/features/liveness/service', () => ({
	precheckScan: vi.fn(),
	submitAttendanceScan: vi.fn(),
	verifySessionCode: vi.fn()
}));

vi.mock('$lib/features/sync/service', () => ({
	cacheSession: vi.fn().mockResolvedValue(undefined),
	flushQueue: vi.fn().mockResolvedValue({ failed: 0 }),
	getCachedSession: vi.fn().mockResolvedValue(null),
	newQueueId: vi.fn(() => 'queue-id'),
	queue: {
		getPendingCount: vi.fn().mockResolvedValue(0),
		getRejected: vi.fn().mockResolvedValue([]),
		getPending: vi.fn().mockResolvedValue([]),
		enqueue: vi.fn().mockResolvedValue(undefined),
		updateStatus: vi.fn().mockResolvedValue(undefined),
		remove: vi.fn().mockResolvedValue(undefined)
	},
	registerOutboxSync: vi.fn().mockResolvedValue(undefined),
	retryDelayMs: vi.fn(() => 1000)
}));

vi.mock('$lib/features/student/store.svelte', () => ({
	initStudent: vi.fn().mockResolvedValue(undefined),
	studentState: {
		student: { firstName: 'Test', studentNumber: 'S1', faceEnrolled: true },
		loading: false
	}
}));

vi.mock('$lib/api/client', async () => {
	const actual = await vi.importActual<typeof import('$lib/api/client')>('$lib/api/client');
	return {
		...actual,
		isMockMode: vi.fn(() => false)
	};
});

vi.mock('$lib/features/liveness/gps', () => ({
	acquireGpsFix: vi.fn()
}));

vi.mock('$lib/shared/location/manager', () => ({
	queryPermissionStatus: vi.fn().mockResolvedValue('granted')
}));

vi.mock('$lib/shared/utils/face-embedding', () => ({
	generateEmbeddingFromLandmarks: vi.fn(),
	serializeFaceEmbedding: vi.fn()
}));

vi.mock('$lib/shared/utils/geo', async () => {
	const actual = await vi.importActual<typeof import('$lib/shared/utils/geo')>('$lib/shared/utils/geo');
	return {
		...actual
	};
});

vi.mock('$lib/features/liveness/components/QRScanner.svelte', async () => ({
	default: (await import('../../../testing/ModalWrapper.svelte')).default
}));

vi.mock('$lib/features/liveness/components/FaceScanner.svelte', async () => ({
	default: (await import('../../../testing/ModalWrapper.svelte')).default
}));

import { goto } from '$app/navigation';
import { APIError } from '$lib/api/client';
import { precheckScan, verifySessionCode } from '$lib/features/liveness/service';
import { Routes } from '$lib/shared/constants/routes';
import Page from './+page.svelte';

const flushAsync = async () => {
	await Promise.resolve();
	await Promise.resolve();
	await tick();
};

const sessionFixture = {
	sessionId: 42,
	courseCode: 'CS101',
	courseName: 'Intro to Testing',
	expiresAt: '2099-01-01T10:00:00Z',
	scheduledStartTime: '2099-01-01T09:00:00Z',
	scheduledEndTime: '2099-01-01T10:00:00Z',
	sessionType: 'lecture' as const,
	classroomName: 'Room 1',
	geofence: {
		radius: 50,
		lat: null,
		lng: null,
		uncertaintyCapMeters: 50,
		gpsHardFloorMeters: 1000,
		gpsReviewAccuracyThreshold: 100
	},
	geofenceEnabled: false,
	isRemote: true
};

const exhaustedPrecheck = {
	enrolled: true,
	alreadyScanned: false,
	retakeAvailable: false,
	attendanceAttemptLimit: 3,
	attemptsUsed: 3,
	attemptsRemaining: 0,
	limitReached: true,
	studentId: 'S1',
	studentName: 'Test Student',
	section: 'A'
};

const driveToConfirm = async () => {
	render(Page);
	await flushAsync();

	await fireEvent.input(screen.getByLabelText('Session code'), {
		target: { value: 'ABC123' }
	});
	await fireEvent.click(screen.getByRole('button', { name: 'Verify Code' }));
	await flushAsync();

	expect(screen.getByRole('heading', { name: 'Session Confirmation' })).toBeInTheDocument();
};

const triggerExhaustedPrecheck = async () => {
	await fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
	await flushAsync();
};

describe('student scan page', () => {
	beforeEach(() => {
		Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
		Object.defineProperty(navigator, 'serviceWorker', {
			value: {
				addEventListener: vi.fn(),
				removeEventListener: vi.fn()
			},
			configurable: true
		});
		vi.mocked(verifySessionCode).mockResolvedValue(sessionFixture);
		vi.mocked(precheckScan).mockResolvedValue(exhaustedPrecheck);
	});

	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
		vi.useRealTimers();
	});

	it('mounts and unmounts without throwing (lifecycle smoke test)', async () => {
		const { unmount } = render(Page);
		await flushAsync();
		expect(() => unmount()).not.toThrow();
	});

	it('shows precheck exhaustion message with zero remaining attempts and redirects after timeout while mounted', async () => {
		vi.useFakeTimers();
		await driveToConfirm();
		await triggerExhaustedPrecheck();

		expect(screen.getByText(/0 attempts remaining/i)).toBeInTheDocument();
		expect(vi.mocked(goto)).not.toHaveBeenCalled();

		await vi.advanceTimersByTimeAsync(2500);
		await flushAsync();

		expect(vi.mocked(goto)).toHaveBeenCalledWith(Routes.DASHBOARD);
	});

	it('clears the exhaustion redirect timer on unmount (no delayed navigation)', async () => {
		vi.useFakeTimers();
		await driveToConfirm();
		await triggerExhaustedPrecheck();

		expect(screen.getByText(/0 attempts remaining/i)).toBeInTheDocument();

		cleanup();
		await vi.advanceTimersByTimeAsync(5000);
		await flushAsync();

		expect(vi.mocked(goto)).not.toHaveBeenCalled();
	});

	it('shows the authoritative attempt count on the confirm screen from the verify response', async () => {
		// Option A contract: verify-code carries the caller's attempt state,
		// so the confirm screen is accurate before precheck re-reads it.
		vi.mocked(verifySessionCode).mockResolvedValue({
			...sessionFixture,
			attendanceAttemptLimit: 3,
			attemptsUsed: 1,
			attemptsRemaining: 2,
			limitReached: false
		});
		await driveToConfirm();

		expect(screen.getByText('2 of 3')).toBeInTheDocument();
	});

	it('reports unlimited attempts when the verify response carries a zero cap', async () => {
		vi.mocked(verifySessionCode).mockResolvedValue({
			...sessionFixture,
			attendanceAttemptLimit: 0,
			attemptsUsed: null,
			attemptsRemaining: null,
			limitReached: false
		});
		await driveToConfirm();

		expect(screen.getByText('Unlimited')).toBeInTheDocument();
	});

	it('shows zero remaining on verify-code exhaustion without the redirect banner', async () => {
		// verify_code only reads the counter (consumed=false), so the
		// remaining count is genuinely 0; the inline scanError shows it and
		// no exhaustion redirect timer starts.
		vi.mocked(verifySessionCode).mockRejectedValue(
			new APIError(
				'attendance_attempt_limit_reached',
				'Maximum of 3 attendance attempts reached for this session (0 attempts remaining)',
				undefined,
				409,
				{
					attempt_limit: 3,
					attempts_used: 5,
					attempts_remaining: 0,
					attempt_consumed: false
				}
			)
		);
		render(Page);
		await flushAsync();

		await fireEvent.input(screen.getByLabelText('Session code'), {
			target: { value: 'ABC123' }
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Verify Code' }));
		await flushAsync();

		expect(screen.getByText(/0 attempts remaining/i)).toBeInTheDocument();
		expect(vi.mocked(goto)).not.toHaveBeenCalled();
	});
});
