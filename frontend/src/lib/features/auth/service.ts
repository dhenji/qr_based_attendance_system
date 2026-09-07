// features/auth/service.ts
// Mock-first auth service: login, register, OTP, logout

import type { User } from '$lib/shared/types';
import { browser } from '$app/environment';

// MOCK flag — swap to false when backend endpoints land
const MOCK = true;

// Mock users (matches features/auth/model.py patterns)
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

// Login (email/password)
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

// Register (claim-based with OTP)
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

// Logout
export const logout = async (): Promise<void> => {
	// Clear mock auth state (real API call when backend ready)
	return;
};

// Get current user from stored token
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
