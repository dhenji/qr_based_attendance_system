"""The session plan: what a session for an offering inherits (D93).

One resolver, three call sites: the professor's course list, the
session-plan read endpoint, and the session-open write path. Every one of
them resolves the same way, so the form a professor sees and the row the
server stores cannot disagree.

What a session inherits from its offering:

* **the meeting** — which day and wall-clock time the class meets, and how
  long it runs. The meeting comes from the offering's active component for
  the session's type (D77); an offering with no components at all falls back
  to its own legacy schedule columns.
* **the next occurrence** — the first meeting whose *end* is still in the
  future. Today's class wins while it is still running; once it has ended the
  next meeting day is picked. Class times are wall clock ("09:00"), so they
  are interpreted in `INSTITUTION_TIMEZONE` and converted to UTC here.
* **the windows** — the offering's default present and late windows.
* **the classroom** — the component's room and coordinates, falling back to
  the offering's.
* **the radius** — payload -> offering -> app setting -> env.

What a session *cannot* inherit is the decision to move. A rescheduled class
is an explicit override carried on the session itself (D93); the offering's
recurring schedule is never touched by an open.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.timezones import resolve_timezone
from features.course.model import Course, CourseOffering, OfferingComponent
from features.system.constants import (
    SETTING_GEOFENCE_RADIUS,
    SETTING_LATE_WINDOW,
    SETTING_PRESENT_WINDOW,
)
from features.system.model import AppSetting
from shared.enums import SessionType
from shared.schedule import day_weekdays, meeting_length_minutes

# Where the plan came from.
# - "component": the offering's active component for this session type (D77).
# - "offering_legacy": the offering's own schedule columns, for a row with no
#   active components at all (the pre-D77 shape).
# - "course_default": no meeting is configured; the duration comes from the
#   course template.
# - "none": no meeting and no course duration either.
PlanSource = Literal["component", "offering_legacy", "course_default", "none"]

# How far ahead the resolver looks for the next meeting day. Seven days covers
# every weekday set, so a meeting always falls inside the window.
LOOKAHEAD_DAYS: int = 8

# The duration a session runs for when nothing else says. The last resort
# behind the course template's `session_duration_hours`.
FALLBACK_DURATION_MINUTES: int = 60


@dataclass(frozen=True)
class SessionPlan:
    """Everything a session inherits from its offering, already resolved."""

    source: PlanSource
    # The meeting, in the institution's local terms. `session_date` is the
    # next occurrence; the two times are the meeting's own wall clock.
    session_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    # The same meeting as UTC instants, ready to store.
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    # The meeting's length in minutes; 0 when no meeting is configured.
    meeting_minutes: int = 0
    duration_minutes: int = FALLBACK_DURATION_MINUTES
    present_window_minutes: int = 0
    late_window_minutes: int = 0
    classroom_name: str | None = None
    classroom_lat: float | None = None
    classroom_lng: float | None = None
    radius_meters: int = 50

    @property
    def has_meeting(self) -> bool:
        """Whether a scheduled meeting was found for this session."""
        return self.scheduled_start is not None


async def active_components(
    session: AsyncSession, offering_id: int
) -> Sequence[OfferingComponent]:
    """The offering's active meeting rows, oldest first."""
    return (
        await session.scalars(
            select(OfferingComponent)
            .where(
                OfferingComponent.offering_id == offering_id,
                OfferingComponent.is_active.is_(True),
            )
            .order_by(OfferingComponent.id)
        )
    ).all()


def _meeting_for(
    components: Sequence[OfferingComponent],
    offering: CourseOffering,
    session_type: SessionType,
) -> tuple[str, str, time, time] | None:
    """The meeting this session belongs to, as (source, days, start, end).

    An offering with active components has exactly one truth per type, and
    the offering-level schedule columns are only a mirror of the *lone*
    meeting (`course/service.py::_mirror_single_component`) — with two or
    more meetings they are stale, so they are never used as a fallback here.
    """
    if components:
        for component in components:
            if component.session_type == session_type.value:
                return (
                    "component",
                    component.schedule_days,
                    component.schedule_start_time,
                    component.schedule_end_time,
                )
        # The offering has meetings, but none of this type. There is no lab
        # schedule to inherit for a lab session, so there is no plan.
        return None

    # No active components: the pre-D77 shape, where the offering row itself
    # carries the schedule.
    return (
        "offering_legacy",
        offering.schedule_days,
        offering.schedule_start_time,
        offering.schedule_end_time,
    )


def next_meeting(
    *,
    days: str,
    start: time,
    end: time,
    now: datetime,
    zone: tzinfo,
) -> tuple[date, datetime, datetime] | None:
    """The next occurrence of a meeting, as (local date, UTC start, UTC end).

    The first candidate day whose meeting has *not* ended yet. A class that
    is still running today is today's; one that has already ended rolls to
    the next meeting day.

    `None` when the days string names no weekday, or when the end time is not
    after the start time (legacy free text the offering validators would
    have rejected) — there is nothing to schedule.
    """
    weekdays = day_weekdays(days)

    if not weekdays:
        return None

    if meeting_length_minutes(start, end) <= 0:
        return None

    local_today = now.astimezone(zone).date()

    for offset in range(LOOKAHEAD_DAYS):
        candidate = local_today + timedelta(days=offset)

        if candidate.weekday() not in weekdays:
            continue

        scheduled_start = datetime.combine(candidate, start, tzinfo=zone)
        scheduled_end = datetime.combine(candidate, end, tzinfo=zone)

        if scheduled_end.astimezone(timezone.utc) > now:
            return (
                candidate,
                scheduled_start.astimezone(timezone.utc),
                scheduled_end.astimezone(timezone.utc),
            )

    return None


