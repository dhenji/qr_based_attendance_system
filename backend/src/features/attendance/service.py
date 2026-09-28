import math
from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from features.attendance.constants import (
    HISTORY_DEFAULT_SORT_BY,
    HISTORY_DEFAULT_SORT_DIR,
    HISTORY_SORT_DIRS,
    HISTORY_SORT_FIELDS,
    SYNC_STALE_SECONDS,
)
from features.attendance.exceptions import (
    AttendanceDomainException,
    FaceMismatchException,
    LivenessFailedException,
    OutsideGeofenceException,
)
from features.attendance.model import Attendance
from features.attendance.schema import (
    GPSInput,
    HistoryCounts,
    HistoryItem,
    HistoryResponse,
    HistorySummary,
    LivenessEvidence,
    ScanRequest,
    ScanResponse,
)
from features.course.model import Course, CourseOffering
from features.enrollment.model import Enrollment
from features.session.exceptions import (
    DuplicateScanException,
    SessionExpiredException,
    SessionNotFoundException,
)
from features.session.model import Session
from features.student.exceptions import NotEnrolledException, StudentNotFoundException
from features.student.model import Student
from features.sync.model import SyncQueue
from shared.enums import QueueStatus, SyncStatus, ValidationStatus
from shared.pagination import MAX_PAGE_SIZE
from shared.query import apply_if

EARTH_RADIUS_METERS: float = 6371000.0

