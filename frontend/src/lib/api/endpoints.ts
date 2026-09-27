// api/endpoints.ts
// Typed endpoint map mirroring backend API contracts
// (from docs/architecture/api-contracts.md)
//
// Urls are relative to /api — the api client prepends that prefix. `mock` is
// optional and only consulted when PUBLIC_MOCK_MODE=true.

import type {
	MeResponse,
	TokenResponse,
} from '$lib/shared/types';
import type {
	StudentDashboardResponse,
	StudentProfileResponse,
} from '$lib/shared/types';

export type ScanStatus = 'present' | 'late' | 'rejected';

export interface SessionVerificationResponse {
	session_id: number;
	offering_id: number;
	course_code: string;
	course_name: string;
	program_code: string;
	year_level_label: string;
	expires_at: string;
	scheduled_end_time: string;
	geofence: { radius: number; lat: number; lng: number };
	present_window_minutes: number;
	late_window_minutes: number;
}

export interface AttendanceScanResponse {
	id: number;
	status: ScanStatus;
	scanned_at: string;
	expires_at: string;
}

// Shared shape for the paginated collection endpoints.
export interface Paginated<T> {
	items: T[];
	total: number;
	page: number;
	size: number;
}

export interface EndpointDef<T> {
	url: string;
	method: 'GET' | 'POST' | 'PUT' | 'DELETE';
	mock?: () => T;
}

// Session QR payload (D18)
export const SessionQREndpoint: EndpointDef<SessionVerificationResponse> = {
	url: '/student/sessions/verify-code',
	method: 'POST',
	mock: () => ({
		session_id: 1,
		offering_id: 1,
		course_code: 'CS101',
		course_name: 'Software Engineering 1',
		program_code: 'BSCS',
		year_level_label: 'Year 1',
		expires_at: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
		scheduled_end_time: new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString(),
		geofence: {
			radius: 50,
			lat: 13.7563,
			lng: 100.5018,
		},
		present_window_minutes: 15,
		late_window_minutes: 5,
	}),
};

// Attendance scan (D18)
export const AttendanceScanEndpoint: EndpointDef<AttendanceScanResponse> = {
	url: '/student/attendance/scan',
	method: 'POST',
	mock: () => ({
		id: 1,
		status: 'present',
		scanned_at: new Date().toISOString(),
		expires_at: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
	}),
};

// Session CRUD (professor)
export const SessionListEndpoint: EndpointDef<Paginated<unknown>> = {
	url: '/professor/sessions',
	method: 'GET',
	mock: () => ({
		items: [],
		total: 0,
		page: 1,
		size: 20,
	}),
};

export const SessionCreateEndpoint: EndpointDef<{
	id: number;
	course_id: number;
	code: string;
	qr_payload: { v: number; code: string; course: number; radius: number; pw: number; lw: number };
	expires_at: string;
	scheduled_end_time: string;
}> = {
	url: '/professor/sessions',
	method: 'POST',
	mock: () => ({
		id: Math.floor(Math.random() * 1000) + 1,
		course_id: 1,
		code: `SESSION-${Math.random().toString(36).substring(2, 6).toUpperCase()}`,
		qr_payload: {
			v: 1,
			code: `A${Math.random().toString(36).substring(2, 4).toUpperCase()}-${Math.random().toString(36).substring(2, 4).toUpperCase()}`,
			course: 1,
			radius: 50,
			pw: 15,
			lw: 5,
		},
		expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
		scheduled_end_time: new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString(),
	}),
};

// Session history (professor) — wireframe 3.5, GET /professor/sessions/history
export const SessionHistoryEndpoint: EndpointDef<Paginated<unknown>> = {
	url: '/professor/sessions/history',
	method: 'GET',
	mock: () => ({
		items: [],
		total: 0,
		page: 1,
		size: 20,
	}),
};

// Live session detail (professor projector view)
export const SessionActiveEndpoint: EndpointDef<unknown> = {
	url: '/professor/sessions/active',
	method: 'GET',
	mock: () => ({}),
};

// Close session (professor)
export const SessionCloseEndpoint: EndpointDef<unknown> = {
	url: '/professor/sessions/close',
	method: 'POST',
	mock: () => ({ id: 0, status: 'closed' }),
};

// Attendance records (professor)
export const AttendanceListEndpoint: EndpointDef<Paginated<unknown>> = {
	url: '/professor/attendance',
	method: 'GET',
	mock: () => ({
		items: [],
		total: 0,
		page: 1,
		size: 20,
	}),
};