async def _app_defaults(
    session: AsyncSession,
    settings: Settings,
) -> dict[str, int]:
    """The system-wide defaults, read from the `app_settings` table.

    These are the values an administrator edits in Admin -> System Settings:
    the geofence radius and the two attendance windows. The environment
    defaults are the fallback for a key that has no row.

    One query for all three keys. The rows used to be ignored entirely by the
    session path — `SessionService` read the environment default and never
    the `app_settings` row — so changing the radius in System Settings did
    nothing for new sessions, and the same was true of the window defaults.
    """
    rows = (
        await session.scalars(
            select(AppSetting).where(
                AppSetting.key.in_(
                    (
                        SETTING_GEOFENCE_RADIUS,
                        SETTING_PRESENT_WINDOW,
                        SETTING_LATE_WINDOW,
                    )
                )
            )
        )
    ).all()

    defaults: dict[str, int] = {
        SETTING_GEOFENCE_RADIUS: int(settings.default_geofence_radius_meters),
        SETTING_PRESENT_WINDOW: int(settings.default_present_window_minutes),
        SETTING_LATE_WINDOW: int(settings.default_late_window_minutes),
    }

    for row in rows:
        try:
            value = int(row.value)
        except (TypeError, ValueError):
            continue

        if value > 0:
            defaults[row.key] = value

    return defaults


async def resolve_session_plan(
    session: AsyncSession,
    *,
    offering: CourseOffering,
    course: Course | None,
    components: Sequence[OfferingComponent],
    session_type: SessionType,
    now: datetime,
    settings: Settings,
) -> SessionPlan:
    """Resolve everything a session for `offering` inherits.

    `components` are the offering's active meeting rows — pass them in
    rather than having the resolver query them, so the open path reads them
    once for both this and the weekly-hours gate.
    """
    zone = resolve_timezone(settings.institution_timezone, label="institution timezone")

    meeting = _meeting_for(components, offering, session_type)
    component = next(
        (
            row
            for row in components
            if row.session_type == session_type.value
        ),
        None,
    )

    session_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    meeting_minutes = 0

    if meeting is not None:
        _source, days, start, end = meeting
        meeting_minutes = meeting_length_minutes(start, end)
        found = next_meeting(
            days=days, start=start, end=end, now=now, zone=zone
        )

        if found is not None:
            session_date, scheduled_start, scheduled_end = found
            start_time = start
            end_time = end

    # The source describes what the professor is being scheduled against, so
    # it is only "component"/"offering_legacy" when an actual occurrence was
    # found. A meeting whose days name no weekday, or whose end is not after
    # its start, resolves to no occurrence and reads as no meeting at all.
    if scheduled_start is not None:
        source: PlanSource = (
            "component" if component is not None else "offering_legacy"
        )
    elif course is not None:
        source = "course_default"
    else:
        source = "none"

    # The duration follows the same rule as the source: a resolved meeting
    # supplies the class's own length, and anything else falls back to the
    # course template. The two can never disagree.
    duration_minutes = meeting_minutes if scheduled_start is not None else 0

    if not duration_minutes and course is not None:
        duration_minutes = int(float(course.session_duration_hours) * 60)

    if not duration_minutes:
        duration_minutes = FALLBACK_DURATION_MINUTES

    # The three session defaults resolve the same way: the offering's own
    # value, then the system-wide default an administrator edits in Admin ->
    # System Settings, then the environment default. A NULL on the offering
    # means "follow the system default" — the offering-level columns are
    # nullable for exactly that reason.
    defaults: dict[str, int] = await _app_defaults(session, settings)

    present_window = (
        offering.default_present_window_minutes
        or defaults[SETTING_PRESENT_WINDOW]
    )
    late_window = (
        offering.default_late_window_minutes or defaults[SETTING_LATE_WINDOW]
    )
    radius = (
        offering.default_classroom_radius_meters
        or defaults[SETTING_GEOFENCE_RADIUS]
    )

    classroom_name = (
        (component.classroom_name if component is not None else None)
        or offering.classroom_name
    )
    classroom_lat = (
        component.classroom_lat if component is not None else None
    )
    if classroom_lat is None:
        classroom_lat = offering.classroom_lat
    classroom_lng = (
        component.classroom_lng if component is not None else None
    )
    if classroom_lng is None:
        classroom_lng = offering.classroom_lng

    return SessionPlan(
        source=source,
        session_date=session_date,
        start_time=start_time,
        end_time=end_time,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        meeting_minutes=meeting_minutes,
        duration_minutes=duration_minutes,
        present_window_minutes=int(present_window),
        late_window_minutes=int(late_window),
        classroom_name=classroom_name,
        classroom_lat=classroom_lat,
        classroom_lng=classroom_lng,
        radius_meters=int(radius),
    )
