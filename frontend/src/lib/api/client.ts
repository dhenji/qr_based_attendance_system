// api/client.ts
// Fetch wrapper with MOCK flag, error types, and auth header injection

import { endpoints } from './endpoints';

// Base API URL — from Vite env with localhost fallback
const BASE_URL =
	(import.meta.env.PUBLIC_API_URL as string | undefined) || 'http://localhost:8000';

// MOCK flag — set to true for mock-first development,
// swap to false when backend endpoints are ready
const MOCK = true;

// Error shape types
export class APIError extends Error {
	constructor(
		public code: string,
		public message: string,
		public field?: string
	) {
		super(message);
		this.name = 'APIError';
	}
}

// API response error shape (matches backend contract)
export interface APIResponseError {
	code: string;
	message: string;
	field?: string;
}

// Auth token injector — set via the auth store when a user logs in
let authToken: string | null = null;

export const setAuthToken = (token: string | null) => {
	authToken = token;
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
	headers.set('Content-Type', 'application/json');

	const url = typeof input === 'string' ? input : input.toString();
	const response = await fetch(`${BASE_URL}${url}`, {
		...init,
		headers,
		credentials: 'include',
	});

	return response;
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

	// Real API call
	const url = new URL(endpointDef.url, BASE_URL);
	if (params) {
		Object.entries(params).forEach(([key, value]) => {
			url.searchParams.append(key, value);
		});
	}

	const response = await fetchWithAuth(url.toString(), {
		method,
		body: body ? JSON.stringify(body) : undefined,
	});

	if (!response.ok) {
		const errorData: APIResponseError = await response.json();
		throw new APIError(
			errorData.code || 'UNKNOWN_ERROR',
			errorData.message || 'Request failed',
			errorData.field
		);
	}

	return response.json() as Promise<T>;
};

// Convenience exports
// Thin wrappers that map each HTTP verb onto apiCall().
export const get = <T>(endpoint: keyof typeof endpoints, params?: Record<string, string>) =>
	apiCall<T>(endpoint, { method: 'GET', params });

export const post = <T>(endpoint: keyof typeof endpoints, body: unknown, params?: Record<string, string>) =>
	apiCall<T>(endpoint, { method: 'POST', body, params });

export const put = <T>(endpoint: keyof typeof endpoints, body: unknown, params?: Record<string, string>) =>
	apiCall<T>(endpoint, { method: 'PUT', body, params });

export const del = <T>(endpoint: keyof typeof endpoints, params?: Record<string, string>) =>
	apiCall<T>(endpoint, { method: 'DELETE', params });