// --- Auth -------------------------------------------------------------------
//
// The backend's TokenResponse carries no user object; identity always comes
// from GET /auth/me. Mock mode fills in a test-data student (24-0001).

const MOCK_TOKENS: TokenResponse = {
	access_token: 'mock-access-token',
	refresh_token: 'mock-refresh-token',
	mfa_pending: false,
	preauth_token: null,
	must_change_password: false,
};

export const AuthOtpRequestEndpoint: EndpointDef<void> = {
	url: '/auth/otp/request',
	method: 'POST',
	mock: () => undefined,
};

export const AuthOtpVerifyEndpoint: EndpointDef<void> = {
	url: '/auth/otp/verify',
	method: 'POST',
	mock: () => undefined,
};

export const AuthRegisterEndpoint: EndpointDef<TokenResponse> = {
	url: '/auth/register',
	method: 'POST',
	mock: () => MOCK_TOKENS,
};

export const AuthLoginEndpoint: EndpointDef<TokenResponse> = {
	url: '/auth/login',
	method: 'POST',
	mock: () => MOCK_TOKENS,
};

export const AuthRefreshEndpoint: EndpointDef<TokenResponse> = {
	url: '/auth/refresh',
	method: 'POST',
	mock: () => MOCK_TOKENS,
};

export const AuthMeEndpoint: EndpointDef<MeResponse> = {
	url: '/auth/me',
	method: 'GET',
	mock: () => ({
		id: 1,
		role: 'student',
		first_name: 'Jose',
		last_name: 'Rizal',
		email: 'jose.rizal@isu.edu.ph',
		mfa_enabled: false,
		security_question_set: true,
		must_change_password: false,
		last_login: null,
		face_enrolled: false,
		face_enrolled_at: null,
		face_embedding_version: 0,
		claim_status: null,
	}),
};

export const AuthMfaVerifyEndpoint: EndpointDef<TokenResponse> = {
	url: '/auth/mfa/verify',
	method: 'POST',
	mock: () => MOCK_TOKENS,
};

export const AuthChangePasswordEndpoint: EndpointDef<void> = {
	url: '/auth/change-password',
	method: 'POST',
	mock: () => undefined,
};

// --- Student ----------------------------------------------------------------

export const StudentProfileEndpoint: EndpointDef<StudentProfileResponse> = {
	url: '/student/profile',
	method: 'GET',
	mock: () => ({
		student_number: '24-0001',
		first_name: 'Jose',
		middle_name: null,
		last_name: 'Rizal',
		email: 'jose.rizal@isu.edu.ph',
		program_code: 'BSCS',
		year_level_label: '1st Year',
		section: 'A',
		is_active: true,
		face_enrolled: false,
		face_enrolled_at: null,
		face_embedding_version: 0,
		created_at: new Date().toISOString(),
		scan_count: 0,
	}),
};

export const StudentDashboardEndpoint: EndpointDef<StudentDashboardResponse> = {
	url: '/student/dashboard',
	method: 'GET',
	mock: () => ({
		compliance_rate: 0,
		scans_today: 0,
		total_scans: 0,
		today_schedule: [],
		recent_activity: [],
	}),
};

// Endpoint registry
// Named, strongly-typed endpoint definitions keyed for the apiCall() layer.
export const endpoints = {
	// Session QR
	sessionQR: SessionQREndpoint,
	// Attendance scan
	attendanceScan: AttendanceScanEndpoint,
	// Session CRUD
	sessionList: SessionListEndpoint,
	sessionCreate: SessionCreateEndpoint,
	sessionHistory: SessionHistoryEndpoint,
	sessionActive: SessionActiveEndpoint,
	sessionClose: SessionCloseEndpoint,
	// Attendance
	attendanceList: AttendanceListEndpoint,
	// Auth
	authOtpRequest: AuthOtpRequestEndpoint,
	authOtpVerify: AuthOtpVerifyEndpoint,
	authRegister: AuthRegisterEndpoint,
	authLogin: AuthLoginEndpoint,
	authRefresh: AuthRefreshEndpoint,
	authMe: AuthMeEndpoint,
	authMfaVerify: AuthMfaVerifyEndpoint,
	authChangePassword: AuthChangePasswordEndpoint,
	// Student
	studentProfile: StudentProfileEndpoint,
	studentDashboard: StudentDashboardEndpoint,
};
