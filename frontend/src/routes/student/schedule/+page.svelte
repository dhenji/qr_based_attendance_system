<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte';
	import SkeletonTable from '$lib/components/SkeletonTable.svelte';
	import { onMount } from 'svelte';
	import { getSchedule } from '$lib/features/student/service';
	import type { ScheduledClass } from '$lib/shared/types';
	import { dayLabels, formatWallClock } from '$lib/shared/utils/schedule';

	// My Schedule — live on GET /student/schedule (no params; identity from
	// the Bearer token). One row per active enrollment ordered by offering_id;
	// empty enrollments return { offerings: [] }, which keeps the original
	// empty-state copy below.

	const today = $derived(
		new Date().toLocaleDateString(undefined, {
			weekday: 'long',
			year: 'numeric',
			month: 'long',
			day: 'numeric',
		})
	);

	let classes = $state<ScheduledClass[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Weekday letters -> JS getDay() index (M=Mon … U=Sun). Mirrors the
	// backend's day_weekdays() so "today" lines up with the server.
	const DAY_LETTER_TO_JS: Record<string, number> = {
		M: 1, T: 2, W: 3, H: 4, F: 5, S: 6, U: 0
	};
	const DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

	const grouped = $derived.by(() => {
		const out: { day: number; name: string; isToday: boolean; items: ScheduledClass[] }[] = [];
		for (let d = 0; d < 7; d++) {
			const items = classes
				.filter((c) => [...new Set(c.scheduleDays.toUpperCase())].some((l) => DAY_LETTER_TO_JS[l] === d))
				.slice()
				.sort((a, b) => a.scheduleStartTime.localeCompare(b.scheduleStartTime));
			out.push({ day: d, name: DAY_NAMES[d], isToday: d === new Date().getDay(), items });
		}
		return out;
	});

	const todayJs = $derived(new Date().getDay());

	const nextClass = $derived.by(() => {
		const now = new Date();
		const todayMinutes = now.getHours() * 60 + now.getMinutes();
		const todayItems = grouped[todayJs].items
			.filter((c) => {
				const [h, m] = c.scheduleStartTime.split(':').map(Number);
				return h * 60 + m > todayMinutes;
			})
			.sort((a, b) => a.scheduleStartTime.localeCompare(b.scheduleStartTime));
		if (todayItems.length) return { item: todayItems[0], dayName: 'today' };
		for (let i = 1; i <= 7; i++) {
			const d = (todayJs + i) % 7;
			if (grouped[d].items.length) return { item: grouped[d].items[0], dayName: DAY_NAMES[d] };
		}
		return null;
	});

	const countdown = $derived.by(() => {
		if (!nextClass || nextClass.dayName !== 'today') return '';
		const now = new Date();
		const [h, m] = nextClass.item.scheduleStartTime.split(':').map(Number);
		const target = new Date(now);
		target.setHours(h, m, 0, 0);
		const diff = Math.round((target.getTime() - now.getTime()) / 60000);
		if (diff <= 0) return 'now';
		const hrs = Math.floor(diff / 60);
		const mins = diff % 60;
		if (hrs > 0) return `in ${hrs}h ${mins}m`;
		return `in ${mins}m`;
	});

	// Per-subject color palette. Stable by sorted course-code index so a course
	// keeps its color across reloads and across the week.
	const PALETTE = [
		'#2563eb', '#7c3aed', '#db2777', '#ea580c', '#16a34a',
		'#0891b2', '#ca8a04', '#9333ea', '#0d9488', '#e11d48'
	];
	const subjectColors = $derived.by(() => {
		const codes = [...new Set(classes.map((c) => c.courseCode))].sort();
		const map: Record<string, string> = {};
		codes.forEach((code, i) => {
			map[code] = PALETTE[i % PALETTE.length];
		});
		return map;
	});
	const colorFor = (code: string): string => subjectColors[code] ?? PALETTE[0];

	const SLOT_START = 8 * 60;
	const SLOT_END = 18 * 60;
	const SLOT_STEP = 30;

	const toMinutes = (t: string): number => {
		const [h, m] = t.split(':').map(Number);
		return (h || 0) * 60 + (m || 0);
	};

	const timeSlots = $derived.by(() => {
		const out: string[] = [];
		for (let m = SLOT_START; m < SLOT_END; m += SLOT_STEP) {
			const h = String(Math.floor(m / 60)).padStart(2, '0');
			const mm = String(m % 60).padStart(2, '0');
			out.push(`${h}:${mm}:00`);
		}
		return out;
	});

	// Anchor a class to the nearest 30-min slot at/before its start so a class
	// that begins at 08:15 still renders instead of vanishing.
	const slotOf = (mins: number): number =>
		Math.max(SLOT_START, Math.min(SLOT_END - SLOT_STEP, Math.floor(mins / SLOT_STEP) * SLOT_STEP));

	// Row index (0-based, inside the 8:00–18:00 body) of the slot a class starts
	// on. The banner is placed with `grid-row: index + 2 / span N`, so it lines
	// up with the row grid exactly — rows, gaps and all — instead of being
	// positioned with hand-computed pixel offsets.
	const startRowIndex = (cls: ScheduledClass): number => {
		const anchor = slotOf(toMinutes(cls.scheduleStartTime));
		return Math.max(0, Math.round((anchor - SLOT_START) / SLOT_STEP));
	};

	const rowSpanFor = (cls: ScheduledClass): number => {
		const dur = toMinutes(cls.scheduleEndTime) - toMinutes(cls.scheduleStartTime);
		const slots = Math.max(1, Math.ceil(dur / SLOT_STEP));
		const anchor = slotOf(toMinutes(cls.scheduleStartTime));
		const remaining = Math.max(1, (SLOT_END - anchor) / SLOT_STEP);
		return Math.min(slots, remaining);
	};

	const load = async () => {
		loading = true;
		error = null;
		try {
			classes = await getSchedule();
		} catch (e: unknown) {
			error = e instanceof Error && e.message ? e.message : 'Could not load schedule.';
		} finally {
			loading = false;
		}
	};

	onMount(() => {
		void load();
	});
</script>

<div class="wrap page-enter">
	<header class="header">
		<div>
			<h1>My Schedule</h1>
			<p class="muted">{today} · {classes.length} enrolled</p>
		</div>
	</header>

	{#if loading}
		<SkeletonTable rows={4} cols={3} label="Loading schedule…" />
	{:else if error}
		<p class="empty error">Could not load schedule: {error} <button class="retry-btn" onclick={() => void load()}>Try again</button></p>
	{:else if classes.length === 0}
		<EmptyState
			icon="file"
			title="No classes scheduled yet"
			hint="Your enrolled subjects will appear here."
		/>
	{:else}
		{#if nextClass}
			<div class="next-card">
				<div class="next-label">Next class{countdown ? ` · ${countdown}` : ''}</div>
				<div class="next-title">{nextClass.item.courseCode} <span class="muted">· {nextClass.item.courseName}</span></div>
				<div class="meta">
					<span>{dayLabels(nextClass.item.scheduleDays).join(', ') || 'Days not set'} · {formatWallClock(nextClass.item.scheduleStartTime)} – {formatWallClock(nextClass.item.scheduleEndTime)}</span>
					<span>{nextClass.item.classroomName ?? 'Room TBA'}</span>
					<span>{nextClass.item.professorName ?? 'Professor TBA'}</span>
				</div>
				<div class="sub muted">{nextClass.item.programCode} · {nextClass.item.yearLevelLabel} · {nextClass.item.semester}</div>
			</div>
		{/if}
		<!-- Weekly grid (desktop) — absolute-positioned banners for reliable spanning -->
		<div class="week-grid-wrap">
			<div class="week-grid">
				<div class="gh-time"></div>
				{#each DAY_NAMES as name, i (i)}
					<div class="gh-day" class:is-today={i === todayJs}>{name.slice(0, 3)}</div>
				{/each}
				{#each timeSlots as time, ri (time)}
					<div class="gt-time" style="grid-row: {ri + 2};">{formatWallClock(time)}</div>
					{#each DAY_NAMES as _name, day (day)}
						<div class="gc-empty" style="grid-row: {ri + 2}; grid-column: {day + 2};"></div>
					{/each}
				{/each}
				{#each classes as c (c.offeringId)}
					{#each DAY_NAMES as _name, day (day)}
						{@const letters = new Set(c.scheduleDays.toUpperCase())}
						{#if [...letters].some((l) => DAY_LETTER_TO_JS[l] === day)}
							{@const ri = startRowIndex(c)}
							{@const span = rowSpanFor(c)}
							<div class="gc-cell" style="grid-row: {ri + 2} / span {span}; grid-column: {day + 2}; background: {colorFor(c.courseCode)};">
								<strong>{c.courseCode}</strong>
								<span>{formatWallClock(c.scheduleStartTime)} – {formatWallClock(c.scheduleEndTime)}</span>
								<span>{c.classroomName ?? 'Room TBA'}</span>
							</div>
						{/if}
					{/each}
				{/each}
			</div>
		</div>



		<!-- Grouped list (mobile fallback) -->
		<div class="grouped-list">
			{#each grouped as g (g.day)}
				{#if g.items.length}
					<section class="day-group" class:is-today={g.isToday}>
						<h2 class="day-heading">{g.name}{g.isToday ? ' · Today' : ''}</h2>
						<ul class="list">
							{#each g.items as c (c.offeringId)}
								<li class="card">
									<div class="row">
										<strong>{c.courseCode}</strong>
										<span class="muted"> · {c.courseName}</span>
									</div>
									<div class="meta">
										<span>{formatWallClock(c.scheduleStartTime)} – {formatWallClock(c.scheduleEndTime)}</span>
										<span>{c.classroomName ?? 'Room TBA'}</span>
										<span>{c.professorName ?? 'Professor TBA'}</span>
									</div>
									<div class="sub muted">{c.programCode} · {c.yearLevelLabel} · {c.semester}</div>
								</li>
							{/each}
						</ul>
					</section>
				{/if}
			{/each}
		</div>
	{/if}
</div>

<style>
	.wrap {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		max-width: 1100px;
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

	.empty {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 2rem;
		color: var(--text-muted);
		font-size: 0.9375rem;
		margin: 0;
	}

	.empty.error {
		color: var(--danger);
	}

	.retry-btn {
		margin-left: 0.75rem;
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		padding: 0.375rem 0.875rem;
		font-size: 0.875rem;
		font-weight: 600;
		font-family: inherit;
		color: var(--brand);
		cursor: pointer;
	}

	.list {
		list-style: none;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		margin: 0;
		padding: 0;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 1rem 1.25rem;
		box-shadow: var(--shadow-sm);
	}

	.row {
		font-size: 1rem;
		margin-bottom: 0.25rem;
	}

	.meta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.375rem 1rem;
		font-size: 0.875rem;
		color: var(--text-secondary);
	}

	.sub {
		margin-top: 0.25rem;
		font-size: 0.75rem;
	}

	.next-card {
		background: var(--bg-card);
		border: 1px solid var(--accent);
		border-radius: 8px;
		padding: 1rem 1.25rem;
		box-shadow: var(--shadow-sm);
		margin-bottom: 1rem;
	}

	.next-label {
		font-size: 0.75rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--accent);
		margin-bottom: 0.25rem;
	}

	.next-title {
		font-size: 1rem;
		margin-bottom: 0.5rem;
	}

	.day-group {
		margin-bottom: 1rem;
	}

	.day-heading {
		font-size: 0.875rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--text-muted);
		margin: 0 0 0.5rem;
	}

	.day-group.is-today .day-heading {
		color: var(--accent);
	}

	/* Weekly grid (desktop) */
	.week-grid-wrap {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		box-shadow: var(--shadow-sm);
		overflow: hidden;
		padding: 0.5rem;
	}

	.week-grid {
		display: grid;
		grid-template-columns: 4.5rem repeat(7, minmax(0, 1fr));
		grid-auto-rows: 2.75rem;
		gap: 2px;
		position: relative;
		background: var(--bg-card);
	}

	.gh-time {
		background: var(--bg-muted);
	}

	.gh-day {
		background: var(--bg-muted);
		text-align: center;
		font-weight: 700;
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--text-muted);
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 4px;
	}

	.gh-day.is-today {
		color: var(--accent);
	}

	.gt-time {
		background: var(--bg-muted);
		font-weight: 600;
		font-size: 0.75rem;
		color: var(--text-muted);
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 4px;
	}

	.gc-cell {
		position: relative;
		z-index: 1;
		border-radius: 6px;
		padding: 0.375rem 0.25rem;
		color: #fff;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		text-align: center;
		gap: 0.125rem;
		overflow: hidden;
		box-sizing: border-box;
	}

	.gc-cell strong {
		font-size: 0.8125rem;
		font-weight: 700;
	}

	.gc-cell span {
		font-size: 0.6875rem;
		opacity: 0.9;
	}

	.gc-empty {
		background: var(--bg-card);
		border-radius: 4px;
	}

	/* Responsive: grid on desktop, grouped list on mobile */
	.grouped-list {
		display: none;
	}

	@media (max-width: 768px) {
		.week-grid-wrap {
			display: none;
		}
		.grouped-list {
			display: block;
		}
	}
</style>
