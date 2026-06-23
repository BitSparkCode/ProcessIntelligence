from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@event.listens_for(Engine, "connect")
def _enforce_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    """Turn on FK enforcement for SQLite so ON DELETE CASCADE actually fires.

    Postgres (production) enforces foreign keys by default; SQLite does not,
    which would otherwise leave orphaned events/cases after a log is deleted.
    Enabling this guarantees a log delete fully removes all derived data
    (privacy / right-to-erasure, Story 5.4).
    """
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