_IDEMPOTENCY_STORE: dict[str, ScanResponse] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres between two GPS points."""
    phi1: float = math.radians(lat1)
    phi2: float = math.radians(lat2)
    dphi: float = math.radians(lat2 - lat1)
    dlambda: float = math.radians(lng2 - lng1)
    a: float = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )

    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(a))


def validate_liveness_evidence(evidence: LivenessEvidence) -> bool:
    """Grade the fixed blink -> left -> right challenge (D31)."""
    if not (
        evidence.blink_detected and evidence.head_turn_left and evidence.head_turn_right
    ):
        return False

    if not evidence.ear_samples:
        return False

    mean_ear: float = sum(evidence.ear_samples) / len(evidence.ear_samples)

    if not 0.05 <= mean_ear <= 0.5:
        return False

    return bool(evidence.pnp_evidence)


def _cached_response(key: str | None) -> ScanResponse | None:
    if key is None:
        return None

    return _IDEMPOTENCY_STORE.get(key)


def _store_response(key: str | None, response: ScanResponse) -> None:
    if key is not None:
        _IDEMPOTENCY_STORE[key] = response


class AttendanceService:
    """Student scan submissions (online + offline-sync replay).

    Only ``flush()`` is used here; commit/rollback stays in the
    request dependency.
    """

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()

    async def submit_scan(
        self, *, payload: ScanRequest, idempotency_key: str | None = None
    ) -> ScanResponse:
        cached: ScanResponse | None = _cached_response(idempotency_key)

        if cached is not None:
            return cached

        now: datetime = _utcnow()
        scanned_at: datetime = _ensure_aware(payload.scanned_at)

        db_session: Session = await self._get_active_session(
            payload.session_id, scanned_at, now
        )
        student: Student = await self._get_active_student(
            payload.student_number, db_session.offering_id
        )
        await self._require_enrollment(student.id, db_session.offering_id)
        await self._require_no_duplicate(student.id, db_session.id)

        self._validate_geofence(db_session, payload.gps)
        self._validate_liveness(payload.liveness_evidence)

        review: bool = self._is_review_band(payload.face_match_score)
        status: str = self._compute_status(db_session, scanned_at, review)
        row: Attendance = await self._write_attendance(
            payload, student.id, db_session.id, scanned_at, status, review
        )
        await self._maybe_record_sync(
            db_session.id, student.id, row.id, scanned_at, now, idempotency_key
        )

        response = ScanResponse(
            id=row.id,
            status=status,  # type: ignore[arg-type]
            scanned_at=row.timestamp,
            expires_at=db_session.expires_at,
        )
        _store_response(idempotency_key, response)

        return response

    async def _get_active_session(
        self, session_id: int, scanned_at: datetime, now: datetime
    ) -> Session:
        row: Session | None = await self._session.get(Session, session_id)

        if row is None:
            raise SessionNotFoundException(session_id)

        expires_at: datetime | None = row.expires_at

        if expires_at is None or _ensure_aware(expires_at) <= now:
            raise SessionExpiredException(row.id)

        if scanned_at > _ensure_aware(expires_at):
            raise SessionExpiredException(row.id)

        return row

    async def _get_active_student(
        self, student_number: str, offering_id: int
    ) -> Student:
        student: Student | None = (
            await self._session.scalars(
                select(Student).where(Student.student_id == student_number).limit(1)
            )
        ).one_or_none()

        if student is None:
            raise StudentNotFoundException(student_number)  # type: ignore[arg-type]

        if not student.is_active:
            raise NotEnrolledException(student.id, offering_id)

        return student

    async def _require_enrollment(self, student_id: int, offering_id: int) -> None:
        enrollment: Enrollment | None = (
            await self._session.scalars(
                select(Enrollment)
                .where(
                    Enrollment.student_id == student_id,
                    Enrollment.offering_id == offering_id,
                )
                .limit(1)
            )
        ).one_or_none()

        if enrollment is None:
            raise NotEnrolledException(student_id, offering_id)

    async def _require_no_duplicate(self, student_id: int, session_id: int) -> None:
        existing: Attendance | None = (
            await self._session.scalars(
                select(Attendance)
                .where(
                    Attendance.session_id == session_id,
                    Attendance.student_id == student_id,
                )
                .limit(1)
            )
        ).one_or_none()

        if existing is not None:
            raise DuplicateScanException(student_id, session_id)

    def _validate_geofence(self, session: Session, gps: GPSInput) -> None:
        if session.classroom_lat is None or session.classroom_lng is None:
            return

        distance: float = haversine_distance(
            gps.lat, gps.lng, session.classroom_lat, session.classroom_lng
        )

        if distance > session.classroom_radius_meters:
            raise OutsideGeofenceException(distance, session.classroom_radius_meters)

    def _validate_liveness(self, evidence: LivenessEvidence) -> None:
        if not validate_liveness_evidence(evidence):
            raise LivenessFailedException()

    def _is_review_band(self, score: float) -> bool:
        threshold: float = self._settings.face_match_threshold
        review_low: float = self._settings.face_review_band_low

        if score < review_low:
            raise FaceMismatchException(score, threshold)

        return score < threshold

    def _compute_status(
        self, session: Session, scanned_at: datetime, review: bool
    ) -> str:
        if review:
            return ValidationStatus.PENDING.value

        anchor: datetime = _ensure_aware(
            session.created_at or session.scheduled_start_time
        )
        elapsed_minutes: float = (scanned_at - anchor).total_seconds() / 60.0

        if elapsed_minutes <= session.present_window_minutes:
            return ValidationStatus.PRESENT.value

        if (
            elapsed_minutes
            <= session.present_window_minutes + session.late_window_minutes
        ):
            return ValidationStatus.LATE.value

        return ValidationStatus.REJECTED.value

    def _build_evidence(
        self, evidence: LivenessEvidence, accuracy: float, review: bool
    ) -> dict:
        data: dict = evidence.model_dump()
        data["accuracy"] = accuracy

        if review:
            data["review"] = True

        return data

    async def _write_attendance(
        self,
        payload: ScanRequest,
        student_id: int,
        session_id: int,
        scanned_at: datetime,
        status: str,
        review: bool,
    ) -> Attendance:
        row = Attendance(
            student_id=student_id,
            session_id=session_id,
            timestamp=scanned_at,
            gps_lat=payload.gps.lat,
            gps_lng=payload.gps.lng,
            validation_status=status,
            sync_status=SyncStatus.SYNCED.value,
            liveness_evidence=self._build_evidence(
                payload.liveness_evidence, payload.gps.accuracy, review
            ),
            face_match_score=Decimal(str(payload.face_match_score)),
            scanned_via=payload.scanned_via.value,
        )
        self._session.add(row)
        await self._session.flush()

        return row

    async def _maybe_record_sync(
        self,
        session_id: int,
        student_id: int,
        attendance_id: int,
        scanned_at: datetime,
        now: datetime,
        idempotency_key: str | None,
    ) -> None:
        if (now - scanned_at).total_seconds() <= SYNC_STALE_SECONDS:
            return

        self._session.add(
            SyncQueue(
                record_data={
                    "session_id": session_id,
                    "student_id": student_id,
                    "attendance_id": attendance_id,
                    "scanned_at": scanned_at.isoformat(),
                    "idempotency_key": idempotency_key,
                },
                status=QueueStatus.DONE.value,
                retry_count=0,
            )
        )
        await self._session.flush()

    async def get_history(
        self,
        *,
        user_id: int,
        program_id: int | None = None,
        year_level_id: int | None = None,
        semester: str | None = None,
        course_id: int | None = None,
        status: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        sort_by: str | None = None,
        sort_dir: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> HistoryResponse:
        """Student history: filter -> count -> summarize -> paginate."""
        page = max(page, 1)
        size = min(max(size, 1), MAX_PAGE_SIZE)
        student: Student = await self._history_student(user_id)
        sort_key, desc = self._history_sort(sort_by, sort_dir)

        filtered: Select[Any] = self._apply_history_filters(
            self._history_base(student.id),
            program_id=program_id,
            year_level_id=year_level_id,
            semester=semester,
            course_id=course_id,
            status=status,
            date_from=date_from,
            date_to=date_to,
        )

        total: int = await self._history_total(filtered)
        tallies: dict[str, int] = await self._history_tallies(filtered)
        enrolled: int = await self._history_enrolled(
            student.id,
            program_id=program_id,
            year_level_id=year_level_id,
            semester=semester,
            course_id=course_id,
            date_from=date_from,
            date_to=date_to,
        )
        scanned: int = await self._history_scanned(
            student.id,
            program_id=program_id,
            year_level_id=year_level_id,
            semester=semester,
            course_id=course_id,
            date_from=date_from,
            date_to=date_to,
        )

        present: int = tallies.get(ValidationStatus.PRESENT.value, 0)
        late: int = tallies.get(ValidationStatus.LATE.value, 0)
        excused: int = tallies.get(ValidationStatus.EXCUSED.value, 0)
        rejected: int = tallies.get(ValidationStatus.REJECTED.value, 0)
        absent: int = max(0, enrolled - scanned)
        compliance, participation = self._history_rates(
            present, late, excused, enrolled
        )
        records: Sequence[Attendance] = await self._history_page(
            filtered, sort_key, desc, page, size
        )

        return HistoryResponse(
            items=await self._history_items(records),
            total=total,
            page=page,
            size=size,
            summary=HistorySummary(
                compliance_rate=compliance,
                participation_rate=participation,
                counts=HistoryCounts(
                    present=present,
                    late=late,
                    absent=absent,
                    excused=excused,
                    rejected=rejected,
                ),
            ),
        )

    async def _history_student(self, user_id: int) -> Student:
        student: Student | None = (
            await self._session.scalars(
                select(Student).where(Student.user_id == user_id).limit(1)
            )
        ).one_or_none()

        if student is None:
            raise StudentNotFoundException(user_id)  # type: ignore[arg-type]

        return student

    def _history_sort(
        self, sort_by: str | None, sort_dir: str | None
    ) -> tuple[str, bool]:
        key: str = (sort_by or HISTORY_DEFAULT_SORT_BY).lower()
        direction: str = (sort_dir or HISTORY_DEFAULT_SORT_DIR).lower()

        if key not in HISTORY_SORT_FIELDS:
            raise AttendanceDomainException(
                message=f"Invalid sort_by '{sort_by}'",
                code="invalid_sort",
                field="sort_by",
            )

        if direction not in HISTORY_SORT_DIRS:
            raise AttendanceDomainException(
                message=f"Invalid sort_dir '{sort_dir}'",
                code="invalid_sort",
                field="sort_dir",
            )

        return key, direction != "asc"

    def _history_base(self, student_id: int) -> Select[Any]:
        return (
            select(Attendance)
            .join(Session, Session.id == Attendance.session_id)
            .join(CourseOffering, CourseOffering.id == Session.offering_id)
            .join(Course, Course.id == CourseOffering.course_id)
            .where(Attendance.student_id == student_id)
        )

    def _apply_history_filters(
        self,
        stmt: Select[Any],
        *,
        program_id: int | None,
        year_level_id: int | None,
        semester: str | None,
        course_id: int | None,
        status: str | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> Select[Any]:
        stmt = apply_if(
            stmt, program_id, lambda v: CourseOffering.program_id == v
        )
        stmt = apply_if(
            stmt, year_level_id, lambda v: CourseOffering.year_level_id == v
        )
        stmt = apply_if(stmt, semester, lambda v: CourseOffering.semester == v)
        stmt = apply_if(
            stmt, course_id, lambda v: CourseOffering.course_id == v
        )
        stmt = apply_if(
            stmt, status, lambda v: Attendance.validation_status == v
        )
        stmt = apply_if(
            stmt, date_from, lambda v: Attendance.timestamp >= v
        )
        stmt = apply_if(stmt, date_to, lambda v: Attendance.timestamp <= v)

        return stmt

    async def _history_total(self, filtered: Select[Any]) -> int:
        return (
            await self._session.scalar(
                select(func.count()).select_from(filtered.subquery())
            )
            or 0
        )

    async def _history_tallies(self, filtered: Select[Any]) -> dict[str, int]:
        rows: Sequence[tuple[str, int]] = (
            await self._session.execute(
                select(
                    Attendance.validation_status, func.count(Attendance.id)
                )
                .select_from(filtered.subquery())
                .group_by(Attendance.validation_status)
            )
        ).all()  # type: ignore[assignment]

        return {status: count for status, count in rows}

    async def _history_enrolled(
        self,
        student_id: int,
        *,
        program_id: int | None,
        year_level_id: int | None,
        semester: str | None,
        course_id: int | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> int:
        stmt: Select[Any] = (
            select(func.count(func.distinct(Session.id)))
            .select_from(Session)
            .join(CourseOffering, CourseOffering.id == Session.offering_id)
            .join(
                Enrollment,
                Enrollment.offering_id == Session.offering_id,
            )
            .where(Enrollment.student_id == student_id)
        )
        stmt = self._apply_offering_scope(
            stmt,
            program_id=program_id,
            year_level_id=year_level_id,
            semester=semester,
            course_id=course_id,
        )
        stmt = apply_if(
            stmt, date_from, lambda v: Session.created_at >= v
        )
        stmt = apply_if(stmt, date_to, lambda v: Session.created_at <= v)

        return (await self._session.scalar(stmt)) or 0  # type: ignore[arg-type]

    async def _history_scanned(
        self,
        student_id: int,
        *,
        program_id: int | None,
        year_level_id: int | None,
        semester: str | None,
        course_id: int | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> int:
        stmt: Select[Any] = (
            select(func.count(Attendance.id))
            .select_from(Attendance)
            .join(Session, Session.id == Attendance.session_id)
            .join(CourseOffering, CourseOffering.id == Session.offering_id)
            .where(Attendance.student_id == student_id)
        )
        stmt = self._apply_offering_scope(
            stmt,
            program_id=program_id,
            year_level_id=year_level_id,
            semester=semester,
            course_id=course_id,
        )
        stmt = apply_if(
            stmt, date_from, lambda v: Attendance.timestamp >= v
        )
        stmt = apply_if(stmt, date_to, lambda v: Attendance.timestamp <= v)

        return (await self._session.scalar(stmt)) or 0  # type: ignore[arg-type]

    def _apply_offering_scope(
        self,
        stmt: Select[Any],
        *,
        program_id: int | None,
        year_level_id: int | None,
        semester: str | None,
        course_id: int | None,
    ) -> Select[Any]:
        stmt = apply_if(
            stmt, program_id, lambda v: CourseOffering.program_id == v
        )
        stmt = apply_if(
            stmt, year_level_id, lambda v: CourseOffering.year_level_id == v
        )
        stmt = apply_if(stmt, semester, lambda v: CourseOffering.semester == v)
        stmt = apply_if(
            stmt, course_id, lambda v: CourseOffering.course_id == v
        )

        return stmt

    @staticmethod
    def _history_rates(
        present: int, late: int, excused: int, enrolled: int
    ) -> tuple[float, float]:
        if enrolled <= 0:
            return 0.0, 0.0

        return (
            round(present / enrolled, 4),
            round((present + late + excused) / enrolled, 4),
        )

    async def _history_page(
        self,
        filtered: Select[Any],
        sort_key: str,
        desc: bool,
        page: int,
        size: int,
    ) -> Sequence[Attendance]:
        columns: dict[str, tuple[Any, ...]] = {
            "date": (Attendance.timestamp,),
            "time": (Attendance.timestamp,),
            "course": (Course.course_code, Course.course_name),
            "status": (Attendance.validation_status,),
            "section": (Attendance.timestamp,),
        }
        cols: tuple[Any, ...] = columns.get(sort_key, (Attendance.timestamp,))
        ordered = [c.desc() if desc else c.asc() for c in cols]
        tie = Attendance.id.desc() if desc else Attendance.id.asc()

        return (
            await self._session.scalars(
                filtered.order_by(*ordered, tie)
                .offset((page - 1) * size)
                .limit(size)
            )
        ).all()

    async def _history_items(
        self, records: Sequence[Attendance]
    ) -> list[HistoryItem]:
        if not records:
            return []

        sessions: Sequence[Session] = (
            await self._session.scalars(
                select(Session).where(
                    Session.id.in_({r.session_id for r in records})
                )
            )
        ).all()
        session_map: dict[int, Session] = {s.id: s for s in sessions}

        offerings: Sequence[CourseOffering] = (
            await self._session.scalars(
                select(CourseOffering).where(
                    CourseOffering.id.in_(
                        {s.offering_id for s in sessions}
                    )
                )
            )
        ).all()
        offering_map: dict[int, CourseOffering] = {o.id: o for o in offerings}

        courses: Sequence[Course] = (
            await self._session.scalars(
                select(Course).where(
                    Course.id.in_({o.course_id for o in offerings})
                )
            )
        ).all()
        course_map: dict[int, Course] = {c.id: c for c in courses}

        items: list[HistoryItem] = []

        for record in records:
            db_session = session_map.get(record.session_id)
            offering = (
                offering_map.get(db_session.offering_id) if db_session else None
            )
            course = course_map.get(offering.course_id) if offering else None

            if db_session is None or offering is None or course is None:
                continue

            items.append(
                HistoryItem(
                    id=record.id,
                    session_id=record.session_id,
                    course_code=course.course_code,
                    course_name=course.course_name,
                    status=record.validation_status,  # type: ignore[arg-type]
                    original_status=record.original_status,  # type: ignore[arg-type]
                    excuse_reason=record.excuse_reason,
                    scanned_at=record.timestamp,
                    scanned_via=record.scanned_via,
                )
            )

        return items
