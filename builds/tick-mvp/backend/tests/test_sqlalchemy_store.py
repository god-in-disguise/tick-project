from __future__ import annotations

import os
import uuid
from decimal import Decimal

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
                wallet_type="platform_custody",
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


def test_postgres_withdrawal_persists_recoverable_signed_transaction() -> None:
    database_url = os.getenv("TICK_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TICK_TEST_DATABASE_URL is not configured")

    sqlalchemy = pytest.importorskip("sqlalchemy")
    from eth_account import Account

    from tick_mvp.core.config import Settings
    from tick_mvp.infrastructure.custody import PrivateKeyCipher
    from tick_mvp.infrastructure.database import create_session_factory, run_sql_migrations
    from tick_mvp.infrastructure.models import LedgerEvent, User, WalletAccount, Withdrawal
    from tick_mvp.wallets.repository import WithdrawalRepository

    run_sql_migrations(database_url)
    engine = sqlalchemy.create_engine(_sqlalchemy_url(database_url), pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    suffix = uuid.uuid4().hex
    user_id = f"user_withdrawal_{suffix}"
    wallet_id = f"wallet_withdrawal_{suffix}"
    withdrawal_id = f"withdrawal_{suffix}"
    key = PrivateKeyCipher.generate_key()
    cipher = PrivateKeyCipher(key)
    account = Account.create()

    with session_factory() as session:
        session.add(
            User(
                id=user_id,
                email=f"{suffix}-withdrawal@test.tick.local",
                display_name="Withdrawal Test",
                avatar_url=None,
                status="active",
            )
        )
        session.add(
            WalletAccount(
                id=wallet_id,
                user_id=user_id,
                chain_id=42161,
                address=account.address,
                wallet_type="platform",
                status="active",
                custody_provider="encrypted_postgres",
                custody_key_ref=f"test:{wallet_id}",
                encrypted_private_key=cipher.encrypt(account.key.hex()),
                gas_wallet=False,
                payload={},
            )
        )
        session.add(
            Withdrawal(
                id=withdrawal_id,
                user_id=user_id,
                wallet_id=wallet_id,
                idempotency_key=f"withdraw-{suffix}",
                request_hash=suffix,
                asset="USDC",
                amount="2.5",
                destination_address="0x1111111111111111111111111111111111111111",
                status="requested",
                payload={},
            )
        )
        session.commit()

    repository = WithdrawalRepository(
        Settings(custody_private_key_encryption_key=key),
        session_factory=session_factory,
    )
    context = repository.load(withdrawal_id)
    assert context.status == "validated"

    tx_hash = "0x" + "ab" * 32
    repository.mark_signed(
        withdrawal_id,
        tx_hash=tx_hash,
        nonce=7,
        signed_raw_transaction="0x02cafe",
    )
    recovered = repository.load(withdrawal_id)
    assert recovered.tx_hash == tx_hash
    assert recovered.signed_raw_transaction == "0x02cafe"

    repository.mark_broadcast(
        withdrawal_id,
        tx_hash=tx_hash,
        payload={"winner": "primary_rpc"},
    )
    repository.mark_confirmed(
        withdrawal_id,
        tx_hash=tx_hash,
        gas_cost_native=Decimal("0.000001"),
        payload={"blockNumber": 123},
    )

    with session_factory() as session:
        withdrawal = session.get(Withdrawal, withdrawal_id)
        ledger = (
            session.query(LedgerEvent)
            .filter(LedgerEvent.withdrawal_id == withdrawal_id)
            .one()
        )
        assert withdrawal.status == "confirmed"
        assert ledger.amount == Decimal("-2.5")


def test_postgres_gas_topup_persists_exact_signed_transaction() -> None:
    database_url = os.getenv("TICK_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TICK_TEST_DATABASE_URL is not configured")

    sqlalchemy = pytest.importorskip("sqlalchemy")
    from tick_mvp.core.config import Settings
    from tick_mvp.infrastructure.custody import SecretCipher
    from tick_mvp.infrastructure.database import create_session_factory, run_sql_migrations
    from tick_mvp.infrastructure.models import GasTopup, User, WalletAccount
    from tick_mvp.wallets.gas_repository import GasTopupRepository

    run_sql_migrations(database_url)
    engine = sqlalchemy.create_engine(_sqlalchemy_url(database_url), pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    suffix = uuid.uuid4().hex
    user_id = f"user_gas_{suffix}"
    wallet_id = f"wallet_gas_{suffix}"
    wallet_address = f"0x{suffix[:40].ljust(40, '0')}"
    key = SecretCipher.generate_key()

    with session_factory() as session:
        session.add(
            User(
                id=user_id,
                email=f"{suffix}-gas@test.tick.local",
                display_name="Gas Test",
                avatar_url=None,
                status="active",
            )
        )
        session.add(
            WalletAccount(
                id=wallet_id,
                user_id=user_id,
                chain_id=42161,
                address=wallet_address,
                wallet_type="platform",
                status="active",
                custody_provider="encrypted_postgres",
                custody_key_ref=f"test:{wallet_id}",
                encrypted_private_key=None,
                gas_wallet=False,
                payload={},
            )
        )
        session.commit()

    repository = GasTopupRepository(
        Settings(custody_private_key_encryption_key=key),
        session_factory=session_factory,
    )
    context = repository.create_or_load(
        user_id=user_id,
        wallet_id=wallet_id,
        wallet_address=wallet_address,
        amount_native=Decimal("0.001"),
    )
    tx_hash = "0x" + "cd" * 32
    repository.mark_signed(
        context.topup_id,
        tx_hash=tx_hash,
        nonce=9,
        signed_raw_transaction="0x02beef",
    )
    recovered = repository.create_or_load(
        user_id=user_id,
        wallet_id=wallet_id,
        wallet_address=wallet_address,
        amount_native=Decimal("0.001"),
    )
    assert recovered.tx_hash == tx_hash
    assert recovered.signed_raw_transaction == "0x02beef"
    repository.mark_broadcast(
        context.topup_id,
        tx_hash=tx_hash,
        payload={"winner": "primary_rpc"},
    )
    repository.mark_confirmed(
        context.topup_id,
        tx_hash=tx_hash,
        gas_cost_native=Decimal("0.00000042"),
        payload={"blockNumber": 123},
    )
    with session_factory() as session:
        topup = session.get(GasTopup, context.topup_id)
        assert topup.status == "confirmed"
        assert topup.gas_cost_native == Decimal("0.00000042")


def test_demo_profile_isolated_and_reset_is_audited() -> None:
    database_url = os.getenv("TICK_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TICK_TEST_DATABASE_URL is not configured")

    sqlalchemy = pytest.importorskip("sqlalchemy")
    from tick_mvp.domain.states import TradingMode
    from tick_mvp.execution.repository import ExecutionRepository
    from tick_mvp.infrastructure.database import create_session_factory, run_sql_migrations
    from tick_mvp.infrastructure.models import DemoProfileReset, User, WalletAccount
    from tick_mvp.infrastructure.sqlalchemy_store import SQLAlchemyStore, StoreConflict

    run_sql_migrations(database_url)
    engine = sqlalchemy.create_engine(_sqlalchemy_url(database_url), pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    suffix = uuid.uuid4().hex
    user_id = f"user_demo_{suffix}"

    with session_factory() as session:
        session.add(
            User(
                id=user_id,
                email=f"{suffix}-demo@test.tick.local",
                display_name="Demo Test",
                avatar_url=None,
                status="active",
            )
        )
        session.add(
            WalletAccount(
                id=f"wallet_demo_{suffix}",
                user_id=user_id,
                chain_id=42161,
                address=f"0x{suffix[:40].ljust(40, '0')}",
                wallet_type="platform_custody",
                status="active",
                custody_provider="test",
                custody_key_ref=f"test:demo:{suffix}",
                encrypted_private_key=None,
                gas_wallet=False,
                payload={},
            )
        )
        session.commit()

    store = SQLAlchemyStore(default_venue="gtrade", session_factory=session_factory)
    profile = store.switch_trading_mode(user_id, TradingMode.DEMO)
    assert profile.balanceUsd == Decimal("1000")

    quote = store.create_quote(
        user_id,
        QuoteRequest(market="BTCDEGEN/USD", side="long", ticketUsd="10", leverage="100"),
    )
    opened = store.accept_open(
        user_id,
        OpenRequest(quoteId=quote.quoteId, idempotencyKey=f"demo-open-{suffix}"),
    )
    assert opened.position.tradingMode == TradingMode.DEMO
    with pytest.raises(StoreConflict):
        store.switch_trading_mode(user_id, TradingMode.LIVE)

    repository = ExecutionRepository(session_factory=session_factory)
    open_context = repository.load(opened.executionAttempt.id)
    repository.mark_demo_open(
        open_context,
        entry_price=Decimal("100"),
        liquidation_price=Decimal("99"),
        stop_loss_price=None,
        take_profit_price=None,
        open_cost_usd=Decimal("0.20"),
        close_cost_usd=Decimal("0.20"),
        quote_payload={"price": "100"},
        delay_ms=1200,
    )
    assert store.demo_balances(user_id).spendableUsdc == Decimal("990")

    closed = store.accept_close(
        user_id,
        CloseRequest(positionId=opened.position.id, idempotencyKey=f"demo-close-{suffix}"),
    )
    close_context = repository.load(closed.executionAttempt.id)
    pnl = repository.mark_demo_close(
        close_context,
        exit_price=Decimal("100.10"),
        gross_pnl_usd=Decimal("1"),
        open_cost_usd=Decimal("0.20"),
        close_cost_usd=Decimal("0.20"),
        returned_usd=Decimal("10.60"),
        reason="manual_close",
        quote_payload={"price": "100.10"},
        delay_ms=1000,
    )
    assert pnl == Decimal("0.60")
    assert store.demo_balances(user_id).spendableUsdc == Decimal("1000.60")
    assert len(store.state(user_id).positions) == 1

    reset = store.reset_demo_profile(user_id)
    assert reset.endedSeason == 1
    assert reset.endingBalanceUsd == Decimal("1000.60")
    assert reset.realizedPnlUsd == Decimal("0.60")
    assert reset.profile.season == 2
    assert reset.profile.balanceUsd == Decimal("1000")
    assert store.state(user_id).positions == []

    with session_factory() as session:
        audit = (
            session.query(DemoProfileReset)
            .filter(DemoProfileReset.user_id == user_id)
            .one()
        )
        assert audit.ended_season == 1
        assert audit.ending_balance_usd == Decimal("1000.60")

    store.switch_trading_mode(user_id, TradingMode.LIVE)
    live_state = store.state(user_id)
    assert live_state.positions == []
    assert live_state.reconciliations == []

def _sqlalchemy_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url
