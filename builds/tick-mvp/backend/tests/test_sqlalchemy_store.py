from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tick_mvp.schemas import CloseRequest, OpenRequest, QuoteRequest


def test_postgres_open_close_persists_fk_order() -> None:
    database_url = os.getenv("TICK_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TICK_TEST_DATABASE_URL is not configured")

    sqlalchemy = pytest.importorskip("sqlalchemy")
    from eth_account import Account

    from tick_mvp.core.config import Settings
    from tick_mvp.execution.repository import ExecutionRepository
    from tick_mvp.infrastructure.custody import PrivateKeyCipher, SecretCipher
    from tick_mvp.infrastructure.database import create_session_factory, run_sql_migrations
    from tick_mvp.infrastructure.models import ExecutionAttempt, Position, User, WalletAccount
    from tick_mvp.infrastructure.sqlalchemy_store import SQLAlchemyStore
    from tick_mvp.venues.base import VenueCloseResult, VenueTxResult

    run_sql_migrations(database_url)

    engine = sqlalchemy.create_engine(_sqlalchemy_url(database_url), pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    suffix = uuid.uuid4().hex
    user_id = f"user_test_{suffix}"
    wallet_id = f"wallet_test_{suffix}"
    encryption_key = PrivateKeyCipher.generate_key()
    account = Account.create()

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
                address=account.address,
                wallet_type="platform_custody",
                status="active",
                custody_provider="test",
                custody_key_ref=f"test:{wallet_id}",
                encrypted_private_key=PrivateKeyCipher(encryption_key).encrypt(
                    account.key.hex()
                ),
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
    repository = ExecutionRepository(
        Settings(custody_private_key_encryption_key=encryption_key),
        session_factory=session_factory,
    )
    context = repository.claim(opened.executionAttempt.id)
    assert context is not None
    assert repository.claim(opened.executionAttempt.id) is None
    repository.mark_broadcast_pending(
        context,
        tx_hash="0x" + "ab" * 32,
        nonce=7,
        signed_raw_transaction="0x02cafe",
    )
    repository.mark_failed(context, "TimeoutError: response lost after broadcast")

    with session_factory() as session:
        execution = session.get(ExecutionAttempt, opened.executionAttempt.id)
        position = session.get(Position, opened.position.id)
        assert execution.status == "unknown"
        assert position.status == "unknown"
        assert SecretCipher(encryption_key).decrypt(execution.raw_tx_ref.encode()) == "0x02cafe"

    closed = store.accept_close(user_id, CloseRequest(positionId=opened.position.id, idempotencyKey=f"close-{suffix}"))

    assert opened.intent.status == "accepted"
    assert opened.executionAttempt.status == "created"
    assert opened.position.status == "opening"
    assert closed.intent.status == "accepted"
    assert closed.executionAttempt.status == "created"
    assert closed.position.status == "closing"

    close_context = repository.claim(closed.executionAttempt.id)
    assert close_context is not None
    repository.mark_broadcast_pending(
        close_context,
        tx_hash="0x" + "cd" * 32,
        nonce=8,
        signed_raw_transaction="0x02beef",
    )
    with session_factory() as session:
        position = session.get(Position, opened.position.id)
        position.status = "liquidated"
        position.closed_at = datetime.now(UTC)
        position.payload = {**(position.payload or {}), "terminalReason": "liquidation"}
        session.commit()

    repository.mark_close_result(
        close_context,
        VenueCloseResult(
            status="closed",
            tx=VenueTxResult(
                status="confirmed",
                tx_hash="0x" + "cd" * 32,
                nonce=8,
                block_number=123,
                gas_used=100,
                effective_gas_price=1,
                payload={},
            ),
            closed_at=datetime.now(UTC),
            venue_realized_pnl_usd=Decimal("-10"),
            account_balance_after_usd=None,
            close_cashflow_usd=Decimal(0),
            payload={},
        ),
    )
    with session_factory() as session:
        execution = session.get(ExecutionAttempt, closed.executionAttempt.id)
        position = session.get(Position, opened.position.id)
        assert execution.status == "venue_executed"
        assert position.status == "liquidated"
        assert execution.payload["terminalPositionWonRace"] == "liquidated"


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
    from tick_mvp.infrastructure.models import (
        DemoProfileReset,
        ExecutionAttempt,
        LedgerEvent,
        Position,
        Reconciliation,
        TradeIntent,
        User,
        WalletAccount,
    )
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
    open_context = repository.claim(opened.executionAttempt.id)
    assert open_context is not None
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
    close_context = repository.claim(closed.executionAttempt.id)
    assert close_context is not None
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

    monitor_quote = store.create_quote(
        user_id,
        QuoteRequest(market="BTCDEGEN/USD", side="long", ticketUsd="10", leverage="100"),
    )
    monitor_opened = store.accept_open(
        user_id,
        OpenRequest(
            quoteId=monitor_quote.quoteId,
            idempotencyKey=f"demo-monitor-open-{suffix}",
        ),
    )
    monitor_context = repository.claim(monitor_opened.executionAttempt.id)
    assert monitor_context is not None
    repository.mark_demo_open(
        monitor_context,
        entry_price=Decimal("100"),
        liquidation_price=Decimal("99"),
        stop_loss_price=Decimal("99.50"),
        take_profit_price=None,
        open_cost_usd=Decimal("0.20"),
        close_cost_usd=Decimal("0.20"),
        quote_payload={"price": "100"},
        delay_ms=1200,
    )
    monitor_snapshot = next(
        snapshot
        for snapshot in repository.open_demo_positions()
        if snapshot.position_id == monitor_opened.position.id
    )
    assert repository.settle_demo_terminal(
        monitor_snapshot,
        exit_price=Decimal("99.50"),
        gross_pnl_usd=Decimal("-5"),
        close_cost_usd=Decimal("0.20"),
        returned_usd=Decimal("4.80"),
        reason="stop_loss",
        quote_payload={"price": "99.50"},
    )
    assert not repository.settle_demo_terminal(
        monitor_snapshot,
        exit_price=Decimal("99.50"),
        gross_pnl_usd=Decimal("-5"),
        close_cost_usd=Decimal("0.20"),
        returned_usd=Decimal("4.80"),
        reason="stop_loss",
        quote_payload={"price": "99.50"},
    )

    with session_factory() as session:
        audit = (
            session.query(DemoProfileReset)
            .filter(DemoProfileReset.user_id == user_id)
            .one()
        )
        assert audit.ended_season == 1
        assert audit.ending_balance_usd == Decimal("1000.60")
        monitor_position = session.get(Position, monitor_opened.position.id)
        assert monitor_position.status == "closed"
        monitor_intent = (
            session.query(TradeIntent)
            .filter(TradeIntent.position_id == monitor_opened.position.id)
            .order_by(TradeIntent.created_at.desc())
            .first()
        )
        monitor_execution = (
            session.query(ExecutionAttempt)
            .filter(ExecutionAttempt.trade_intent_id == monitor_intent.id)
            .one()
        )
        monitor_reconciliation = (
            session.query(Reconciliation)
            .filter(Reconciliation.position_id == monitor_opened.position.id)
            .one()
        )
        monitor_ledger = (
            session.query(LedgerEvent)
            .filter(
                LedgerEvent.position_id == monitor_opened.position.id,
                LedgerEvent.event_type == "demo_position_settled",
            )
            .one()
        )
        assert monitor_execution.status == "venue_executed"
        assert monitor_reconciliation.difference_usd == Decimal("0")
        assert monitor_ledger.execution_attempt_id == monitor_execution.id

    store.switch_trading_mode(user_id, TradingMode.LIVE)
    live_state = store.state(user_id)
    assert live_state.positions == []
    assert live_state.reconciliations == []

def _sqlalchemy_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url
