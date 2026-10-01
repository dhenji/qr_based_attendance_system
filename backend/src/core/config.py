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

    # Attendance defaults (D13, geofence). The two window values mirror
    # `shared.constants.DEFAULT_PRESENT_WINDOW_MINUTES` /
    # `DEFAULT_LATE_WINDOW_MINUTES`, which is what an offering row defaults to;
    # core deliberately does not import `shared`, so keep the pair in step.
    default_present_window_minutes: int = 5
    default_late_window_minutes: int = 10
    default_geofence_radius_meters: int = 50
    otp_expires_minutes: int = 5

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

    # Cloudfare Trunstile CAPTCHA (optional)
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
