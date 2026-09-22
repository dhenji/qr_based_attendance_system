<script lang="ts">
	// FaceScanner
	// Liveness check via MediaPipe FaceLandmarker (478 landmarks).
	// Tracks the user's blink in real time and fires `onBlink` once a single
	// blink is confirmed (D31: Eye Aspect Ratio below 0.25 across N frames).
	import { onDestroy } from 'svelte';
	import type { NormalizedLandmark, DrawingOptions } from '@mediapipe/tasks-vision';
	import { initFaceModel, type LoadedFaceModel } from '$lib/features/liveness/model';

	interface FaceConnection {
		start: number;
		end: number;
	}

	let { active, onBlink } = $props<{ active: boolean; onBlink: () => void }>();

	let stage: HTMLDivElement;
	let video: HTMLVideoElement;
	let canvas: HTMLCanvasElement;

	type FaceStatus =
		| 'initializing'
		| 'no_face'
		| 'too_far'
		| 'center_face'
		| 'looking'
		| 'detecting'
		| 'passed';

	let status = $state<FaceStatus>('initializing');
	let error = $state<string | null>(null);

	// Face-guide oval position/size in normalized video space (0..1).
	// MediaPipe landmarks are normalized over the video, and the video fills
	// the stage 1:1 (object-fit: fill), so the same coordinates work for both.
	const GUIDE_CX = 0.5;
	const GUIDE_CY = 0.5;
	const GUIDE_RX = 0.275;
	const GUIDE_RY = 0.4;

	// Distance cap: a face smaller than this is treated as too far to read.
	// Monocular cameras can't give an exact metric distance, so this uses the
	// pinhole model (distance = IPD / (2 * eyeSpread * tan(HFOV / 2))). IPD is
	// the average adult inter-pupillary distance and HFOV is a typical phone
	// front camera's horizontal field of view — both tunable per device.
	const IPD_M = 0.063;
	const FRONT_CAM_HFOV_DEG = 70;
	const MAX_FACE_DISTANCE_M = 0.5;

	let countdown = $state(0);
	let beginDetection = $state(false);
	let countdownTimerId: ReturnType<typeof setInterval> | null = null;

	// Live handles: landmarker for detection, drawing for the overlay renderer.
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
	// Canvas-overlay renderer constructor, shared with the warm model.
	let drawingCtor: LoadedFaceModel['DrawingUtils'] | null = null;
	let faceOval: FaceConnection[] = [];
	let leftEye: FaceConnection[] = [];
	let rightEye: FaceConnection[] = [];
	let stream: MediaStream | null = null;
	let rafId = 0;
	let lastVideoTime = -1;
	let closedFrames = 0;
	let blinkFired = false;
	// EMA-smoothed EAR; damps single-frame landmark jitter.
	let smoothedEar = 1;
	// Per-user open-eye baseline and closing-phase bookkeeping for blink math.
	let earBaseline: number | null = null;
	let idleFrames = 0;
	let blinkMinEar = 1;

	interface FaceResult {
		faceLandmarks?: NormalizedLandmark[][];
	}

	// Blink math (Eye Aspect Ratio)
	// MediaPipe FaceLandmarker (478 landmarks) EAR indices
	const LEFT_EYE = [362, 385, 387, 263, 373, 380];
	const RIGHT_EYE = [33, 160, 158, 133, 153, 144];
	const EYE_SMOOTH = 0.5; // light smoothing (was a heavy 0.7 EMA)
	const BLINK_DEPTH = 0.55; // closure = EAR below baseline x 0.55
	const RECOVER_LEVEL = 0.85; // reopen = EAR above baseline x 0.85
	const MIN_CLOSED_FRAMES = 2; // min sampled closure frames
	const MAX_BLINK_FRAMES = 20; // ~0.7s: longer closure = squint, reset
	const ARMING_FRAMES = 8; // idle frames before the baseline is trusted

	// Euclidean distance between two landmarks.
	const pointDist = (lm: Array<{ x: number; y: number }>, i: number, j: number) =>
		Math.hypot(lm[i].x - lm[j].x, lm[i].y - lm[j].y);

	// EAR = (d(p1,p5) + d(p2,p4)) / (2 * d(p0,p3)) — ratio shrinks when the eye closes.
	const eyeEar = (lm: Array<{ x: number; y: number }>, eye: number[]) =>
		(pointDist(lm, eye[1], eye[5]) + pointDist(lm, eye[2], eye[4])) / (2 * pointDist(lm, eye[0], eye[3]));

	// Centroid of the full 478-point face mesh.
	const faceCenter = (lm: Array<{ x: number; y: number }>) => {
		let cx = 0;
		let cy = 0;
		for (const p of lm) {
			cx += p.x;
			cy += p.y;
		}
		return { x: cx / lm.length, y: cy / lm.length };
	};

	// Elliptical containment test: face is "in the guide" when its center
	// sits inside the oval. Blink detection is skipped otherwise.
	const isInsideGuide = (lm: Array<{ x: number; y: number }>) => {
		const c = faceCenter(lm);
		const dx = (c.x - GUIDE_CX) / GUIDE_RX;
		const dy = (c.y - GUIDE_CY) / GUIDE_RY;
		return dx * dx + dy * dy <= 1;
	};

	// Estimated face-to-camera distance in meters from the inter-eye spread in
	// the frame (landmarks 33 and 263 are the outer eye corners). Monocular
	// depth is ambiguous without a known focal length, so the horizontal field
	// of view is assumed — see FRONT_CAM_HFOV_DEG.
	const faceDistanceM = (lm: Array<{ x: number; y: number }>) => {
		const eyeSpread = Math.abs(lm[263].x - lm[33].x);
		const halfFovRad = (FRONT_CAM_HFOV_DEG * Math.PI) / 360;
		return IPD_M / (2 * eyeSpread * Math.tan(halfFovRad));
	};

	// Per-status instruction shown to the user before detection begins.
	const preHintText = $derived(countdown > 0 ? `Get ready \u2026 ${countdown}` : 'Face model loading\u2026');

	// Per-status instruction shown to the user.
	const hintText = $derived.by(() => {
		if (!beginDetection) {
			switch (status) {
				case 'initializing':
					return 'Loading face model\u2026';
				default:
					return preHintText;
			}
		}
		switch (status) {
			case 'no_face':
				return 'Look at the camera: face not detected';
			case 'too_far':
				return 'Move closer to the camera (max ~0.5 m)';
			case 'center_face':
				return 'Center your face in the oval';
			case 'looking':
				return 'Look at the camera and blink once';
			case 'detecting':
				return 'Eyes closing \u2014 blink fully\u2026';
			case 'passed':
				return 'Verified';
			default:
				return '';
		}
	});

	// True once the face is tracked inside the guide oval — turns the guide green.
	const aligned = $derived(
		beginDetection &&
			status !== 'no_face' &&
			status !== 'too_far' &&
			status !== 'center_face' &&
			status !== 'initializing'
	);

	// Start/stop the scanner when the `active` prop toggles.
	$effect(() => {
		if (active) {
			start();
		} else {
			stop();
		}
	});

	// Guarantee no camera/model leaks when the component is removed.
	onDestroy(() => {
		clearCountdown();
		stop();
	});

	const clearCountdown = () => {
		if (countdownTimerId) {
			clearInterval(countdownTimerId);
			countdownTimerId = null;
		}
	};

	const startCountdown = () => {
		clearCountdown();
		beginDetection = false;
		countdown = 3;
		countdownTimerId = setInterval(() => {
			countdown -= 1;
			if (countdown <= 0) {
				clearCountdown();
				beginDetection = true;
			}
		}, 1000);
	};

	// start
	// Boot sequence: reuse the shared warm landmarker, open the front camera,
	// then loop detection per frame.
	const start = async () => {
		error = null;
		blinkFired = false;
		closedFrames = 0;
		smoothedEar = 1;
		earBaseline = null;
		idleFrames = 0;
		blinkMinEar = 1;
		lastVideoTime = -1;
		status = 'initializing';
		beginDetection = false;
		clearCountdown();

		try {
			// Grab the pre-warmed model instance — no re-download or re-compile.
			const loaded = await initFaceModel();
			landmarker = loaded.landmarker;
			faceOval = loaded.connections.faceOval;
			leftEye = loaded.connections.leftEye;
			rightEye = loaded.connections.rightEye;
			drawingCtor = loaded.DrawingUtils;

			// Front-facing selfie camera, no audio.
			stream = await navigator.mediaDevices.getUserMedia({
				video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
				audio: false,
			});
			video.srcObject = stream;
			await video.play();

			// Per-frame render loop: only detect when fresh frame data arrives.
			const tick = () => {
				if (!landmarker || video.readyState < 2) {
					rafId = requestAnimationFrame(tick);
					return;
				}
				// Size the canvas + overlay once the stream dimensions are known.
				if (video.videoWidth && canvas.width !== video.videoWidth) {
					canvas.width = video.videoWidth;
					canvas.height = video.videoHeight;
					stage.style.aspectRatio = `${video.videoWidth} / ${video.videoHeight}`;
if (!drawing && drawingCtor) {
					drawing = new drawingCtor(canvas.getContext('2d') as CanvasRenderingContext2D);
				}
				}
				if (video.currentTime !== lastVideoTime) {
					lastVideoTime = video.currentTime;
					const result = landmarker.detectForVideo(video, performance.now());
					if (beginDetection) {
						draw(result);
						evaluate(result);
					}
				}
				rafId = requestAnimationFrame(tick);
			};
			rafId = requestAnimationFrame(tick);
			status = 'no_face';
			startCountdown();
		} catch (err) {
			stop();
			if (err instanceof Error && err.name === 'NotAllowedError') {
				error = 'Camera access blocked. Allow camera access and retry.';
			} else {
				error = err instanceof Error ? err.message : 'Failed to start face scanner';
			}
		}
	};

	// draw
	// Overlay the detected face oval + eyes onto the canvas as a wireframe.
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

	// evaluate
	// Blink state machine: smooth the EAR, then require a genuine close -> open
	// transition before firing. A blink closes for a few frames and reopens;
	// a held squint exceeds MAX_BLINK_FRAMES and resets without ever firing.
	const evaluate = (result: FaceResult) => {
		if (!result.faceLandmarks?.length) {
			closedFrames = 0;
			earBaseline = null;
			idleFrames = 0;
			status = 'no_face';
			return;
		}
		const lm = result.faceLandmarks[0];

		// Reject faces outside the guide or too far away — never analyze those.
		if (!isInsideGuide(lm)) {
			closedFrames = 0;
			status = 'center_face';
			return;
		}
		if (faceDistanceM(lm) > MAX_FACE_DISTANCE_M) {
			closedFrames = 0;
			status = 'too_far';
			return;
		}

		const avgEar = (eyeEar(lm, LEFT_EYE) + eyeEar(lm, RIGHT_EYE)) / 2;
		// Light smoothing damps jitter without filtering out a real blink.
		smoothedEar = smoothedEar * (1 - EYE_SMOOTH) + avgEar * EYE_SMOOTH;

		// Idle: adapt the open-eye baseline, then wait for a deep enough dip.
		if (closedFrames === 0) {
			idleFrames += 1;
			if (earBaseline === null) {
				earBaseline = smoothedEar;
			} else {
				earBaseline = earBaseline * (1 - 0.08) + smoothedEar * 0.08;
			}
			// Give the baseline a couple frames to settle before trusting it.
			if (idleFrames < ARMING_FRAMES) {
				status = 'looking';
				return;
			}
			if (smoothedEar < earBaseline * BLINK_DEPTH) {
				closedFrames = 1;
				blinkMinEar = smoothedEar;
				status = 'detecting';
			} else {
				status = 'looking';
			}
			return;
		}

		// Closing phase: hold while still below the recovery level, tracking the
		// deepest point so even a brief/partial blink counts once it reopens.
		blinkMinEar = Math.min(blinkMinEar, smoothedEar);
		closedFrames += 1;
		if (closedFrames > MAX_BLINK_FRAMES) {
			// Stayed closed far too long to be a blink (squint) — drop it.
			earBaseline = smoothedEar;
			idleFrames = 0;
			closedFrames = 0;
			blinkMinEar = 1;
			status = 'looking';
			return;
		}
		if (smoothedEar > earBaseline! * RECOVER_LEVEL) {
			// Reopened: a blink only if it truly dipped and lasted long enough.
			const isBlink = closedFrames >= MIN_CLOSED_FRAMES && blinkMinEar <= earBaseline! * BLINK_DEPTH;
			earBaseline = smoothedEar;
			idleFrames = 0;
			closedFrames = 0;
			blinkMinEar = 1;
			status = isBlink ? 'passed' : 'looking';
			if (isBlink && !blinkFired) {
				blinkFired = true;
				onBlink();
			}
			return;
		}
		status = 'detecting';
	};

	// stop
	// Tear down everything: animation loop, camera stream, and renderer.
	const stop = () => {
		clearCountdown();
		cancelAnimationFrame(rafId);
		rafId = 0;
		countdown = 0;
		beginDetection = false;
		stream?.getTracks().forEach((t) => t.stop());
		stream = null;
		if (video) video.srcObject = null;
		// The landmarker is shared and stays warm — only drop our references.
		landmarker = null;
		drawing = null;
		drawingCtor = null;
		faceOval = [];
		leftEye = [];
		rightEye = [];
	};
