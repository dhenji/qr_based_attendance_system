// api/client.ts
// Fetch wrapper: auth header injection, automatic token refresh, typed errors,
// and an opt-in mock mode for UI work without a running backend.

import { endpoints } from './endpoints';

// Base API URL — from Vite env with localhost fallback.
// Warns once in dev when PUBLIC_API_URL is unset so a misconfigured
// deployment surfaces early instead of silently hitting localhost.
const RAW_BASE_URL = import.meta.env.PUBLIC_API_URL as string | undefined;
const BASE_URL = (RAW_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');

if (!RAW_BASE_URL && import.meta.env.DEV) {
	console.warn('[api] PUBLIC_API_URL is unset — falling back to http://localhost:8000');
}

// Default per-request timeout (ms). Each transport aborts hung requests so
// spinners surface "Request timed out, try again." instead of hanging forever.
export const DEFAULT_TIMEOUT_MS = 30_000;

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
		// HTTP status, when the failure came from a response. Absent for
		// transport failures, which surface as APIError with code
		// 'network_error' (or 'request_timeout' / 'request_cancelled').
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

// Configured fetch with auth headers. Accepts an optional AbortSignal so
// callers (and the apiCall timeout below) can cancel hung requests.
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

// Race a fetch against a timeout. Returns the response, or throws an
// APIError with code 'request_timeout' when the deadline fires. A caller
// signal is honoured too — aborting it rejects the same way.
const fetchWithTimeout = async (
	doFetch: (signal: AbortSignal) => Promise<Response>,
	timeoutMs: number,
	outerSignal?: AbortSignal | null
): Promise<Response> => {
	const controller = new AbortController();
	const timer = setTimeout(() => controller.abort(), timeoutMs);
	const onOuterAbort = () => controller.abort();
	try {
		if (outerSignal) {
			if (outerSignal.aborted) controller.abort();
			else outerSignal.addEventListener('abort', onOuterAbort, { once: true });
		}
		return await doFetch(controller.signal);
	} catch (e) {
		if (controller.signal.aborted) {
			const causedByCaller = outerSignal?.aborted ?? false;
			throw new APIError(
				causedByCaller ? 'request_cancelled' : 'request_timeout',
				causedByCaller ? 'Request was cancelled.' : 'Request timed out, try again.'
			);
		}
		// Transport failure (offline, DNS, refused connection): fetch rejects
		// with a plain TypeError. Wrap it so callers branching on
		// `e instanceof APIError` (e.g. the scan offline-queue gate) never
		// mistake a programming bug for a dropped connection — only these
		// codes may be queued/retried as offline.
		if (e instanceof APIError) throw e;
		// Browsers report transport failures as "Failed to fetch", which tells
		// the user nothing. Keep transport details in the console and surface a
		// stable, actionable message in the UI.
		if (e instanceof Error) {
			console.warn('[api] request failed before a response:', e.message);
		}
		throw new APIError(
			'network_error',
			'Unable to reach the server. Check your connection and try again.'
		);
	} finally {
		clearTimeout(timer);
		if (outerSignal) outerSignal.removeEventListener('abort', onOuterAbort);
	}
};

// Single transparent 401-refresh shared by every transport: runs the fetch,
// and on a 401 with a registered handler mints one fresh token and retries
// exactly once. Each caller passes a closure that builds its own request so
// header handling stays per-site (fetchWithAuth re-reads the live token;
// postForm rebuilds its manual headers on retry).
const fetchWith401Retry = async (
	doFetch: () => Promise<Response>
): Promise<Response> => {
	const response = await doFetch();
	if (response.status === 401 && unauthorizedHandler) {
		const freshToken = await unauthorizedHandler();
		if (freshToken) {
			authToken = freshToken;
			return doFetch();
		}
	}
	return response;
};

// Turn an error response into an APIError.
//
// The backend has three distinct error envelopes and they need different unwrapping:
//   1. AppException  -> {"detail": {"code", "message", "field"}}  (main.py handler)
//   2. FastAPI 422   -> {"detail": [{loc, msg, type}, ...]}
//   3. HTTPException -> {"detail": "some string"}
// Plain-text 500s (unhandled non-AppException escapes to FastAPI's default
// text body) fall through to the generic branch with the text preserved.
export const parseError = async (response: Response): Promise<APIError> => {
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
		// Surface every issue, not just the first: multi-field forms otherwise
		// lose all but one error. Field stays the first offending one so
		// callers can still focus it.
		const messages: string[] = [];
		let field: string | undefined;
		for (const entry of detail) {
			if (!isRecord(entry)) continue;
			const msg = typeof entry.msg === 'string' ? entry.msg : null;
			if (msg) messages.push(msg);
			if (field === undefined && Array.isArray(entry.loc) && entry.loc.length > 1) {
				// loc is ["body", "password"] — the trailing entry is the field.
				field = String(entry.loc[entry.loc.length - 1]);
			}
		}
		const message = messages.length > 0 ? messages.join('; ') : 'Validation failed';
		return new APIError('validation_error', message, field, status);
	}

	if (typeof detail === 'string') {
		// Plain-string HTTPException (401/403/404/429 from the backend).
		// Give it a stable code derived from the status so callers branching
		// on e.code (scan/excuse maps) can distinguish it instead of seeing
		// a generic 'request_failed'.
		const code =
			status === 401
				? 'invalid_token'
				: status === 403
					? 'forbidden'
					: status === 404
						? 'not_found'
						: status === 429
							? 'rate_limited'
							: 'request_failed';
		return new APIError(code, detail, undefined, status);
	}

	// Plain-text or empty body (e.g. FastAPI's default 500 page): preserve a
	// truncated slice so the message is actionable instead of opaque.
	const snippet = text.trim().slice(0, 200);
	const message = snippet ? snippet : `Request failed (${status})`;
	return new APIError('request_failed', message, undefined, status);
};

