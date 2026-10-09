// features/student/store.svelte.ts
// Student dashboard + scan state using Svelte 5 runes ($state object store)

import type { LivenessEvidence, ScheduledClass, Student, StudentDashboardResponse } from '$lib/shared/types';
import {
	getProfile,
	updateProfile,
	getSchedule,
	getSessionHistory,
	getDashboard,
	submitScan,
	type StudentHistoryRow,
} from '$lib/features/student/service';
import { me } from '$lib/features/auth/service';

// Student state
export type SessionHistoryItem = {
	id: number;
	sessionId?: number;
	courseId?: number;
	code: string;
	courseName: string;
	status: 'present' | 'late' | 'absent' | 'excused' | 'pending' | 'rejected';
	originalStatus?: string;
	excuseReason?: string;
	scannedAt: string;
	scannedVia: 'qr' | 'manual';
};

const toStoreItem = (row: StudentHistoryRow): SessionHistoryItem => ({
	id: row.id,
	sessionId: row.sessionId,
	code: row.courseCode,
	courseName: row.courseName,
	status: row.status,
	originalStatus: row.originalStatus,
	excuseReason: row.excuseReason,
	scannedAt: row.scannedAt,
	scannedVia: row.scannedVia === 'manual' ? 'manual' : 'qr',
});

const EMPTY_DASHBOARD: StudentDashboardResponse = {
	compliance_rate: 0,
	scans_today: 0,
	total_scans: 0,
	today_schedule: [],
	recent_activity: [],
};

// Student state
// Profile + dashboard + schedule + session history in one reactive object.
// Renders the dashboard and backs the scan flow.
export const studentState = $state({
	student: null as Student | null,
	dashboard: { ...EMPTY_DASHBOARD } as StudentDashboardResponse,
	courses: [] as ScheduledClass[],
	history: [] as SessionHistoryItem[],
	loading: false,
	error: null as string | null,
	scanLoading: false,
});

// Derived stats
// Read-only helpers for the dashboard UI (module-scope $derived can't be
// exported, hence functions reading studentState).
//
// The compliance rate comes from GET /student/dashboard, which computes it as
// present / total_expected_sessions. An empty dashboard has no data yet, so
// `hasData` distinguishes "0%" from "nothing to report".
export const hasDashboardData = () => studentState.dashboard.total_scans > 0;
// The dashboard's compliance_rate is a 0-1 fraction (backend `_history_rates`
// does round(present/enrolled, 4)), so it has to be scaled before display. This
// previously omitted the *100, and Math.round(0.85) === 1 meant the student's
// headline Attendance Rate always read "0%" or "1%".
export const complianceRate = () => Math.round(studentState.dashboard.compliance_rate * 100);
export const scansToday = () => studentState.dashboard.scans_today;
export const totalScans = () => studentState.dashboard.total_scans;
export const isLoading = () => studentState.loading || studentState.scanLoading;

const toMessage = (e: unknown, fallback: string) =>
	e instanceof Error && e.message ? e.message : fallback;

// init
// One-shot bootstrap: loads the profile, dashboard summary, schedule, and
// history into state. Each leg is independent — a single failure never blanks
// the page. Profile falls back to GET /auth/me; dashboard falls back to
// EMPTY_DASHBOARD. studentState.error is set only when every leg fails.
export const initStudent = async (): Promise<void> => {
	studentState.loading = true;
	studentState.error = null;
	let failures = 0;
	try {
		const [profileRes, dashboardRes] = await Promise.allSettled([getProfile(), getDashboard()]);

		if (profileRes.status === 'fulfilled' && profileRes.value) {
			studentState.student = profileRes.value;
		} else {
			failures += 1;
			try {
				const identity = await me();
				if (identity && identity.role === 'student') {
					studentState.student = {
						id: identity.email,
						userId: String(identity.id),
						studentNumber: '',
						email: identity.email,
						firstName: identity.first_name ?? 'Student',
						lastName: identity.last_name ?? '',
						programCode: '',
						yearLevelLabel: '',
						faceEnrolled: identity.face_enrolled ?? false,
						faceEnrolledAt: identity.face_enrolled_at ?? undefined,
						faceEmbeddingVersion: identity.face_embedding_version ?? undefined,
						isActive: true,
					};
				} else if (identity) {
					studentState.student = {
						id: identity.email,
						userId: String(identity.id),
						studentNumber: '',
						email: identity.email,
						firstName: identity.first_name ?? 'Student',
						lastName: identity.last_name ?? '',
						programCode: '',
						yearLevelLabel: '',
						faceEnrolled: false,
						isActive: true,
					};
				} else {
					studentState.student = null;
				}
			} catch {
				studentState.student = null;
			}
		}

		if (dashboardRes.status === 'fulfilled' && dashboardRes.value) {
			studentState.dashboard = dashboardRes.value;
		} else {
			failures += 1;
			studentState.dashboard = { ...EMPTY_DASHBOARD };
		}

		try {
			studentState.courses = await getSchedule();
		} catch {
			failures += 1;
			studentState.courses = [];
		}

		try {
			const res = await getSessionHistory({ page: 1, size: 20 });
			studentState.history = res.items.map(toStoreItem);
		} catch {
			failures += 1;
			studentState.history = [];
		}

		if (failures >= 4 && !studentState.student) {
			studentState.error = 'Failed to load student data';
		}
	} catch (e: unknown) {
		studentState.error = toMessage(e, 'Failed to load student data');
	} finally {
		studentState.loading = false;
	}
};

// Actions
// doUpdateProfile: profile is read-only (D32) — never wipes local state.
// updateProfile throws, so a failed edit preserves the current student.
export const doUpdateProfile = async (updates: Partial<Student>): Promise<void> => {
	studentState.loading = true;
	studentState.error = null;
	try {
		const next = await updateProfile(updates);
		if (next) studentState.student = next;
		else studentState.error = 'Student profile is read-only.';
	} catch (e: unknown) {
		studentState.error = toMessage(e, 'Student profile is read-only.');
	} finally {
		studentState.loading = false;
	}
};

// doSubmitScan: submits via the single live scan path (student/service.ts
// delegates to liveness/service.ts in real mode), then refreshes history so
// the dashboard stays in sync with the latest records.
export const doSubmitScan = async (scanData: {
	sessionId: number;
	qrStudentNumber: string;
	gps: { lat: number; lng: number; accuracy: number };
	livenessEvidence: LivenessEvidence;
	faceMatchScore: number;
	scannedAt: string;
}) => {
	studentState.scanLoading = true;
	studentState.error = null;
	try {
		const result = await submitScan(scanData);
		try {
			const res = await getSessionHistory({ page: 1, size: 20 });
			studentState.history = res.items.map(toStoreItem);
		} catch {
			// Scan succeeded; history refresh is best-effort.
		}
		return result;
	} catch (e: unknown) {
		studentState.error = toMessage(e, 'Scan failed');
		throw e;
	} finally {
		studentState.scanLoading = false;
	}
};
