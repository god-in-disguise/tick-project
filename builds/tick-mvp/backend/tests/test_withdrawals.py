from __future__ import annotations

from decimal import Decimal

import pytest

from tick_mvp.core.config import Settings
from tick_mvp.domain.states import WithdrawalStatus
from tick_mvp.wallets.arbitrum import (
    WalletTransferResult,
    WithdrawalRejected,
    WithdrawalRetryable,
    _amount_units,
)
from tick_mvp.wallets.repository import WithdrawalContext
from tick_mvp.wallets.service import WithdrawalService


TX_HASH = "0x" + "ab" * 32
RAW_TRANSACTION = "0x02cafe"


class FakeRepository:
    def __init__(self, context: WithdrawalContext) -> None:
        self.context = context
        self.calls: list[tuple] = []

    def load(self, withdrawal_id: str) -> WithdrawalContext:
        self.calls.append(("load", withdrawal_id))
        return self.context

    def mark_signed(self, withdrawal_id: str, **kwargs) -> None:
        self.calls.append(("signed", withdrawal_id, kwargs))

    def mark_broadcast(self, withdrawal_id: str, **kwargs) -> None:
        self.calls.append(("broadcast", withdrawal_id, kwargs))

    def mark_confirmed(self, withdrawal_id: str, **kwargs) -> None:
        self.calls.append(("confirmed", withdrawal_id, kwargs))

    def mark_reverted(self, withdrawal_id: str, **kwargs) -> None:
        self.calls.append(("reverted", withdrawal_id, kwargs))

    def mark_failed(self, withdrawal_id: str, error: str) -> None:
        self.calls.append(("failed", withdrawal_id, error))

    def mark_retryable_error(self, withdrawal_id: str, error: str) -> None:
        self.calls.append(("retryable", withdrawal_id, error))


class FakeExecutor:
    def __init__(
        self,
        result: WalletTransferResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def transfer(self, context, *, on_prepared, on_broadcast):
        self.calls += 1
        if self.error is not None:
            raise self.error
        on_prepared(TX_HASH, 7, RAW_TRANSACTION)
        on_broadcast(TX_HASH, {"winner": "primary_rpc"})
        return self.result

    def close(self) -> None:
        pass


def test_confirmed_withdrawal_persists_before_broadcast() -> None:
    repository = FakeRepository(_context())
    executor = FakeExecutor(_confirmed_result())
    service = WithdrawalService(
        settings=Settings(tick_real_execution_enabled=True),
        repository=repository,
        executor=executor,
    )

    result = service.execute("withdrawal_1")

    assert result["status"] == "confirmed"
    assert [call[0] for call in repository.calls] == [
        "load",
        "signed",
        "broadcast",
        "confirmed",
    ]
    assert repository.calls[1][2]["signed_raw_transaction"] == RAW_TRANSACTION


def test_dry_run_does_not_claim_or_mutate_withdrawal() -> None:
    repository = FakeRepository(_context(status=WithdrawalStatus.REQUESTED))
    executor = FakeExecutor(_confirmed_result())
    service = WithdrawalService(
        settings=Settings(tick_real_execution_enabled=False),
        repository=repository,
        executor=executor,
    )

    result = service.execute("withdrawal_1")

    assert result["status"] == "dry_run"
    assert repository.calls == []
    assert executor.calls == 0


def test_terminal_withdrawal_is_not_submitted_twice() -> None:
    repository = FakeRepository(
        _context(status=WithdrawalStatus.CONFIRMED, tx_hash=TX_HASH)
    )
    executor = FakeExecutor(_confirmed_result())
    service = WithdrawalService(
        settings=Settings(tick_real_execution_enabled=True),
        repository=repository,
        executor=executor,
    )

    result = service.execute("withdrawal_1")

    assert result["alreadyTerminal"] is True
    assert executor.calls == 0


def test_permanent_rejection_marks_failed_without_retry() -> None:
    repository = FakeRepository(_context())
    executor = FakeExecutor(error=WithdrawalRejected("insufficient USDC balance"))
    service = WithdrawalService(
        settings=Settings(tick_real_execution_enabled=True),
        repository=repository,
        executor=executor,
    )

    result = service.execute("withdrawal_1")

    assert result["status"] == "failed"
    assert repository.calls[-1] == (
        "failed",
        "withdrawal_1",
        "insufficient USDC balance",
    )


def test_transport_error_remains_retryable() -> None:
    repository = FakeRepository(_context())
    executor = FakeExecutor(error=TimeoutError("RPC timeout"))
    service = WithdrawalService(
        settings=Settings(tick_real_execution_enabled=True),
        repository=repository,
        executor=executor,
    )

    with pytest.raises(WithdrawalRetryable, match="RPC timeout"):
        service.execute("withdrawal_1")

    assert repository.calls[-1][0] == "retryable"


def test_usdc_amount_rejects_more_than_six_decimals() -> None:
    assert _amount_units(Decimal("10.123456")) == 10_123_456
    with pytest.raises(WithdrawalRejected, match="6 decimal"):
        _amount_units(Decimal("10.1234567"))


def _context(
    *,
    status: WithdrawalStatus = WithdrawalStatus.VALIDATED,
    tx_hash: str | None = None,
) -> WithdrawalContext:
    return WithdrawalContext(
        withdrawal_id="withdrawal_1",
        user_id="user_1",
        wallet_id="wallet_1",
        wallet_address="0x" + "12" * 20,
        private_key_hex="0x" + "34" * 32,
        asset="USDC",
        amount=Decimal("10"),
        destination_address="0x" + "56" * 20,
        status=status,
        tx_hash=tx_hash,
        nonce=7 if tx_hash else None,
        signed_raw_transaction=RAW_TRANSACTION if tx_hash else None,
    )


def _confirmed_result() -> WalletTransferResult:
    return WalletTransferResult(
        status="confirmed",
        tx_hash=TX_HASH,
        nonce=7,
        block_number=123,
        gas_used=55_000,
        effective_gas_price=10_000_000,
        gas_cost_native=Decimal("0.00000055"),
        payload={"timingMs": {"total": 900}},
    )
