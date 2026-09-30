// features/auth/mock.ts
// Mock fixtures for PUBLIC_MOCK_MODE=true. Kept separate from service.ts so the
// real call sites stay readable.

import type { MeResponse, TokenResponse } from '$lib/shared/types';

// Test-data student 24-0001 (docs/testing/test-data.md §4) using the
// {first}.{middle}.{last}@isu.edu.ph convention.
const MOCK_STUDENT: MeResponse = {
	id: 1,
	role: 'student',
	first_name: 'Jose',
	last_name: 'Rizal',
	email: 'jose.p.rizal@isu.edu.ph',
	mfa_enabled: false,
	security_question_set: true,
	must_change_password: false,
	last_login: null,
	face_enrolled: false,
	face_enrolled_at: null,
	face_embedding_version: 0,
	claim_status: null,
};

const MOCK_PROFESSOR: MeResponse = {
	...MOCK_STUDENT,
	id: 2,
	role: 'professor',
	first_name: 'Maria',
	last_name: 'Dela Cruz',
	email: 'maria.c.delacruz@isu.edu.ph',
	face_enrolled: null,
	face_enrolled_at: null,
	face_embedding_version: null,
	claim_status: 'active',
};

const delay = <T>(value: T): Promise<T> => Promise.resolve(value);

const studentTokens: TokenResponse = {
	access_token: 'mock-access-token-student',
	refresh_token: 'mock-refresh-token-student',
	mfa_pending: false,
	preauth_token: null,
	must_change_password: false,
};

const professorTokens: TokenResponse = {
	access_token: 'mock-access-token-professor',
	refresh_token: 'mock-refresh-token-professor',
	mfa_pending: false,
	preauth_token: null,
	must_change_password: false,
};

// Who the last mock login signed in as, so /auth/me returns a matching identity
// instead of always claiming to be the student.
let signedInAs: MeResponse = MOCK_STUDENT;

export const mockLogin = async (email: string): Promise<TokenResponse> => {
	const normalized = email.trim().toLowerCase();

	if (normalized === MOCK_PROFESSOR.email) {
		signedInAs = MOCK_PROFESSOR;
		return delay(professorTokens);
	}

	if (normalized === MOCK_STUDENT.email) {
		signedInAs = MOCK_STUDENT;
		return delay(studentTokens);
	}

	throw new Error('Invalid email or password.');
};

export const mockRegister = async (): Promise<TokenResponse> => {
	signedInAs = MOCK_STUDENT;
	return delay(studentTokens);
};

export const mockMe = async (): Promise<MeResponse> => delay(signedInAs);

export const mockMfaVerify = async (): Promise<TokenResponse> => delay(signedInAs === MOCK_PROFESSOR ? professorTokens : studentTokens);

export const mockNoop = async (): Promise<void> => delay(undefined);
