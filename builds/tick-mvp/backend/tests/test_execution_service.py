from dataclasses import replace
from decimal import Decimal

import pytest

pytest.importorskip("sqlalchemy")

from tick_mvp.core.config import Settings
from tick_mvp.domain.states import TradeAction, TradeSide
from tick_mvp.execution.repository import ExecutionContext
from tick_mvp.execution.service import ExecutionService, InsufficientSpendableUSDC


class FakeRepository:
    def load(self, execution_attempt_id: str) -> ExecutionContext:
        return ExecutionContext(
            execution_id=execution_attempt_id,
            intent_id="intent_1",
            user_id="user_1",
            action=TradeAction.OPEN,
            market="BTCDEGEN-USD",
            side=TradeSide.LONG,
            wallet_id="wallet_1",
            wallet_address="0x1111111111111111111111111111111111111111",
            private_key_hex="0x" + "1" * 64,
            quote_id="quote_1",
            position_id="pos_1",
            ticket_usd=Decimal("10"),
            leverage=Decimal("500"),
            notional_usd=Decimal("5000"),
            stop_loss_price=None,
            take_profit_price=None,
            liquidation_price=None,
            venue_position_id=None,
            quote_payload={},
        )

    def load_user_wallet_credentials(self, user_id: str) -> tuple[str, str]:
        assert user_id == "user_1"
        return "0x1111111111111111111111111111111111111111", "0x" + "1" * 64

    def load_user_wallet_context(self, user_id: str) -> tuple[str, str, str]:
        address, private_key = self.load_user_wallet_credentials(user_id)
        return "wallet_1", address, private_key


class FakeVenue:
    def __init__(self) -> None:
        self.preparations = 0

    def prepare_wallet(
        self,
        *,
        private_key_hex: str,
        required_collateral_usd: Decimal,
        ensure_transaction_gas=None,
    ):
        assert private_key_hex == "0x" + "1" * 64
        self.preparations += 1
        return {
            "allowanceReady": required_collateral_usd == Decimal("10"),
            "approvalSubmitted": False,
            "delegationReady": True,
        }


class BalanceVenue:
    def __init__(self, balances: list[Decimal]) -> None:
        self._balances = iter(balances)
        self.reads = 0

    def collateral_balance_usd(self, *, private_key_hex: str) -> Decimal:
        assert private_key_hex == "0x" + "1" * 64
        self.reads += 1
        return next(self._balances)


class UnexpectedBalanceReadVenue:
    def collateral_balance_usd(self, *, private_key_hex: str) -> Decimal:
        raise AssertionError("open hot path must not read collateral balance")


class NoGasAccounting:
    def total_charges_usdc(self, user_id: str) -> Decimal:
        return Decimal(0)


def test_execution_service_dry_run_does_not_trade() -> None:
    service = ExecutionService(settings=Settings(tick_real_execution_enabled=False), repository=FakeRepository())

    result = service.execute("exec_1")

    assert result["executionAttemptId"] == "exec_1"
    assert result["status"] == "dry_run"


def test_execution_service_prepares_user_wallet_before_swipe() -> None:
    service = ExecutionService(settings=Settings(), repository=FakeRepository())
    service._venue = FakeVenue()

    result = service.prepare_user_wallet("user_1", Decimal("10"))

    assert result["status"] == "ready"
    assert result["allowanceReady"] is True


def test_open_worker_authoritatively_prepares_an_uncached_wallet() -> None:
    repository = FakeRepository()
    venue = FakeVenue()
    service = ExecutionService(
        settings=Settings(
            tick_real_execution_enabled=True,
            gas_payer_mode="platform_agent",
        ),
        repository=repository,
    )
    service._venue = venue
    service._execute_live = lambda _context: {"status": "open"}

    result = service.execute("exec_1")

    assert result == {"status": "open"}
    assert venue.preparations == 1


def test_open_worker_uses_recent_successful_wallet_preparation() -> None:
    repository = FakeRepository()
    venue = FakeVenue()
    service = ExecutionService(
        settings=Settings(
            tick_real_execution_enabled=True,
            gas_payer_mode="platform_agent",
        ),
        repository=repository,
    )
    service._venue = venue
    service._execute_live = lambda _context: {"status": "open"}

    service.prepare_user_wallet("user_1", Decimal("10"))
    service.execute("exec_1")

    assert venue.preparations == 1


def test_close_balance_waits_for_returned_collateral() -> None:
    repository = FakeRepository()
    context = replace(
        repository.load("exec_1"),
        account_balance_before_open_usd=Decimal("42.76"),
    )
    venue = BalanceVenue([Decimal("32.76"), Decimal("32.76"), Decimal("41.50")])
    service = ExecutionService(settings=Settings(), repository=repository)
    service._venue = venue

    balance = service._wait_for_close_balance(context, timeout_seconds=0.1, poll_seconds=0)

    assert balance == Decimal("41.50")
    assert venue.reads == 3


def test_open_without_prepared_balance_does_not_block_on_rpc() -> None:
    repository = FakeRepository()
    context = repository.load("exec_1")
    service = ExecutionService(settings=Settings(), repository=repository)
    service._venue = UnexpectedBalanceReadVenue()

    service._require_open_balance(context)


def test_open_rejects_known_insufficient_spendable_balance() -> None:
    repository = FakeRepository()
    context = repository.load("exec_1")
    service = ExecutionService(
        settings=Settings(),
        repository=repository,
        gas_accounting=NoGasAccounting(),
    )
    service._remember_balance(context.user_id, Decimal("9.99"))

    with pytest.raises(InsufficientSpendableUSDC):
        service._require_open_balance(context)
