<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { initFaceModel } from '$lib/features/liveness/model';
	import { trapFocus } from '$lib/shared/actions/focusTrap';
	import { Html5Qrcode } from 'html5-qrcode';
	import QRScanner from '$lib/features/liveness/components/QRScanner.svelte';
	import FaceScanner from '$lib/features/liveness/components/FaceScanner.svelte';
	import {
		precheckScan,
		submitAttendanceScan,
		validateGPS,
		verifySessionCode,
		type SessionVerification
	} from '$lib/features/liveness/service';
	import {
		cacheSession,
		flushQueue,
		getCachedSession,
		newQueueId,
		queue,
		registerOutboxSync,
		retryDelayMs,
		type QueuedScan
	} from '$lib/features/sync/service';
	import { initStudent, studentState } from '$lib/features/student/store.svelte';
	import { APIError, isMockMode } from '$lib/api/client';
	import { Routes } from '$lib/shared/constants/routes';
	import { formatLocalDateTime } from '$lib/shared/utils/format';
	import type { LivenessEvidence } from '$lib/shared/types';

	type Step = 'entry' | 'confirm' | 'liveness';

	let sessionCode = $state('');
	let session = $state<SessionVerification | null>(null);
	let step = $state<Step>('entry');
	let uploading = $state(false);
	let fileInput: HTMLInputElement | null = $state(null);
	// D27 step-2 ID gate: the number is editable and compared server-side
	// case-insensitively (403 student_number_mismatch on spoof). Identity
	// always resolves from the authenticated user — the input can never
	// impersonate another student.
	let idNumber = $state('');
	let checkingId = $state(false);
	let verifiedNumber = $state('');
	let verifiedName = $state('');
	let precheckFailed = $state(false);
	let alreadyScannedStop = $state(false);
	let showPermission = $state(false);
	let qrActive = $state(false);
	let livenessActive = $state(false);
	let showSuccess = $state(false);
	let showFailure = $state(false);
	let verifying = $state(false);
	let submitting = $state(false);
	let offline = $state(typeof navigator !== 'undefined' ? !navigator.onLine : false);
	let pendingCount = $state(0);
	let rejectedItems = $state<QueuedScan[]>([]);
	let showQueued = $state(false);
	let queuedCode = $state('');
	let flushing = $state(false);
	let retryTimerId: ReturnType<typeof setTimeout> | null = null;
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

	// Success overlay owns its auto-dismiss timer. Done navigates away,
	// Stay keeps the receipt open (stops the timer) for screenshots, slow
	// readers, and switch control — Escape still dismisses via onOverlayKeydown.
	const dismissSuccess = () => {
		clearCountdown();
		showSuccess = false;
		void goto(Routes.DASHBOARD);
	};

	const stayOnSuccess = () => {
		clearCountdown();
	};

	const getErrorMessage = (error: unknown, fallback: string) =>
		error instanceof Error ? error.message : fallback;

	// D15 rejection reasons + session lookup failures mapped to user text.
	// Raw codes never reach the UI.
	const SCAN_ERROR_MESSAGES: Record<string, string> = {
		duplicate_scan: 'You have already scanned for this session.',
		outside_geofence: 'You are outside the attendance geofence.',
		liveness_failed: 'Liveness check failed. Please try again in good lighting.',
		face_mismatch: 'Face did not match the enrolled record. Please try again.',
		face_not_enrolled: 'Face enrollment is required before you can proceed with attendance. Please contact your administrator to complete your face enrollment.',
		not_enrolled: 'You are not enrolled in this course offering.',
		student_number_mismatch: 'That ID number does not match your account.',
		student_not_found: 'No student record found for your account. Contact an administrator.',
		session_expired: 'This session has closed for scanning.',
		session_not_found: 'Session not found. Check the code and try again.',
	};

	const toUserMessage = (error: unknown, fallback: string): string => {
		if (error instanceof APIError && error.code && SCAN_ERROR_MESSAGES[error.code]) {
			return SCAN_ERROR_MESSAGES[error.code];
		}
		if (error instanceof APIError && error.status === 410) {
			return 'This session has closed for scanning.';
		}
		return getErrorMessage(error, fallback);
	};

	// Only transport failures may be queued/retried as offline
	// ('network_error' from the fetch wrapper, plus 'request_timeout' whose
	// idempotent replay is safe via X-Idempotency-Key). Any other APIError is
	// a server decision (4xx rejections) and must never be queued; any
	// non-APIError is a local bug (GPS, programming error) and must surface.
	const isNetworkError = (error: unknown): boolean =>
		error instanceof APIError && (error.code === 'network_error' || error.code === 'request_timeout');

	const refreshQueueState = async () => {
		try {
			pendingCount = await queue.getPendingCount();
			rejectedItems = await queue.getRejected();
		} catch {
			pendingCount = 0;
			rejectedItems = [];
		}
	};

	const clearRetryTimer = () => {
		if (retryTimerId) clearTimeout(retryTimerId);
		retryTimerId = null;
	};

	const flushNow = async () => {
		if (flushing) return;
		flushing = true;
		try {
			const result = await flushQueue();
			await refreshQueueState();
			if (result.failed > 0) {
				const pending = await queue.getPending().catch(() => []);
				const worst = pending.reduce((max, item) => Math.max(max, item.attempts), 0);
				clearRetryTimer();
				retryTimerId = setTimeout(() => void flushNow(), retryDelayMs(worst));
			}
		} finally {
			flushing = false;
		}
	};

	const retryRejected = async (id: string) => {
		await queue.updateStatus(id, 'pending').catch(() => undefined);
		await flushNow();
	};

	const discardRejected = async (id: string) => {
		await queue.remove(id).catch(() => undefined);
		await refreshQueueState();
	};

	const rejectedMessage = (code: string | null): string =>
		(code && SCAN_ERROR_MESSAGES[code]) || 'The attendance scan was rejected.';

	onDestroy(() => {
		clearCountdown();
		clearRetryTimer();
	});

	onMount(() => {
		void initFaceModel();
		if (!studentState.student && !studentState.loading) {
			void initStudent();
		}
		const handleOnline = () => {
			offline = false;
			void flushNow();
		};
		const handleOffline = () => {
			offline = true;
		};
		window.addEventListener('online', handleOnline);
		window.addEventListener('offline', handleOffline);
		// Service-worker Background Sync relay: a worker wake-up (e.g. after
		// a browser restart) asks open pages to run the authed drain.
		const handleWorkerMessage = (event: MessageEvent) => {
			if ((event.data as { type?: unknown } | null)?.type === 'FLUSH_OUTBOX') {
				void flushNow();
			}
		};
		if ('serviceWorker' in navigator) {
			navigator.serviceWorker.addEventListener('message', handleWorkerMessage);
		}
		void refreshQueueState().then(() => {
			if (pendingCount > 0) void registerOutboxSync().catch(() => undefined);
		});
		if (navigator.onLine) void flushNow();
		return () => {
			window.removeEventListener('online', handleOnline);
			window.removeEventListener('offline', handleOffline);
			if ('serviceWorker' in navigator) {
				navigator.serviceWorker.removeEventListener('message', handleWorkerMessage);
			}
		};
	});

	const verifyCode = async (code: string) => {
		const normalizedCode = code.trim();
		if (!normalizedCode || verifying) return;

		// Check if we're trying to scan a different session code than already verified
		if (session && sessionCode && sessionCode !== normalizedCode) {
			scanError = `Session changed from ${sessionCode} to ${normalizedCode}. Please restart your ID check.`;
			// Reset to entry step to force restart
			backToEntry();
			return;
		}

		verifying = true;
		scanError = null;
		try {
			const verifiedSession = await verifySessionCode(normalizedCode);
			sessionCode = normalizedCode;
			session = verifiedSession;
			void cacheSession({
				session_id: verifiedSession.sessionId,
				code: normalizedCode,
				course_code: verifiedSession.courseCode,
				course_name: verifiedSession.courseName,
				expires_at: verifiedSession.expiresAt,
				geofence: verifiedSession.geofence,
				geofenceEnabled: verifiedSession.geofenceEnabled,
				isRemote: verifiedSession.isRemote
			}).catch(() => undefined);
			showFailure = false;
			rejectionReason = '';
			precheckFailed = false;
			alreadyScannedStop = false;
			qrActive = false;
			if (!idNumber) idNumber = studentNumber;
			goToConfirm();
		} catch (error) {
			// Offline with a fresh cached config for this code: the session was
			// verified before the signal dropped, so the scan may proceed —
			// the server re-validates everything on sync. Precheck is a server
			// gate and cannot run offline, so it is skipped here.
			if (isNetworkError(error)) {
				const cached = await getCachedSession(normalizedCode).catch(() => null);
				if (cached) {
					sessionCode = normalizedCode;
					session = {
						sessionId: cached.session_id,
						courseCode: cached.course_code,
						courseName: cached.course_name,
						expiresAt: cached.expires_at,
						geofence: cached.geofence,
						geofenceEnabled: cached.geofenceEnabled,
						isRemote: cached.isRemote,
						scheduledEndTime: cached.expires_at
					};
					showFailure = false;
					rejectionReason = '';
					precheckFailed = false;
					alreadyScannedStop = false;
					qrActive = false;
					if (!idNumber) idNumber = studentNumber;
					goToConfirm();
					return;
				}
			}
			scanError = toUserMessage(error, 'Unable to verify the session code');
		} finally {
			verifying = false;
		}
	};

	const handleVerifyCode = () => {
		void verifyCode(sessionCode);
	};

	const handleScanned = (code: string) => {
		void verifyCode(code);
	};

	const handleUploadClick = () => {
		fileInput?.click();
	};

	const handleFileChange = async (event: Event) => {
		const input = event.target as HTMLInputElement;
		const file = input.files?.[0];
		if (!file || uploading) return;
		uploading = true;
		scanError = null;
		try {
			const scanner = new Html5Qrcode('upload-qr-reader');
			const decoded = await scanner.scanFile(file, false);
			try { scanner.clear(); } catch { /* ignore */ }
			if (!decoded) {
				scanError = 'Could not read a QR code from that image. Try another image or enter the code manually.';
				return;
			}
			await verifyCode(decoded);
		} catch {
			scanError = 'Could not read a QR code from that image. Try another image or enter the code manually.';
		} finally {
			uploading = false;
			input.value = '';
		}
	};

	// D27 step-2 gate: enrollment + duplicate check before GPS/face run.
	// Flags (not raises) enrolled/already_scanned; hard-stops on both.
	// Offline skips the gate — the server re-validates on submit/sync.
	const checkId = async () => {
		if (!session || checkingId) return;
		const entered = idNumber.trim();
		if (!entered) {
			scanError = 'Enter your student ID number to continue.';
			return;
		}

		checkingId = true;
		scanError = null;
		try {
			const result = await precheckScan({ sessionId: session.sessionId, studentNumber: entered });
			if (!result.enrolled) {
				precheckFailed = true;
				rejectionReason = SCAN_ERROR_MESSAGES.not_enrolled;
				showFailure = true;
				return;
			}
			if (result.alreadyScanned) {
				precheckFailed = true;
				alreadyScannedStop = true;
				rejectionReason = SCAN_ERROR_MESSAGES.duplicate_scan;
				showFailure = true;
				return;
			}
			if (!isMockMode() && studentState.student?.faceEnrolled === false) {
				precheckFailed = true;
				rejectionReason = SCAN_ERROR_MESSAGES.face_not_enrolled;
				showFailure = true;
				return;
			}
			verifiedNumber = entered;
			verifiedName = result.studentName;
			startLiveness();
		} catch (error) {
			if (isNetworkError(error)) {
				// Offline: proceed without the gate; submit queues for sync.
				verifiedNumber = entered;
				startLiveness();
				return;
			}
			scanError = toUserMessage(error, 'Unable to check your ID number');
		} finally {
			checkingId = false;
		}
	};

	const goToConfirm = () => {
		qrActive = false;
		livenessActive = false;
		showSuccess = false;
		showFailure = false;
		scanError = null;
		step = 'confirm';
	};

	const backToConfirm = () => {
		if (submitting) return;
		livenessActive = false;
		showFailure = false;
		rejectionReason = '';
		scanError = null;
		precheckFailed = false;
		alreadyScannedStop = false;
		step = 'confirm';
	};

	const startLiveness = () => {
		qrActive = false;
		showPermission = false;
		showSuccess = false;
		showFailure = false;
		showQueued = false;
		scannedAt = '';
		step = 'liveness';
		livenessActive = true;
	};

	const backToEntry = () => {
		if (submitting) return;
		submitting = false;
		checkingId = false;
		verifying = false;
		clearCountdown();
		qrActive = false;
		livenessActive = false;
		showPermission = false;
		showSuccess = false;
		showFailure = false;
		uploading = false;
		precheckFailed = false;
		alreadyScannedStop = false;
		verifiedNumber = '';
		verifiedName = '';
		session = null;
		scanError = null;
		rejectionReason = '';
		scannedAt = '';
		showQueued = false;
		step = 'entry';
	};

	const retryLiveness = () => {
		showFailure = false;
		showQueued = false;
		rejectionReason = '';
		scanError = null;
		startLiveness();
	};

	// Escape closes whichever scan overlay is open, mirroring the visible button
	// on each so keyboard and pointer users get the same outcome. The success
	// overlay follows its own auto-dismiss path (clear the timer, return to the
	// dashboard) rather than dropping the student back at the entry step.
	// This window-level handler is the single Escape owner for all four overlays;
	// the dialogs use `use:trapFocus` for Tab containment and focus restore only,
	// so Escape is never handled twice.
	const onOverlayKeydown = (event: KeyboardEvent) => {
		if (event.key !== 'Escape') return;
		if (showPermission || showQueued || showFailure) {
			backToEntry();
		} else if (showSuccess) {
			dismissSuccess();
		}
	};

	const getPositionOnce = (
		options: PositionOptions
	): Promise<{ lat: number; lng: number; accuracy: number }> =>
		new Promise((resolve, reject) => {
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
				(err) => {
					if (err.code === err.PERMISSION_DENIED) {
						reject(new Error('Location permission is required'));
					} else if (err.code === err.TIMEOUT) {
						reject(new Error('Location timed out. Try again near a window or outdoors.'));
					} else {
						reject(new Error('Unable to read your location. Try again.'));
					}
				},
				options
			);
		});

	const getCurrentPosition = async (): Promise<{
		lat: number;
		lng: number;
		accuracy: number;
	}> => {
		// High-accuracy first; on timeout fall back once to a faster low-power
		// fix so a weak GPS signal still yields a scan instead of a hard fail.
		try {
			return await getPositionOnce({ enableHighAccuracy: true, maximumAge: 0, timeout: 10000 });
		} catch (e) {
			if (e instanceof Error && e.message.includes('timed out')) {
				return await getPositionOnce({ enableHighAccuracy: false, maximumAge: 30000, timeout: 8000 });
			}
			throw e;
		}
	};

	const handleLivenessComplete = async (livenessEvidence: LivenessEvidence) => {
		if (submitting) return;
		if (!session) {
			rejectionReason = 'Verify the session before starting face liveness';
			showFailure = true;
			return;
		}
		// Prefer the precheck-verified number; fall back to the profile when
		// the gate was skipped offline.
		const submitNumber = verifiedNumber || studentNumber;
		if (!submitNumber) {
			rejectionReason = 'Student profile is unavailable. Reload and try again.';
			showFailure = true;
			return;
		}

		// Generate idempotency key once per attempt (shared between live POST and offline replay)
		const idempotencyKey = newQueueId();

		livenessActive = false;
		submitting = true;
		showSuccess = false;
		showFailure = false;
		showQueued = false;
		scanError = null;

		let gps: { lat: number; lng: number; accuracy: number } | null = null;
		let reachedSubmit = false;
		try {
			// Location is only required when the session actually enforces a
			// geofence. Requesting it otherwise (no classroom, disabled, or
			// remote) would prompt for permission without a feature needing it.
			const geofenceRequired =
				session.geofenceEnabled !== false &&
				session.isRemote !== true &&
				session.geofence.lat !== null &&
				session.geofence.lng !== null;
			if (geofenceRequired) {
				gps = await getCurrentPosition();
				// The contract allows a null center (session/schema.py VerifyGeofence),
				// and the server skips its check in that case — so does this pre-check.
				// Without the guard, null coerces to 0 in the Haversine math and every
				// scan reads as thousands of km "outside" a center that was never set.
				if (
					!validateGPS(
						gps.lat,
						gps.lng,
						session.geofence.lat as number,
						session.geofence.lng as number,
						session.geofence.radius
					)
				) {
					throw new Error('You are outside the attendance geofence');
				}
			}

			reachedSubmit = true;
			const result = await submitAttendanceScan({
				sessionId: session.sessionId,
				studentNumber: submitNumber,
				gps,
				livenessEvidence,
				scannedAt: new Date().toISOString(),
				idempotencyKey,
			});

			if (result.status === 'rejected') {
				rejectionReason =
					'The attendance scan was rejected. Check your enrollment, location, and lighting, then try again.';
				showFailure = true;
				return;
			}

			resultStatus = result.status;
			scannedAt = result.scannedAt;
			showSuccess = true;
			clearCountdown();
			countdown = 3;
			countdownTimerId = setInterval(() => {
				countdown -= 1;
				if (countdown <= 0) {
					dismissSuccess();
				}
			}, 1000);
		} catch (error) {
			// The scan completed locally but the POST never reached the server:
			// queue the evidence (device-time scanned_at) for automatic sync.
			// Anything before the POST — GPS, geofence, server rejections —
			// keeps the failure overlay, since there is nothing valid to queue.
			if (reachedSubmit && session && isNetworkError(error)) {
				try {
					await queue.enqueue({
						type: 'attendance_scan',
						payload: {
							sessionId: session.sessionId,
							sessionCode,
							studentNumber: submitNumber,
							gps,
							livenessEvidence,
							scannedAt: new Date().toISOString(),
							idempotencyKey
						}
					});
					await refreshQueueState();
					livenessActive = false;
					showQueued = true;
					queuedCode = sessionCode;
				} catch {
					rejectionReason = toUserMessage(error, 'Unable to submit the attendance scan');
					showFailure = true;
				}
			} else {
				rejectionReason = toUserMessage(error, 'Unable to submit the attendance scan');
				showFailure = true;
			}
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
	{#if offline || pendingCount > 0}
		<div class="offline-banner">
			{#if isMockMode() && pendingCount > 0}
				Mock mode · {pendingCount} queued (sync disabled without a backend).
			{:else if offline}
				You are offline · Records will sync when connected.
			{:else}
				Back online · Syncing queued records.
			{/if}
			{#if pendingCount > 0}
				<span class="offline-count">{pendingCount} pending</span>
			{/if}
			{#if !offline && pendingCount > 0 && !isMockMode()}
				<button class="banner-retry" onclick={() => void flushNow()} disabled={flushing}>
					{flushing ? 'Syncing…' : 'Retry now'}
				</button>
			{/if}
		</div>
	{/if}

	{#if rejectedItems.length > 0}
		<div class="rejected-card" role="status">
			{#each rejectedItems as item (item.id)}
				<p class="rejected-row">
					<span>{item.payload.sessionCode} · {rejectedMessage(item.lastError)}</span>
					<span class="rejected-actions">
						<button class="banner-retry" onclick={() => void retryRejected(item.id)}>Retry</button>
						<button class="banner-retry" onclick={() => void discardRejected(item.id)}>Discard</button>
					</span>
				</p>
			{/each}
		</div>
	{/if}

	{#if scanError}
		<p class="error" role="alert">{scanError}</p>
	{/if}

	<div aria-live="polite" class="sr-only">
		{verifying ? 'Verifying session code' : uploading ? 'Reading QR image' : ''}
	</div>

	{#if step === 'entry'}
		<div class="page">
			<div class="page-header">
				<button class="back-btn" onclick={() => goto(Routes.DASHBOARD)}>
					← <span>Back</span>
				</button>
				<h1>Scan to Attend</h1>
			</div>

			<!-- QR Code Scanner (primary) -->
			<section class="card">
				<h2 class="section-title">Scan Session QR Code</h2>
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

				{#if verifying}
					<p class="footnote" aria-live="polite">Verifying session…</p>
				{:else}
					<p class="footnote">Align the QR code within the frame, or upload an image below.</p>
				{/if}

				<div class="camera-actions">
					<button
						class={qrActive ? 'btn-danger' : 'btn-primary'}
						onclick={toggleQr}
						disabled={verifying || uploading}
					>
						{qrActive ? 'Stop Camera' : 'Start Camera'}
					</button>
					<button
						class="btn-secondary"
						disabled={uploading || qrActive}
						onclick={handleUploadClick}
					>
						{uploading ? 'Reading…' : 'Upload QR image'}
					</button>
				</div>

				<div id="upload-qr-reader" style="display: none;"></div>
				<input
					bind:this={fileInput}
					type="file"
					accept="image/*"
					style="display: none;"
					onchange={handleFileChange}
				/>

				<p class="footnote">
					Point the camera at the session QR code shown on the projector, or upload a
					screenshot/photo of it.
				</p>
			</section>

			<!-- Manual entry -->
			<section class="card">
				<h2 class="section-title">Session Code (manual entry)</h2>
				<div class="code-row">
					<input
						class="form-input code-input code-input-plain"
						placeholder="Enter code from projector (e.g. wan9YQXY)"
						aria-label="Session code"
						autocomplete="off"
						spellcheck={false}
						value={sessionCode}
						oninput={(e) => { sessionCode = (e.target as HTMLInputElement).value; }}
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
				Scan the QR code (or enter a code manually), complete session confirmation, then
				finish face liveness.
			</p>
		</div>
	{:else if step === 'confirm'}
		<div class="page">
			<div class="page-header">
				<button class="back-btn" onclick={backToEntry} disabled={verifying}>
					← <span>Back</span>
				</button>
				<h1>Session Confirmation</h1>
			</div>
			{#if session}
				<p class="footnote" style="margin-top: -0.5rem; margin-bottom: 1rem; font-weight: 600;">
					{session.courseCode} — {session.courseName}
				</p>
				<p class="footnote" style="margin-top: -0.75rem; margin-bottom: 1rem;">
					{session.sessionType ?? 'Session'} · {session.isRemote ? 'Remote / online' : (session.classroomName ?? 'On campus')}
				</p>
			{/if}

			{#if verifying}
				<section class="card">
					<p class="footnote">Verifying session…</p>
				</section>
			{:else if !session}
				<section class="card">
					<p class="error" role="alert">Session information is unavailable. Go back and try again.</p>
				</section>
			{:else}
				<section class="card">
					<h2 class="section-title">Session details</h2>
					<div class="ticket-lines">
						<p class="ticket-line">
							<span class="ticket-label">Course</span>
							<span class="ticket-value">
								<span class="mono-data">{session.courseCode}</span>
								{session.courseName}
							</span>
						</p>
						<p class="ticket-line">
							<span class="ticket-label">Session type</span>
							<span class="ticket-value">{session.sessionType ?? '—'}</span>
						</p>
						<p class="ticket-line">
							<span class="ticket-label">Session ends</span>
							<span class="ticket-value mono-data">{formatLocalDateTime(session.expiresAt)}</span>
						</p>
						<p class="ticket-line">
							<span class="ticket-label">Class ends</span>
							<span class="ticket-value mono-data">{session.scheduledEndTime ? formatLocalDateTime(session.scheduledEndTime) : '—'}</span>
						</p>
						<p class="ticket-line">
							<span class="ticket-label">Location</span>
							<span class="ticket-value">
								{#if session.isRemote}
									Remote / online session
								{:else if session.classroomName}
									{session.classroomName}
								{:else if session.geofence.lat !== null && session.geofence.lng !== null}
									Classroom coordinates available
								{:else}
									No classroom location
								{/if}
							</span>
						</p>
						<p class="ticket-line">
							<span class="ticket-label">Student ID</span>
							<span class="ticket-value mono-data">{idNumber || '—'}</span>
						</p>
						{#if !session.isRemote && session.geofence.lat !== null && session.geofence.lng !== null}
							<p class="ticket-line">
								<span class="ticket-label">Map</span>
								<span class="ticket-value">
									<a
										href={`https://www.openstreetmap.org/?mlat=${session.geofence.lat}&mlon=${session.geofence.lng}#map=17/${session.geofence.lat}/${session.geofence.lng}`}
										target="_blank"
										rel="noopener noreferrer"
									>
										View on map
									</a>
								</span>
							</p>
							<div class="map-preview">
								<iframe
									title="Classroom location"
									src={`https://www.openstreetmap.org/export/embed.html?bbox=${session.geofence.lng - 0.005},${session.geofence.lat - 0.005},${session.geofence.lng + 0.005},${session.geofence.lat + 0.005}&layer=mapnik&marker=${session.geofence.lat},${session.geofence.lng}`}
									loading="lazy"
								></iframe>
							</div>
						{/if}
					</div>

					{#if !idNumber}
						<p class="footnote">Your student ID is not available. Please complete your profile.</p>
					{/if}

					<div class="camera-actions" style="margin-top: 1.25rem;">
						<button
							class="btn-secondary"
							disabled={checkingId || !idNumber}
							onclick={() => void checkId()}
						>
							{checkingId ? 'Checking…' : 'Confirm'}
						</button>
						<button class="btn-secondary" onclick={backToEntry} disabled={verifying}>
							Cancel
						</button>
					</div>
				</section>
			{/if}
		</div>
	{:else}
		<div class="page">
			<div class="page-header">
				<button class="back-btn" onclick={backToConfirm} disabled={submitting}>
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
					Phase 2: blink once for face liveness — then the head-tilt check
					starts automatically (left, center, right, center).
					Your result is submitted to the attendance service for verification.
					The face-match score sent with your scan is a provisional client
					value while server-side matching lands — what is verified today
					is your liveness evidence.
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
			<div
				class="modal"
				role="dialog"
				aria-modal="true"
				aria-labelledby="scan-permission-title"
				tabindex="-1"
				use:trapFocus
			>
				<h3 id="scan-permission-title" class="modal-title">Allow Access</h3>
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
			<div
				class="result ticket"
				role="alertdialog"
				aria-modal="true"
				aria-labelledby="scan-success-title"
				tabindex="-1"
				use:trapFocus
			>
				<div class="ticket-main">
					<p class="ticket-eyebrow">Attendly · Check-in record</p>
					<span class="stamp" class:stamp-late={resultStatus === 'late'}>
						{resultStatus === 'late' ? 'Late' : 'Present'}
					</span>
					<h3 id="scan-success-title" class="result-title">
						Attendance {resultStatus === 'late' ? 'Recorded Late' : 'Recorded!'}
					</h3>
					<div class="ticket-lines">
						<p class="ticket-line">
							<span class="ticket-label">Student</span>
							<span class="ticket-value">{studentName}</span>
						</p>
						<p class="ticket-line">
							<span class="ticket-label">Course</span>
							<span class="ticket-value">
								<span class="mono-data">{session?.courseCode ?? 'Session'}</span>
								{session?.courseName ?? ''}
							</span>
						</p>
						{#if scannedAt}
							<p class="ticket-line">
								<span class="ticket-label">Recorded</span>
								<span class="ticket-value mono-data">{formatLocalDateTime(scannedAt)}</span>
							</p>
						{/if}
					</div>
					<p class="verified">Liveness evidence accepted</p>
					<p class="verify-note">Face match provisional — liveness verified</p>
				</div>
				<div class="ticket-foot">
					<p class="auto-dismiss">
						{#if countdown > 0}
							Auto-dismissing in <span class="mono-data">{countdown}s</span>…
						{:else}
							Auto-dismiss paused — receipt stays open.
						{/if}
					</p>
					<div class="result-actions">
						<button class="btn-primary try-again" onclick={dismissSuccess}>Done</button>
						{#if countdown > 0}
							<button class="btn-secondary try-again" onclick={stayOnSuccess}>Stay</button>
						{/if}
					</div>
				</div>
			</div>
		</div>
	{/if}

	<!-- Queued Overlay -->
	{#if showQueued}
		<div class="overlay">
			<div
				class="result"
				role="alertdialog"
				aria-modal="true"
				aria-labelledby="scan-queued-title"
				tabindex="-1"
				use:trapFocus
			>
				<h3 id="scan-queued-title" class="result-title">Evidence saved</h3>
				<p class="result-line">{studentName}</p>
				<p class="result-line">
					<span class="mono-data">{session?.courseCode ?? queuedCode}</span>
					{session?.courseName ? ` — ${session.courseName}` : ''}
				</p>
				<p class="reject-desc">
					You are offline. The scan will verify automatically after sync.
				</p>
				<button class="btn-primary try-again" onclick={backToEntry}>Done</button>
			</div>
		</div>
	{/if}

	<!-- Failure Overlay -->
	{#if showFailure}
		<div class="overlay">
			<div
				class="result"
				role="alertdialog"
				aria-modal="true"
				aria-labelledby="scan-failure-title"
				tabindex="-1"
				use:trapFocus
			>
				<h3 id="scan-failure-title" class="result-title">Attendance Rejected</h3>
				<div class="reject-reason">{rejectionReason || 'The scan could not be accepted'}</div>
				<p class="reject-desc">
					The attendance service rejected this scan. You can try again.
				</p>
				{#if alreadyScannedStop}
					<button class="btn-primary try-again" onclick={() => goto(Routes.HISTORY)}>
						View History
					</button>
					<button
						class="btn-primary try-again"
						onclick={() => { showFailure = false; alreadyScannedStop = false; precheckFailed = false; }}
					>
						Back
					</button>
				{:else if precheckFailed}
					<button
						class="btn-primary try-again"
						onclick={() => { showFailure = false; precheckFailed = false; }}
					>
						Try Again
					</button>
				{:else}
					<button class="btn-primary try-again" onclick={retryLiveness}>
						Try Again
					</button>
				{/if}
			</div>
		</div>
	{/if}
</div>

<svelte:window onkeydown={onOverlayKeydown} />

<style>
	.scan {
		display: flex;
		flex-direction: column;
	}

	.offline-banner {
		background: var(--warning-bg);
		border: 1px solid var(--warning-bg);
		border-radius: 8px;
		padding: 0.625rem 1rem;
		margin-bottom: 1rem;
		display: flex;
		align-items: center;
		gap: 0.5rem;
		color: var(--warning-text);
		font-size: 0.875rem;
	}

	.offline-count {
		margin-left: auto;
		font-weight: 700;
	}

	.banner-retry {
		background: var(--bg-card);
		border: 1px solid var(--warning-bg);
		border-radius: 6px;
		padding: 0.25rem 0.625rem;
		font-family: inherit;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--warning-text);
		cursor: pointer;
	}

	.banner-retry:disabled {
		opacity: 0.6;
		cursor: wait;
	}

	.rejected-card {
		background: var(--danger-bg);
		border: 1px solid var(--danger-bg);
		border-radius: 8px;
		padding: 0.625rem 1rem;
		margin-bottom: 1rem;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.rejected-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		margin: 0;
		color: var(--danger-strong);
		font-size: 0.875rem;
	}

	.rejected-actions {
		display: flex;
		gap: 0.375rem;
		flex-shrink: 0;
	}

	.rejected-actions .banner-retry {
		border-color: var(--danger-bg);
		color: var(--danger-strong);
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
		color: var(--accent);
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
		color: var(--brand);
		margin: 0;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 1.25rem;
		margin-bottom: 1.25rem;
		box-shadow: var(--shadow-sm);
	}

	.section-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.0625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0 0 1rem;
	}

	.code-row {
		display: flex;
		gap: 0.75rem;
	}

	.form-input {
		width: 100%;
		padding: 0.625rem 0.875rem;
		border: 1.5px solid var(--border-strong);
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		outline: none;
		transition: border-color 0.15s;
		background: var(--bg-card);
	}

	.form-input:focus {
		border-color: var(--accent);
	}

	.code-input {
		flex: 1;
		min-width: 0;
		font-family: 'JetBrains Mono', monospace;
		letter-spacing: 0.1em;
		text-transform: uppercase;
	}

	.code-input-plain {
		text-transform: none;
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
		background: var(--brand);
		border: 1px solid var(--brand);
		color: var(--on-brand);
		box-shadow: 0 4px 14px rgba(30, 58, 95, 0.28);
	}

	.btn-primary:hover {
		background: var(--brand-hover);
		border-color: var(--brand-hover);
		transform: translateY(-1px);
	}

	.btn-secondary {
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		color: var(--text-strong);
	}

	.btn-secondary:hover {
		background: var(--bg-hover);
	}

	.btn-danger {
		background: var(--bg-card);
		border: 1px solid var(--danger);
		color: var(--danger);
	}

	.btn-danger:hover {
		background: var(--danger-bg);
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
		border: 2px dashed var(--border);
	}

	.viewport.inactive {
		background: var(--bg-muted);
	}

	.inactive-content {
		text-align: center;
		color: var(--text-muted);
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

	.viewfinder :global(video) {
		width: 100%;
		height: 100%;
	}

	.corner {
		position: absolute;
		width: 22px;
		height: 22px;
		border: 0 solid var(--border);
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
		background: linear-gradient(90deg, transparent, var(--accent), transparent);
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
		color: var(--text-muted);
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
		background: var(--bg-card);
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
		color: var(--text);
		margin: 0 0 0.75rem;
	}

	.modal-desc {
		color: var(--text-muted);
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
		color: var(--text-muted);
		font-size: 0.8125rem;
		font-family: inherit;
		padding: 0;
	}

	.modal-link:hover {
		color: var(--text-secondary);
		text-decoration: underline;
	}

	/* Receipt card shared by the success/queued/failure overlays. Previously
	 * this was unstyled text (inheriting white --on-brand) floating over the
	 * dimmed page; each overlay now gets a real card surface. */
	.result {
		text-align: center;
		color: var(--text);
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 12px;
		box-shadow: var(--shadow-lg);
		max-width: 380px;
		width: 100%;
		overflow: hidden;
		padding: 1.5rem;
	}

	/* The ticket rebuilds its own ruled sections, so the card's generic
	 * padding drops to zero — header, body, and foot span edge to edge. */
	.result.ticket {
		padding: 0;
	}

	.result-title {
		font-size: 1.125rem;
		font-weight: 700;
		color: var(--text);
		margin: 0 0 0.75rem;
	}

	.result-line {
		color: var(--text-secondary);
		margin: 0 0 0.25rem;
	}

	.verified {
		color: var(--success);
		font-weight: 600;
		font-size: 0.875rem;
		margin: 1rem 0 0;
	}

	.verify-note {
		color: var(--text-muted);
		font-size: 0.8125rem;
		margin: 0.25rem 0 0;
	}

	.auto-dismiss {
		color: var(--text-muted);
		font-size: 0.8125rem;
		margin: 0;
	}

	.reject-reason {
		background: var(--danger-bg);
		border-radius: 8px;
		padding: 0.75rem 1rem;
		margin-bottom: 1rem;
		font-size: 0.875rem;
		color: var(--danger);
	}

	.reject-desc {
		color: var(--text-secondary);
		font-size: 0.875rem;
		margin-bottom: 1.5rem;
	}

	.try-again {
		max-width: 200px;
		margin: 0 auto;
		display: block;
	}

	.result-actions {
		display: flex;
		gap: 0.75rem;
		justify-content: center;
		flex-wrap: wrap;
		margin-top: 1rem;
	}

	.result-actions .try-again {
		margin: 0;
	}

	/* --- Check-in receipt (success overlay only) -------------------------- */
	/* The one showpiece: brand header, a status stamp, mono machine facts,
	 * then a dashed tear into the action strip. Same data the old receipt
	 * read; only the presentation changed, a11y contract untouched. */
	.ticket-main {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.75rem;
		padding: 1.5rem 1.5rem 1.25rem;
	}

	.ticket-eyebrow {
		align-self: stretch;
		font-family: var(--font-data);
		font-size: 0.6875rem;
		font-weight: 500;
		letter-spacing: 0.22em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.stamp {
		font-family: var(--font-data);
		font-size: 1.375rem;
		font-weight: 700;
		letter-spacing: 0.18em;
		text-transform: uppercase;
		color: var(--success);
		border: 2.5px solid currentColor;
		border-radius: 10px;
		padding: 0.5rem 1.25rem 0.4375rem;
		transform: rotate(-4deg);
		animation: stamp-in 240ms cubic-bezier(0.34, 1.4, 0.44, 1) both;
	}

	.stamp-late {
		color: var(--warning-text);
	}

	@keyframes stamp-in {
		from {
			opacity: 0;
			transform: rotate(-4deg) scale(1.6);
		}
		to {
			opacity: 1;
			transform: rotate(-4deg) scale(1);
		}
	}

	.ticket .result-title {
		margin: 0 0 0.25rem;
	}

	.ticket-lines {
		display: grid;
		gap: 0.375rem;
		width: 100%;
		margin: 0;
	}

	.ticket-line {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 1rem;
		margin: 0;
		font-size: 0.9375rem;
	}

	.ticket-label {
		flex: none;
		color: var(--text-muted);
		font-size: 0.8125rem;
	}

	.ticket-value {
		text-align: right;
		font-weight: 600;
		color: var(--text);
		min-width: 0;
		overflow-wrap: anywhere;
	}

	.ticket-foot {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.625rem;
		padding: 0.875rem 1.5rem 1.25rem;
		background: var(--bg-muted);
		border-top: 2px dashed var(--border-strong);
	}

	@media (prefers-reduced-motion: reduce) {
		.scan-line,
		.stamp {
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

	.map-preview {
		width: 100%;
		aspect-ratio: 16 / 9;
		margin-top: 0.75rem;
		border-radius: 8px;
		overflow: hidden;
		border: 1px solid var(--border);
	}

	.map-preview iframe {
		width: 100%;
		height: 100%;
		border: 0;
	}

	:global(.scan button:focus-visible),
	:global(.scan input:focus-visible) {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
</style>