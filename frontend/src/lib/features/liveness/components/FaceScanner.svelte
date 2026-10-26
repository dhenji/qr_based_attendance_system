<script lang="ts">
	// FaceScanner
	// Liveness check via MediaPipe FaceLandmarker (478 landmarks).
	import { onDestroy } from 'svelte';
	import type { DrawingOptions, Matrix, NormalizedLandmark } from '@mediapipe/tasks-vision';
	import { initFaceModel, type LoadedFaceModel } from '$lib/features/liveness/model';
	import type { LivenessEvidence } from '$lib/shared/types';

	interface FaceConnection {
		start: number;
		end: number;
	}

	let { active, onComplete } = $props<{
		active: boolean;
		onComplete: (evidence: LivenessEvidence) => void;
	}>();

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

	type ChallengeStage = 'blink' | 'blink_success' | 'left' | 'left_center' | 'right' | 'right_center' | 'complete';

	let status = $state<FaceStatus>('initializing');
	let challengeStage = $state<ChallengeStage>('blink');
	let challengeMessage = $state('');
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
	let blinkCountdown = $state(0);
	let blinkSuccessTimerId: ReturnType<typeof setInterval> | null = null;

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
	let earSamples: number[] = [];
	let yawSamples: number[] = [];
	let yawBaseline: number | null = null;
	let yawSource: 'matrix' | 'landmarks' | null = null;
	let lastYaw = 0;
	let peakLeftYaw = 0;
	let peakRightYaw = 0;
	let poseHoldFrames = $state(0);
	let centerHoldFrames = $state(0);
	let stageStartedAt = 0;
	let completionSent = false;
	let startToken = 0;
	// EMA-smoothed EAR; damps single-frame landmark jitter.
	let smoothedEar = 1;
	// Per-user open-eye baseline and closing-phase bookkeeping for blink math.
	let earBaseline: number | null = null;
	let idleFrames = 0;
	let blinkMinEar = 1;
	let lastFaceLandmarks: any[] = [];

	interface FaceResult {
		faceLandmarks?: NormalizedLandmark[][];
		facialTransformationMatrixes?: Matrix[];
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
	const POSE_HOLD_FRAMES = 8;
	const CENTER_HOLD_FRAMES = 5;
	const LEFT_YAW_THRESHOLD = -15;
	const RIGHT_YAW_THRESHOLD = 15;
	const CENTER_YAW_THRESHOLD = 5;
	const STAGE_TIMEOUT_MS = 12000;
	const MAX_POSE_SAMPLES = 120;
	const MAX_EAR_SAMPLES = 100;
	// Retry budget for stage timeouts: after this many auto-restarts the
	// challenge halts with a surfaced error + manual Try again instead of
	// looping the camera forever.
	const MAX_STAGE_ATTEMPTS = 3;
	let stageAttempts = $state(0);
	let stageTimedOut = $state(false);

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
	const isInsideGuide = (lm: Array<{ x: number; y: number }>, scale = 1) => {
		const c = faceCenter(lm);
		const dx = (c.x - GUIDE_CX) / (GUIDE_RX * scale);
		const dy = (c.y - GUIDE_CY) / (GUIDE_RY * scale);
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

	const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

	const yawFromMatrix = (matrix: Matrix | undefined) => {
		if (!matrix || matrix.rows < 3 || matrix.columns < 3) return null;
		const data = Array.from(matrix.data ?? []);
		const at = (row: number, column: number) => Number(data[column * matrix.rows + row] ?? 0);
		const rotation = [
			[at(0, 0), at(0, 1), at(0, 2)],
			[at(1, 0), at(1, 1), at(1, 2)],
			[at(2, 0), at(2, 1), at(2, 2)]
		];
		for (let column = 0; column < 3; column += 1) {
			const scale = Math.hypot(
				rotation[0][column],
				rotation[1][column],
				rotation[2][column]
			) || 1;
			rotation[0][column] /= scale;
			rotation[1][column] /= scale;
			rotation[2][column] /= scale;
		}
		const yaw = Math.asin(clamp(-rotation[2][0], -1, 1));
		return -(yaw * 180) / Math.PI;
	};

	const yawFromLandmarks = (lm: Array<{ x: number; y: number }>) => {
		const eyeSpan = Math.abs(lm[263].x - lm[33].x);
		if (eyeSpan < 0.001) return null;
		const eyeCenter = (lm[33].x + lm[263].x) / 2;
		return -((lm[1].x - eyeCenter) / eyeSpan) * 45;
	};

	const relativeYaw = (result: FaceResult, lm: Array<{ x: number; y: number }>) => {
		const matrixYaw = yawFromMatrix(result.facialTransformationMatrixes?.[0]);
		const source = matrixYaw === null ? 'landmarks' : 'matrix';
		const rawYaw = matrixYaw ?? yawFromLandmarks(lm);
		if (rawYaw === null) return null;
		if (yawSource !== source) {
			yawSource = source;
			yawBaseline = null;
		}
		if (yawBaseline === null) yawBaseline = rawYaw;
		return rawYaw - yawBaseline;
	};

	// Per-status instruction shown to the user before detection begins.
	const preHintText = $derived(
		countdown > 0 ? `${challengeMessage || 'Get ready'} … ${countdown}` : 'Face model loading…'
	);

	// Hold progress 0..1 for the on-camera progress bar during tilt stages.
	const holdProgress = $derived.by(() => {
		if (challengeStage === 'left' || challengeStage === 'right') {
			return Math.min(1, poseHoldFrames / POSE_HOLD_FRAMES);
		}
		if (challengeStage === 'left_center' || challengeStage === 'right_center') {
			return Math.min(1, centerHoldFrames / CENTER_HOLD_FRAMES);
		}
		return 0;
	});

	// True during a tilt stage while the user should be moving or holding —
	// drives the on-camera arrow cue.
	const showTurnCue = $derived(
		beginDetection &&
			(challengeStage === 'left' ||
				challengeStage === 'left_center' ||
				challengeStage === 'right' ||
				challengeStage === 'right_center')
	);

	const turnCue = $derived.by(() => {
		switch (challengeStage) {
			case 'left':
				return { arrow: '←', label: 'Turn left' };
			case 'left_center':
				return { arrow: '◎', label: 'Back to center' };
			case 'right':
				return { arrow: '→', label: 'Turn right' };
			case 'right_center':
				return { arrow: '◎', label: 'Back to center' };
			default:
				return { arrow: '', label: '' };
		}
	});

	// Wipe the overlay canvas so a stopped session never leaves a frozen
	// wireframe behind (the "stuck to old face" report on retry).
	const clearView = () => {
		try {
			const ctx = canvas?.getContext('2d');
			ctx?.clearRect(0, 0, canvas.width || 0, canvas.height || 0);
		} catch {
			// Canvas may not be bound yet on early teardown — safe to skip.
		}
	};

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
				switch (challengeStage) {
					case 'blink_success':
						return '';
					case 'left':
						return 'Turn your head to your left ←';
					case 'left_center':
						return 'Return your head to center ◎';
					case 'right':
						return 'Turn your head to your right →';
					case 'right_center':
						return 'Return your head to center ◎';
					case 'complete':
						return 'Verified';
					default:
						return 'Look at the camera and blink once';
				}
			case 'detecting':
				if (challengeStage === 'blink') return 'Eyes closing — blink fully…';
				switch (challengeStage) {
					case 'left':
						return 'Holding left turn… keep it there ←';
					case 'left_center':
						return 'Centering… hold still ◎';
					case 'right':
						return 'Holding right turn… keep it there →';
					case 'right_center':
						return 'Centering… hold still ◎';
					default:
						return 'Hold still…';
				}
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
		clearBlinkSuccess();
		stop();
	});

	const clearCountdown = () => {
		if (countdownTimerId) {
			clearInterval(countdownTimerId);
			countdownTimerId = null;
		}
	};

	const clearBlinkSuccess = () => {
		if (blinkSuccessTimerId) {
			clearInterval(blinkSuccessTimerId);
			blinkSuccessTimerId = null;
		}
		blinkCountdown = 0;
	};

	// Phase 2 → Phase 3 handoff: freeze tilt detection for 3s while the
	// success card replaces the viewport. The camera stream and RAF loop
	// keep running underneath so resume is instant; yaw state is reset so
	// the head-turn starts from a clean baseline.
	const startBlinkSuccessPause = () => {
		clearBlinkSuccess();
		challengeStage = 'blink_success';
		status = 'passed';
		yawBaseline = null;
		yawSource = null;
		yawSamples = [];
		peakLeftYaw = 0;
		peakRightYaw = 0;
		poseHoldFrames = 0;
		centerHoldFrames = 0;
		blinkCountdown = 3;
		blinkSuccessTimerId = setInterval(() => {
			blinkCountdown -= 1;
			if (blinkCountdown <= 0) {
				clearBlinkSuccess();
				challengeStage = 'left';
				status = 'looking';
				stageStartedAt = performance.now();
			}
		}, 1000);
	};

	const startCountdown = (message = '') => {
		clearCountdown();
		challengeMessage = message;
		beginDetection = false;
		countdown = 3;
		countdownTimerId = setInterval(() => {
			countdown -= 1;
			if (countdown <= 0) {
				clearCountdown();
				beginDetection = true;
				challengeMessage = '';
				stageStartedAt = performance.now();
				status = 'looking';
			}
		}, 1000);
	};

	const resetChallenge = () => {
		stageAttempts += 1;
		if (stageAttempts > MAX_STAGE_ATTEMPTS) {
			// Budget exhausted: halt auto-restarts with the preview left live
			// so the user sees the last frame. beginDetection=false stops
			// evaluate() from re-arming another timeout; the manual Try again
			// button below resets the budget via start().
			clearBlinkSuccess();
			clearCountdown();
			beginDetection = false;
			challengeStage = 'blink';
			challengeMessage = '';
			stageStartedAt = 0;
			completionSent = false;
			status = 'no_face';
			stageTimedOut = true;
			error =
				'Liveness timed out after 3 tries — check your lighting, face the camera, then try again.';
			return;
		}
		clearBlinkSuccess();
		challengeStage = 'blink';
		challengeMessage = '';
		blinkFired = false;
		closedFrames = 0;
		earSamples = [];
		smoothedEar = 1;
		earBaseline = null;
		idleFrames = 0;
		blinkMinEar = 1;
		yawSamples = [];
		yawBaseline = null;
		yawSource = null;
		lastYaw = 0;
		peakLeftYaw = 0;
		peakRightYaw = 0;
		poseHoldFrames = 0;
		centerHoldFrames = 0;
		stageStartedAt = 0;
		completionSent = false;
		status = 'no_face';
		startCountdown('Challenge timed out — starting again');
	};

	// start
	// Boot sequence: reuse the shared warm landmarker, open the front camera,
	// then loop detection per frame.
	const start = async () => {
		startToken += 1;
		const token = startToken;
		error = null;
		stageTimedOut = false;
		stageAttempts = 0;
		challengeStage = 'blink';
		challengeMessage = '';
		blinkFired = false;
		closedFrames = 0;
		earSamples = [];
		smoothedEar = 1;
		earBaseline = null;
		idleFrames = 0;
		blinkMinEar = 1;
		yawSamples = [];
		yawBaseline = null;
		yawSource = null;
		lastYaw = 0;
		peakLeftYaw = 0;
		peakRightYaw = 0;
		poseHoldFrames = 0;
		centerHoldFrames = 0;
		stageStartedAt = 0;
		completionSent = false;
		lastVideoTime = -1;
		lastFaceLandmarks = [];
		status = 'initializing';
		beginDetection = false;
		clearCountdown();
		clearBlinkSuccess();
		clearView();

		try {
			// Grab the pre-warmed model instance — no re-download or re-compile.
			const loaded = await initFaceModel();
			if (token !== startToken) return;
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
			if (token !== startToken) {
				stream.getTracks().forEach((t) => t.stop());
				stream = null;
				return;
			}
			video.srcObject = stream;
			await video.play();
			// A stop() can fire while play() is pending (component deactivation,
			// unmount, retry press mid-boot). Bailing here keeps the rAF arm
			// below from creating a loop stop() can no longer cancel — its
			// cancelAnimationFrame already ran before we armed anything.
			if (token !== startToken) return;

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
				}
				// Recreate the overlay renderer whenever it's missing (e.g. after
				// stop() dropped it on retry with the same resolution, where the
				// resize branch above never runs). Kept separate so a retry never
				// loses the wireframe.
				if (!drawing && drawingCtor && canvas.width) {
					drawing = new drawingCtor(canvas.getContext('2d') as CanvasRenderingContext2D);
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
	// Always clears first so a lost face never leaves a frozen overlay behind.
	const draw = (result: FaceResult) => {
		const ctx = canvas?.getContext('2d');
		if (!ctx) return;
		ctx.clearRect(0, 0, canvas.width, canvas.height);
		if (!result.faceLandmarks?.length || !drawing) return;
		const lm = result.faceLandmarks[0];
		drawing.drawConnectors(lm, faceOval, { color: '#94a3b8', lineWidth: 2 });
		drawing.drawConnectors(lm, leftEye, { color: '#4f9cf9', lineWidth: 2 });
		drawing.drawConnectors(lm, rightEye, { color: '#4f9cf9', lineWidth: 2 });
	};

	const evaluate = (result: FaceResult) => {
		// Frozen during the blink-success card: keep the preview alive but
		// ignore frames so the 3s pause can't time out or pollute yaw stats.
		if (challengeStage === 'blink_success') return;
		if (beginDetection && stageStartedAt > 0 && performance.now() - stageStartedAt > STAGE_TIMEOUT_MS) {
			resetChallenge();
			return;
		}

		if (!result.faceLandmarks?.length) {
			closedFrames = 0;
			earBaseline = null;
			idleFrames = 0;
			poseHoldFrames = 0;
			centerHoldFrames = 0;
			lastFaceLandmarks = [];
			status = 'no_face';
			return;
		}
		const lm = result.faceLandmarks[0];
		// Keep the landmarks from the frame currently being graded so the
		// scan submission's embedding comes from the same face that is
		// passing liveness (see scan/+page.svelte liveFaceEmbedding).
		lastFaceLandmarks = result.faceLandmarks;
		const guideScale = challengeStage === 'blink' ? 1 : 1.25;
		if (!isInsideGuide(lm, guideScale)) {
			closedFrames = 0;
			poseHoldFrames = 0;
			centerHoldFrames = 0;
			status = 'center_face';
			return;
		}
		if (faceDistanceM(lm) > MAX_FACE_DISTANCE_M) {
			closedFrames = 0;
			poseHoldFrames = 0;
			centerHoldFrames = 0;
			status = 'too_far';
			return;
		}

		const yaw = relativeYaw(result, lm);
		if (yaw !== null) {
			lastYaw = yaw;
			if (yawSamples.length >= MAX_POSE_SAMPLES) yawSamples.shift();
			yawSamples.push(Number(yaw.toFixed(2)));
			if (yaw < 0) peakLeftYaw = Math.min(peakLeftYaw, yaw);
			if (yaw > 0) peakRightYaw = Math.max(peakRightYaw, yaw);
		}

		const avgEar = (eyeEar(lm, LEFT_EYE) + eyeEar(lm, RIGHT_EYE)) / 2;
		if (earSamples.length >= MAX_EAR_SAMPLES) earSamples.shift();
		earSamples.push(Number(avgEar.toFixed(4)));
		smoothedEar = smoothedEar * (1 - EYE_SMOOTH) + avgEar * EYE_SMOOTH;

		if (challengeStage === 'blink') {
			if (closedFrames === 0) {
				idleFrames += 1;
				if (earBaseline === null) {
					earBaseline = smoothedEar;
				} else {
					earBaseline = earBaseline * (1 - 0.08) + smoothedEar * 0.08;
				}
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

			blinkMinEar = Math.min(blinkMinEar, smoothedEar);
			closedFrames += 1;
			if (closedFrames > MAX_BLINK_FRAMES) {
				earBaseline = smoothedEar;
				idleFrames = 0;
				closedFrames = 0;
				blinkMinEar = 1;
				status = 'looking';
				return;
			}
			if (smoothedEar > earBaseline! * RECOVER_LEVEL) {
				const isBlink = closedFrames >= MIN_CLOSED_FRAMES && blinkMinEar <= earBaseline! * BLINK_DEPTH;
				earBaseline = smoothedEar;
				idleFrames = 0;
				closedFrames = 0;
				blinkMinEar = 1;
				status = 'looking';
				if (isBlink && !blinkFired) {
					blinkFired = true;
					startBlinkSuccessPause();
				}
				return;
			}
			status = 'detecting';
			return;
		}

		if (yaw === null) {
			poseHoldFrames = 0;
			centerHoldFrames = 0;
			status = 'looking';
			return;
		}

		const isCenter = Math.abs(yaw) <= CENTER_YAW_THRESHOLD;
		if (isCenter) {
			centerHoldFrames += 1;
			poseHoldFrames = 0;
		} else {
			centerHoldFrames = 0;
			const meetsTurn =
				(challengeStage === 'left' && yaw <= LEFT_YAW_THRESHOLD) ||
				(challengeStage === 'right' && yaw >= RIGHT_YAW_THRESHOLD);
			poseHoldFrames = meetsTurn ? poseHoldFrames + 1 : 0;
		}
		status = poseHoldFrames > 0 || centerHoldFrames > 0 ? 'detecting' : 'looking';

		if (challengeStage === 'left' && poseHoldFrames >= POSE_HOLD_FRAMES) {
			challengeStage = 'left_center';
			status = 'looking';
			poseHoldFrames = 0;
			centerHoldFrames = 0;
			stageStartedAt = performance.now();
			return;
		}
		if (challengeStage === 'right' && poseHoldFrames >= POSE_HOLD_FRAMES) {
			challengeStage = 'right_center';
			status = 'looking';
			poseHoldFrames = 0;
			centerHoldFrames = 0;
			stageStartedAt = performance.now();
			return;
		}
		if (
			challengeStage === 'left_center' &&
			centerHoldFrames >= CENTER_HOLD_FRAMES
		) {
			challengeStage = 'right';
			status = 'looking';
			poseHoldFrames = 0;
			centerHoldFrames = 0;
			stageStartedAt = performance.now();
			return;
		}
		if (
			challengeStage === 'right_center' &&
			centerHoldFrames >= CENTER_HOLD_FRAMES
		) {
			challengeStage = 'complete';
			status = 'passed';
			if (!completionSent) {
				let faceImage: string | undefined;
				try {
					if (video && video.videoWidth && video.videoHeight) {
						const c = document.createElement('canvas');
						c.width = video.videoWidth;
						c.height = video.videoHeight;
						const ctx = c.getContext('2d');
						if (ctx) {
							ctx.drawImage(video, 0, 0, c.width, c.height);
							const dataUrl = c.toDataURL('image/jpeg', 0.8);
							faceImage = dataUrl.split(',')[1];
						}
					}
				} catch {
					faceImage = undefined;
				}
				completionSent = true;
				onComplete({
					blinkDetected: true,
					headTurnLeft: true,
					headTurnRight: true,
					earSamples: [...earSamples],
					faceCount: lastFaceLandmarks?.length || 1,
					pnpEvidence: {
						source: yawSource ?? 'landmarks',
						baseline_yaw: Number((yawBaseline ?? 0).toFixed(2)),
						yaw: Number(lastYaw.toFixed(2)),
						peak_left_yaw: Number(peakLeftYaw.toFixed(2)),
						peak_right_yaw: Number(peakRightYaw.toFixed(2)),
						yaw_samples: [...yawSamples],
					},
					faceLandmarks: lastFaceLandmarks,
					faceImage,
				});
			}
		}
	};

	// stop
	// Tear down everything: animation loop, camera stream, renderer, and the
	// frozen last frame — a retry must restart from a clean live view.
	const stop = () => {
		startToken += 1;
		stageAttempts = 0;
		stageTimedOut = false;
		clearCountdown();
		clearBlinkSuccess();
		cancelAnimationFrame(rafId);
		rafId = 0;
		countdown = 0;
		beginDetection = false;
		challengeStage = 'blink';
		challengeMessage = '';
		status = 'initializing';
		blinkFired = false;
		closedFrames = 0;
		earSamples = [];
		smoothedEar = 1;
		earBaseline = null;
		idleFrames = 0;
		blinkMinEar = 1;
		yawSamples = [];
		yawBaseline = null;
		yawSource = null;
		lastYaw = 0;
		peakLeftYaw = 0;
		peakRightYaw = 0;
		poseHoldFrames = 0;
		centerHoldFrames = 0;
		stageStartedAt = 0;
		completionSent = false;
		lastVideoTime = -1;
		lastFaceLandmarks = [];
		clearView();
		stream?.getTracks().forEach((t) => t.stop());
		stream = null;
		try {
			if (video) {
				video.pause();
				video.srcObject = null;
				video.load();
			}
		} catch {
			if (video) video.srcObject = null;
		}
		// The landmarker is shared and stays warm — only drop our references.
		landmarker = null;
		drawing = null;
		drawingCtor = null;
		faceOval = [];
		leftEye = [];
		rightEye = [];
	};

	// Manual retry after an error (timeout budget exhausted or camera
	// failure). start() resets the budget, so this never inherits a spent
	// counter. Safe to call while `active` stays true — the $effect only
	// fires on prop toggles, not on this call.
	const retry = () => {
		stageAttempts = 0;
		stageTimedOut = false;
		error = null;
		void start();
	};
</script>

<div class="scanner">
	<div class="stage" bind:this={stage}>
		<video bind:this={video} autoplay muted playsinline></video>
		<canvas bind:this={canvas}></canvas>
		{#if challengeStage !== 'blink_success'}
			<!-- Static guide oval: user must keep their face inside this dashed ellipse. -->
			<div class="face-guide" class:aligned aria-hidden="true"></div>
		{/if}
		{#if showTurnCue && challengeStage !== 'blink_success'}
			<!-- Arrow + label are decorative duplicates: the live .hint below
				carries the same instruction as the screen-reader text. -->
			<div class="turn-cue" aria-hidden="true">
				<span
					class="turn-arrow"
					style={challengeStage === 'left'
						? '--nudge: -6px'
						: challengeStage === 'right'
							? '--nudge: 6px'
							: '--nudge: 0px'}>{turnCue.arrow}</span>
				<span class="turn-label">{turnCue.label}</span>
				<div
					class="hold-bar"
					role="progressbar"
					aria-label="Hold progress"
					aria-valuemin={0}
					aria-valuemax={100}
					aria-valuenow={Math.round(holdProgress * 100)}
				>
					<div
						class="hold-fill"
						style={`width: ${Math.round(holdProgress * 100)}%`}
					></div>
				</div>
			</div>
		{/if}
		{#if !error && challengeStage !== 'blink_success'}
			<div class="hint" role="status" aria-live="polite" class:passed={status === 'passed' && beginDetection}>{hintText}</div>
		{/if}
		{#if countdown > 0}
			<div class="countdown-overlay" aria-live="polite">
				<span class="countdown-number">{countdown}</span>
			</div>
		{/if}
		{#if challengeStage === 'blink_success'}
			<div class="blink-success" aria-live="polite">
				<div class="success-icon" aria-hidden="true">✓</div>
				<h3 class="success-title">Face liveness successful</h3>
				<p class="success-sub">Starting head-tilt check in {blinkCountdown}s…</p>
				<span class="blink-count">{blinkCountdown}</span>
			</div>
		{/if}
	</div>
	{#if error}
		<p class="error" role="alert">{error}</p>
		<button class="retry-btn" type="button" onclick={retry}>Try again</button>
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

	/* On-camera directional cue for the tilt phase: arrow + label chip with
		a hold-progress bar underneath. Text alternative stays in .hint. */
	.turn-cue {
		position: absolute;
		top: 0.75rem;
		left: 50%;
		transform: translateX(-50%);
		z-index: 3;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.375rem;
		pointer-events: none;
	}

	.turn-arrow {
		width: 3rem;
		height: 3rem;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1.5rem;
		font-weight: 700;
		color: white;
		background: rgba(37, 99, 235, 0.85);
		border-radius: 50%;
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);
		animation: nudge 1.2s ease-in-out infinite;
	}

	.turn-label {
		color: white;
		background: rgba(15, 23, 42, 0.75);
		padding: 0.25rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 600;
		border-radius: 99px;
		white-space: nowrap;
	}

	.hold-bar {
		width: 8rem;
		height: 0.375rem;
		background: rgba(255, 255, 255, 0.25);
		border-radius: 99px;
		overflow: hidden;
	}

	.hold-fill {
		height: 100%;
		background: var(--success);
		border-radius: 99px;
		transition: width 0.1s linear;
	}

	@keyframes nudge {
		0%,
		100% {
			transform: translateX(0);
		}
		50% {
			transform: translateX(var(--nudge, 4px));
		}
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

	/* Phase 2 → 3 handoff card: replaces the viewport for 3s while the
		camera stream keeps running underneath (detection paused). */
	.blink-success {
		position: absolute;
		inset: 0;
		z-index: 5;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		text-align: center;
		color: white;
		background: linear-gradient(160deg, #16a34a, #15803d);
		border-radius: 10px;
		padding: 1.5rem;
	}

	.success-icon {
		width: 3.5rem;
		height: 3.5rem;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1.75rem;
		font-weight: 700;
		color: #16a34a;
		background: white;
		border-radius: 50%;
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
	}

	.success-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.25rem;
		font-weight: 700;
		margin: 0.5rem 0 0;
	}

	.success-sub {
		color: rgba(255, 255, 255, 0.85);
		font-size: 0.875rem;
		margin: 0;
	}

	.blink-count {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 3rem;
		font-weight: 700;
		line-height: 1;
		margin-top: 0.5rem;
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
		.blink-count {
			animation: none;
		}
		.turn-arrow {
			animation: none;
		}
	}

	.error {
		color: var(--danger-strong);
		background: var(--danger-bg);
		border-radius: 8px;
		padding: 0.5rem 0.875rem;
		font-size: 0.8125rem;
		text-align: center;
		max-width: 90%;
		margin: 0.75rem auto 0;
	}

	.retry-btn {
		display: block;
		margin: 0.75rem auto 0;
		padding: 0.625rem 1.25rem;
		border-radius: 8px;
		border: 1px solid var(--brand);
		background: var(--brand);
		color: var(--on-brand);
		font: inherit;
		font-size: 0.875rem;
		font-weight: 600;
		cursor: pointer;
	}
</style>