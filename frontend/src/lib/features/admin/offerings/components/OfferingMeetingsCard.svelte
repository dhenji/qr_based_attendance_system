<script lang="ts">
	import AppIcon from '$lib/components/AppIcon.svelte';
	import ClassroomMapPicker from '$lib/components/ClassroomMapPicker.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import DayPicker from '$lib/features/admin/offerings/components/DayPicker.svelte';
	import { refreshAdminOfferingDetail } from '$lib/features/admin/offerings/store.svelte';
	import { archiveComponent, createComponent, updateComponent } from '$lib/features/admin/offerings/service';
	import { componentCreateSchema } from '$lib/features/admin/offerings/schema';
	import { parseOptCoord } from '$lib/features/admin/offerings/formHelpers';
	import {
		weeklyHoursBreakdown,
		weeklyWriteBlocked,
		type ScheduleMeetingLike,
		type WeeklyHoursBreakdown,
	} from '$lib/shared/utils/schedule';
	import { APIError } from '$lib/api/client';
	import { WEEKLY_HOURS_CODES, friendlyActionError } from '$lib/shared/utils/deleteErrors';
	import { describeError } from '$lib/shared/utils/errors';
	import { notifyEntityChanged } from '$lib/shared/utils/entityEvents';
	import { trapFocus } from '$lib/shared/actions/focusTrap';
	import type { AdminCourse, AdminOffering, OfferingComponent } from '$lib/shared/types';

	// Class meetings card (detail page, Settings tab): the active component
	// rows, their weekly-hours projection against the course units, and the
	// add/edit/remove flows. The offering row already carries its active
	// components, so every write refreshes the detail and renders from there.

	interface Props {
		offering: AdminOffering;
		course: AdminCourse | null;
		breakdown: WeeklyHoursBreakdown | null;
		rows: ScheduleMeetingLike[];
	}

	let { offering, course, breakdown, rows }: Props = $props();

	let compError = $state<string | null>(null);
	let compBusy = $state(false);
	let removeCompTarget = $state<OfferingComponent | null>(null);
	let addMeetingOpen = $state(false);
	let c_type = $state<'lecture' | 'lab'>('lab');
	let c_days = $state('');
	let c_start = $state('');
	let c_end = $state('');
	let c_room = $state('');
	let c_lat = $state('');
	let c_lng = $state('');
	let editingComp = $state<OfferingComponent | null>(null);
	let editConfirmOpen = $state(false);
	let e_days = $state('');
	// Legacy rows may carry free-text days outside the MTWHFSU alphabet that
	// the picker cannot represent; those edits keep a plain input so saving
	// can never silently drop characters. Decided when the edit opens.
	let e_customDays = $state(false);
	let e_start = $state('');
	let e_end = $state('');
	let e_room = $state('');
	let e_lat = $state('');
	let e_lng = $state('');

	const addProjection = $derived(
		weeklyHoursBreakdown(
			[
				...rows,
				{ schedule_days: c_days, schedule_start_time: c_start, schedule_end_time: c_end },
			],
			course?.units ?? null
		)
	);

	const editProjection = $derived.by(() => {
		const target = editingComp;
		if (!target) return null;
		return weeklyHoursBreakdown(
			[
				...offering.components
					.filter((c) => c.id !== target.id)
					.map((c) => ({
						schedule_days: c.scheduleDays,
						schedule_start_time: c.scheduleStartTime,
						schedule_end_time: c.scheduleEndTime,
					})),
				{ schedule_days: e_days, schedule_start_time: e_start, schedule_end_time: e_end },
			],
			course?.units ?? null
		);
	});

	// Grandfathered or mid-build totals off the requirement may only converge:
	// strictly closer without crossing sides (same rule as the backend
	// `_check_weekly_hours`). `course.units` is null until the lookup
	// resolves, so every projection below is gated on it.
	const addBlocked = $derived(
		course && addProjection
			? weeklyWriteBlocked(breakdown?.scheduled ?? null, addProjection.scheduled, course.units)
			: false
	);

	// Curated meeting-write errors: weekly 422s render the backend message
	// verbatim (it carries the tailored scheduled/limit/over/short numbers);
	// every other API failure maps through the friendly copy so raw row ids
	// never render.
	const compFailure = (e: unknown, fallback: string): string => {
		if (e instanceof APIError && e.code && WEEKLY_HOURS_CODES.has(e.code)) {
			return describeError(e, fallback);
		}
		return friendlyActionError(e, fallback);
	};

	const resetCompForm = () => {
		c_type = 'lab';
		c_days = '';
		c_start = '';
		c_end = '';
		c_room = '';
		c_lat = '';
		c_lng = '';
	};

	const submitAddComponent = async () => {
		compError = null;
		compBusy = true;
		try {
			const parsed = componentCreateSchema.safeParse({
				session_type: c_type,
				schedule_days: c_days,
				schedule_start_time: c_start,
				schedule_end_time: c_end,
				classroom_name: c_room || undefined,
			});
			if (!parsed.success) {
				compError = parsed.error.issues[0]?.message ?? 'Check the component and try again.';
				return;
			}
			// Duplicate pre-check on the backend unique key (session_type,
			// schedule_days, schedule_start_time), naming the table row it
			// clashes with — same idiom as the create surfaces.
			const clashIndex = offering.components.findIndex(
				(c) =>
					c.sessionType === parsed.data.session_type &&
					c.scheduleDays === parsed.data.schedule_days &&
					c.scheduleStartTime.slice(0, 5) === parsed.data.schedule_start_time.slice(0, 5)
			);
			if (clashIndex >= 0) {
				const hit = offering.components[clashIndex];
				const hitLabel = hit.sessionType === 'lab' ? 'Laboratory' : 'Lecture';
				compError = `Duplicates meeting ${clashIndex + 1} (${hitLabel} ${hit.scheduleDays} ${hit.scheduleStartTime.slice(0, 5)}). Change the type, days, or time.`;
				return;
			}
			// Weekly-hours requirement (backend 422 weekly_hours_exceed_units /
			// weekly_hours_below_units): the course's units are the required
			// scheduled meeting hours per week, counting all existing meetings
			// plus this draft. Off-requirement totals may only converge.
			if (course && addBlocked) {
				compError =
					addProjection && addProjection.status === 'under'
						? `Weekly scheduled hours (${addProjection.scheduled}h) fall short of the ${course.units}-unit requirement (${addProjection.limit}h) for ${course.courseCode} — lengthen a meeting instead.`
						: `Weekly scheduled hours (${addProjection?.scheduled}h) exceed the ${course.units}-unit requirement (${addProjection?.limit}h) for ${course.courseCode} — shorten a meeting first.`;
				return;
			}
			if (c_type === 'lab' && (!c_lat.trim() || !c_lng.trim())) {
				compError = 'Laboratory meetings require both latitude and longitude.';
				return;
			}
			await createComponent(offering.id, {
				session_type: parsed.data.session_type,
				schedule_days: parsed.data.schedule_days,
				schedule_start_time: parsed.data.schedule_start_time,
				schedule_end_time: parsed.data.schedule_end_time,
				classroom_name: parsed.data.classroom_name || undefined,
				classroom_lat: parseOptCoord(c_lat, 'Latitude', -90, 90),
				classroom_lng: parseOptCoord(c_lng, 'Longitude', -180, 180),
			});
			resetCompForm();
			await refreshAdminOfferingDetail(offering.id);
			notifyEntityChanged('offerings');
		} catch (e: unknown) {
			// The inline weekly-hours status already reports these, so setting
			// compError too would duplicate the same failure message.
			if (!(e instanceof APIError && e.code && WEEKLY_HOURS_CODES.has(e.code))) {
				compError = compFailure(e, 'Save failed. Please try again.');
			}
		} finally {
			compBusy = false;
		}
	};

	const openEditComponent = (c: OfferingComponent) => {
		editingComp = c;
		editConfirmOpen = false;
		compError = null;
		e_days = c.scheduleDays;
		e_customDays = !/^[MTWHFSU]+$/.test(c.scheduleDays);
		e_start = c.scheduleStartTime.slice(0, 5);
		e_end = c.scheduleEndTime.slice(0, 5);
		e_room = c.classroomName ?? '';
		e_lat = c.classroomLat !== undefined ? String(c.classroomLat) : '';
		e_lng = c.classroomLng !== undefined ? String(c.classroomLng) : '';
	};

	const submitEditComponent = async () => {
		if (!editingComp) return;
		compError = null;
		const parsed = componentCreateSchema.safeParse({
			session_type: editingComp.sessionType,
			schedule_days: e_days,
			schedule_start_time: e_start,
			schedule_end_time: e_end,
			classroom_name: e_room || undefined,
		});
		if (!parsed.success) {
			compError = parsed.error.issues[0]?.message ?? 'Check the component and try again.';
			return;
		}
		// Confirm gate: a save that leaves the total mismatched without
		// converging (the pre-D81 blocker) needs a deliberate click.
		// Converging fixes and exact landings save straight through.
		if (
			course &&
			editProjection &&
			weeklyWriteBlocked(breakdown?.scheduled ?? null, editProjection.scheduled, course.units)
		) {
			editConfirmOpen = true;
			return;
		}
		await persistEditComponent();
	};

	const persistEditComponent = async () => {
		if (!editingComp) return;
		editConfirmOpen = false;
		compBusy = true;
		compError = null;
		try {
			if (editingComp.sessionType === 'lab' && (!e_lat.trim() || !e_lng.trim())) {
				compError = 'Laboratory meetings require both latitude and longitude.';
				return;
			}
			const parsed = componentCreateSchema.safeParse({
				session_type: editingComp.sessionType,
				schedule_days: e_days,
				schedule_start_time: e_start,
				schedule_end_time: e_end,
				classroom_name: e_room || undefined,
			});
			if (!parsed.success) {
				compError = parsed.error.issues[0]?.message ?? 'Check the component and try again.';
				return;
			}
			await updateComponent(offering.id, editingComp.id, {
				schedule_days: parsed.data.schedule_days,
				schedule_start_time: parsed.data.schedule_start_time,
				schedule_end_time: parsed.data.schedule_end_time,
				classroom_name: e_room.trim() ? e_room.trim() : null,
				classroom_lat: e_lat.trim() ? parseOptCoord(e_lat, 'Latitude', -90, 90) : null,
				classroom_lng: e_lng.trim() ? parseOptCoord(e_lng, 'Longitude', -180, 180) : null,
			});
			editingComp = null;
			await refreshAdminOfferingDetail(offering.id);
			notifyEntityChanged('offerings');
		} catch (e: unknown) {
			compError = compFailure(e, 'Save failed. Please try again.');
		} finally {
			compBusy = false;
		}
	};

	const removeMeetingRow = async (c: OfferingComponent): Promise<boolean> => {
		if (compBusy) return false;
		compError = null;
		compBusy = true;
		try {
			await archiveComponent(offering.id, c.id);
			if (editingComp?.id === c.id) editingComp = null;
			editConfirmOpen = false;
			await refreshAdminOfferingDetail(offering.id);
			notifyEntityChanged('offerings');
			return true;
		} catch (e: unknown) {
			compError = compFailure(e, 'Remove failed. Please try again.');
			return false;
		} finally {
			compBusy = false;
		}
	};

	const askRemoveMeeting = (c: OfferingComponent) => {
		if (compBusy) return;
		compError = null;
		removeCompTarget = c;
	};

	const confirmRemoveMeeting = async () => {
		if (!removeCompTarget) return;
		if (await removeMeetingRow(removeCompTarget)) removeCompTarget = null;
	};
