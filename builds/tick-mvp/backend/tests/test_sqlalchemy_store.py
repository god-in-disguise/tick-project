from __future__ import annotations

import os
import uuid

import pytest

from tick_mvp.schemas import CloseRequest, OpenRequest, QuoteRequest


def test_postgres_open_close_persists_fk_order() -> None:
    database_url = os.getenv("TICK_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TICK_TEST_DATABASE_URL is not configured")

    sqlalchemy = pytest.importorskip("sqlalchemy")
    from tick_mvp.infrastructure.database import create_session_factory, run_sql_migrations
    from tick_mvp.infrastructure.models import User, WalletAccount
    from tick_mvp.infrastructure.sqlalchemy_store import SQLAlchemyStore

    run_sql_migrations(database_url)

    engine = sqlalchemy.create_engine(_sqlalchemy_url(database_url), pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    suffix = uuid.uuid4().hex
    user_id = f"user_test_{suffix}"
    wallet_id = f"wallet_test_{suffix}"

    with session_factory() as session:
        session.add(
            User(
                id=user_id,
                email=f"{suffix}@test.tick.local",
                display_name="Test User",
                avatar_url=None,
                status="active",
            )
        )
        session.add(
            WalletAccount(
                id=wallet_id,
                user_id=user_id,
                chain_id=42161,
                address=f"0x{suffix[:40].ljust(40, '0')}",
                wallet_type="platform",
                status="active",
                custody_provider="test",
                custody_key_ref=f"test:{wallet_id}",
                encrypted_private_key=None,
                gas_wallet=False,
                payload={},
            )
        )
        session.commit()

    store = SQLAlchemyStore(default_venue="gtrade", session_factory=session_factory)
    quote = store.create_quote(
        user_id,
        QuoteRequest(market="BTCDEGEN/USD", side="long", ticketUsd="10", leverage="100"),
    )

    opened = store.accept_open(user_id, OpenRequest(quoteId=quote.quoteId, idempotencyKey=f"open-{suffix}"))
    closed = store.accept_close(user_id, CloseRequest(positionId=opened.position.id, idempotencyKey=f"close-{suffix}"))

    assert opened.intent.status == "accepted"
    assert opened.executionAttempt.status == "created"
    assert opened.position.status == "opening"
    assert closed.intent.status == "accepted"
    assert closed.executionAttempt.status == "created"
    assert closed.position.status == "closing"


def _sqlalchemy_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url