// One request/response round trip, with one transparent retry after a 401 when
// the registered handler can mint a new access token. Success JSON is parsed
// defensively: a non-JSON/empty body surfaces as APIError (not a raw
// SyntaxError) so toUserMessage/toAuthMessage always apply.
const request = async <T>(
	url: string,
	init: RequestInit,
	timeoutMs: number = DEFAULT_TIMEOUT_MS
): Promise<T> => {
	const doRoundTrip = (signal: AbortSignal): Promise<Response> =>
		fetchWith401Retry(() => fetchWithAuth(url, { ...init, signal }));
	const response = await fetchWithTimeout(doRoundTrip, timeoutMs, init.signal ?? null);

	if (!response.ok) {
		throw await parseError(response);
	}

	// 204 No Content (e.g. POST /auth/otp/request) — response.json() would throw
	if (response.status === 204) {
		return undefined as T;
	}

	try {
		return (await response.json()) as T;
	} catch {
		throw new APIError(
			'request_failed',
			'Invalid response from the server. Please try again.',
			undefined,
			response.status
		);
	}
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

// In-flight GET dedup + short-lived cache. Both are best-effort and only
// apply to real (non-mock) GET requests without a caller abort signal, so a
// caller can still cancel its own request without affecting shared ones.
const __inflight = new Map<string, Promise<unknown>>();
const __cache = new Map<string, { value: unknown; expires: number }>();

const __serializeParams = (params?: QueryParams): string => {
	if (!params) return '';
	const keys = Object.keys(params).sort();
	return JSON.stringify(keys.map((k) => [k, params[k]]));
};

const __cacheKey = (
	endpoint: keyof typeof endpoints,
	suffix: string,
	params: QueryParams | undefined,
	token: string | null
): string => `${String(endpoint)}|${suffix || ''}|${__serializeParams(params)}|${token || ''}`;

export const invalidateApiCache = (matcher?: (key: string) => boolean): void => {
	if (!matcher) {
		__cache.clear();
		return;
	}
	for (const key of [...__cache.keys()]) {
		if (matcher(key)) __cache.delete(key);
	}
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
		// Per-request timeout override (ms) and caller abort signal.
		timeoutMs?: number;
		signal?: AbortSignal | null;
		// Opt-in short-lived response cache (ms). Only meaningful for GETs;
		// 0/unset disables caching. Mutations should call invalidateApiCache.
		cacheTtlMs?: number;
	} = {}
): Promise<T> => {
	const { method = 'GET', body, params, suffix = '', headers, timeoutMs, signal, cacheTtlMs = 0 } = options;
	const endpointDef = endpoints[endpoint];

	// Mock mode — return mock data (call inputs forwarded so stateful mocks
	// can filter/sort/paginate lists and apply CRUD payloads like the backend).
	// Defs without a mock throw explicitly instead of resolving to an empty
	// stub: silent `{}` masks missing fixtures as downstream undefined-property
	// failures.
	if (MOCK) {
		if (endpointDef.mock) {
			try {
				return endpointDef.mock(forMock(params), suffix, body, method) as unknown as T;
			} catch (e: unknown) {
				// Stateful mocks throw plain Errors for domain rejections
				// (not-found, duplicate). Normalize to APIError so callers
				// branching on `e instanceof APIError` (e.g. scan's
				// isNetworkError offline-queue gate) treat them as
				// server-decided, never as network failures to retry/queue.
				if (e instanceof APIError) throw e;
				throw new APIError(
					'request_failed',
					e instanceof Error && e.message ? e.message : 'Mock request failed'
				);
			}
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
		...(headers === undefined ? {} : { headers }),
		...(signal ? { signal } : {})
	};

	// GET dedup + opt-in cache (real mode only). Mutations bypass this.
	if (method === 'GET' && !MOCK) {
		const key = __cacheKey(endpoint, suffix, params, authToken);
		const now = Date.now();
		if (cacheTtlMs > 0) {
			const cached = __cache.get(key);
			if (cached && cached.expires > now) {
				return Promise.resolve(cached.value as T);
			}
		}
		if (!signal) {
			const existing = __inflight.get(key);
			if (existing) return existing as Promise<T>;
			const promise = request<T>(url.toString(), init, timeoutMs ?? DEFAULT_TIMEOUT_MS)
				.then((value) => {
					if (cacheTtlMs > 0) {
						__cache.set(key, { value, expires: Date.now() + cacheTtlMs });
					}
					return value;
				})
				.finally(() => {
					__inflight.delete(key);
				});
			__inflight.set(key, promise);
			return promise;
		}
	}
	return request<T>(url.toString(), init, timeoutMs ?? DEFAULT_TIMEOUT_MS);
};

// Convenience exports
// Thin wrappers that map each HTTP verb onto apiCall(). `suffix` appends an
// id-in-path segment (e.g. `/active/${id}`).
export const get = <T>(
	endpoint: keyof typeof endpoints,
	params?: QueryParams,
	suffix?: string,
	opts?: { timeoutMs?: number; signal?: AbortSignal | null; cacheTtlMs?: number }
) => apiCall<T>(endpoint, { method: 'GET', params, suffix, ...opts });

export const post = <T>(
	endpoint: keyof typeof endpoints,
	body?: unknown,
	params?: QueryParams,
	suffix?: string,
	headers?: Record<string, string>,
	opts?: { timeoutMs?: number; signal?: AbortSignal | null; cacheTtlMs?: number }
) => apiCall<T>(endpoint, { method: 'POST', body, params, suffix, headers, ...opts });

export const put = <T>(
	endpoint: keyof typeof endpoints,
	body?: unknown,
	params?: QueryParams,
	suffix?: string,
	opts?: { timeoutMs?: number; signal?: AbortSignal | null; cacheTtlMs?: number }
) => apiCall<T>(endpoint, { method: 'PUT', body, params, suffix, ...opts });

export const patch = <T>(
	endpoint: keyof typeof endpoints,
	body?: unknown,
	params?: QueryParams,
	suffix?: string,
	opts?: { timeoutMs?: number; signal?: AbortSignal | null; cacheTtlMs?: number }
) => apiCall<T>(endpoint, { method: 'PATCH', body, params, suffix, ...opts });

export const del = <T>(
	endpoint: keyof typeof endpoints,
	params?: QueryParams,
	suffix?: string,
	body?: unknown,
	headers?: Record<string, string>,
	opts?: { timeoutMs?: number; signal?: AbortSignal | null; cacheTtlMs?: number }
) => apiCall<T>(endpoint, { method: 'DELETE', params, suffix, body, headers, ...opts });

// Multipart upload for CSV roster imports (POST /admin/students/import,
// POST /admin/professors/import). Sends FormData without a JSON Content-Type
// so the browser sets the multipart boundary; auth + 401-retry reuse
// fetchWithAuth/request. Mock mode returns the endpoint's mock payload.
export const postForm = async <T>(
	endpoint: keyof typeof endpoints,
	form: FormData,
	params?: QueryParams,
	suffix?: string,
	opts?: { timeoutMs?: number; signal?: AbortSignal | null; cacheTtlMs?: number }
): Promise<T> => {
	const endpointDef = endpoints[endpoint];

	if (MOCK) {
		if (endpointDef.mock) {
			try {
				// Forward the uploaded file to the mock so CSV imports can
				// derive counts/errors from its real rows instead of a fixed
				// fixture. Face-enrollment uploads carry photo fields, not a
				// 'file' field — those mocks read the suffix and ignore this.
				let mockBody: unknown;
				const uploaded = form.get('file');
				if (typeof File !== 'undefined' && uploaded instanceof File) {
					const fileText = await uploaded.text().catch(() => '');
					mockBody = { fileName: uploaded.name, fileSize: uploaded.size, fileText };
				}
				return endpointDef.mock(forMock(params), suffix, mockBody, 'POST') as unknown as T;
			} catch (e: unknown) {
				if (e instanceof APIError) throw e;
				throw new APIError(
					'request_failed',
					e instanceof Error && e.message ? e.message : 'Mock request failed'
				);
			}
		}
		throw new APIError(
			'mock_mode',
			`No mock fixture for ${endpointDef.url} — wire one or bypass postForm in mock mode`
		);
	}

	const url = new URL(`${API_PREFIX}${endpointDef.url}${suffix ?? ''}`, BASE_URL);
	appendParams(url, params);

	// Headers are rebuilt per attempt so the retry carries the fresh token.
	const doFetch = (signal: AbortSignal): Promise<Response> => {
		const headers = new Headers();
		if (authToken) {
			headers.set('Authorization', `Bearer ${authToken}`);
		}
		return fetchWith401Retry(() =>
			fetch(url.toString(), {
				method: 'POST',
				headers,
				body: form,
				credentials: 'include',
				signal
			})
		);
	};

	const response = await fetchWithTimeout(doFetch, opts?.timeoutMs ?? DEFAULT_TIMEOUT_MS, opts?.signal ?? null);

	if (!response.ok) {
		throw await parseError(response);
	}

	if (response.status === 204) {
		return undefined as T;
	}

	try {
		return (await response.json()) as T;
	} catch {
		throw new APIError(
			'request_failed',
			'Invalid response from the server. Please try again.',
			undefined,
			response.status
		);
	}
};

// Central registry for raw text/blob routes. These return text/csv or binary
// rather than JSON, so they cannot use the typed EndpointDef registry in
// endpoints.ts — but every path still lives here, so a contract rename breaks
// at the import site instead of hiding in scattered string literals.
export const TEXT_EXPORTS = {
	studentTemplate: '/admin/students/import/template',
	programTemplate: '/admin/programs/import/template',
	courseTemplate: '/admin/courses/import/template',
	studentHistory: '/student/attendance/history/export',
	adminOverview: '/admin/attendance/overview/export',
	adminAnalytics: '/admin/analytics/export',
	professorReports: '/professor/reports/export',
} as const;

export const backupDownloadPath = (id: number): string => `/admin/backups/${id}/download`;

// Raw-text download for CSV templates (TEXT_EXPORTS.studentTemplate) and
// filtered CSV exports (TEXT_EXPORTS.adminOverview). Returns the CSV text
// for client-side download; the path comes from TEXT_EXPORTS above.
export const getText = async (
	path: string,
	params?: QueryParams,
	opts?: { timeoutMs?: number; signal?: AbortSignal | null; cacheTtlMs?: number }
): Promise<string> => {
	if (MOCK) {
		throw new APIError('mock_mode', 'Server CSV download is unavailable in mock mode');
	}

	const url = new URL(`${API_PREFIX}${path}`, BASE_URL);
	appendParams(url, params);

	const response = await fetchWithTimeout(
		(signal) => fetchWith401Retry(() => fetchWithAuth(url.toString(), { method: 'GET', signal })),
		opts?.timeoutMs ?? DEFAULT_TIMEOUT_MS,
		opts?.signal ?? null
	);

	if (!response.ok) {
		throw await parseError(response);
	}

	if (response.status === 204) return '';

	return response.text();
};

// Raw-text POST for CSV exports (TEXT_EXPORTS.professorReports). The export
// route takes a JSON filter body and returns text/csv, so it fits neither
// apiCall (JSON response) nor getText (GET). Auth header + 401-refresh reuse
// fetchWithAuth; the path comes from TEXT_EXPORTS above.
export const postText = async (
	path: string,
	body: unknown,
	opts?: { timeoutMs?: number; signal?: AbortSignal | null; cacheTtlMs?: number }
): Promise<string> => {
	if (MOCK) {
		throw new APIError('mock_mode', 'Server CSV export is unavailable in mock mode');
	}

	const url = new URL(`${API_PREFIX}${path}`, BASE_URL);

	const response = await fetchWithTimeout(
		(signal) =>
			fetchWith401Retry(() =>
				fetchWithAuth(url.toString(), {
					method: 'POST',
					body: JSON.stringify(body),
					signal
				})
			),
		opts?.timeoutMs ?? DEFAULT_TIMEOUT_MS,
		opts?.signal ?? null
	);

	if (!response.ok) {
		throw await parseError(response);
	}

	if (response.status === 204) return '';

	return response.text();
};

// Binary download for encrypted backup archives
// (backupDownloadPath(id) → application/octet-stream with a
// Content-Disposition filename). getText cannot handle binary, so this fetches
// a Blob and parses the filename header instead.
export const getBlob = async (
	path: string,
	params?: QueryParams,
	opts?: { timeoutMs?: number; signal?: AbortSignal | null; cacheTtlMs?: number }
): Promise<{ blob: Blob; filename: string }> => {
	if (MOCK) {
		throw new APIError('mock_mode', 'Server file download is unavailable in mock mode');
	}

	const url = new URL(`${API_PREFIX}${path}`, BASE_URL);
	appendParams(url, params);

	const response = await fetchWithTimeout(
		(signal) => fetchWith401Retry(() => fetchWithAuth(url.toString(), { method: 'GET', signal })),
		opts?.timeoutMs ?? DEFAULT_TIMEOUT_MS,
		opts?.signal ?? null
	);

	if (!response.ok) {
		throw await parseError(response);
	}

	const blob = await response.blob();
	const disposition = response.headers.get('content-disposition') ?? '';
	const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
	const filename = match?.[1] ? decodeURIComponent(match[1].trim()) : path.split('/').pop() ?? 'download';
	return { blob, filename };
};
