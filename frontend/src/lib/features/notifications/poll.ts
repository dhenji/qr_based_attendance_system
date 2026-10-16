// features/notifications/poll.ts
// Layout badge polling (frontend-only, no push server).
//
// Student bell: count of reviewed excuse requests newer than the last-seen
// timestamp in localStorage. Professor bell: pending-queue total. Both poll on
// mount, every POLL_INTERVAL_MS, and on window focus/visibility — all
// fail-soft (mock mode, offline, and 401s hide the badge, never an error).
// Closed-app delivery is impossible without backend VAPID keys + a
// subscription store, so the copy never promises it.

import { browser } from '$app/environment';
import { isMockMode } from '$lib/api/client';
import { listExcuseRequests } from '$lib/features/excuse/service';
import { getPrefs } from '$lib/features/settings/service';
import { listStudentExcuses } from '$lib/features/student/service';

export const POLL_INTERVAL_MS = 60_000;

// Bell preview truncation, shared so the student/professor/admin layouts can
// never drift apart (previously the same 60-char slice lived in 3 files).
export const NOTIF_PREVIEW_MAX_LENGTH = 60;

export const truncateNotifPreview = (reason: string, max: number = NOTIF_PREVIEW_MAX_LENGTH): string =>
	reason.length > max ? `${reason.slice(0, max)}…` : reason;

const STUDENT_SEEN_KEY = 'notif_student_excuse_seen';

const readSeen = (): string | null => {
	if (!browser) return null;
	try {
		return localStorage.getItem(STUDENT_SEEN_KEY);
	} catch {
		return null;
	}
};

export const markStudentSeen = (): void => {
	if (!browser) return;
	try {
		localStorage.setItem(STUDENT_SEEN_KEY, new Date().toISOString());
	} catch {
		// Storage unavailable (private mode): badge just recomputes next load.
	}
};

// getStudentUpdateCount
// Reviewed (approved/rejected) rows with reviewed_at newer than last-seen.
// First run seeds last-seen to now and reports 0, so history never badges.
export const getStudentUpdateCount = async (): Promise<number> => {
	if (!browser || isMockMode()) return 0;
	try {
		const { items } = await listStudentExcuses({ page: 1, size: 20 });
		let seen = readSeen();
		if (!seen) {
			markStudentSeen();
			return 0;
		}
		let count = 0;
		for (const row of items) {
			if (row.status === 'pending') continue;
			if (row.reviewedAt && row.reviewedAt > seen) count += 1;
		}
		return count;
	} catch {
		return 0;
	}
};

// getProfessorPendingCount
// Live pending-queue total (size=1 keeps it cheap). Fail-soft to 0.
export const getProfessorPendingCount = async (): Promise<number> => {
	if (!browser || isMockMode()) return 0;
	try {
		const result = await listExcuseRequests({ status: 'pending', page: 1, size: 1 });
		return result.total ?? 0;
	} catch {
		return 0;
	}
};

// maybeNotify
// Best-effort OS toast on a newly-detected edge. Only fires when the user
// opted into push in settings AND already granted permission — this never
// requests permission on its own (the settings toggle does that). Returns
// whether the toast was shown. No backend, no service-worker push.
export const maybeNotify = (title: string, body: string): boolean => {
	try {
		if (!browser || !getPrefs().pushNotifications) return false;
		if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return false;
		new Notification(title, { body });
		return true;
	} catch {
		return false;
	}
};

// requestNotificationPermission
// Called from the settings push toggle: opting in requests OS permission so
// a later poll edge can toast; opting out leaves the permission as-is.
export const requestNotificationPermission = async (): Promise<NotificationPermission | null> => {
	try {
		if (!browser || typeof Notification === 'undefined') return null;
		if (Notification.permission === 'granted' || Notification.permission === 'denied') {
			return Notification.permission;
		}
		return await Notification.requestPermission();
	} catch {
		return null;
	}
};
