import logging
import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from .models import Base

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data/gpx_editor.db")


def _ensure_sqlite_dir(url: str) -> None:
    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///") :]
        if path and path != ":memory:":
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)


_ensure_sqlite_dir(DATABASE_URL)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# Columns added after the table already existed somewhere. create_all() only
# creates missing tables, so existing databases need these filled in by hand.
# Keep entries here forever: they're skipped when the column is already present.
_ADDED_COLUMNS = {
    "days": [
        ("lock_start", "BOOLEAN NOT NULL DEFAULT 0"),
        ("lock_end", "BOOLEAN NOT NULL DEFAULT 0"),
        ("source_points", "JSON"),
    ],
}


def _add_missing_columns() -> None:
    """Best-effort schema top-up. Never fatal: a database that can't be altered
    (bind-mounted SQLite can refuse) should still serve, loudly rather than dying."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    for table, columns in _ADDED_COLUMNS.items():
        if table not in existing_tables:
            continue  # create_all will make it with everything already on it
        present = {c["name"] for c in inspector.get_columns(table)}
        for name, ddl in columns:
            if name in present:
                continue
            try:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                logger.info("Added missing column %s.%s", table, name)
            except OperationalError as exc:
                logger.error(
                    "Could not add column %s.%s (%s). Apply it manually: "
                    "ALTER TABLE %s ADD COLUMN %s %s;",
                    table,
                    name,
                    exc.orig,
                    table,
                    name,
                    ddl,
                )


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
