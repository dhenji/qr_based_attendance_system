from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    PROFESSOR = "professor"
    STUDENT = "student"


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
