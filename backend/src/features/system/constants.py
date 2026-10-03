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
