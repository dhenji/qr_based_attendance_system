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
// Mints a presigned URL per file and PUTs the bytes, returning the object
// urls for the excuse submit body. In mock mode the PUT is skipped (mock
// upload_urls are not fetchable) and the mock object_urls are returned.
export const uploadAttachments = async (files: File[]): Promise<string[]> => {
	const objectUrls: string[] = [];
	for (const file of files) {
		const extension = attachmentExtension(file.name);
		const minted = await post<PresignedUrlResponse>('uploadPresigned', {
			filename: file.name,
			size_bytes: file.size,
			content_type: contentTypeFor(extension, file.type),
		});
		if (!isMockMode()) {
			const response = await fetch(minted.upload_url, {
				method: 'PUT',
				body: file,
				headers: { 'Content-Type': contentTypeFor(extension, file.type) },
			});
			if (!response.ok) {
				throw new Error(`${file.name}: upload failed (${response.status}).`);
			}
		}
		objectUrls.push(minted.object_url);
	}
	return objectUrls;
};
