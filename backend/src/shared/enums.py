from enum import StrEnum


class UserRole(StrEnum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    PROFESSOR = "professor"
    STUDENT = "student"


class OtpPurpose(StrEnum):
    CLAIM = "claim"
    FORGET_PASSWORD = "forget_password"


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


class SyncStatus(StrEnum):
    SYNCED = "synced"
    PENDING = "pending"
    FAILED = "failed"


class QueueStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
