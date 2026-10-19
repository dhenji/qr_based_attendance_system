"""The human reading of an audit row.

ADR-064 made the audit endpoints return the stored row unaltered: "Nothing
is derived: no `actor_name` join, no `category` mapping." That was the
right call for the STORED row — the evidence should be the evidence — but it
left the read model to every client, and the clients disagreed with the
contract (ADR-086).

This module is the read model. It turns a stored row into what an
administrator actually needs to answer "who changed what, when, and can I
prove it?":

- an ACTOR: a name and a role, not a ``users.id``;
- a SUBJECT: the record's name, not ``course_offering #12``;
- a SUMMARY: one sentence;
- CHANGES: a field-level diff, not a JSON blob.

Two rules make it hold up as the trail grows:

**The snapshot first.** Every ``_<entity>_snapshot`` method on the server
already carries the human identifiers — a program snapshot has ``code`` and
``name``, a course snapshot has ``course_code`` and ``course_name``, a
student snapshot has ``student_id`` and the names. So the label is read out
of ``new_value ?? old_value`` and a database lookup is only the fallback.

That is not just an optimisation. A hard-deleted program has no row left to
join against: its audit snapshot is the only surviving record of it. A join
returns null; the snapshot returns "BSCS · Bachelor of Science in Computer
Science". The snapshot is the more durable evidence, so it is read first.

**Batched lookups.** The rows on one page are resolved together — one query
per table, not one per row — so the cost of a page is a small constant
rather than a multiple of the page size.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from features.auth.model import User
from features.course.model import Course, CourseOffering
from features.professor.model import Professor
from features.program.model import Program, YearLevel
from features.student.model import Student
from features.system.model import AuditLog
from shared.enums import AuditAction, AuditEntity

# --- Vocabulary -------------------------------------------------------------

# The human name of each snapshot field. Keyed by the field name the
# server's `_<entity>_snapshot` methods use, so a field nobody has mapped
# yet renders under its own name — visible, not silent.
FIELD_LABELS: dict[str, str] = {
    # program
    "code": "Code",
    "name": "Name",
    "description": "Description",
    "total_years": "Years in the program",
    "is_active": "Status",
    # year level
    "program_id": "Program",
    "year_number": "Year number",
    "label": "Label",
    "term_structure": "Terms",
    "sort_order": "Order",
    # course
    "course_code": "Course code",
    "course_name": "Course name",
    "units": "Units",
    "session_duration_hours": "Session length (hours)",
    # offering
    "course_id": "Course",
    "year_level_id": "Year level",
    "semester": "Term",
    "academic_year": "Academic year",
    "sessions_per_week": "Sessions per week",
    "schedule_days": "Meeting days",
    "schedule_start_time": "Starts",
    "schedule_end_time": "Ends",
    "classroom_name": "Classroom",
    "classroom_lat": "Latitude",
    "classroom_lng": "Longitude",
    "default_present_window_minutes": "Present window (min)",
    "default_late_window_minutes": "Late window (min)",
    # offering component
    "offering_id": "Offering",
    "session_type": "Session type",
    # student
    "student_id": "Student",
    "first_name": "First name",
    "last_name": "Last name",
    "email": "Email",
    "section": "Section",
    "face_enrolled_at": "Face enrolled at",
    # professor
    "department": "Department",
    # session
    "professor_id": "Professor",
    "session_code": "Session code",
    "scheduled_start_time": "Scheduled start",
    "scheduled_end_time": "Scheduled end",
    "expires_at": "Expires at",
    # account
    "failed_login_attempts": "Failed sign-in attempts",
    "is_locked": "Account locked",
    "locked_at": "Locked at",
    "must_change_password": "Must change password",
    "role": "Role",
    # assignment
    "is_primary": "Role",
    "effective_from": "Effective from",
    "effective_to": "Effective to",
    # excuse
    "initiated_by": "Initiated by",
    "initiated_via": "Submitted via",
    "reason": "Reason",
    "attachment_count": "Attachments",
    "status": "Status",
    "reviewed_by": "Reviewed by",
    "review_notes": "Review notes",
    # backup
    "kind": "Backup type",
    "filename": "File",
    "size_bytes": "File size",
    "storage_backend": "Storage",
    "sha256": "Checksum",
    # batches
    "imported": "Imported",
    "duplicates": "Skipped (already existed)",
    "errors": "Errors",
    "enrolled": "Enrolled",
    "skipped": "Skipped",
    "processed": "Processed",
    "succeeded": "Succeeded",
    "failed": "Failed",
    "removed": "Removed",
    "otp_codes": "Expired sign-in codes",
    "sync_queue": "Finished sync rows",
    # attendance review
    "validation_status": "Attendance status",
    "review_note": "Review note",
    # face template
    "face_embedding_version": "Face template version",
    # system settings
    "present_window_default": "Present window (min)",
    "late_window_default": "Late window (min)",
    "geofence_default_radius": "Geofence radius (m)",
    "backup_retention_daily": "Daily backups kept",
    "backup_retention_monthly": "Monthly backups kept",
}

# The verb each action is read as. One table, so the summary sentence, the
# client's chip and the CSV export cannot disagree about it.
ACTION_LABELS: dict[str, str] = {
    AuditAction.CREATE: "Created",
    AuditAction.UPDATE: "Updated",
    AuditAction.ARCHIVE: "Archived",
    AuditAction.DELETE: "Deleted",
    AuditAction.IMPORT: "Imported",
    AuditAction.ENROLL: "Enrolled",
    AuditAction.UNENROLL: "Removed",
    AuditAction.ASSIGN: "Assigned",
    AuditAction.REASSIGN: "Reassigned",
    AuditAction.REOPEN: "Reopened",
    AuditAction.UNASSIGN: "Assignment ended",
    AuditAction.OPEN: "Opened",
    AuditAction.CLOSE: "Closed",
    AuditAction.APPROVE: "Approved",
    AuditAction.REJECT: "Rejected",
    AuditAction.REVOKE: "Revoked",
    AuditAction.LOCK: "Locked",
    AuditAction.UNLOCK: "Unlocked",
    AuditAction.LOGIN_FAILED: "Sign-in failed",
    AuditAction.PASSWORD_RESET: "Password reset",
}

# The human name of each entity type.
ENTITY_LABELS: dict[str, str] = {
    AuditEntity.PROGRAM: "Program",
    AuditEntity.YEAR_LEVEL: "Year level",
    AuditEntity.COURSE: "Course",
    AuditEntity.COURSE_OFFERING: "Course offering",
    AuditEntity.OFFERING_COMPONENT: "Schedule component",
    AuditEntity.STUDENT: "Student",
    AuditEntity.PROFESSOR: "Professor",
    AuditEntity.ENROLLMENT: "Enrollment",
    AuditEntity.COURSE_PROFESSOR: "Teaching assignment",
    AuditEntity.EXCUSE: "Excuse request",
    AuditEntity.SESSION: "Class session",
    AuditEntity.FACE_ENROLLMENT: "Face template",
    AuditEntity.ATTENDANCE_RECORD: "Attendance record",
    AuditEntity.BACKUP: "Backup",
    AuditEntity.APP_SETTING: "System setting",
    AuditEntity.USER: "User account",
    AuditEntity.MAINTENANCE: "Maintenance run",
}

# This system's meeting-day letters. `T` is Tuesday and `H` is Thursday —
# the conventional initials do not apply here
# (`features/student/service.py::_meets_on`). Rendering "MWF" as
# Mon/Wed/Fri by accident would put every meeting on the wrong day.
DAY_INITIALS: dict[str, str] = {
    "M": "Mon",
    "T": "Tue",
    "W": "Wed",
    "H": "Thu",
    "F": "Fri",
    "S": "Sat",
    "U": "Sun",
}

# --- Value formatting -------------------------------------------------------


def _title_case(value: str) -> str:
    return value[:1].upper() + value[1:].replace("_", " ")


def _time_only(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return "—"
    return value[:5] if len(value) >= 5 else value


def _date_text(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return "—"
    return value[:10]


def _term_text(value: Any) -> str:
    if not isinstance(value, dict):
        return "—"
    terms = value.get("terms")
    if not isinstance(terms, list):
        return "—"
    labels = [
        str(term.get("label") or term.get("code") or "")
        for term in terms
        if isinstance(term, dict)
    ]
    labels = [label for label in labels if label]
    if not labels:
        return "No terms"
    return f"{len(labels)} term{'' if len(labels) == 1 else 's'}: {', '.join(labels)}"


def _days_text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "—"
    days = [DAY_INITIALS[letter] for letter in value.strip().upper() if letter in DAY_INITIALS]
    return ", ".join(days) if days else value


def _status_text(value: Any) -> str:
    if not isinstance(value, str):
        return "—"
    known = {
        "present": "Present",
        "late": "Late",
        "absent": "Absent",
        "excused": "Excused",
        "pending": "Pending",
        "rejected": "Rejected",
        "approved": "Approved",
        "active": "Active",
        "inactive": "Inactive",
        "completed": "Completed",
        "failed": "Failed",
        "started": "Started",
    }
    return known.get(value, _title_case(value))


def _role_text(value: Any) -> str:
    if not isinstance(value, str):
        return "—"
    known = {
        "super_admin": "Super admin",
        "admin": "Admin",
        "professor": "Professor",
        "student": "Student",
        "system": "System",
    }
    return known.get(value, _title_case(value))


def _bytes_text(value: Any) -> str:
    if not isinstance(value, (int, float)) or value <= 0:
        return "—"
    units = ["B", "KB", "MB", "GB"]
    size = float(value)
    unit = 0
    while size >= 1024 and unit < len(units) - 1:
        size /= 1024
        unit += 1
    return f"{size:.0f} {units[unit]}" if unit == 0 else f"{size:.1f} {units[unit]}"


def format_value(field: str, value: Any) -> str:
    """One snapshot value, as something an administrator can read."""
    if field == "is_active":
        return "Active" if value is True else "Archived" if value is False else "—"
    if field == "is_locked":
        return "Locked" if value is True else "Not locked" if value is False else "—"
    if field == "must_change_password":
        if value is True:
            return "Yes — must change at next sign-in"
        return "No" if value is False else "—"
    if field == "enrolled":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        return "Yes" if value is True else "No" if value is False else "—"
    if field == "validation_status" or field == "status":
        return _status_text(value)
    if field == "role":
        return _role_text(value)
    if field == "initiated_by":
        return {"professor": "Professor", "student": "Student"}.get(value, "—")
    if field == "initiated_via":
        return {
            "quick_excuse": "Quick excuse",
            "prof_with_evidence": "With evidence",
            "request": "Request",
        }.get(value, "—")
    if field == "session_type":
        return {"lecture": "Lecture", "lab": "Laboratory"}.get(value, "—")
    if field == "schedule_days":
        return _days_text(value)
    if field in ("schedule_start_time", "schedule_end_time"):
        return _time_only(value)
    if field in (
        "scheduled_start_time",
        "scheduled_end_time",
        "expires_at",
        "locked_at",
        "face_enrolled_at",
    ):
        return value if isinstance(value, str) and value else "—"
    if field in ("effective_from", "effective_to"):
        return _date_text(value)
    if field == "term_structure":
        return _term_text(value)
    if field == "size_bytes":
        return _bytes_text(value)
    if field == "sha256":
        if isinstance(value, str) and len(value) > 16:
            return f"{value[:16]}…"
        return str(value) if value else "—"
    if field == "kind":
        return {"full": "Full database", "analytics": "Analytics"}.get(value, "—")
    if field == "storage_backend":
        return {"local": "Local", "s3": "S3"}.get(value, "—")
    if field == "total_years":
        return f"{value} years" if isinstance(value, int) else "—"
    if field == "session_duration_hours":
        if isinstance(value, (int, float)):
            return f"{value} {'hour' if value == 1 else 'hours'}"
        return "—"
    if field in (
        "default_present_window_minutes",
        "default_late_window_minutes",
        "present_window_default",
        "late_window_default",
    ):
        return f"{value} min" if isinstance(value, int) else "—"
    if field == "geofence_default_radius":
        return f"{value} m" if isinstance(value, int) else "—"
    if field == "is_primary":
        return "Primary" if value is True else "Assistant" if value is False else "—"
    if field == "year_number":
        return f"Year {value}" if isinstance(value, int) else "—"
    if field == "attachment_count":
        if isinstance(value, int):
            return f"{value} attachment{'' if value == 1 else 's'}"
        return "—"
    if field == "face_embedding_version":
        return f"v{value}" if isinstance(value, int) else "—"
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value if value else "—"
    return str(value)


# --- The diff ----------------------------------------------------------------


@dataclass(frozen=True)
class AuditChange:
    field: str
    label: str
    before: str
    after: str


def _deep_equal(left: Any, right: Any) -> bool:
    if left == right:
        return True
    if left is None or right is None or not isinstance(left, (dict, list)) or not isinstance(right, (dict, list)):
        return False
    return str(left) == str(right)


def diff_snapshots(
    old_value: dict[str, Any] | None,
    new_value: dict[str, Any] | None,
) -> list[AuditChange]:
    """The field-level difference between two snapshots.

    A create has no ``old_value`` and a delete has no ``new_value``, so both
    are reported as one-sided changes: the field reads "— → Active" rather
    than an empty cell. A field that was never set is left out entirely.
    """
    before = old_value or {}
    after = new_value or {}
    keys = sorted(set(before) | set(after))
    changes: list[AuditChange] = []
    for key in keys:
        old = before.get(key)
        new = after.get(key)
        if old_value is not None and new_value is not None and _deep_equal(old, new):
            continue
        if old_value is None and new is None:
            continue
        if new_value is None and old is None:
            continue
        changes.append(
            AuditChange(
                field=key,
                label=FIELD_LABELS.get(key, key.replace("_", " ")),
                before="—" if old_value is None else format_value(key, old),
                after="—" if new_value is None else format_value(key, new),
            )
        )
    return changes


# --- The resolved view -------------------------------------------------------


@dataclass
class AuditActor:
    kind: str  # "user" | "anonymous"
    id: int | None = None
    name: str = "No signed-in user"
    email: str | None = None
    role: str | None = None


@dataclass
class _Account:
    """A `users` row with the name its roster carries, if any.

    The `users` table has no name columns — a person's name lives on their
    student or professor row — so the name is outer-joined in, exactly as
    `features/admin/service.py::_users_stmt` does it.
    """

    id: int
    email: str
    role: str
    first_name: str | None = None
    last_name: str | None = None

    @property
    def name(self) -> str:
        return _full_name(self.first_name, self.last_name) or self.email


@dataclass
class AuditSubject:
    type: str
    id: int | None = None
    label: str = ""
    sublabel: str | None = None


@dataclass
class AuditRowView:
    actor: AuditActor
    subject: AuditSubject
    summary: str
    action_label: str
    changes: list[AuditChange] = field(default_factory=list)


def _full_name(first: str | None, last: str | None) -> str:
    return " ".join(part for part in (first, last) if part and part.strip()).strip()


class AuditLabelResolver:
    """Resolves the human reading of a page of audit rows.

    The lookups are batched: one query per table for the whole page, and a
    table is only queried when some row actually needs it.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users: dict[int, _Account] = {}
        self._programs: dict[int, Program] = {}
        self._year_levels: dict[int, YearLevel] = {}
        self._courses: dict[int, Course] = {}
        self._offerings: dict[int, CourseOffering] = {}
        self._students: dict[int, Student] = {}
        self._professors: dict[int, Professor] = {}

    async def resolve(self, rows: Sequence[AuditLog]) -> list[AuditRowView]:
        await self._load(rows)
        return [self._view(row) for row in rows]

    # -- loading ---------------------------------------------------------

    async def _load(self, rows: Sequence[AuditLog]) -> None:
        user_ids: set[int] = {r.performed_by for r in rows if r.performed_by is not None}
        program_ids: set[int] = set()
        year_level_ids: set[int] = set()
        course_ids: set[int] = set()
        offering_ids: set[int] = set()
        student_ids: set[int] = set()
        professor_ids: set[int] = set()

        for row in rows:
            if row.entity_type == AuditEntity.USER and row.entity_id is not None:
                user_ids.add(row.entity_id)
            snapshot = row.new_value or row.old_value or {}
            if row.entity_type == AuditEntity.YEAR_LEVEL:
                program_ids.update(_ids(snapshot.get("program_id")))
            elif row.entity_type == AuditEntity.COURSE_OFFERING:
                course_ids.update(_ids(snapshot.get("course_id")))
                program_ids.update(_ids(snapshot.get("program_id")))
                year_level_ids.update(_ids(snapshot.get("year_level_id")))
            elif row.entity_type in (
                AuditEntity.OFFERING_COMPONENT,
                AuditEntity.SESSION,
                AuditEntity.ENROLLMENT,
            ):
                offering_ids.update(_ids(snapshot.get("offering_id")))
            elif row.entity_type == AuditEntity.COURSE_PROFESSOR:
                offering_ids.update(_ids(snapshot.get("offering_id")))
                professor_ids.update(_ids(snapshot.get("professor_id")))
            elif row.entity_type == AuditEntity.EXCUSE:
                student_ids.update(_ids(snapshot.get("student_id")))
            elif row.entity_type == AuditEntity.FACE_ENROLLMENT:
                # The id here is a STUDENT id: a face template lives on the
                # student row, so that is its id space.
                student_ids.update(_ids(row.entity_id))

        if user_ids:
            self._users = {
                row[0].id: _Account(
                    id=row[0].id,
                    email=row[0].email,
                    role=row[0].role,
                    first_name=row[1] or row[3],
                    last_name=row[2] or row[4],
                )
                for row in (
                    await self._session.execute(
                        select(
                            User,
                            Student.first_name,
                            Student.last_name,
                            Professor.first_name,
                            Professor.last_name,
                        )
                        .outerjoin(Student, Student.user_id == User.id)
                        .outerjoin(Professor, Professor.user_id == User.id)
                        .where(User.id.in_(user_ids))
                    )
                ).all()
            }
        if program_ids:
            self._programs = {
                p.id: p
                for p in (
                    await self._session.scalars(
                        select(Program).where(Program.id.in_(program_ids))
                    )
                ).all()
            }
        if year_level_ids:
            self._year_levels = {
                y.id: y
                for y in (
                    await self._session.scalars(
                        select(YearLevel).where(YearLevel.id.in_(year_level_ids))
                    )
                ).all()
            }
        if course_ids:
            self._courses = {
                c.id: c
                for c in (
                    await self._session.scalars(
                        select(Course).where(Course.id.in_(course_ids))
                    )
                ).all()
            }
        if offering_ids:
            self._offerings = {
                o.id: o
                for o in (
                    await self._session.scalars(
                        select(CourseOffering).where(
                            CourseOffering.id.in_(offering_ids)
                        )
                    )
                ).all()
            }
            # An offering's own course, program and year level are needed to
            # name it, so they are collected after the offerings are known.
            for offering in self._offerings.values():
                course_ids.add(offering.course_id)
                program_ids.add(offering.program_id)
                year_level_ids.add(offering.year_level_id)
        if course_ids and not self._courses:
            self._courses = {
                c.id: c
                for c in (
                    await self._session.scalars(
                        select(Course).where(Course.id.in_(course_ids))
                    )
                ).all()
            }
        if program_ids and not self._programs:
            self._programs = {
                p.id: p
                for p in (
                    await self._session.scalars(
                        select(Program).where(Program.id.in_(program_ids))
                    )
                ).all()
            }
        if year_level_ids and not self._year_levels:
            self._year_levels = {
                y.id: y
                for y in (
                    await self._session.scalars(
                        select(YearLevel).where(YearLevel.id.in_(year_level_ids))
                    )
                ).all()
            }
        if student_ids:
            self._students = {
                s.id: s
                for s in (
                    await self._session.scalars(
                        select(Student).where(Student.id.in_(student_ids))
                    )
                ).all()
            }
        if professor_ids:
            self._professors = {
                p.id: p
                for p in (
                    await self._session.scalars(
                        select(Professor).where(Professor.id.in_(professor_ids))
                    )
                ).all()
            }

    # -- building --------------------------------------------------------

    def _actor(self, row: AuditLog) -> AuditActor:
        if row.performed_by is None:
            # Nobody was authenticated: an anonymous lockout, or an
            # unattended run.
            return AuditActor(kind="anonymous")
        user = self._users.get(row.performed_by)
        if user is None:
            return AuditActor(
                kind="user",
                id=row.performed_by,
                name=f"User #{row.performed_by}",
            )
        return AuditActor(
            kind="user",
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
        )

    def _course_label(self, course_id: Any) -> str:
        course = self._courses.get(course_id) if isinstance(course_id, int) else None
        if course is None:
            return f"Course #{course_id}"
        return f"{course.course_code} · {course.course_name}"

    def _program_label(self, program_id: Any) -> str:
        program = self._programs.get(program_id) if isinstance(program_id, int) else None
        return program.code if program is not None else f"Program #{program_id}"

    def _year_label(self, year_level_id: Any) -> str:
        level = (
            self._year_levels.get(year_level_id)
            if isinstance(year_level_id, int)
            else None
        )
        return level.label if level is not None else f"Year level #{year_level_id}"

    def _offering_headline(self, offering: CourseOffering) -> str:
        return self._course_label(offering.course_id)

    def _offering_caption(self, offering: CourseOffering) -> str:
        return (
            f"{self._program_label(offering.program_id)} "
            f"{self._year_label(offering.year_level_id)} · "
            f"{offering.semester} Sem · {offering.academic_year}"
        )

    def _component_subject(
        self, entity_type: str, entity_id: int | None, snapshot: dict[str, Any]
    ) -> AuditSubject:
        """A schedule component of an offering."""
        offering_id = snapshot.get("offering_id")
        offering = (
            self._offerings.get(offering_id) if isinstance(offering_id, int) else None
        )
        kind = "Laboratory" if snapshot.get("session_type") == "lab" else "Lecture"
        caption = " · ".join(
            part
            for part in (
                format_value("schedule_days", snapshot.get("schedule_days")),
                f"{format_value('schedule_start_time', snapshot.get('schedule_start_time'))}"
                f"–{format_value('schedule_end_time', snapshot.get('schedule_end_time'))}",
                str(snapshot.get("classroom_name") or ""),
            )
            if part and part != "—"
        )
        return AuditSubject(
            type=entity_type,
            id=entity_id,
            label=(
                f"{self._offering_headline(offering)} — {kind} component"
                if offering is not None
                else f"Schedule component of offering #{offering_id}"
            ),
            sublabel=caption or None,
        )

    def _subject(self, row: AuditLog) -> AuditSubject:
        snapshot = row.new_value or row.old_value or {}
        entity_type = row.entity_type
        entity_id = row.entity_id

        if entity_type == AuditEntity.PROGRAM:
            if entity_id is None:
                return AuditSubject(
                    type=entity_type,
                    label="Program import",
                    sublabel=_import_caption(snapshot),
                )
            code = str(snapshot.get("code") or "")
            name = str(snapshot.get("name") or "")
            return AuditSubject(
                type=entity_type,
                id=entity_id,
                label=f"{code} · {name}" if code and name else code or name or f"Program #{entity_id}",
                sublabel=str(snapshot.get("description") or "") or None,
            )

        if entity_type == AuditEntity.YEAR_LEVEL:
            label = str(snapshot.get("label") or "")
            program_id = snapshot.get("program_id")
            program = (
                self._programs.get(program_id) if isinstance(program_id, int) else None
            )
            return AuditSubject(
                type=entity_type,
                id=entity_id,
                label=(
                    f"{program.code} · {label}"
                    if program is not None and label
                    else label or f"Year level #{entity_id}"
                ),
                sublabel=program.name if program is not None else None,
            )

        if entity_type == AuditEntity.COURSE:
            if entity_id is None:
                return AuditSubject(
                    type=entity_type,
                    label="Course import",
                    sublabel=_import_caption(snapshot),
                )
            code = str(snapshot.get("course_code") or "")
            name = str(snapshot.get("course_name") or "")
            units = snapshot.get("units")
            return AuditSubject(
                type=entity_type,
                id=entity_id,
                label=(
                    f"{code} · {name}"
                    if code and name
                    else code or name or f"Course #{entity_id}"
                ),
                sublabel=f"{units} units" if isinstance(units, int) else None,
            )

        if entity_type == AuditEntity.COURSE_OFFERING:
            # LEGACY: before ADR-086 a schedule component was written as
            # `course_offering` with the OFFERING's id, so the member had two
            # id spaces. A component's snapshot carries `session_type` and no
            # `semester`; an offering's is the other way round. Old rows are
            # read as what they are rather than migrated.
            if (
                snapshot.get("session_type") is not None
                and snapshot.get("semester") is None
            ):
                return self._component_subject(entity_type, entity_id, snapshot)
            course_id = snapshot.get("course_id")
            program_id = snapshot.get("program_id")
            year_level_id = snapshot.get("year_level_id")
            semester = str(snapshot.get("semester") or "")
            academic_year = str(snapshot.get("academic_year") or "")
            caption = " · ".join(
                part
                for part in (
                    self._program_label(program_id)
                    if program_id is not None
                    else "",
                    self._year_label(year_level_id)
                    if year_level_id is not None
                    else "",
                    f"{semester} Sem" if semester else "",
                    academic_year,
                )
                if part
            )
            return AuditSubject(
                type=entity_type,
                id=entity_id,
                label=self._course_label(course_id),
                sublabel=caption or None,
            )

        if entity_type == AuditEntity.OFFERING_COMPONENT:
            return self._component_subject(entity_type, entity_id, snapshot)

        if entity_type == AuditEntity.STUDENT:
            if entity_id is None:
                return AuditSubject(
                    type=entity_type,
                    label="Student import",
                    sublabel=_import_caption(snapshot),
                )
            number = str(snapshot.get("student_id") or "")
            name = _full_name(
                str(snapshot.get("first_name") or ""),
                str(snapshot.get("last_name") or ""),
            )
            return AuditSubject(
                type=entity_type,
                id=entity_id,
                label=(
                    f"{number} · {name}"
                    if number and name
                    else number or name or f"Student #{entity_id}"
                ),
                sublabel=str(snapshot.get("email") or "") or None,
            )

        if entity_type == AuditEntity.PROFESSOR:
            if entity_id is None:
                return AuditSubject(
                    type=entity_type,
                    label="Professor import",
                    sublabel=_import_caption(snapshot),
                )
            name = _full_name(
                str(snapshot.get("first_name") or ""),
                str(snapshot.get("last_name") or ""),
            )
            return AuditSubject(
                type=entity_type,
                id=entity_id,
                label=name or f"Professor #{entity_id}",
                sublabel=str(snapshot.get("email") or "")
                or str(snapshot.get("department") or "")
                or None,
            )

        if entity_type == AuditEntity.ENROLLMENT:
            offering_id = snapshot.get("offering_id")
            offering = (
                self._offerings.get(offering_id)
                if isinstance(offering_id, int)
                else None
            )
            if entity_id is None:
                return AuditSubject(
                    type=entity_type,
                    label=(
                        f"Enrolled students in {self._offering_headline(offering)}"
                        if offering is not None
                        else "Bulk enrollment"
                    ),
                    sublabel=(
                        self._offering_caption(offering)
                        if offering is not None
                        else f"{snapshot.get('enrolled', 0)} enrolled · "
                        f"{snapshot.get('skipped', 0)} skipped"
                    ),
                )
            number = str(snapshot.get("student_id") or "")
            return AuditSubject(
                type=entity_type,
                id=entity_id,
                label=(
                    f"{number} in {self._offering_headline(offering)}"
                    if number and offering is not None
                    else number or f"Enrollment #{entity_id}"
                ),
                sublabel=(
                    self._offering_caption(offering) if offering is not None else None
                ),
            )

        if entity_type == AuditEntity.COURSE_PROFESSOR:
            offering_id = snapshot.get("offering_id")
            professor_id = snapshot.get("professor_id")
            offering = (
                self._offerings.get(offering_id)
                if isinstance(offering_id, int)
                else None
            )
            professor = (
                self._professors.get(professor_id)
                if isinstance(professor_id, int)
                else None
            )
            professor_name = (
                _full_name(professor.first_name, professor.last_name)
                if professor is not None
                else f"Professor #{professor_id}"
            )
            course = (
                self._offering_headline(offering)
                if offering is not None
                else f"offering #{offering_id}"
            )
            role = "Primary" if snapshot.get("is_primary") is True else "Assistant"
            effective_from = snapshot.get("effective_from")
            effective_to = snapshot.get("effective_to")
            caption = " · ".join(
                part
                for part in (
                    role,
                    f"from {_date_text(effective_from)}" if effective_from else "",
                    f"to {_date_text(effective_to)}" if effective_to else "",
                )
                if part
            )
            return AuditSubject(
                type=entity_type,
                id=entity_id,
                label=f"{professor_name} → {course}",
                sublabel=caption or None,
            )

        if entity_type == AuditEntity.EXCUSE:
            student_id = snapshot.get("student_id")
            student = (
                self._students.get(student_id) if isinstance(student_id, int) else None
            )
            if student is not None:
                label = f"{_full_name(student.first_name, student.last_name)} ({student.student_id})"
            else:
                label = f"Excuse request #{entity_id}"
            return AuditSubject(
                type=entity_type,
                id=entity_id,
                label=label,
                sublabel=str(snapshot.get("reason") or "") or None,
            )

        if entity_type == AuditEntity.SESSION:
            offering_id = snapshot.get("offering_id")
            offering = (
                self._offerings.get(offering_id)
                if isinstance(offering_id, int)
                else None
            )
            code = str(snapshot.get("session_code") or "")
            return AuditSubject(
                type=entity_type,
                id=entity_id,
                label=code or f"Session #{entity_id}",
                sublabel=(
                    self._offering_caption(offering)
                    if offering is not None
                    else format_value("session_type", snapshot.get("session_type"))
                ),
            )

        if entity_type == AuditEntity.FACE_ENROLLMENT:
            student = (
                self._students.get(entity_id) if isinstance(entity_id, int) else None
            )
            return AuditSubject(
                type=entity_type,
                id=entity_id,
                label=(
                    f"Face template — {_full_name(student.first_name, student.last_name)}"
                    if student is not None
                    else f"Face template #{entity_id}"
                ),
                sublabel=student.student_id if student is not None else None,
            )

        if entity_type == AuditEntity.ATTENDANCE_RECORD:
            return AuditSubject(
                type=entity_type,
                id=entity_id,
                label=f"Attendance record #{entity_id}",
                sublabel=format_value(
                    "validation_status", snapshot.get("validation_status")
                ),
            )

        if entity_type == AuditEntity.BACKUP:
            filename = str(snapshot.get("filename") or "")
            caption = " · ".join(
                part
                for part in (
                    format_value("kind", snapshot.get("kind")),
                    format_value("size_bytes", snapshot.get("size_bytes")),
                    format_value("status", snapshot.get("status")),
                )
                if part and part != "—"
            )
            return AuditSubject(
                type=entity_type,
                id=entity_id,
                label=filename or f"Backup #{entity_id}",
                sublabel=caption or None,
            )

        if entity_type == AuditEntity.APP_SETTING:
            names = [FIELD_LABELS.get(key, key) for key in snapshot]
            return AuditSubject(
                type=entity_type,
                id=entity_id,
                label="System settings",
                sublabel=", ".join(names) or None,
            )

        if entity_type == AuditEntity.USER:
            user = self._users.get(entity_id) if isinstance(entity_id, int) else None
            email = str(snapshot.get("email") or "") or (user.email if user else "")
            role = snapshot.get("role") or (user.role if user else None)
            return AuditSubject(
                type=entity_type,
                id=entity_id,
                label=email or f"User #{entity_id}",
                sublabel=format_value("role", role) if role else None,
            )

        if entity_type == AuditEntity.MAINTENANCE:
            is_sync = "processed" in snapshot
            is_cleanup = "removed" in snapshot
            caption = " · ".join(
                f"{FIELD_LABELS.get(key, key)}: {format_value(key, value)}"
                for key, value in snapshot.items()
            )
            return AuditSubject(
                type=entity_type,
                id=entity_id,
                label=(
                    "Offline sync reconciliation"
                    if is_sync
                    else "Expired-data cleanup"
                    if is_cleanup
                    else "Maintenance run"
                ),
                sublabel=caption or None,
            )

        return AuditSubject(
            type=entity_type,
            id=entity_id,
            label=f"{ENTITY_LABELS.get(entity_type, entity_type)} #{entity_id}",
        )

    def _view(self, row: AuditLog) -> AuditRowView:
        actor = self._actor(row)
        subject = self._subject(row)
        changes = diff_snapshots(row.old_value, row.new_value)
        verb = ACTION_LABELS.get(row.action, row.action.replace("_", " "))
        if row.action == AuditAction.ENROLL:
            summary = (
                subject.label
                if subject.label.startswith("Enrolled")
                else f"Enrolled students in {subject.label}"
            )
        elif row.action == AuditAction.UNENROLL:
            summary = f"Removed {subject.label}"
        elif row.action == AuditAction.IMPORT:
            summary = subject.label
        elif row.action == AuditAction.UNASSIGN:
            summary = f"Ended {subject.label}"
        elif len(changes) == 1:
            summary = f"{verb} {subject.label} — {changes[0].label}"
        else:
            summary = f"{verb} {subject.label}"
        return AuditRowView(
            actor=actor,
            subject=subject,
            summary=summary,
            action_label=verb,
            changes=changes,
        )


def _import_caption(snapshot: dict[str, Any]) -> str | None:
    imported = snapshot.get("imported")
    if not isinstance(imported, int):
        return None
    duplicates = snapshot.get("duplicates")
    errors = snapshot.get("errors")
    return (
        f"{imported} imported · {duplicates if isinstance(duplicates, int) else 0} "
        f"already existed · {errors if isinstance(errors, int) else 0} errors"
    )


def _ids(value: Any) -> Iterable[int]:
    if isinstance(value, bool):
        return ()
    if isinstance(value, int):
        return (value,)
    return ()
