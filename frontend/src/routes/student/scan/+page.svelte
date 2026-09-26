<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { initFaceModel } from '$lib/features/liveness/model';
	import QRScanner from '$lib/features/liveness/components/QRScanner.svelte';
	import FaceScanner from '$lib/features/liveness/components/FaceScanner.svelte';
	import {
		submitAttendanceScan,
		validateGPS,
		verifySessionCode,
		type SessionVerification
	} from '$lib/features/liveness/service';
	import { studentState } from '$lib/features/student/store.svelte';
	import { Routes } from '$lib/shared/constants/routes';
	import { formatTime } from '$lib/shared/utils/format';
	import type { LivenessEvidence } from '$lib/shared/types';

	type Step = 'entry' | 'qr' | 'liveness';

	let sessionCode = $state('');
	let session = $state<SessionVerification | null>(null);
	let step = $state<Step>('entry');
	let showPermission = $state(false);
	let qrActive = $state(false);
	let livenessActive = $state(false);
	let showSuccess = $state(false);
	let showFailure = $state(false);
	let verifying = $state(false);
	let submitting = $state(false);
	let offline = $state(false);
	let scanError = $state<string | null>(null);
	let rejectionReason = $state('');
	let resultStatus = $state<'present' | 'late'>('present');
	let scannedAt = $state('');
	let countdown = $state(0);
	let countdownTimerId: ReturnType<typeof setInterval> | null = null;

	const studentName = $derived(studentState.student?.firstName ?? 'Student');
	const studentNumber = $derived(studentState.student?.studentNumber ?? '');

	const clearCountdown = () => {
		if (countdownTimerId) clearInterval(countdownTimerId);
		countdownTimerId = null;
		countdown = 0;
	};

	const getErrorMessage = (error: unknown, fallback: string) =>
		error instanceof Error ? error.message : fallback;

	onDestroy(() => {
		clearCountdown();
	});

	onMount(() => {
		void initFaceModel();
	});

	const verifyCode = async (code: string, openScanner: boolean) => {
		const normalizedCode = code.trim();
		if (!normalizedCode || verifying) return;

		verifying = true;
		scanError = null;
		try {
			const verifiedSession = await verifySessionCode(normalizedCode);
			sessionCode = normalizedCode;
			session = verifiedSession;
			showFailure = false;
			rejectionReason = '';
			if (openScanner) goToQr();
			else startLiveness();
		} catch (error) {
			scanError = getErrorMessage(error, 'Unable to verify the session code');
		} finally {
			verifying = false;
		}
	};

	const handleVerifyCode = () => {
		void verifyCode(sessionCode, true);
	};

	const handleScanned = (code: string) => {
		void verifyCode(code, false);
	};

	const goToQr = () => {
		qrActive = false;
		livenessActive = false;
		showSuccess = false;
		showFailure = false;
		step = 'qr';
		showPermission = true;
	};

	const startLiveness = () => {
		qrActive = false;
		showPermission = false;
		showSuccess = false;
		showFailure = false;
		scannedAt = '';
		step = 'liveness';
		livenessActive = true;
	};

	const backToQr = () => {
		livenessActive = false;
		step = 'qr';
		qrActive = true;
	};

	const backToEntry = () => {
		qrActive = false;
		livenessActive = false;
		showPermission = false;
		showSuccess = false;
		showFailure = false;
		session = null;
		scanError = null;
		rejectionReason = '';
		scannedAt = '';
		step = 'entry';
	};

	const retryLiveness = () => {
		showFailure = false;
		rejectionReason = '';
		scanError = null;
		startLiveness();
	};

	const getCurrentPosition = () =>
		new Promise<{ lat: number; lng: number; accuracy: number }>((resolve, reject) => {
			if (!navigator.geolocation) {
				reject(new Error('Location services are unavailable'));
				return;
			}

			navigator.geolocation.getCurrentPosition(
				({ coords }) =>
					resolve({
						lat: coords.latitude,
						lng: coords.longitude,
						accuracy: coords.accuracy,
					}),
				() => reject(new Error('Location permission is required')),
				{ enableHighAccuracy: true, maximumAge: 0, timeout: 10000 }
			);
		});

	const handleLivenessComplete = async (livenessEvidence: LivenessEvidence) => {
		if (submitting) return;
		if (!session) {
			rejectionReason = 'Verify the session before starting face liveness';
			showFailure = true;
			return;
		}

		livenessActive = false;
		submitting = true;
		showSuccess = false;
		showFailure = false;
		scanError = null;

		try {
			const gps = await getCurrentPosition();
			if (
				!validateGPS(
					gps.lat,
					gps.lng,
					session.geofence.lat,
					session.geofence.lng,
					session.geofence.radius
				)
			) {
				throw new Error('You are outside the attendance geofence');
			}

			const result = await submitAttendanceScan({
				sessionId: session.sessionId,
				studentNumber,
				gps,
				livenessEvidence,
				scannedAt: new Date().toISOString(),
			});

			if (result.status === 'rejected') {
				rejectionReason = 'The attendance scan was rejected';
				showFailure = true;
				return;
			}

			resultStatus = result.status;
			scannedAt = result.scannedAt;
			showSuccess = true;
			countdown = 3;
			countdownTimerId = setInterval(() => {
				countdown -= 1;
				if (countdown <= 0) {
					clearCountdown();
					showSuccess = false;
					goto(Routes.DASHBOARD);
				}
			}, 1000);
		} catch (error) {
			rejectionReason = getErrorMessage(error, 'Unable to submit the attendance scan');
			showFailure = true;
		} finally {
			submitting = false;
		}
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

	{#if scanError}
		<p class="error" role="alert">{scanError}</p>
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
					<button
						class="btn-secondary"
						disabled={verifying}
						onclick={() => void handleVerifyCode()}
					>
						{verifying ? 'Verifying…' : 'Verify Code'}
					</button>
				</div>
			</section>

			<p class="footnote">
				Verify the session code to open the QR scanner, then complete face liveness.
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
					Scan the session QR code shown on the projector. Face liveness opens after verification.
				</p>
			</section>
		</div>
	{:else}
		<div class="page">
			<div class="page-header">
				<button class="back-btn" onclick={backToQr}>
					← <span>Back</span>
				</button>
				<h1>Face Liveness</h1>
			</div>

			<section class="card">
				<h2 class="section-title">Complete Liveness Check</h2>
				<div class="viewport">
					<FaceScanner active={livenessActive} onComplete={handleLivenessComplete} />
				</div>
				<p class="footnote">
					Blink once, then turn your head left, return to center, turn right, and return to center.
					Your result is submitted to the attendance service for verification.
				</p>
				{#if submitting}
					<p class="footnote">Submitting attendance…</p>
				{/if}
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
				<h3 class="result-title">Attendance {resultStatus === 'late' ? 'Recorded Late' : 'Recorded!'}</h3>
				<p class="result-line">{studentName}</p>
				<p class="result-line">
					{session?.courseCode ?? 'Session'} — {session?.courseName ?? ''}
				</p>
				{#if scannedAt}
					<p class="result-line">{formatTime(scannedAt)}</p>
				{/if}
				<p class="verified">Liveness evidence accepted</p>
				<p class="auto-dismiss">Auto-dismissing in {countdown}s...</p>
			</div>
		</div>
	{/if}

	<!-- Failure Overlay -->
	{#if showFailure}
		<div class="overlay">
			<div class="result">
				<h3 class="result-title">Attendance Rejected</h3>
				<div class="reject-reason">{rejectionReason || 'The scan could not be accepted'}</div>
				<p class="reject-desc">
					The attendance service rejected this scan. You can try again.
				</p>
				<button class="btn-primary try-again" onclick={retryLiveness}>
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