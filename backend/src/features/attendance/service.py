from __future__ import annotations

import csv
import io
import math
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from core.config import Settings, get_settings
from features.attendance.constants import (
    EAR_MEAN_MAX,
    EAR_MEAN_MIN,
    HISTORY_DEFAULT_SORT_BY,
    HISTORY_DEFAULT_SORT_DIR,
    HISTORY_SORT_DIRS,
    HISTORY_SORT_FIELDS,
    IDEMPOTENCY_TTL_SECONDS,
    OVERVIEW_TREND_EPSILON,
    RECENT_SCANS_MAX_LIMIT,
    REVIEW_DECISIONS,
    REVIEW_DEFAULT_STATUS,
    REVIEW_NOTE_EVIDENCE_KEY,
    REVIEW_STATUSES,
    SYNC_STALE_SECONDS,
    _IDEMPOTENCY_MAX_ENTRIES,
)
from features.attendance.exceptions import (
    AttendanceDomainException,
    FaceMismatchException,
    LivenessFailedException,
    OutsideGeofenceException,
    ReviewNotFoundException,
    ReviewNotPendingException,
    StudentNumberMismatchException,
)
from features.attendance.model import Attendance
from features.attendance.schema import (
    GPSInput,
    HistoryCounts,
    HistoryItem,
    HistoryResponse,
    HistorySummary,
    LivenessEvidence,
    LivenessReviewItem,
    OverviewItem,
    OverviewResponse,
    PrecheckRequest,
    PrecheckResponse,
    RecentScanItem,
    RecentScansResponse,
    ResolveReviewResponse,
    ScanRequest,
    ScanResponse,
)
from features.course.model import Course, CourseOffering
from features.course_professor.model import CourseProfessor
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
from shared.audit import record_audit
from shared.enums import (
    AuditAction,
    AuditEntity,
    QueueStatus,
    SyncStatus,
    ValidationStatus,
)
from shared.pagination import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PaginatedResponse,
)
from shared.query import apply_if
from shared.rates import attendance_rates

EARTH_RADIUS_METERS: float = 6371000.0

# Scan idempotency cache, keyed by "user_id:session_id:caller-supplied key"
# and valued as a monotonic deadline. Scoping the key by student and session is
# what stops one student's replay from being served another student's cached
# response; the deadline and the prune stop the map growing without bound (it is
# process-local, so a multi-instance deployment still needs a shared store -
# see shared/rate_limit.py for the same caveat).
_IDEMPOTENCY_STORE: dict[str, tuple[float, ScanResponse]] = {}


@dataclass(frozen=True, kw_only=True)
class _HistoryFilters:
    """The one filter set shared by the record, enrolled, and scanned queries.

    `status` narrows the record query only — the enrolled/scanned denominators
    are deliberately status-agnostic, which is why the whole set is passed
    rather than each helper taking the subset it happens to use.
    """

    program_id: int | None = None
    year_level_id: int | None = None
    semester: str | None = None
    course_id: int | None = None
    status: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value


def _haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
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


def _validate_liveness_evidence(evidence: LivenessEvidence) -> bool:
    """Grade the fixed blink -> left -> right challenge (D31)."""
    if not (
        evidence.blink_detected and evidence.head_turn_left and evidence.head_turn_right
    ):
        return False

    if not evidence.ear_samples:
        return False

    mean_ear: float = sum(evidence.ear_samples) / len(evidence.ear_samples)

    if not EAR_MEAN_MIN <= mean_ear <= EAR_MEAN_MAX:
        return False

    return bool(evidence.pnp_evidence)


def _idempotency_key_for(user_id: int, session_id: int, key: str | None) -> str | None:
    return None if key is None else f"{user_id}:{session_id}:{key}"


def _prune_idempotency(now: float) -> None:
    """Drop expired entries once the map outgrows its cap."""

    if len(_IDEMPOTENCY_STORE) <= _IDEMPOTENCY_MAX_ENTRIES:
        return

    for cache_key, (deadline, _) in list(_IDEMPOTENCY_STORE.items()):
        if deadline <= now:
            del _IDEMPOTENCY_STORE[cache_key]


def _cached_response(cache_key: str | None) -> ScanResponse | None:
    if cache_key is None:
        return None

    entry: tuple[float, ScanResponse] | None = _IDEMPOTENCY_STORE.get(cache_key)

    if entry is None:
        return None

    deadline, response = entry

    if deadline <= time.monotonic():
        # Expired: fall through and re-process rather than replaying a stale
        # response for a submission that could now be well outside its window.
        del _IDEMPOTENCY_STORE[cache_key]
        return None

    return response


def _store_response(cache_key: str | None, response: ScanResponse) -> None:
    if cache_key is None:
        return

    now: float = time.monotonic()
    _IDEMPOTENCY_STORE[cache_key] = (now + IDEMPOTENCY_TTL_SECONDS, response)
    _prune_idempotency(now)


