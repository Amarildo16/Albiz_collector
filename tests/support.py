from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from shutil import rmtree
from typing import Iterator
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from albiz_collector import db as db_module
from albiz_collector.config import settings


TESTS_ROOT = Path(__file__).resolve().parent
FIXTURES_ROOT = TESTS_ROOT / "fixtures"
TMP_ROOT = TESTS_ROOT / ".tmp"


def fixture_path(*parts: str) -> Path:
    return FIXTURES_ROOT.joinpath(*parts)


@contextmanager
def isolated_db_environment() -> Iterator[tuple[Path, sessionmaker[Session], object]]:
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    temp_dir = TMP_ROOT / f"test-run-{uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=False)

    database_path = temp_dir / "test.sqlite3"
    raw_storage_dir = temp_dir / "raw"
    raw_storage_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine(f"sqlite:///{database_path}", future=True, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    original_engine = db_module.engine
    original_session_local = db_module.SessionLocal
    original_database_url = settings.database_url
    original_raw_storage_dir = settings.raw_storage_dir

    db_module.engine = engine
    db_module.SessionLocal = session_factory
    settings.database_url = f"sqlite:///{database_path}"
    settings.raw_storage_dir = raw_storage_dir

    try:
        yield temp_dir, session_factory, engine
    finally:
        settings.database_url = original_database_url
        settings.raw_storage_dir = original_raw_storage_dir
        db_module.engine = original_engine
        db_module.SessionLocal = original_session_local
        engine.dispose()
        rmtree(temp_dir, ignore_errors=True)
