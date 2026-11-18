from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import Row, Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.security import hash_password, verify_password
from core.timezones import resolve_timezone

from shared.audit import record_audit
from shared.base import BaseCRUD
from shared.csv_import import (
    CsvColumn,
    CsvEmailCheck,
    CsvGroup,
    CsvRow,
    CsvSchema,
    parse_import_csv,
    strip_lower,
)
from shared.enums import AuditAction, AuditEntity, SessionType
from shared.pagination import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    PaginatedResponse,
)
from shared.schedule import meeting_minutes, openable_session_types

from features.auth.model import User
from features.course.exceptions import OfferingNotFoundException
from features.course.model import Course, CourseOffering, OfferingComponent
from features.course_professor.exceptions import OverlappingAssignmentException
from features.course_professor.model import CourseProfessor
from features.course_professor.service import CourseProfessorService
from features.enrollment.model import Enrollment
from features.professor.exceptions import (
    CurrentPasswordInvalidException,
    PasswordReusedException,
    ProfessorAccountUnlinkedException,
    ProfessorEmailExistsException,
    ProfessorHasRecordsException,
    ProfessorNotArchivedException,
    ProfessorNotFoundException,
)
from features.professor.model import Professor
from features.professor.schema import (
    AssignedCourse,
    AssignedOfferingComponent,
    AssignedOfferingItem,
    ProfessorCreate,
    ProfessorDetail,
    ProfessorImportError,
    ProfessorImportResult,
    ProfessorProfileRead,
    ProfessorRead,
    ProfessorUpdate,
)
from features.program.model import Program, YearLevel
from features.session.model import Session
from features.session.plan import next_meeting
from features.student.model import Student

ROSTER_CSV_COLUMNS: tuple[CsvColumn, ...] = (
    CsvColumn("first_name"),
    CsvColumn("middle_name"),
    CsvColumn("last_name"),
    CsvColumn("email", normalize=strip_lower),
    CsvColumn("department"),
)

ROSTER_CSV_SCHEMA = CsvSchema(
    columns=ROSTER_CSV_COLUMNS,
    subject="professor",
    subject_column="email",
    subject_fallback="on line",
    checks=(
        CsvGroup(
            columns=("first_name", "last_name", "email"),
            reason="missing required field for {subject} {key}",
        ),
        CsvEmailCheck("email", "invalid email for {subject} {key}"),
    ),
)


_PROFESSOR_SORT_COLUMNS: dict[str, tuple[Any, ...]] = {
    "last_name": (Professor.last_name, Professor.first_name),
    "email": (Professor.email,),
    "created_at": (Professor.created_at,),
}


@dataclass(kw_only=True)
class _RosterRow:
    line: int
    first_name: str
    middle_name: str | None
    last_name: str
    email: str
    department: str | None


def _to_roster_row(raw: CsvRow) -> _RosterRow:
    values: dict[str, str] = raw.values

    return _RosterRow(
        line=raw.line,
        first_name=values["first_name"],
        middle_name=values["middle_name"] or None,
        last_name=values["last_name"],
        email=values["email"],
        department=values["department"] or None,
    )


def _assignments_stmt(professor_id: int) -> Select[tuple[Any, ...]]:
    """Current-dated, active assignments, projected in `_to_assigned_offering` order."""
    today: date = date.today()

    return (
        select(
            CourseOffering.id,
            CourseOffering.course_id,
            Course.course_code,
            Course.course_name,
            CourseOffering.program_id,
            Program.code,
            CourseOffering.year_level_id,
            YearLevel.label,
            CourseOffering.semester,
            CourseOffering.academic_year,
            CourseProfessor.is_primary,
            CourseProfessor.effective_from,
            CourseProfessor.effective_to,
            Course.units,
            # The configuration a session inherits (D93).
            CourseOffering.schedule_days,
            CourseOffering.schedule_start_time,
            CourseOffering.schedule_end_time,
            CourseOffering.classroom_name,
            CourseOffering.classroom_lat,
            CourseOffering.classroom_lng,
            CourseOffering.default_present_window_minutes,
            CourseOffering.default_late_window_minutes,
            CourseOffering.default_classroom_radius_meters,
        )
        .join(CourseProfessor, CourseProfessor.offering_id == CourseOffering.id)
        .join(Course, Course.id == CourseOffering.course_id)
        .join(Program, Program.id == CourseOffering.program_id)
        .join(YearLevel, YearLevel.id == CourseOffering.year_level_id)
        .where(
            CourseProfessor.professor_id == professor_id,
            CourseProfessor.effective_from <= today,
            or_(
                CourseProfessor.effective_to.is_(None),
                CourseProfessor.effective_to >= today,
            ),
            CourseOffering.is_active.is_(True),
        )
        .order_by(CourseOffering.id.asc())
    )


