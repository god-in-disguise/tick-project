from decimal import Decimal

from tick_mvp.wallets.accounting import (
    GasAccountingService,
    GasTransaction,
    spendable_usdc,
)


class FakeOracle:
    def price(self):
        return Decimal("3500"), 1_784_000_000


class FakeRepository:
    def __init__(self) -> None:
        self.charges = []

    def record_charge(self, **kwargs):
        self.charges.append(kwargs)
        return kwargs["charge"].charge_usdc

    def total_charges_usdc(self, user_id: str) -> Decimal:
        return Decimal("0.123456")


def test_actual_native_gas_is_converted_to_usdc() -> None:
    repository = FakeRepository()
    service = GasAccountingService(repository=repository, oracle=FakeOracle())
    transaction = GasTransaction(
        tx_hash="0x" + "ab" * 32,
        gas_used=1_000_000,
        effective_gas_price=20_000_000,
        operation="open",
    )

    charge = service.charge(user_id="user_1", transaction=transaction)

    assert transaction.native_cost == Decimal("0.00002")
    assert charge.charge_usdc == Decimal("0.070000")
    assert repository.charges[0]["charge"] == charge


def test_spendable_usdc_reserves_platform_gas_charges() -> None:
    assert spendable_usdc(Decimal("42.76"), Decimal("0.123456")) == Decimal(
        "42.636544"
    )
    assert spendable_usdc(Decimal("0.05"), Decimal("0.10")) == Decimal(0)
