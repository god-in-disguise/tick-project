from decimal import Decimal

from tick_mvp.domain.states import GasTopupStatus
from tick_mvp.wallets.gas import GasFundingService, GasTopupResult
from tick_mvp.wallets.gas_repository import GasTopupContext


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


class FakeExecutor:
    def __init__(self, balance: Decimal) -> None:
        self.balance = balance
        self.transfers = 0

    @property
    def platform_address(self) -> str:
        return "0x" + "99" * 20

    def native_balance(self, address: str) -> Decimal:
        return self.balance

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
