"""Runtime configuration, read from the environment or a .env file."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CHATFACE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8000

    silence_timeout_s: float = 20.0
    """Silence in LISTENING before the session ends and the mic closes."""

    identity_timeout_s: float = 2.0
    """How long WAKE waits for identification before starting anyway."""


settings = Settings()
