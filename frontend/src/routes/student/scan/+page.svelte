<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { initFaceModel } from '$lib/features/liveness/model';
	import QRScanner from '$lib/features/liveness/components/QRScanner.svelte';
	import FaceScanner from '$lib/features/liveness/components/FaceScanner.svelte';
	import { submitFaceChallenge } from '$lib/features/liveness/service';
	import { studentState } from '$lib/features/student/store.svelte';
	import { Routes } from '$lib/shared/constants/routes';

	let sessionCode = $state('');
	let step = $state<'entry' | 'qr' | 'liveness'>('entry');
	let showPermission = $state(false);
	let qrActive = $state(false);
	let livenessActive = $state(false);
	let showSuccess = $state(false);
	let showFailure = $state(false);
	let offline = $state(false);
	let countdown = $state(0);
	let countdownTimerId: ReturnType<typeof setInterval> | null = null;

	const studentName = $derived(studentState.student?.firstName ?? 'John Doe');

	onDestroy(() => {
		if (countdownTimerId) clearInterval(countdownTimerId);
	});

	// Warm up the MediaPipe face model while the student is still on the entry
	// screen, so it's ready by the time the face liveness camera opens.
	onMount(() => {
		void initFaceModel();
	});

	const handleVerifyCode = () => {
		if (!sessionCode) return;
		goToQr();
	};

	const handleScanned = (code: string) => {
		sessionCode = code;
		startLiveness();
	};

	// Step 1 -> 2: open the QR scanner, guarded by the camera permission modal.
	const goToQr = () => {
		qrActive = false;
		livenessActive = false;
		step = 'qr';
		showPermission = true;
	};

	// Step 2 -> 3: QR decoded, move on to the face liveness check.
	const startLiveness = () => {
		qrActive = false;
		step = 'liveness';
		livenessActive = true;
	};

	// Step 3 -> 2: reopen the QR camera (permission already granted once).
	const backToQr = () => {
		livenessActive = false;
		step = 'qr';
		qrActive = true;
	};

	// Step 2 -> 1: release the camera and return to manual code entry.
	const backToEntry = () => {
		qrActive = false;
		livenessActive = false;
		showPermission = false;
		step = 'entry';
	};

	const handleBlink = () => {
		livenessActive = false;
		void submitFaceChallenge(98, {
			blinkDetected: true,
			headTurnLeft: false,
			headTurnRight: false,
			earSamples: [],
			pnpEvidence: {},
		});
		showSuccess = true;
		countdown = 3;
		countdownTimerId = setInterval(() => {
			countdown -= 1;
			if (countdown <= 0) {
				if (countdownTimerId) clearInterval(countdownTimerId);
				countdownTimerId = null;
				showSuccess = false;
				goto(Routes.DASHBOARD);
			}
		}, 1000);
	};

	const toggleQr = () => {
		if (!qrActive) showPermission = true;
		else qrActive = false;
	};
</script>

