// features/admin/settings/service.ts
// Admin system settings (wireframe 4.9, api-contracts.md §System Settings &
// Backups).
//
// No backend exists yet (features/system is model-only and unmounted), so the
// calls below go through endpoint defs whose mocks return deterministic,
// contract-shaped data. Real API by default; mocks only when
// PUBLIC_MOCK_MODE=true. PATCH/flush/cleanup mutate the mock module state,
// so saves visibly stick for the session — the page labels the whole surface
// as demo data until the backend lands.
//
// Analytics export reuses the live-or-mock analytics getters and CSV
// builders from the sibling analytics service; backup download is a JSON
// descriptor (a mock cannot produce a pg_dump binary).

import { get, patch, post } from '$lib/api/client';
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
// Stand-in for GET /admin/backups/{id}/download: a mock cannot emit a
// pg_dump binary, so the descriptor names the row a real download would
// serve. Labelled as demo on the page.
export const downloadBackupDescriptor = (row: BackupLogItem): void => {
	const blob = new Blob(
		[
			JSON.stringify(
				{
					demo: true,
					note: 'Descriptor only — the backup backend is not built yet.',
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
	link.download = `backup-${row.id}-descriptor.json`;
	document.body.appendChild(link);
	link.click();
	link.remove();
	URL.revokeObjectURL(url);
};

// --- Analytics export (settings Export block) ---------------------------------

const stamp = (): string => new Date().toISOString().slice(0, 10);

export const exportAnalyticsOverview = async (): Promise<void> => {
	const overview = await getAnalyticsOverview();
	downloadCsv(`analytics-overview-${stamp()}.csv`, overviewCsv(overview));
};

export const exportAnalyticsComparison = async (): Promise<void> => {
	const items = await getAnalyticsComparison();
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

export const formatBytes = (bytes: number): string => {
	if (bytes <= 0) return '—';
	const units = ['B', 'KB', 'MB', 'GB'];
	let value = bytes;
	let unit = 0;
	while (value >= 1024 && unit < units.length - 1) {
		value /= 1024;
		unit += 1;
	}
	return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
};
