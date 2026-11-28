<script lang="ts">
	import { onMount } from 'svelte';
	import ClassroomMapPicker from '$lib/components/ClassroomMapPicker.svelte';
	import RadiusSelector from '$lib/components/RadiusSelector.svelte';
	import { adminOfferingDetailState, updateAdminOffering } from '$lib/features/admin/offerings/store.svelte';
	import { offeringSettingsSchema, windowsWithinDuration } from '$lib/features/admin/offerings/schema';
	import { parseOptCoord } from '$lib/features/admin/offerings/formHelpers';
	import type { AdminCourse, AdminOffering } from '$lib/shared/types';

	// Offering settings card (detail page, Settings tab): mutable rates,
	// classroom, and geofence only — identity fields are not patchable.
	// Blank rate/radius fields mean "follow the system default" (D93).

	interface Props {
		offering: AdminOffering;
		course: AdminCourse | null;
		systemDefaults: { present: number; late: number; radius: number } | null;
		sessionCount: number;
		expectedTotal: number | null;
	}

	let { offering, course, systemDefaults, sessionCount, expectedTotal }: Props = $props();

	let s_present = $state('');
	let s_late = $state('');
	let s_radius = $state('');
	let s_room = $state('');
	let s_lat = $state('');
	let s_lng = $state('');
	let settingsError = $state<string | null>(null);
	let settingsFieldErrors = $state<Record<string, string>>({});
	let settingsBusy = $state(false);
	let settingsOpen = $state(false);

	// A blank field means "follow the system default" (D93), so a NULL on the
	// offering reads as an empty input rather than the text "null". Read the
	// store after a save because that is where updateAdminOffering lands the
	// fresh row.
	const fillSettings = () => {
		const o = adminOfferingDetailState.offering ?? offering;
		settingsError = null;
		settingsFieldErrors = {};
		s_present = o.presentWindowMinutes === null ? '' : String(o.presentWindowMinutes);
		s_late = o.lateWindowMinutes === null ? '' : String(o.lateWindowMinutes);
		s_radius =
			o.defaultClassroomRadiusMeters === null || o.defaultClassroomRadiusMeters === undefined
				? ''
				: String(o.defaultClassroomRadiusMeters);
		s_room = o.classroomName ?? '';
		s_lat = o.classroomLat === undefined || o.classroomLat === null ? '' : String(o.classroomLat);
		s_lng = o.classroomLng === undefined || o.classroomLng === null ? '' : String(o.classroomLng);
	};

	onMount(fillSettings);

	const submitSettings = async () => {
		settingsError = null;
		settingsFieldErrors = {};
		settingsBusy = true;
		try {
			const parsedSettings = offeringSettingsSchema.safeParse({
				present: s_present,
				late: s_late,
				radius: s_radius,
				room: s_room,
				lat: s_lat,
				lng: s_lng,
			});
			if (!parsedSettings.success) {
				const fe: Record<string, string> = {};
				for (const issue of parsedSettings.error.issues) {
					const key = String(issue.path[0] ?? '');
					if (key && !fe[key]) fe[key] = issue.message;
				}
				settingsFieldErrors = fe;
				settingsError =
					Object.keys(fe).length > 0
						? 'Some information needs your attention. Review the highlighted fields and correct the indicated errors.'
						: (parsedSettings.error.issues[0]?.message ?? 'Check the settings and try again.');
				return;
			}
			// A blank field means "follow the system default" (D93): the
			// offering stores NULL and the session resolves the value from
			// Admin -> System Settings.
			const present = s_present.trim() === '' ? null : Number(s_present);
			const late = s_late.trim() === '' ? null : Number(s_late);
			if (
				(present !== null && (!Number.isInteger(present) || present < 1 || present > 480)) ||
				(late !== null && (!Number.isInteger(late) || late < 1 || late > 480))
			) {
				settingsError = 'Windows must be whole minutes between 1 and 480';
				return;
			}
			if (
				course &&
				present !== null &&
				late !== null &&
				!windowsWithinDuration(present, late, course.sessionDurationHours)
			) {
				settingsError = `Present + late windows exceed the ${course.courseCode} session duration (${course.sessionDurationHours * 60} min)`;
				return;
			}
			const radius = s_radius.trim() === '' ? null : Number(s_radius);
			if (radius !== null && (!Number.isInteger(radius) || radius < 1 || radius > 1000)) {
				settingsError = 'The geofence radius must be a whole number of metres between 1 and 1000';
				return;
			}
			let lat: number | null = null;
			let lng: number | null = null;
			if (s_lat.trim() !== '' || s_lng.trim() !== '') {
				try {
					lat = parseOptCoord(s_lat, 'Latitude', -90, 90) ?? null;
					lng = parseOptCoord(s_lng, 'Longitude', -180, 180) ?? null;
				} catch (e: unknown) {
					settingsError = e instanceof Error ? e.message : 'Invalid coordinates';
					return;
				}
				if (lat === null || lng === null) {
					settingsError = 'Both latitude and longitude are required to pin a classroom';
					return;
				}
			}
			await updateAdminOffering(offering.id, {
				classroom_name: s_room.trim() ? s_room.trim() : null,
				classroom_lat: lat,
				classroom_lng: lng,
				default_present_window_minutes: present,
				default_late_window_minutes: late,
				default_classroom_radius_meters: radius,
			});
			fillSettings();
			settingsOpen = false;
		} catch (e: unknown) {
			settingsError = e instanceof Error && e.message ? e.message : 'Save failed. Please try again.';
			settingsOpen = true;
		} finally {
			settingsBusy = false;
		}
	};
