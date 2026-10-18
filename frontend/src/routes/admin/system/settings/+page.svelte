<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { Routes } from '$lib/shared/constants/routes';
	import { formatDate, formatTime } from '$lib/shared/utils/format';
	import {
		cleanupSystem,
		downloadBackupArchive,
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

	// Admin system settings (wireframe 4.9). Live backend: settings persist to
	// app_settings, backups download as encrypted archives.

	let settings = $state<SystemSettings | null>(null);
	let backups = $state<BackupLogItem[]>([]);
	let loading = $state(true);
	let loadError = $state<string | null>(null);

	let geofence = $state('50');
	let presentWin = $state('5');
	let lateWin = $state('10');
	let retentionDaily = $state('30');
	let retentionMonthly = $state('12');
	let saving = $state(false);
	let saveError = $state<string | null>(null);
	let saveNote = $state<string | null>(null);

	let backupBusy = $state(false);
	let backupError = $state<string | null>(null);
	let backupNote = $state<string | null>(null);
	let downloadBusy = $state(false);

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
			retentionDaily = String(fetched.backup_retention_daily ?? 30);
			retentionMonthly = String(fetched.backup_retention_monthly ?? 12);
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
		const daily = parsePositiveInt(retentionDaily);
		const monthly = parsePositiveInt(retentionMonthly);
		if (radius === null || present === null || late === null || daily === null || monthly === null) {
			saveError = 'Geofence, windows, and retention must all be whole numbers of at least 1.';
			return;
		}
		saving = true;
		try {
			settings = await patchSettings({
				geofence_default_radius: radius,
				present_window_default: present,
				late_window_default: late,
				backup_retention_daily: daily,
				backup_retention_monthly: monthly
			});
			// These persist: `app_settings` is a real table and this route commits
			// through the request dependency, so a success message must not imply
			// the values were session-only. It used to say exactly that, which
			// told admins a save had not stuck when it had.
			saveNote = 'Defaults saved. They take effect immediately and persist on the server.';
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
			backupNote = `Backup #${started.backup_id} started. It appears below once it completes.`;
		} catch (e) {
			backupError = e instanceof Error ? e.message : 'Could not start a backup.';
		} finally {
			backupBusy = false;
		}
	};

	const downloadBackup = async (row: BackupLogItem) => {
		if (downloadBusy) return;
		downloadBusy = true;
		backupError = null;
		try {
			await downloadBackupArchive(row);
		} catch (e) {
			backupError = e instanceof Error ? e.message : 'Could not download this backup.';
		} finally {
			downloadBusy = false;
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
				<div class="field">
					<label class="form-label" for="set-retention-daily">Backup retention daily (days)</label>
					<input id="set-retention-daily" class="form-input" inputmode="numeric" bind:value={retentionDaily} />
				</div>
				<div class="field">
					<label class="form-label" for="set-retention-monthly">Backup retention monthly (months)</label>
					<input id="set-retention-monthly" class="form-input" inputmode="numeric" bind:value={retentionMonthly} />
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
					Status: {backupStatusText(latestBackup)}
					· {formatBytes(latestBackup.size_bytes)} · {latestBackup.storage_backend}
				</p>
			{:else}
				<p class="muted">No backups recorded yet.</p>
			{/if}
			{#if backups.length > 0}
				<ul class="backup-list">
					{#each backups.slice(0, 5) as row (row.id)}
						<li class="backup-row">
							<span class="mono">#{row.id} · {row.status} · {formatDate(row.started_at)}</span>
							<button
								class="btn btn-secondary btn-small"
								type="button"
								disabled={downloadBusy || row.status !== 'completed'}
								title={row.status === 'completed' ? 'Download the encrypted backup archive' : 'Only completed backups can be downloaded'}
								onclick={() => void downloadBackup(row)}
							>
								{downloadBusy ? 'Preparing…' : 'Download'}
							</button>
						</li>
					{/each}
				</ul>
			{/if}
			{#if backupError}
				<p class="error" role="alert">{backupError}</p>
			{/if}
			{#if backupNote}
				<p class="note" role="status">{backupNote}</p>
			{/if}
			<div class="actions">
				<button class="btn btn-secondary" type="button" disabled={backupBusy} onclick={() => void backupNow()}>
					{backupBusy ? 'Starting…' : 'Backup Now'}
				</button>
				<button
					class="btn btn-secondary"
					type="button"
					disabled={!latestCompleted || downloadBusy}
					title={latestCompleted ? 'Download the encrypted backup archive' : 'No completed backup yet'}
					onclick={() => latestCompleted && void downloadBackup(latestCompleted)}
				>
					{downloadBusy ? 'Preparing…' : 'Download'}
				</button>
			</div>
			<p class="muted">Backup archives are encrypted with the server key — there is no key-management UI; key rotation happens deployment-side.</p>
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
				<button
					class="btn btn-secondary"
					type="button"
					title="Print the current page as PDF"
					onclick={() => window.print()}
				>
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
		width: 100%;
		min-width: 0;
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
		box-shadow: var(--shadow-sm);
		padding: 1.25rem;
		min-width: 0;
	}

	.section-title {
		font-size: 1.125rem;
		font-weight: 700;
		color: var(--text);
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
		color: var(--text-secondary);
	}

	.form-input {
		padding: 0.625rem 0.875rem;
		border: 1.5px solid var(--border-strong);
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		color: var(--text-strong);
		outline: none;
		background: var(--bg-input);
		width: 100%;
	}

	.form-input:focus {
		border-color: var(--accent);
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
		background: var(--brand);
		color: var(--on-brand);
	}

	.btn-primary:disabled {
		opacity: 0.6;
		cursor: wait;
	}

	.btn-secondary {
		background: var(--bg-card);
		border-color: var(--border-strong);
		color: var(--brand);
	}

	.btn-secondary:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0.75rem 0 0;
	}

	.note {
		color: var(--success);
		font-size: 0.875rem;
		margin: 0.75rem 0 0;
	}

	.backup-status {
		color: var(--text);
		font-size: 0.9375rem;
		margin: 0.75rem 0 0;
	}

	.backup-list {
		list-style: none;
		margin: 0.75rem 0 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.backup-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		flex-wrap: wrap;
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--divider);
		border-radius: 8px;
		background: var(--bg-page);
		font-size: 0.875rem;
	}

	.mono {
		font-family: ui-monospace, monospace;
	}

	.btn-small {
		padding: 0.375rem 0.75rem;
		font-size: 0.8125rem;
	}

	@media (max-width: 640px) {
		.field-grid {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
