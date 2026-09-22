// features/sync/service.ts
// IndexedDB offline queue

import type { SyncQueueRecord } from '$lib/shared/types';

// MOCK flag — swap to false when IndexedDB sync (docs/architecture/offline-first.md) is implemented
const MOCK = true;

// queue
// Offline sync queue stored in IndexedDB. Every method returns mock data while
// MOCK is true, and is a no-op/placeholder once the real IndexedDB wrapper lands.
export const queue = {
	// Enqueue a record for offline sync
	enqueue: async (
		record: Omit<SyncQueueRecord, 'id' | 'createdAt' | 'attempts' | 'maxAttempts'>
	) => {
		if (MOCK) {
			const id = Math.random().toString(36).substring(2, 15);
			return {
				id,
				type: record.type,
				status: 'pending' as const,
				payload: record.payload,
				createdAt: new Date().toISOString(),
				attempts: 0,
				maxAttempts: 3,
			};
		}
		return {
			id: Math.random().toString(36).substring(2, 15),
			type: record.type,
			status: 'pending' as const,
			payload: record.payload,
			createdAt: new Date().toISOString(),
			attempts: 0,
			maxAttempts: 3,
		};
	},

	// Dequeue next record
	dequeue: async () => {
		if (MOCK) {
			return {
				id: Math.random().toString(36).substring(2, 15),
				type: 'attendance_scan' as const,
				status: 'synced' as const,
				payload: {},
				createdAt: new Date(Date.now() - 3600000).toISOString(),
				attempts: 1,
				maxAttempts: 3,
			};
		}
		return null;
	},

	// Update record status
	updateStatus: async (_id: string, _status: SyncQueueRecord['status']) => {
		if (MOCK) {
			return;
		}
		return;
	},

	// Get all pending records
	getPending: async () => {
		if (MOCK) {
			return [
				{
					id: 'rec-1',
					type: 'attendance_scan' as const,
					status: 'pending' as const,
					payload: { sessionId: 1, studentId: 'student-1' },
					createdAt: new Date(Date.now() - 3600000).toISOString(),
					attempts: 1,
					maxAttempts: 3,
				},
			];
		}
		return [];
	},
};
