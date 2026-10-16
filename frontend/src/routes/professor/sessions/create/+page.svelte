<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import {
		initProfessorCourses,
		professorState
	} from '$lib/features/professor/store.svelte';
	import type { ProfessorCourseSummary } from '$lib/shared/types';
	import { openSession, SESSION_CODE_SAMPLE } from '$lib/features/session/service';
	import { invalidateAttendanceDirectory } from '$lib/features/attendance/service';
	import { professorActiveSession } from '$lib/shared/constants/routes';

	// D11: two entry points, one page. Arriving from a My Courses card carries
	// ?offering=, which locks the course and hides the selector. Arriving from
	// the dashboard's "New Session" omits it, so the selector shows and defaults
	// to the first active assignment. Wireframe 3.2a / 3.2b.
	const lockedOfferingId = $derived.by(() => {
		const raw = page.url.searchParams.get('offering');
		if (raw === null) return null;
		const parsed = Number(raw);
		return Number.isInteger(parsed) ? parsed : null;
	});

	const isLocked = $derived(lockedOfferingId !== null);

let selectedOfferingId = $state<number | null>(null);

	onMount(() => {
		void (async () => {
			await initProfessorCourses();
			if (lockedOfferingId === null && selectedOfferingId === null) {
				selectedOfferingId = professorState.courses[0]?.offeringId ?? null;
			}
		})();
	});

	const selected = $derived.by<ProfessorCourseSummary | null>(() => {
		const wanted = lockedOfferingId ?? selectedOfferingId;
		if (wanted === null) return null;
		return professorState.courses.find((course) => course.offeringId === wanted) ?? null;
	});

	// Reseed the per-offering form fields whenever the resolved course changes,
	// so switching in the selector variant never leaves another course's numbers
	// behind.
	//
	// The assignment contract carries no schedule, classroom, or window
	// defaults, so the form seeds sane constants instead of offering prefill:
	// 90-minute duration with 15/5 present/late windows on a 50m geofence.
	// Anything left at these values is sent explicitly, and the server applies
	// the offering/app fallbacks for fields the form does not cover
	// (classroom name/coords when no override is typed).
	//
	// Geofence is mandatory for every session type (lecture and lab): the
	// professor always types classroom coordinates, which are sent as the
	// session location. The server still falls back to the offering for the
	// classroom *name* when no override name is typed (D17).
	let isLab = $state(false);
	let radius = $state(50);
	let durationMinutes = $state(90);
	let presentWindow = $state(15);
	let lateWindow = $state(5);
	let classroomOverride = $state('');
	// D17: an override moves the geofence, so it needs coordinates as well as a
	// name — the contract exposes no course coordinates to inherit, so both
	// are required when the override is active. Svelte's number binding yields
	// undefined for an empty input, which is why the validity check below uses
	// a loose null comparison.
	let classroomLat = $state<number | null>(null);
	let classroomLng = $state<number | null>(null);

	let lastSeededOfferingId = $state<number | null>(null);

	$effect(() => {
		const course = selected;
		if (course === null || course.offeringId === lastSeededOfferingId) return;

		lastSeededOfferingId = course.offeringId;
		radius = 50;
		durationMinutes = 90;
		presentWindow = 15;
		lateWindow = 5;
		classroomOverride = '';
		classroomLat = null;
		classroomLng = null;
		isLab = false;
		// A generated session belongs to the previous offering. Clear it so View
		// Live Session cannot open stale projector data after switching courses.
		generatedSessionId = null;
		generatedCode = null;
		generatedExpiry = null;
		error = null;
	});

	// D17: a blank override name means "keep the offering defaults", and nothing
	// is sent for the classroom.
	const overrideActive = $derived(classroomOverride.trim() !== '');

	// What the geofence will actually use, which is what the callout displays.
	// Without an override the server falls back to the offering classroom,
	// whose name the contract does not expose — hence the generic label.
	const effectiveRoom = $derived(
		overrideActive ? classroomOverride.trim() : 'Offering default classroom'
	);

	const effectiveLat = $derived(classroomLat);

	const effectiveLng = $derived(classroomLng);

	// Coordinates are required for every session: without them the scan
	// gate has nothing to enforce against.
	const coordsInvalid = $derived(
		classroomLat == null || classroomLng == null || Number.isNaN(classroomLat) || Number.isNaN(classroomLng)
	);

	// D13: present + late must fit inside the duration. The backend answers
	// windows_exceed_duration (422) for the same condition.
	const windowsFit = $derived(presentWindow + lateWindow <= durationMinutes);

	const durationInvalid = $derived(durationMinutes <= 0);
	const windowsInvalid = $derived(presentWindow < 0 || lateWindow < 0);

	// The server sets scheduled_end = now + duration (no class timetable feeds
	// it), so the scan window always closes exactly at now + duration. The
	// preview below is exact, not an estimate.
	const expiryPreview = $derived.by(() => {
		if (durationInvalid) return null;
		return { at: new Date(Date.now() + durationMinutes * 60 * 1000) };
	});

	const RADII = [10, 20, 30, 50, 100] as const;

	let submitting = $state(false);
	let generatedSessionId = $state<number | null>(null);
	let generatedCode = $state<string | null>(null);
	let generatedExpiry = $state<string | null>(null);
	let error = $state<string | null>(null);

	const canSubmit = $derived(
		selected !== null &&
			selected.scheduleOk &&
			windowsFit &&
			!durationInvalid &&
			!windowsInvalid &&
			!coordsInvalid &&
			!submitting
	);

	const handleGenerate = async () => {
		const course = selected;
		if (course === null || !canSubmit) return;

		submitting = true;
		error = null;

		try {
			const created = await openSession(course.offeringId, {
				sessionType: isLab ? 'lab' : 'lecture',
				durationMinutes,
				presentWindowMinutes: presentWindow,
				lateWindowMinutes: lateWindow,
				geofenceRadius: radius,
				// D17: blank means "keep the offering default", so only send the
				// override when the professor actually typed one.
				// Coordinates are always sent: every session carries a geofence,
// lecture and lab alike (canSubmit already blocks until both are
// typed, so the ?? fallbacks below are type-level only).
				classroomName: classroomOverride.trim() || undefined,
				classroomLat: classroomLat ?? undefined,
				classroomLng: classroomLng ?? undefined
			});

			generatedSessionId = created.id;
			generatedCode = created.qrPayload.code;
			generatedExpiry =
				created.expiresAt === null ? null : dateTimeText(new Date(created.expiresAt));
			invalidateAttendanceDirectory();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to open session';
		} finally {
			submitting = false;
		}
	};

	const viewLiveSession = () => {
		if (generatedSessionId === null) return;
		void goto(professorActiveSession(generatedSessionId));
	};

	const clockText = (date: Date) =>
		date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });

	const dateText = (date: Date) =>
		date.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });

	const dateTimeText = (date: Date): string => {
		const today = new Date();
		const day = date.toDateString() === today.toDateString() ? 'Today' : dateText(date);
		return `${day}, ${clockText(date)}`;
	};
