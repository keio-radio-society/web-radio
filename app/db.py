from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from .config import settings, ensure_directories

ensure_directories()

sqlite_connect_args = {"check_same_thread": False}
engine = create_engine(settings.database_url, connect_args=sqlite_connect_args)


def init_db() -> None:
    """Create database tables if they are missing."""

    SQLModel.metadata.create_all(engine)
    _ensure_columns()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager wrapping a Session for manual control."""

    with Session(engine) as session:
        yield session


def _ensure_columns() -> None:
    with Session(engine) as session:
        result = session.exec(text("PRAGMA table_info(appsettings)")).all()
        columns = {row[1] for row in result}
        if "audio_playback_device" not in columns:
            session.exec(text("ALTER TABLE appsettings ADD COLUMN audio_playback_device TEXT"))