async def _keyed_by_id[M: DeclarativeBase](
    session: AsyncSession, model: type[M], ids: set[int]
) -> dict[int, M]:
    """Load a lookup map, skipping the query entirely when `ids` is empty.

    `_load_review_maps` chains these (students -> sessions -> offerings ->
    courses) to hydrate a page of rows without a query per row.
    """
    if not ids:
        return {}

    return {
        obj.id: obj
        for obj in (
            await session.scalars(select(model).where(model.id.in_(ids)))
        ).all()
    }


_HISTORY_COUNT_FIELDS: dict[str, str] = {
    "present": ValidationStatus.PRESENT.value,
    "late": ValidationStatus.LATE.value,
    "excused": ValidationStatus.EXCUSED.value,
    "rejected": ValidationStatus.REJECTED.value,
}


def _pending_review_filter(stmt: Select[Any]) -> Select[Any]:
    return stmt.where(Attendance.validation_status == ValidationStatus.PENDING.value)


def _approved_review_filter(stmt: Select[Any]) -> Select[Any]:
    return stmt.where(
        Attendance.validation_status.in_(
            [ValidationStatus.PRESENT.value, ValidationStatus.LATE.value]
        ),
        Attendance.original_status.is_not(None),
    )


def _rejected_review_filter(stmt: Select[Any]) -> Select[Any]:
    return stmt.where(
        Attendance.validation_status == ValidationStatus.REJECTED.value,
        Attendance.original_status.is_not(None),
    )


_REVIEW_FILTERS: dict[str, Callable[[Select[Any]], Select[Any]]] = {
    "pending": _pending_review_filter,
    "approved": _approved_review_filter,
    "rejected": _rejected_review_filter,
}


