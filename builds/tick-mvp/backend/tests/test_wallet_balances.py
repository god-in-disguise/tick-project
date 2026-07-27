from decimal import Decimal

from tick_mvp.infrastructure.wallet_balances import _quantize


def test_quantize_supports_max_uint_allowance() -> None:
    allowance = Decimal(2**256 - 1) / Decimal(10**6)

    result = _quantize(allowance, 6)

    assert result == allowance
