// features/student/store.svelte.ts
// Student dashboard + scan state using Svelte 5 runes ($state object store)

import type { Student, Course } from '$lib/shared/types';
import {
	getProfile,
	updateProfile,
	getSchedule,
	getSessionHistory,
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

export const studentState = $state({
	student: null as Student | null,
	courses: [] as Course[],
	history: [] as SessionHistoryItem[],
	loading: false,
	error: null as string | null,
	scanLoading: false,
});

// Derived (functions — module-scope $derived cannot be exported)
export const complianceRate = () =>
	studentState.student ? Math.round((studentState.student as Record<string, number> & Student).attendanceRate ?? 0) : 0;
export const participationRate = () =>
	studentState.student ? Math.round((studentState.student as Record<string, number> & Student).participationRate ?? 0) : 0;
export const isLoading = () => studentState.loading || studentState.scanLoading;

// Initialize on first load
export const initStudent = async (): Promise<void> => {
	studentState.loading = true;
	studentState.error = null;
	try {
		studentState.student = await getProfile();
		studentState.courses = await getSchedule();
		const res = await getSessionHistory();
		studentState.history = res.items;
	} catch (e: unknown) {
		studentState.error = e instanceof Error ? e.message : 'Failed to load student data';
	} finally {
		studentState.loading = false;
	}
};

// Actions
export const doUpdateProfile = async (updates: Partial<Student>): Promise<void> => {
	studentState.loading = true;
	studentState.error = null;
	try {
		studentState.student = await updateProfile(updates);
	} catch (e: unknown) {
		studentState.error = e instanceof Error ? e.message : 'Failed to update profile';
	} finally {
		studentState.loading = false;
	}
};

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
		studentState.history = res.items;
		return result;
	} catch (e: unknown) {
		studentState.error = e instanceof Error ? e.message : 'Scan failed';
		throw e;
	} finally {
		studentState.scanLoading = false;
	}
};
