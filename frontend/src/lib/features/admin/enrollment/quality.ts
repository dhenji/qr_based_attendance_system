// Client-side quality checks for uploaded face-enrollment photos.
// Mirrors the backend thresholds in shared/face_quality.py. These are
// usability hints only; the backend re-validates authoritatively.

export type FacePhotoQualityResult = { ok: boolean; reason?: string };

const BRIGHTNESS_MIN = 40;
const BRIGHTNESS_MAX = 220;
const SHARPNESS_MIN = 50;
const MIN_DIMENSION = 160;

export async function validateFacePhoto(file: File): Promise<FacePhotoQualityResult> {
	if (file.size === 0) return { ok: false, reason: 'Photo is empty' };

	let bitmap: ImageBitmap;
	try {
		bitmap = await createImageBitmap(file);
	} catch {
		return { ok: false, reason: 'Photo could not be decoded. Use JPG, PNG, or WebP.' };
	}

	if (bitmap.width < MIN_DIMENSION || bitmap.height < MIN_DIMENSION) {
		bitmap.close();
		return {
			ok: false,
			reason: 'Image resolution is too low. Use a higher-resolution photo.',
		};
	}

	const canvas = document.createElement('canvas');
	canvas.width = bitmap.width;
	canvas.height = bitmap.height;
	const ctx = canvas.getContext('2d');
	if (!ctx) {
		bitmap.close();
		return { ok: true };
	}
	ctx.drawImage(bitmap, 0, 0);
	const data = ctx.getImageData(0, 0, bitmap.width, bitmap.height).data;
	bitmap.close();

	// Brightness (luminance average).
	let lumSum = 0;
	const pixelCount = data.length / 4;
	for (let i = 0; i < data.length; i += 4) {
		lumSum += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
	}
	const brightness = pixelCount > 0 ? lumSum / pixelCount : 128;
	if (brightness < BRIGHTNESS_MIN) {
		return { ok: false, reason: 'Image is too dark. Improve the lighting and try again.' };
	}
	if (brightness > BRIGHTNESS_MAX) {
		return { ok: false, reason: 'Image is too bright. Reduce lighting and try again.' };
	}

	// Sharpness (Laplacian variance) on a downscaled grayscale copy.
	const scale = Math.min(1, 512 / Math.max(bitmap.width, bitmap.height));
	// bitmap already closed; recompute dimensions from canvas
	const w = Math.max(1, Math.round(canvas.width * scale));
	const h = Math.max(1, Math.round(canvas.height * scale));
	const small = document.createElement('canvas');
	small.width = w;
	small.height = h;
	const sctx = small.getContext('2d');
	if (!sctx) return { ok: true };
	sctx.drawImage(canvas, 0, 0, w, h);
	const sdata = sctx.getImageData(0, 0, w, h).data;
	const gray = new Float32Array(w * h);
	for (let i = 0, j = 0; i < sdata.length; i += 4, j++) {
		gray[j] = 0.299 * sdata[i] + 0.587 * sdata[i + 1] + 0.114 * sdata[i + 2];
	}
	let sum = 0;
	let sumSq = 0;
	let count = 0;
	for (let y = 1; y < h - 1; y++) {
		for (let x = 1; x < w - 1; x++) {
			const idx = y * w + x;
			const lap = gray[idx - w] + gray[idx + w] + gray[idx - 1] + gray[idx + 1] - 4 * gray[idx];
			sum += lap;
			sumSq += lap * lap;
			count++;
		}
	}
	const variance = count > 0 ? sumSq / count - (sum / count) ** 2 : SHARPNESS_MIN;
	if (variance < SHARPNESS_MIN) {
		return { ok: false, reason: 'The image is blurry. Hold still and try again.' };
	}

	return { ok: true };
}
