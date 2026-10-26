from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "QR Attendance System API"
    debug: bool = False
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/attendance_sys"
    )
    cors_origins: str = "http://localhost:5173"
    hmac_secret_key: str = ""

    # Client-IP resolution behind proxies. Empty (default) trusts nothing:
    # limiter keys and Turnstile use `request.client.host` exactly as
    # received. Set to the comma-separated CIDRs of your load balancer /
    # ingress when deployed behind one; the leftmost X-Forwarded-For entry is
    # then used, but ONLY when the direct peer is inside those CIDRs — an
    # untrusted peer's header is always ignored, otherwise any client could
    # pick its own rate-limit bucket.
    trusted_proxy_cidrs: str = ""

    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    preauth_token_expire_minutes: int = 5
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    recovery_token_expire_minutes: int = 5

    # Account lockout fields
    lockout_attempts: int = 5
    lockout_duration_minutes: int = 15

    # Face enrollment fields
    face_match_threshold: float = 0.70
    face_review_band_low: float = 0.65
    face_embedding_version: int = 1
    face_embedding_algorithm: str = "mediapipe-v1"
    # Face embedding model selection. "mobilefacenet" runs a local ONNX
    # MobileFaceNet (112x112) on the server; falls back to the landmark
    # pipeline only when the model is missing or fails to load.
    face_embedding_model: str = "mobilefacenet"
    mobilefacenet_model_path: str | None = None
    face_embedding_dim: int = 512
    face_input_size: int = 112
    face_embedding_normalize: str = "minus_one_one"

    # Backup-attachment fields
    backup_storage_type: str = "local"
    backup_local_dir: str = "./backups"
    backup_s3_bucket: str = ""
    backup_s3_endpoint: str = ""
    backup_s3_prefix: str = "backups/"
    backup_encryption_key: str = ""
    backup_encryption_key_version: int = 1
    backup_retention_daily: int = 30
    backup_retention_monthly: int = 12
    backup_exclude_otp_codes: bool = False
    # Nightly full-backup schedule. 03:00 is what the admin System Settings
    # panel displays as the last backup time, and it clears the 02:00 risk
    # batch so the two heavy jobs never overlap.
    backup_cron: str = "0 3 * * *"

    # Attendance defaults (D13, geofence). The two window values mirror
    # `shared.constants.DEFAULT_PRESENT_WINDOW_MINUTES` /
    # `DEFAULT_LATE_WINDOW_MINUTES`, which is what an offering row defaults to;
    # core deliberately does not import `shared`, so keep the pair in step.
    default_present_window_minutes: int = 5
    default_late_window_minutes: int = 10
    default_geofence_radius_meters: int = 50
    otp_expires_minutes: int = 5

    # Wall-clock class times (`course_offerings.schedule_start_time` /
    # `schedule_end_time`) are naive local times: "09:00" means nine in the
    # morning wherever the class is held. This zone says where. The session
    # plan resolver (D93) interprets them here and converts to UTC on write,
    # so "today's meeting" is a local-calendar concept and every stored
    # timestamp stays UTC.
    #
    # UTC by default, matching the rest of the system's UTC-day semantics.
    # An unknown zone name warns and falls back to UTC (see
    # `core.timezones.resolve_timezone`) rather than failing the boot.
    institution_timezone: str = "UTC"

    # How early and how late a session may be opened (D94). A session may
    # only be opened while its class is running, so these two values are the
    # grace around that window: a professor who arrives before the class
    # starts, or who opens a class that is still running a few minutes past
    # its end, is let in.
    #
    # Both are the environment fallback for the `app_settings` rows an
    # administrator edits in Admin -> System Settings, exactly like the two
    # attendance windows and the geofence radius (D93).
    session_early_open_minutes: int = 30
    session_late_open_minutes: int = 0

    # Risk scoring (D35)
    risk_absence_rate_high: float = 0.30
    risk_absence_rate_medium: float = 0.15
    risk_streak_gaps_high: int = 3
    risk_sync_lag_high: int = 5
    risk_trend_negative: float = -0.05
    risk_batch_cron: str = "0 2 * * *"
    risk_batch_chunk_size: int = 1000
    risk_batch_workers: int = 4
    risk_batch_dry_run: bool = False

    # Background scheduler. `scheduler_enabled` is the kill switch for dev
    # (`uvicorn --reload` restarts the scheduler on every save) and for any
    # deployment that wants crons handled outside the API process.
    # `scheduler_timezone` is a zoneinfo name; an unknown one falls back to UTC
    # with a warning rather than failing the boot, because a slim container
    # image may ship without the tz database. `scheduler_misfire_grace_seconds`
    # is how long a delayed run is still worth starting.
    scheduler_enabled: bool = True
    scheduler_timezone: str = "UTC"
    scheduler_misfire_grace_seconds: int = 300

    # Attachment storage (excuse evidence). `s3` reuses the backup_* bucket and
    # credentials: the two features share one backend. `attachments_local_dir`
    # only applies to the `local` dev backend.
    attachments_storage_type: str = "local"
    attachments_max_bytes: int = 5242880
    attachments_local_dir: str = "./attachments"

    # Email / SMTP. An empty `smtp_host` disables delivery: `shared/email.py`
    # logs the message instead of connecting, so a deployment without a relay
    # still serves OTP codes and excuse notifications. `smtp_from` falls back to
    # `smtp_user` and then to a placeholder, so a From header is always present.
    # Deliberately unvalidated - mail is deployment config, not a boot
    # requirement, so unlike JWT_SECRET it must not fail Settings construction.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_start_tls: bool = True
    smtp_use_ssl: bool = False
    smtp_timeout_seconds: int = 10

    # Cloudflare Turnstile CAPTCHA (optional; empty = pass-through no-op)
    turnstile_secret_key: str = ""

    # Testing/benchmark + backup tuning
    benchmark_mode: bool = False
    backup_compression_level: int = 6

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @model_validator(mode="after")
    def require_jwt_secret_in_prod(self) -> "Settings":
        if not self.debug and not self.jwt_secret:
            raise ValueError("JWT_SECRET must be set when DEBUG=false")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
