from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_DATABASE_URL = "mysql+pymysql://root@localhost/albiz_collector"


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    return int(value.strip())


def _env_csv_ints(name: str, default: Iterable[int]) -> list[int]:
    value = os.getenv(name)
    if not value:
        return list(default)
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def _project_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (PROJECT_ROOT / candidate).resolve()


def _env_path(name: str, default: str) -> Path:
    value = os.getenv(name)
    return _project_path(value.strip() if value else default)


def _env_database_url(name: str, default: str) -> str:
    return _resolve_database_url(os.getenv(name, default))


def _resolve_database_url(database_url: str) -> str:
    try:
        url = make_url(database_url)
    except Exception:
        return database_url

    if not url.drivername.startswith("sqlite"):
        return database_url

    database = url.database
    if not database or database == ":memory:" or database.startswith("file:"):
        return database_url

    database_path = Path(database)
    if database_path.is_absolute():
        return database_url

    return url.set(database=_project_path(database_path).as_posix()).render_as_string(
        hide_password=False
    )


@dataclass(slots=True)
class Settings:
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    database_url: str = field(
        default_factory=lambda: _env_database_url("DATABASE_URL", DEFAULT_DATABASE_URL)
    )
    raw_storage_dir: Path = field(
        default_factory=lambda: _env_path("RAW_STORAGE_DIR", "./data/raw")
    )
    http_timeout_seconds: int = field(
        default_factory=lambda: _env_int("HTTP_TIMEOUT_SECONDS", 30)
    )
    http_user_agent: str = field(
        default_factory=lambda: os.getenv(
            "HTTP_USER_AGENT",
            "AlbizCollector/0.1 (+thesis-research; contact-yourself@example.com)",
        )
    )

    app_export_page_url: str = "https://www.app.gov.al/export-public-calls/"
    app_export_download_url_template: str = "https://www.app.gov.al/GetData/ExportDocument?year={year}"
    app_export_years: list[int] = field(
        default_factory=lambda: _env_csv_ints("APP_EXPORT_YEARS", range(2010, 2027))
    )
    app_download_enabled: bool = field(
        default_factory=lambda: _env_bool("APP_DOWNLOAD_ENABLED", True)
    )

    qkb_notices_index_url: str = "https://qkb.gov.al/shpallje/"
    qkb_notice_categories: dict[str, str] = field(
        default_factory=lambda: {
            "court_notices": "https://format.qkb.gov.al/njoftime-gjyqesore/",
            "creditor_notices": "https://format.qkb.gov.al/njoftime-per-kreditoret/",
            "enforcement_office_notices": "https://format.qkb.gov.al/njoftime-nga-zyra-permbarimore/",
            "customs_notices": "https://format.qkb.gov.al/njoftime-nga-organet-doganore/",
            "beneficiary_owners_notices": "https://format.qkb.gov.al/njoftime-per-regjistrin-e-pronareve-perfitues/",
            "other_notices": "https://format.qkb.gov.al/njoftime-te-tjera/",
        }
    )
    qkb_notices_playwright_headless: bool = field(
        default_factory=lambda: _env_bool("QKB_NOTICES_PLAYWRIGHT_HEADLESS", True)
    )
    qkb_notices_wait_ms: int = field(
        default_factory=lambda: _env_int("QKB_NOTICES_WAIT_MS", 2500)
    )
    qkb_notices_search_button_text: str = field(
        default_factory=lambda: os.getenv("QKB_NOTICES_SEARCH_BUTTON_TEXT", "Kërko")
    )
    qkb_notices_parse_document_links_only: bool = field(
        default_factory=lambda: _env_bool("QKB_NOTICES_PARSE_DOCUMENT_LINKS_ONLY", False)
    )
    qkb_notices_date_from_selector: str | None = field(
        default_factory=lambda: os.getenv("QKB_NOTICES_DATE_FROM_SELECTOR") or None
    )
    qkb_notices_date_to_selector: str | None = field(
        default_factory=lambda: os.getenv("QKB_NOTICES_DATE_TO_SELECTOR") or None
    )

    qkb_search_url: str = "https://format.qkb.gov.al/kerko-per-subjekt/"
    qkb_search_nipt_selector: str = field(
        default_factory=lambda: os.getenv("QKB_SEARCH_NIPT_SELECTOR", "#nipt")
    )
    qkb_search_date_from_selector: str = field(
        default_factory=lambda: os.getenv("QKB_SEARCH_DATE_FROM_SELECTOR", "#dataNga")
    )
    qkb_search_date_to_selector: str = field(
        default_factory=lambda: os.getenv("QKB_SEARCH_DATE_TO_SELECTOR", "#dataNe")
    )

    scheduler_app_exports_hour: int = field(
        default_factory=lambda: _env_int("SCHEDULER_APP_EXPORTS_HOUR", 5)
    )
    scheduler_enable_qkb_search: bool = field(
        default_factory=lambda: _env_bool("SCHEDULER_ENABLE_QKB_SEARCH", True)
    )
    scheduler_qkb_search_hour: int = field(
        default_factory=lambda: _env_int("SCHEDULER_QKB_SEARCH_HOUR", 6)
    )
    scheduler_qkb_search_lookback_days: int = field(
        default_factory=lambda: _env_int("SCHEDULER_QKB_SEARCH_LOOKBACK_DAYS", 1)
    )


def ensure_runtime_directories() -> None:
    settings.raw_storage_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
