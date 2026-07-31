from decimal import Decimal

from tick_mvp.domain.states import GasSweepStatus, GasTopupStatus
from tick_mvp.wallets.gas import (
    GasFundingService,
    GasSweepResult,
    GasTopupResult,
    StaleGasTopupTransaction,
)
from tick_mvp.wallets.gas_repository import GasTopupContext
from tick_mvp.wallets.gas_sweep_repository import GasSweepContext


class FakeRepository:
    def __init__(self) -> None:
        self.context: GasTopupContext | None = None
        self.calls = []

    def create_or_load(self, **kwargs) -> GasTopupContext:
        self.calls.append(("create", kwargs))
        self.context = GasTopupContext(
            topup_id="gas_topup_1",
            user_id=kwargs["user_id"],
            wallet_id=kwargs["wallet_id"],
            wallet_address=kwargs["wallet_address"],
            amount_native=kwargs["amount_native"],
            status=GasTopupStatus.CREATED,
            tx_hash=None,
            nonce=None,
            signed_raw_transaction=None,
        )
        return self.context

    def mark_signed(self, topup_id: str, **kwargs) -> None:
        self.calls.append(("signed", topup_id, kwargs))

    def mark_broadcast(self, topup_id: str, **kwargs) -> None:
        self.calls.append(("broadcast", topup_id, kwargs))

    def mark_confirmed(self, topup_id: str, **kwargs) -> None:
        self.calls.append(("confirmed", topup_id, kwargs))

    def mark_reverted(self, topup_id: str, **kwargs) -> None:
        self.calls.append(("reverted", topup_id, kwargs))

    def mark_retryable_error(self, topup_id: str, error: str) -> None:
        self.calls.append(("retryable", topup_id, error))

    def mark_superseded(self, topup_id: str, **kwargs) -> None:
        self.calls.append(("superseded", topup_id, kwargs))


class FakeExecutor:
    def __init__(self, balance: Decimal) -> None:
        self.balance = balance
        self.transfers = 0

    @property
    def platform_address(self) -> str:
        return "0x" + "99" * 20

    def native_balance(self, address: str) -> Decimal:
        return self.balance

    def required_native(self, gas_units: int) -> Decimal:
        return Decimal(gas_units) / Decimal("10000000000")

    def transfer(self, context, *, on_prepared, on_broadcast) -> GasTopupResult:
        self.transfers += 1
        on_prepared("0x" + "ab" * 32, 4, "0x02cafe")
        on_broadcast("0x" + "ab" * 32, {"winner": "primary_rpc"})
        return GasTopupResult(
            status="confirmed",
            tx_hash="0x" + "ab" * 32,
            nonce=4,
            block_number=123,
            gas_used=21_000,
            effective_gas_price=20_000_000,
            gas_cost_native=Decimal("0.00000042"),
            payload={},
        )

    def close(self) -> None:
        pass


class FakeSweepRepository:
    def __init__(self, recoverable: Decimal) -> None:
        self.recoverable = recoverable
        self.context: GasSweepContext | None = None
        self.calls: list[tuple] = []

    def load_active(self, **kwargs):
        self.calls.append(("load_active", kwargs))
        return self.context

    def recoverable_native(self, **kwargs) -> Decimal:
        self.calls.append(("recoverable", kwargs))
        return self.recoverable

    def create_or_load(self, **kwargs) -> GasSweepContext:
        self.calls.append(("create", kwargs))
        self.context = GasSweepContext(
            sweep_id="gas_sweep_1",
            user_id=kwargs["user_id"],
            wallet_id=kwargs["wallet_id"],
            wallet_address=kwargs["wallet_address"],
            amount_native=kwargs["amount_native"],
            status=GasSweepStatus.CREATED,
            tx_hash=None,
            nonce=None,
            signed_raw_transaction=None,
        )
        return self.context

    def mark_signed(self, sweep_id: str, **kwargs) -> None:
        self.calls.append(("signed", sweep_id, kwargs))

    def mark_broadcast(self, sweep_id: str, **kwargs) -> None:
        self.calls.append(("broadcast", sweep_id, kwargs))

    def mark_confirmed(self, sweep_id: str, **kwargs) -> None:
        self.calls.append(("confirmed", sweep_id, kwargs))

    def mark_reverted(self, sweep_id: str, **kwargs) -> None:
        self.calls.append(("reverted", sweep_id, kwargs))

    def mark_retryable_error(self, sweep_id: str, error: str) -> None:
        self.calls.append(("retryable", sweep_id, error))

    def mark_superseded(self, sweep_id: str, **kwargs) -> None:
        self.calls.append(("superseded", sweep_id, kwargs))


class SweepExecutor(FakeExecutor):
    def sweep_plan(
        self,
        address: str,
        recoverable_native: Decimal,
    ) -> tuple[Decimal, Decimal]:
        return self.balance, min(self.balance, recoverable_native) - Decimal("0.00001")

    def sweep(
        self,
        context,
        *,
        private_key_hex,
        on_prepared,
        on_broadcast,
    ) -> GasSweepResult:
        tx_hash = "0x" + "cd" * 32
        on_prepared(tx_hash, 9, "0x02beef")
        on_broadcast(tx_hash, {"winner": "primary_rpc"})
        return GasSweepResult(
            status="confirmed",
            tx_hash=tx_hash,
            nonce=9,
            block_number=125,
            gas_used=21_000,
            effective_gas_price=10_000_000,
            amount_native=context.amount_native,
            gas_cost_native=Decimal("0.00000021"),
            payload={},
        )


