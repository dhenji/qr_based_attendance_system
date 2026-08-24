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
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @model_validator(mode="after")
    def require_jwt_secret_in_prod(self) -> "Settings":
        if not self.debug and not self.jwt_secret:
            raise ValueError("JWT_SECRET must be set when DEBUG=false")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
