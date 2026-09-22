<script lang="ts">
	import { onDestroy } from 'svelte';
	import type { NormalizedLandmark, DrawingOptions } from '@mediapipe/tasks-vision';

	interface FaceConnection {
		start: number;
		end: number;
	}

	let { active, onBlink } = $props<{ active: boolean; onBlink: () => void }>();

	let stage: HTMLDivElement;
	let video: HTMLVideoElement;
	let canvas: HTMLCanvasElement;

	type FaceStatus = 'initializing' | 'no_face' | 'looking' | 'detecting' | 'passed';

	let status = $state<FaceStatus>('initializing');
	let error = $state<string | null>(null);

	let landmarker: {
		detectForVideo(video: HTMLVideoElement, now: number): FaceResult;
		close(): void;
	} | null = null;
	let drawing: {
		drawConnectors(
			landmarks?: NormalizedLandmark[],
			connections?: FaceConnection[],
			style?: DrawingOptions
		): void;
	} | null = null;
	let faceOval: FaceConnection[] = [];
	let leftEye: FaceConnection[] = [];
	let rightEye: FaceConnection[] = [];
	let stream: MediaStream | null = null;
	let rafId = 0;
	let lastVideoTime = -1;
	let closedFrames = 0;
	let blinkFired = false;

	interface FaceResult {
		faceLandmarks?: NormalizedLandmark[][];
	}

	// MediaPipe FaceLandmarker (478 landmarks) EAR indices
	const LEFT_EYE = [362, 385, 387, 263, 373, 380];
	const RIGHT_EYE = [33, 160, 158, 133, 153, 144];
	const EAR_THRESHOLD = 0.25; // D31: EAR < 0.25 counts as eye closed
	const CLOSED_FRAMES_REQUIRED = 3;

	const pointDist = (lm: Array<{ x: number; y: number }>, i: number, j: number) =>
		Math.hypot(lm[i].x - lm[j].x, lm[i].y - lm[j].y);

	// EAR = (d(p1,p5) + d(p2,p4)) / (2 * d(p0,p3))
	const eyeEar = (lm: Array<{ x: number; y: number }>, eye: number[]) =>
		(pointDist(lm, eye[1], eye[5]) + pointDist(lm, eye[2], eye[4])) / (2 * pointDist(lm, eye[0], eye[3]));

	const hintText = $derived.by(() => {
		switch (status) {
			case 'initializing':
				return 'Loading face model\u2026';
			case 'no_face':
				return 'Look at the camera: face not detected';
			case 'looking':
				return 'Look at the camera and blink once';
			case 'detecting':
				return 'Blink detected \u2014 verifying\u2026';
			case 'passed':
				return 'Verified';
			default:
				return '';
		}
	});

	$effect(() => {
		if (active) {
			start();
		} else {
			stop();
		}
	});

	onDestroy(() => {
		stop();
	});

	const start = async () => {
		error = null;
		blinkFired = false;
		closedFrames = 0;
		lastVideoTime = -1;
		status = 'initializing';

		try {
			const mod = await import('@mediapipe/tasks-vision');
			const { FilesetResolver, FaceLandmarker, DrawingUtils } = mod;

			faceOval = FaceLandmarker.FACE_LANDMARKS_FACE_OVAL;
			leftEye = FaceLandmarker.FACE_LANDMARKS_LEFT_EYE;
			rightEye = FaceLandmarker.FACE_LANDMARKS_RIGHT_EYE;

			const fileset = await FilesetResolver.forVisionTasks('/wasm');

			const createWithDelegate = (delegate: 'GPU' | 'CPU') =>
				FaceLandmarker.createFromOptions(fileset, {
					baseOptions: { modelAssetPath: '/models/face_landmarker.task', delegate },
					runningMode: 'VIDEO',
					numFaces: 1,
					minFaceDetectionConfidence: 0.5,
					minFacePresenceConfidence: 0.5,
					minTrackingConfidence: 0.5,
				});

			try {
				landmarker = await createWithDelegate('GPU');
			} catch {
				landmarker = await createWithDelegate('CPU');
			}

			stream = await navigator.mediaDevices.getUserMedia({
				video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
				audio: false,
			});
			video.srcObject = stream;
			await video.play();

			const tick = () => {
				if (!landmarker || video.readyState < 2) {
					rafId = requestAnimationFrame(tick);
					return;
				}
				if (video.videoWidth && canvas.width !== video.videoWidth) {
					canvas.width = video.videoWidth;
					canvas.height = video.videoHeight;
					stage.style.aspectRatio = `${video.videoWidth} / ${video.videoHeight}`;
					if (!drawing) {
						drawing = new DrawingUtils(canvas.getContext('2d') as CanvasRenderingContext2D);
					}
				}
				if (video.currentTime !== lastVideoTime) {
					lastVideoTime = video.currentTime;
					const result = landmarker.detectForVideo(video, performance.now());
					draw(result);
					evaluate(result);
				}
				rafId = requestAnimationFrame(tick);
			};
			rafId = requestAnimationFrame(tick);
			status = 'no_face';
		} catch (err) {
			stop();
			if (err instanceof Error && err.name === 'NotAllowedError') {
				error = 'Camera access blocked. Allow camera access and retry.';
			} else {
				error = err instanceof Error ? err.message : 'Failed to start face scanner';
			}
		}
	};

	const draw = (result: FaceResult) => {
		if (!result.faceLandmarks?.length || !drawing) return;
		const ctx = canvas.getContext('2d');
		if (!ctx) return;
		ctx.clearRect(0, 0, canvas.width, canvas.height);
		const lm = result.faceLandmarks[0];
		drawing.drawConnectors(lm, faceOval, { color: '#94a3b8', lineWidth: 2 });
		drawing.drawConnectors(lm, leftEye, { color: '#4f9cf9', lineWidth: 2 });
		drawing.drawConnectors(lm, rightEye, { color: '#4f9cf9', lineWidth: 2 });
	};

	const evaluate = (result: FaceResult) => {
		if (!result.faceLandmarks?.length) {
			closedFrames = 0;
			status = 'no_face';
			return;
		}
		const lm = result.faceLandmarks[0];
		const avgEar = (eyeEar(lm, LEFT_EYE) + eyeEar(lm, RIGHT_EYE)) / 2;

		if (avgEar < EAR_THRESHOLD) {
			closedFrames += 1;
			status = 'detecting';
			if (!blinkFired && closedFrames >= CLOSED_FRAMES_REQUIRED) {
				blinkFired = true;
				status = 'passed';
				onBlink();
			}
		} else {
			closedFrames = 0;
			status = 'looking';
		}
	};

	const stop = () => {
		cancelAnimationFrame(rafId);
		rafId = 0;
		stream?.getTracks().forEach((t) => t.stop());
		stream = null;
		if (video) video.srcObject = null;
		landmarker?.close();
		landmarker = null;
		drawing = null;
		faceOval = [];
		leftEye = [];
		rightEye = [];
	};
