from __future__ import annotations

from decimal import Decimal
from typing import Any


def whole_trade_wallet_delta(
    position_payload: dict[str, Any] | None,
    account_balance_after_usd: Decimal | None,
) -> Decimal | None:
    if account_balance_after_usd is None:
        return None
    raw_baseline = (position_payload or {}).get("accountBalanceBeforeOpenUsd")
    if raw_baseline is None:
        return None
    return account_balance_after_usd - Decimal(str(raw_baseline))


def net_wallet_delta(
    position_payload: dict[str, Any] | None,
    account_balance_after_usd: Decimal | None,
    gas_ledger_total_usd: Decimal = Decimal(0),
) -> Decimal | None:
    wallet_delta = whole_trade_wallet_delta(
        position_payload,
        account_balance_after_usd,
    )
    if wallet_delta is None:
        return None
    return wallet_delta + gas_ledger_total_usd


def reconciliation_difference(
    wallet_delta_usd: Decimal | None,
    venue_realized_pnl_usd: Decimal | None,
    gas_ledger_total_usd: Decimal = Decimal(0),
) -> Decimal | None:
    if wallet_delta_usd is None or venue_realized_pnl_usd is None:
        return None
    expected_net = venue_realized_pnl_usd + gas_ledger_total_usd
    return wallet_delta_usd - expected_net