</script>

<section class="card">
	<h2 class="card-title">Class meetings</h2>
	<p class="muted">Each row is one weekly meeting with its own days, time, and room. A course with a Monday laboratory and a Wednesday lecture is two rows — sessions inherit the room of their meeting type.</p>
	{#if breakdown && course}
		{#if breakdown.status === 'ok'}
			<p class="hint">{breakdown.scheduled}h scheduled of {breakdown.limit}h weekly requirement ({course.courseCode} · exact).</p>
		{:else if breakdown.status === 'over'}
			<p class="error" role="alert">{breakdown.scheduled}h scheduled of {breakdown.limit}h weekly requirement ({course.courseCode} · {-breakdown.remaining}h over).</p>
		{:else}
			<p class="error" role="alert">{breakdown.scheduled}h scheduled of {breakdown.limit}h weekly requirement ({course.courseCode} · {breakdown.remaining}h short).</p>
		{/if}
		{#if breakdown.status !== 'ok'}
			<div class="blocked-note" role="note">
				<AppIcon name="alert" size={16} />
				<span><strong>Sessions cannot be opened for this offering</strong> until the total matches — new sessions are refused and reactivation is disabled.</span>
			</div>
		{/if}
	{/if}
	{#if offering.components.length === 0}
		<EmptyState
			icon="chart"
			title="No active components"
			hint="Add one below so sessions have a schedule to inherit."
		/>
	{:else}
		<div class="table-wrap">
			<table>
				<thead>
					<tr>
						<th scope="col">Type</th>
						<th scope="col">Days</th>
						<th scope="col">Time</th>
						<th scope="col">Room</th>
						<th scope="col"><span class="sr">Actions</span></th>
					</tr>
				</thead>
				<tbody>
					{#each offering.components as comp (comp.id)}
						<tr>
							<td>
								<span class="badge type-lab" class:type-lec={comp.sessionType === 'lecture'}>
									{comp.sessionType === 'lab' ? 'Laboratory' : 'Lecture'}
								</span>
							</td>
							<td>{comp.scheduleDays}</td>
							<td>{comp.scheduleStartTime.slice(0, 5)}–{comp.scheduleEndTime.slice(0, 5)}</td>
							<td>{comp.classroomName ?? '—'}</td>
							<td>
								<div class="row-actions">
									<button class="link" onclick={() => openEditComponent(comp)}>Edit</button>
									<button class="link" disabled={compBusy} onclick={() => askRemoveMeeting(comp)}>Remove</button>
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
	{#if editingComp}
		<div class="comp-edit">
			<h3 class="sub-title">Edit {editingComp.sessionType === 'lab' ? 'laboratory' : 'lecture'} meeting</h3>
			{#if e_customDays}
				<label>Days<input class="input" bind:value={e_days} placeholder="MWF" /></label>
			{:else}
				<DayPicker bind:value={e_days} />
			{/if}
			<div class="grid2">
				<label>Start time<input class="input" type="time" bind:value={e_start} /></label>
				<label>End time<input class="input" type="time" bind:value={e_end} /></label>
			</div>
			<label>Room (optional)<input class="input" bind:value={e_room} placeholder="Lab 101" /></label>
			<div class="grid2">
				<label>Latitude {editingComp?.sessionType === 'lab' ? '(required)' : '(optional)'}<input class="input" inputmode="decimal" bind:value={e_lat} /></label>
				<label>Longitude {editingComp?.sessionType === 'lab' ? '(required)' : '(optional)'}<input class="input" inputmode="decimal" bind:value={e_lng} /></label>
			</div>
			<ClassroomMapPicker
				lat={e_lat.trim() === '' ? null : Number(e_lat)}
				lng={e_lng.trim() === '' ? null : Number(e_lng)}
				onChange={(la, lo) => { e_lat = String(la); e_lng = String(lo); }}
				onClear={() => { e_lat = ''; e_lng = ''; }}
				height="320px"
			/>
			{#if course && editProjection}
				<p class="hint">Saving would bring the weekly total to {editProjection.scheduled}h of {editProjection.limit}h ({editProjection.status === 'ok' ? 'exact' : editProjection.status === 'under' ? `${editProjection.remaining}h short` : `${-editProjection.remaining}h over`}). Reshapes save freely — the panel above tracks the total back to exact.</p>
			{/if}
			{#if compError}
				<p class="error" role="alert">{compError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => { editingComp = null; editConfirmOpen = false; }}>Cancel</button>
				<button class="btn btn-primary" aria-busy={compBusy} disabled={compBusy} onclick={submitEditComponent}>
					{compBusy ? 'Saving…' : 'Save'}
				</button>
			</div>
		</div>
	{:else}
		<div class="comp-add-trigger">
			<button class="btn btn-primary" onclick={() => { if (!addMeetingOpen) resetCompForm(); addMeetingOpen = !addMeetingOpen; }}>
				{addMeetingOpen ? 'Hide form' : 'Add meeting'}
			</button>
		</div>
		{#if addMeetingOpen}
			<div class="comp-add">
				<h3 class="sub-title">Add a meeting</h3>
				<p class="hint">One row, one time: days on the same row share the time below. For a different time, add another row.</p>
				{#if compError}
					<p class="error" role="alert">{compError}</p>
				{/if}
				<DayPicker bind:value={c_days} />
				<label>Type
					<select class="input" bind:value={c_type}>
						<option value="lecture">Lecture</option>
						<option value="lab">Laboratory</option>
					</select>
				</label>
				<div class="grid2">
					<label>Start time<input class="input" type="time" bind:value={c_start} /></label>
					<label>End time<input class="input" type="time" bind:value={c_end} /></label>
				</div>
				<label>Room (optional)<input class="input" bind:value={c_room} placeholder="Lab 101" /></label>
				<div class="grid2">
					<label>Latitude {c_type === 'lab' ? '(required)' : '(optional)'}<input class="input" inputmode="decimal" bind:value={c_lat} placeholder="14.5995" /></label>
					<label>Longitude {c_type === 'lab' ? '(required)' : '(optional)'}<input class="input" inputmode="decimal" bind:value={c_lng} placeholder="120.9842" /></label>
				</div>
				<ClassroomMapPicker
					lat={c_lat.trim() === '' ? null : Number(c_lat)}
					lng={c_lng.trim() === '' ? null : Number(c_lng)}
					onChange={(la, lo) => { c_lat = String(la); c_lng = String(lo); }}
					onClear={() => { c_lat = ''; c_lng = ''; }}
					height="320px"
				/>
				<p class="hint">Laboratory meetings should carry coordinates: lab sessions enforce the geofence. Leave the coordinates blank to inherit the offering default.</p>
				{#if course && addProjection && c_days.trim() && c_start && c_end}
					{#if addBlocked}
						<p class="error" role="alert">Adding this meeting would bring the weekly total to {addProjection.scheduled}h of {addProjection.limit}h ({addProjection.status === 'under' ? `${addProjection.remaining}h short` : `${-addProjection.remaining}h over`}).</p>
					{:else}
						<p class="hint">Adding this meeting would bring the weekly total to {addProjection.scheduled}h of {addProjection.limit}h ({addProjection.status === 'ok' ? 'exact' : addProjection.status === 'under' ? `${addProjection.remaining}h short` : `${-addProjection.remaining}h over`}).</p>
					{/if}
				{/if}
				<div class="modal-actions">
					<button class="btn btn-ghost" onclick={() => (addMeetingOpen = false)}>Cancel</button>
					<button class="btn btn-primary" aria-busy={compBusy} disabled={compBusy} onclick={async () => { await submitAddComponent(); if (!compError) addMeetingOpen = false; }}>
						{compBusy ? 'Adding…' : 'Add meeting'}
					</button>
				</div>
			</div>
		{/if}
	{/if}
</section>

{#if editConfirmOpen && course && editProjection}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="edit-confirm-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (editConfirmOpen = false) }}
		>
			<h2 id="edit-confirm-title" class="modal-title">Save a mismatched total?</h2>
			<p class="modal-text">
				Saving would leave the weekly total at {editProjection.scheduled}h against the
				{course.units}-unit requirement ({editProjection.status === 'under' ? `${editProjection.remaining}h short` : `${-editProjection.remaining}h over`}).
				The red panels will track it until the schedule converges back to exact.
			</p>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (editConfirmOpen = false)}>Cancel</button>
				<button class="btn btn-primary" aria-busy={compBusy} disabled={compBusy} onclick={() => void persistEditComponent()}>
					{compBusy ? 'Saving…' : 'Save anyway'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if removeCompTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="component-remove-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (removeCompTarget = null) }}
		>
			<h2 id="component-remove-title" class="modal-title">Remove this meeting?</h2>
			<p class="modal-text">
				It will be taken off this offering's active schedule. Attendance history
				for past sessions is kept.
			</p>
			{#if compError}
				<p class="error" role="alert">{compError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (removeCompTarget = null)}>Cancel</button>
				<button class="btn btn-danger" disabled={compBusy} onclick={confirmRemoveMeeting}>
					{compBusy ? 'Removing…' : 'Remove'}
				</button>
			</div>
		</div>
	</div>
{/if}

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

	.card .muted {
		margin-bottom: 1rem;
	}

	.muted {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0;
	}

	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.875rem;
	}

	th,
	td {
		text-align: left;
		padding: 0.625rem 0.5rem;
		border-bottom: 1px solid var(--divider);
		vertical-align: middle;
	}

	th {
		color: var(--text-muted);
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.badge {
		display: inline-block;
		padding: 0.125rem 0.5rem;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--success);
		background: var(--success-bg);
	}

	.badge.type-lec {
		color: var(--success);
		background: var(--success-bg);
	}

	.badge.type-lab {
		color: var(--warning-text);
		background: var(--warning-bg);
	}

	/* Blocked-sessions callout: icon + tinted box, unmissable next to the
	totals it explains. */
	.blocked-note {
		display: flex;
		align-items: flex-start;
		gap: 0.5rem;
		font-size: 0.8125rem;
		color: var(--danger);
		background: var(--danger-bg);
		border: 1px solid var(--danger-bg);
		border-radius: 8px;
		padding: 0.625rem 0.875rem;
		margin: 0;
	}

	.blocked-note :global(svg) {
		flex-shrink: 0;
		margin-top: 0.125rem;
	}

	.sub-title {
		margin: 1rem 0 0.5rem;
		font-size: 1rem;
		font-weight: 700;
		color: var(--text);
	}

	.comp-add-trigger {
		margin-top: 1.25rem;
		padding-top: 1rem;
		border-top: 1px solid var(--divider);
		display: flex;
		justify-content: flex-end;
	}

	.comp-add {
		display: flex;
		flex-direction: column;
		gap: 0.875rem;
		margin-top: 1rem;
		padding: 1.25rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--bg-page);
	}

	.comp-edit {
		display: flex;
		flex-direction: column;
		gap: 0.875rem;
		margin-top: 1.25rem;
		padding-top: 1.25rem;
		border-top: 1px solid var(--divider);
	}

	/* Inside the meeting forms the flex `gap` owns the vertical rhythm —
		section-level margins would otherwise stack on top of it (e.g. a
		2.4rem pile-up between the heading and its hint). */
	.comp-edit > .hint,
	.comp-edit > .sub-title {
		margin: 0;
	}

	.comp-edit label,
	.comp-add label {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.row-actions {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.link {
		background: none;
		border: none;
		padding: 0;
		color: var(--accent);
		font-size: 0.8125rem;
		font-weight: 600;
		cursor: pointer;
	}

	.link:hover {
		text-decoration: underline;
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

	.grid2 {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.875rem;
	}

	.table-wrap {
		overflow-x: auto;
	}

	.modal-overlay {
		position: fixed;
		inset: 0;
		z-index: 100;
		background: var(--overlay);
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
	}

	.modal {
		width: 100%;
		max-width: 520px;
		max-height: 90vh;
		overflow-y: auto;
		background: var(--bg-card);
		border-radius: 12px;
		box-shadow: var(--shadow-lg);
		padding: 1.75rem 1.5rem;
	}

	.modal-title {
		margin: 0 0 1rem;
		font-size: 1.25rem;
		font-weight: 700;
		color: var(--text);
	}

	.modal-text {
		margin: 0 0 1.5rem;
		font-size: 0.9375rem;
		color: var(--text-secondary);
	}

	.modal-actions {
		display: flex;
		gap: 0.75rem;
		justify-content: flex-end;
		margin-top: 1.5rem;
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