class StaleThenSuccessfulExecutor(FakeExecutor):
    def transfer(self, context, *, on_prepared, on_broadcast) -> GasTopupResult:
        self.transfers += 1
        nonce = 31 if self.transfers == 1 else 33
        tx_hash = "0x" + ("31" if self.transfers == 1 else "33") * 32
        on_prepared(tx_hash, nonce, "0x02cafe")
        if self.transfers == 1:
            raise StaleGasTopupTransaction(tx_hash=tx_hash, nonce=nonce)
        on_broadcast(tx_hash, {"winner": "primary_rpc"})
        return GasTopupResult(
            status="confirmed",
            tx_hash=tx_hash,
            nonce=nonce,
            block_number=124,
            gas_used=21_000,
            effective_gas_price=20_000_000,
            gas_cost_native=Decimal("0.00000042"),
            payload={},
        )


def test_low_user_wallet_is_topped_up_to_target() -> None:
    repository = FakeRepository()
    executor = FakeExecutor(Decimal("0.0001"))
    service = GasFundingService(repository=repository, executor=executor)

    result = service.ensure_funded(
        user_id="user_1",
        wallet_id="wallet_1",
        wallet_address="0x" + "12" * 20,
    )

    assert result["status"] == "funded"
    assert result["amountEth"] == "0.0009"
    assert executor.transfers == 1
    assert [call[0] for call in repository.calls] == [
        "create",
        "signed",
        "broadcast",
        "confirmed",
    ]

    warm = service.ensure_funded(
        user_id="user_1",
        wallet_id="wallet_1",
        wallet_address="0x" + "12" * 20,
    )
    assert warm["source"] == "warm_cache"
    assert executor.transfers == 1


def test_funded_user_wallet_does_not_create_topup() -> None:
    repository = FakeRepository()
    executor = FakeExecutor(Decimal("0.0005"))
    service = GasFundingService(repository=repository, executor=executor)

    result = service.ensure_funded(
        user_id="user_1",
        wallet_id="wallet_1",
        wallet_address="0x" + "12" * 20,
    )

    assert result["status"] == "ready"
    assert repository.calls == []
    assert executor.transfers == 0


def test_stale_persisted_nonce_is_retired_and_resigned_once() -> None:
    repository = FakeRepository()
    executor = StaleThenSuccessfulExecutor(Decimal("0.0001"))
    service = GasFundingService(repository=repository, executor=executor)

    result = service.ensure_funded(
        user_id="user_1",
        wallet_id="wallet_1",
        wallet_address="0x" + "12" * 20,
    )

    assert result["status"] == "funded"
    assert executor.transfers == 2
    assert [call[0] for call in repository.calls] == [
        "create",
        "signed",
        "superseded",
        "create",
        "signed",
        "broadcast",
        "confirmed",
    ]


def test_operation_sized_topup_uses_required_gas_plus_buffer() -> None:
    repository = FakeRepository()
    executor = FakeExecutor(Decimal("0"))
    service = GasFundingService(
        repository=repository,
        sweep_repository=FakeSweepRepository(Decimal(0)),
        executor=executor,
    )

    result = service.ensure_funded(
        user_id="user_1",
        wallet_id="wallet_1",
        wallet_address="0x" + "12" * 20,
        required_gas_units=220_000,
    )

    assert result["requiredEth"] == "0.000042"
    assert result["amountEth"] == "0.000042"


def test_reclaim_sweeps_only_tracked_platform_reserve() -> None:
    sweep_repository = FakeSweepRepository(Decimal("0.0009"))
    executor = SweepExecutor(Decimal("0.001"))
    service = GasFundingService(
        repository=FakeRepository(),
        sweep_repository=sweep_repository,
        executor=executor,
    )

    result = service.reclaim_excess(
        user_id="user_1",
        wallet_id="wallet_1",
        wallet_address="0x" + "12" * 20,
        private_key_hex="0x" + "34" * 32,
    )

    assert result["status"] == "reclaimed"
    assert result["amountEth"] == "0.00089"
    assert [call[0] for call in sweep_repository.calls] == [
        "load_active",
        "recoverable",
        "create",
        "signed",
        "broadcast",
        "confirmed",
    ]


def test_reclaim_does_not_sweep_untracked_external_eth() -> None:
    sweep_repository = FakeSweepRepository(Decimal(0))
    service = GasFundingService(
        repository=FakeRepository(),
        sweep_repository=sweep_repository,
        executor=SweepExecutor(Decimal("1")),
    )

    result = service.reclaim_excess(
        user_id="user_1",
        wallet_id="wallet_1",
        wallet_address="0x" + "12" * 20,
        private_key_hex="0x" + "34" * 32,
    )

    assert result["status"] == "retained"
    assert not any(call[0] == "create" for call in sweep_repository.calls)
