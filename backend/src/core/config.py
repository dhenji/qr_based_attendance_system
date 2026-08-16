from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "QR Attendance System API"
    debug: bool = False
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/attendance_sys"
    )
    cors_origins: str = "http://localhost:5173"
    hmac_secret_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
