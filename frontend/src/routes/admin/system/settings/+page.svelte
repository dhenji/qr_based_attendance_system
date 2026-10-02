<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { Routes } from '$lib/shared/constants/routes';
	import { formatDate, formatTime } from '$lib/shared/utils/format';
	import {
		cleanupSystem,
		downloadBackupDescriptor,
		exportAnalyticsAtRisk,
		exportAnalyticsComparison,
		exportAnalyticsOverview,
		exportAnalyticsTrends,
		flushSync,
		formatBytes,
		getSettings,
		listBackups,
		patchSettings,
		triggerBackup,
		type BackupLogItem,
		type SystemSettings
	} from '$lib/features/admin/settings/service';

	// Admin system settings (wireframe 4.9). No settings backend exists yet,
	// so every block reads contract-shaped mocks and the banner says so —
	// saves stick for the session only, via the mock module state.

	let settings = $state<SystemSettings | null>(null);
	let backups = $state<BackupLogItem[]>([]);
	let loading = $state(true);
	let loadError = $state<string | null>(null);

	let geofence = $state('50');
	let presentWin = $state('5');
	let lateWin = $state('10');
	let saving = $state(false);
	let saveError = $state<string | null>(null);
	let saveNote = $state<string | null>(null);

	let backupBusy = $state(false);
	let backupError = $state<string | null>(null);
	let backupNote = $state<string | null>(null);

	let flushBusy = $state(false);
	let cleanupBusy = $state(false);
	let maintenanceNote = $state<string | null>(null);
	let maintenanceError = $state<string | null>(null);

	let exporting = $state<string | null>(null);
	let exportError = $state<string | null>(null);

	const load = async () => {
		loading = true;
		loadError = null;
		try {
			const [fetched, rows] = await Promise.all([getSettings(), listBackups()]);
			settings = fetched;
			backups = rows;
			geofence = String(fetched.geofence_default_radius);
			presentWin = String(fetched.present_window_default);
			lateWin = String(fetched.late_window_default);
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Unable to load system settings.';
		} finally {
			loading = false;
		}
	};

	onMount(() => {
		void load();
	});

	const latestBackup = $derived(backups[0] ?? null);
	const latestCompleted = $derived(backups.find((b) => b.status === 'completed') ?? null);

	const parsePositiveInt = (value: string): number | null => {
		if (!/^\d+$/.test(value.trim())) return null;
		const parsed = parseInt(value.trim(), 10);
		return parsed >= 1 ? parsed : null;
	};

	const saveDefaults = async () => {
		if (saving) return;
		saveError = null;
		saveNote = null;
		const radius = parsePositiveInt(geofence);
		const present = parsePositiveInt(presentWin);
		const late = parsePositiveInt(lateWin);
		if (radius === null || present === null || late === null) {
			saveError = 'Geofence radius and both windows must be whole numbers of at least 1.';
			return;
		}
		saving = true;
		try {
			settings = await patchSettings({
				geofence_default_radius: radius,
				present_window_default: present,
				late_window_default: late
			});
			saveNote = 'Defaults saved for this session (demo data — the settings backend is not built yet).';
		} catch (e) {
			saveError = e instanceof Error ? e.message : 'Could not save defaults.';
		} finally {
			saving = false;
		}
	};

	const backupNow = async () => {
		if (backupBusy) return;
		backupBusy = true;
		backupError = null;
		backupNote = null;
		try {
			const started = await triggerBackup();
			backups = await listBackups();
			backupNote = `Backup #${started.backup_id} started (demo — no file is produced).`;
		} catch (e) {
			backupError = e instanceof Error ? e.message : 'Could not start a backup.';
		} finally {
			backupBusy = false;
		}
	};

	const forceSync = async () => {
		if (flushBusy) return;
		flushBusy = true;
		maintenanceError = null;
		maintenanceNote = null;
		try {
			const result = await flushSync();
			settings = await getSettings();
			maintenanceNote = `Sync flushed: ${result.succeeded} succeeded, ${result.failed} failed of ${result.processed} processed.`;
		} catch (e) {
			maintenanceError = e instanceof Error ? e.message : 'Force sync failed.';
		} finally {
			flushBusy = false;
		}
	};

	const cleanUp = async () => {
		if (cleanupBusy) return;
		cleanupBusy = true;
		maintenanceError = null;
		maintenanceNote = null;
		try {
			const result = await cleanupSystem();
			maintenanceNote = `Cleaned up ${result.removed} expired records.`;
		} catch (e) {
			maintenanceError = e instanceof Error ? e.message : 'Clean up failed.';
		} finally {
			cleanupBusy = false;
		}
	};

	const exportDataset = async (name: string, run: () => Promise<void>) => {
		if (exporting) return;
		exporting = name;
		exportError = null;
		try {
			await run();
		} catch (e) {
			exportError = e instanceof Error ? e.message : `Export of ${name} failed.`;
		} finally {
			exporting = null;
		}
	};

	const backupStatusText = (row: BackupLogItem): string => {
		if (row.status === 'completed' && row.finished_at) {
			return `Healthy · Last: ${formatDate(row.finished_at)} ${formatTime(row.finished_at)}`;
		}
		if (row.status === 'started') return 'Running…';
		return 'Failed';
	};
