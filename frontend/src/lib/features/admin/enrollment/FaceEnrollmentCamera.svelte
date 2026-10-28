<script lang="ts">
	// FaceEnrollmentCamera
	// Live-camera capture for the three enrollment angles (front, left, right).
	// Reuses the shared MediaPipe FaceLandmarker (model.ts) and the camera
	// boot sequence from FaceScanner.svelte. Produces three JPEG Files and
	// hands them to the existing multipart enrollment endpoint unchanged.
	import { onDestroy } from 'svelte';
	import type { Matrix, NormalizedLandmark } from '@mediapipe/tasks-vision';
	import { initFaceModel, type LoadedFaceModel } from '$lib/features/liveness/model';

	interface Props {
		active: boolean;
		onComplete: (photos: { front: File; left: File; right: File }) => void;
		onCancel?: () => void;
		singleSlot?: 'front' | 'left' | 'right' | null;
		onCapture?: (slot: 'front' | 'left' | 'right', file: File) => void;
		autoCaptureEnabled?: boolean;
	}

	let { active, onComplete, onCancel, singleSlot = null, onCapture, autoCaptureEnabled = false }: Props = $props();
	let autoCapture = $state(autoCaptureEnabled);

	type Step = 'front' | 'left' | 'right';
	type FaceStatus = 'initializing' | 'no_face' | 'multiple_faces' | 'too_far' | 'center_face' | 'too_dark' | 'too_bright' | 'blurry' | 'eyes_closed' | 'ready' | 'captured';

	let stage: HTMLDivElement;
	let video: HTMLVideoElement;
	let canvas: HTMLCanvasElement;

	let step = $state<Step>('front');
	let status = $state<FaceStatus>('initializing');
	let error = $state<string | null>(null);
	let holdFrames = $state(0);
	let frameCount = 0;
	let captured = $state<Partial<Record<Step, File>>>({});
	let capturing = $state(false);
	let reviewFile = $state<File | null>(null);
	let reviewPreview = $state<string | null>(null);
	let reviewSlot = $state<Step | null>(null);

	// Guide oval (normalized video space), matches FaceScanner.
	const GUIDE_CX = 0.5;
	const GUIDE_CY = 0.5;
	const GUIDE_RX = 0.275;
	const GUIDE_RY = 0.4;

	const IPD_M = 0.063;
	const FRONT_CAM_HFOV_DEG = 70;
	const MAX_FACE_DISTANCE_M = 0.5;
	const HOLD_FRAMES = 8;

	const BRIGHTNESS_MIN = 40;
	const BRIGHTNESS_MAX = 220;
	const SHARPNESS_MIN = 50;
	const EAR_MIN = 0.2;
	const LEFT_EYE_IDX = [33, 160, 158, 133, 153, 144] as const;
	const RIGHT_EYE_IDX = [362, 385, 387, 263, 373, 380] as const;

	let landmarker: LoadedFaceModel['landmarker'] | null = null;
	let drawing: InstanceType<LoadedFaceModel['DrawingUtils']> | null = null;
	let drawingCtor: LoadedFaceModel['DrawingUtils'] | null = null;
	let faceOval: Array<{ start: number; end: number }> = [];
	let leftEye: Array<{ start: number; end: number }> = [];
	let rightEye: Array<{ start: number; end: number }> = [];
	let stream: MediaStream | null = null;
	let rafId = 0;
	let lastVideoTime = -1;
	let startToken = 0;

	let yawBaseline: number | null = null;
	let yawSource: 'matrix' | 'landmarks' | null = null;

	const stepLabel = $derived(
		step === 'front' ? 'Front' : step === 'left' ? 'Left' : 'Right'
	);
	const stepInstruction = $derived(
		step === 'front'
			? 'Look straight at the camera'
			: step === 'left'
				? 'Turn your head to your left'
				: 'Turn your head to your right'
	);
	const holdProgress = $derived(Math.min(1, holdFrames / HOLD_FRAMES));

	const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));

	const pointDist = (lm: Array<{ x: number; y: number }>, i: number, j: number) =>
		Math.hypot(lm[i].x - lm[j].x, lm[i].y - lm[j].y);

	const faceCenter = (lm: Array<{ x: number; y: number }>) => {
		let cx = 0, cy = 0;
		for (const p of lm) { cx += p.x; cy += p.y; }
		return { x: cx / lm.length, y: cy / lm.length };
	};

	const isInsideGuide = (lm: Array<{ x: number; y: number }>) => {
		const c = faceCenter(lm);
		const dx = (c.x - GUIDE_CX) / GUIDE_RX;
		const dy = (c.y - GUIDE_CY) / GUIDE_RY;
		return dx * dx + dy * dy <= 1;
	};

	const faceDistanceM = (lm: Array<{ x: number; y: number }>) => {
		const eyeSpread = Math.abs(lm[263].x - lm[33].x);
		const halfFovRad = (FRONT_CAM_HFOV_DEG * Math.PI) / 360;
		return IPD_M / (2 * eyeSpread * Math.tan(halfFovRad));
	};

	let metricCanvas: HTMLCanvasElement | null = null;
	let metricCtx: CanvasRenderingContext2D | null = null;

	const earFor = (lm: Array<{ x: number; y: number }>, idx: readonly number[]) => {
		const pt = (i: number) => ({ x: lm[idx[i]].x, y: lm[idx[i]].y });
		const dist = (a: { x: number; y: number }, b: { x: number; y: number }) =>
			Math.hypot(a.x - b.x, a.y - b.y);
		const vertical1 = dist(pt(1), pt(4));
		const vertical2 = dist(pt(2), pt(5));
		const horizontal = dist(pt(0), pt(3));
		if (horizontal <= 1e-9) return 0;
		return (vertical1 + vertical2) / (2 * horizontal);
	};

	const facePixelBox = (lm: Array<{ x: number; y: number }>, w: number, h: number) => {
		let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
		for (const p of lm) {
			const x = p.x * w;
			const y = p.y * h;
			if (x < minX) minX = x;
			if (y < minY) minY = y;
			if (x > maxX) maxX = x;
			if (y > maxY) maxY = y;
		}
		return {
			x: Math.max(0, Math.floor(minX)),
			y: Math.max(0, Math.floor(minY)),
			w: Math.min(w, Math.ceil(maxX - minX)),
			h: Math.min(h, Math.ceil(maxY - minY)),
		};
	};

	const regionBrightness = (lm: Array<{ x: number; y: number }>) => {
		if (!video || !metricCtx || !metricCanvas) return 255;
		const w = video.videoWidth;
		const h = video.videoHeight;
		if (!w || !h) return 255;
		metricCanvas.width = w;
		metricCanvas.height = h;
		metricCtx.drawImage(video, 0, 0, w, h);
		const box = facePixelBox(lm, w, h);
		if (box.w <= 0 || box.h <= 0) return 255;
		const data = metricCtx.getImageData(box.x, box.y, box.w, box.h).data;
		let sum = 0;
		const n = data.length / 4;
		for (let i = 0; i < data.length; i += 4) {
			const r = data[i], g = data[i + 1], b = data[i + 2];
			sum += 0.299 * r + 0.587 * g + 0.114 * b;
		}
		return n > 0 ? sum / n : 255;
	};

	const regionSharpness = (lm: Array<{ x: number; y: number }>) => {
		if (!video || !metricCtx || !metricCanvas) return 999;
		const w = video.videoWidth;
		const h = video.videoHeight;
		if (!w || !h) return 999;
		metricCanvas.width = w;
		metricCanvas.height = h;
		metricCtx.drawImage(video, 0, 0, w, h);
		const box = facePixelBox(lm, w, h);
		if (box.w < 3 || box.h < 3) return 999;
		const data = metricCtx.getImageData(box.x, box.y, box.w, box.h).data;
		// grayscale
		const gray = new Float32Array(box.w * box.h);
		for (let i = 0, j = 0; i < data.length; i += 4, j++) {
			gray[j] = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
		}
		// Laplacian variance
		let sum = 0;
		let sumSq = 0;
		let count = 0;
		for (let y = 1; y < box.h - 1; y++) {
			for (let x = 1; x < box.w - 1; x++) {
				const idx = y * box.w + x;
				const lap =
					gray[idx - box.w] + gray[idx + box.w] + gray[idx - 1] + gray[idx + 1] - 4 * gray[idx];
				sum += lap;
				sumSq += lap * lap;
				count++;
			}
		}
		if (count === 0) return 999;
		const mean = sum / count;
		return sumSq / count - mean * mean;
	};

	const yawFromMatrix = (matrix: Matrix | undefined) => {
		if (!matrix || matrix.rows < 3 || matrix.columns < 3) return null;
		const data = Array.from(matrix.data ?? []);
		const at = (row: number, col: number) => Number(data[col * matrix.rows + row] ?? 0);
		const rotation = [
			[at(0,0), at(0,1), at(0,2)],
			[at(1,0), at(1,1), at(1,2)],
			[at(2,0), at(2,1), at(2,2)],
		];
		for (let col = 0; col < 3; col++) {
			const scale = Math.hypot(rotation[0][col], rotation[1][col], rotation[2][col]) || 1;
			rotation[0][col] /= scale;
			rotation[1][col] /= scale;
			rotation[2][col] /= scale;
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

	const relativeYaw = (_result: { facialTransformationMatrixes?: Matrix[] }, lm: Array<{ x: number; y: number }>) => {
		// Landmark-only yaw: cheaper than matrix math and good enough for angle capture.
		const rawYaw = yawFromLandmarks(lm);
		if (rawYaw === null) return null;

		// A single-slot retake starts directly on the requested angle, so there is
		// no front-facing pose available to establish a relative baseline. Use the
		// landmark yaw directly for left/right retakes.
		if (singleSlot) return rawYaw;

		if (yawSource !== 'landmarks') { yawSource = 'landmarks'; yawBaseline = null; }
		// Calibrate from the initial front-facing pose and preserve that baseline
		// while advancing through left and right. Resetting it at each angle makes
		// the turned pose become its own baseline, so the angle condition never passes.
		if (yawBaseline === null) yawBaseline = rawYaw;
		return rawYaw - yawBaseline;
	};

	const conditionMet = (yaw: number | null, lm: Array<{ x: number; y: number }>) => {
		if (yaw === null) return false;
		if (!isInsideGuide(lm)) return false;
		// Eye-span distance estimation is unreliable when the head is turned.
		if (step === 'front' && faceDistanceM(lm) > MAX_FACE_DISTANCE_M) return false;
		if (step === 'front') return Math.abs(yaw) <= 8;
		if (step === 'left') return yaw <= -15;
		return yaw >= 15;
	};

	const clearView = () => {
		try {
			const ctx = canvas?.getContext('2d');
			ctx?.clearRect(0, 0, canvas.width || 0, canvas.height || 0);
		} catch { /* ignore */ }
	};

	const captureFrame = async (): Promise<File | null> => {
		if (!video || !canvas) return null;
		if (video.videoWidth) {
			canvas.width = video.videoWidth;
			canvas.height = video.videoHeight;
		}
		const ctx = canvas.getContext('2d');
		if (!ctx) return null;
		ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
		return await new Promise<File | null>((resolve) => {
			canvas.toBlob((blob) => {
				if (!blob) { resolve(null); return; }
				const file = new File([blob], `${step}.jpg`, { type: 'image/jpeg' });
				resolve(file);
			}, 'image/jpeg', 0.92);
		});
	};

	const stop = () => {
		discardReview();
		startToken += 1;
		cancelAnimationFrame(rafId);
		rafId = 0;
		lastVideoTime = -1;
		clearView();
		stream?.getTracks().forEach((t) => t.stop());
		stream = null;
		try {
			if (video) { video.pause(); video.srcObject = null; video.load(); }
		} catch { if (video) video.srcObject = null; }
		landmarker = null;
		drawing = null;
		drawingCtor = null;
		faceOval = [];
		leftEye = [];
		rightEye = [];
		yawBaseline = null;
		yawSource = null;
		metricCanvas = null;
		metricCtx = null;
		status = 'initializing';
		holdFrames = 0;
		frameCount = 0;
	};

	const start = async (preserveCurrentStep = false) => {
		startToken += 1;
		const token = startToken;
		error = null;
		status = 'initializing';
		holdFrames = 0;
		frameCount = 0;
		if (!preserveCurrentStep) step = singleSlot ?? 'front';
		clearView();
		try {
			const loaded = await initFaceModel();
			if (token !== startToken) return;
			landmarker = loaded.landmarker;
			faceOval = loaded.connections.faceOval;
			leftEye = loaded.connections.leftEye;
			rightEye = loaded.connections.rightEye;
			drawingCtor = loaded.DrawingUtils;
			metricCanvas = document.createElement('canvas');
			metricCtx = metricCanvas.getContext('2d');

			stream = await navigator.mediaDevices.getUserMedia({
				video: { facingMode: 'user', width: { ideal: 320 }, height: { ideal: 240 } },
				audio: false,
			});
			if (token !== startToken) {
				stream.getTracks().forEach((t) => t.stop());
				stream = null;
				return;
			}
			video.srcObject = stream;
			await video.play();
			if (token !== startToken) return;

			const tick = () => {
				// Keep the preview alive independently of the current enrollment angle.
				// Some browsers can pause the video element after a capture/review transition
				// even while the camera track is still live.
				if (video.paused && stream?.getVideoTracks().some((track) => track.readyState === 'live')) {
					void video.play().catch(() => { /* retry on the next animation frame */ });
				}
				try {
					if (landmarker && video.readyState >= 2) {
						if (video.videoWidth && canvas.width !== video.videoWidth) {
							canvas.width = video.videoWidth;
							canvas.height = video.videoHeight;
							stage.style.aspectRatio = `${video.videoWidth} / ${video.videoHeight}`;
						}
						if (!drawing && drawingCtor && canvas.width) {
							drawing = new drawingCtor(canvas.getContext('2d') as CanvasRenderingContext2D);
						}
						if (video.currentTime !== lastVideoTime) {
							lastVideoTime = video.currentTime;
							const result = landmarker.detectForVideo(video, performance.now());
							evaluate(result);
						}
					}
				} catch (frameError) {
					// A single inference error must not terminate the animation loop and
					// leave the camera UI appearing frozen. The next frame can recover.
					console.warn('Face enrollment frame processing failed; retrying.', frameError);
				} finally {
					rafId = requestAnimationFrame(tick);
				}
			};
			rafId = requestAnimationFrame(tick);
			status = 'no_face';
		} catch (err) {
			stop();
			if (err instanceof Error && err.name === 'NotAllowedError') {
				error = 'Camera access blocked. Allow camera access and retry.';
			} else {
				error = err instanceof Error ? err.message : 'Failed to start camera';
			}
		}
	};

	const evaluate = (result: { faceLandmarks?: NormalizedLandmark[][]; facialTransformationMatrixes?: Matrix[] }) => {
		if (capturing || reviewFile) return;
		if (!result.faceLandmarks?.length) {
			holdFrames = 0;
			status = 'no_face';
			return;
		}
		if (result.faceLandmarks.length > 1) {
			holdFrames = 0;
			status = 'multiple_faces';
			return;
		}
		const lm = result.faceLandmarks[0];
		if (!isInsideGuide(lm)) {
			holdFrames = 0;
			status = 'center_face';
			return;
		}
		// Enforce distance only for the front-facing pose; eye-span estimation
		// becomes unreliable when the head is turned to either side.
		if (step === 'front' && faceDistanceM(lm) > MAX_FACE_DISTANCE_M) {
			holdFrames = 0;
			status = 'too_far';
			return;
		}
		const brightness = regionBrightness(lm);
		if (brightness < BRIGHTNESS_MIN) {
			holdFrames = 0;
			status = 'too_dark';
			return;
		}
		if (brightness > BRIGHTNESS_MAX) {
			holdFrames = 0;
			status = 'too_bright';
			return;
		}
		const sharpness = regionSharpness(lm);
		if (sharpness < SHARPNESS_MIN) {
			holdFrames = 0;
			status = 'blurry';
			return;
		}
		const leftEar = earFor(lm, LEFT_EYE_IDX);
		const rightEar = earFor(lm, RIGHT_EYE_IDX);
		if (leftEar <= EAR_MIN || rightEar <= EAR_MIN) {
			holdFrames = 0;
			status = 'eyes_closed';
			return;
		}
		const yaw = relativeYaw(result, lm);
		if (conditionMet(yaw, lm)) {
			status = 'ready';
			holdFrames += 1;
			if (autoCapture && holdFrames >= HOLD_FRAMES) {
				void doCapture();
			}
		} else {
			holdFrames = 0;
			status = 'center_face';
		}
	};

	const doCapture = async () => {
		if (capturing || reviewFile) return;
		capturing = true;
		const file = await captureFrame();
		capturing = false;
		if (!file) {
			error = 'Could not capture the photo. Please try again.';
			return;
		}
		reviewFile = file;
		reviewSlot = step;
		reviewPreview = URL.createObjectURL(file);
		holdFrames = 0;
		status = 'captured';
	};

	const discardReview = () => {
		if (reviewPreview) URL.revokeObjectURL(reviewPreview);
		reviewPreview = null;
		reviewFile = null;
		reviewSlot = null;
		holdFrames = 0;
	};

	const useReviewPhoto = () => {
		if (!reviewFile || !reviewSlot) return;
		const file = reviewFile;
		const slot = reviewSlot;
		discardReview();

		if (singleSlot) {
			onCapture?.(singleSlot, file);
			stop();
			return;
		}

		captured = { ...captured, [slot]: file };
		let nextStep: Step;
		if (slot === 'front') nextStep = 'left';
		else if (slot === 'left') nextStep = 'right';
		else {
			onComplete(captured as { front: File; left: File; right: File });
			return;
		}

		// Turn auto-capture off when advancing so the next angle is not captured
		// before the user has repositioned their head.
		autoCapture = false;

		// Restart the camera stream when changing angles. Preserve the front yaw
		// baseline so restarting does not make the next pose its own baseline.
		const savedYawBaseline = yawBaseline;
		const savedYawSource = yawSource;
		stop();
		yawBaseline = savedYawBaseline;
		yawSource = savedYawSource;
		step = nextStep;
		void start(true);
	};

	const retakeReviewPhoto = () => {
		discardReview();
		autoCapture = false;
		// Restart the camera stream cleanly so the retake starts from a fresh
		// frame, mirroring what Use Photo does when advancing to the next angle.
		// Preserve the current step/yaw baseline since we're re-capturing the
		// same slot, not advancing.
		const savedYawBaseline = yawBaseline;
		const savedYawSource = yawSource;
		stop();
		yawBaseline = savedYawBaseline;
		yawSource = savedYawSource;
		void start(true);
	};

	const retry = () => {
		error = null;
		discardReview();
		step = singleSlot ?? 'front';
		captured = {};
		holdFrames = 0;
		void start();
	};

	const manualCapture = () => {
		if (capturing) return;
		void doCapture();
	};

	$effect(() => {
		if (active) void start();
		else stop();
	});

	onDestroy(() => stop());
</script>

<div class="cam">
	<div class="stage" bind:this={stage}>
		<video bind:this={video} autoplay muted playsinline></video>
		<canvas bind:this={canvas}></canvas>
		<div class="face-guide" class:aligned={status === 'ready'} aria-hidden="true"></div>
		{#if !error && !reviewFile}
			<div class="hint" role="status" aria-live="polite">{stepInstruction}</div>
		{/if}
		{#if holdFrames > 0}
			<div class="hold-bar" role="progressbar" aria-valuenow={Math.round(holdProgress * 100)} aria-valuemin={0} aria-valuemax={100}>
				<div class="hold-fill" style={`width: ${Math.round(holdProgress * 100)}%`}></div>
			</div>
		{/if}
	</div>

	<p class="step-label">Capturing: <strong>{stepLabel}</strong> ({Object.keys(captured).length}/3)</p>

	{#if reviewFile && reviewPreview}
		<div class="review" aria-label="Review captured photo">
			<img src={reviewPreview} alt={`Review ${reviewSlot ?? step} photo`} />
			<p class="status">Review this {reviewSlot ?? step} photo before using it.</p>
			<div class="actions">
				<button class="btn primary" onclick={useReviewPhoto}>Use Photo</button>
				<button class="btn" onclick={retakeReviewPhoto}>Retake Photo</button>
				{#if onCancel}
					<button class="btn ghost" onclick={() => { discardReview(); onCancel?.(); }}>Cancel</button>
				{/if}
			</div>
		</div>
	{:else if error}
		<p class="error" role="alert">{error}</p>
		<button class="btn" onclick={retry}>Try again</button>
	{:else}
		<p class="status">
			{#if status === 'initializing'}Loading camera…
			{:else if status === 'no_face'}No face detected
			{:else if status === 'multiple_faces'}Only one face allowed
			{:else if status === 'too_far'}Move closer
			{:else if status === 'center_face'}Center your face in the oval
			{:else if status === 'too_dark'}Image too dark — improve lighting
			{:else if status === 'too_bright'}Image too bright — reduce lighting
			{:else if status === 'blurry'}Image blurry — hold still
			{:else if status === 'eyes_closed'}Keep your eyes open
			{:else if status === 'ready'}Face aligned — capture when ready
			{:else}Captured{/if}
		</p>
		<label class="auto-toggle">
			<input type="checkbox" bind:checked={autoCapture} />
			Automatically capture when aligned
		</label>
		<div class="actions">
			<button class="btn" onclick={manualCapture} disabled={capturing || status !== 'ready'}>Capture now</button>
			{#if onCancel}
				<button class="btn ghost" onclick={onCancel}>Cancel</button>
			{/if}
		</div>
	{/if}
</div>

<style>
	.cam { display: flex; flex-direction: column; gap: 0.75rem; align-items: center; }
	.stage { position: relative; width: 100%; aspect-ratio: 4 / 3; background: #0f172a; border-radius: 10px; overflow: hidden; }
	video, canvas { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: fill; transform: scaleX(-1); }
	.face-guide { position: absolute; left: 50%; top: 50%; width: 55%; height: 80%; transform: translate(-50%, -50%); border-radius: 50%; border: 2px dashed rgba(148,163,184,0.75); pointer-events: none; transition: border-color .2s, background .2s; }
	.face-guide.aligned { border-color: rgba(34,197,94,0.9); background: rgba(34,197,94,0.08); }
	.hint { position: absolute; left: 0; right: 0; bottom: 0.75rem; text-align: center; color: rgba(255,255,255,0.9); background: rgba(15,23,42,0.6); padding: 0.375rem 0.875rem; font-size: 0.8125rem; border-radius: 99px; width: fit-content; margin: 0 auto; pointer-events: none; }
	.hold-bar { position: absolute; bottom: 0.25rem; left: 50%; transform: translateX(-50%); width: 8rem; height: 0.375rem; background: rgba(255,255,255,0.25); border-radius: 99px; overflow: hidden; }
	.hold-fill { height: 100%; background: var(--success, #16a34a); border-radius: 99px; transition: width .1s linear; }
	.step-label { font-size: 0.875rem; color: var(--text-muted, #64748b); margin: 0; }
	.status { font-size: 0.875rem; color: var(--text-secondary, #475569); margin: 0; }
	.actions { display: flex; gap: 0.5rem; }
	.btn { padding: 0.5rem 1rem; border-radius: 8px; border: 1px solid var(--border-strong, #cbd5e1); background: var(--bg-card, #fff); color: var(--text-strong, #0f172a); font: inherit; font-size: 0.875rem; font-weight: 600; cursor: pointer; }
	.btn:disabled { opacity: 0.6; cursor: not-allowed; }
	.btn.ghost { background: transparent; }
	.btn.primary { background: var(--brand); color: var(--on-brand); border-color: var(--brand); }
	.btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
	.review { display: flex; flex-direction: column; align-items: center; gap: 0.75rem; width: 100%; }
	.review img { display: block; width: 100%; max-width: 22rem; max-height: 45vh; object-fit: contain; border-radius: 10px; background: #0f172a; }
	.auto-toggle { display: flex; align-items: center; gap: 0.5rem; font-size: 0.875rem; color: var(--text-secondary, #475569); }
	.error { color: var(--danger, #dc2626); font-size: 0.875rem; margin: 0; }
</style>
