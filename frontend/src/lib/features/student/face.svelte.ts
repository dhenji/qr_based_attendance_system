// features/student/face.svelte.ts
// Face-embedding pull + encrypted cache (D29, offline-first.md §face_embeddings).
//
// Version-gated pull: GET /student/me/face-embedding?current_version=N.
// 200 carries a newer base64 blob; 204 (client resolves to undefined) means
// the cached version is current; 404 face_embedding_not_found means no
// enrollment on file, so the cache is cleared (revocation). Every other
// failure resolves to `unavailable` — the pull must never break login.
//
// At rest the blob is AES-GCM encrypted under a non-extractable device key
// persisted as a CryptoKey in IndexedDB (structured-clone safe), generated
// once per device. Two tabs racing key creation is benign: last write wins
// and the loser re-pulls on its next login.
//
// Client-side embedding *compare* is a separate future slice: enrollment
// blobs are still server stubs with no documented decrypt scheme, so there
// is nothing meaningful to match against yet.

import { APIError, get, isMockMode } from '$lib/api/client';
import type { StudentFaceEmbeddingResponse } from '$lib/api/endpoints';
import { FACE_STORE, KEY_STORE, idbDelete, idbGet, idbPut } from '$lib/features/sync/service';

export type FaceCacheState = 'current' | 'updated' | 'absent' | 'unavailable';
export type FaceCacheResult = { state: FaceCacheState; version: number | null };

export type FaceCacheRow = {
	student: string;
	version: number;
	iv: string;
	ciphertext: string;
	fetched_at: string;
};

const DEVICE_KEY_ID = 'face-device-key';

export const faceCacheState = $state<FaceCacheResult>({ state: 'unavailable', version: null });

const toBase64 = (bytes: Uint8Array): string => {
	let text = '';
	for (let index = 0; index < bytes.length; index += 0x8000) {
		text += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
	}
	return btoa(text);
};

const getDeviceKey = async (): Promise<CryptoKey> => {
	const existing = await idbGet<{ id: string; key: CryptoKey }>(KEY_STORE, DEVICE_KEY_ID).catch(
		() => undefined
	);
	if (existing) return existing.key;
	const key = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, [
		'encrypt',
		'decrypt'
	]);
	await idbPut(KEY_STORE, { id: DEVICE_KEY_ID, key });
	return key;
};

const encryptBlob = async (
	key: CryptoKey,
	base64: string
): Promise<{ iv: string; ciphertext: string }> => {
	const iv = crypto.getRandomValues(new Uint8Array(12));
	const ciphertext = await crypto.subtle.encrypt(
		{ name: 'AES-GCM', iv },
		key,
		new TextEncoder().encode(base64)
	);
	return { iv: toBase64(iv), ciphertext: toBase64(new Uint8Array(ciphertext)) };
};

const readCachedVersion = async (student: string): Promise<number> => {
	const row = await idbGet<FaceCacheRow>(FACE_STORE, student).catch(() => undefined);
	return row?.version ?? 0;
};

// pullFaceEmbedding
// Version-gated pull keyed by account email (stable per account; the endpoint
// resolves identity from the JWT, so nothing identifying travels in the URL).
// Skip entirely when the account reports no enrollment — that pull would 404
// by design.
export const pullFaceEmbedding = async (
	student: string,
	faceEnrolled: boolean
): Promise<FaceCacheResult> => {
	if (
		!faceEnrolled ||
		isMockMode() ||
		typeof indexedDB === 'undefined' ||
		typeof crypto?.subtle === 'undefined'
	) {
		return { state: faceEnrolled ? 'unavailable' : 'absent', version: null };
	 }
	const currentVersion = await readCachedVersion(student).catch(() => 0);
	let response: StudentFaceEmbeddingResponse | undefined;
	try {
		response = await get<StudentFaceEmbeddingResponse | undefined>('studentFaceEmbedding', {
			current_version: String(currentVersion)
		});
	} catch (error) {
		// Only the exact not-enrolled code clears the cache: any other 404
		// (or network failure) leaves the last good blob alone.
		if (error instanceof APIError && error.code === 'face_embedding_not_found') {
			await idbDelete(FACE_STORE, student).catch(() => undefined);
			return { state: 'absent', version: null };
		}
		return { state: 'unavailable', version: currentVersion > 0 ? currentVersion : null };
	}
	if (!response) return { state: 'current', version: currentVersion };
	try {
		const key = await getDeviceKey();
		const { iv, ciphertext } = await encryptBlob(key, response.embedding);
		await idbPut(FACE_STORE, {
			student,
			version: response.version,
			iv,
			ciphertext,
			fetched_at: new Date().toISOString()
		} satisfies FaceCacheRow);
		return { state: 'updated', version: response.version };
	} catch {
		return { state: 'unavailable', version: currentVersion > 0 ? currentVersion : null };
	}
};

// refreshFaceCache
// Fire-and-forget entry for the auth session hook: pulls, then publishes the
// outcome for the profile indicator. Never rejects.
export const refreshFaceCache = async (student: string, faceEnrolled: boolean): Promise<void> => {
	try {
		const result = await pullFaceEmbedding(student, faceEnrolled);
		faceCacheState.state = result.state;
		faceCacheState.version = result.version;
	} catch {
		faceCacheState.state = 'unavailable';
		faceCacheState.version = null;
	}
};
