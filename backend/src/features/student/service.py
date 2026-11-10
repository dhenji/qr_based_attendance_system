from __future__ import annotations

import base64
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import hash_password, verify_password
from features.analytics.model import StudentRiskScore
from features.attendance.model import Attendance
from features.auth.model import User
from features.course.model import Course, CourseOffering
from features.course_professor.model import CourseProfessor
from features.enrollment.model import Enrollment
from features.excuse.model import ExcuseRequest
from features.professor.model import Professor
from features.program.exceptions import (
    ProgramNotFoundException,
    YearLevelNotFoundException,
)
from features.program.model import Program, YearLevel
from features.student.exceptions import (
    CurrentPasswordInvalidException,
    PasswordReusedException,
    FaceEmbeddingNotFoundException,
    StudentEmailExistsException,
    StudentHasRecordsException,
    StudentIdExistsException,
    StudentNotArchivedException,
    StudentAccountUnlinkedException,
    StudentNotFoundException,
    YearLevelMismatchException,
)
from features.student.model import Student
from features.student.schema import (
    ChangePasswordRequest,
    FaceEmbeddingResponse,
    ScheduleItem,
    ScheduleResponse,
    StudentCreate,
    StudentDetail,
    StudentImportError,
    StudentImportResult,
    StudentRead,
    StudentUpdate,
)
from shared.audit import record_audit
from shared.base import BaseCRUD
from shared.cache import get_face_embedding_cached
from shared.csv_import import (
    CsvColumn,
    CsvEmailCheck,
    CsvGroup,
    CsvRow,
    CsvSchema,
    parse_import_csv,
    strip_lower,
    strip_upper,
)
from shared.enums import AuditAction, AuditEntity
from shared.pagination import PaginatedResponse
from shared.query import apply_if
from shared.schedule import day_weekdays

ROSTER_CSV_COLUMNS: tuple[CsvColumn, ...] = (
    CsvColumn(
        "student_id", normalize=strip_upper, required_reason="missing student_id"
    ),
    CsvColumn("first_name"),
    CsvColumn("middle_name"),
    CsvColumn("last_name"),
    CsvColumn("email", normalize=strip_lower),
    CsvColumn("program_code", normalize=strip_upper),
    CsvColumn("section"),
    CsvColumn("year_level"),
)

ROSTER_CSV_SCHEMA = CsvSchema(
    columns=ROSTER_CSV_COLUMNS,
    subject="student",
    subject_column="student_id",
    checks=(
        CsvGroup(
            columns=("first_name", "last_name", "email"),
            reason="missing required field for {subject} {key}",
        ),
        CsvEmailCheck("email", "invalid email for {subject} {key}"),
        CsvGroup(
            columns=("program_code", "year_level"),
            reason="missing program_code/year_level for {subject} {key}",
        ),
    ),
)


_STUDENT_SORT_COLUMNS: dict[str, tuple[Any, ...]] = {
    "last_name": (Student.last_name, Student.first_name),
    "student_id": (Student.student_id,),
    "created_at": (Student.created_at,),
}


@dataclass(kw_only=True)
class _ImportState:
    """Counters and seen-sets for one roster import run.

    Mutable by design: the per-row helpers own the bookkeeping so the driver
    loop stays a flat read/dispatch/collect.
    """

    imported: int = 0
    duplicates: int = 0
    seen_ids: set[str] = field(default_factory=set)
    seen_emails: set[str] = field(default_factory=set)


@dataclass(kw_only=True)
class _RosterRow:
    line: int
    student_id: str
    first_name: str
    middle_name: str | None
    last_name: str
    email: str
    program_code: str
    section: str | None
    year_level: str


def _to_roster_row(raw: CsvRow) -> _RosterRow:
    values: dict[str, str] = raw.values

    return _RosterRow(
        line=raw.line,
        student_id=values["student_id"],
        first_name=values["first_name"],
        middle_name=values["middle_name"] or None,
        last_name=values["last_name"],
        email=values["email"],
        program_code=values["program_code"],
        section=values["section"] or None,
        year_level=values["year_level"],
    )