def _to_assigned_offering(row: Sequence[Any]) -> AssignedOfferingItem:
    (
        offering_id,
        course_id,
        course_code,
        course_name,
        program_id,
        program_code,
        year_level_id,
        year_level_label,
        semester,
        academic_year,
        is_primary,
        effective_from,
        effective_to,
        units,
        schedule_days,
        schedule_start_time,
        schedule_end_time,
        classroom_name,
        classroom_lat,
        classroom_lng,
        default_present_window_minutes,
        default_late_window_minutes,
        default_classroom_radius_meters,
    ) = row

    return AssignedOfferingItem(
        offering_id=offering_id,
        course_id=course_id,
        course_code=course_code,
        course_name=course_name,
        program_id=program_id,
        program_code=program_code,
        year_level_id=year_level_id,
        year_level_label=year_level_label,
        semester=semester,
        academic_year=academic_year,
        is_primary=bool(is_primary),
        effective_from=effective_from,
        effective_to=effective_to,
        units=int(units),
        schedule_days=schedule_days or "",
        schedule_start_time=schedule_start_time,
        schedule_end_time=schedule_end_time,
        classroom_name=classroom_name,
        classroom_lat=classroom_lat,
        classroom_lng=classroom_lng,
        default_present_window_minutes=int(default_present_window_minutes or 0),
        default_late_window_minutes=int(default_late_window_minutes or 0),
        default_classroom_radius_meters=default_classroom_radius_meters,
    )


def parse_professor_roster_csv(
    content: bytes,
) -> tuple[list[_RosterRow], list[ProfessorImportError]]:
    """Parse the professor roster-import CSV upload.

    Returns (valid_rows, errors). Never raises on bad rows — every problem
    is reported as a ProfessorImportError with its 1-based line number
    (header = 1). Emails are lowercased so duplicate detection agrees with
    single-create.
    """
    rows, errors = parse_import_csv(
        content,
        ROSTER_CSV_SCHEMA,
        error=lambda line, reason: ProfessorImportError(line=line, reason=reason),
    )

    return [_to_roster_row(row) for row in rows], errors


