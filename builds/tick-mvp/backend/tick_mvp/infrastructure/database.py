from __future__ import annotations

from collections.abc import Iterator

from tick_mvp.core.config import get_settings


def create_engine_from_settings():
    from sqlalchemy import create_engine

    return create_engine(get_settings().database_url, pool_pre_ping=True)


def create_session_factory(engine=None):
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=engine or create_engine_from_settings(), autoflush=False, expire_on_commit=False)


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
