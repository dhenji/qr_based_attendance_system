<script lang="ts">
	import { onMount } from 'svelte';
	import { studentState, initStudent } from '$lib/features/student/store.svelte';
	import { formatDate } from '$lib/shared/utils/format';

	onMount(() => {
		initStudent();
	});

	const student = $derived(studentState.student);

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
		<p class="muted">Loading…</p>
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
		</section>

		<section class="card">
			<h2 class="section-title">My QR</h2>
			<div class="qr-tile">
				<div class="qr-placeholder">QR</div>
				<div class="qr-label">{student.studentNumber}</div>
			</div>
			<p class="muted qr-note">Your QR code will appear here once the backend provides it.</p>
		</section>

		<div class="admin-note">Changes to your profile are handled by your administrator.</div>

		<p class="meta muted">Account: {accountLabel} · Scans: {student.scanCount ?? 0}</p>
	{:else}
		<p class="empty">No profile data yet. Your profile will appear here once the backend is connected.</p>
	{/if}
</div>

<style>
	.wrap {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		max-width: 720px;
		margin-inline: auto;
		font-family: system-ui, sans-serif;
	}

	.header h1 {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.625rem;
		font-weight: 700;
		color: #1e293b;
		margin: 0 0 0.25rem;
	}

	.muted {
		color: #64748b;
		font-size: 0.875rem;
		margin: 0;
	}

	.card {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		padding: 1.5rem;
		box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
	}

	.section-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.0625rem;
		font-weight: 700;
		color: #1e293b;
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
		background: #1e3a5f;
		color: white;
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
		color: #334155;
		min-width: 0;
	}

	.field {
		font-size: 0.8125rem;
		font-weight: 700;
		color: #64748b;
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
		background: #f1f5f9;
		color: #64748b;
	}

	.badge.ok {
		background: #dcfce7;
		color: #16a34a;
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
		border: 2px dashed #cbd5e1;
		border-radius: 8px;
		display: flex;
		align-items: center;
		justify-content: center;
		color: #94a3b8;
		font-size: 0.875rem;
		font-weight: 700;
	}

	.qr-label {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.9375rem;
		font-weight: 700;
		color: #1e293b;
	}

	.qr-note {
		text-align: center;
	}

	.admin-note {
		padding: 0.75rem 1rem;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		background: #f8fafc;
		color: #64748b;
		font-size: 0.875rem;
		text-align: center;
	}

	.meta {
		text-align: center;
		font-size: 0.8125rem;
	}

	.empty {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		padding: 2rem;
		color: #64748b;
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