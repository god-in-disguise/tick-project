from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from tick_mvp.core.config import get_settings


def create_engine_from_settings():
    from sqlalchemy import create_engine

    return create_engine(_sqlalchemy_url(get_settings().database_url), pool_pre_ping=True)


def create_session_factory(engine=None):
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=engine or create_engine_from_settings(), autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(session_factory=None) -> Iterator:
    factory = session_factory or create_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def run_sql_migrations(database_url: str | None = None, migrations_dir: Path | None = None) -> None:
    import psycopg

    root = Path(__file__).resolve().parents[2]
    migration_root = migrations_dir or root / "migrations"
    statements = [path.read_text() for path in sorted(migration_root.glob("*.sql"))]
    if not statements:
        return

    with psycopg.connect(database_url or get_settings().database_url) as connection:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        connection.commit()


def _sqlalchemy_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url