</script>

<section class="card">
	<div class="card-head">
		<h2 class="card-title">Offering settings</h2>
		{#if !settingsOpen}
			<button class="btn btn-primary btn-small" style="margin-bottom: 0.5rem;" onclick={() => (settingsOpen = true)}>Edit offering settings</button>
		{/if}
	</div>
	<p class="muted">Rates and windows only. Course, program, year, semester, and academic year are identity — they cannot be changed after creation.</p>
	{#if settingsError}
		<p class="error" role="alert">{settingsError}</p>
	{/if}
	{#if !settingsOpen}
		<dl class="settings-summary">
			<div><dt>Present window</dt><dd>{offering.presentWindowMinutes ?? systemDefaults?.present ?? '—'} min{offering.presentWindowMinutes === null ? ' (system default)' : ''}</dd></div>
			<div><dt>Late window</dt><dd>{offering.lateWindowMinutes ?? systemDefaults?.late ?? '—'} min{offering.lateWindowMinutes === null ? ' (system default)' : ''}</dd></div>
			<div><dt>Geofence radius</dt><dd>{offering.defaultClassroomRadiusMeters ?? systemDefaults?.radius ?? '—'} m{offering.defaultClassroomRadiusMeters === null ? ' (system default)' : ''}</dd></div>
		</dl>
	{/if}
	{#if settingsOpen}
		<div class="form">
			<div class="grid2">
				<label>Sessions / week (automatic)<input class="input" value={sessionCount} disabled aria-label="Sessions per week, counted automatically from the meetings" /></label>
				<label>Semester weeks (from term)<input class="input" value={offering.semesterWeeks} disabled aria-label="Session weeks, set on the term in Manage Terms" /></label>
			</div>
			<p class="hint">Sessions per week are counted from the class meetings above — one per meeting day — and update automatically when meetings change.</p>
			{#if expectedTotal !== null}
				<p class="hint">{sessionCount} sessions/week × {offering.semesterWeeks} weeks = {expectedTotal} expected sessions this term. Edit the term's weeks in Program Management → Year Levels → Manage Terms.</p>
			{/if}
			<div class="grid2">
				<label>
					Present window, min
					<input
						class="input"
						class:invalid={!!settingsFieldErrors.present}
						inputmode="numeric"
						placeholder={systemDefaults ? `System default (${systemDefaults.present})` : 'System default'}
						bind:value={s_present}
						aria-invalid={!!settingsFieldErrors.present}
						aria-describedby="offering-present-help"
						oninput={() => { if (settingsFieldErrors.present) settingsFieldErrors = { ...settingsFieldErrors, present: '' }; }}
					/>
					{#if settingsFieldErrors.present}
						<p class="field-error" role="alert">{settingsFieldErrors.present}</p>
					{:else}
						<p class="hint" id="offering-present-help">1–480 minutes. Blank follows the system default.</p>
					{/if}
				</label>
				<label>
					Late window, min
					<input
						class="input"
						class:invalid={!!settingsFieldErrors.late}
						inputmode="numeric"
						placeholder={systemDefaults ? `System default (${systemDefaults.late})` : 'System default'}
						bind:value={s_late}
						aria-invalid={!!settingsFieldErrors.late}
						aria-describedby="offering-late-help"
						oninput={() => { if (settingsFieldErrors.late) settingsFieldErrors = { ...settingsFieldErrors, late: '' }; }}
					/>
					{#if settingsFieldErrors.late}
						<p class="field-error" role="alert">{settingsFieldErrors.late}</p>
					{:else}
						<p class="hint" id="offering-late-help">1–480 minutes. Blank follows the system default.</p>
					{/if}
				</label>
			</div>
			<p class="hint">
				Present + late windows must fit the course session duration. Leave a field
				blank to follow the system default.
			</p>
			<label>
				Default classroom (optional)
				<input
					class="input"
					class:invalid={!!settingsFieldErrors.room}
					bind:value={s_room}
					placeholder="Room 301"
					maxlength="100"
					aria-invalid={!!settingsFieldErrors.room}
					aria-describedby="offering-room-help"
					oninput={() => { if (settingsFieldErrors.room) settingsFieldErrors = { ...settingsFieldErrors, room: '' }; }}
				/>
				{#if settingsFieldErrors.room}
					<p class="field-error" role="alert">{settingsFieldErrors.room}</p>
				{:else}
					<p class="hint" id="offering-room-help">Optional. Used when a meeting has no classroom of its own.</p>
				{/if}
			</label>
			<p class="hint">Used when a class meeting has no classroom of its own. Meetings can override this per row.</p>
			<div class="grid2">
				<label>
					Default latitude (optional)
					<input
						class="input"
						class:invalid={!!settingsFieldErrors.lat}
						inputmode="decimal"
						bind:value={s_lat}
						placeholder="14.5995"
						aria-invalid={!!settingsFieldErrors.lat}
						aria-describedby="offering-lat-help"
						oninput={() => { if (settingsFieldErrors.lat) settingsFieldErrors = { ...settingsFieldErrors, lat: '' }; }}
					/>
					{#if settingsFieldErrors.lat}
						<p class="field-error" role="alert">{settingsFieldErrors.lat}</p>
					{:else}
						<p class="hint" id="offering-lat-help">-90 to 90. Optional.</p>
					{/if}
				</label>
				<label>
					Default longitude (optional)
					<input
						class="input"
						class:invalid={!!settingsFieldErrors.lng}
						inputmode="decimal"
						bind:value={s_lng}
						placeholder="120.9842"
						aria-invalid={!!settingsFieldErrors.lng}
						aria-describedby="offering-lng-help"
						oninput={() => { if (settingsFieldErrors.lng) settingsFieldErrors = { ...settingsFieldErrors, lng: '' }; }}
					/>
					{#if settingsFieldErrors.lng}
						<p class="field-error" role="alert">{settingsFieldErrors.lng}</p>
					{:else}
						<p class="hint" id="offering-lng-help">-180 to 180. Optional.</p>
					{/if}
				</label>
			</div>
			<p class="hint">Both latitude and longitude are required to pin a classroom.</p>
			<ClassroomMapPicker
				lat={s_lat.trim() === '' ? null : Number(s_lat)}
				lng={s_lng.trim() === '' ? null : Number(s_lng)}
				onChange={(la, lo) => { s_lat = String(la); s_lng = String(lo); }}
				onClear={() => { s_lat = ''; s_lng = ''; }}
			/>
			<div class="field">
				<RadiusSelector
					value={Number(s_radius) || systemDefaults?.radius || 50}
					min={1}
					max={1000}
					defaultValue={systemDefaults?.radius}
					inheriting={s_radius.trim() === ''}
					defaultChipLabel={systemDefaults ? `Default (${systemDefaults.radius} m)` : 'Default'}
					onDefault={() => (s_radius = '')}
					onChange={(v) => (s_radius = String(v))}
				/>
				{#if settingsFieldErrors.radius}
					<p class="field-error" role="alert">{settingsFieldErrors.radius}</p>
				{:else}
					<p class="hint">
						Blank inherits the value set in System Settings. A value here applies to this
						offering's sessions only.
					</p>
				{/if}
			</div>
		</div>
		<div class="modal-actions">
			<button class="btn btn-ghost" onclick={fillSettings}>Reset</button>
			<button class="btn btn-primary" aria-busy={settingsBusy} disabled={settingsBusy} onclick={submitSettings}>
				{settingsBusy ? 'Saving…' : 'Save'}
			</button>
		</div>
	{/if}
</section>

<style>
	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 1.5rem;
		box-shadow: var(--shadow-sm);
	}

	.card-title {
		margin: 0 0 0.375rem;
		font-size: 1.125rem;
		font-weight: 700;
		color: var(--text);
	}

	.card-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
	}

	.card .muted {
		margin-bottom: 1rem;
	}

	.muted {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0;
	}

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0 0 1rem;
	}

	.hint {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin: 1rem 0 0;
	}

	.input {
		padding: 0.625rem 0.875rem;
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		color: var(--text-strong);
		background: var(--bg-card);
	}

	.input:focus {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
	}

	.input:disabled {
		background: var(--divider);
		color: var(--text-muted);
		cursor: not-allowed;
	}

	.input.invalid {
		border-color: var(--danger);
	}

	.field-error {
		color: var(--danger);
		font-size: 0.75rem;
		margin: 0;
	}

	.form {
		display: flex;
		flex-direction: column;
		gap: 0.875rem;
	}

	.form label {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.grid2 {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.875rem;
	}

	.modal-actions {
		display: flex;
		gap: 0.75rem;
		justify-content: flex-end;
		margin-top: 1.5rem;
	}

	.settings-summary {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
		gap: 0.5rem 1rem;
		padding: 0.5rem 0;
		margin: 0;
	}
	.settings-summary div {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}
	.settings-summary dt {
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--text-muted, #666);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}
	.settings-summary dd {
		margin: 0;
		font-size: 0.9375rem;
		font-weight: 600;
		color: var(--text-strong, #111);
	}

	@media (max-width: 640px) {
		.card {
			padding: 1.25rem;
		}

		.grid2 {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
