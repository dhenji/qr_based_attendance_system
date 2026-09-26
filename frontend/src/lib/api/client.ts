// api/client.ts
// Fetch wrapper: auth header injection, automatic token refresh, typed errors,
// and an opt-in mock mode for UI work without a running backend.

import { endpoints } from './endpoints';

// Base API URL — from Vite env with localhost fallback
const BASE_URL = (
	(import.meta.env.PUBLIC_API_URL as string | undefined) || 'http://localhost:8000'
).replace(/\/+$/, '');

// Every backend router is mounted under /api (backend/src/api/router.py), so the
// urls in endpoints.ts are stored relative to that prefix.
const API_PREFIX = '/api';

// Mock mode — opt in with PUBLIC_MOCK_MODE=true to run the UI without a backend.
// Defaults to real API calls.
const MOCK = import.meta.env.PUBLIC_MOCK_MODE === 'true';

export const isMockMode = () => MOCK;

// Error shape types
export class APIError extends Error {
	constructor(
		public code: string,
		public message: string,
		public field?: string,
		// HTTP status, when the failure came from a response. Absent for network
		// failures, which surface as plain TypeErrors instead.
		public status?: number
	) {
		super(message);
		this.name = 'APIError';
	}
}

// API response error shape (matches backend contract)
export interface APIResponseError {
	code?: string;
	message?: string;
	field?: string;
	detail?: {
		code?: string;
		message?: string;
		field?: string;
	};
}

type JsonRecord = Record<string, unknown>;

const isRecord = (value: unknown): value is JsonRecord =>
	typeof value === 'object' && value !== null && !Array.isArray(value);

// Auth token injector — set by features/auth/tokens.ts whenever tokens change
let authToken: string | null = null;

export const setAuthToken = (token: string | null) => {
	authToken = token;
};

export const getAuthToken = () => authToken;

// Invoked when a request comes back 401. Should return a fresh access token, or
// null if the session cannot be recovered. Registered by features/auth/tokens.ts
// to keep this module free of a circular import.
type UnauthorizedHandler = () => Promise<string | null>;

let unauthorizedHandler: UnauthorizedHandler | null = null;

export const setUnauthorizedHandler = (handler: UnauthorizedHandler | null) => {
	unauthorizedHandler = handler;
};

// Configured fetch with auth headers
const fetchWithAuth = async (
	input: RequestInfo,
	init: RequestInit = {}
): Promise<Response> => {
	const headers = new Headers(init.headers || {});
	if (authToken) {
		headers.set('Authorization', `Bearer ${authToken}`);
	}
	// Only declare a JSON body when there is one — setting Content-Type on a
	// bodyless request forces a needless CORS preflight.
	if (init.body !== undefined && init.body !== null) {
		headers.set('Content-Type', 'application/json');
	}

	return fetch(input, {
		...init,
		headers,
		credentials: 'include',
	});
};

// Turn an error response into an APIError.
//
// The backend has three distinct error envelopes and they need different unwrapping:
//   1. AppException  -> {"detail": {"code", "message", "field"}}  (main.py handler)
//   2. FastAPI 422   -> {"detail": [{loc, msg, type}, ...]}
//   3. HTTPException -> {"detail": "some string"}
const parseError = async (response: Response): Promise<APIError> => {
	const body: unknown = await response.json().catch(() => ({}));
	const detail = isRecord(body) ? body.detail : undefined;
	const { status } = response;

	if (isRecord(detail)) {
		const code = typeof detail.code === 'string' ? detail.code : 'request_failed';
		const message = typeof detail.message === 'string' ? detail.message : 'Request failed';
		const field = typeof detail.field === 'string' ? detail.field : undefined;
		return new APIError(code, message, field, status);
	}

	if (Array.isArray(detail) && detail.length > 0) {
		const first = isRecord(detail[0]) ? detail[0] : undefined;
		const loc = first && Array.isArray(first.loc) ? first.loc : [];
		// loc is ["body", "password"] — the trailing entry is the offending field
		const field = loc.length > 1 ? String(loc[loc.length - 1]) : undefined;
		const message = first && typeof first.msg === 'string' ? first.msg : 'Validation failed';
		return new APIError('validation_error', message, field, status);
	}

	if (typeof detail === 'string') {
		return new APIError('request_failed', detail, undefined, status);
	}

	return new APIError('request_failed', `Request failed (${status})`, undefined, status);
};

// One request/response round trip, with one transparent retry after a 401 when
// the registered handler can mint a new access token.
const request = async <T>(url: string, init: RequestInit, alreadyRetried: boolean): Promise<T> => {
	const response = await fetchWithAuth(url, init);

	if (response.status === 401 && !alreadyRetried && unauthorizedHandler) {
		const freshToken = await unauthorizedHandler();
		if (freshToken) {
			authToken = freshToken;
			return request<T>(url, init, true);
		}
	}

	if (!response.ok) {
		throw await parseError(response);
	}

	// 204 No Content (e.g. POST /auth/otp/request) — response.json() would throw
	if (response.status === 204) {
		return undefined as T;
	}

	return response.json() as Promise<T>;
};

// Generic API call handler
const apiCall = async <T>(
	endpoint: keyof typeof endpoints,
	options: {
		method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
		body?: unknown;
		params?: Record<string, string>;
	} = {}
): Promise<T> => {
	const { method = 'GET', body, params } = options;
	const endpointDef = endpoints[endpoint];

	// Mock mode — return mock data
	if (MOCK) {
		if (endpointDef.mock) {
			return endpointDef.mock() as unknown as T;
		}
		// Return stub structure
		return {} as unknown as T;
	}

	const url = new URL(`${API_PREFIX}${endpointDef.url}`, BASE_URL);
	if (params) {
		Object.entries(params).forEach(([key, value]) => {
			url.searchParams.append(key, value);
		});
	}

	const init: RequestInit = {
		method,
		body: body === undefined ? undefined : JSON.stringify(body),
	};

	return request<T>(url.toString(), init, false);
};

// Convenience exports
// Thin wrappers that map each HTTP verb onto apiCall().
export const get = <T>(endpoint: keyof typeof endpoints, params?: Record<string, string>) =>
	apiCall<T>(endpoint, { method: 'GET', params });

export const post = <T>(endpoint: keyof typeof endpoints, body?: unknown, params?: Record<string, string>) =>
	apiCall<T>(endpoint, { method: 'POST', body, params });

export const put = <T>(endpoint: keyof typeof endpoints, body?: unknown, params?: Record<string, string>) =>
	apiCall<T>(endpoint, { method: 'PUT', body, params });

export const del = <T>(endpoint: keyof typeof endpoints, params?: Record<string, string>) =>
	apiCall<T>(endpoint, { method: 'DELETE', params });
