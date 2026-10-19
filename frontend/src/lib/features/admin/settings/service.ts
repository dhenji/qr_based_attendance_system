// features/admin/settings/service.ts
// Admin system settings (wireframe 4.9, api-contracts.md §System Settings &
// Backups).
//
// All of this is live: `features/system` is mounted at api/router.py and serves
// GET/PATCH /admin/system/settings, GET/POST /admin/backups,
// GET /admin/backups/{id}/download, POST /admin/system/sync/flush and
// POST /admin/system/cleanup. Settings live in the `app_settings` table, so a
// successful PATCH persists — the page used to claim the values were
// session-only demo data, which was false. Real API by default; the endpoint
// defs' mocks are only consulted when PUBLIC_MOCK_MODE=true.
//
// Analytics export reuses the live-or-mock analytics getters and CSV
// builders from the sibling analytics service. Backup download is the one
// genuine gap: see downloadBackupDescriptor below.

import { backupDownloadPath, get, getBlob, isMockMode, patch, post } from '$lib/api/client';
import type {
	BackupLogItemResponse,
	SystemSettingsResponse
} from '$lib/api/endpoints';
import {
	atRiskCsv,
	comparisonCsv,
	downloadCsv,
	getAnalyticsComparison,
	getAnalyticsOverview,
	getAnalyticsTrends,
	getAtRisk,
	overviewCsv,
	trendsCsv
} from '$lib/features/admin/analytics/service';

export type SystemSettings = SystemSettingsResponse;
export type BackupLogItem = BackupLogItemResponse;

export type SettingsPatch = Partial<
	Pick<
		SystemSettings,
		| 'geofence_default_radius'
		| 'present_window_default'
		| 'late_window_default'
		| 'backup_retention_daily'
		| 'backup_retention_monthly'
	>
>;

export const getSettings = async (): Promise<SystemSettings> =>
	get<SystemSettings>('systemSettings');

export const patchSettings = async (patchBody: SettingsPatch): Promise<SystemSettings> => {
	const response = await patch<SystemSettings>('systemSettingsPatch', patchBody);
	return response;
};

export const listBackups = async (): Promise<BackupLogItem[]> => {
	const response = await get<{ items: BackupLogItem[] }>('systemBackups');
	return response.items ?? [];
};

export const triggerBackup = async (): Promise<{ backup_id: number; status: 'started' }> =>
	post<{ backup_id: number; status: 'started' }>('systemBackupTrigger');

export const flushSync = async (): Promise<{ processed: number; succeeded: number; failed: number }> =>
	post<{ processed: number; succeeded: number; failed: number }>('systemSyncFlush');

export const cleanupSystem = async (): Promise<{ removed: number }> =>
	post<{ removed: number }>('systemCleanup');

// downloadBackupDescriptor
// Mock-mode stand-in: describes the row as JSON because getBlob throws in
// mock mode (no backend to fetch from). The file is clearly labelled
// mock-only so it is never mistaken for a real encrypted archive. Live mode
// never calls this directly — downloadBackupArchive below fetches the
// encrypted archive first.
export const downloadBackupDescriptor = (row: BackupLogItem): void => {
	const blob = new Blob(
		[
			JSON.stringify(
				{
					mock: true,
					note: 'Mock-mode descriptor only — the backup archive itself is unavailable without a backend.',
					backup: row
				},
				null,
				2
			)
		],
		{ type: 'application/json;charset=utf-8' }
	);
	const url = URL.createObjectURL(blob);
	const link = document.createElement('a');
	link.href = url;
	link.download = `backup-${row.id}-mock-descriptor.json`;
	document.body.appendChild(link);
	link.click();
	link.remove();
	setTimeout(() => URL.revokeObjectURL(url), 60_000);
};

// downloadBackupArchive
// backupDownloadPath(id) (application/octet-stream + filename).
// Saves the real encrypted archive under the server filename. In mock mode
// (no backend) it falls back to the JSON descriptor so the button still does
// something; live failures throw so the page surfaces them instead of
// writing a misleading descriptor.
export const downloadBackupArchive = async (row: BackupLogItem): Promise<void> => {
	try {
		const { blob, filename } = await getBlob(backupDownloadPath(row.id));
		const url = URL.createObjectURL(blob);
		const link = document.createElement('a');
		link.href = url;
		link.download = filename || row.filename;
		document.body.appendChild(link);
		link.click();
		link.remove();
		setTimeout(() => URL.revokeObjectURL(url), 60_000);
	} catch (e) {
		if (isMockMode()) {
			downloadBackupDescriptor(row);
			return;
		}
		throw e;
	}
};

// --- Analytics export (settings Export block) ---------------------------------

const stamp = (): string => new Date().toISOString().slice(0, 10);

export const exportAnalyticsOverview = async (): Promise<void> => {
	const overview = await getAnalyticsOverview();
	downloadCsv(`analytics-overview-${stamp()}.csv`, overviewCsv(overview));
};

export const exportAnalyticsComparison = async (): Promise<void> => {
	const { items } = await getAnalyticsComparison();
	downloadCsv(`analytics-comparison-${stamp()}.csv`, comparisonCsv(items));
};

export const exportAnalyticsTrends = async (): Promise<void> => {
	const items = await getAnalyticsTrends();
	downloadCsv(`analytics-trends-${stamp()}.csv`, trendsCsv(items));
};

export const exportAnalyticsAtRisk = async (): Promise<void> => {
	const items = await getAtRisk();
	downloadCsv(`analytics-atrisk-${stamp()}.csv`, atRiskCsv(items));
};

// `formatBytes` now lives in `$lib/shared/utils/format` — the audit reader
// needs it for a backup row's `size_bytes` snapshot too, and a shared
// formatter is the one home for it. Re-exported here so the settings page
// keeps a single import site for the slice's helpers.
export { formatBytes } from '$lib/shared/utils/format';
