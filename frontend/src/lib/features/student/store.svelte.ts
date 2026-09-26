// features/student/store.svelte.ts
// Student dashboard + scan state using Svelte 5 runes ($state object store)

import type { Course, Student, StudentDashboardResponse } from '$lib/shared/types';
import {
	getProfile,
	updateProfile,
	getSchedule,
	getSessionHistory,
	getDashboard,
	submitScan,
} from '$lib/features/student/service';

// Student state
export type SessionHistoryItem = {
	id: number;
	courseId: number;
	code: string;
	courseName: string;
	status: 'present' | 'late' | 'absent' | 'excused' | 'rejected';
	originalStatus?: string;
	excuseReason?: string;
	scannedAt: string;
	scannedVia: 'qr' | 'manual';
};

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
	courses: [] as Course[],
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
export const complianceRate = () => Math.round(studentState.dashboard.compliance_rate);
export const scansToday = () => studentState.dashboard.scans_today;
export const totalScans = () => studentState.dashboard.total_scans;
export const isLoading = () => studentState.loading || studentState.scanLoading;

const toMessage = (e: unknown, fallback: string) =>
	e instanceof Error && e.message ? e.message : fallback;

// init
// One-shot bootstrap: loads the profile, dashboard summary, schedule, and
// history into state. The profile and dashboard run together; schedule and
// history are still empty placeholders.
export const initStudent = async (): Promise<void> => {
	studentState.loading = true;
	studentState.error = null;
	try {
		const [profile, dashboard] = await Promise.all([getProfile(), getDashboard()]);
		studentState.student = profile;
		studentState.dashboard = dashboard;
		studentState.courses = await getSchedule();
		const res = await getSessionHistory();
		studentState.history = res.items as SessionHistoryItem[];
	} catch (e: unknown) {
		studentState.error = toMessage(e, 'Failed to load student data');
	} finally {
		studentState.loading = false;
	}
};

// Actions
// doUpdateProfile: apply partial profile edits and reflect them in state.
export const doUpdateProfile = async (updates: Partial<Student>): Promise<void> => {
	studentState.loading = true;
	studentState.error = null;
	try {
		studentState.student = await updateProfile(updates);
	} catch (e: unknown) {
		studentState.error = toMessage(e, 'Failed to update profile');
	} finally {
		studentState.loading = false;
	}
};

// doSubmitScan: submits a scan, then refreshes history so the dashboard is in
// sync with the latest records.
export const doSubmitScan = async (scanData: {
	sessionId: number;
	qrStudentNumber: string;
	gps: { lat: number; lng: number; accuracy: number };
	livenessEvidence: {
		blinkDetected: boolean;
		headTurnLeft: boolean;
		headTurnRight: boolean;
		earSamples: number[];
		pnpEvidence: object;
	};
	faceMatchScore: number;
	scannedAt: string;
}) => {
	studentState.scanLoading = true;
	studentState.error = null;
	try {
		const result = await submitScan(scanData);
		const res = await getSessionHistory();
		studentState.history = res.items as SessionHistoryItem[];
		return result;
	} catch (e: unknown) {
		studentState.error = toMessage(e, 'Scan failed');
		throw e;
	} finally {
		studentState.scanLoading = false;
	}
};
