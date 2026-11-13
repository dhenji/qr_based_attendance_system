<script lang="ts">
	import SkeletonDetail from '$lib/components/SkeletonDetail.svelte';
	import ClassroomMapPicker from '$lib/components/ClassroomMapPicker.svelte';
	import RadiusSelector from '$lib/components/RadiusSelector.svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import {
		initProfessorCourses,
		professorState
	} from '$lib/features/professor/store.svelte';
	import type { CourseType, ProfessorCourseSummary } from '$lib/shared/types';
	import {
		getSessionPlan,
		openSession,
		SESSION_CODE_SAMPLE
	} from '$lib/features/session/service';
	import type { SessionPlanResponse } from '$lib/shared/types';
	import { invalidateAttendanceDirectory } from '$lib/features/attendance/service';
	import { professorActiveSession, Routes } from '$lib/shared/constants/routes';
	import { APIError } from '$lib/api/client';
	import {
		formatInZone,
		formatWallClock,
		parseDateOnly,
		parseTimeToMinutes,
		zonedDateInputValue,
		zonedTimeInputValue
	} from '$lib/shared/utils/schedule';

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

	// D93: the session inherits the offering's configuration — the meeting it
	// belongs to, the next occurrence of that meeting, the attendance windows,
	// the classroom and the geofence radius. The plan comes from the server
	// (GET /professor/offerings/{id}/session-plan) so the form renders what
	// will actually be stored instead of re-deriving the schedule here.
	let plan = $state<SessionPlanResponse | null>(null);
	let planLoading = $state(false);
	let planError = $state<string | null>(null);

	// Reseed the per-offering form fields whenever the resolved course or the
	// session type changes, so switching in the selector variant never leaves
	// another course's numbers behind.
	//
	// Everything the plan carries is a *default*: the professor can still
	// change the duration, the windows and the radius, and the form sends
	// what they end up with. The classroom and the scheduled time are only
	// sent when the professor explicitly overrides them, so the offering's
	// own configuration is what lands in the row.
	//
	// Geofence is mandatory for every session type (lecture and lab): the
	// coordinates come from the offering's plan, and the professor only types
	// them when the offering has none.
	//
	// D95: the offering declares what it meets, so the form offers only
	// those types. The professor's choice is kept, but it falls back to the
	// first openable type — a laboratory-only offering must not ask for a
	// lecture plan on load.
	let chosenType = $state<CourseType | null>(null);
	let radius = $state(50);
	let durationMinutes = $state(90);
	let presentWindow = $state(15);
	let lateWindow = $state(5);
	// The plan's own values, kept as the inherited baseline (D93). A field is
	// sent only when the professor changed it, so the server's inheritance is
	// authoritative at open time — an administrator who retunes the offering
	// between the page load and the open still wins, and a plan that failed
	// to load can never smuggle a stale value into the session.
	let inherited = $state<{
		duration: number;
		present: number;
		late: number;
		radius: number;
	} | null>(null);
	// D17: an override moves the geofence, so it needs coordinates as well as a
	// name — both are required when the override is active and the plan has
	// none. Svelte's number binding yields undefined for an empty input,
	// which is why the validity check below uses a loose null comparison.
	let classroomOverride = $state('');
	let classroomLat = $state<number | null>(null);
	let classroomLng = $state<number | null>(null);
	// D17/D93: the explicit "use a different room" toggle. Off means the
	// offering's classroom applies and nothing is sent for it.
	let locationOverride = $state(false);
	let remoteSession = $state(false);
	let noClassroom = $state(false);

	$effect(() => {
		if (sessionType === 'lab' && remoteSession) remoteSession = false;
	});

	// D93: the schedule exception — a class that starts earlier or later than
	// planned, or one that has been moved to another day.
	let scheduleOverride = $state(false);
	let overrideDate = $state('');
	let overrideStart = $state('');
	// D94: why the professor moved the class, in their own words.
	let overrideReason = $state('');
	// D94: the start time the professor confirmed. It is kept as the value
	// they confirmed rather than as a flag, so editing the date or the time
	// takes the confirmation with it.
	let confirmedStart = $state('');

	let lastPlanKey = $state<string | null>(null);

	// D95: the types this offering can open. The server resolved them (an
	// offering with no meeting is a lecture offering), so the page renders
	// what it was told rather than deciding for itself.
	const openableTypes = $derived<CourseType[]>(
		selected !== null && selected.sessionTypes.length > 0
			? selected.sessionTypes
			: ['lecture']
	);

	const sessionType = $derived.by<CourseType>(() => {
		if (chosenType !== null && openableTypes.includes(chosenType)) return chosenType;
		return openableTypes[0];
	});

	// D95: the server refused this type because the offering does not meet
	// it. The course list is refreshed so the form stops offering it.
	const isTypeRefusal = (e: unknown): boolean =>
		e instanceof APIError && e.code === 'session_type_not_configured';

	const loadPlan = async (offeringId: number, type: CourseType) => {
		planLoading = true;
		planError = null;
		// A plan reload (new offering or session type) is a fresh attempt: drop
		// any verdict left over from a previously refused open so the form does
		// not stay blocked after the server would now permit it.
		windowRefused = false;
		error = null;
		try {
			const loaded = await getSessionPlan(offeringId, type);
			plan = loaded;
			inherited = {
				duration: loaded.duration_minutes,
				present: loaded.present_window_minutes,
				late: loaded.late_window_minutes,
				radius: loaded.radius_meters
			};
			durationMinutes = loaded.duration_minutes;
			presentWindow = loaded.present_window_minutes;
			lateWindow = loaded.late_window_minutes;
			radius = loaded.radius_meters;
			if (!locationOverride) {
				classroomOverride = loaded.classroom_name ?? '';
				classroomLat = loaded.classroom_lat;
				classroomLng = loaded.classroom_lng;
			}
			if (!scheduleOverride) {
				overrideDate = loaded.session_date ?? '';
				overrideStart = (loaded.start_time ?? '').slice(0, 5);
			}
		} catch (e: unknown) {
			plan = null;
			// No baseline: nothing is sent for the inherited fields, so the
			// server resolves them from the offering.
			inherited = null;
			planError = e instanceof Error ? e.message : 'Could not load the session plan';
			// D95: the offering no longer meets this type — the list the
			// page rendered is stale, so it is refreshed and the toggle
			// corrects itself.
			if (isTypeRefusal(e)) void initProfessorCourses();
		} finally {
			planLoading = false;
		}
	};

	$effect(() => {
		const course = selected;
		if (course === null) return;

		const key = `${course.offeringId}:${sessionType}`;
		if (key === lastPlanKey) return;

		lastPlanKey = key;
		void loadPlan(course.offeringId, sessionType);
	});

	// D17: an override replaces the offering's classroom for this session
	// only. The toggle is explicit, so the offering's own classroom keeps
	// applying until the professor says otherwise.
	const overrideActive = $derived(locationOverride);

	// A "different room" whose name and pin have both been cleared: the
	// session has no physical location, so the geofence is disabled and the
	// radius selection is meaningless.
	const locationCleared = $derived(
		sessionType === 'lecture' && (noClassroom || remoteSession)
	);

	// What the geofence will actually use, which is what the callout displays.
	const effectiveRoom = $derived(
		overrideActive && classroomOverride.trim() !== ''
			? classroomOverride.trim()
			: (plan?.classroom_name ?? 'Offering default classroom')
	);

	const effectiveLat = $derived(classroomLat);

	const effectiveLng = $derived(classroomLng);

	// Coordinates are required only for laboratory sessions (the backend
	// rejects a lab open without them). Lectures may legitimately have no
	// coordinates, in which case the geofence is skipped for that session.
	const coordsInvalid = $derived(
		sessionType === 'lab' &&
			!remoteSession &&
			(classroomLat == null ||
				classroomLng == null ||
				Number.isNaN(classroomLat) ||
				Number.isNaN(classroomLng))
	);

	// D13: present + late must fit inside the duration. The backend answers
	// windows_exceed_duration (422) for the same condition.
	const windowsFit = $derived(presentWindow + lateWindow <= durationMinutes);

	const durationInvalid = $derived(durationMinutes <= 0);
	const windowsInvalid = $derived(presentWindow < 0 || lateWindow < 0);

	// The scheduled window the session will carry: the plan's next
	// occurrence, or the exception the professor asked for. An override keeps
	// the meeting's length, so its end is the chosen start plus the
	// duration — the plan's own end belongs to the plan.
	const scheduledDate = $derived(
		scheduleOverride ? overrideDate : (plan?.session_date ?? '')
	);
	const scheduledStartTime = $derived(
		scheduleOverride ? overrideStart : (plan?.start_time ?? '').slice(0, 5)
	);
	// Class length for an override follows the offering's meeting length (a
	// timetable fact), not the scan window duration — so editing the duration
	// never moves the class end. Falls back to the requested duration when no
	// meeting is configured.
	const overrideClassLength = $derived(
		inherited !== null && inherited.duration > 0 ? inherited.duration : durationMinutes
	);
	const scheduledEndTime = $derived.by(() => {
		if (!scheduleOverride) return (plan?.end_time ?? '').slice(0, 5);
		const start = parseTimeToMinutes(overrideStart);
		if (start === null) return '';
		const minutes = (start + overrideClassLength) % (24 * 60);
		const hours = String(Math.floor(minutes / 60)).padStart(2, '0');
		const rest = String(minutes % 60).padStart(2, '0');
		return `${hours}:${rest}`;
	});

	const overrideDateValid = $derived(
		!scheduleOverride || /^\d{4}-\d{2}-\d{2}$/.test(overrideDate)
	);

	// Which of the inherited fields the professor has moved off the plan
	// (D93). The page shows the source of each value, so a session that
	// departs from the offering says so.
	const durationOverridden = $derived(
		inherited !== null && durationMinutes !== inherited.duration
	);
	const presentOverridden = $derived(
		inherited !== null && presentWindow !== inherited.present
	);
	const lateOverridden = $derived(inherited !== null && lateWindow !== inherited.late);
	const radiusOverridden = $derived(inherited !== null && radius !== inherited.radius);
	const overrideTimeValid = $derived(
		!scheduleOverride || /^([01]\d|2[0-3]):([0-5]\d)$/.test(overrideStart)
	);

	// D94: the server's verdict on whether the session may be opened right
	// now. The page never re-derives the window — it renders what
	// `GET /professor/offerings/{id}/session-plan` resolved, and the backend
	// refuses the open either way.
	const startWindow = $derived(plan?.start_window ?? null);
	const outsideWindow = $derived(startWindow !== null && !startWindow.permitted);

	const overrideStartInPast = $derived.by(() => {
		if (!scheduleOverride || !overrideDateValid || !overrideTimeValid) return false;
		const window = startWindow;
		const nowIso = window?.current_time ?? null;
		if (!nowIso) return false;
		const zone =
			window !== null && window.timezone !== ''
				? window.timezone
				: (plan?.timezone ?? 'UTC');
		const nowDate = zonedDateInputValue(nowIso, zone);
		const nowTime = zonedTimeInputValue(nowIso, zone);
		if (!nowDate || !nowTime) return false;
		// A previous calendar day is always past the grace window.
		if (overrideDate < nowDate) return true;
		if (overrideDate > nowDate) return false;
		const toMinutes = (t: string): number => {
			const [h, m] = t.split(':').map(Number);
			return h * 60 + m;
		};
		const graceMinutes = 0; // OVERRIDE_PAST_GRACE_MINUTES
		return toMinutes(overrideStart) < toMinutes(nowTime) - graceMinutes;
	});
	// Set when the backend refuses an open that the plan had permitted — a
	// plan loaded a while ago, or a class that ended while the form was up.
	let windowRefused = $state(false);
	const blocked = $derived(outsideWindow || windowRefused);

	// The professor confirms the alternative start time they picked; editing
	// it takes the confirmation with it.
	const overrideConfirmed = $derived(
		confirmedStart !== '' && confirmedStart === `${overrideDate} ${overrideStart}`
	);

	const windowHeadline = $derived.by(() => {
		const window = startWindow;
		if (window === null) return 'This session is outside its scheduled time.';
		if (window.reason === 'not_scheduled_today')
			return 'This course has no class scheduled today.';
		if (window.reason === 'before_window' && window.start_time !== null)
			return `The class starts at ${formatWallClock(window.start_time)}.`;
		if (window.reason === 'after_window' && window.start_time !== null)
			return `The class was scheduled for ${formatWallClock(window.start_time)}–${formatWallClock(
				window.end_time ?? ''
			)}.`;
		return 'This session is outside its scheduled time.';
	});

	// The scheduled time and the current time, side by side. Both come from
	// the server: the class time is the institution's wall clock, and the
	// current time is an instant rendered in the institution's zone.
	const windowScheduleLabel = $derived.by(() => {
		const window = startWindow;
		if (window === null) return '';
		const date = window.scheduled_date ?? plan?.session_date ?? '';
		const start = window.start_time ?? plan?.start_time ?? '';
		const end = window.end_time ?? plan?.end_time ?? '';
		if (start === '') return '';
		const day = parseDateOnly(date);
		const dayText =
			day === null
				? ''
				: day.toLocaleDateString(undefined, {
						weekday: 'short',
						month: 'short',
						day: 'numeric'
					});
		return `${dayText} ${formatWallClock(start)}–${formatWallClock(end)}`.trim();
	});

	// The institution-wall-clock window during which an open is permitted
	// (early-open grace … late-open grace around the class). Shown in the
	// blocked panel so the professor sees exactly when they can try again.
	const openWindowLabel = $derived.by(() => {
		const window = startWindow;
		if (window === null || window.opens_at === null || window.closes_at === null)
			return '';
		const zone = window.timezone === '' ? 'UTC' : window.timezone;
		const open = formatInZone(window.opens_at, zone, {
			hour: 'numeric',
			minute: '2-digit'
		});
		const close = formatInZone(window.closes_at, zone, {
			hour: 'numeric',
			minute: '2-digit'
		});
		return `${open} – ${close}`;
	});

	const windowCurrentLabel = $derived.by(() => {
		const window = startWindow;
		if (window === null || window.current_time === null) return '';
		const zone = window.timezone === '' ? 'UTC' : window.timezone;
		const day = formatInZone(window.current_time, zone, {
			weekday: 'short',
			month: 'short',
			day: 'numeric'
		});
		const time = formatInZone(window.current_time, zone, {
			hour: 'numeric',
			minute: '2-digit'
		});
		return `${day} ${time}`.trim();
	});

	// Widths for the visual timeline bar: class length vs scan duration,
	// scaled to the longer of the two so both always fit.
	const timelineWidths = $derived.by(() => {
		const classLen = inherited !== null && inherited.duration > 0 ? inherited.duration : durationMinutes;
		const scanLen = durationMinutes;
		const maxLen = Math.max(classLen, scanLen, 1);
		return {
			classPct: (classLen / maxLen) * 100,
			scanPct: (scanLen / maxLen) * 100,
		};
	});

	// Preview of the two time concepts the session will carry: the scan
	// window (start + duration) and the class end (offering schedule, or
	// start + duration in override mode). Shown so the professor sees the
	// effect of the duration field before opening.
	const previewTimes = $derived.by(() => {
		if (durationInvalid) return null;
		const start = parseTimeToMinutes(scheduledStartTime);
		if (start === null) return null;
		const scanEndMin = (start + durationMinutes) % (24 * 60);
		const scanEnd = `${String(Math.floor(scanEndMin / 60)).padStart(2, '0')}:${String(scanEndMin % 60).padStart(2, '0')}`;
		const classEnd = scheduledEndTime || '—';
		const overtime =
			scheduledEndTime !== '' &&
			parseTimeToMinutes(scheduledEndTime) !== null &&
			((parseTimeToMinutes(scheduledEndTime)! - start + 24 * 60) % (24 * 60)) < durationMinutes;
		return { scanStart: scheduledStartTime, scanEnd, classEnd, overtime };
	});

	const RADII = [10, 20, 30, 50, 100] as const;

	// The radius the session would inherit if the professor changes nothing:
	// the server-resolved default for this offering (offering override ->
	// app setting -> env). The "Default" chip restores exactly this value,
	// so the professor can always get back to the configured radius.
	const defaultRadius = $derived(inherited === null ? null : inherited.radius);

	// The chips on offer: the standard radii plus the effective default, so a
	// default that is not one of the standard numbers (an administrator may
	// set any value in 10..1000) is still visible and selectable instead of
	// leaving every chip unselected.
	const radiusOptions = $derived.by(() => {
		const options = new Set<number>(RADII);
		if (defaultRadius !== null) options.add(defaultRadius);
		return [...options].sort((a, b) => a - b);
	});

	// Whether the professor has moved anything off the inherited plan (D93).
	// The back control asks before discarding these, so a half-configured
	// session is not lost to a stray click. Switching the session type counts:
	// it reloads the plan, which re-seeds the fields.
	const isDirty = $derived(
		(inherited !== null &&
			(durationOverridden ||
				presentOverridden ||
				lateOverridden ||
				radiusOverridden)) ||
			locationOverride ||
			scheduleOverride ||
			chosenType !== null
	);

	let confirmLeave = $state(false);

	// Leaving the form. The destination is fixed rather than history-based:
	// this page is also reachable from the dashboard, where "back" would land
	// somewhere unrelated. Unsaved changes are confirmed first.
	const requestLeave = () => {
		if (isDirty) {
			confirmLeave = true;
			return;
		}
		void goto(Routes.PROFESSOR_COURSES);
	};

	const leave = () => {
		confirmLeave = false;
		void goto(Routes.PROFESSOR_COURSES);
	};

	let submitting = $state(false);
	let generatedSessionId = $state<number | null>(null);
	let generatedCode = $state<string | null>(null);
	let generatedExpiry = $state<string | null>(null);
	let generatedScheduled = $state<string | null>(null);
	let generatedOverridden = $state(false);
	// D96: the session was created and is awaiting the professor's confirmation
	// before leaving the form. Auto-navigation is gone — the professor sees the
	// code and scheduled time, and steps forward only on purpose.
	let confirmCreated = $state(false);
	// D96: the "Generate Session Code" button asks once more before opening the
	// session, so a stray click on a half-configured form does not mint a code.
	let confirmGenerate = $state(false);
	let error = $state<string | null>(null);

	const canSubmit = $derived(
		selected !== null &&
			selected.scheduleOk &&
			windowsFit &&
			!durationInvalid &&
			!windowsInvalid &&
			!coordsInvalid &&
			overrideDateValid &&
			overrideTimeValid &&
			!overrideStartInPast &&
			// D94: outside the class's scheduled time the professor has to
			// pick a different start time and confirm it. Inside it, the
			// normal flow is unchanged.
			(!blocked || (scheduleOverride && overrideConfirmed)) &&
			// A plan that failed to load leaves the inherited fields
			// unresolved; opening now would send a guess, so the page asks
			// for a retry instead.
			planError === null &&
			!planLoading &&
			!submitting
	);

	// D94: the two ways out of a window the professor is not inside. Waiting
	// returns to the course list; starting elsewhere opens the picker.
	const waitForScheduledTime = () => {
		void goto(Routes.PROFESSOR_COURSES);
	};

	const selectDifferentStartTime = () => {
		// The picker opens on the server's clock, read in the institution's
		// zone: a professor who is late means "now", not the next class.
		const window = startWindow;
		const zone =
			window !== null && window.timezone !== ''
				? window.timezone
				: (plan?.timezone ?? 'UTC');
		let seeded = false;
		if (window !== null && window.current_time !== null) {
			const day = zonedDateInputValue(window.current_time, zone);
			const time = zonedTimeInputValue(window.current_time, zone);
			if (day !== '' && time !== '') {
				overrideDate = day;
				overrideStart = time;
				seeded = true;
			}
		}
		if (!seeded) {
			const nowIso = new Date().toISOString();
			const day = zonedDateInputValue(nowIso, zone);
			const time = zonedTimeInputValue(nowIso, zone);
			if (day !== '' && time !== '') {
				overrideDate = day;
				overrideStart = time;
			}
		}
		scheduleOverride = true;
		// An explicit override is the sanctioned way past the open window, so a
		// prior "outside window" refusal no longer applies.
		windowRefused = false;
		error = null;
		confirmedStart = '';
	};

	const confirmStartTime = () => {
		// Guard: refuse to confirm a start time that is already past the
		// allowed grace window, even if the disabled-state gate missed it.
		if (overrideStartInPast) {
			error = 'The selected start time is in the past. Choose the current or a future time.';
			return;
		}
		confirmedStart = `${overrideDate} ${overrideStart}`;
	};

	// The actual open call. Split out so the confirmation panel and the
	// programmatic path share one implementation (D96).
	const doGenerate = async () => {
		const course = selected;
		if (course === null || !canSubmit) return;

		submitting = true;
		error = null;

		try {
			// Only what the professor actually changed is sent (D93). An
			// untouched field stays absent, so the server resolves it from the
			// offering's plan rather than from a copy the page happened to
			// load.
			// Always send a value the professor actually edited, even when the
			// plan failed to load (inherited === null): otherwise a stale/empty
			// baseline would silently drop the professor's input and the server
			// would fall back to the offering's defaults.
			const changed = {
				...(inherited === null || durationMinutes !== inherited.duration
					? { durationMinutes }
					: {}),
				...(inherited === null || presentWindow !== inherited.present
					? { presentWindowMinutes: presentWindow }
					: {}),
				...(inherited === null || lateWindow !== inherited.late
					? { lateWindowMinutes: lateWindow }
					: {}),
				...( (inherited === null || radius !== inherited.radius) && !locationCleared
					? { geofenceRadius: radius }
					: {})
			};

			const created = await openSession(course.offeringId, {
				sessionType: sessionType,
				...changed,
				// D17: the classroom is only sent when the professor
				// overrode it — the offering's own classroom is what the
				// server resolves otherwise.
				...(overrideActive
					? {
							classroomOverride: true,
							classroomName: classroomOverride.trim() || undefined,
							classroomLat: classroomLat ?? undefined,
							classroomLng: classroomLng ?? undefined
						}
					: {}),
				...(remoteSession ? { isRemote: true, classroomOverride: true } : {}),
				geofenceEnabled: !noClassroom && !remoteSession,
				...(noClassroom ? { classroomOverride: true } : {}),
				// D93: the schedule exception, in the institution's wall
				// clock. Both fields travel together so the override is
				// unambiguous. D94 adds the professor's own reason.
				...(scheduleOverride
					? {
							sessionDate: overrideDate,
							startTime: overrideStart,
							overrideReason: overrideReason.trim() || undefined
						}
					: {})
			});

			generatedSessionId = created.id;
			generatedCode = created.qrPayload.code;
			generatedExpiry =
				created.expiresAt === null ? null : dateTimeText(new Date(created.expiresAt));
			generatedScheduled = `${created.scheduledStartTime} → ${created.scheduledEndTime}`;
			generatedOverridden = created.scheduleOverridden;
			invalidateAttendanceDirectory();
			// D96: creation succeeds — hold the professor on the form with a
			// confirmation panel rather than navigating away. The live session
			// is reached only after the professor confirms.
			if (typeof created.id === 'number' && Number.isInteger(created.id) && created.id > 0) {
				confirmCreated = true;
				return;
			}
			error = 'Session created but session ID is missing from response.';
		} catch (e) {
			// D94: the backend refuses an open outside the class's scheduled
			// time. That is not a failure to report — it is the window the
			// form asks about, so the same panel is shown.
			if (e instanceof APIError && e.code === 'session_outside_scheduled_time') {
				windowRefused = true;
				error = e.message;
				return;
			}
			// D95: the offering does not meet this type, so the list the
			// form rendered is stale. Refresh it and say what went wrong.
			if (isTypeRefusal(e)) {
				void initProfessorCourses();
				chosenType = null;
			}
			error = e instanceof Error ? e.message : 'Failed to open session';
		} finally {
			submitting = false;
		}
	};

	// D96: the button asks once more before opening the session. A session
	// code is minted server-side and cannot be undone, so a stray click on a
	// half-configured form should not reach it.
	const confirmGenerateAction = async () => {
		confirmGenerate = false;
		await doGenerate();
	};

	const dismissGenerate = () => {
		confirmGenerate = false;
	};

	const requestGenerate = () => {
		if (!canSubmit) return;
		confirmGenerate = true;
	};

	const viewLiveSession = () => {
		if (generatedSessionId === null) return;
		void goto(professorActiveSession(generatedSessionId));
	};

	// D96: the professor steps out of the confirmation panel into the live
	// session. The panel is dismissed first so the destination is the only
	// thing left on screen.
	const openLiveSession = () => {
		confirmCreated = false;
		if (generatedSessionId === null) return;
		void goto(professorActiveSession(generatedSessionId));
	};

	// D96: dismissing the confirmation panel without opening the live session
	// leaves the professor on the form with the generated code shown, so they
	// can regenerate or simply navigate away.
	const dismissCreated = () => {
		confirmCreated = false;
	};

	const retryPlan = () => {
		const course = selected;
		if (course === null) return;
		lastPlanKey = null;
		void loadPlan(course.offeringId, sessionType);
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
		<button class="btn btn-ghost back-btn" type="button" onclick={requestLeave}>
			<AppIcon name="arrow-left" size={16} />
			Back to My Courses
		</button>
		<div>
			<h1>Open New Session</h1>
			<p class="muted">Configure and generate a session code for attendance</p>
		</div>
	</header>

	{#if professorState.coursesLoading}
		<SkeletonDetail rows={4} label="Loading your courses…" />
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
				{#each openableTypes as type (type)}
					<button
						class="toggle-btn"
						class:selected={sessionType === type}
						aria-pressed={sessionType === type}
						onclick={() => (chosenType = type)}
					>
						<AppIcon name={type === 'lab' ? 'shield' : 'file'} size={16} />
						{type === 'lab' ? 'Laboratory' : 'Lecture'}
					</button>
				{/each}
			</div>
			<p class="hint">
				{#if openableTypes.length > 1}
					Both types enforce the geofence: students must be within the radius to scan.
				{:else}
					Sessions enforce the geofence: students must be within the radius to scan.
				{/if}
			</p>
		</div>

		{#if remoteSession}
			<div class="lab-banner">
				<AppIcon name="alert" size={16} />
				<span>
					<strong>Remote session:</strong> geofencing is disabled and no classroom coordinates are required.
				</span>
			</div>
		{:else if sessionType === 'lab'}
			<div class="lab-banner">
				<AppIcon name="alert" size={16} />
				<span>
					<strong>Geofence required:</strong> students must be within the geofence radius to scan attendance.
					Classroom coordinates come from the offering; type them only if the room changed.
				</span>
			</div>
		{:else}
			<div class="lab-banner">
				<AppIcon name="alert" size={16} />
				<span>
					<strong>Geofence applies when coordinates are set:</strong> students must be within the radius to scan.
					Leave the coordinates blank to skip geofencing for this lecture.
				</span>
			</div>
		{/if}

		<div class="field">
			<span class="form-label">Scheduled Time</span>
			{#if planError}
				<p class="field-error">{planError}</p>
				<p class="hint">
					The offering's schedule, classroom and attendance windows could not be
					read, so the session would not know what to inherit. Retry before opening.
				</p>
				<button class="btn btn-secondary" type="button" onclick={retryPlan}>
					<AppIcon name="alert" size={16} />
					Retry
				</button>
			{:else if planLoading && plan === null}
				<p class="hint">Loading the offering's schedule…</p>
			{:else if plan !== null && plan.source !== 'none' && plan.source !== 'course_default'}
				<div class="schedule">
					<AppIcon name="calendar" size={16} />
					<span>
						{scheduledDate || 'Next meeting'}
						{scheduledStartTime}–{scheduledEndTime}
						{#if plan.timezone && plan.timezone !== 'UTC'}
							<span class="muted">({plan.timezone})</span>
						{/if}
					</span>
					{#if scheduleOverride}
						<span class="location-tag">Override</span>
					{/if}
				</div>

				{#if blocked}
					<div class="window-note" role="alert">
						<AppIcon name="alert" size={18} />
						<div class="window-note-body">
							<p class="window-note-title">{windowHeadline}</p>
							{#if windowScheduleLabel !== ''}
								<p class="window-note-line">
									<span class="muted">Scheduled</span> {windowScheduleLabel}
								</p>
							{/if}
							{#if windowCurrentLabel !== ''}
								<p class="window-note-line">
									<span class="muted">Current time</span> {windowCurrentLabel}
								</p>
							{/if}
							{#if openWindowLabel !== ''}
								<p class="window-note-line">
									<span class="muted">Open window</span> {openWindowLabel}
								</p>
							{/if}
							<p class="window-note-line">
								Please wait until the scheduled time or select a different start time to
								continue.
							</p>
							<div class="window-note-actions">
								<button
									class="btn btn-secondary"
									type="button"
									onclick={waitForScheduledTime}
								>
									<AppIcon name="calendar" size={16} />
									Wait for Scheduled Time
								</button>
								{#if !scheduleOverride}
									<button
										class="btn btn-primary"
										type="button"
										onclick={selectDifferentStartTime}
									>
										Select Different Start Time
									</button>
								{/if}
							</div>
						</div>
					</div>
				{/if}

				{#if !blocked && !scheduleOverride}
					<div class="field">
						<button
							class="btn btn-secondary"
							type="button"
							onclick={selectDifferentStartTime}
						>
							Start at a different time
						</button>
					</div>
				{/if}
				{#if scheduleOverride}
					<div class="override-box">
						<div class="field-row">
							<div class="field">
								<label class="form-label" for="override-date">Date</label>
								<input
									id="override-date"
									class="form-input"
									class:invalid={!overrideDateValid}
									type="date"
									bind:value={overrideDate}
								/>
							</div>
							<div class="field">
								<label class="form-label" for="override-start">Start time</label>
								<input
									id="override-start"
									class="form-input"
									class:invalid={!overrideTimeValid || overrideStartInPast}
									type="time"
									bind:value={overrideStart}
								/>
							</div>
						</div>
						{#if overrideStartInPast}
							<p class="field-error">
								Start time is in the past — pick the current time or a later one.
							</p>
						{/if}
						<div class="field">
							<label class="form-label" for="override-reason">Reason (optional)</label>
							<input
								id="override-reason"
								class="form-input"
								type="text"
								maxlength="255"
								placeholder="Why is the class starting at a different time?"
								bind:value={overrideReason}
							/>
						</div>
						{#if blocked}
							<div class="field">
								<button
									class="btn btn-secondary"
									type="button"
									disabled={!overrideDateValid || !overrideTimeValid || overrideStartInPast}
									onclick={confirmStartTime}
								>
									<AppIcon name="check" size={16} />
									{overrideConfirmed ? 'Start time confirmed' : 'Use this start time'}
								</button>
								{#if overrideConfirmed}
									<span class="hint">The session will start at {overrideDate} {overrideStart}.</span>
								{/if}
							</div>
						{/if}
						<p class="hint">
							The session keeps the meeting's length and applies to this session only — the
							offering's weekly schedule is not changed.
						</p>
						<div class="field">
							<button
								class="btn btn-secondary"
								type="button"
								onclick={() => {
									scheduleOverride = false;
									overrideDate = '';
									overrideStart = '';
									overrideReason = '';
									confirmedStart = '';
								}}
							>
								Cancel override
							</button>
						</div>
					</div>
				{/if}
			{:else}
				<div class="schedule">
					<AppIcon name="calendar" size={16} />
					<span>No configured meeting for this offering — the session will start now.</span>
				</div>
			{/if}
		</div>

		{#if sessionType !== 'lab' && !(locationOverride && (classroomOverride.trim() !== '' || classroomLat !== null || classroomLng !== null))}
		<div class="field">
			<label class="override-toggle">
				<input
					type="checkbox"
					checked={noClassroom}
					onchange={(e) => {
						noClassroom = e.currentTarget.checked;
						if (noClassroom) {
							remoteSession = false;
							locationOverride = true;
							classroomOverride = '';
							classroomLat = null;
							classroomLng = null;
						} else {
							locationOverride = false;
							if (plan) {
								classroomOverride = plan.classroom_name ?? '';
								classroomLat = plan.classroom_lat;
								classroomLng = plan.classroom_lng;
							}
						}
					}}
				/>
				No classroom
			</label>
		</div>
		<div class="field">
			<label class="override-toggle">
				<input
					type="checkbox"
					checked={remoteSession}
					onchange={(e) => {
						remoteSession = e.currentTarget.checked;
						if (remoteSession) {
							noClassroom = false;
							locationOverride = false;
							classroomLat = null;
							classroomLng = null;
						}
					}}
				/>
				Remote / online session
			</label>
		</div>
		{/if}

		{#if !remoteSession}
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
		{/if}

		{#if !(remoteSession || locationCleared)}
		<div class="field">
			<span class="form-label">
				Geofence Radius
				<span class="required-tag">Required</span>
			</span>
			<div class="radius-group" role="group" aria-label="Geofence radius">
				<RadiusSelector
					value={radius}
					min={1}
					max={1000}
					defaultValue={defaultRadius ?? undefined}
					inheriting={defaultRadius !== null && radius === defaultRadius}
					defaultChipLabel={defaultRadius !== null ? `Default (${defaultRadius} m)` : undefined}
					onDefault={() => {
						if (defaultRadius !== null) radius = defaultRadius;
					}}
					onChange={(v) => (radius = v)}
				/>
			</div>
			<p class="hint">
				Students must be within this radius to scan.
				{#if inherited !== null}
					Default: {inherited.radius} m.
				{:else}
					The offering’s default radius is unavailable — retry loading the plan.
				{/if}
			</p>
			{#if inherited !== null && radiusOverridden}
				<p class="hint">
					<span class="location-tag">Override</span>
				</p>
			{/if}
		</div>
		{:else}
			<p class="hint">
				{#if remoteSession}
					Geofence skipped — no classroom coordinates.
				{/if}
			</p>
		{/if}

			<p class="hint" style="margin-bottom: 0.5rem;">
				Class time comes from the offering's schedule. The scan window is how long students can scan (can be shorter or longer than the class).
			</p>
			<div class="field">
				<label class="form-label" for="duration">Scan window duration (minutes)</label>
				<div class="duration-chips">
					{#if inherited !== null && inherited.duration > 0}
						<button type="button" class="chip" class:chip-selected={durationMinutes === inherited!.duration} onclick={() => (durationMinutes = inherited!.duration)}>
							Class length ({inherited!.duration})
						</button>
					{/if}
					{#each [30, 45, 60, 90, 120] as preset (preset)}
						<button type="button" class="chip" class:chip-selected={durationMinutes === preset} onclick={() => (durationMinutes = preset)}>
							{preset}
						</button>
					{/each}
				</div>
				<input
					id="duration"
					class="form-input"
					class:invalid={durationInvalid}
					type="number"
					min="1"
					bind:value={durationMinutes}
				/>
				{#if inherited !== null}
					<p class="hint">
						Class runs {plan?.start_time?.slice(0, 5) ?? '—'}–{plan?.end_time?.slice(0, 5) ?? '—'} ({inherited.duration} m) — the scheduled meeting length
						{#if durationOverridden}
							<span class="location-tag">Override</span>
						{/if}
					</p>
				{/if}
				{#if previewTimes}
					<div class="session-timeline" aria-label="Class time vs scan window">
						<div class="tl-row">
							<span class="tl-label">Class</span>
							<div class="tl-track">
								<div class="tl-bar tl-class" style="width: {timelineWidths.classPct}%;"></div>
							</div>
							<span class="tl-time">{previewTimes.scanStart}–{previewTimes.classEnd}</span>
						</div>
						<div class="tl-row">
							<span class="tl-label">Scan</span>
							<div class="tl-track">
								<div
									class="tl-bar tl-scan"
									class:tl-overtime={previewTimes.overtime}
									style="width: {timelineWidths.scanPct}%;"
								></div>
							</div>
							<span class="tl-time">{previewTimes.scanStart}–{previewTimes.scanEnd}</span>
						</div>
					</div>
					<p class="hint">
						Scan window {previewTimes.scanStart} → {previewTimes.scanEnd}
						· Class ends {previewTimes.classEnd}
						{#if previewTimes.overtime}
							<span class="location-tag">Extends past class end</span>
						{:else if previewTimes.scanEnd !== previewTimes.classEnd && previewTimes.scanEnd < previewTimes.classEnd}
							<span class="location-tag">Closes before class ends</span>
						{/if}
					</p>
				{/if}
				{#if scheduleOverride}
					<p class="hint">
						Class end follows the offering's meeting length (start + class length); the scan window follows the duration.
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
					{#if inherited !== null}
						<p class="hint">
							{inherited.present} min from the offering
							{#if presentOverridden}
								<span class="location-tag">Override</span>
							{/if}
						</p>
					{/if}
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
					{#if inherited !== null}
						<p class="hint">
							{inherited.late} min from the offering
							{#if lateOverridden}
								<span class="location-tag">Override</span>
							{/if}
						</p>
					{/if}
				</div>
			</div>

			<div class="check" class:bad={!windowsFit} role="status">
				<span class="check-math">
					Present {presentWindow} + Late {lateWindow} ≤ Duration {durationMinutes}
				</span>
				<AppIcon name={windowsFit ? 'check' : 'alert'} size={18} />
			</div>

		{#if !remoteSession && !noClassroom}
		<div class="field">
			<span class="form-label">Classroom</span>
			<div class="field">
				<label class="override-toggle">
					<input
						type="checkbox"
						checked={locationOverride}
						onchange={(e) => {
							const checked = e.currentTarget.checked;
							if (checked) {
								noClassroom = false;
								locationOverride = true;
							} else {
								locationOverride = false;
								if (plan) {
									classroomOverride = plan.classroom_name ?? '';
									classroomLat = plan.classroom_lat;
									classroomLng = plan.classroom_lng;
								} else {
									classroomOverride = '';
									classroomLat = null;
									classroomLng = null;
								}
							}
						}}
					/>
					Use a different room
				</label>
			</div>

			{#if locationOverride}
				<div class="field">
					<label class="form-label" for="classroom">Classroom name (optional)</label>
					<input
						id="classroom"
						class="form-input"
						type="text"
						placeholder="e.g. Lab 101, Room 301"
						bind:value={classroomOverride}
					/>
					<p class="hint">
						Blank uses the offering default classroom name (D17).
					</p>
				</div>

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
						<ClassroomMapPicker
							lat={classroomLat}
							lng={classroomLng}
							onChange={(la, lo) => { classroomLat = la; classroomLng = lo; }}
							onClear={() => { classroomLat = null; classroomLng = null; }}
							height="320px"
						/>
						<p class="hint">
							The geofence centers here. {sessionType === 'lab'
								? 'Both coordinates are required for a laboratory session.'
								: 'Coordinates are optional for a lecture — leave them blank to skip geofencing.'}
						</p>
						{#if coordsInvalid}
							<p class="field-error">
								Both coordinates are required to open a session.
							</p>
						{/if}
					</div>
			{:else}
				<p class="hint">
					The offering's classroom and coordinates apply. Tick "Use a different room" if the
					class moved — the change applies to this session only.
				</p>
				{#if sessionType === 'lab' && coordsInvalid}
					<p class="field-error">
						This offering has no classroom coordinates. Tick "Use a different room" and
						type them before opening a laboratory session.
					</p>
				{/if}
			{/if}
		</div>
		{/if}

			<div class="preview" class:generated={generatedCode !== null}>
				<span class="preview-label">HMAC Preview · Session Code</span>
				{#if generatedCode}
					<span class="preview-code">{generatedCode}</span>
					<p class="preview-hint">
						Scan window closes at {generatedExpiry}. Show this on the projector for
						students to scan.
					</p>
					<p class="preview-hint">
						Scheduled {generatedScheduled}
						{#if generatedOverridden}
							— overridden for this session.
						{/if}
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
					onclick={requestGenerate}
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

{#if confirmLeave}
	<Modal
		title="Discard session details?"
		onclose={() => (confirmLeave = false)}
		closeOnBackdrop={false}
	>
		<p class="leave-message">
			You changed this session's settings and they have not been saved. Leaving now
			discards them.
		</p>
		{#snippet footer()}
			<button class="leave-btn" type="button" onclick={() => (confirmLeave = false)}>
				Keep editing
			</button>
			<button class="leave-btn leave-primary" type="button" onclick={leave}>
				Leave
			</button>
		{/snippet}
	</Modal>
{/if}

{#if confirmCreated}
		<Modal
			title="Session created"
			onclose={dismissCreated}
			closeOnBackdrop={false}
		>
			<div class="confirm-created">
				<div class="confirm-created-icon">
					<AppIcon name="check" size={28} />
				</div>
				<p class="confirm-created-text">
					Your session is active. Show the code on the projector for students to scan.
				</p>
				<div class="confirm-created-code">
					<span class="preview-label">Session Code</span>
					<span class="preview-code">{generatedCode}</span>
				</div>
				{#if generatedExpiry}
					<p class="confirm-created-hint">
						Scan window closes at {generatedExpiry}.
					</p>
				{/if}
				{#if generatedScheduled}
					<p class="confirm-created-hint">
						Scheduled {generatedScheduled}
						{#if generatedOverridden}
							— overridden for this session.
						{/if}
					</p>
				{/if}
			</div>
			{#snippet footer()}
				<button class="leave-btn" type="button" onclick={dismissCreated}>
					Stay on this form
				</button>
				<button class="leave-btn leave-primary" type="button" onclick={openLiveSession}>
					<AppIcon name="shield" size={16} />
					Open Live Session
				</button>
			{/snippet}
		</Modal>
	{/if}

	{#if confirmGenerate}
		<Modal
			title="Generate session code?"
			onclose={dismissGenerate}
			closeOnBackdrop={false}
		>
			<div class="confirm-generate">
				<div class="confirm-generate-icon">
					<AppIcon name="qr" size={28} />
				</div>
				<p class="confirm-generate-text">
					Opening this session starts the scan window and generates a new code. It cannot be
					undone — students who scan before you are ready will be marked present.
				</p>
				<div class="confirm-generate-summary">
					{#if selected}
						<div class="confirm-generate-row">
							<span class="confirm-generate-label">Course</span>
							<span>{selected.courseCode} — {selected.courseName}</span>
						</div>
					{/if}
					<div class="confirm-generate-row">
						<span class="confirm-generate-label">Type</span>
						<span>{sessionType === 'lab' ? 'Laboratory' : 'Lecture'}</span>
					</div>
					<div class="confirm-generate-row">
						<span class="confirm-generate-label">Scheduled</span>
						<span>
							{scheduledDate || 'Now'}
							{#if scheduledDate}
								{scheduledStartTime}–{scheduledEndTime}
							{/if}
						</span>
					</div>
					<div class="confirm-generate-row">
						<span class="confirm-generate-label">Scan window</span>
						<span>{scheduledStartTime || 'Now'}–{previewTimes?.scanEnd ?? scheduledEndTime}</span>
					</div>
					<div class="confirm-generate-row">
						<span class="confirm-generate-label">Class ends</span>
						<span>
							{scheduledEndTime || '—'}
							{#if previewTimes?.overtime}
								(extended)
							{:else if previewTimes && previewTimes.scanEnd !== previewTimes.classEnd && previewTimes.scanEnd < previewTimes.classEnd}
								(shortened)
							{/if}
						</span>
					</div>
					<div class="confirm-generate-row">
						<span class="confirm-generate-label">Duration</span>
						<span>{durationMinutes} min</span>
					</div>
				</div>
				{#if durationOverridden || presentOverridden || lateOverridden || radiusOverridden || locationOverride || scheduleOverride}
					<p class="confirm-generate-hint">
						These settings differ from the offering's plan and apply to this session only.
					</p>
				{/if}
			</div>
			{#snippet footer()}
				<button class="leave-btn" type="button" onclick={dismissGenerate}>
					Keep editing
				</button>
				<button class="leave-btn leave-primary" type="button" onclick={confirmGenerateAction}>
					<AppIcon name="qr" size={16} />
					Generate
				</button>
			{/snippet}
		</Modal>
	{/if}

<style>
	.create {
		display: flex;
		flex-direction: column;
		gap: 2rem;
		/* The layout's content column is 1100px, so a fixed-width form has to
		   center itself or it hugs the left edge on wide screens. */
		max-width: 700px;
		margin: 0 auto;
	}

	.header {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 0.75rem;
	}

	.header h1 {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0 0 0.25rem;
	}

	/* The back control is a navigation affordance, not a competing action,
	   so it sits above the title at a smaller size than the buttons below. */
	.back-btn {
		padding: 0.5rem 0.875rem;
		font-size: 0.875rem;
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
		gap: 0.625rem;
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

	/* --- Schedule callout (D93) --------------------------------------------- */

	.schedule {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.5rem;
		padding: 0.75rem;
		background: var(--bg-page);
		border: 1px solid var(--border);
		border-radius: 8px;
		font-size: 0.8125rem;
		color: var(--text-secondary);
	}

	.schedule :global(svg) {
		color: var(--text-muted);
		flex-shrink: 0;
	}

	/* --- Override toggle ------------------------------------------------------ */

	.override-toggle {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
		cursor: pointer;
	}

	.override-toggle input {
		accent-color: var(--brand);
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
		border-color: var(--warning-text);
		color: var(--warning-text);
	}

	/* --- Session timing timeline -------------------------------------------- */
	.session-timeline {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		margin: 0.5rem 0 0.25rem;
		padding: 0.625rem 0.75rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--bg-muted);
	}

	.tl-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.tl-label {
		flex: 0 0 3rem;
		font-size: 0.75rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--text-muted);
	}

	.tl-track {
		flex: 1 1 auto;
		height: 0.625rem;
		border-radius: 999px;
		background: var(--bg-page);
		border: 1px solid var(--border);
		overflow: hidden;
		position: relative;
	}

	.tl-bar {
		height: 100%;
		border-radius: 999px;
		transition: width 0.15s ease;
	}

	.tl-class {
		background: var(--text-muted);
		opacity: 0.45;
	}

	.tl-scan {
		background: var(--brand);
	}

	.tl-scan.tl-overtime {
		background: var(--warning-text);
	}

	.tl-time {
		flex: 0 0 auto;
		font-family: var(--font-data);
		font-size: 0.75rem;
		color: var(--text-secondary);
		white-space: nowrap;
	}

	.duration-chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.375rem;
		margin-bottom: 0.5rem;
	}

	.chip {
		padding: 0.3125rem 0.625rem;
		border-radius: 999px;
		border: 1px solid var(--border-strong);
		background: var(--bg-card);
		color: var(--text-secondary);
		font-size: 0.8125rem;
		font-weight: 600;
		cursor: pointer;
		font-family: inherit;
	}

	.chip:hover {
		background: var(--bg-hover);
		color: var(--text-strong);
	}

	.chip-selected {
		background: var(--brand);
		border-color: var(--brand);
		color: var(--on-brand);
	}

	.location-tag {
		margin-left: 0.5rem;
		padding: 0.125rem 0.5rem;
		border-radius: 6px;
		background: var(--warning-bg);
		border: 1px solid var(--warning-text);
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
		border: 2px solid var(--success);
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
		color: var(--text-muted);
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

	/* The ghost variant is the professor portal's back-control treatment
	   (see professor/sessions/active/[id]). */
	.btn-ghost {
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		color: var(--text-strong);
	}

	.btn-ghost:hover {
		background: var(--bg-hover);
	}

	.btn:disabled {
		color: var(--text-muted);
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

	/* D94: the session is outside its class's scheduled time. The professor
	   has two ways out, so the panel states both of them and the scheduled
	   time next to the current one. */
	.window-note {
		display: flex;
		align-items: flex-start;
		gap: 0.625rem;
		background: var(--warning-bg);
		border: 1px solid var(--warning-bg);
		border-radius: 8px;
		padding: 0.875rem 1rem;
	}

	.window-note :global(svg) {
		flex-shrink: 0;
		margin-top: 0.125rem;
		color: var(--warning-text);
	}

	.window-note-body {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		min-width: 0;
	}

	.window-note-title {
		margin: 0;
		font-size: 0.9375rem;
		font-weight: 600;
		color: var(--warning-text);
	}

	.window-note-line {
		margin: 0;
		font-size: 0.875rem;
		color: var(--text-secondary);
	}

	.window-note-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-top: 0.5rem;
	}

	.empty {
		color: var(--text-muted);
		font-size: 0.9375rem;
		margin: 0;
	}

	/* --- Leave confirmation --------------------------------------------------- */

	.leave-message {
		margin: 0;
		font-size: 0.9375rem;
		color: var(--text-secondary);
	}

	/* Its own button styles rather than the page's `.btn`: the page's primary
	   button flexes to fill its row, which is wrong inside the dialog's
	   right-aligned action row. */
	.leave-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0.5rem 1rem;
		border-radius: 8px;
		border: 1px solid var(--border-strong);
		background: var(--bg-card);
		color: var(--text-strong);
		font-family: inherit;
		font-size: 0.875rem;
		font-weight: 600;
		cursor: pointer;
	}

	.leave-btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.leave-primary {
		background: var(--brand);
		border-color: var(--brand);
		color: var(--on-brand);
	}

	/* --- Session creation confirmation ---------------------------------------- */

	/* The confirmation panel is a success moment, so the icon is tinted to
	   match the generated-preview treatment rather than the neutral modal. */
	.confirm-created {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.75rem;
		text-align: center;
	}

	.confirm-created-icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 3rem;
		height: 3rem;
		border-radius: 50%;
		background: var(--success-bg);
		color: var(--success);
	}

	.confirm-created-text {
		margin: 0;
		font-size: 0.9375rem;
		color: var(--text-secondary);
	}

	.confirm-created-code {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.25rem;
		padding: 1rem;
		width: 100%;
		background: var(--bg-page);
		border-radius: 8px;
	}

	.confirm-created-hint {
		margin: 0;
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	/* --- Generate confirmation ------------------------------------------------ */

	/* A pre-flight check before the irreversible open. The icon is tinted
	   with the brand so the panel reads as "action about to happen" rather
	   than a neutral prompt. */
	.confirm-generate {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.confirm-generate-icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 3rem;
		height: 3rem;
		border-radius: 50%;
		background: var(--brand);
		color: var(--on-brand);
	}

	.confirm-generate-text {
		margin: 0;
		font-size: 0.9375rem;
		color: var(--text-secondary);
		line-height: 1.4;
	}

	.confirm-generate-summary {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		padding: 0.875rem;
		background: var(--bg-page);
		border-radius: 8px;
	}

	.confirm-generate-row {
		display: flex;
		justify-content: space-between;
		gap: 0.75rem;
		font-size: 0.875rem;
	}

	.confirm-generate-label {
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.04em;
		font-size: 0.75rem;
		font-weight: 600;
	}

	.confirm-generate-hint {
		margin: 0;
		font-size: 0.8125rem;
		color: var(--warning-text);
	}

	@media (max-width: 640px) {
		.session-timeline {
			padding: 0.5rem;
		}

		.tl-label {
			flex: 0 0 2.5rem;
			font-size: 0.6875rem;
		}

		.tl-time {
			font-size: 0.6875rem;
		}

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
		.btn {
			transition: none;
		}
	}
</style>