class AttendanceService:
    """Student scan submissions (online + offline-sync replay).

    Only ``flush()`` is used here; commit/rollback stays in the
    request dependency.
    """

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()

    async def _resolve_scan_parties(
        self,
        session_id: int,
        scanned_at: datetime,
        now: datetime,
        user_id: int,
        student_number: str,
    ) -> tuple[Session, Student]:
        db_session: Session = await self._get_active_session(
            session_id, scanned_at, now
        )
        student: Student = await self._get_active_student(
            user_id, student_number, db_session.offering_id
        )
        await self._require_enrollment(student.id, db_session.offering_id)
        await self._require_no_duplicate(student.id, db_session.id)
        return db_session, student

    def _decide_scan_outcome(
        self, db_session: Session, scanned_at: datetime, face_match_score: float
    ) -> tuple[str, str | None, bool]:
        review: bool = self._is_review_band(face_match_score)
        computed: str = self._compute_status(db_session, scanned_at)
        status: str = ValidationStatus.PENDING.value if review else computed
        original: str | None = computed if review else None
        return status, original, review

    async def _persist_scan(
        self,
        payload: ScanRequest,
        student_id: int,
        db_session: Session,
        scanned_at: datetime,
        status: str,
        review: bool,
        original: str | None,
        now: datetime,
        cache_key: str | None,
        idempotency_key: str | None,
    ) -> ScanResponse:
        """Write the attendance row and build the response.

        Takes the already-loaded `db_session` rather than an id so
        `expires_at` never reads `row.session`: that relationship declares
        no `lazy=`, so touching it on a freshly-flushed row would raise
        MissingGreenlet in async (coding-standards §1.6). It resolved
        before only because the same request had incidentally loaded this
        Session into the identity map.
        """
        row: Attendance = await self._write_attendance(
            payload, student_id, db_session.id, scanned_at, status, review, original
        )
        await self._maybe_record_sync(
            db_session.id, student_id, row.id, scanned_at, now, idempotency_key
        )

        response = ScanResponse(
            id=row.id,
            status=status,  # type: ignore[arg-type]
            scanned_at=row.timestamp,
            expires_at=db_session.expires_at,
        )
        _store_response(cache_key, response)
        return response

    async def submit_scan(
        self,
        *,
        payload: ScanRequest,
        user_id: int,
        idempotency_key: str | None = None,
    ) -> ScanResponse:
        cache_key: str | None = _idempotency_key_for(
            user_id, payload.session_id, idempotency_key
        )
        cached: ScanResponse | None = _cached_response(cache_key)

        if cached is not None:
            return cached

        now: datetime = _utcnow()
        scanned_at: datetime = _ensure_aware(payload.scanned_at)

        db_session, student = await self._resolve_scan_parties(
            payload.session_id, scanned_at, now, user_id, payload.student_number
        )

        if not self._settings.benchmark_mode:
            # Load profile: skip the geofence + liveness gates so a benchmark
            # run measures routing + persistence, not sensor checks.
            self._validate_geofence(db_session, payload.gps)
            self._validate_liveness(payload.liveness_evidence)

        status, original, review = self._decide_scan_outcome(
            db_session, scanned_at, payload.face_match_score
        )

        return await self._persist_scan(
            payload,
            student.id,
            db_session,
            scanned_at,
            status,
            review,
            original,
            now,
            cache_key,
            idempotency_key,
        )

    async def precheck_scan(
        self, *, session_id: int, user_id: int, student_number: str
    ) -> PrecheckResponse:
        """Read-only pre-check: validates session, enrollment, and duplicate scan.

        Does not write attendance_records or sync_queue rows.
        """
        now: datetime = _utcnow()

        db_session: Session = await self._get_active_session(session_id, now, now)

        student: Student = await self._get_active_student(
            user_id, student_number, db_session.offering_id
        )

        enrolled: bool = True
        try:
            await self._require_enrollment(student.id, db_session.offering_id)
        except NotEnrolledException:
            enrolled = False

        already_scanned: bool = False
        try:
            await self._require_no_duplicate(student.id, db_session.id)
        except DuplicateScanException:
            already_scanned = True

        return PrecheckResponse(
            enrolled=enrolled,
            already_scanned=already_scanned,
            student={
                "student_id": student.student_id,
                "name": f"{student.first_name} {student.last_name}",
                "section": student.section,
            },
        )

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
        self, user_id: int, student_number: str, offering_id: int
    ) -> Student:
        """Resolve the scanning student from the *authenticated* user.

        `student_number` is still read off the body because the contract
        documents it (api-contracts.md:935), but it is only ever used to
        check the body against the token - never to select the row. Keying
        the lookup off the payload instead would let any authenticated
        student submit or replay a scan as somebody else.
        """

        student: Student | None = (
            await self._session.scalars(
                select(Student).where(Student.user_id == user_id).limit(1)
            )
        ).one_or_none()

        if student is None:
            # A STUDENT-role user with no linked `students` row. There is no
            # student number to name here, so the id in the message is the
            # account id; the 404 `student_not_found` code still holds.
            raise StudentNotFoundException(user_id)

        # `students.student_id` is upper-cased on write (StudentCreate
        # normalizes it) while the request field is only stripped, so the
        # comparison has to be case-insensitive.
        if (student.student_id or "").upper() != student_number.strip().upper():
            raise StudentNumberMismatchException(student_number, student.student_id)

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

        distance: float = _haversine_distance(
            gps.lat, gps.lng, session.classroom_lat, session.classroom_lng
        )

        if distance > session.classroom_radius_meters:
            raise OutsideGeofenceException(distance, session.classroom_radius_meters)

    def _validate_liveness(self, evidence: LivenessEvidence) -> None:
        if not _validate_liveness_evidence(evidence):
            raise LivenessFailedException()

    def _is_review_band(self, score: float) -> bool:
        threshold: float = self._settings.face_match_threshold
        review_low: float = self._settings.face_review_band_low

        if score < review_low:
            raise FaceMismatchException(score, threshold)

        return score < threshold

    def _compute_status(self, session: Session, scanned_at: datetime) -> str:
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
        original_status: str | None = None,
    ) -> Attendance:
        row = Attendance(
            student_id=student_id,
            session_id=session_id,
            timestamp=scanned_at,
            gps_lat=payload.gps.lat,
            gps_lng=payload.gps.lng,
            validation_status=status,
            original_status=original_status,
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

        # The row is queued, not archived: nothing has processed it yet, so it
        # is what the active-session and system-settings pending counts report
        # and what an operator's forced sync picks up. Replaying it is safe
        # because the original idempotency key travels with it, so the replay
        # returns the result already recorded here.
        self._session.add(
            SyncQueue(
                record_data={
                    "session_id": session_id,
                    "student_id": student_id,
                    "attendance_id": attendance_id,
                    "scanned_at": scanned_at.isoformat(),
                    "idempotency_key": idempotency_key,
                },
                status=QueueStatus.PENDING.value,
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
        page: int = DEFAULT_PAGE,
        size: int = DEFAULT_PAGE_SIZE,
    ) -> HistoryResponse:
        """Student history: filter -> count -> summarize -> paginate."""
        page, size = self._normalize_history_paging(page, size)
        student = await self._history_student(user_id)
        sort_key, desc = self._history_sort(sort_by, sort_dir)
        filters = _HistoryFilters(
            program_id=program_id,
            year_level_id=year_level_id,
            semester=semester,
            course_id=course_id,
            status=status,
            date_from=date_from,
            date_to=date_to,
        )

        filtered = self._apply_history_filters(self._history_base(student.id), filters)
        total = await self._history_total(filtered)
        tallies = await self._history_tallies(filtered)
        summary = self._summarize_history(
            tallies,
            await self._history_enrolled(student.id, filters),
            await self._history_scanned(student.id, filters),
        )
        records = await self._history_page(filtered, sort_key, desc, page, size)

        return await self._build_history_response(
            records=records, total=total, page=page, size=size, summary=summary
        )

    def _normalize_history_paging(self, page: int, size: int) -> tuple[int, int]:
        page = max(page, 1)
        size = min(max(size, 1), MAX_PAGE_SIZE)
        return page, size

    def _summarize_history(
        self, tallies: dict[str, int], enrolled: int, scanned: int
    ) -> HistorySummary:
        counts = HistoryCounts(
            **{
                name: tallies.get(status, 0)
                for name, status in _HISTORY_COUNT_FIELDS.items()
            }
        )
        absent = max(0, enrolled - scanned)
        compliance, participation = attendance_rates(
            present=counts.present,
            late=counts.late,
            excused=counts.excused,
            enrolled=enrolled,
        )
        return HistorySummary(
            compliance_rate=compliance,
            participation_rate=participation,
            counts=HistoryCounts(
                present=counts.present,
                late=counts.late,
                absent=absent,
                excused=counts.excused,
                rejected=counts.rejected,
            ),
        )

    async def _build_history_response(
        self,
        records: Sequence[Attendance],
        total: int,
        page: int,
        size: int,
        summary: HistorySummary,
    ) -> HistoryResponse:
        return HistoryResponse(
            items=await self._history_items(records),
            total=total,
            page=page,
            size=size,
            summary=summary,
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
        self, stmt: Select[Any], filters: _HistoryFilters
    ) -> Select[Any]:
        stmt = apply_if(
            stmt, filters.program_id, lambda v: CourseOffering.program_id == v
        )
        stmt = apply_if(
            stmt, filters.year_level_id, lambda v: CourseOffering.year_level_id == v
        )
        stmt = apply_if(stmt, filters.semester, lambda v: CourseOffering.semester == v)
        stmt = apply_if(
            stmt, filters.course_id, lambda v: CourseOffering.course_id == v
        )
        stmt = apply_if(
            stmt, filters.status, lambda v: Attendance.validation_status == v
        )
        stmt = apply_if(stmt, filters.date_from, lambda v: Attendance.timestamp >= v)
        stmt = apply_if(stmt, filters.date_to, lambda v: Attendance.timestamp <= v)

        return stmt

    async def _history_total(self, filtered: Select[Any]) -> int:
        return (
            await self._session.scalar(
                select(func.count()).select_from(filtered.subquery())
            )
            or 0
        )

    async def _history_tallies(self, filtered: Select[Any]) -> dict[str, int]:
        """Per-status counts over the filtered set.

        The status column has to be read off the subquery. Selecting
        `Attendance.validation_status` while selecting *from* the subquery
        would add `attendance_records` as a second FROM element, silently
        cross-joining the whole table into the group-by and producing rates
        above 1.0.
        """
        scoped = filtered.subquery()
        status = scoped.c.validation_status

        rows: Sequence[tuple[str, int]] = (
            await self._session.execute(
                select(status, func.count()).select_from(scoped).group_by(status)
            )
        ).all()  # type: ignore[assignment]

        return {found: count for found, count in rows}

    async def _history_enrolled(self, student_id: int, filters: _HistoryFilters) -> int:
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
        stmt = self._apply_offering_scope(stmt, filters)
        stmt = apply_if(stmt, filters.date_from, lambda v: Session.created_at >= v)
        stmt = apply_if(stmt, filters.date_to, lambda v: Session.created_at <= v)

        return (await self._session.scalar(stmt)) or 0  # type: ignore[arg-type]

    async def _history_scanned(self, student_id: int, filters: _HistoryFilters) -> int:
        stmt: Select[Any] = (
            select(func.count(Attendance.id))
            .select_from(Attendance)
            .join(Session, Session.id == Attendance.session_id)
            .join(CourseOffering, CourseOffering.id == Session.offering_id)
            .where(Attendance.student_id == student_id)
        )
        stmt = self._apply_offering_scope(stmt, filters)
        stmt = apply_if(stmt, filters.date_from, lambda v: Attendance.timestamp >= v)
        stmt = apply_if(stmt, filters.date_to, lambda v: Attendance.timestamp <= v)

        return (await self._session.scalar(stmt)) or 0  # type: ignore[arg-type]

    def _apply_offering_scope(
        self, stmt: Select[Any], filters: _HistoryFilters
    ) -> Select[Any]:
        """The offering-scoped half of the filter set, without `status`.

        The enrolled/scanned denominators must stay status-agnostic, so they
        take the offering scope only — applying `status` here would silently
        change the compliance-rate denominator.
        """
        stmt = apply_if(
            stmt, filters.program_id, lambda v: CourseOffering.program_id == v
        )
        stmt = apply_if(
            stmt, filters.year_level_id, lambda v: CourseOffering.year_level_id == v
        )
        stmt = apply_if(stmt, filters.semester, lambda v: CourseOffering.semester == v)
        stmt = apply_if(
            stmt, filters.course_id, lambda v: CourseOffering.course_id == v
        )

        return stmt

    async def _history_page(
        self,
        filtered: Select[Any],
        sort_key: str,
        desc: bool,
        page: int,
        size: int,
    ) -> Sequence[Attendance]:
        stmt: Select[Any] = self._history_ordered(filtered, sort_key, desc)

        return (
            await self._session.scalars(stmt.offset((page - 1) * size).limit(size))
        ).all()

    @staticmethod
    def _history_ordered(
        filtered: Select[Any], sort_key: str, desc: bool
    ) -> Select[Any]:
        """Apply the history sort, with `Attendance.id` as the tie-breaker.

        Split out of `_history_page` so the CSV export can order the full set
        without inheriting the pagination it must not apply.
        """

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

        return filtered.order_by(*ordered, tie)

    async def _history_items(self, records: Sequence[Attendance]) -> list[HistoryItem]:
        if not records:
            return []

        session_map: dict[int, Session] = await _keyed_by_id(
            self._session, Session, {r.session_id for r in records}
        )
        offering_map: dict[int, CourseOffering] = await _keyed_by_id(
            self._session,
            CourseOffering,
            {s.offering_id for s in session_map.values()},
        )
        course_map: dict[int, Course] = await _keyed_by_id(
            self._session, Course, {o.course_id for o in offering_map.values()}
        )

        items: list[HistoryItem] = []

        for record in records:
            db_session = session_map.get(record.session_id)
            offering = offering_map.get(db_session.offering_id) if db_session else None
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

    async def _review_stmt(self, key: str) -> Select[Any]:
        return _REVIEW_FILTERS[key](select(Attendance))

    async def _review_page(
        self, stmt: Select[Any], page: int, size: int
    ) -> tuple[Sequence[Attendance], int]:
        total: int = (
            await self._session.scalar(
                select(func.count()).select_from(stmt.subquery())
            )
            or 0
        )
        records: Sequence[Attendance] = (
            await self._session.scalars(
                stmt.order_by(Attendance.timestamp.desc(), Attendance.id.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
        ).all()
        return records, total

    async def _load_review_maps(self, records: Sequence[Attendance]) -> tuple[
        dict[int, Student],
        dict[int, Session],
        dict[int, CourseOffering],
        dict[int, Course],
    ]:
        students: dict[int, Student] = await _keyed_by_id(
            self._session, Student, {r.student_id for r in records}
        )
        sessions: dict[int, Session] = await _keyed_by_id(
            self._session, Session, {r.session_id for r in records}
        )
        offerings: dict[int, CourseOffering] = await _keyed_by_id(
            self._session,
            CourseOffering,
            {s.offering_id for s in sessions.values()},
        )
        courses: dict[int, Course] = await _keyed_by_id(
            self._session, Course, {o.course_id for o in offerings.values()}
        )
        return students, sessions, offerings, courses

    def _review_items(
        self,
        records: Sequence[Attendance],
        students: dict[int, Student],
        sessions: dict[int, Session],
        offerings: dict[int, CourseOffering],
        courses: dict[int, Course],
    ) -> list[LivenessReviewItem]:
        items: list[LivenessReviewItem] = []
        for record in records:
            student = students.get(record.student_id)
            db_session = sessions.get(record.session_id)
            if student is None or db_session is None:
                continue
            offering = offerings.get(db_session.offering_id)
            course = courses.get(offering.course_id) if offering else None
            if course is None:
                continue
            items.append(
                LivenessReviewItem(
                    id=record.id,
                    student_number=student.student_id,
                    student_name=f"{student.first_name} {student.last_name}",
                    session_code=db_session.session_code,
                    course_code=course.course_code,
                    face_match_score=(
                        float(record.face_match_score)
                        if record.face_match_score is not None
                        else None
                    ),
                    evidence=dict(record.liveness_evidence or {}),
                    scanned_at=record.timestamp,
                )
            )
        return items

    async def list_liveness_review(
        self,
        *,
        status: str | None = None,
        page: int = DEFAULT_PAGE,
        size: int = DEFAULT_PAGE_SIZE,
    ) -> PaginatedResponse[LivenessReviewItem]:
        key: str = (status or REVIEW_DEFAULT_STATUS).lower()
        if key not in REVIEW_STATUSES:
            raise AttendanceDomainException(
                message=f"Invalid status '{status}'",
                code="invalid_status",
                field="status",
            )
        page = max(page, 1)
        size = min(max(size, 1), MAX_PAGE_SIZE)

        stmt = await self._review_stmt(key)
        records, total = await self._review_page(stmt, page, size)

        if not records:
            return PaginatedResponse[LivenessReviewItem](
                items=[], total=total, page=page, size=size
            )

        students, sessions, offerings, courses = await self._load_review_maps(records)
        items = self._review_items(records, students, sessions, offerings, courses)

        return PaginatedResponse[LivenessReviewItem](
            items=items, total=total, page=page, size=size
        )

    async def _load_pending_review(self, record_id: int) -> tuple[Attendance, dict]:
        row: Attendance | None = await self._session.get(Attendance, record_id)
        if row is None:
            raise ReviewNotFoundException(record_id)

        evidence: dict = dict(row.liveness_evidence or {})
        if row.validation_status != ValidationStatus.PENDING.value or not evidence.get(
            "review", False
        ):
            raise ReviewNotPendingException(record_id)

        return row, evidence

    def _restore_approved_status(self, row: Attendance) -> str:
        restored: str | None = row.original_status
        if restored not in (
            ValidationStatus.PRESENT.value,
            ValidationStatus.LATE.value,
        ):
            # synchronous fallback — cannot be async here; caller fetches session
            # and recomputes if needed
            restored = ValidationStatus.PRESENT.value
        return restored

    async def _resolve_approved_status(self, row: Attendance, record_id: int) -> str:
        """The status an approved record should carry.

        `original_status` is the cheap answer, but a record that was
        originally PRESENT has to be re-evaluated against the session's
        late window, so that one case falls through to a full recompute.
        The session is fetched explicitly — `row.session` would raise
        MissingGreenlet in async (coding-standards §1.6).
        """
        restored: str = self._restore_approved_status(row)

        if restored != ValidationStatus.PRESENT.value:
            return restored

        db_session: Session | None = await self._session.get(Session, row.session_id)

        if db_session is None:
            raise ReviewNotFoundException(record_id)

        recomputed: str = self._compute_status(db_session, _ensure_aware(row.timestamp))

        if recomputed not in (
            ValidationStatus.PRESENT.value,
            ValidationStatus.LATE.value,
        ):
            return ValidationStatus.PRESENT.value

        return recomputed

    async def _apply_resolution(
        self, row: Attendance, evidence: dict, status: str, note: str | None
    ) -> None:
        row.validation_status = status
        evidence.pop("review", None)

        if note is not None:
            evidence[REVIEW_NOTE_EVIDENCE_KEY] = note

        row.liveness_evidence = evidence
        await self._session.flush()

    async def resolve_review(
        self,
        *,
        record_id: int,
        decision: str,
        actor_id: int,
        note: str | None = None,
    ) -> ResolveReviewResponse:
        row, evidence = await self._load_pending_review(record_id)

        if decision not in REVIEW_DECISIONS:
            raise AttendanceDomainException(
                message=f"Invalid decision '{decision}'",
                code="invalid_decision",
                field="decision",
            )

        if decision == "approve":
            status = await self._resolve_approved_status(row, record_id)
        else:
            status = ValidationStatus.REJECTED.value

        previous: str = row.validation_status
        await self._apply_resolution(row, evidence, status, note)

        # Approving restores a computed present/late status and rejecting marks
        # the record `rejected`, so both rewrite a student's attendance outcome
        # on an administrator's judgement. The note alone lives inside
        # `liveness_evidence`; this is what ties the outcome to the person.
        await record_audit(
            self._session,
            actor_id=actor_id,
            action=(
                AuditAction.APPROVE
                if decision == "approve"
                else AuditAction.REJECT
            ),
            entity_type=AuditEntity.ATTENDANCE_RECORD,
            entity_id=row.id,
            old_value={"validation_status": previous},
            new_value={
                "validation_status": row.validation_status,
                "review_note": note,
            },
        )

        return ResolveReviewResponse(
            id=row.id,
            status=ValidationStatus(row.validation_status),  # type: ignore[arg-type]
            reviewed_by=actor_id,
            reviewed_at=_utcnow(),
        )

    async def get_overview(
        self,
        *,
        course_id: int | None = None,
        professor_id: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> OverviewResponse:
        """Per-course sessions, compliance rate, and trend over the filter set."""
        offering_ids: list[int] = await self._overview_offering_ids(
            course_id, professor_id
        )

        if not offering_ids:
            return OverviewResponse(items=[])

        offerings: Sequence[CourseOffering] = (
            await self._session.scalars(
                select(CourseOffering).where(CourseOffering.id.in_(offering_ids))
            )
        ).all()

        if not offerings:
            return OverviewResponse(items=[])

        sessions: Sequence[Session] = await self._overview_sessions(
            offering_ids, date_from, date_to
        )
        enrolled_by_offering: dict[int, set[int]] = (
            await self._overview_enrollments(offering_ids)
        )
        tallies: dict[int, Counter[str]] = await self._overview_tallies(
            [row.id for row in sessions]
        )
        enrolled_by_session: dict[int, int] = {
            row.id: len(enrolled_by_offering.get(row.offering_id, set()))
            for row in sessions
        }
        sessions_by_course: dict[int, list[Session]] = {}

        for row in sessions:
            offering = next((o for o in offerings if o.id == row.offering_id), None)

            if offering is None:
                continue

            sessions_by_course.setdefault(offering.course_id, []).append(row)

        course_ids: list[int] = sorted({offering.course_id for offering in offerings})
        course_map: dict[int, Course] = (
            {
                row.id: row
                for row in (
                    await self._session.scalars(
                        select(Course).where(Course.id.in_(course_ids))
                    )
                ).all()
            }
            if course_ids
            else {}
        )
        items: list[OverviewItem] = []

        for current_id in course_ids:
            course_sessions: list[Session] = sorted(
                sessions_by_course.get(current_id, []),
                key=lambda row: (_ensure_aware(row.created_at), row.id),
            )
            course: Course | None = course_map.get(current_id)
            expected: int = sum(
                enrolled_by_session.get(row.id, 0) for row in course_sessions
            )
            present, late, excused = self._overview_status_counts(
                course_sessions, tallies
            )
            # One rate definition (shared.rates): compliance is present/expected.
            avg_rate: float = attendance_rates(
                present=present, late=late, excused=excused, enrolled=expected
            )[0]

            items.append(
                OverviewItem(
                    course_id=current_id,
                    course_code=course.course_code if course else "",
                    course_name=course.course_name if course else "",
                    sessions_count=len(course_sessions),
                    avg_rate=avg_rate,
                    trend=self._overview_trend(
                        course_sessions, tallies, enrolled_by_session
                    ),
                )
            )

        items.sort(key=lambda item: (item.course_code, item.course_id))

        return OverviewResponse(items=items)

    async def _overview_offering_ids(
        self, course_id: int | None, professor_id: int | None
    ) -> list[int]:
        stmt = select(CourseOffering.id)
        stmt = apply_if(stmt, course_id, lambda v: CourseOffering.course_id == v)

        if professor_id is not None:
            today: date = datetime.now(timezone.utc).date()
            assigned = (
                select(CourseProfessor.offering_id)
                .where(CourseProfessor.professor_id == professor_id)
                .where(CourseProfessor.effective_from <= today)
                .where(
                    (CourseProfessor.effective_to.is_(None))
                    | (CourseProfessor.effective_to >= today)
                )
            )
            stmt = stmt.where(CourseOffering.id.in_(assigned))

        return list((await self._session.scalars(stmt)).all())

    async def _overview_sessions(
        self,
        offering_ids: list[int],
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> Sequence[Session]:
        if not offering_ids:
            return []

        stmt = select(Session).where(Session.offering_id.in_(offering_ids))
        stmt = apply_if(stmt, date_from, lambda v: Session.created_at >= v)
        stmt = apply_if(stmt, date_to, lambda v: Session.created_at <= v)

        return (await self._session.scalars(stmt)).all()

    async def _overview_enrollments(
        self, offering_ids: list[int]
    ) -> dict[int, set[int]]:
        if not offering_ids:
            return {}

        rows: Sequence[tuple[int, int]] = (
            await self._session.execute(
                select(Enrollment.offering_id, Enrollment.student_id).where(
                    Enrollment.offering_id.in_(offering_ids)
                )
            )
        ).all()  # type: ignore[assignment]
        grouped: dict[int, set[int]] = {}

        for offering_id, student_id in rows:
            grouped.setdefault(offering_id, set()).add(student_id)

        return grouped

    async def _overview_tallies(
        self, session_ids: list[int]
    ) -> dict[int, Counter[str]]:
        """Validation-status counts keyed by session id."""
        if not session_ids:
            return {}

        rows: Sequence[tuple[int, str, int]] = (
            await self._session.execute(
                select(
                    Attendance.session_id,
                    Attendance.validation_status,
                    func.count(),
                )
                .where(Attendance.session_id.in_(session_ids))
                .group_by(Attendance.session_id, Attendance.validation_status)
            )
        ).all()  # type: ignore[assignment]

        tallies: dict[int, Counter[str]] = {}
        for session_id, status, count in rows:
            tallies.setdefault(session_id, Counter())[status] = count
        return tallies

    @staticmethod
    def _overview_status_counts(
        ordered: Sequence[Session], tallies: dict[int, Counter[str]]
    ) -> tuple[int, int, int]:
        """Present/late/excused totals across a set of sessions."""
        present = late = excused = 0
        for row in ordered:
            session_tally = tallies.get(row.id, Counter())
            present += session_tally.get(ValidationStatus.PRESENT.value, 0)
            late += session_tally.get(ValidationStatus.LATE.value, 0)
            excused += session_tally.get(ValidationStatus.EXCUSED.value, 0)
        return present, late, excused

    def _overview_trend(
        self,
        ordered: list[Session],
        tallies: dict[int, Counter[str]],
        enrolled_by_session: dict[int, int],
    ) -> str:
        """Half-split trend: second-half compliance vs first-half compliance."""
        if len(ordered) < 2:
            return "flat"

        mid: int = len(ordered) // 2

        def _rate(rows: list[Session]) -> float:
            enrolled: int = sum(
                enrolled_by_session.get(row.id, 0) for row in rows
            )
            present, late, excused = self._overview_status_counts(rows, tallies)
            return attendance_rates(
                present=present, late=late, excused=excused, enrolled=enrolled
            )[0]

        first: list[Session] = ordered[:mid]
        second: list[Session] = ordered[mid:]
        diff: float = _rate(second) - _rate(first)

        if diff > OVERVIEW_TREND_EPSILON:
            return "up"

        if diff < -OVERVIEW_TREND_EPSILON:
            return "down"

        return "flat"

    async def get_recent_scans(self, *, limit: int = 10) -> RecentScansResponse:
        """Latest scans newest-first, capped by the requested limit."""
        capped: int = min(max(limit, 1), RECENT_SCANS_MAX_LIMIT)
        records: Sequence[Attendance] = (
            await self._session.scalars(
                select(Attendance)
                .order_by(Attendance.timestamp.desc(), Attendance.id.desc())
                .limit(capped)
            )
        ).all()

        if not records:
            return RecentScansResponse(items=[])

        students, sessions, offerings, courses = await self._load_review_maps(
            records
        )
        items: list[RecentScanItem] = []

        for record in records:
            student = students.get(record.student_id)
            db_session = sessions.get(record.session_id)

            if student is None or db_session is None:
                continue

            offering = offerings.get(db_session.offering_id)
            course = courses.get(offering.course_id) if offering else None

            if course is None:
                continue

            items.append(
                RecentScanItem(
                    id=record.id,
                    scanned_at=record.timestamp,
                    student_name=" ".join(
                        part
                        for part in (
                            student.first_name,
                            student.middle_name,
                            student.last_name,
                        )
                        if part
                    ),
                    course_code=course.course_code,
                    status=record.validation_status,
                )
            )

        return RecentScansResponse(items=items)

    async def export_overview_csv(
        self,
        *,
        course_id: int | None = None,
        professor_id: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> str:
        """Full overview filter set rendered as CSV text for download."""
        overview: OverviewResponse = await self.get_overview(
            course_id=course_id,
            professor_id=professor_id,
            date_from=date_from,
            date_to=date_to,
        )
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "course_id",
                "course_code",
                "course_name",
                "sessions_count",
                "avg_rate",
                "trend",
            ]
        )

        for item in overview.items:
            writer.writerow(
                [
                    item.course_id,
                    item.course_code,
                    item.course_name,
                    item.sessions_count,
                    item.avg_rate,
                    item.trend,
                ]
            )

        return buffer.getvalue()

    async def export_history_csv(
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
    ) -> str:
        """Full history filter set rendered as CSV text for download.

        Every matching row, never one page. The paginated endpoint stops at
        MAX_PAGE_SIZE, so borrowing its query would hand back a file that
        silently disagrees with the `total` the student was just shown;
        `_history_ordered` gives the sort without the limit.

        Generation and file persistence stay separate -- this returns text, the
        router streams it.
        """
        student: Student = await self._history_student(user_id)
        sort_key, desc = self._history_sort(sort_by, sort_dir)
        filters = _HistoryFilters(
            program_id=program_id,
            year_level_id=year_level_id,
            semester=semester,
            course_id=course_id,
            status=status,
            date_from=date_from,
            date_to=date_to,
        )

        filtered = self._apply_history_filters(self._history_base(student.id), filters)

        records: Sequence[Attendance] = (
            await self._session.scalars(
                self._history_ordered(filtered, sort_key, desc)
            )
        ).all()

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "id",
                "session_id",
                "course_code",
                "course_name",
                "status",
                "original_status",
                "excuse_reason",
                "scanned_at",
                "scanned_via",
            ]
        )

        for item in await self._history_items(records):
            writer.writerow(
                [
                    item.id,
                    item.session_id,
                    item.course_code,
                    item.course_name,
                    # `.value` because `HistoryItem` types these as
                    # `ValidationStatus`; the sibling exports write plain
                    # scalars, so the cell has to be text either way.
                    item.status.value,
                    item.original_status.value if item.original_status else "",
                    item.excuse_reason or "",
                    # isoformat, not `str(datetime)`: the reports export does
                    # the same, and `csv.writer` would otherwise emit a
                    # space-separated value that no spreadsheet parses as a date.
                    item.scanned_at.isoformat(),
                    item.scanned_via or "",
                ]
            )

        return buffer.getvalue()
