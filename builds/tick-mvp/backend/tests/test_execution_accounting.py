from decimal import Decimal

from tick_mvp.domain.accounting import net_wallet_delta, whole_trade_wallet_delta


def test_whole_trade_wallet_delta_uses_pre_open_balance() -> None:
    result = whole_trade_wallet_delta(
        {"accountBalanceBeforeOpenUsd": "50.000000"},
        Decimal("48.882074"),
    )

    assert result == Decimal("-1.117926")


def test_whole_trade_wallet_delta_requires_complete_snapshots() -> None:
    assert whole_trade_wallet_delta({}, Decimal("48.882074")) is None
    assert whole_trade_wallet_delta({"accountBalanceBeforeOpenUsd": "50"}, None) is None


def test_net_wallet_delta_includes_platform_gas_ledger() -> None:
    result = net_wallet_delta(
        {"accountBalanceBeforeOpenUsd": "19.145902"},
        Decimal("22.472386"),
        Decimal("-0.105111"),
    )

    assert result == Decimal("3.221373")
