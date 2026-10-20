<script lang="ts">
	import SkeletonDetail from '$lib/components/SkeletonDetail.svelte';
	import { onMount } from 'svelte';
	import { studentState, initStudent } from '$lib/features/student/store.svelte';
	import { faceCacheState, refreshFaceCache } from '$lib/features/student/face.svelte';
	import { formatDate } from '$lib/shared/utils/format';

	const faceCacheLabel = $derived(
		faceCacheState.state === 'current' || faceCacheState.state === 'updated'
			? `Cached on this device${faceCacheState.version !== null ? ` (v${faceCacheState.version})` : ''}`
			: faceCacheState.state === 'absent'
				? 'No face data on file'
				: 'Offline face data unavailable'
	);

	onMount(() => {
		void initStudent().then(() => {
			// Re-pull on profile visits: an admin may have enrolled or
			// re-enrolled the student after sign-in.
			const profile = studentState.student;
			if (profile?.email) void refreshFaceCache(profile.email, profile.faceEnrolled);
		});
	});

	const student = $derived(studentState.student);

	// My QR is generated on-device from the student number (no backend QR
	// route exists). Dynamic import keeps it client-side; failures fall back
	// to the number below rather than a broken image.
	let qrDataUrl = $state<string | null>(null);
	let qrFailed = $state(false);

	$effect(() => {
		const code = student?.studentNumber?.trim() ?? '';
		if (!code) {
			qrDataUrl = null;
			qrFailed = false;
			return;
		}
		let cancelled = false;
		qrFailed = false;
		void import('qrcode')
			.then(({ default: QRCode }) => QRCode.toDataURL(code, { margin: 1, width: 256 }))
			.then((url) => {
				if (!cancelled) qrDataUrl = url;
			})
			.catch(() => {
				if (!cancelled) {
					qrDataUrl = null;
					qrFailed = true;
				}
			});
		return () => {
			cancelled = true;
		};
	});

	const fullName = $derived(
		student
			? [student.firstName, student.middleName, student.lastName].filter(Boolean).join(' ')
			: ''
	);

	const initials = $derived(
		student
			? [student.firstName, student.lastName]
					.map((name) => (name ? name[0] : ''))
					.filter(Boolean)
					.join('')
			: ''
	);

	const accountLabel = $derived(
		student?.createdAt
			? new Date(student.createdAt).toLocaleDateString(undefined, {
					month: 'short',
					year: 'numeric',
				})
			: '—'
	);
</script>

<div class="wrap">
	<header class="header">
		<h1>My Profile</h1>
		<p class="muted">Read-only · identity is managed by your administrator</p>
	</header>

	{#if studentState.loading}
		<SkeletonDetail rows={4} label="Loading profile…" />
	{:else if student}
		<section class="card identity">
			<div class="avatar">{initials}</div>
			<div class="identity-grid">
				<span class="field">Student ID</span>
				<span>{student.studentNumber}</span>
				<span class="field">Name</span>
				<span>{fullName}</span>
				<span class="field">Program</span>
				<span>
					{student.programCode}
					{#if student.programName}<span class="muted">· {student.programName}</span>{/if}
				</span>
				<span class="field">Year Level</span>
				<span>{student.yearLevelLabel}</span>
				{#if student.section}
					<span class="field">Section</span>
					<span>{student.section}</span>
				{/if}
				<span class="field">Email</span>
				<span>{student.email || '—'}</span>
			</div>
		</section>

		<section class="card">
			<h2 class="section-title">Face Enrollment</h2>
			<div class="face-row">
				<span class="badge" class:ok={student.faceEnrolled}>
					{student.faceEnrolled ? 'Enrolled' : 'Not enrolled'}
				</span>
				<span class="muted">Version {student.faceEmbeddingVersion ?? '—'}</span>
			</div>
			<p class="muted">Enrolled: {student.faceEnrolledAt ? formatDate(student.faceEnrolledAt) : '—'}</p>
			{#if student.faceEnrolled}
				<p class="muted">Offline-ready: {faceCacheLabel}</p>
			{/if}
		</section>

		<section class="card">
			<h2 class="section-title">My QR</h2>
			<div class="qr-tile">
				{#if qrDataUrl}
					<img class="qr-code" src={qrDataUrl} alt="QR code for {student.studentNumber}" width="128" height="128" />
				{:else}
					<div class="qr-placeholder">QR</div>
				{/if}
				<div class="qr-label">{student.studentNumber}</div>
			</div>
			{#if qrFailed}
				<p class="muted qr-note">Could not render the QR code — show your student number above instead.</p>
			{:else}
				<p class="muted qr-note">Generated on this device from your student number.</p>
			{/if}
		</section>

		<div class="admin-note">Changes to your profile are handled by your administrator.</div>

		<p class="meta muted">Account: {accountLabel} · Scans: {student.scanCount ?? 0}</p>
	{:else if studentState.error}
		<p class="empty">Could not load your profile: {studentState.error}</p>
	{:else}
		<p class="empty">No profile data available for this account.</p>
	{/if}
</div>

<style>
	.wrap {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		max-width: 720px;
		margin-inline: auto;
	}

	.header h1 {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0 0 0.25rem;
	}

	.muted {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 1.5rem;
		box-shadow: var(--shadow-sm);
	}

	.section-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.0625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0 0 1rem;
	}

	.identity {
		display: flex;
		gap: 1.5rem;
		align-items: flex-start;
		flex-wrap: wrap;
	}

	.avatar {
		width: 72px;
		height: 72px;
		border-radius: 50%;
		background: var(--brand);
		color: var(--on-brand);
		display: flex;
		align-items: center;
		justify-content: center;
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.5rem;
		font-weight: 700;
		flex-shrink: 0;
	}

	.identity-grid {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 0.5rem 1.5rem;
		font-size: 0.9375rem;
		color: var(--text-secondary);
		min-width: 0;
	}

	.field {
		font-size: 0.8125rem;
		font-weight: 700;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.02em;
		padding-top: 0.0625rem;
	}

	.face-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 0.75rem;
	}

	.badge {
		display: inline-block;
		padding: 0.25rem 0.75rem;
		border-radius: 999px;
		font-size: 0.8125rem;
		font-weight: 700;
		background: var(--bg-muted);
		color: var(--text-muted);
	}

	.badge.ok {
		background: var(--success-bg);
		color: var(--success);
	}

	.qr-tile {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.75rem;
	}

	.qr-placeholder {
		width: 128px;
		height: 128px;
		border: 2px dashed var(--border-strong);
		border-radius: 8px;
		display: flex;
		align-items: center;
		justify-content: center;
		color: #94a3b8;
		font-size: 0.875rem;
		font-weight: 700;
	}

	.qr-code {
		width: 128px;
		height: 128px;
		border-radius: 8px;
		image-rendering: pixelated;
	}

	.qr-label {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.9375rem;
		font-weight: 700;
		color: var(--text);
	}

	.qr-note {
		text-align: center;
	}

	.admin-note {
		padding: 0.75rem 1rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--bg-page);
		color: var(--text-muted);
		font-size: 0.875rem;
		text-align: center;
	}

	.meta {
		text-align: center;
		font-size: 0.8125rem;
	}

	.empty {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 2rem;
		color: var(--text-muted);
		font-size: 0.9375rem;
		margin: 0;
	}

	@media (max-width: 640px) {
		.identity {
			flex-direction: column;
			align-items: center;
			text-align: center;
		}

		.identity-grid {
			grid-template-columns: 1fr;
			text-align: left;
			width: 100%;
		}
	}
</style>