</script>

<div class="scanner">
	<div class="stage" bind:this={stage}>
		<video bind:this={video} autoplay muted playsinline></video>
		<canvas bind:this={canvas}></canvas>
		<!-- Static guide oval: user must keep their face inside this dashed ellipse. -->
		<div class="face-guide" class:aligned aria-hidden="true"></div>
		{#if !error}
			<div class="hint" class:passed={status === 'passed' && beginDetection}>{hintText}</div>
		{/if}
		{#if countdown > 0}
			<div class="countdown-overlay" aria-live="polite">
				<span class="countdown-number">{countdown}</span>
			</div>
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

	/* Static alignment guide: dashed oval the face must stay inside. */
	.face-guide {
		position: absolute;
		left: 50%;
		top: 50%;
		width: 55%;
		height: 80%;
		transform: translate(-50%, -50%);
		border-radius: 50%;
		border: 2px dashed rgba(148, 163, 184, 0.75);
		background: rgba(37, 99, 235, 0.06);
		box-shadow: 0 0 0 1px rgba(15, 23, 42, 0.12) inset;
		pointer-events: none;
		transition: border-color 0.2s ease, background 0.2s ease;
	}

	.face-guide.aligned {
		border-color: rgba(34, 197, 94, 0.9);
		background: rgba(34, 197, 94, 0.08);
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

	.countdown-overlay {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		background: rgba(15, 23, 42, 0.35);
		border-radius: 10px;
		pointer-events: none;
	}

	.countdown-number {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 6rem;
		font-weight: 700;
		color: white;
		line-height: 1;
		text-shadow: 0 4px 24px rgba(0, 0, 0, 0.45);
		animation: pulse 1s ease-in-out infinite;
	}

	@keyframes pulse {
		0%,
		100% {
			transform: scale(1);
			opacity: 1;
		}
		50% {
			transform: scale(1.15);
			opacity: 0.85;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.countdown-number {
			animation: none;
		}
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