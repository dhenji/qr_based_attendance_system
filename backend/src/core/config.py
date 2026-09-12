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
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @model_validator(mode="after")
    def require_jwt_secret_in_prod(self) -> "Settings":
        if not self.debug and not self.jwt_secret:
            raise ValueError("JWT_SECRET must be set when DEBUG=false")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
