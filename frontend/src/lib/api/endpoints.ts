// api/endpoints.ts
// Typed endpoint map mirroring backend API contracts
// (from docs/architecture/api-contracts.md)

type ScanStatus = 'present' | 'late' | 'rejected';

interface EndpointDef<T> {
	url: string;
	method: 'GET' | 'POST' | 'PUT' | 'DELETE';
	mock: () => T;
}

// Session QR payload (D18)
export const SessionQREndpoint: EndpointDef<{
	session_id: number;
	course_id: number;
	course_code: string;
	course_name: string;
	expires_at: string;
	scheduled_end_time: string;
	geofence: { radius: number; lat: number; lng: number };
	present_window_minutes: number;
	late_window_minutes: number;
}> = {
	url: '/student/sessions/verify-code',
	method: 'POST',
	mock: () => ({
		session_id: Math.floor(Math.random() * 1000) + 1,
		course_id: Math.floor(Math.random() * 50) + 1,
		course_code: `COURSE-${Math.floor(Math.random() * 20) + 1}`,
		course_name: `Course ${Math.floor(Math.random() * 20) + 1}`,
		expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
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
export const AttendanceScanEndpoint: EndpointDef<{
	attendance_id: number;
	status: ScanStatus;
	scanned_at: string;
	expires_at: string;
}> = {
	url: '/student/attendance/scan',
	method: 'POST',
	mock: () => ({
		attendance_id: Math.floor(Math.random() * 10000) + 1,
		status: (['present', 'late', 'rejected'] as ScanStatus[])[Math.floor(Math.random() * 3)],
		scanned_at: new Date().toISOString(),
		expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
	}),
};

// Session CRUD (professor)
export const SessionListEndpoint: EndpointDef<{
	items: unknown[];
	total: number;
	page: number;
	size: number;
}> = {
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

// Attendance records (professor)
export const AttendanceListEndpoint: EndpointDef<{
	items: unknown[];
	total: number;
	page: number;
	size: number;
}> = {
	url: '/professor/attendance',
	method: 'GET',
	mock: () => ({
		items: [],
		total: 0,
		page: 1,
		size: 20,
	}),
};

// Auth endpoints (mock)
export const AuthLoginEndpoint: EndpointDef<{
	access_token: string;
	user: { id: string; email: string; role: string };
}> = {
	url: '/auth/login',
	method: 'POST',
	mock: () => ({
		access_token: 'mock-jwt-token',
		user: {
			id: 'user-123',
			email: 'student@test.com',
			role: 'student',
		},
	}),
};

export const AuthRegisterEndpoint: EndpointDef<{
	user: { id: string; email: string; role: string };
}> = {
	url: '/auth/register',
	method: 'POST',
	mock: () => ({
		user: {
			id: Math.random().toString(36).substring(2, 9),
			email: 'new@test.com',
			role: 'student',
		},
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
	// Attendance
	attendanceList: AttendanceListEndpoint,
	// Auth
	authLogin: AuthLoginEndpoint,
	authRegister: AuthRegisterEndpoint,
};
