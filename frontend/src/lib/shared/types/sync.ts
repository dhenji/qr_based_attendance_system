// sync.ts
// Offline queue entry (docs/architecture/offline-first.md).
//
// NOTE: The authoritative queue row type lives in
// `$lib/features/sync/service.ts` (`QueuedScan`). This shared alias is kept
// for documentation/typing convenience and must stay in sync with that shape.
export interface SyncQueueRecord {
	id: string;
	type: 'attendance_scan' | 'excuse_request' | 'face_enrollment';
	status: 'pending' | 'syncing' | 'synced' | 'rejected';
	payload: unknown;
	createdAt: string;
	updatedAt: string;
	attempts: number;
	maxAttempts: number;
	lastError: string | null;
}