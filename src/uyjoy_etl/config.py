from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from uyjoy_etl.category_catalog import default_category_paths


def _bool_from_env(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "ha"}


def _csv_from_env(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    return tuple(item.strip().strip("/") for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class DatabaseConfig:
    """Postgresga ulanish uchun kerak bo'ladigan sozlamalar."""

    host: str
    port: int
    database: str
    user: str
    password: str
    connection_url: str | None = None

    @property
    def dsn(self) -> str:
        if self.connection_url:
            return self.connection_url
        return (
            f"host={self.host} port={self.port} dbname={self.database} "
            f"user={self.user} password={self.password}"
        )

    @property
    def admin_dsn(self) -> str:
        if self.connection_url:
            return self.connection_url
        return (
            f"host={self.host} port={self.port} dbname=postgres "
            f"user={self.user} password={self.password}"
        )

    @property
    def database_is_managed(self) -> bool:
        """Cloud provider bergan tayyor database URL ishlatilayotganini bildiradi."""

        return bool(self.connection_url)


@dataclass(frozen=True)
class OlxConfig:
    """OLX scraping jarayoni uchun asosiy sozlamalar."""

    base_url: str
    user_agent: str
    timeout_seconds: int
    request_delay_seconds: float
    max_retries: int
    category_paths: tuple[str, ...]
    max_pages_per_category: int
    fetch_details: bool


@dataclass(frozen=True)
class AppConfig:
    root_dir: Path
    logs_dir: Path
    database: DatabaseConfig
    olx: OlxConfig


def load_config() -> AppConfig:
    """`.env` faylini o'qib, butun ilova konfiguratsiyasini tayyorlaydi."""

    root_dir = Path(__file__).resolve().parents[2]
    load_dotenv(root_dir / ".env")

    logs_dir = root_dir / "logs"

    database = _database_config_from_env()

    olx = OlxConfig(
        base_url=os.getenv("OLX_BASE_URL", "https://www.olx.uz").rstrip("/"),
        user_agent=os.getenv(
            "OLX_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) UyJoyETL/0.1",
        ),
        timeout_seconds=int(os.getenv("OLX_REQUEST_TIMEOUT_SECONDS", "30")),
        request_delay_seconds=float(os.getenv("OLX_REQUEST_DELAY_SECONDS", "1.5")),
        max_retries=int(os.getenv("OLX_MAX_RETRIES", "3")),
        category_paths=_csv_from_env(os.getenv("OLX_CATEGORY_PATHS"), default_category_paths()),
        max_pages_per_category=int(os.getenv("OLX_MAX_PAGES_PER_CATEGORY", "1")),
        fetch_details=_bool_from_env(os.getenv("OLX_FETCH_DETAILS"), True),
    )

    return AppConfig(root_dir=root_dir, logs_dir=logs_dir, database=database, olx=olx)


def _database_config_from_env() -> DatabaseConfig:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        parsed = urlparse(database_url)
        return DatabaseConfig(
            host=parsed.hostname or "",
            port=parsed.port or 5432,
            database=parsed.path.lstrip("/") or "postgres",
            user=parsed.username or "",
            password=parsed.password or "",
            connection_url=database_url,
        )

    return DatabaseConfig(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "uyjoy_olx"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )
