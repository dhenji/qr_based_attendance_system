from __future__ import annotations

from pydantic import BaseModel, Field

from features.attendance.schema import RecentScanItem


class TodayScheduleEntry(BaseModel):
    """One of today's classes for the student dashboard.

    Mirrors `ScheduleItem`, which is what `GET /student/schedule` returns: the
    dashboard filters that response down to today rather than re-querying, so a
    class shows the same classroom and professor the student already sees
    elsewhere. `schedule_days` and the two times travel along for the same
    reason — a dashboard tile is not a place to hide detail.
    """

    offering_id: int
    course_code: str
    course_name: str
    schedule_days: str
    schedule_start_time: str
    schedule_end_time: str
    classroom_name: str | None = None
    professor_name: str | None = None


class RecentActivityEntry(BaseModel):
    """One recent scan row for the student dashboard.

    A structural subset of `HistoryItem`: the dashboard only needs enough to
    render a feed line, and keeping it separate means the tile cannot drift into
    showing fields the history endpoint does not actually return.
    """

    id: int
    session_id: int
    course_code: str
    course_name: str
    status: str
    scanned_at: str


class StudentDashboardResponse(BaseModel):
    """`GET /student/dashboard` — the student's own numbers, nothing else.

    `compliance_rate` is the same number `GET /student/attendance/history`
    reports in its summary, taken from there rather than recomputed: two code
    paths computing "compliance" is how they come to disagree.
    """

    compliance_rate: float = 0.0
    scans_today: int = 0
    total_scans: int = 0
    today_schedule: list[TodayScheduleEntry] = Field(default_factory=list)
    recent_activity: list[RecentActivityEntry] = Field(default_factory=list)


class ProfessorTodaySession(BaseModel):
    """One of today's sessions, as the contract's `{offering, scanned, enrolled}`.

    `offering_id` and `session_id` come from `SessionOfferingTile`, which splits
    the contract's bare `offering` because a tile is keyed by session and the
    client needs both to link onward.
    """

    session_id: int
    offering_id: int
    scanned: int
    enrolled: int


class ProfessorDashboardResponse(BaseModel):
    """`GET /professor/dashboard` — today, plus the term-rate headline.

    `sessions_completed` counts today's sessions that have already closed
    (`expires_at` in the past), since sessions carry no status column; see
    `SessionService._session_status`.
    """

    sessions_today: int = 0
    sessions_completed: int = 0
    total_students: int = 0
    avg_rate: float = 0.0
    today_sessions: list[ProfessorTodaySession] = Field(default_factory=list)


class AdminDashboardResponse(BaseModel):
    """`GET /admin/dashboard` — roster sizes, today's volume, the sync backlog.

    `student_count` / `professor_count` / `program_count` are roster sizes
    (`is_active` rows), deliberately *not* the analytics overview's
    `total_students`, which counts students enrolled in a session in scope.
    Conflating the two would make the dashboard disagree with the admin list
    page it sits above.
    """

    student_count: int = 0
    professor_count: int = 0
    program_count: int = 0
    avg_rate: float = 0.0
    scans_today: int = 0
    pending_sync: int = 0
    recent_scans: list[RecentScanItem] = Field(default_factory=list)