</script>

<div class="page">
	<header class="header">
		<div>
			<h1>System Settings</h1>
			<p class="muted">Attendance defaults, backups, exports, and maintenance.</p>
		</div>
	</header>

	<p class="demo" role="status">
		Demo data — the system settings backend is not built yet. Changes apply to this session only.
	</p>

	{#if loading}
		<section class="card"><p class="muted">Loading system settings…</p></section>
	{:else if loadError}
		<section class="card">
			<p class="error">{loadError}</p>
			<button class="btn btn-secondary" type="button" onclick={() => void load()}>Try again</button>
		</section>
	{:else}
		<section class="card" aria-label="Attendance defaults">
			<h2 class="section-title">Attendance Defaults</h2>
			<div class="field-grid">
				<div class="field">
					<label class="form-label" for="set-geofence">Geofence radius (meters)</label>
					<input id="set-geofence" class="form-input" inputmode="numeric" bind:value={geofence} />
				</div>
				<div class="field">
					<label class="form-label" for="set-present">Default present window (min)</label>
					<input id="set-present" class="form-input" inputmode="numeric" bind:value={presentWin} />
				</div>
				<div class="field">
					<label class="form-label" for="set-late">Default late window (min)</label>
					<input id="set-late" class="form-input" inputmode="numeric" bind:value={lateWin} />
				</div>
			</div>
			{#if saveError}
				<p class="error" role="alert">{saveError}</p>
			{/if}
			{#if saveNote}
				<p class="note" role="status">{saveNote}</p>
			{/if}
			<button class="btn btn-primary" type="button" disabled={saving} onclick={() => void saveDefaults()}>
				{saving ? 'Saving…' : 'Save Changes'}
			</button>
		</section>

		<section class="card" aria-label="Academic structure updates">
			<h2 class="section-title">Academic Structure Updates</h2>
			<p class="muted">
				Add or rename year levels, adjust term structures, and move courses between
				programs. All changes are audited.
			</p>
			<div class="actions">
				<button class="btn btn-secondary" type="button" onclick={() => goto(Routes.ADMIN_PROGRAMS)}>
					Edit Programs →
				</button>
				<button class="btn btn-secondary" type="button" onclick={() => goto(Routes.ADMIN_AUDIT_LOGS)}>
					View Audit Logs
				</button>
			</div>
		</section>

		<section class="card" aria-label="Backup">
			<h2 class="section-title">Backup</h2>
			<p class="muted">Full database backup · AES-256-GCM · Retention: {settings?.backup_retention_daily ?? 30}D daily + {settings?.backup_retention_monthly ?? 12} monthly</p>
			{#if latestBackup}
				<p class="backup-status" role="status">
					Status: {latestBackup.status === 'completed' ? '✅' : latestBackup.status === 'started' ? '⏳' : '❌'}
					{backupStatusText(latestBackup)} · {formatBytes(latestBackup.size_bytes)} · {latestBackup.storage_backend}
				</p>
			{:else}
				<p class="muted">No backups recorded yet.</p>
			{/if}
			{#if backupError}
				<p class="error" role="alert">{backupError}</p>
			{/if}
			{#if backupNote}
				<p class="note" role="status">{backupNote}</p>
			{/if}
			<div class="actions">
				<button class="btn btn-secondary" type="button" disabled={backupBusy} onclick={() => void backupNow()}>
					{backupBusy ? 'Starting…' : '💾 Backup Now'}
				</button>
				<button
					class="btn btn-secondary"
					type="button"
					disabled={!latestCompleted}
					title={latestCompleted ? 'Download a JSON descriptor of this backup (demo)' : 'No completed backup yet'}
					onclick={() => latestCompleted && downloadBackupDescriptor(latestCompleted)}
				>
					📥 Download
				</button>
				<button class="btn btn-secondary" type="button" disabled title="Key management needs the backup backend">
					🔒 Key Mgmt
				</button>
			</div>
		</section>

		<section class="card" aria-label="Analytics export">
			<h2 class="section-title">Analytics Export</h2>
			<p class="muted">Aggregated CSV downloads of the reporting data — separate from backups.</p>
			{#if exportError}
				<p class="error" role="alert">{exportError}</p>
			{/if}
			<div class="actions">
				<button class="btn btn-secondary" type="button" disabled={exporting !== null} onclick={() => void exportDataset('overview', exportAnalyticsOverview)}>
					{exporting === 'overview' ? 'Exporting…' : 'Overview CSV'}
				</button>
				<button class="btn btn-secondary" type="button" disabled={exporting !== null} onclick={() => void exportDataset('comparison', exportAnalyticsComparison)}>
					{exporting === 'comparison' ? 'Exporting…' : 'Comparison CSV'}
				</button>
				<button class="btn btn-secondary" type="button" disabled={exporting !== null} onclick={() => void exportDataset('trends', exportAnalyticsTrends)}>
					{exporting === 'trends' ? 'Exporting…' : 'Trends CSV'}
				</button>
				<button class="btn btn-secondary" type="button" disabled={exporting !== null} onclick={() => void exportDataset('at-risk', exportAnalyticsAtRisk)}>
					{exporting === 'at-risk' ? 'Exporting…' : 'At-risk CSV'}
				</button>
				<button class="btn btn-secondary" type="button" disabled title="PDF export needs backend file generation">
					Export PDF
				</button>
			</div>
		</section>

		<section class="card" aria-label="Maintenance">
			<h2 class="section-title">Maintenance</h2>
			<p class="muted" role="status">Pending sync: {settings?.pending_sync_count ?? 0}</p>
			{#if maintenanceError}
				<p class="error" role="alert">{maintenanceError}</p>
			{/if}
			{#if maintenanceNote}
				<p class="note" role="status">{maintenanceNote}</p>
			{/if}
			<div class="actions">
				<button class="btn btn-secondary" type="button" disabled={flushBusy} onclick={() => void forceSync()}>
					{flushBusy ? 'Syncing…' : 'Force Sync'}
				</button>
				<button class="btn btn-secondary" type="button" disabled={cleanupBusy} onclick={() => void cleanUp()}>
					{cleanupBusy ? 'Cleaning…' : 'Clean Up'}
				</button>
			</div>
		</section>
	{/if}
</div>

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		font-family: system-ui, sans-serif;
		width: 100%;
		min-width: 0;
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

	.demo {
		background: #fffbeb;
		border: 1px solid #fde68a;
		border-radius: 8px;
		padding: 0.75rem 1rem;
		color: #92400e;
		font-size: 0.875rem;
		margin: 0;
	}

	.card {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
		padding: 1.25rem;
		min-width: 0;
	}

	.section-title {
		font-size: 1.125rem;
		font-weight: 700;
		color: #1e293b;
		margin: 0 0 0.75rem;
	}

	.field-grid {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 0.75rem;
		margin-bottom: 1rem;
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		min-width: 0;
	}

	.form-label {
		font-size: 0.8125rem;
		font-weight: 600;
		color: #475569;
	}

	.form-input {
		padding: 0.625rem 0.875rem;
		border: 1.5px solid #d1d5db;
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		color: #0f172a;
		outline: none;
		background: white;
		width: 100%;
	}

	.form-input:focus {
		border-color: #2563eb;
	}

	.actions {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
		margin-top: 1rem;
	}

	.btn {
		border-radius: 8px;
		padding: 0.625rem 1.25rem;
		font-size: 0.9375rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
		border: 1px solid transparent;
	}

	.btn-primary {
		background: #1e3a5f;
		color: white;
	}

	.btn-primary:disabled {
		opacity: 0.6;
		cursor: wait;
	}

	.btn-secondary {
		background: white;
		border-color: #cbd5e1;
		color: #1e3a5f;
	}

	.btn-secondary:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.error {
		color: #b91c1c;
		font-size: 0.875rem;
		margin: 0.75rem 0 0;
	}

	.note {
		color: #15803d;
		font-size: 0.875rem;
		margin: 0.75rem 0 0;
	}

	.backup-status {
		color: #1e293b;
		font-size: 0.9375rem;
		margin: 0.75rem 0 0;
	}

	@media (max-width: 640px) {
		.field-grid {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
