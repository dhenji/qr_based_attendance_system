"""Bounds and filenames for the database backup pipeline."""

from __future__ import annotations

# Work files inside the per-run temp directory. Stages communicate through
# files rather than pipes, so a large database is never buffered in memory.
WORK_DUMP_NAME: str = "backup.dump"
WORK_GZ_NAME: str = "backup.dump.gz"

# Companion integrity file written next to each stored blob.
SIDECAR_SUFFIX: str = ".sha256"

# Bytes per read when hashing the encrypted blob.
READ_CHUNK_BYTES: int = 1024 * 64

# How much of a failed tool's stderr lands in the raised message / log row.
STDERR_TAIL_CHARS: int = 500
ERROR_MAX_CHARS: int = 2000

# gzip level clamp; the configured level is pinned into this range.
GZIP_LEVEL_MIN: int = 1
GZIP_LEVEL_MAX: int = 9

# Fallback when the configured prefix is empty; mirrors the Settings default.
S3_PREFIX_FALLBACK: str = "backups/"

# Owner-only blobs on the local backend.
LOCAL_FILE_MODE: int = 0o600

# System settings keys persisted in the app_settings table. Seeded from
# the matching `core.config.Settings` defaults when a row is missing.
SETTING_GEOFENCE_RADIUS: str = "geofence_default_radius"
SETTING_PRESENT_WINDOW: str = "present_window_default"
SETTING_LATE_WINDOW: str = "late_window_default"
SETTING_RETENTION_DAILY: str = "backup_retention_daily"
SETTING_RETENTION_MONTHLY: str = "backup_retention_monthly"

SETTING_KEY_MAX_LENGTH: int = 100

# Per-setting bounds enforced on PATCH; values are stored as text and
# parsed back to int on read.
GEOFENCE_RADIUS_MIN: int = 10
GEOFENCE_RADIUS_MAX: int = 1000
WINDOW_MIN_MINUTES: int = 1
WINDOW_MAX_MINUTES: int = 120
RETENTION_DAILY_MIN: int = 1
RETENTION_DAILY_MAX: int = 365
RETENTION_MONTHLY_MIN: int = 1
RETENTION_MONTHLY_MAX: int = 120

# Entity types surfaced by GET /admin/system/academic-structure. Assignment
# changes (course_professors) and enrollments are audited separately.
STRUCTURAL_ENTITY_TYPES: tuple[str, ...] = (
    "program",
    "year_level",
    "course",
    "course_offering",
)

# Query-string caps for the GET /admin/audit-logs filters. Both mirror the
# `audit_logs` column widths (`String(50)`); a longer filter could never match a
# stored value, so rejecting it at the edge beats an always-empty page.
ENTITY_TYPE_MAX_LENGTH: int = 50
ACTION_MAX_LENGTH: int = 50

# Timestamped object name for analytics CSVs persisted through backup storage.
EXPORT_FILENAME_PREFIX: str = "analytics_"