<div class="scan">
	{#if offline}
		<div class="offline-banner">
			You are offline · Records will sync when connected.
			<span class="offline-count">3 pending</span>
		</div>
	{/if}

	{#if step === 'entry'}
		<div class="page">
			<div class="page-header">
				<button class="back-btn" onclick={() => goto(Routes.DASHBOARD)}>
					← <span>Back</span>
				</button>
				<h1>Attendance Scanner</h1>
			</div>

			<!-- Session Code -->
			<section class="card">
				<h2 class="section-title">Session Code (manual entry)</h2>
				<div class="code-row">
					<input
						class="form-input code-input"
						placeholder="Enter code from projector (e.g. A7X-9K2M)"
						value={sessionCode}
						oninput={(e) => { sessionCode = (e.target as HTMLInputElement).value.toUpperCase(); }}
					/>
					<button class="btn-secondary" onclick={handleVerifyCode}>
						Verify Code
					</button>
				</div>
			</section>

			<p class="footnote">
				Verify the session code to open the QR scanner, then face liveness (blink).
			</p>
		</div>
	{:else if step === 'qr'}
		<div class="page">
			<div class="page-header">
				<button class="back-btn" onclick={backToEntry}>
					← <span>Back</span>
				</button>
				<h1>QR Scanner</h1>
			</div>

			<!-- QR Camera Scanner -->
			<section class="card">
				<h2 class="section-title">QR Camera Scanner</h2>
				<div
					class="viewport"
					class:inactive={!qrActive}
				>
					{#if !qrActive}
						<div class="inactive-content">
							<p class="inactive-title">Camera inactive</p>
							<p class="inactive-hint">Click "Start Camera" to begin</p>
						</div>
					{:else}
						<div class="viewfinder">
							<span class="corner tl"></span>
							<span class="corner tr"></span>
							<span class="corner bl"></span>
							<span class="corner br"></span>
							<QRScanner
								active={qrActive}
								onScanned={handleScanned}
							/>
							<div class="scan-line"></div>
						</div>
					{/if}
				</div>

				<div class="camera-actions">
					<button
						class={qrActive ? 'btn-danger' : 'btn-primary'}
						onclick={toggleQr}
					>
						{qrActive ? 'Stop Camera' : 'Start Camera'}
					</button>
				</div>

				<p class="footnote">
					Scan the QR code shown on the projector — face liveness (blink) opens automatically.
				</p>
			</section>
		</div>
	{:else}
		<!-- Face Liveness step: camera with face/eye outline + blink detection -->
		<div class="page">
			<div class="page-header">
				<button class="back-btn" onclick={backToQr}>
					← <span>Back</span>
				</button>
				<h1>Face Liveness</h1>
			</div>

			<section class="card">
				<h2 class="section-title">Blink to Verify</h2>
				<div class="viewport">
					<FaceScanner active={livenessActive} onBlink={handleBlink} />
				</div>
				<p class="footnote">
					Look at the camera and blink once — a real blink is detected and attendance is
					recorded automatically.
				</p>
			</section>
		</div>
	{/if}

	<!-- Permission Modal -->
	{#if showPermission}
		<div class="overlay">
			<div class="modal">
				<h3 class="modal-title">Allow Access</h3>
				<p class="modal-desc">
					Camera is needed for QR scanning and the face liveness check.
				</p>
				<button
					class="btn-primary allow-btn"
					onclick={() => { showPermission = false; qrActive = true; }}
				>
					Allow Camera
				</button>
				<button class="modal-link" onclick={backToEntry}>
					No thanks, enter manually
				</button>
			</div>
		</div>
	{/if}

	<!-- Success Overlay -->
	{#if showSuccess}
		<div class="overlay">
			<div class="result">
				<h3 class="result-title">Attendance Recorded!</h3>
				<p class="result-line">{studentName}</p>
				<p class="result-line">CS101 — 9:02 AM</p>
				<p class="verified">Face liveness verified (blink)</p>
				<p class="auto-dismiss">Auto-dismissing in {countdown}s...</p>
			</div>
		</div>
	{/if}

	<!-- Failure Overlay -->
	{#if showFailure}
		<div class="overlay">
			<div class="result">
				<h3 class="result-title">Attendance Rejected</h3>
				<div class="reject-reason">Already scanned session</div>
				<p class="reject-desc">
					Possible reasons: duplicate scan, outside geofence, QR/face liveness failed
				</p>
				<button class="btn-primary try-again" onclick={() => (showFailure = false)}>
					Try Again
				</button>
			</div>
		</div>
	{/if}
</div>

<style>
	.scan {
		display: flex;
		flex-direction: column;
		font-family: system-ui, sans-serif;
	}

	.offline-banner {
		background: #fff7ed;
		border: 1px solid #fed7aa;
		border-radius: 8px;
		padding: 0.625rem 1rem;
		margin-bottom: 1rem;
		display: flex;
		align-items: center;
		gap: 0.5rem;
		color: #c2410c;
		font-size: 0.875rem;
	}

	.offline-count {
		margin-left: auto;
	}

	.page {
		max-width: 700px;
		margin: 0 auto;
		width: 100%;
	}

	.page-header {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 1.5rem;
	}

	.back-btn {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		background: none;
		border: none;
		cursor: pointer;
		color: #2563eb;
		font-weight: 600;
		font-size: 0.875rem;
		font-family: inherit;
		padding: 0;
	}

	.back-btn:hover {
		text-decoration: underline;
	}

	h1 {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.375rem;
		font-weight: 700;
		color: #1e3a5f;
		margin: 0;
	}

	.card {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		padding: 1.25rem;
		margin-bottom: 1.25rem;
		box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
	}

	.section-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.0625rem;
		font-weight: 700;
		color: #1e293b;
		margin: 0 0 1rem;
	}

	.code-row {
		display: flex;
		gap: 0.75rem;
	}

	.form-input {
		width: 100%;
		padding: 0.625rem 0.875rem;
		border: 1.5px solid #d1d5db;
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		outline: none;
		transition: border-color 0.15s;
		background: white;
	}

	.form-input:focus {
		border-color: #2563eb;
	}

	.code-input {
		flex: 1;
		min-width: 0;
		font-family: 'JetBrains Mono', monospace;
		letter-spacing: 0.1em;
		text-transform: uppercase;
	}

	.btn-primary,
	.btn-secondary,
	.btn-danger {
		padding: 0.625rem 1.125rem;
		border-radius: 8px;
		font-size: 0.9375rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
		white-space: nowrap;
		transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
	}

	.btn-primary {
		background: #1e3a5f;
		border: 1px solid #1e3a5f;
		color: white;
		box-shadow: 0 4px 14px rgba(30, 58, 95, 0.28);
	}

	.btn-primary:hover {
		background: #16324f;
		border-color: #16324f;
		transform: translateY(-1px);
	}

	.btn-secondary {
		background: white;
		border: 1px solid #cbd5e1;
		color: #0f172a;
	}

	.btn-secondary:hover {
		background: #f1f5f9;
	}

	.btn-danger {
		background: white;
		border: 1px solid #dc2626;
		color: #dc2626;
	}

	.btn-danger:hover {
		background: #fef2f2;
	}

	.viewport {
		width: 100%;
		aspect-ratio: 4 / 3;
		background: #0f172a;
		border-radius: 12px;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		position: relative;
		overflow: hidden;
		border: 2px dashed #e2e8f0;
	}

	.viewport.inactive {
		background: #f1f5f9;
	}

	.inactive-content {
		text-align: center;
		color: #64748b;
	}

	.inactive-title {
		margin: 0;
		font-size: 0.875rem;
	}

	.inactive-hint {
		margin: 0.25rem 0 0;
		font-size: 0.75rem;
	}

	.viewfinder {
		position: relative;
		width: 100%;
		height: 100%;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.viewfinder :global(#qr-reader) {
		width: 100%;
		height: 100%;
	}

	.corner {
		position: absolute;
		width: 22px;
		height: 22px;
		border: 0 solid #94a3b8;
		z-index: 2;
	}

	.corner.tl {
		top: 16px;
		left: 16px;
		border-top-width: 4px;
		border-left-width: 4px;
		border-top-left-radius: 8px;
	}

	.corner.tr {
		top: 16px;
		right: 16px;
		border-top-width: 4px;
		border-right-width: 4px;
		border-top-right-radius: 8px;
	}

	.corner.bl {
		bottom: 16px;
		left: 16px;
		border-bottom-width: 4px;
		border-left-width: 4px;
		border-bottom-left-radius: 8px;
	}

	.corner.br {
		bottom: 16px;
		right: 16px;
		border-bottom-width: 4px;
		border-right-width: 4px;
		border-bottom-right-radius: 8px;
	}

	.scan-line {
		position: absolute;
		left: 0;
		right: 0;
		height: 3px;
		background: linear-gradient(90deg, transparent, #2563eb, transparent);
		top: 50%;
		animation: scan 2s ease-in-out infinite;
		z-index: 2;
		pointer-events: none;
	}

	@keyframes scan {
		0%,
		100% {
			top: 10%;
		}
		50% {
			top: 90%;
		}
	}

	.camera-actions {
		display: flex;
		gap: 0.75rem;
		margin-top: 1rem;
	}

	.camera-actions > button {
		flex: 1;
		min-width: 0;
	}

	.footnote {
		color: #64748b;
		font-size: 0.8125rem;
		margin-top: 1rem;
		margin-bottom: 0;
	}

	.overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.5);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 200;
		padding: 1rem;
	}

	.modal {
		background: white;
		border-radius: 12px;
		padding: 2rem;
		max-width: 360px;
		width: 100%;
		text-align: center;
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
	}

	.modal-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.25rem;
		font-weight: 700;
		color: #1e293b;
		margin: 0 0 0.75rem;
	}

	.modal-desc {
		color: #64748b;
		font-size: 0.875rem;
		margin-bottom: 1.5rem;
	}

	.allow-btn {
		width: 100%;
		margin-bottom: 0.625rem;
	}

	.modal-link {
		background: none;
		border: none;
		cursor: pointer;
		color: #64748b;
		font-size: 0.8125rem;
		font-family: inherit;
		padding: 0;
	}

	.modal-link:hover {
		color: #334155;
		text-decoration: underline;
	}

	.result {
		text-align: center;
		color: white;
		max-width: 380px;
		width: 100%;
	}

	.result-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.75rem;
		font-weight: 700;
		margin: 0 0 0.5rem;
	}

	.result-line {
		color: rgba(255, 255, 255, 0.8);
		margin: 0 0 0.25rem;
	}

	.verified {
		color: #16a34a;
		font-weight: 600;
	}

	.auto-dismiss {
		color: rgba(255, 255, 255, 0.5);
		font-size: 0.875rem;
		margin-top: 1rem;
	}

	.reject-reason {
		background: #7f1d1d;
		border-radius: 8px;
		padding: 0.75rem 1rem;
		margin-bottom: 1rem;
		font-size: 0.875rem;
		color: white;
	}

	.reject-desc {
		color: rgba(255, 255, 255, 0.6);
		font-size: 0.875rem;
		margin-bottom: 1.5rem;
	}

	.try-again {
		max-width: 200px;
		margin: 0 auto;
		display: block;
	}

	@media (prefers-reduced-motion: reduce) {
		.scan-line {
			animation: none;
		}
	}

	@media (max-width: 480px) {
		.camera-actions {
			flex-direction: column;
		}

		.code-row {
			flex-direction: column;
		}

		.code-row .btn-secondary {
			width: 100%;
		}
	}

	:global(.scan button:focus-visible),
	:global(.scan input:focus-visible) {
		outline: 2px solid #2563eb;
		outline-offset: 2px;
	}
</style>