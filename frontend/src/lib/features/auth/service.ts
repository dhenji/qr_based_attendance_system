// features/auth/service.ts
// Mock-first auth service: login, register, OTP, logout

import type { User } from '$lib/shared/types';
import { browser } from '$app/environment';

// MOCK flag — swap to false when backend endpoints land
const MOCK = true;

// Mock data
// Hard-coded users mirroring the backend roles so login works offline.
const MOCK_USERS = {
	student: {
		id: 'user-1',
		email: 'student@test.com',
		role: 'student' as const,
	},
	professor: {
		id: 'user-2',
		email: 'prof@test.com',
		role: 'professor' as const,
	},
	admin: {
		id: 'user-3',
		email: 'admin@test.com',
		role: 'admin' as const,
	},
};

// Login
// Email/password login. Maps known test emails to mock users; anything else
// throws so the UI can show the error state.
export const login = async (email: string, _password: string): Promise<{ user: User; accessToken: string }> => {
	if (MOCK) {
		if (email === 'student@test.com') {
			return { user: MOCK_USERS.student, accessToken: 'mock-jwt-token-student' };
		}
		if (email === 'prof@test.com') {
			return { user: MOCK_USERS.professor, accessToken: 'mock-jwt-token-professor' };
		}
		if (email === 'admin@test.com') {
			return { user: MOCK_USERS.admin, accessToken: 'mock-jwt-token-admin' };
		}
		throw new Error('Invalid credentials');
	}

	return { user: MOCK_USERS.student, accessToken: 'mock-jwt-token' };
};

// Register & OTP
// Claim-based registration: user provides email + student number, then confirms
// via OTP. Both endpoints return the newly created user in mock mode.
export const register = async (email: string, _studentNumber: string): Promise<User> => {
	if (MOCK) {
		return {
			id: Math.random().toString(36).substring(2, 9),
			email,
			role: 'student',
		};
	}
	return {
		id: Math.random().toString(36).substring(2, 9),
		email,
		role: 'student',
	};
};

// OTP verification
export const verifyOTP = async (email: string, _otpCode: string): Promise<User> => {
	if (MOCK) {
		return {
			id: Math.random().toString(36).substring(2, 9),
			email,
			role: 'student',
		};
	}
	return {
		id: Math.random().toString(36).substring(2, 9),
		email,
		role: 'student',
	};
};

// Session helpers
// Logout clears auth state (real API call once backend is wired up).
export const logout = async (): Promise<void> => {
	// Clear mock auth state (real API call when backend ready)
	return;
};

// me
// Resolve the current user from the token stored in localStorage.
export const me = async (): Promise<User | null> => {
	if (MOCK) {
		const token = browser ? localStorage.getItem('auth_token') : null;
		if (token === 'mock-jwt-token-student') return MOCK_USERS.student;
		if (token === 'mock-jwt-token-professor') return MOCK_USERS.professor;
		if (token === 'mock-jwt-token-admin') return MOCK_USERS.admin;
		return null;
	}
	return null;
};
