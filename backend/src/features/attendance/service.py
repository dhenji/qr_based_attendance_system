import math
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from features.attendance.constants import SYNC_STALE_SECONDS
from features.attendance.exceptions import (
    FaceMismatchException,
    LivenessFailedException,
    OutsideGeofenceException,
)
from features.attendance.model import Attendance
from features.attendance.schema import (
    GPSInput,
    LivenessEvidence,
    ScanRequest,
    ScanResponse,
)
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
