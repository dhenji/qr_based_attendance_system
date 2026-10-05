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
// Plain-text 500s (unhandled non-AppException escapes to FastAPI's default
// text body) fall through to the generic branch with the text preserved.
const parseError = async (response: Response): Promise<APIError> => {
	const { status } = response;
	// Read as text first: the body can only be consumed once, and a
	// plain-text 500 has no JSON to parse.
	const text = await response.text().catch(() => '');
	let body: unknown = {};
	if (text) {
		try {
			body = JSON.parse(text) as unknown;
		} catch {
			// Not JSON — keep the raw text for the fallback below.
			body = {};
		}
	}
	const detail = isRecord(body) ? body.detail : undefined;

	if (isRecord(detail)) {
		const code = typeof detail.code === 'string' ? detail.code : 'request_failed';
		const message = typeof detail.message === 'string' ? detail.message : 'Request failed';
		const field = typeof detail.field === 'string' ? detail.field : undefined;
		return new APIError(code, message, field, status);
	}

	if (Array.isArray(detail)) {
		if (detail.length === 0) {
			return new APIError('validation_error', 'Validation failed', undefined, status);
		}
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

	// Plain-text or empty body (e.g. FastAPI's default 500 page): preserve a
	// truncated slice so the message is actionable instead of opaque.
	const snippet = text.trim().slice(0, 200);
	const message = snippet ? snippet : `Request failed (${status})`;
	return new APIError('request_failed', message, undefined, status);
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

// Query values accept arrays for repeated keys (?course_ids=1&course_ids=2)
// — FastAPI parses those into list[int], while a comma-joined string does
// not split server-side.
export type QueryParams = Record<string, string | string[]>;

const appendParams = (url: URL, params?: QueryParams): void => {
	if (!params) return;
	for (const [key, value] of Object.entries(params)) {
		if (Array.isArray(value)) {
			for (const entry of value) url.searchParams.append(key, entry);
		} else {
			url.searchParams.append(key, value);
		}
	}
};

// Mocks predate repeated keys and parse comma-joined values (e.g.
// parseCourseIds), so arrays collapse to comma strings on the mock path
// while the live path above repeats the key.
const forMock = (params?: QueryParams): Record<string, string> | undefined => {
	if (!params) return undefined;
	return Object.fromEntries(
		Object.entries(params).map(([key, value]) => [
			key,
			Array.isArray(value) ? value.join(',') : value,
		])
	);
};

// Generic API call handler
const apiCall = async <T>(
	endpoint: keyof typeof endpoints,
	options: {
		method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
		body?: unknown;
		params?: QueryParams;
		// Extra path segment for id-in-path routes, e.g. `/active/${id}` or
		// `/${id}/close` for the professor session detail/close endpoints.
		suffix?: string;
		// Extra request headers, merged by fetchWithAuth (auth + JSON
		// Content-Type still applied there). Used for X-Idempotency-Key on
		// offline-queue replays (docs/architecture/offline-first.md).
		headers?: Record<string, string>;
	} = {}
): Promise<T> => {
	const { method = 'GET', body, params, suffix = '', headers } = options;
	const endpointDef = endpoints[endpoint];

	// Mock mode — return mock data (call inputs forwarded so stateful mocks
	// can filter/sort/paginate lists and apply CRUD payloads like the backend).
	// Defs without a mock throw explicitly instead of resolving to an empty
	// stub: silent `{}` masks missing fixtures as downstream undefined-property
	// failures.
	if (MOCK) {
		if (endpointDef.mock) {
			return endpointDef.mock(forMock(params), suffix, body, method) as unknown as T;
		}
		throw new APIError(
			'mock_mode',
			`No mock fixture for ${endpointDef.url} — wire one or bypass apiCall in mock mode`
		);
	}

	const url = new URL(`${API_PREFIX}${endpointDef.url}${suffix}`, BASE_URL);
	appendParams(url, params);

	const init: RequestInit = {
		method,
		body: body === undefined ? undefined : JSON.stringify(body),
		...(headers === undefined ? {} : { headers })
	};

	return request<T>(url.toString(), init, false);
};

// Convenience exports
// Thin wrappers that map each HTTP verb onto apiCall(). `suffix` appends an
// id-in-path segment (e.g. `/active/${id}`).
export const get = <T>(
	endpoint: keyof typeof endpoints,
	params?: QueryParams,
	suffix?: string
) => apiCall<T>(endpoint, { method: 'GET', params, suffix });

export const post = <T>(
	endpoint: keyof typeof endpoints,
	body?: unknown,
	params?: QueryParams,
	suffix?: string,
	headers?: Record<string, string>
) => apiCall<T>(endpoint, { method: 'POST', body, params, suffix, headers });

export const put = <T>(endpoint: keyof typeof endpoints, body?: unknown, params?: QueryParams) =>
	apiCall<T>(endpoint, { method: 'PUT', body, params });

export const patch = <T>(
	endpoint: keyof typeof endpoints,
	body?: unknown,
	params?: QueryParams,
	suffix?: string
) => apiCall<T>(endpoint, { method: 'PATCH', body, params, suffix });

export const del = <T>(
	endpoint: keyof typeof endpoints,
	params?: QueryParams,
	suffix?: string
) => apiCall<T>(endpoint, { method: 'DELETE', params, suffix });

// Multipart upload for CSV roster imports (POST /admin/students/import,
// POST /admin/professors/import). Sends FormData without a JSON Content-Type
// so the browser sets the multipart boundary; auth + 401-retry reuse
// fetchWithAuth/request. Mock mode returns the endpoint's mock payload.
export const postForm = async <T>(
	endpoint: keyof typeof endpoints,
	form: FormData,
	params?: QueryParams,
	suffix?: string
): Promise<T> => {
	const endpointDef = endpoints[endpoint];

	if (MOCK) {
		if (endpointDef.mock) {
			return endpointDef.mock(forMock(params), suffix, undefined, 'POST') as unknown as T;
		}
		throw new APIError(
			'mock_mode',
			`No mock fixture for ${endpointDef.url} — wire one or bypass postForm in mock mode`
		);
	}

	const url = new URL(`${API_PREFIX}${endpointDef.url}${suffix ?? ''}`, BASE_URL);
	appendParams(url, params);

	const headers = new Headers();
	if (authToken) {
		headers.set('Authorization', `Bearer ${authToken}`);
	}

	const doFetch = async (alreadyRetried: boolean): Promise<T> => {
		const response = await fetch(url.toString(), {
			method: 'POST',
			headers,
			body: form,
			credentials: 'include',
		});

		if (response.status === 401 && !alreadyRetried && unauthorizedHandler) {
			const freshToken = await unauthorizedHandler();
			if (freshToken) {
				authToken = freshToken;
				headers.set('Authorization', `Bearer ${freshToken}`);
				return doFetch(true);
			}
		}

		if (!response.ok) {
			throw await parseError(response);
		}

		if (response.status === 204) {
			return undefined as T;
		}

		return response.json() as Promise<T>;
	};

	return doFetch(false);
};

// Raw-text download for CSV templates (GET /admin/students/import/template)
// and filtered CSV exports (GET /admin/attendance/overview/export). Text/csv
// routes have no endpoint def (they return text, not JSON), so the path is
// passed directly. Returns the CSV text for client-side download.
export const getText = async (path: string, params?: QueryParams): Promise<string> => {
	if (MOCK) {
		throw new APIError('mock_mode', 'Server CSV download is unavailable in mock mode');
	}

	const url = new URL(`${API_PREFIX}${path}`, BASE_URL);
	appendParams(url, params);

	const doFetch = async (alreadyRetried: boolean): Promise<string> => {
		const response = await fetchWithAuth(url.toString(), { method: 'GET' });

		if (response.status === 401 && !alreadyRetried && unauthorizedHandler) {
			const freshToken = await unauthorizedHandler();
			if (freshToken) {
				authToken = freshToken;
				return doFetch(true);
			}
		}

		if (!response.ok) {
			throw await parseError(response);
		}

		return response.text();
	};

	return doFetch(false);
};

// Raw-text POST for CSV exports (POST /professor/reports/export). The export
// route takes a JSON filter body and returns text/csv, so it fits neither
// apiCall (JSON response) nor getText (GET). Auth header + 401-refresh reuse
// fetchWithAuth; the path is passed directly, mirroring getText.
export const postText = async (path: string, body: unknown): Promise<string> => {
	if (MOCK) {
		throw new APIError('mock_mode', 'Server CSV export is unavailable in mock mode');
	}

	const url = new URL(`${API_PREFIX}${path}`, BASE_URL);

	const doFetch = async (alreadyRetried: boolean): Promise<string> => {
		const response = await fetchWithAuth(url.toString(), {
			method: 'POST',
			body: JSON.stringify(body)
		});

		if (response.status === 401 && !alreadyRetried && unauthorizedHandler) {
			const freshToken = await unauthorizedHandler();
			if (freshToken) {
				authToken = freshToken;
				return doFetch(true);
			}
		}

		if (!response.ok) {
			throw await parseError(response);
		}

		return response.text();
	};

	return doFetch(false);
};

// Binary download for encrypted backup archives
// (GET /admin/backups/{id}/download → application/octet-stream with a
// Content-Disposition filename). getText cannot handle binary, so this fetches
// a Blob and parses the filename header instead.
export const getBlob = async (
	path: string,
	params?: QueryParams
): Promise<{ blob: Blob; filename: string }> => {
	if (MOCK) {
		throw new APIError('mock_mode', 'Server file download is unavailable in mock mode');
	}

	const url = new URL(`${API_PREFIX}${path}`, BASE_URL);
	appendParams(url, params);

	const doFetch = async (alreadyRetried: boolean): Promise<{ blob: Blob; filename: string }> => {
		const response = await fetchWithAuth(url.toString(), { method: 'GET' });

		if (response.status === 401 && !alreadyRetried && unauthorizedHandler) {
			const freshToken = await unauthorizedHandler();
			if (freshToken) {
				authToken = freshToken;
				return doFetch(true);
			}
		}

		if (!response.ok) {
			throw await parseError(response);
		}

		const blob = await response.blob();
		const disposition = response.headers.get('content-disposition') ?? '';
		const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
		const filename = match?.[1] ? decodeURIComponent(match[1].trim()) : path.split('/').pop() ?? 'download';
		return { blob, filename };
	};

	return doFetch(false);
};
