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
    VALID = "valid"
    PENDING = "pending"
    REJECTED = "rejected"


class SyncStatus(StrEnum):
    SYNCED = "synced"
    PENDING = "pending"
    FAILED = "failed"


class QueueStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