</script>

<div class="scanner">
	<div class="stage" bind:this={stage}>
		<video bind:this={video} autoplay muted playsinline></video>
		<canvas bind:this={canvas}></canvas>
		{#if !error}
			<div class="hint" class:passed={status === 'passed'}>{hintText}</div>
		{/if}
	</div>
	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}
</div>

<style>
	.scanner {
		position: relative;
		width: 100%;
		height: 100%;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
	}

	.stage {
		position: relative;
		height: 100%;
		aspect-ratio: 4 / 3;
	}

	video,
	canvas {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: fill;
		border-radius: 10px;
	}

	.hint {
		position: absolute;
		left: 0;
		right: 0;
		bottom: 0.75rem;
		text-align: center;
		color: rgba(255, 255, 255, 0.9);
		background: rgba(15, 23, 42, 0.6);
		padding: 0.375rem 0.875rem;
		font-size: 0.8125rem;
		border-radius: 99px;
		width: fit-content;
		margin: 0 auto;
		pointer-events: none;
	}

	.hint.passed {
		background: rgba(22, 163, 74, 0.85);
		color: white;
		font-weight: 600;
	}

	.error {
		color: #fecaca;
		background: rgba(127, 29, 29, 0.7);
		border-radius: 8px;
		padding: 0.5rem 0.875rem;
		font-size: 0.8125rem;
		text-align: center;
		max-width: 90%;
		margin: 0.75rem auto 0;
	}
</style>