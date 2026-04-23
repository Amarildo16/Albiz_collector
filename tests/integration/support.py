from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from albiz_collector import db as db_module
from albiz_collector.config import PROJECT_ROOT, settings


TMP_ROOT = Path(__file__).resolve().parents[1] / ".tmp"
RUN_MYSQL_INTEGRATION_TESTS_ENV = "RUN_MYSQL_INTEGRATION_TESTS"
MYSQL_INTEGRATION_ADMIN_URL_ENV = "MYSQL_INTEGRATION_ADMIN_URL"


@dataclass(frozen=True)
class MySqlIntegrationContext:
    database_name: str
    database_url: str
    temp_dir: Path
    raw_storage_dir: Path
    session_factory: sessionmaker[Session]
    engine: Engine


def mysql_integration_enabled() -> bool:
    value = os.getenv(RUN_MYSQL_INTEGRATION_TESTS_ENV, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def require_mysql_integration() -> None:
    if not mysql_integration_enabled():
        raise unittest.SkipTest(
            f"Set {RUN_MYSQL_INTEGRATION_TESTS_ENV}=1 to run MySQL integration tests."
        )

    admin_url = _admin_url()
    if not admin_url.drivername.startswith("mysql"):
        raise unittest.SkipTest(
            "MySQL integration tests require a mysql+pymysql SQLAlchemy URL in "
            f"{MYSQL_INTEGRATION_ADMIN_URL_ENV} or DATABASE_URL."
        )


@contextmanager
def mysql_integration_environment() -> MySqlIntegrationContext:
    require_mysql_integration()

    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    temp_dir = TMP_ROOT / f"mysql-integration-{uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=False)
    raw_storage_dir = temp_dir / "raw"
    raw_storage_dir.mkdir(parents=True, exist_ok=True)

    database_name = f"albiz_it_{uuid4().hex}"
    admin_url = _admin_url()
    admin_engine = create_engine(
        admin_url.render_as_string(hide_password=False),
        future=True,
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )

    with admin_engine.connect() as connection:
        connection.execute(
            text(
                f"CREATE DATABASE `{database_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )

    database_url = admin_url.set(database=database_name).render_as_string(hide_password=False)
    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    original_engine = db_module.engine
    original_session_local = db_module.SessionLocal
    original_database_url = settings.database_url
    original_raw_storage_dir = settings.raw_storage_dir

    db_module.engine = engine
    db_module.SessionLocal = session_factory
    settings.database_url = database_url
    settings.raw_storage_dir = raw_storage_dir

    context = MySqlIntegrationContext(
        database_name=database_name,
        database_url=database_url,
        temp_dir=temp_dir,
        raw_storage_dir=raw_storage_dir,
        session_factory=session_factory,
        engine=engine,
    )

    try:
        yield context
    finally:
        settings.database_url = original_database_url
        settings.raw_storage_dir = original_raw_storage_dir
        db_module.engine = original_engine
        db_module.SessionLocal = original_session_local
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS `{database_name}`"))
        admin_engine.dispose()
        rmtree(temp_dir, ignore_errors=True)


def alembic_upgrade_head() -> None:
    command.upgrade(_alembic_config(), "head")


def alembic_stamp_head() -> None:
    command.stamp(_alembic_config(), "head")


def alembic_head_revision() -> str:
    return ScriptDirectory.from_config(_alembic_config()).get_current_head()


def _alembic_config() -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    return config


def _admin_url() -> URL:
    explicit = os.getenv(MYSQL_INTEGRATION_ADMIN_URL_ENV)
    if explicit:
        return make_url(explicit)
    return make_url(settings.database_url).set(database="mysql")