# `schedule_days` is an uppercase string of day initials, "MWF" or "TF" in the
# seed. Nothing in the schema constrains the letters, so `shared.schedule`
# owns the one interpretation of them (D93): T is Tuesday, H is Thursday (T
# was already taken), U is Sunday (S is Saturday). An unrecognised letter
# matches nothing rather than raising: a typo in one offering's schedule
# should hide that one class from today's list, not break a student's whole
# dashboard.
def _meets_on(schedule_days: str | None, day: date) -> bool:
    """Whether an offering with these `schedule_days` meets on `day`.

    Membership rather than a first-letter comparison: "MWF" must match a
    Wednesday, which it does not if only `M` is looked at. Monday is 0 in both
    `date.weekday()` and the shared map, so the comparison is direct.
    """
    return day.weekday() in day_weekdays(schedule_days)


def _schedule_stmt(student_id: int) -> Select[tuple[Any, ...]]:
    """Active offerings for `student_id`, projected in `_to_schedule_item` order."""
    return (
        select(
            CourseOffering.id,
            CourseOffering.course_id,
            Course.course_code,
            Course.course_name,
            Program.code,
            YearLevel.label,
            CourseOffering.semester,
            CourseOffering.schedule_days,
            CourseOffering.schedule_start_time,
            CourseOffering.schedule_end_time,
            CourseOffering.classroom_name,
        )
        .select_from(Enrollment)
        .join(CourseOffering, CourseOffering.id == Enrollment.offering_id)
        .join(Course, Course.id == CourseOffering.course_id)
        .join(Program, Program.id == CourseOffering.program_id)
        .join(YearLevel, YearLevel.id == CourseOffering.year_level_id)
        .where(
            Enrollment.student_id == student_id,
            CourseOffering.is_active.is_(True),
        )
        .order_by(CourseOffering.id.asc())
    )


def _to_schedule_item(row: Sequence[Any], names: dict[int, str]) -> ScheduleItem:
    (
        offering_id,
        course_id,
        course_code,
        course_name,
        program_code,
        year_level_label,
        semester,
        schedule_days,
        schedule_start_time,
        schedule_end_time,
        classroom_name,
    ) = row

    return ScheduleItem(
        offering_id=offering_id,
        course_id=course_id,
        course_code=course_code,
        course_name=course_name,
        program_code=program_code,
        year_level_label=year_level_label,
        semester=semester,
        schedule_days=schedule_days,
        schedule_start_time=schedule_start_time,
        schedule_end_time=schedule_end_time,
        classroom_name=classroom_name,
        professor_name=names.get(offering_id),
    )


def parse_roster_csv(
    content: bytes,
) -> tuple[list[_RosterRow], list[StudentImportError]]:
    """Parse the roster-import CSV upload.

    Returns (valid_rows, errors). Never raises on bad rows — every problem is
    reported as a StudentImportError with its 1-based line number (header = 1).
    Values are normalized the same way as StudentCreate (student_id upper,
    email lower) so duplicate detection agrees with single-create.
    """
    rows, errors = parse_import_csv(
        content,
        ROSTER_CSV_SCHEMA,
        error=lambda line, reason: StudentImportError(line=line, reason=reason),
    )

    return [_to_roster_row(row) for row in rows], errors


class StudentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._students: BaseCRUD[Student] = BaseCRUD(Student, session)
        self._programs: BaseCRUD[Program] = BaseCRUD(Program, session)
        self._years: BaseCRUD[YearLevel] = BaseCRUD(YearLevel, session)

    async def create(
        self, *, payload: StudentCreate, actor_id: int | None = None
    ) -> StudentRead:
        if await self._students.get_by(student_id=payload.student_id) is not None:
            raise StudentIdExistsException(payload.student_id)

        if await self._students.get_by(email=payload.email) is not None:
            raise StudentEmailExistsException(payload.email)

        year_level, _ = await self._resolve_cohort(
            payload.year_level_id, payload.program_id
        )

        student: Student = await self._students.create(
            student_id=payload.student_id,
            first_name=payload.first_name,
            middle_name=payload.middle_name,
            last_name=payload.last_name,
            email=payload.email,
            year_level_id=year_level.id,
            section=payload.section,
        )

        # A roster row appearing is a change to the institution, so it is
        # audited like any other. The client used to INFER these rows from
        # `created_at` because nothing recorded them; an inferred row is not
        # evidence (ADR-086).
        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.CREATE,
            entity_type=AuditEntity.STUDENT,
            entity_id=student.id,
            new_value=self._student_snapshot(student),
        )

        return await self._to_read(student)

    async def get(self, *, student_id: int) -> StudentDetail:
        return await self._to_detail(await self._get_or_404(student_id))

    async def get_profile(self, *, user_id: int) -> StudentDetail:
        """Get the student profile for the authenticated user.

        Resolves the student by user_id (from the auth token) and returns
        the full detail including face enrollment metadata and scan count.
        """
        student: Student | None = await self._students.get_by(user_id=user_id)

        if student is None:
            raise StudentNotFoundException(user_id)

        return await self._to_detail(student)

    async def get_face_embedding(
        self, *, user_id: int, current_version: int = 0
    ) -> FaceEmbeddingResponse | None:
        """Return the student's embedding if the client copy is stale.

        Return `None` when the client is current (router maps to 204).
        Raises 404 when the identity is missing or has no blob stored.
        """

        student: Student | None = await self._students.get_by(user_id=user_id)

        if student is None:
            raise StudentNotFoundException(user_id)

        blob: bytes | None = await get_face_embedding_cached(self._session, student.id)

        if blob is None:
            raise FaceEmbeddingNotFoundException(user_id)

        server_version: int = student.face_embedding_version or 0

        if current_version >= server_version:
            return None

        return FaceEmbeddingResponse(
            version=server_version, embedding=base64.b64encode(blob).decode("ascii")
        )

    async def get_schedule(self, *, user_id: int) -> ScheduleResponse:
        """Enrolled offerings with schedule, classroom, and professor name.

        Active offerings only (`CourseOffering.is_active`), stable
        `offering_id ASC` order (presentation sorting stays frontend-side).
        Professor names resolve to the current primary assignment, else the
        latest current assignment, else None. Read-only: no rows written.
        """
        student: Student | None = await self._students.get_by(user_id=user_id)

        if student is None:
            raise StudentNotFoundException(user_id)

        rows = (
            await self._session.execute(_schedule_stmt(student.id))
        ).all()

        names: dict[int, str] = await self._schedule_professor_names(
            [row[0] for row in rows]
        )

        return ScheduleResponse(
            offerings=[_to_schedule_item(row, names) for row in rows]
        )

    async def _schedule_professor_names(
        self, offering_ids: list[int]
    ) -> dict[int, str]:
        """Current professor display name per offering (batched, one query).

        Keeps only assignments whose effective window covers today, then
        picks primary first, latest `effective_from` on ties — mirroring
        `ProfessorService._assigned_offerings`.
        """
        if not offering_ids:
            return {}

        today: date = date.today()
        prof_rows = (
            await self._session.execute(
                select(
                    CourseProfessor.offering_id,
                    Professor.first_name,
                    Professor.last_name,
                    CourseProfessor.is_primary,
                    CourseProfessor.effective_from,
                )
                .join(Professor, Professor.id == CourseProfessor.professor_id)
                .where(
                    CourseProfessor.offering_id.in_(offering_ids),
                    CourseProfessor.effective_from <= today,
                    or_(
                        CourseProfessor.effective_to.is_(None),
                        CourseProfessor.effective_to >= today,
                    ),
                )
            )
        ).all()

        ranked: dict[int, tuple[tuple[bool, Any], str]] = {}

        for offering_id, first_name, last_name, is_primary, effective_from in prof_rows:
            key: tuple[bool, Any] = (bool(is_primary), effective_from)
            current = ranked.get(offering_id)

            if current is None or key > current[0]:
                ranked[offering_id] = (key, f"{first_name} {last_name}")

        return {offering_id: name for offering_id, (_, name) in ranked.items()}

    async def list(
        self,
        *,
        search: str | None,
        program_id: int | None,
        year_level_id: int | None,
        section: str | None,
        is_active: bool | None,
        sort_by: str | None,
        sort_dir: str | None,
        page: int,
        size: int,
    ) -> PaginatedResponse[StudentRead]:
        stmt: Select[tuple[Student]] = self._list_stmt(
            search=search,
            program_id=program_id,
            year_level_id=year_level_id,
            section=section,
            is_active=is_active,
        )

        total: int = (
            await self._session.scalar(
                select(func.count()).select_from(stmt.subquery())
            )
            or 0
        )

        rows: Sequence[Student] = (
            await self._session.scalars(
                self._apply_order(stmt, sort_by=sort_by, sort_dir=sort_dir)
                .offset((page - 1) * size)
                .limit(size)
            )
        ).all()

        return PaginatedResponse[StudentRead](
            items=[await self._to_read(row) for row in rows],
            total=total,
            page=page,
            size=size,
        )

    @staticmethod
    def _list_stmt(
        *,
        search: str | None,
        program_id: int | None,
        year_level_id: int | None,
        section: str | None,
        is_active: bool | None,
    ) -> Select[tuple[Student]]:
        """Base select with every list filter applied.

        Criteria are built lazily by `apply_if` so a missing filter never
        constructs a comparison that would reject ``None``.
        """
        stmt: Select[tuple[Student]] = select(Student)
        stmt = apply_if(stmt, year_level_id, lambda v: Student.year_level_id == v)
        stmt = apply_if(
            stmt,
            program_id,
            lambda v: Student.year_level_id.in_(
                select(YearLevel.id).where(YearLevel.program_id == v)
            ),
        )
        stmt = apply_if(stmt, section, lambda v: Student.section == v)
        stmt = apply_if(stmt, is_active, lambda v: Student.is_active == v)

        if search:
            term: str = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Student.student_id.ilike(term),
                    Student.first_name.ilike(term),
                    Student.middle_name.ilike(term),
                    Student.last_name.ilike(term),
                    Student.email.ilike(term),
                )
            )

        return stmt

    async def update(
        self, *, student_id: int, payload: StudentUpdate, actor_id: int | None
    ) -> StudentRead:
        student: Student = await self._get_or_404(student_id)
        values: dict[str, Any] = payload.model_dump(exclude_unset=True)

        # Extract cohort fields for joint validation
        program_id: int | None = values.pop("program_id", None)
        year_level_id: int | None = values.pop("year_level_id", None)

        for field, value in values.items():
            if handler := self._FIELD_HANDLERS.get(field):
                await handler(self, student, value, student_id, actor_id)
            else:
                setattr(student, field, value)

        if program_id is not None or year_level_id is not None:
            await self._resolve_and_set_cohort(student, program_id, year_level_id)

        await self._session.flush()
        # Reload after the flush: `updated_at` is server-side (TimestampMixin), so
        # it is expired and would raise MissingGreenlet if read synchronously.
        await self._session.refresh(student)

        # No audit row for the field edits themselves: only the archive and
        # reactivate transitions are trail-worthy here, and `is_active` routes
        # through `archive()`/`reactivate()` below. Auditing here too would log
        # the same transition twice on a PATCH that flips `is_active`.
        return await self._to_read(student)

    async def _handle_email(
        self, student: Student, value: str, student_id: int, actor_id: int | None
    ) -> None:
        # `actor_id` is unused: only `is_active` needs to reach the audited
        # archive/reactivate methods. It is accepted because `_FIELD_HANDLERS`
        # calls every handler with one signature.
        if value != student.email:
            existing: Student | None = await self._students.get_by(email=value)
            if existing is not None and existing.id != student.id:
                raise StudentEmailExistsException(value)
        student.email = value

    async def _handle_is_active(
        self, student: Student, value: bool, student_id: int, actor_id: int | None
    ) -> None:
        # Both directions route through the dedicated method so a PATCH that
        # flips `is_active` is audited on exactly the same path as a direct
        # call, and appears once rather than twice.
        if value is False:
            await self.archive(student_id=student.id, actor_id=actor_id)
        else:
            await self.reactivate(student_id=student.id, actor_id=actor_id)

    async def _resolve_and_set_cohort(
        self, student: Student, program_id: int | None, year_level_id: int | None
    ) -> None:
        target_program: int = (
            program_id
            if program_id is not None
            else (await self._year_level(student.year_level_id)).program_id
        )
        target_year: int = (
            year_level_id if year_level_id is not None else student.year_level_id
        )
        year_level, _ = await self._resolve_cohort(target_year, target_program)
        student.year_level_id = year_level.id

    _FIELD_HANDLERS: dict[str, Callable] = {
        "email": _handle_email,
        "is_active": _handle_is_active,
    }

    async def archive(self, *, student_id: int, actor_id: int | None) -> StudentRead:
        student: Student = await self._get_or_404(student_id)
        old_value: dict[str, Any] = self._student_snapshot(student)
        student.is_active = False
        # Face revocation: an archived identity must not stay matchable.
        student.face_embedding = None
        student.face_enrolled_at = None
        student.face_embedding_version = (student.face_embedding_version or 0) + 1
        await self._set_linked_user_active(
            user_id=student.user_id, is_active=False, actor_id=actor_id
        )
        await self._session.flush()
        # Reload after the flush: `updated_at` is server-side (TimestampMixin), so
        # it is expired and would raise MissingGreenlet if read synchronously.
        await self._session.refresh(student)

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.ARCHIVE,
            entity_type=AuditEntity.STUDENT,
            entity_id=student.id,
            old_value=old_value,
            new_value=self._student_snapshot(student),
        )

        return await self._to_read(student)

    async def reactivate(
        self, *, student_id: int, actor_id: int | None
    ) -> StudentRead:
        student: Student = await self._get_or_404(student_id)
        old_value: dict[str, Any] = self._student_snapshot(student)
        student.is_active = True
        await self._set_linked_user_active(
            user_id=student.user_id, is_active=True, actor_id=actor_id
        )
        await self._session.flush()
        # Reload after the flush: `updated_at` is server-side (TimestampMixin), so
        # it is expired and would raise MissingGreenlet if read synchronously.
        await self._session.refresh(student)

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.UPDATE,
            entity_type=AuditEntity.STUDENT,
            entity_id=student.id,
            old_value=old_value,
            new_value=self._student_snapshot(student),
        )

        return await self._to_read(student)

    async def change_password(
        self, user_id: int, current_password: str, new_password: str
    ) -> None:
        """Change the student's password.

        Validates the current password against the linked User record,
        then updates the hash and clears must_change_password.

        The User is loaded with an explicit second query rather than read
        off `student.user`: the relationship declares no `lazy=`, so
        touching it after the `Student` query would raise MissingGreenlet
        in async (coding-standards §1.6).
        """
        student: Student | None = await self._students.get_by(user_id=user_id)

        if student is None:
            raise StudentNotFoundException(user_id)

        user: User | None = await self._session.get(User, user_id)

        if user is None:
            raise StudentNotFoundException(user_id)

        if not verify_password(current_password, user.password_hash):
            raise CurrentPasswordInvalidException()

        if verify_password(new_password, user.password_hash):
            raise PasswordReusedException()

        user.password_hash = hash_password(new_password)
        user.must_change_password = False

        await self._session.flush()

    async def import_roster(
        self, *, content: bytes, actor_id: int | None
    ) -> StudentImportResult:
        """Create NEW roster students from a CSV upload.

        Unlike offering bulk-enroll (which attaches existing students),
        every valid row inserts a student. Rows whose student_id or email
        already exists — in the database or earlier in the same file — are
        counted as duplicates, not errors.
        """
        rows, parse_errors = parse_roster_csv(content)
        state = _ImportState()
        errors: list[StudentImportError] = list(parse_errors)

        for row in rows:
            if await self._is_duplicate_row(row, state):
                state.duplicates += 1
                continue

            error: StudentImportError | None = await self._import_row(row, state)

            if error is None:
                state.imported += 1
            else:
                errors.append(error)

        await self._session.flush()

        # One row for the upload, not one per student: a 400-line roster would
        # bury every other action in the trail. `entity_id` is null because the
        # subject is the batch, which has no row of its own.
        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.IMPORT,
            entity_type=AuditEntity.STUDENT,
            entity_id=None,
            new_value={
                "imported": state.imported,
                "duplicates": state.duplicates,
                "errors": len(errors),
            },
        )

        errors.sort(key=lambda e: e.line)

        return StudentImportResult(
            imported=state.imported, duplicates=state.duplicates, errors=errors
        )

    async def _is_duplicate_row(
        self, row: _RosterRow, state: _ImportState
    ) -> bool:
        """Row collides with an earlier row in this file or with the database.

        Both the id and the email are checked, in-file first, so a repeat of
        either counts as a duplicate rather than a per-line error.
        """
        return (
            row.student_id in state.seen_ids
            or row.email in state.seen_emails
            or await self._students.get_by(student_id=row.student_id) is not None
            or await self._students.get_by(email=row.email) is not None
        )

    async def _import_row(
        self, row: _RosterRow, state: _ImportState
    ) -> StudentImportError | None:
        """Insert one student. Returns the error to report, or None on success.

        The seen-sets are populated *before* the program and year-level
        lookups, so a row rejected for an unknown program still suppresses a
        later row repeating the same id or email.
        """
        state.seen_ids.add(row.student_id)
        state.seen_emails.add(row.email)

        program = await self._programs.get_by(code=row.program_code)

        if program is None:
            return StudentImportError(
                line=row.line,
                reason=f"unknown program_code {row.program_code}",
            )

        year_level = await self._resolve_import_year_level(program.id, row.year_level)

        if year_level is None:
            return StudentImportError(
                line=row.line,
                reason=(
                    f"unknown year_level {row.year_level} "
                    f"for program {row.program_code}"
                ),
            )

        self._session.add(
            Student(
                student_id=row.student_id,
                first_name=row.first_name,
                middle_name=row.middle_name,
                last_name=row.last_name,
                email=row.email,
                year_level_id=year_level.id,
                section=row.section,
            )
        )

        return None

    async def hard_delete(self, *, student_id: int, actor_id: int | None) -> None:
        """Permanently delete an archived student with no referencing rows."""
        student: Student = await self._get_or_404(student_id)

        if student.is_active:
            raise StudentNotArchivedException(student.id)

        for model in (Enrollment, Attendance, ExcuseRequest, StudentRiskScore):
            count: int = (
                await self._session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.student_id == student.id)
                )
                or 0
            )

            if count:
                raise StudentHasRecordsException(student.id)

        # Snapshot before the delete: the instance is detached once flushed.
        old_value: dict[str, Any] = self._student_snapshot(student)

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.DELETE,
            entity_type=AuditEntity.STUDENT,
            entity_id=student.id,
            old_value=old_value,
        )

        # Capture before the delete: the instance is detached once flushed.
        # The login must not survive the roster row: deactivate instead of
        # deleting so audit history keyed by the user id stays intact.
        linked_user_id: int | None = student.user_id
        await self._session.delete(student)
        await self._session.flush()
        await self._set_linked_user_active(
            user_id=linked_user_id, is_active=False, actor_id=actor_id
        )
        await self._session.flush()

    @staticmethod
    def _student_snapshot(student: Student) -> dict[str, Any]:
        """The audited columns of a student row.

        The face embedding is deliberately absent — it is an encrypted blob and
        `audit_logs` is readable by every admin. `face_embedding_version` is
        kept because it is the signal that the embedding changed.
        """
        return {
            "student_id": student.student_id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "email": student.email,
            "year_level_id": student.year_level_id,
            "section": student.section,
            "is_active": student.is_active,
            "face_enrolled_at": (
                student.face_enrolled_at.isoformat()
                if student.face_enrolled_at
                else None
            ),
            "face_embedding_version": student.face_embedding_version or 0,
        }

    async def _get_or_404(self, student_id: int) -> Student:
        student: Student | None = await self._students.get(student_id)

        if student is None:
            raise StudentNotFoundException(student_id)

        return student

    async def account_user_id(self, student_id: int) -> int:
        """The `users.id` behind this roster row, for credential operations.

        Public because `POST /admin/students/{id}/reset-password` needs to
        resolve the roster row to an account before handing off to
        `AuthService.admin_reset_password`, which owns the credential write.
        """
        student: Student = await self._get_or_404(student_id)

        if student.user_id is None:
            raise StudentAccountUnlinkedException(student_id)

        return student.user_id

    async def _set_linked_user_active(
        self, *, user_id: int | None, is_active: bool, actor_id: int | None
    ) -> None:
        """Sync the login gate with the roster flag.

        Auth (`login`, `refresh_token`, `_get_active_user`) gates only on
        `users.is_active`, so archiving a roster row without touching the
        linked user leaves the login working. Unclaimed rows (`user_id=None`)
        have no login and are a no-op. No-op when the flag already matches so
        re-archiving does not spam the audit trail.
        """
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

    async def _year_level(self, year_level_id: int) -> YearLevel:
        year_level: YearLevel | None = await self._session.get(YearLevel, year_level_id)

        if year_level is None:
            raise YearLevelNotFoundException(year_level_id)

        return year_level

    async def _resolve_cohort(
        self, year_level_id: int, program_id: int
    ) -> tuple[YearLevel, Program]:
        year_level: YearLevel | None = await self._session.get(YearLevel, year_level_id)

        if year_level is None:
            raise YearLevelNotFoundException(year_level_id, program_id)

        program: Program | None = await self._session.get(Program, program_id)

        if program is None:
            raise ProgramNotFoundException(program_id)

        if year_level.program_id != program_id:
            raise YearLevelMismatchException(year_level_id, program_id)

        return year_level, program

    async def _resolve_import_year_level(
        self, program_id: int, raw: str
    ) -> YearLevel | None:
        """Match a CSV year_level cell to a YearLevel of the program.

        Accepts a year_number ("1") or a label ("1st Year",
        case-insensitive). Returns None when nothing matches so the caller
        can report a per-line error.
        """
        levels: Sequence[YearLevel] = await self._years.list(program_id=program_id)
        text: str = raw.strip()

        if text.isdigit():
            for level in levels:
                if level.year_number == int(text):
                    return level

            return None

        lowered: str = text.lower()

        for level in levels:
            if level.label.lower() == lowered:
                return level

        return None

    async def _scan_count(self, student_pk: int) -> int:
        return (
            await self._session.scalar(
                select(func.count())
                .select_from(Attendance)
                .where(Attendance.student_id == student_pk)
            )
            or 0
        )

    async def _to_read(self, student: Student) -> StudentRead:
        year_level: YearLevel = await self._year_level(student.year_level_id)
        program: Program | None = await self._session.get(
            Program, year_level.program_id
        )

        return StudentRead(
            id=student.id,
            student_id=student.student_id,
            first_name=student.first_name,
            middle_name=student.middle_name,
            last_name=student.last_name,
            email=student.email,
            program_id=year_level.program_id,
            year_level_id=student.year_level_id,
            program_code=program.code if program is not None else "",
            year_level_label=year_level.label,
            section=student.section,
            is_active=student.is_active,
            claim_status="Claimed" if student.user_id is not None else "Unclaimed",
            face_enrolled=student.face_embedding is not None,
            created_at=student.created_at,
            scan_count=await self._scan_count(student.id),
        )

    async def _to_detail(self, student: Student) -> StudentDetail:
        read: StudentRead = await self._to_read(student)

        return StudentDetail(
            **read.model_dump(),
            student_number=student.student_id,
            face_enrolled_at=student.face_enrolled_at,
            face_embedding_version=student.face_embedding_version or 0,
        )

    @staticmethod
    def _apply_order(
        stmt: Select[tuple[Student]], *, sort_by: str | None, sort_dir: str | None
    ) -> Select[tuple[Student]]:
        columns: tuple[Any, ...] | None = _STUDENT_SORT_COLUMNS.get(sort_by or "")

        if columns is None:
            return stmt.order_by(Student.id)

        desc: bool = (sort_dir or "asc").lower() == "desc"
        ordered = [col.desc() if desc else col.asc() for col in columns]

        return stmt.order_by(*ordered, Student.id.asc())
