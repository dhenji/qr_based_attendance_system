// features/excuse/attachments.ts
// Excuse-evidence upload helpers (D24 presigned flow).
//
// Files never pass through the API: the client mints a URL per file via
// POST /upload/presigned-url, PUTs the bytes to upload_url itself, then
// submits the excuse carrying the returned object_urls. Constraints mirror
// api-contracts.md §Attachment Uploads: max 5 files, 5 MiB each,
// PDF/JPG/PNG/HEIC by extension (case-insensitive).

import { isMockMode, post } from '$lib/api/client';
import type { PresignedUrlResponse } from '$lib/api/endpoints';

export const ATTACHMENTS_MAX_FILES = 5;
export const ATTACHMENTS_MAX_BYTES = 5 * 1024 * 1024;
const ALLOWED_EXTENSIONS = new Set(['pdf', 'jpg', 'jpeg', 'png', 'heic']);

// Expected MIME per extension. file.type is checked only when non-empty —
// an empty type still passes here (the server re-validates); a non-empty
// mismatch (e.g. text/plain renamed to .pdf) is rejected early.
const MIME_FOR_EXTENSION: Record<string, Set<string>> = {
	pdf: new Set(['application/pdf']),
	jpg: new Set(['image/jpeg']),
	jpeg: new Set(['image/jpeg']),
	png: new Set(['image/png']),
	heic: new Set(['image/heic', 'image/heif']),
};

export const attachmentExtension = (filename: string): string => {
	const dot = filename.lastIndexOf('.');
	return dot === -1 ? '' : filename.slice(dot + 1).toLowerCase();
};

const contentTypeFor = (extension: string, fallback: string): string => {
	if (fallback) return fallback;
	switch (extension) {
		case 'pdf':
			return 'application/pdf';
		case 'jpg':
		case 'jpeg':
			return 'image/jpeg';
		case 'png':
			return 'image/png';
		case 'heic':
			return 'image/heic';
		default:
			return 'application/octet-stream';
	}
};

export type AttachmentValidation = {
	valid: File[];
	errors: string[];
};

// validateAttachmentFiles
// Filters a FileList/array down to uploadable files. Returns per-file error
// strings for the rejected ones so the picker can render them inline.
export const validateAttachmentFiles = (files: File[] | FileList): AttachmentValidation => {
	const list = Array.from(files);
	const valid: File[] = [];
	const errors: string[] = [];
	for (const file of list) {
		if (valid.length >= ATTACHMENTS_MAX_FILES) {
			errors.push(`${file.name}: at most ${ATTACHMENTS_MAX_FILES} files per request.`);
			continue;
		}
		const extension = attachmentExtension(file.name);
		if (!ALLOWED_EXTENSIONS.has(extension)) {
			errors.push(`${file.name}: only PDF, JPG, PNG, or HEIC files are accepted.`);
			continue;
		}
		if (file.type) {
			const allowed = MIME_FOR_EXTENSION[extension];
			if (allowed && !allowed.has(file.type.toLowerCase())) {
				errors.push(`${file.name}: file type does not match its extension.`);
				continue;
			}
		}
		if (file.size <= 0) {
			errors.push(`${file.name}: file is empty.`);
			continue;
		}
		if (file.size > ATTACHMENTS_MAX_BYTES) {
			errors.push(`${file.name}: exceeds the 5 MiB limit.`);
			continue;
		}
		valid.push(file);
	}
	return { valid, errors };
};

// uploadAttachments
// Mints a presigned URL per file and PUTs the bytes, returning per-file
// results so one transient failure never discards prior successes. Uploads
// run with limited concurrency (default 3) with an optional progress
// callback. In mock mode the PUT is skipped (mock upload_urls are not
// fetchable) and the mock object_urls are returned.
export type AttachmentUploadFailure = {
	file: File;
	message: string;
};

export type AttachmentUploadResult = {
	ok: string[];
	failed: AttachmentUploadFailure[];
};

export type UploadProgress = (done: number, total: number) => void;

// Bounded PUT: a hung proxy connection otherwise never settles, wedging one
// worker slot (and the excuse modal's Submit progress with it) forever.
const UPLOAD_TIMEOUT_MS = 60_000;

const uploadOne = async (file: File): Promise<string> => {
	const extension = attachmentExtension(file.name);
	const minted = await post<PresignedUrlResponse>('uploadPresigned', {
		filename: file.name,
		size_bytes: file.size,
		content_type: contentTypeFor(extension, file.type),
	});
	if (!isMockMode()) {
		const controller = new AbortController();
		const timer = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS);
		try {
			const response = await fetch(minted.upload_url, {
				method: 'PUT',
				body: file,
				headers: { 'Content-Type': contentTypeFor(extension, file.type) },
				signal: controller.signal,
			});
			if (!response.ok) {
				throw new Error(`${file.name}: upload failed (${response.status}).`);
			}
		} catch (error: unknown) {
			if (error instanceof DOMException && error.name === 'AbortError') {
				throw new Error(`${file.name}: upload timed out — try again.`);
			}
			throw error;
		} finally {
			clearTimeout(timer);
		}
	}
	return minted.object_url;
};

export const uploadAttachments = async (
	files: File[],
	opts: { concurrency?: number; onProgress?: UploadProgress } = {}
): Promise<AttachmentUploadResult> => {
	const total = files.length;
	if (total === 0) return { ok: [], failed: [] };
	const concurrency = Math.max(1, Math.min(opts.concurrency ?? 3, total));
	const urls: (string | null)[] = new Array(total).fill(null);
	const failures: (AttachmentUploadFailure | null)[] = new Array(total).fill(null);
	let done = 0;
	let next = 0;
	const worker = async (): Promise<void> => {
		while (true) {
			const index = next;
			next += 1;
			if (index >= total) return;
			try {
				urls[index] = await uploadOne(files[index]);
			} catch (error) {
				failures[index] = {
					file: files[index],
					message: error instanceof Error && error.message ? error.message : `${files[index].name}: upload failed.`,
				};
			}
			done += 1;
			opts.onProgress?.(done, total);
		}
	};
	await Promise.all(Array.from({ length: concurrency }, () => worker()));
	return {
		ok: urls.filter((url): url is string => url !== null),
		failed: failures.filter((f): f is AttachmentUploadFailure => f !== null),
	};
};