</script>

<div class="create">
	<header class="header">
		<div>
			<h1>Open New Session</h1>
			<p class="muted">Configure and generate a session code for attendance</p>
		</div>
	</header>

	{#if professorState.coursesLoading}
		<section class="card">
			<p class="empty">Loading your courses…</p>
		</section>
	{:else if professorState.coursesError}
		<section class="card">
			<p class="empty">Could not load your courses: {professorState.coursesError}</p>
			<button class="btn btn-secondary" type="button" onclick={() => void initProfessorCourses()}>Try again</button>
		</section>
	{:else if selected === null}
		<section class="card">
			<p class="empty">
				{isLocked
					? 'That course assignment could not be found. Open a session from My Courses instead.'
					: 'No course assignments available to open a session for.'}
			</p>
		</section>
	{:else}
		<section class="card">
			{#if isLocked}
				<div class="field">
					<span class="form-label">Course</span>
					<div class="locked-course">
						<div class="locked-head">
							<span class="locked-name">
								{selected.courseCode} — {selected.courseName}
							</span>
							<AppIcon name="lock" size={14} />
						</div>
						<span class="locked-meta">
							{selected.programCode} · {selected.academicYear} · {selected.semester}
						</span>
						<span class="locked-meta">
							{selected.sections.length > 0 ? `Section ${selected.sections.join(', ')}` : 'No section assigned'} · {selected.enrolledCount} enrolled
						</span>
					</div>
				</div>
		{:else}
			<div class="field">
				<label class="form-label" for="offering">Select Course</label>
				<select
					id="offering"
					class="form-input"
					value={selected.offeringId}
					onchange={(e) => (selectedOfferingId = Number(e.currentTarget.value))}
				>
					{#each professorState.courses as course (course.offeringId)}
						<option value={course.offeringId}>
							{course.courseCode} — {course.courseName} ({course.programCode})
						</option>
					{/each}
				</select>
				<p class="hint">Your active assignments this term.</p>
			</div>
		{/if}

		<div class="field">
			<span class="form-label">Session Type</span>
			<div class="toggle-group" role="group" aria-label="Session type">
				<button
					class="toggle-btn"
					class:selected={!isLab}
					aria-pressed={!isLab}
					onclick={() => (isLab = false)}
				>
					<AppIcon name="file" size={16} />
					Lecture
				</button>
				<button
					class="toggle-btn"
					class:selected={isLab}
					aria-pressed={isLab}
					onclick={() => (isLab = true)}
				>
					<AppIcon name="shield" size={16} />
					Laboratory
				</button>
			</div>
			<p class="hint">
				Both types enforce the geofence: students must be within the radius to scan.
			</p>
		</div>

		<div class="lab-banner">
			<AppIcon name="alert" size={16} />
			<span>
				<strong>Geofence required:</strong> Students must be within the geofence radius to scan attendance.
				Classroom coordinates are required for every session.
			</span>
		</div>

		<div class="location" class:overridden={overrideActive}>
				<AppIcon name="pin" size={16} />
				<span>
					{effectiveRoom}
					{#if effectiveLat !== null && effectiveLng !== null}
						({effectiveLat.toFixed(4)}°N, {effectiveLng.toFixed(4)}°E)
					{/if}
				</span>
				{#if overrideActive}
					<span class="location-tag">Override</span>
				{/if}
			</div>

		<div class="field">
			<span class="form-label">
				Geofence Radius
				<span class="required-tag">Required</span>
			</span>
			<div class="radius-group" role="group" aria-label="Geofence radius">
				{#each RADII as option (option)}
					<button
						class="radius-btn"
						class:selected={radius === option}
						aria-pressed={radius === option}
						onclick={() => (radius = option)}
					>
						{option}m
					</button>
				{/each}
			</div>
			<p class="hint">Students must be within this distance from the classroom to scan.</p>
		</div>

			<div class="field">
				<label class="form-label" for="duration">Duration (minutes)</label>
				<input
					id="duration"
					class="form-input"
					class:invalid={durationInvalid}
					type="number"
					min="1"
					bind:value={durationMinutes}
				/>
				{#if expiryPreview}
					<p class="hint">
						Scan window closes {dateTimeText(expiryPreview.at)} ({durationMinutes}m from now)
					</p>
				{/if}
			</div>

			<div class="field-row">
				<div class="field">
					<label class="form-label" for="present">Present window (min)</label>
					<input
						id="present"
						class="form-input"
						class:invalid={windowsInvalid}
						type="number"
						min="0"
						bind:value={presentWindow}
					/>
				</div>
				<div class="field">
					<label class="form-label" for="late">Late window (min)</label>
					<input
						id="late"
						class="form-input"
						class:invalid={windowsInvalid}
						type="number"
						min="0"
						bind:value={lateWindow}
					/>
				</div>
			</div>

			<div class="check" class:bad={!windowsFit} role="status">
				<span class="check-math">
					Present {presentWindow} + Late {lateWindow} ≤ Duration {durationMinutes}
				</span>
				<AppIcon name={windowsFit ? 'check' : 'alert'} size={18} />
			</div>

		<div class="field">
			<label class="form-label" for="classroom">
				Classroom name (optional)
			</label>
			<input
				id="classroom"
				class="form-input"
				type="text"
				placeholder="e.g. Lab 101, Room 301"
				bind:value={classroomOverride}
			/>
			<p class="hint">
				Blank uses the offering default classroom name (D17). Coordinates below always apply.
			</p>

			<div class="override-box">
					<div class="field-row">
						<div class="field">
							<label class="form-label" for="override-lat">Latitude</label>
							<input
								id="override-lat"
								class="form-input"
								class:invalid={coordsInvalid}
								type="number"
								step="0.0001"
								placeholder="e.g. 13.7563"
								bind:value={classroomLat}
							/>
						</div>
						<div class="field">
							<label class="form-label" for="override-lng">Longitude</label>
							<input
								id="override-lng"
								class="form-input"
								class:invalid={coordsInvalid}
								type="number"
								step="0.0001"
								placeholder="e.g. 100.5018"
								bind:value={classroomLng}
							/>
						</div>
					</div>
					<p class="hint">
						The geofence centers here. Both coordinates are required for every session.
					</p>
					{#if coordsInvalid}
						<p class="field-error">
							Both coordinates are required to open a session.
						</p>
					{/if}
				</div>
		</div>

			<div class="preview" class:generated={generatedCode !== null}>
				<span class="preview-label">HMAC Preview · Session Code</span>
				{#if generatedCode}
					<span class="preview-code">{generatedCode}</span>
					<p class="preview-hint">
						Scan window closes at {generatedExpiry}. Show this on the projector for
						students to scan.
					</p>
				{:else}
					<span class="preview-code pending">{SESSION_CODE_SAMPLE}</span>
					<p class="preview-hint">Generated when you open the session.</p>
				{/if}
			</div>

			{#if error}
				<p class="error">{error}</p>
			{/if}

			{#if selected && !selected.scheduleOk}
				<div class="blocked-note" role="alert">
					<AppIcon name="alert" size={16} />
					<span><strong>Sessions can't be opened for {selected.courseCode} yet</strong> — its weekly
					schedule doesn't match the {selected.units}-unit requirement. Contact
					your administrator.</span>
				</div>
			{/if}

			<div class="actions">
				<button
					class="btn btn-primary"
					data-testid="generate-code"
					disabled={!canSubmit}
					onclick={handleGenerate}
				>
					<AppIcon name="qr" size={18} />
					{submitting ? 'Generating…' : 'Generate Session Code'}
				</button>
				<button
					class="btn btn-secondary"
					disabled={generatedSessionId === null}
					title={generatedSessionId === null ? 'Generate a session code first' : undefined}
					onclick={viewLiveSession}
				>
					<AppIcon name="shield" size={18} />
					View Live Session
				</button>
			</div>
			{#if generatedSessionId === null}
				<p class="hint">Generate a session code to unlock the live projector view.</p>
			{/if}
		</section>
	{/if}
</div>

<style>
	.create {
		display: flex;
		flex-direction: column;
		gap: 2rem;
		font-family: system-ui, sans-serif;
		/* The layout's content column is 1100px, so a fixed-width form has to
		   center itself or it hugs the left edge on wide screens. */
		max-width: 700px;
		margin: 0 auto;
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
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 2rem;
		box-shadow: var(--shadow-sm);
	}

	/* --- Fields -------------------------------------------------------------- */

	.field {
		display: flex;
		flex-direction: column;
		gap: 0.4375rem;
	}

	.field-row {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 1rem;
	}

	.form-label {
		font-size: 0.8125rem;
		font-weight: 600;
		letter-spacing: 0.02em;
		color: var(--text-secondary);
	}

	.form-input {
		padding: 0.625rem 0.75rem;
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		color: var(--text-strong);
		background: var(--bg-card);
	}

	.form-input:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
	}

	.form-input.invalid {
		border-color: var(--danger);
	}

	.hint {
		margin: 0;
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	/* A blocking reason, not a suggestion — this is what silently disables
	   Generate, so it has to be visible rather than just a red border. */
	.field-error {
		margin: 0;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--danger-strong);
	}

	/* --- Locked course panel (D11) ------------------------------------------- */

	.locked-course {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		padding: 1rem;
		background: var(--bg-page);
		border: 1px solid var(--border);
		border-radius: 8px;
	}

	.locked-head {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		color: var(--text);
	}

	.locked-head :global(svg) {
		color: var(--text-muted);
	}

	.locked-name {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1rem;
		font-weight: 700;
	}

	.locked-meta {
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	/* --- Location callout ---------------------------------------------------- */

	.location {
		display: flex;
		align-items: center;
		/* The room/coordinate string plus the Override tag can exceed a narrow
		   viewport, and overflow-x: hidden would clip it. */
		flex-wrap: wrap;
		gap: 0.5rem;
		padding: 0.75rem;
		background: var(--info-bg);
		border: 1px solid var(--info-bg);
		border-radius: 8px;
		font-size: 0.8125rem;
		color: var(--info-text);
	}

	/* Once overridden, the callout is reporting the session's geofence rather
	   than the course's, so it gets the amber treatment to say so. */
	.location.overridden {
		background: var(--warning-bg);
		border-color: #fcd34d;
		color: var(--warning-text);
	}

	.location-tag {
		margin-left: auto;		padding: 0.125rem 0.5rem;
		border-radius: 6px;
		background: var(--warning-bg);
		border: 1px solid #fcd34d;
		color: var(--warning-text);
		font-size: 0.6875rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		flex-shrink: 0;
	}

	/* --- Classroom override -------------------------------------------------- */

	.override-box {
		display: flex;
		flex-direction: column;
		gap: 0.4375rem;
		margin-top: 0.25rem;
		padding: 1rem;
		background: var(--bg-page);
		border: 1px solid var(--border);
		border-radius: 8px;
	}

	/* --- Radius toggle group ------------------------------------------------- */

	.radius-group {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.radius-btn {
		padding: 0.5rem 1rem;
		border-radius: 8px;
		border: 1px solid var(--border-strong);
		background: var(--bg-card);
		color: var(--text-strong);
		font-family: inherit;
		font-size: 0.8125rem;
		font-weight: 600;
		cursor: pointer;
		transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
	}

	.radius-btn:hover {
		background: var(--bg-hover);
	}

	.radius-btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.radius-btn.selected {
		background: var(--brand);
		border-color: var(--brand);
		color: var(--on-brand);
	}

	/* --- Session type toggle -------------------------------------------------- */

	.toggle-group {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.toggle-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.625rem 1rem;
		border-radius: 8px;
		border: 1px solid var(--border-strong);
		background: var(--bg-card);
		color: var(--text-strong);
		font-family: inherit;
		font-size: 0.875rem;
		font-weight: 600;
		cursor: pointer;
		transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
	}

	.toggle-btn:hover {
		background: var(--bg-hover);
	}

	.toggle-btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.toggle-btn.selected {
		background: var(--brand);
		border-color: var(--brand);
		color: var(--on-brand);
	}

	/* --- Lab mode banner ----------------------------------------------------- */

	.lab-banner {
		display: flex;
		align-items: flex-start;
		gap: 0.5rem;
		padding: 0.75rem 1rem;
		border-radius: 8px;
		background: var(--info-bg);
		border: 1px solid var(--info-bg);
		color: var(--info-text);
		font-size: 0.8125rem;
		line-height: 1.4;
	}

	.lab-banner :global(svg) {
		flex-shrink: 0;
		margin-top: 0.125rem;
	}

	/* --- Required field tag -------------------------------------------------- */

	.required-tag {
		display: inline-block;
		padding: 0.125rem 0.375rem;
		border-radius: 4px;
		background: var(--danger-bg);
		color: var(--danger-strong);
		font-size: 0.6875rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		margin-left: 0.5rem;
	}

	/* --- D13 window check ---------------------------------------------------- */

	.check {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 0.75rem 1rem;
		border-radius: 8px;
		background: var(--success-bg);
		border: 1px solid var(--success-bg);
		color: var(--success);
	}

	.check.bad {
		background: var(--danger-bg);
		border-color: var(--danger-bg);
		color: var(--danger-strong);
	}

	.check-math {
		font-size: 0.8125rem;
		font-weight: 600;
	}

	/* --- Code preview -------------------------------------------------------- */

	.preview {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.5rem;
		padding: 1.5rem;
		border-radius: 12px;
		background: var(--bg-page);
		border: 2px dashed var(--border-strong);
		text-align: center;
		/* Query container so .preview-code can size itself against the width it
		   actually has, rather than against the viewport. */
		container-type: inline-size;
	}

	.preview.generated {
		background: linear-gradient(135deg, var(--success-bg), var(--success-bg));
		border: 2px solid #22c55e;
		border-style: solid;
	}

	.preview-label {
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.preview.generated .preview-label {
		color: var(--success);
	}

	/* Sized from the container, not the viewport. The code is `XX-XXXX` — seven
	   monospace glyphs plus 0.15em of tracking each, so ~5.25em of width. At
	   16cqw that is 84cqw of the box, which leaves room at any screen size
	   instead of overflowing and being clipped by the root layout's
	   overflow-x: hidden. */
	.preview-code {
		font-family: 'JetBrains Mono', monospace;
		font-size: min(2.5rem, 16cqw);
		font-weight: 700;
		letter-spacing: 0.15em;
		line-height: 1;
		color: var(--brand);
		max-width: 100%;
		overflow-wrap: anywhere;
	}

	/* The placeholder is a shape preview only, so it stays visibly inert. */
	.preview-code.pending {
		color: #94a3b8;
	}

	.preview-hint {
		margin: 0.25rem 0 0;
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	/* --- Actions ------------------------------------------------------------- */

	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
	}

	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.75rem 1.25rem;
		border-radius: 8px;
		font-size: 0.9375rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
		white-space: nowrap;
		transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
	}

	.btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.btn-primary {
		flex: 1 1 auto;
		background: var(--brand);
		border: 1px solid var(--brand);
		color: var(--on-brand);
		box-shadow: 0 4px 14px rgba(30, 58, 95, 0.28);
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--brand-hover);
		border-color: var(--brand-hover);
		transform: translateY(-1px);
	}

	.btn-secondary {
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		color: var(--text-strong);
	}

	.btn:disabled {
		color: #94a3b8;
		background: var(--bg-page);
		border-color: var(--border);
		cursor: not-allowed;
		box-shadow: none;
	}

	.error {
		margin: 0;
		color: var(--danger);
		font-size: 0.875rem;
	}

	/* Blocked-sessions callout: icon + tinted box shown before submit. */
	.blocked-note {
		display: flex;
		align-items: flex-start;
		gap: 0.5rem;
		font-size: 0.875rem;
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

	.empty {
		color: var(--text-muted);
		font-size: 0.9375rem;
		margin: 0;
	}

	@media (max-width: 640px) {
		.card {
			padding: 1.25rem;
		}

		/* Reclaim horizontal room for the code itself. */
		.preview {
			padding: 1.25rem 0.75rem;
		}

		.field-row {
			grid-template-columns: minmax(0, 1fr);
		}

		.actions .btn {
			flex: 1 1 auto;
		}

		.preview-code {
			letter-spacing: 0.08em;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.radius-btn,
		.btn {
			transition: none;
		}
	}
</style>
