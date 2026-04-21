from __future__ import annotations

from typing import Final

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


NAMING_CONVENTION: Final[dict[str, str]] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

SCHEMA_BOOTSTRAP_NOTE: Final[str] = (
    "init_db() creates any missing tables for the current SQLAlchemy models. "
    "It does not apply schema migrations or reconcile changes to an existing database."
)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def load_model_definitions() -> None:
    from . import models  # noqa: F401


def init_db() -> None:
    """Bootstrap a fresh local schema for the currently imported models.

    This path is intentionally lightweight: it creates missing tables but does
    not attempt to migrate or reconcile an existing schema. When model changes
    require schema evolution, update the database manually or recreate the local
    development database before running this again.
    """

    load_model_definitions()
    Base.metadata.create_all(bind=engine)
