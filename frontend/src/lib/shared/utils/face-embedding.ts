// Face embedding serialization utilities
// Must match backend format: FACEEMB1 header + algorithm + float32 array

const MAGIC = 'FACEEMB1';
export const EMBEDDING_DIM = 128;

export function l2Normalize(vec: Float32Array | number[]): Float32Array {
	const arr = vec instanceof Float32Array ? vec : new Float32Array(vec);
	let norm = 0;
	for (let i = 0; i < arr.length; i++) {
		norm += arr[i] * arr[i];
	}
	norm = Math.sqrt(norm);
	if (norm === 0 || !isFinite(norm)) {
		return new Float32Array(arr);
	}
	const out = new Float32Array(arr.length);
	for (let i = 0; i < arr.length; i++) {
		out[i] = arr[i] / norm;
	}
	return out;
}

export function serializeFaceEmbedding(
	embedding: Float32Array | number[],
	algorithm = 'mediapipe-v1',
	version = 1
): string {
	const emb = l2Normalize(embedding);
	// Ensure dimension
	const dim = emb.length;
	const algoBytes = new TextEncoder().encode(algorithm);
	
	// Header: magic(8) + ver(1) + algoLen(2, big endian) + dim(4, big endian)
	const buffer = new ArrayBuffer(8 + 1 + 2 + 4 + algoBytes.length + dim * 4);
	const view = new DataView(buffer);
	
	// Write magic
	const magicBytes = new TextEncoder().encode(MAGIC);
	for (let i = 0; i < 8; i++) {
		view.setUint8(i, magicBytes[i]);
	}
	
	let offset = 8;
	view.setUint8(offset++, version & 0xff);
	view.setUint16(offset, algoBytes.length, false); // big endian
	offset += 2;
	view.setUint32(offset, dim, false); // big endian
	offset += 4;
	
	// Write algorithm
	for (let i = 0; i < algoBytes.length; i++) {
		view.setUint8(offset++, algoBytes[i]);
	}
	
	// Write float32 array
	for (let i = 0; i < dim; i++) {
		view.setFloat32(offset, emb[i], false); // big endian to match backend? backend uses struct '>...' big endian
		offset += 4;
	}
	
	// Convert to base64
	const bytes = new Uint8Array(buffer);
	let binary = '';
	for (let i = 0; i < bytes.byteLength; i++) {
		binary += String.fromCharCode(bytes[i]);
	}
	return btoa(binary);
}

export function generateEmbeddingFromLandmarks(landmarks: any[]): Float32Array {
	if (!landmarks || landmarks.length === 0) {
		// Return zero vector if no landmarks
		return new Float32Array(EMBEDDING_DIM);
	}
	
	const lm = landmarks[0];
	const vec: number[] = [];
	
	// Use first EMBEDDING_DIM landmark coordinates (like backend fallback)
	for (let i = 0; i < EMBEDDING_DIM && i < lm.length; i++) {
		const landmark = lm[i];
		// Use x, y, z if available
		if (landmark.z !== undefined) {
			vec.push(landmark.x || 0, landmark.y || 0, landmark.z || 0);
		} else {
			vec.push(landmark.x || 0, landmark.y || 0, 0);
		}
	}
	
	// If we don't have enough values, pad with zeros
	while (vec.length < EMBEDDING_DIM) {
		vec.push(0);
	}
	
	return l2Normalize(vec.slice(0, EMBEDDING_DIM));
}
