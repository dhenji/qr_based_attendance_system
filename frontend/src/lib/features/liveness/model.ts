// features/liveness/model.ts
// MediaPipe FaceLandmarker singleton: downloads the wasm runtime + the .task
// model once per session and shares the instance across scans, so the heavy
// ~13 MB load never repeats. Call initFaceModel() early to warm it up.

import type { FaceLandmarker } from '@mediapipe/tasks-vision';

// Connection pairs used to draw the face wireframe overlay.
export interface FaceConnections {
	faceOval: Array<{ start: number; end: number }>;
	leftEye: Array<{ start: number; end: number }>;
	rightEye: Array<{ start: number; end: number }>;
}

export interface LoadedFaceModel {
	landmarker: FaceLandmarker;
	connections: FaceConnections;
	DrawingUtils: typeof import('@mediapipe/tasks-vision').DrawingUtils;
}

let ready: Promise<LoadedFaceModel> | null = null;

// Returns the shared load promise. Idempotent — every caller awaits the same
// in-flight load, and a failed load resets so the next call retries.
export const initFaceModel = (): Promise<LoadedFaceModel> => {
	if (!ready) {
		ready = load().catch((err) => {
			ready = null;
			throw err;
		});
	}
	return ready;
};

// load: fetch the wasm fileset, then create the landmarker GPU-first.
const load = async (): Promise<LoadedFaceModel> => {
	const { FilesetResolver, FaceLandmarker, DrawingUtils } = await import('@mediapipe/tasks-vision');

	const fileset = await FilesetResolver.forVisionTasks('/wasm');

	// Prefer the GPU delegate; some devices throw, so fall back to CPU.
	const createWithDelegate = (delegate: 'GPU' | 'CPU') =>
		FaceLandmarker.createFromOptions(fileset, {
			baseOptions: { modelAssetPath: '/models/face_landmarker.task', delegate },
			runningMode: 'VIDEO',
			numFaces: 1,
			minFaceDetectionConfidence: 0.5,
			minFacePresenceConfidence: 0.5,
			minTrackingConfidence: 0.5,
		});

	let landmarker: FaceLandmarker;
	try {
		landmarker = await createWithDelegate('GPU');
	} catch {
		landmarker = await createWithDelegate('CPU');
	}

	return {
		landmarker,
		connections: {
			faceOval: FaceLandmarker.FACE_LANDMARKS_FACE_OVAL,
			leftEye: FaceLandmarker.FACE_LANDMARKS_LEFT_EYE,
			rightEye: FaceLandmarker.FACE_LANDMARKS_RIGHT_EYE,
		},
		DrawingUtils,
	};
};