from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    PROFESSOR = "professor"
    STUDENT = "student"


class AuditEntity(StrEnum):
    """The `entity_type` vocabulary of the audit trail.

    The column is free-form `String(50)`, so this enum is the contract rather
    than a database constraint: adding a member is a code change, and the
    reader endpoint rejects a filter outside it.
    """

    PROGRAM = "program"
    YEAR_LEVEL = "year_level"
    COURSE = "course"
    COURSE_OFFERING = "course_offering"
    STUDENT = "student"
    PROFESSOR = "professor"
    ENROLLMENT = "enrollment"
    COURSE_PROFESSOR = "course_professor"
    EXCUSE = "excuse"
    SESSION = "session"
    FACE_ENROLLMENT = "face_enrollment"
    ATTENDANCE_RECORD = "attendance_record"
    BACKUP = "backup"
    APP_SETTING = "app_setting"
    USER = "user"
    # Aggregate subject for the maintenance runs (sync flush, expired-data
    # cleanup): one audit row per run, with the per-table counts in
    # `new_value`, so a large backlog cannot bury the rest of the trail.
    MAINTENANCE = "maintenance"


class AuditAction(StrEnum):
    """The `action` vocabulary of the audit trail. See `AuditEntity`."""

    CREATE = "create"
    UPDATE = "update"
    ARCHIVE = "archive"
    DELETE = "delete"
    IMPORT = "import"
    ENROLL = "enroll"
    UNENROLL = "unenroll"
    ASSIGN = "assign"
    UNASSIGN = "unassign"
    OPEN = "open"
    CLOSE = "close"
    APPROVE = "approve"
    REJECT = "reject"
    REVOKE = "revoke"
    LOCK = "lock"
    UNLOCK = "unlock"
    LOGIN_FAILED = "login_failed"
    PASSWORD_RESET = "password_reset"


class OtpPurpose(StrEnum):
    CLAIM = "claim"
    FORGET_PASSWORD = "forget_password"
    LOGIN = "login"


class ValidationStatus(StrEnum):
    PRESENT = "present"
    LATE = "late"
    ABSENT = "absent"
    EXCUSED = "excused"
    PENDING = "pending"
    REJECTED = "rejected"


class ExcuseInitiatedBy(StrEnum):
    PROFESSOR = "professor"
    STUDENT = "student"


class ExcuseInitiatedVia(StrEnum):
    QUICK = "quick"
    PROF_WITH_EVIDENCE = "prof_with_evidence"
    REQUEST = "request"


class ExcuseStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class BackupKind(StrEnum):
    FULL = "full"
    ANALYTICS = "analytics"


class BackupStorage(StrEnum):
    LOCAL = "local"
    S3 = "s3"


class BackupStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class ScannedVia(StrEnum):
    QR_CAMERA = "qr_camera"
    MANUAL_CODE = "manual_code"


class SessionType(StrEnum):
    """Lecture vs laboratory session/component vocabulary (D77).

    Stored as free-form `String(20)` with a CHECK constraint, mirroring how
    `ValidationStatus` is handled: the enum is the contract, the database
    only guards the value set.
    """

    LECTURE = "lecture"
    LAB = "lab"


class SyncStatus(StrEnum):
    SYNCED = "synced"
    PENDING = "pending"
    FAILED = "failed"


class QueueStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