class ProfessorService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._professors: BaseCRUD[Professor] = BaseCRUD(Professor, session)

    async def create(
        self, *, payload: ProfessorCreate, assigned_by: int
    ) -> ProfessorRead:
        if await self._professors.get_by(email=payload.email) is not None:
            raise ProfessorEmailExistsException(payload.email)

        professor: Professor = await self._professors.create(
            first_name=payload.first_name,
            middle_name=payload.middle_name,
            last_name=payload.last_name,
            email=payload.email,
            department=payload.department,
        )

        # A roster row appearing is a change to the institution, so it is
        # audited like any other. The client used to INFER these rows from
        # `created_at` because nothing recorded them; an inferred row is not
        # evidence (ADR-086).
        await record_audit(
            self._session,
            actor_id=assigned_by,
            action=AuditAction.CREATE,
            entity_type=AuditEntity.PROFESSOR,
            entity_id=professor.id,
            new_value=self._professor_snapshot(professor),
        )

        for offering_id in dict.fromkeys(payload.courses):
            await self._assign_offering(
                professor_id=professor.id,
                offering_id=offering_id,
                assigned_by=assigned_by,
            )

        return await self._to_read(professor)

    async def get(self, *, professor_id: int) -> ProfessorDetail:
        professor: Professor = await self._get_or_404(professor_id)
        read: ProfessorRead = await self._to_read(professor)

        return ProfessorDetail(**read.model_dump())

    async def list(
        self,
        *,
        search: str | None,
        department: str | None,
        is_active: bool | None,
        sort_by: str | None,
        sort_dir: str | None,
        page: int,
        size: int,
    ) -> PaginatedResponse[ProfessorRead]:
        stmt: Select[tuple[Professor]] = select(Professor)

        if department is not None:
            stmt = stmt.where(Professor.department == department)

        if is_active is not None:
            stmt = stmt.where(Professor.is_active == is_active)

        if search:
            term: str = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Professor.first_name.ilike(term),
                    Professor.middle_name.ilike(term),
                    Professor.last_name.ilike(term),
                    Professor.email.ilike(term),
                )
            )

        total: int = (
            await self._session.scalar(
                select(func.count()).select_from(stmt.subquery())
            )
            or 0
        )

        rows: Sequence[Professor] = (
            await self._session.scalars(
                self._apply_order(stmt, sort_by=sort_by, sort_dir=sort_dir)
                .offset((page - 1) * size)
                .limit(size)
            )
        ).all()

        return PaginatedResponse[ProfessorRead](
            items=[await self._to_read(row) for row in rows],
            total=total,
            page=page,
            size=size,
        )

    async def update(
        self, *, professor_id: int, payload: ProfessorUpdate, assigned_by: int
    ) -> ProfessorRead:
        professor: Professor = await self._get_or_404(professor_id)
        values: dict[str, Any] = payload.model_dump(exclude_unset=True)

        is_active: bool | None = values.pop("is_active", None)
        courses: list[int] | None = values.pop("courses", None)

        if "email" in values and values["email"] != professor.email:
            existing: Professor | None = await self._professors.get_by(
                email=values["email"]
            )

            if existing is not None and existing.id != professor.id:
                raise ProfessorEmailExistsException(values["email"])

        for field, value in values.items():
            setattr(professor, field, value)

        if is_active is False:
            await self._archive_row(professor, assigned_by)
        elif is_active is True:
            professor.is_active = True
            await self._set_linked_user_active(
                user_id=professor.user_id, is_active=True, actor_id=assigned_by
            )

        await self._session.flush()
        # Reload after the flush: `updated_at` is server-side (TimestampMixin), so
        # it is expired and would raise MissingGreenlet if read synchronously.
        await self._session.refresh(professor)

        if courses is not None:
            await self._replace_assignments(
                professor_id=professor.id,
                offering_ids=courses,
                assigned_by=assigned_by,
            )

        return await self._to_read(professor)

    async def archive(
        self, *, professor_id: int, actor_id: int | None
    ) -> ProfessorRead:
        professor: Professor = await self._get_or_404(professor_id)
        await self._archive_row(professor, actor_id)
        # _archive_row flushes, which expires the server-side `updated_at`.
        await self._session.refresh(professor)

        return await self._to_read(professor)

    async def reactivate(
        self, *, professor_id: int, actor_id: int | None
    ) -> ProfessorRead:
        professor: Professor = await self._get_or_404(professor_id)
        old_value: dict[str, Any] = self._professor_snapshot(professor)
        professor.is_active = True
        await self._set_linked_user_active(
            user_id=professor.user_id, is_active=True, actor_id=actor_id
        )
        await self._session.flush()
        # Reload after the flush: `updated_at` is server-side (TimestampMixin), so
        # it is expired and would raise MissingGreenlet if read synchronously.
        await self._session.refresh(professor)

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.UPDATE,
            entity_type=AuditEntity.PROFESSOR,
            entity_id=professor.id,
            old_value=old_value,
            new_value=self._professor_snapshot(professor),
        )

        return await self._to_read(professor)

    async def import_roster(
        self, *, content: bytes, actor_id: int | None
    ) -> ProfessorImportResult:
        """Create NEW professor records from a CSV upload.

        Rows whose email already exists — in the database or earlier in the
        same file — are counted as duplicates, not errors. No user rows are
        created: imports stay Unclaimed until self-registration.
        """
        rows, errors = parse_professor_roster_csv(content)
        imported = 0
        duplicates = 0
        seen_emails: set[str] = set()

        for row in rows:
            if (
                row.email in seen_emails
                or await self._professors.get_by(email=row.email) is not None
            ):
                duplicates += 1
                seen_emails.add(row.email)
                continue

            seen_emails.add(row.email)
            self._session.add(
                Professor(
                    first_name=row.first_name,
                    middle_name=row.middle_name,
                    last_name=row.last_name,
                    email=row.email,
                    department=row.department,
                )
            )
            imported += 1

        await self._session.flush()

        # One row for the upload rather than one per professor, so a large
        # roster cannot bury every other action in the trail.
        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.IMPORT,
            entity_type=AuditEntity.PROFESSOR,
            entity_id=None,
            new_value={
                "imported": imported,
                "duplicates": duplicates,
                "errors": len(errors),
            },
        )

        errors.sort(key=lambda e: e.line)

        return ProfessorImportResult(
            imported=imported, duplicates=duplicates, errors=errors
        )

    async def hard_delete(self, *, professor_id: int, actor_id: int | None) -> None:
        """Permanently delete an archived professor with no sessions or assignments."""
        professor: Professor = await self._get_or_404(professor_id)

        if professor.is_active:
            raise ProfessorNotArchivedException(professor.id)

        session_count: int = (
            await self._session.scalar(
                select(func.count())
                .select_from(Session)
                .where(Session.professor_id == professor.id)
            )
            or 0
        )

        if session_count:
            raise ProfessorHasRecordsException(professor.id)

        assignment_count: int = (
            await self._session.scalar(
                select(func.count())
                .select_from(CourseProfessor)
                .where(CourseProfessor.professor_id == professor.id)
            )
            or 0
        )

        if assignment_count:
            raise ProfessorHasRecordsException(professor.id)

        # Snapshot before the delete: the instance is detached once flushed.
        old_value: dict[str, Any] = self._professor_snapshot(professor)

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.DELETE,
            entity_type=AuditEntity.PROFESSOR,
            entity_id=professor.id,
            old_value=old_value,
        )

        # Capture before the delete: the login must not survive the roster row.
        linked_user_id: int | None = professor.user_id
        await self._session.delete(professor)
        await self._session.flush()
        await self._set_linked_user_active(
            user_id=linked_user_id, is_active=False, actor_id=actor_id
        )
        await self._session.flush()

    async def resolve_professor_id(self, *, user_id: int) -> int:
        """Map a user id to its claimed professor row; 404 when unclaimed."""
        return (await self._get_professor_by_user_or_404(user_id)).id

    async def list_assigned_offerings(
        self,
        *,
        user_id: int,
        page: int = DEFAULT_PAGE,
        size: int = DEFAULT_PAGE_SIZE,
    ) -> PaginatedResponse[AssignedOfferingItem]:
        """Own active assignments with course-card enrichment.

        Active means the course_professors effective window covers today and
        the offering itself is active. Each row carries units, enrolled_count
        and the derived section set for the course cards.
        """
        professor: Professor = await self._get_professor_by_user_or_404(user_id)
        items: Sequence[AssignedOfferingItem] = await self._assigned_offerings(
            professor.id
        )
        window: list[AssignedOfferingItem] = list(
            items[(page - 1) * size : page * size]
        )
        await self._enrich_assigned_offerings(window)

        return PaginatedResponse[AssignedOfferingItem](
            items=window, total=len(items), page=page, size=size
        )

    async def get_self_profile(self, *, user_id: int) -> ProfessorProfileRead:
        """Self profile for the account header (wireframes 3.9).

        ``claim_status`` derives from ``professors.user_id`` non-null and
        ``session_count`` counts every session row owned by the professor.
        """
        professor: Professor = await self._get_professor_by_user_or_404(user_id)
        assigned: list[AssignedOfferingItem] = list(
            await self._assigned_offerings(professor.id)
        )
        await self._enrich_assigned_offerings(assigned)
        session_count: int = (
            await self._session.scalar(
                select(func.count())
                .select_from(Session)
                .where(Session.professor_id == professor.id)
            )
            or 0
        )

        return ProfessorProfileRead(
            id=professor.id,
            first_name=professor.first_name,
            middle_name=professor.middle_name,
            last_name=professor.last_name,
            email=professor.email,
            department=professor.department,
            assigned_courses=assigned,
            claim_status="Claimed" if professor.user_id is not None else "Unclaimed",
            created_at=professor.created_at,
            session_count=session_count,
        )

    async def _archive_row(self, professor: Professor, actor_id: int | None) -> None:
        # Soft archive touches only its own row for course data (ADR-058): no
        # cascade to course_professors / sessions. The linked login IS synced
        # (users.is_active) because auth gates only on the users table — an
        # archived roster row must not stay login-capable.
        old_value: dict[str, Any] = self._professor_snapshot(professor)
        professor.is_active = False
        await self._set_linked_user_active(
            user_id=professor.user_id, is_active=False, actor_id=actor_id
        )
        await self._session.flush()

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.ARCHIVE,
            entity_type=AuditEntity.PROFESSOR,
            entity_id=professor.id,
            old_value=old_value,
            new_value=self._professor_snapshot(professor),
        )

    async def _set_linked_user_active(
        self, *, user_id: int | None, is_active: bool, actor_id: int | None
    ) -> None:
        """Sync the login gate with the roster flag (see StudentService)."""
        if user_id is None:
            return
        user: User | None = await self._session.get(User, user_id)
        if user is None or user.is_active == is_active:
            return
        old_value: dict[str, Any] = {"is_active": user.is_active}
        user.is_active = is_active
        await self._session.flush()
        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.UPDATE,
            entity_type=AuditEntity.USER,
            entity_id=user.id,
            old_value=old_value,
            new_value={"is_active": is_active},
        )

    @staticmethod
    def _professor_snapshot(professor: Professor) -> dict[str, Any]:
        return {
            "email": professor.email,
            "first_name": professor.first_name,
            "last_name": professor.last_name,
            "department": professor.department,
            "is_active": professor.is_active,
        }

    @staticmethod
    def _assignment_snapshot(record: CourseProfessor) -> dict[str, Any]:
        return {
            "offering_id": record.offering_id,
            "professor_id": record.professor_id,
            "is_primary": record.is_primary,
            "effective_from": (
                record.effective_from.isoformat() if record.effective_from else None
            ),
            "effective_to": (
                record.effective_to.isoformat() if record.effective_to else None
            ),
        }

    async def _get_or_404(self, professor_id: int) -> Professor:
        professor: Professor | None = await self._professors.get(professor_id)

        if professor is None:
            raise ProfessorNotFoundException(professor_id)

        return professor

    async def account_user_id(self, professor_id: int) -> int:
        """The `users.id` behind this roster row, for credential operations.

        Public because `POST /admin/professors/{id}/reset-password` needs to
        resolve the roster row to an account before handing off to
        `AuthService.admin_reset_password`, which owns the credential write.
        """
        professor: Professor = await self._get_or_404(professor_id)

        if professor.user_id is None:
            raise ProfessorAccountUnlinkedException(professor_id)

        return professor.user_id

    async def change_password(
        self, *, user_id: int, current_password: str, new_password: str
    ) -> None:
        """Professor self-service password change (mirrors student flow)."""
        await self._get_professor_by_user_or_404(user_id)

        user: User | None = await self._session.get(User, user_id)

        if user is None:
            raise ProfessorNotFoundException(user_id)

        if not verify_password(current_password, user.password_hash):
            raise CurrentPasswordInvalidException()

        if verify_password(new_password, user.password_hash):
            raise PasswordReusedException()

        user.password_hash = hash_password(new_password)
        user.must_change_password = False

        await self._session.flush()

    async def _get_professor_by_user_or_404(self, user_id: int) -> Professor:
        professor: Professor | None = await self._professors.get_by(user_id=user_id)

        if professor is None:
            raise ProfessorNotFoundException(user_id)

        return professor

    async def _assigned_offerings(
        self, professor_id: int
    ) -> Sequence[AssignedOfferingItem]:
        """Active assignments, one row per offering.

        The query can return more than one active row for the same offering
        when a handover leaves an old assignment ending today and a new one
        starting today. The UI keys course rows by offering id, so collapse
        duplicates here and keep the most current assignment.
        """
        rows = (await self._session.execute(_assignments_stmt(professor_id))).all()

        by_offering: dict[int, AssignedOfferingItem] = {}
        for row in rows:
            item = _to_assigned_offering(row)
            current = by_offering.get(item.offering_id)
            if current is None or self._assignment_rank(item) > self._assignment_rank(
                current
            ):
                by_offering[item.offering_id] = item

        return list(by_offering.values())

    @staticmethod
    def _assignment_rank(item: AssignedOfferingItem) -> tuple[bool, date, bool]:
        """Order duplicate active rows for the same offering.

        Prefer an open-ended assignment, then the latest start date, then the
        primary role. Deterministic so the page does not flicker between two
        rows that share an offering id.
        """
        return (item.effective_to is None, item.effective_from, item.is_primary)

    async def _enrich_assigned_offerings(
        self, items: Sequence[AssignedOfferingItem]
    ) -> None:
        """Fill enrolled_count and section for one page of assignments.

        Both aggregates run as a single GROUP BY query each over the page's
        offering ids, so enrichment stays constant-query regardless of page
        size. `section` is the distinct set of `students.section` across the
        offering's enrollments (derived — no stored column backs it).
        `schedule_ok` compares the merged meeting total against the row's
        units in whole minutes (same rule as the session-open gate); rows
        with no configured meetings stay True.
        """
        if not items:
            return

        offering_ids: list[int] = [item.offering_id for item in items]
        by_offering: dict[int, AssignedOfferingItem] = {
            item.offering_id: item for item in items
        }

        counts = (
            await self._session.execute(
                select(Enrollment.offering_id, func.count())
                .where(Enrollment.offering_id.in_(offering_ids))
                .group_by(Enrollment.offering_id)
            )
        ).all()

        for offering_id, count in counts:
            item = by_offering.get(offering_id)

            if item is not None:
                item.enrolled_count = int(count)

        section_rows = (
            await self._session.execute(
                select(Enrollment.offering_id, Student.section)
                .join(Student, Student.id == Enrollment.student_id)
                .where(
                    Enrollment.offering_id.in_(offering_ids),
                    Student.section.is_not(None),
                )
                .group_by(Enrollment.offering_id, Student.section)
                .order_by(Student.section.asc())
            )
        ).all()

        grouped: dict[int, list[str]] = {}

        for offering_id, section in section_rows:
            grouped.setdefault(offering_id, []).append(section)

        for offering_id, sections in grouped.items():
            item = by_offering.get(offering_id)

            if item is not None:
                item.section = sections

        component_rows: Sequence[OfferingComponent] = (
            await self._session.scalars(
                select(OfferingComponent)
                .where(
                    OfferingComponent.offering_id.in_(offering_ids),
                    OfferingComponent.is_active.is_(True),
                )
                .order_by(OfferingComponent.id)
            )
        ).all()

        minutes_by_offering: dict[int, float] = {}
        components_by_offering: dict[int, list[OfferingComponent]] = {}

        for component in component_rows:
            minutes_by_offering[component.offering_id] = minutes_by_offering.get(
                component.offering_id, 0.0
            ) + meeting_minutes(
                component.schedule_days,
                component.schedule_start_time,
                component.schedule_end_time,
            )
            components_by_offering.setdefault(component.offering_id, []).append(
                component
            )

        for offering_id, total_minutes in minutes_by_offering.items():
            item = by_offering.get(offering_id)

            if item is not None:
                item.schedule_ok = int(round(total_minutes)) == int(item.units) * 60

        # D93: the meetings a session inherits, and the next occurrence of the
        # first one. The occurrence is resolved with the shared pure helper —
        # no query per offering — so the list stays a constant number of
        # round trips however many assignments a professor holds.
        zone = resolve_timezone(
            get_settings().institution_timezone, label="institution timezone"
        )
        now = datetime.now(timezone.utc)

        # D95: every assignment reports the types it can open — the ones it
        # configures as active meetings, or a lecture when it has none. The
        # shared helper owns the rule, so this list and the admin's badge
        # cannot disagree.
        for offering_id, item in by_offering.items():
            item.session_types = openable_session_types(
                component.session_type
                for component in components_by_offering.get(offering_id, [])
            )

        for offering_id, components in components_by_offering.items():
            item = by_offering.get(offering_id)

            if item is None:
                continue

            item.components = [
                AssignedOfferingComponent(
                    id=component.id,
                    session_type=SessionType(component.session_type),
                    schedule_days=component.schedule_days,
                    schedule_start_time=component.schedule_start_time,
                    schedule_end_time=component.schedule_end_time,
                    classroom_name=component.classroom_name,
                    classroom_lat=component.classroom_lat,
                    classroom_lng=component.classroom_lng,
                )
                for component in components
            ]

            first = components[0]
            found = next_meeting(
                days=first.schedule_days,
                start=first.schedule_start_time,
                end=first.schedule_end_time,
                now=now,
                zone=zone,
            )

            if found is not None:
                day, _start, _end = found
                item.next_session_date = day
                item.next_session_start = first.schedule_start_time
                item.next_session_end = first.schedule_end_time

    async def _get_offering_or_404(self, offering_id: int) -> CourseOffering:
        offering: CourseOffering | None = await self._session.get(
            CourseOffering, offering_id
        )

        if offering is None:
            raise OfferingNotFoundException(offering_id)

        return offering

    async def _assign_offering(
        self, *, professor_id: int, offering_id: int, assigned_by: int
    ) -> CourseProfessor:
        # Presence check only: the helper raises 404 when the offering is gone.
        # The returned row is intentionally unused here.
        await self._get_offering_or_404(offering_id)
        today: date = date.today()

        overlap_service = CourseProfessorService(self._session)
        overlap: list[CourseProfessor] = await overlap_service.check_overlap(
            offering_id, professor_id, today, None
        )

        if overlap:
            existing: CourseProfessor = overlap[0]
            raise OverlappingAssignmentException(
                offering_id,
                professor_id,
                today,
                None,
                existing.effective_from,
                existing.effective_to,
            )

        record = CourseProfessor(
            offering_id=offering_id,
            professor_id=professor_id,
            is_primary=False,
            effective_from=today,
            effective_to=None,
            assigned_by=assigned_by,
        )
        self._session.add(record)
        await self._session.flush()

        await record_audit(
            self._session,
            actor_id=assigned_by,
            action=AuditAction.ASSIGN,
            entity_type=AuditEntity.COURSE_PROFESSOR,
            entity_id=None,
            new_value=self._assignment_snapshot(record),
        )

        return record

    async def _replace_assignments(
        self, *, professor_id: int, offering_ids: Sequence[int], assigned_by: int
    ) -> None:
        target: set[int] = set(dict.fromkeys(offering_ids))

        existing: Sequence[CourseProfessor] = (
            await self._session.scalars(
                select(CourseProfessor).where(
                    CourseProfessor.professor_id == professor_id
                )
            )
        ).all()
        current: set[int] = {row.offering_id for row in existing}

        for row in existing:
            if row.offering_id not in target:
                old_value: dict[str, Any] = self._assignment_snapshot(row)
                await self._session.delete(row)

                await record_audit(
                    self._session,
                    actor_id=assigned_by,
                    action=AuditAction.UNASSIGN,
                    entity_type=AuditEntity.COURSE_PROFESSOR,
                    entity_id=None,
                    old_value=old_value,
                )

        await self._session.flush()

        for offering_id in target - current:
            await self._assign_offering(
                professor_id=professor_id,
                offering_id=offering_id,
                assigned_by=assigned_by,
            )

    async def _assigned_courses(self, professor_id: int) -> Sequence[AssignedCourse]:
        rows: Sequence[Row[tuple[int, str]]] = (
            await self._session.execute(
                select(CourseOffering.id, Course.course_code)
                .join(CourseProfessor, CourseProfessor.offering_id == CourseOffering.id)
                .join(Course, CourseOffering.course_id == Course.id)
                .where(CourseProfessor.professor_id == professor_id)
                .distinct()
                .order_by(CourseOffering.id)
            )
        ).all()

        return [
            AssignedCourse(offering_id=offering_id, course_code=course_code)
            for offering_id, course_code in rows
        ]

    async def _to_read(self, professor: Professor) -> ProfessorRead:
        return ProfessorRead(
            id=professor.id,
            first_name=professor.first_name,
            middle_name=professor.middle_name,
            last_name=professor.last_name,
            email=professor.email,
            department=professor.department,
            is_active=professor.is_active,
            claim_status="Claimed" if professor.user_id is not None else "Unclaimed",
            assigned_courses=list(await self._assigned_courses(professor.id)),
            created_at=professor.created_at,
        )

    @staticmethod
    def _apply_order(
        stmt: Select[tuple[Professor]], *, sort_by: str | None, sort_dir: str | None
    ) -> Select[tuple[Professor]]:
        columns: tuple[Any, ...] | None = _PROFESSOR_SORT_COLUMNS.get(sort_by or "")

        if columns is None:
            return stmt.order_by(Professor.id)

        desc: bool = (sort_dir or "asc").lower() == "desc"
        ordered = [col.desc() if desc else col.asc() for col in columns]

        return stmt.order_by(*ordered, Professor.id.asc())
