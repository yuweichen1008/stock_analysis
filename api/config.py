"""
Centralised settings — read from environment variables / .env file.
All services import `settings` from here instead of calling os.getenv() directly.
"""
from __future__ import annotations

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    # Local dev: sqlite:///./data/oracle_game.db
    # Production: postgresql+psycopg2://user:pass@/dbname?host=/cloudsql/...
    DATABASE_URL: str = "sqlite:///./data/oracle_game.db"

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 10_080  # 7 days

    # ── Internal API protection ───────────────────────────────────────────────
    INTERNAL_API_SECRET: str = "change-me-internal-secret"

    # ── OAuth providers ───────────────────────────────────────────────────────
    GOOGLE_CLIENT_ID: str = ""
    APPLE_TEAM_ID: str = ""
    APPLE_CLIENT_ID: str = ""      # e.g. com.yourco.oracle

    # ── Google Cloud Storage ──────────────────────────────────────────────────
    # Leave empty to read signal CSVs from local disk (dev mode)
    GCS_BUCKET: str = ""

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Comma-separated origins, or "*" for open (dev)
    ALLOWED_ORIGINS: str = "*"

    def allowed_origins_list(self) -> List[str]:
        if self.ALLOWED_ORIGINS == "*":
            return ["*"]
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()
